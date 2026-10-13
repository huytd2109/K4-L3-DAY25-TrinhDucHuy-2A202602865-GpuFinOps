# NimbusAI — GPU Cost Optimization Report

**Period:** monthly\
**Baseline spend:** $27,133\
**Optimized spend:** $14,636\
**Projected savings:** $12,497  (**46%**)

## Savings by lever

| Lever | Savings (USD) |
|---|---|
| Inference (cascade/cache/batch) | $1,202 |
| Purchasing (spot/reserved) | $10,040 |
| Right-size util-lies | $655 |
| Kill idle GPUs | $600 |

## Sustainability

- Energy per query: 13.20 Wh
- Carbon per query: 5.015 gCO2e
- Cleanest region (lab carbon factors): europe-north1
- Cheapest electricity region (lab prices): us-east-wa

_Figures are June-2026 as-of snapshots; re-baseline before acting._

## Phạm vi và dữ liệu

Bài thực hành chạy bằng Python trong `.venv` của Day25; dữ liệu tổng hợp seed=25. Giá model/GPU, hệ số điện và carbon là giả định của lab, không phải báo giá hiện tại. Không chạy GPU, cloud hay API bên ngoài. Chọn extension 3 (cache) và 4 (reasoning).

| CSV | Số dòng | SHA-256 |
|---|---:|---|
| price_catalog.csv | 7 | `64783180a4aed0635cb370895e32e0434f67ccd8e7aa7d0c63a0b6fd2b7b5476` |
| gpu_telemetry.csv | 264 | `0e2351c932b182991b95e4ea12c180addd18b84eba1942d2cce107134a0a145d` |
| token_usage.csv | 2400 | `9e6c5657f2689aeb4d0ce9a572ada153cea89c69587b77afe96fd5e3f2bc94a9` |
| workloads.csv | 8 | `e183fea3b26667b5efb444241ec8ea248c6f883b62eef2607ebe637649583967` |

Đã đọc bốn CSV bằng `pandas.read_csv` trước khi sửa. Catalog có giá các tier, HBM, peak FLOPs và bandwidth; telemetry có util/MFU/MBU và bộ nhớ thực dùng; token log có route/cache/batch/reasoning/tags; workloads có giờ/ngày, ngày chạy và số GPU.

## Kết quả trước/sau trên cùng dữ liệu

Đã chạy M1–M5 trước khi sửa. Cột trước được tái tính bằng công thức gốc (cache chỉ tính read, không write) để giữ kết quả đối chiếu khi chạy lại.

| Chỉ số | Trước mở rộng | Sau mở rộng |
|---|---:|---:|
| M2 USD/ngày optimized | 8.484623 | 8.811379 |
| M2 USD/1M-token optimized | 1.126323 | 1.169700 |
| M2 savings | 82.640% | 82.0% |
| M3 on-demand / optimized, USD/tháng | 25,667 / 15,627 | 25,667 / 15,627 |
| M3 savings | 39.1% | 39.1% |
| M5 baseline, USD/tháng | 27,133 | 27,133 |
| M5 optimized, USD/tháng | 14,626 | 14,636 |
| M5 projected savings | 46.095% | 46.058% |

## M1 — Guide 4.3

| GPU | Loại | Util % | MFU | MBU | Idle giờ/ngày |
|---|---|---:|---:|---:|---:|
| gpu-h100-0 | H100 | 94.4 | 0.417 | 0.446 | 0 |
| gpu-h100-1 | H100 | 95.2 | 0.408 | 0.440 | 0 |
| gpu-h100-2 | H100 | 94.3 | 0.401 | 0.423 | 0 |
| gpu-h100-3 | H100 | 93.1 | 0.427 | 0.444 | 0 |
| gpu-h100-4 | H100 | 98.2 | 0.194 | 0.207 | 0 |
| gpu-h100-5 | H100 | 61.1 | 0.261 | 0.271 | 8 |
| gpu-a100-0 | A100 | 31.4 | 0.259 | 0.276 | 0 |
| gpu-a100-1 | A100 | 28.0 | 0.236 | 0.247 | 0 |
| gpu-a10g-0 | A10G | 25.0 | 0.218 | 0.235 | 0 |
| gpu-a10g-1 | A10G | 96.9 | 0.268 | 0.302 | 0 |
| gpu-l4-0 | L4 | 40.0 | 0.302 | 0.328 | 0 |

1. Util trung bình cao nhất: `gpu-h100-4` = 98.2%, MFU=0.194. Các GPU bị flag: `gpu-h100-4`, `gpu-a10g-1`.
2. GPU-Util đo thời gian có kernel hoạt động; MFU đo FLOPs đạt được/peak. Memory stall, kernel launch overhead hoặc I/O có thể làm GPU bận nhưng ít FLOPs. Đây là giả thuyết cần profiler xác nhận; MBU thấp riêng lẻ chưa chứng minh memory-bound.
3. Idle: $20.00/ngày = $600/tháng; 2.21% baseline tổng M5, hoặc 3.90% hóa đơn fleet telemetry on-demand 24h/ngày ($15,393.60/tháng). Hai mẫu dữ liệu có phạm vi khác nhau.

