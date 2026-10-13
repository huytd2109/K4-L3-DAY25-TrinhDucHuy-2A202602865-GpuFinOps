"""M2 — Inference Cost Levers: $/1M-token, batch x cache x cascade (deck §7).

Run: python missions/m2_inference_levers.py
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from missions._common import load_csv, num
from finops import pricing, sustainability

# $/1M tokens (input, output) — illustrative 2026.
MODEL_PRICES = {"small": (0.20, 0.40), "large": (3.00, 15.00)}
# Scenario assumptions, NOT measured prefix reuse or provider quotes. The CSV
# contains reads only; amortize additional writes outside the log over these reads.
AVG_CACHE_READS = 4.0
CACHE_WRITE_PER_M = 1.0
REASONING_CAP = 0.10
REASONING_OUTPUT_MULTIPLIER = 6  # data/generate.py uses six times the output tokens


def optimized_request_cost(row: dict, avg_cache_reads: float = AVG_CACHE_READS,
                           write_cost_per_m: float = CACHE_WRITE_PER_M) -> float:
    """Cascade + batch + profitable cache reads including amortized write cost."""
    inp, out = int(num(row["input_tokens"])), int(num(row["output_tokens"]))
    pin, pout = MODEL_PRICES[row["route_tier"]]
    batch = bool(int(num(row["is_batch"])))
    cached = min(inp, max(0, int(num(row["cached_input_tokens"]))))
    use_cache = cached > 0 and pricing.cache_is_worth_it(
        avg_cache_reads, write_cost_per_m, price_in_per_m=pin, batch=batch)
    cost = pricing.request_cost(inp, out, pin, pout,
                                cached_in=cached if use_cache else 0, batch=batch)
    if use_cache:
        cost += cached / 1e6 * write_cost_per_m / avg_cache_reads
    return cost


def reasoning_budget(rows: list[dict], cap_fraction: float = REASONING_CAP,
                     avg_cache_reads: float = AVG_CACHE_READS,
                     write_cost_per_m: float = CACHE_WRITE_PER_M) -> dict:
    """Simulate a traffic cap, retaining all requests and demoting excess reasoning.

    Demotion keeps input, route, cache and batch unchanged, divides output by the
    generator's factor six (rounded), and removes the 80x lab energy multiplier.
    CSV order chooses which requests to demote; quality/latency are not evaluated.
    """
    if not 0 <= cap_fraction <= 1:
        raise ValueError("Reasoning cap must be between zero and one")
    groups = {flag: {"requests": 0, "tokens": 0, "cost_usd": 0.0, "wh": 0.0}
              for flag in (0, 1)}
    remaining = int(len(rows) * cap_fraction)
    after = {"requests": len(rows), "reasoning_requests": 0, "tokens": 0,
             "cost_usd": 0.0, "wh": 0.0, "demoted_requests": 0}
    for row in rows:
        reasoning = bool(int(num(row["is_reasoning"])))
        tokens = int(num(row["input_tokens"])) + int(num(row["output_tokens"]))
        g = groups[int(reasoning)]
        g["requests"] += 1
        g["tokens"] += tokens
        g["cost_usd"] += optimized_request_cost(row, avg_cache_reads, write_cost_per_m)
        g["wh"] += sustainability.wh_per_query(tokens, is_reasoning=reasoning)
        capped = dict(row)
        if reasoning and remaining <= 0:
            capped["output_tokens"] = round(int(num(row["output_tokens"])) / REASONING_OUTPUT_MULTIPLIER)
            reasoning = False
            after["demoted_requests"] += 1
        elif reasoning:
            remaining -= 1
            after["reasoning_requests"] += 1
        capped_tokens = int(num(capped["input_tokens"])) + int(num(capped["output_tokens"]))
        after["tokens"] += capped_tokens
        after["cost_usd"] += optimized_request_cost(capped, avg_cache_reads, write_cost_per_m)
        after["wh"] += sustainability.wh_per_query(capped_tokens, is_reasoning=reasoning)
    before = {"requests": len(rows), "reasoning_requests": groups[1]["requests"],
              "tokens": sum(g["tokens"] for g in groups.values()),
              "cost_usd": sum(optimized_request_cost(row, avg_cache_reads, write_cost_per_m) for row in rows),
              "wh": sum(g["wh"] for g in groups.values())}
    if not after["demoted_requests"]:
        after.update(before)
    for g in groups.values():
        for key in ("requests", "tokens", "cost_usd", "wh"):
            g[key + "_share"] = g[key] / before[key] if before[key] else 0.0
    # Avoid floating-point residue being reported as savings below the cap.
    cost_saved = before["cost_usd"] - after["cost_usd"] if after["demoted_requests"] else 0.0
    wh_saved = before["wh"] - after["wh"] if after["demoted_requests"] else 0.0
    return {"groups": groups, "before": before, "after": after,
            "cap_fraction": cap_fraction, "saved_usd": cost_saved, "saved_wh": wh_saved}


def run(verbose: bool = True, avg_cache_reads: float = AVG_CACHE_READS,
        write_cost_per_m: float = CACHE_WRITE_PER_M) -> dict:
    rows = load_csv("token_usage.csv")
    base_cost = cascade_cost = cache_cost = legacy_cost = no_cache_cost = 0.0
    optimized_costs = []
    total_tokens = 0
    for r in rows:
        inp, out = int(num(r["input_tokens"])), int(num(r["output_tokens"]))
        cached = int(num(r["cached_input_tokens"]))
        is_batch = bool(int(num(r["is_batch"])))
        total_tokens += inp + out
        # BASELINE: naive deployment — everything on the large model, no cache, no batch
        lin, lout = MODEL_PRICES["large"]
        base_cost += pricing.request_cost(inp, out, lin, lout)
        # OPTIMIZED: cascade (route_tier), prompt caching, batch API
        pin, pout = MODEL_PRICES[r["route_tier"]]
        cascade_cost += pricing.request_cost(inp, out, pin, pout)
        cache_cost += pricing.request_cost(inp, out, pin, pout, cached_in=cached)
        legacy_cost += pricing.request_cost(inp, out, pin, pout, cached_in=cached, batch=is_batch)
        no_cache_cost += pricing.request_cost(inp, out, pin, pout, batch=is_batch)
        optimized_costs.append(optimized_request_cost(r, avg_cache_reads, write_cost_per_m))

    # Use the same summation as the scenario, allocation and reasoning summaries.
    opt_cost = sum(optimized_costs)
    base_pm = pricing.dollars_per_million(base_cost, total_tokens)
    opt_pm = pricing.dollars_per_million(opt_cost, total_tokens)
    savings_pct = (1 - opt_cost / base_cost) * 100 if base_cost else 0.0
    stages = [
        {"stage": name, "daily_usd": cost,
         "per_m": pricing.dollars_per_million(cost, total_tokens)}
        for name, cost in [("Baseline", base_cost), ("Cascade", cascade_cost),
                           ("Cascade + cache (reads only)", cache_cost),
                           ("Cascade + cache + batch (original)", legacy_cost),
                           ("Cascade + batch (no cache)", no_cache_cost),
                           ("Profitable cache + writes + batch", opt_cost)]]
    scenarios = []
    for reads in (1.0, avg_cache_reads, 16.0):
        cost = sum(optimized_request_cost(r, reads, write_cost_per_m) for r in rows)
        scenarios.append({"reads": reads, "daily_usd": cost,
                          "per_m": pricing.dollars_per_million(cost, total_tokens)})
    thresholds = []
    for tier, (pin, _) in MODEL_PRICES.items():
        for batch in (False, True):
            thresholds.append({"tier": tier, "batch": batch,
                               "break_even_reads": write_cost_per_m / (pin * 0.90 * (0.50 if batch else 1.0))})
    reasoning = reasoning_budget(rows, avg_cache_reads=avg_cache_reads, write_cost_per_m=write_cost_per_m)

    if verbose:
        print("== M2 Inference Cost Levers ==")
        print(f"requests={len(rows)}  tokens={total_tokens:,}")
        print(f"baseline  : ${base_cost:,.2f}/day   ${base_pm:.3f}/1M-token")
        print(f"optimized : ${opt_cost:,.2f}/day   ${opt_pm:.3f}/1M-token")
        print(f"savings   : {savings_pct:.1f}%  (cascade + caching + batch)")
        print(f"discount stack (batch + 100% cache): {pricing.discount_stack(batch=True, cache_hit_frac=1.0):.3f} of naive")
        print("Sequential levers / cache extension (same token denominator):")
        for stage in stages:
            print(f"  {stage['stage']}: ${stage['daily_usd']:.6f}/day  ${stage['per_m']:.6f}/1M-token")
        print(f"Assumed cache writes=${write_cost_per_m:.2f}/1M prefix tokens; reads/write={avg_cache_reads:g}; writes not batch-discounted")
        for threshold in thresholds:
            print(f"  {threshold['tier']} batch={threshold['batch']}: reads > {threshold['break_even_reads']:.6f}")
        for scenario in scenarios:
            print(f"  reads/write={scenario['reads']:g}: ${scenario['daily_usd']:.6f}/day  ${scenario['per_m']:.6f}/1M-token")
        for flag, group in reasoning["groups"].items():
            print(f"  reasoning={flag}: {group['requests']} requests ({group['requests_share']:.3%}), "
                  f"{group['tokens']:,} tokens, ${group['cost_usd']:.6f} ({group['cost_usd_share']:.3%}), "
                  f"{group['wh']:.3f} Wh ({group['wh_share']:.3%})")
        print(f"Reasoning cap={REASONING_CAP:.0%}: demoted={reasoning['after']['demoted_requests']}, "
              f"saved=${reasoning['saved_usd']:.6f}, {reasoning['saved_wh']:.3f} Wh")

    return {
        "baseline_daily": round(base_cost, 2), "optimized_daily": round(opt_cost, 2),
        "baseline_per_m": round(base_pm, 3), "optimized_per_m": round(opt_pm, 3),
        "savings_pct": round(savings_pct, 1), "total_tokens": total_tokens,
        "stages": stages, "cache_scenarios": scenarios, "cache_thresholds": thresholds,
        "cache_assumptions": {"avg_reads": avg_cache_reads, "write_cost_per_m": write_cost_per_m},
        "reasoning": reasoning,
    }


if __name__ == "__main__":
    run()
