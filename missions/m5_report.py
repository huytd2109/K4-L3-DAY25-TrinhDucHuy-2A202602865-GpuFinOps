"""M5 — Optimization Report: combine M1-M4 into baseline-vs-optimized (deck §1/§11).

Run: python missions/m5_report.py   ->  outputs/report.md + outputs/savings.png
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import os
import hashlib
from missions._common import num, catalog_by_type, load_csv, ROOT
from finops import report, sustainability
from missions import m1_efficiency_audit, m2_inference_levers, m3_purchasing, m4_allocation

DAYS = 30
# one tier down for over-provisioned ("util-lie") GPUs
RIGHTSIZE_MAP = {"H100": "A100", "H200": "H100", "A100": "A10G", "A10G": "L4", "L4": "L4"}


def lab_analysis(r1: dict, r2: dict, r3: dict, r4: dict, baseline: float,
                 optimized: float, levers: dict, cat: dict) -> str:
    """Reproducible evidence and Guide answers in the existing report artifact."""
    stages = r2["stages"]
    original_levers = dict(levers)
    original_levers["Inference (cascade/cache/batch)"] = round(
        (round(stages[0]["daily_usd"], 2) - round(stages[3]["daily_usd"], 2)) * DAYS)
    original_baseline = round(stages[0]["daily_usd"], 2) * DAYS + r3["on_demand_monthly"]
    original_optimized = original_baseline - sum(original_levers.values())
    lines = [
        "", "## Phạm vi và dữ liệu", "",
        "Bài thực hành chạy bằng Python trong `.venv` của Day25; dữ liệu tổng hợp seed=25. "
        "Giá model/GPU, hệ số điện và carbon là giả định của lab, không phải báo giá hiện tại. "
        "Không chạy GPU, cloud hay API bên ngoài. Chọn extension 3 (cache) và 4 (reasoning).",
        "", "| CSV | Số dòng | SHA-256 |", "|---|---:|---|",
    ]
    for filename in ("price_catalog.csv", "gpu_telemetry.csv", "token_usage.csv", "workloads.csv"):
        with open(os.path.join(ROOT, "data", filename), "rb") as source:
            digest = hashlib.sha256(source.read()).hexdigest()
        lines.append(f"| {filename} | {len(load_csv(filename))} | `{digest}` |")
    lines += [
        "", "Đã đọc bốn CSV bằng `pandas.read_csv` trước khi sửa. Catalog có giá các tier, "
        "HBM, peak FLOPs và bandwidth; telemetry có util/MFU/MBU và bộ nhớ thực dùng; "
        "token log có route/cache/batch/reasoning/tags; workloads có giờ/ngày, ngày chạy và số GPU.",
        "", "## Kết quả trước/sau trên cùng dữ liệu", "",
        "Đã chạy M1–M5 trước khi sửa. Cột trước được tái tính bằng công thức gốc "
        "(cache chỉ tính read, không write) để giữ kết quả đối chiếu khi chạy lại.",
        "", "| Chỉ số | Trước mở rộng | Sau mở rộng |", "|---|---:|---:|",
        f"| M2 USD/ngày optimized | {stages[3]['daily_usd']:.6f} | {stages[5]['daily_usd']:.6f} |",
        f"| M2 USD/1M-token optimized | {stages[3]['per_m']:.6f} | {stages[5]['per_m']:.6f} |",
        f"| M2 savings | {(1-stages[3]['daily_usd']/stages[0]['daily_usd'])*100:.3f}% | {r2['savings_pct']:.1f}% |",
        f"| M3 on-demand / optimized, USD/tháng | {r3['on_demand_monthly']:,} / {r3['optimized_monthly']:,} | {r3['on_demand_monthly']:,} / {r3['optimized_monthly']:,} |",
        f"| M3 savings | {r3['savings_pct']:.1f}% | {r3['savings_pct']:.1f}% |",
        f"| M5 baseline, USD/tháng | {original_baseline:,.0f} | {baseline:,.0f} |",
        f"| M5 optimized, USD/tháng | {original_optimized:,.0f} | {optimized:,.0f} |",
        f"| M5 projected savings | {(1-original_optimized/original_baseline)*100:.3f}% | {(1-optimized/baseline)*100:.3f}% |",
        "", "## M1 — Guide 4.3", "",
        "| GPU | Loại | Util % | MFU | MBU | Idle giờ/ngày |", "|---|---|---:|---:|---:|---:|",
    ]
    for gpu in r1["summary"]:
        lines.append(f"| {gpu['gpu_id']} | {gpu['gpu_type']} | {gpu['gpu_util_pct']:.1f} | {gpu['mfu']:.3f} | {gpu['mbu']:.3f} | {gpu['idle_hours']} |")
    busiest = max(r1["summary"], key=lambda gpu: gpu["gpu_util_pct"])
    fleet_monthly = sum(num(cat[gpu["gpu_type"]]["on_demand_hr"]) * 24 * DAYS for gpu in r1["summary"])
    idle_monthly = r1["idle_waste_daily"] * DAYS
    lines += [
        "", f"1. Util trung bình cao nhất: `{busiest['gpu_id']}` = {busiest['gpu_util_pct']:.1f}%, MFU={busiest['mfu']:.3f}. "
        f"Các GPU bị flag: {', '.join('`'+gpu['gpu_id']+'`' for gpu in r1['lies'])}.",
        "2. GPU-Util đo thời gian có kernel hoạt động; MFU đo FLOPs đạt được/peak. "
        "Memory stall, kernel launch overhead hoặc I/O có thể làm GPU bận nhưng ít FLOPs. "
        "Đây là giả thuyết cần profiler xác nhận; MBU thấp riêng lẻ chưa chứng minh memory-bound.",
        f"3. Idle: ${r1['idle_waste_daily']:.2f}/ngày = ${idle_monthly:,.0f}/tháng; "
        f"{idle_monthly/baseline:.2%} baseline tổng M5, hoặc {idle_monthly/fleet_monthly:.2%} "
        f"hóa đơn fleet telemetry on-demand 24h/ngày (${fleet_monthly:,.2f}/tháng). Hai mẫu dữ liệu có phạm vi khác nhau.",
        "", "## M2 — Guide 5.4 và extension 3: cache có đáng dùng?", "",
        "| Bước tuần tự | USD/ngày | USD/1M-token | Giảm so bước trước, USD/ngày |", "|---|---:|---:|---:|",
    ]
    for index, stage in enumerate(stages[:4]):
        delta = stages[index-1]["daily_usd"] - stage["daily_usd"] if index else 0.0
        lines.append(f"| {stage['stage']} | {stage['daily_usd']:.6f} | {stage['per_m']:.6f} | {delta:.6f} |")
    contributions = {"cascade": stages[0]["daily_usd"]-stages[1]["daily_usd"],
                     "cache": stages[1]["daily_usd"]-stages[2]["daily_usd"],
                     "batch": stages[2]["daily_usd"]-stages[3]["daily_usd"]}
    assumptions = r2["cache_assumptions"]
    lines += [
        "", f"1. `{max(contributions, key=contributions.get)}` đóng góp lớn nhất trong thứ tự cascade → cache → batch. "
        "Các khoản trên là marginal savings theo thứ tự này, không phải hiệu quả độc lập để cộng tùy ý.",
        "2. `0.05 = 0.50 × 0.10`: chiết khấu batch nhân với giá cached input. "
        "Đây là góc nhìn input 100% cached; output vẫn có giá riêng nên cả request không nhất thiết giảm 95%.",
        "3. Không dùng batch cho chat tương tác hoặc tác vụ cần phản hồi tức thì; ưu tiên eval/offline cho phép chờ.",
        "", f"**Giả định extension:** phí ghi bổ sung ${assumptions['write_cost_per_m']:.2f}/1M prefix token, "
        f"{assumptions['avg_reads']:g} reads/write ở cấu hình mặc định, cached read giá 0.10× input. "
        "Writes nằm ngoài token log, được phân bổ `cached_tokens / reads_per_write`; không giảm giá ghi theo batch. "
        "CSV không có prefix ID/số lần đọc nên không thể suy ra reuse thực tế; đây là phân tích kịch bản, "
        f"chưa bao gồm TTL/lưu trữ. Denominator luôn là cùng {r2['total_tokens']:,} token phục vụ trên dữ liệu này.",
        "", "`reads_hòa_vốn = write_USD_per_M / (input_USD_per_M × 0.90 × batch_factor)`. "
        "Chỉ bật cache khi reads lớn hơn ngưỡng; bằng ngưỡng không có lợi nhuận.",
        "", "| Model | Batch | Reads hòa vốn |", "|---|---|---:|",
    ]
    for threshold in r2["cache_thresholds"]:
        lines.append(f"| {threshold['tier']} | {threshold['batch']} | {threshold['break_even_reads']:.6f} |")
    lines += ["", "| Kịch bản cache | USD/ngày | USD/1M-token |", "|---|---:|---:|",
              f"| Không cache, cascade + batch | {stages[4]['daily_usd']:.6f} | {stages[4]['per_m']:.6f} |",
              f"| Gốc: reads only, chưa tính writes | {stages[3]['daily_usd']:.6f} | {stages[3]['per_m']:.6f} |"]
    for scenario in r2["cache_scenarios"]:
        lines.append(f"| {scenario['reads']:g} reads/write, có gate + writes | {scenario['daily_usd']:.6f} | {scenario['per_m']:.6f} |")
    lines += ["", "Với 4 reads/write, small bị tắt cache (cả batch và non-batch), large được bật. "
              "Ít reads làm phí ghi khó hoàn vốn; 16 reads/write vượt tất cả ngưỡng. "
              "Chi phí sau mở rộng cao hơn công thức gốc vì gốc bỏ phí ghi; không phải một khoản tiết kiệm mới.",
              "", "## Extension 4 — Ngân sách reasoning", "",
              "| is_reasoning | Requests | % request | Tokens | % token | USD/ngày | % chi phí | Wh/ngày | % năng lượng |",
              "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    reasoning = r2["reasoning"]
    for flag, group in reasoning["groups"].items():
        lines.append(f"| {flag} | {group['requests']} | {group['requests_share']:.3%} | {group['tokens']:,} | "
                     f"{group['tokens_share']:.3%} | {group['cost_usd']:.6f} | {group['cost_usd_share']:.3%} | "
                     f"{group['wh']:.3f} | {group['wh_share']:.3%} |")
    lines += ["", "| Cap 10% traffic | Requests | Reasoning requests | Tokens | USD/ngày | Wh/ngày |", "|---|---:|---:|---:|---:|---:|"]
    for label, values in [("Trước cap", reasoning["before"]), ("Sau cap", reasoning["after"])]:
        lines.append(f"| {label} | {values['requests']} | {values['reasoning_requests']} | {values['tokens']:,} | {values['cost_usd']:.6f} | {values['wh']:.3f} |")
    lines += [
        "", f"Demoted={reasoning['after']['demoted_requests']}; savings=${reasoning['saved_usd']:.6f}/ngày "
        f"và {reasoning['saved_wh']:.3f} Wh/ngày. Traffic reasoning hiện dưới 10%, nên savings bằng 0; "
        "không đổi model, output hoặc số request ở dữ liệu này.",
        "`wh_per_query` của lab dùng 0.30 Wh/1k token và hệ số 80× khi reasoning; output của "
        "generator còn dài 6×. Các hệ số này là mô hình ước lượng, không phải điện đo thực tế. "
        "Nếu vượt cap, mô phỏng giữ tối đa floor(10% × requests) reasoning theo thứ tự CSV; "
        "phần vượt chuyển sang non-reasoning, giữ input/route/cache/batch, output chia 6 (làm tròn) "
        "và bỏ hệ số năng lượng 80×. Savings khi đó phải kiểm tra lại chất lượng và độ dài output.",
        "Đề xuất chỉ dùng reasoning cho tác vụ nhiều bước hoặc sau khi câu trả lời thường không đạt "
        "bộ kiểm tra chất lượng; cap là ngân sách trần, không phải quota bắt buộc dùng hết. "
        "Dataset không có confidence/quality score nên chưa kiểm chứng được rule routing này.",
        "", "## M3 — Guide 6.4", "",
        "| Job | Ngày thực tế | GPU | Tier | On-demand USD/30 ngày | Optimized USD/30 ngày |", "|---|---:|---|---|---:|---:|",
    ]
    days = {job["job_id"]: job["days"] for job in load_csv("workloads.csv")}
    for job in r3["recommendations"]:
        lines.append(f"| {job['job_id']} | {days[job['job_id']]} | {job['gpu_type']} | {job['tier']} | {job['on_demand']:,} | {job['optimized']:,} |")
    lines += [
        "", "1. Spot: job-train-llm, job-train-embed, job-finetune, job-dev-sandbox, job-batch-eval; "
        "đều interruptible=1, giờ/ngày <24. Cần checkpoint và chấp nhận job kéo dài khi bị thu hồi.",
        "2. Effective hours = GPU-hours × (1 + 0.03) + GPU-hours × 0.05 × 0.5 = 1.055 × GPU-hours. "
        "Phần tăng là overhead checkpoint và tính lại phần việc mất; đây là kỳ vọng mô hình.",
        "3. Ba job inference được reserved theo duty cycle; tuy nhiên chỉ có 30 ngày workload, "
        "chưa đủ căn cứ cam kết 3 năm. Khi chưa chứng minh nhu cầu dài hạn, on-demand có thể phù hợp hơn. "
        "M3 gốc bỏ qua cột days và tính reserved theo giờ dùng thay vì toàn bộ giờ cam kết; "
        "đặc biệt job-infer-search chạy 18h/ngày chưa tính 6h reserved không dùng. "
        "Bảng này giữ nguyên policy để đối chiếu, không phải quyết định mua đã xác nhận.",
        "", "## M4 — Guide 7.4", "",
        "M4 dùng chung hàm tính chi phí mới của M2, gồm cache gate và phí ghi phân bổ.",
        "", "| Team | USD/ngày | % tổng |", "|---|---:|---:|",
    ]
    for team, cost in sorted(r4["by_team_exact"].items(), key=lambda item: -item[1]):
        lines.append(f"| {team} | {cost:.6f} | {cost/r4['total_daily']:.3%} |")
    top = max(r4["by_team_exact"], key=r4["by_team_exact"].get)
    tagged = sum(all(row[key].strip() for key in ("team", "project")) for row in load_csv("token_usage.csv"))
    lines += [
        "", f"1. `{top}` tốn nhiều nhất: {r4['by_team_exact'][top]/r4['total_daily']:.3%} tổng inference optimized.",
        f"2. Có {tagged}/2400 requests đủ team/project ({tagged/2400:.3%}); vượt gate 80%, "
        f"chargeback ready={r4['chargeback_ready']}. Cần tiếp tục sửa các project thiếu tag trước phân bổ đầy đủ.",
        "3. FOCUS giúp chuẩn hóa tên cột, đơn vị và kỳ chi phí giữa các nhà cung cấp để so sánh/phân bổ. "
        "`focus_export.csv` là mẫu 50 request đầu, có BilledCost/team/project; tổng mẫu không phải tổng 2400 request. "
        "Đây là export FOCUS-style tối giản, chưa phải chứng nhận tuân thủ đầy đủ chuẩn.",
        "", "## Điện, carbon và ưu tiên thực hiện", "",
        "Sustainability đầu báo cáo dùng trung bình Wh/request thực tính từ toàn bộ token log, gồm reasoning. "
        "Ví dụ 800 token không reasoning của code gốc = 0.24 Wh và 0.0912 gCO2e ở us-east-1, "
        "không đại diện cho trung bình dữ liệu này.",
        "", "| Vùng | USD/kWh | gCO2e/kWh | USD điện/ngày | gCO2e/ngày |", "|---|---:|---:|---:|---:|",
    ]
    total_wh = reasoning["before"]["wh"]
    for region, carbon in sustainability.REGION_CARBON.items():
        lines.append(f"| {region} | {sustainability.REGION_PRICE_KWH[region]:.3f} | {carbon} | "
                     f"{sustainability.energy_cost_usd(total_wh, region):.6f} | {sustainability.carbon_g(total_wh, region):.3f} |")
    lines += [
        "", "Sạch nhất: europe-north1 (30 g/kWh); điện rẻ nhất: us-east-wa ($0.055/kWh). "
        "Cùng lượng công việc/năng lượng, chọn vùng sạch giảm carbon nhưng không nhất thiết có điện rẻ nhất. "
        "Giá điện không phải giá thuê GPU; không cộng tiền điện vào bill thuê để tránh đếm trùng. "
        "Cần kiểm tra latency, dữ liệu và GPU sẵn có trước khi đổi vùng.",
        "", "Ưu tiên: (1) xác minh purchasing/nhu cầu cam kết vì đây là lever lớn nhất trong mô hình; "
        "(2) triển khai cascade có gate chất lượng, cache có gate chi phí và batch cho offline; "
        "(3) tắt GPU ở 8 giờ idle đã phát hiện; (4) chỉ right-size sau benchmark bộ nhớ, throughput và latency. "
        "Theo dõi riêng ngân sách reasoning và vùng carbon khi SLA cho phép.",
        "", "**Giới hạn tổng M5:** tổng và biểu đồ là projected savings theo bốn bucket của lab, "
        "quy đổi 30 ngày; không phải mức tiết kiệm thực đo. Right-size gốc dùng map H100→A100/A10G→L4 "
        "chưa kiểm tra capacity/throughput. Telemetry, workloads và token log không có join key chung, "
        "nên không chứng minh được idle/right-size độc lập với purchasing; có nguy cơ cộng trùng savings. "
        "Không diễn giải 46% này thành cam kết business impact hoặc độ chính xác/hiệu năng model.",
    ]
    return "\n".join(lines) + "\n"


def run(verbose: bool = True) -> dict:
    r1 = m1_efficiency_audit.run(verbose=False)
    r2 = m2_inference_levers.run(verbose=False)
    r3 = m3_purchasing.run(verbose=False)
    r4 = m4_allocation.run(verbose=False)
    cat = catalog_by_type()

    # --- buckets ---
    infer_savings = (r2["stages"][0]["daily_usd"] - r2["stages"][5]["daily_usd"]) * DAYS
    purchasing_savings = r3["on_demand_monthly"] - r3["optimized_monthly"]

    idle_savings = r1["idle_waste_daily"] * DAYS
    rightsize_savings = 0.0
    for lie in r1["lies"]:
        cur = lie["gpu_type"]
        tgt = RIGHTSIZE_MAP.get(cur, cur)
        delta = num(cat[cur]["on_demand_hr"]) - num(cat[tgt]["on_demand_hr"])
        rightsize_savings += max(0.0, delta) * 24 * DAYS

    levers = {
        "Inference (cascade/cache/batch)": round(infer_savings),
        "Purchasing (spot/reserved)": round(purchasing_savings),
        "Right-size util-lies": round(rightsize_savings),
        "Kill idle GPUs": round(idle_savings),
    }
    baseline = r2["stages"][0]["daily_usd"] * DAYS + r3["on_demand_monthly"]
    optimized = baseline - sum(levers.values())
    total_pct = sum(levers.values()) / baseline * 100 if baseline else 0.0

    # --- sustainability snapshot ---
    budget = r2["reasoning"]["before"]
    wh = budget["wh"] / budget["requests"] if budget["requests"] else 0.0
    sust = {
        "wh_per_query": wh,
        "carbon_g": sustainability.carbon_g(wh, "us-east-1"),
        "best_region": min(sustainability.REGION_CARBON, key=sustainability.REGION_CARBON.get),
        "cheapest_region": min(sustainability.REGION_PRICE_KWH, key=sustainability.REGION_PRICE_KWH.get),
    }

    md = report.build_report(baseline, optimized, levers, sustainability=sust)
    md += "\n" + lab_analysis(r1, r2, r3, r4, baseline, optimized, levers, cat)
    out_md = os.path.join(ROOT, "outputs", "report.md")
    os.makedirs(os.path.dirname(out_md), exist_ok=True)
    with open(out_md, "w", encoding="utf-8") as f:
        f.write(md)
    png = report.savings_waterfall(levers, os.path.join(ROOT, "outputs", "savings.png"))

    if verbose:
        # Windows redirected stdout may default to cp1252, which cannot print Vietnamese.
        if hasattr(_sys.stdout, "reconfigure"):
            _sys.stdout.reconfigure(encoding="utf-8")
        print("== M5 Optimization Report ==")
        print(md)
        print(f"\nWritten: outputs/report.md" + (f" + outputs/savings.png" if png else " (matplotlib absent: PNG skipped)"))

    return {"baseline_monthly": round(baseline), "optimized_monthly": round(optimized),
            "levers": levers, "total_savings_pct": round(total_pct, 1)}


if __name__ == "__main__":
    run()