## M2 — Guide 5.4 và extension 3: cache có đáng dùng?

| Bước tuần tự | USD/ngày | USD/1M-token | Giảm so bước trước, USD/ngày |
|---|---:|---:|---:|
| Baseline | 48.874161 | 6.487984 | 0.000000 |
| Cascade | 11.475643 | 1.523377 | 37.398518 |
| Cascade + cache (reads only) | 10.279188 | 1.364549 | 1.196455 |
| Cascade + cache + batch (original) | 8.484623 | 1.126323 | 1.794565 |

1. `cascade` đóng góp lớn nhất trong thứ tự cascade → cache → batch. Các khoản trên là marginal savings theo thứ tự này, không phải hiệu quả độc lập để cộng tùy ý.
2. `0.05 = 0.50 × 0.10`: chiết khấu batch nhân với giá cached input. Đây là góc nhìn input 100% cached; output vẫn có giá riêng nên cả request không nhất thiết giảm 95%.
3. Không dùng batch cho chat tương tác hoặc tác vụ cần phản hồi tức thì; ưu tiên eval/offline cho phép chờ.

**Giả định extension:** phí ghi bổ sung $1.00/1M prefix token, 4 reads/write ở cấu hình mặc định, cached read giá 0.10× input. Writes nằm ngoài token log, được phân bổ `cached_tokens / reads_per_write`; không giảm giá ghi theo batch. CSV không có prefix ID/số lần đọc nên không thể suy ra reuse thực tế; đây là phân tích kịch bản, chưa bao gồm TTL/lưu trữ. Denominator luôn là cùng 7,533,027 token phục vụ trên dữ liệu này.

`reads_hòa_vốn = write_USD_per_M / (input_USD_per_M × 0.90 × batch_factor)`. Chỉ bật cache khi reads lớn hơn ngưỡng; bằng ngưỡng không có lợi nhuận.

| Model | Batch | Reads hòa vốn |
|---|---|---:|
| small | False | 5.555556 |
| small | True | 11.111111 |
| large | False | 0.370370 |
| large | True | 0.740741 |

| Kịch bản cache | USD/ngày | USD/1M-token |
|---|---:|---:|
| Không cache, cascade + batch | 9.658588 | 1.282166 |
| Gốc: reads only, chưa tính writes | 8.484623 | 1.126323 |
| 1 reads/write, có gate + writes | 9.076181 | 1.204852 |
| 4 reads/write, có gate + writes | 8.811379 | 1.169700 |
| 16 reads/write, có gate + writes | 8.591122 | 1.140461 |

Với 4 reads/write, small bị tắt cache (cả batch và non-batch), large được bật. Ít reads làm phí ghi khó hoàn vốn; 16 reads/write vượt tất cả ngưỡng. Chi phí sau mở rộng cao hơn công thức gốc vì gốc bỏ phí ghi; không phải một khoản tiết kiệm mới.

## Extension 4 — Ngân sách reasoning

| is_reasoning | Requests | % request | Tokens | % token | USD/ngày | % chi phí | Wh/ngày | % năng lượng |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | 2199 | 91.625% | 6,291,871 | 83.524% | 7.410823 | 84.105% | 1887.561 | 5.959% |
| 1 | 201 | 8.375% | 1,241,156 | 16.476% | 1.400556 | 15.895% | 29787.744 | 94.041% |

| Cap 10% traffic | Requests | Reasoning requests | Tokens | USD/ngày | Wh/ngày |
|---|---:|---:|---:|---:|---:|
| Trước cap | 2400 | 201 | 7,533,027 | 8.811379 | 31675.305 |
| Sau cap | 2400 | 201 | 7,533,027 | 8.811379 | 31675.305 |

Demoted=0; savings=$0.000000/ngày và 0.000 Wh/ngày. Traffic reasoning hiện dưới 10%, nên savings bằng 0; không đổi model, output hoặc số request ở dữ liệu này.
`wh_per_query` của lab dùng 0.30 Wh/1k token và hệ số 80× khi reasoning; output của generator còn dài 6×. Các hệ số này là mô hình ước lượng, không phải điện đo thực tế. Nếu vượt cap, mô phỏng giữ tối đa floor(10% × requests) reasoning theo thứ tự CSV; phần vượt chuyển sang non-reasoning, giữ input/route/cache/batch, output chia 6 (làm tròn) và bỏ hệ số năng lượng 80×. Savings khi đó phải kiểm tra lại chất lượng và độ dài output.
Đề xuất chỉ dùng reasoning cho tác vụ nhiều bước hoặc sau khi câu trả lời thường không đạt bộ kiểm tra chất lượng; cap là ngân sách trần, không phải quota bắt buộc dùng hết. Dataset không có confidence/quality score nên chưa kiểm chứng được rule routing này.

## M3 — Guide 6.4

| Job | Ngày thực tế | GPU | Tier | On-demand USD/30 ngày | Optimized USD/30 ngày |
|---|---:|---|---|---:|---:|
| job-train-llm | 14 | H100 | spot | 12,000 | 7,596 |
| job-train-embed | 5 | A100 | spot | 2,148 | 1,393 |
| job-finetune | 3 | H100 | spot | 900 | 570 |
| job-infer-chat | 30 | A10G | reserved | 4,320 | 2,592 |
| job-infer-rag | 30 | A100 | reserved | 3,866 | 2,160 |
| job-infer-search | 30 | L4 | reserved | 1,728 | 972 |
| job-dev-sandbox | 22 | A10G | spot | 480 | 203 |
| job-batch-eval | 30 | H100 | spot | 225 | 142 |

1. Spot: job-train-llm, job-train-embed, job-finetune, job-dev-sandbox, job-batch-eval; đều interruptible=1, giờ/ngày <24. Cần checkpoint và chấp nhận job kéo dài khi bị thu hồi.
2. Effective hours = GPU-hours × (1 + 0.03) + GPU-hours × 0.05 × 0.5 = 1.055 × GPU-hours. Phần tăng là overhead checkpoint và tính lại phần việc mất; đây là kỳ vọng mô hình.
3. Ba job inference được reserved theo duty cycle; tuy nhiên chỉ có 30 ngày workload, chưa đủ căn cứ cam kết 3 năm. Khi chưa chứng minh nhu cầu dài hạn, on-demand có thể phù hợp hơn. M3 gốc bỏ qua cột days và tính reserved theo giờ dùng thay vì toàn bộ giờ cam kết; đặc biệt job-infer-search chạy 18h/ngày chưa tính 6h reserved không dùng. Bảng này giữ nguyên policy để đối chiếu, không phải quyết định mua đã xác nhận.

## M4 — Guide 7.4

M4 dùng chung hàm tính chi phí mới của M2, gồm cache gate và phí ghi phân bổ.

| Team | USD/ngày | % tổng |
|---|---:|---:|
| assistant | 2.764502 | 31.374% |
| search | 2.512873 | 28.519% |
| eval | 1.802541 | 20.457% |
| rag | 1.731462 | 19.650% |

1. `assistant` tốn nhiều nhất: 31.374% tổng inference optimized.
2. Có 2203/2400 requests đủ team/project (91.792%); vượt gate 80%, chargeback ready=True. Cần tiếp tục sửa các project thiếu tag trước phân bổ đầy đủ.
3. FOCUS giúp chuẩn hóa tên cột, đơn vị và kỳ chi phí giữa các nhà cung cấp để so sánh/phân bổ. `focus_export.csv` là mẫu 50 request đầu, có BilledCost/team/project; tổng mẫu không phải tổng 2400 request. Đây là export FOCUS-style tối giản, chưa phải chứng nhận tuân thủ đầy đủ chuẩn.

## Điện, carbon và ưu tiên thực hiện

Sustainability đầu báo cáo dùng trung bình Wh/request thực tính từ toàn bộ token log, gồm reasoning. Ví dụ 800 token không reasoning của code gốc = 0.24 Wh và 0.0912 gCO2e ở us-east-1, không đại diện cho trung bình dữ liệu này.

| Vùng | USD/kWh | gCO2e/kWh | USD điện/ngày | gCO2e/ngày |
|---|---:|---:|---:|---:|
| us-east-1 | 0.120 | 380 | 3.801037 | 12036.616 |
| us-west-2 | 0.070 | 120 | 2.217271 | 3801.037 |
| europe-north1 | 0.090 | 30 | 2.850777 | 950.259 |
| europe-central2 | 0.180 | 660 | 5.701555 | 20905.701 |
| us-east-wa | 0.055 | 90 | 1.742142 | 2850.777 |

Sạch nhất: europe-north1 (30 g/kWh); điện rẻ nhất: us-east-wa ($0.055/kWh). Cùng lượng công việc/năng lượng, chọn vùng sạch giảm carbon nhưng không nhất thiết có điện rẻ nhất. Giá điện không phải giá thuê GPU; không cộng tiền điện vào bill thuê để tránh đếm trùng. Cần kiểm tra latency, dữ liệu và GPU sẵn có trước khi đổi vùng.

Ưu tiên: (1) xác minh purchasing/nhu cầu cam kết vì đây là lever lớn nhất trong mô hình; (2) triển khai cascade có gate chất lượng, cache có gate chi phí và batch cho offline; (3) tắt GPU ở 8 giờ idle đã phát hiện; (4) chỉ right-size sau benchmark bộ nhớ, throughput và latency. Theo dõi riêng ngân sách reasoning và vùng carbon khi SLA cho phép.

**Giới hạn tổng M5:** tổng và biểu đồ là projected savings theo bốn bucket của lab, quy đổi 30 ngày; không phải mức tiết kiệm thực đo. Right-size gốc dùng map H100→A100/A10G→L4 chưa kiểm tra capacity/throughput. Telemetry, workloads và token log không có join key chung, nên không chứng minh được idle/right-size độc lập với purchasing; có nguy cơ cộng trùng savings. Không diễn giải 46% này thành cam kết business impact hoặc độ chính xác/hiệu năng model.
