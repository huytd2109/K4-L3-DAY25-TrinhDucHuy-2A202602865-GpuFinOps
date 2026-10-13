# Day25 — GPU FinOps: phân tích và khuyến nghị cho NimbusAI

**Sinh viên:** Trịnh Đức Huy — 2A202602865. **Kiểm tra:** 13/10/2026.

Dữ liệu tổng hợp seed=25; giá và hệ số năng lượng là giả định lab. Tháng quy đổi 30 ngày; chưa đo GPU/hóa đơn thực tế.

## 1. Baseline vs. Optimized

| Chỉ số | Baseline | Optimized |
|---|---:|---:|
| Inference M2, USD/ngày | 48.874161 | 8.811379 |
| Inference M2, USD/1M-token | 6.487984 | 1.169700 |
| Purchasing M3, USD/tháng | 25,667 | 15,627 |
| Tổng dự phóng M5, USD/tháng | 27,133 | 14,636 |

M2 phục vụ cùng **7,533,027 token/ngày**, giảm **82.0%**, gồm phí ghi cache. M3 giảm **39.1%**. M5 dự phóng giảm **12,497 USD/tháng (46.1%)**. `$/1M-token` chỉ áp dụng M2: job GPU chưa có token tương ứng để quy đổi tổng M5.

M3 gốc quy đổi mọi job 30 ngày, reserved tính theo giờ dùng; chưa chứng minh nhu cầu ba năm. Idle/right-size chưa có join key với purchasing, nên tổng M5 có nguy cơ cộng trùng savings.

## 2. Phân tích từng đòn bẩy

| Đòn bẩy M5 | Savings USD/tháng | Tỷ trọng savings |
|---|---:|---:|
| Purchasing: spot/reserved | 10,040 | 80.34% |
| Inference: cascade/cache/batch | 1,202 | 9.62% |
| Right-size GPU bị flag | 655 | 5.24% |
| Tắt GPU idle | 600 | 4.80% |

**Purchasing đóng góp nhiều nhất:** tiền thuê GPU chiếm phần lớn baseline; spot/reserved rẻ hơn on-demand. Cần xác minh thời hạn cam kết và checkpoint trước khi mua.

Trong M2 gốc, cascade → cache → batch giảm chi phí **48.874161 → 11.475643 → 10.279188 → 8.484623 USD/ngày**. Cascade lớn nhất: **37.398518 USD/ngày**, vì phần lớn request sang model nhỏ. Cache và batch giảm tiếp **1.196455** và **1.794565 USD/ngày**. Đây là savings tuần tự, chưa tính writes; sau extension, chi phí cuối là 8.811379 USD/ngày.

## 3. GPU-Util Lie và tác động tài chính

| GPU bị flag | Util trung bình | MFU | Right-size giả định | Savings USD/tháng |
|---|---:|---:|---|---:|
| gpu-h100-4 | 98.2% | 0.194 | H100 → A100 | 511.20 |
| gpu-a10g-1 | 96.9% | 0.268 | A10G → L4 | 144.00 |

GPU-Util đo thời gian kernel hoạt động; MFU đo FLOPs đạt được/peak. Memory stall hoặc overhead có thể làm GPU bận nhưng ít FLOPs; cần profiler xác nhận nguyên nhân.

Hai GPU vẫn trả giá thuê đầy đủ; right-size dự phóng **655.20 USD/tháng** (M5 làm tròn 655), chưa benchmark bộ nhớ/throughput. Riêng `gpu-h100-5` idle **8 giờ/ngày**, tương đương **600 USD/tháng** có thể tránh nếu tắt đúng lịch.

## 4. Hai phần mở rộng đã thực hiện

**Extension 3 — Cache có đáng dùng?** Thêm `cache_is_worth_it()` tại `finops/pricing.py`, gọi ở M2; M4 dùng chung cách tính. Giả định writes **1 USD/1M prefix token**, phân bổ theo reads/write, không giảm theo batch. CSV thiếu prefix ID/số reads, nên reuse là giả định.

Ngưỡng reads hòa vốn = `write_price / (input_price × 0.90 × batch_factor)`. Small cần **>5.555556** không batch, **>11.111111** có batch; large tương ứng **>0.370370**, **>0.740741**. Với 4 reads/write, chỉ large dùng cache.

| Kịch bản | USD/ngày | USD/1M-token |
|---|---:|---:|
| Không cache, cascade + batch | 9.658588 | 1.282166 |
| 1 read/write, có gate + phí ghi | 9.076181 | 1.204852 |
| 4 reads/write, có gate + phí ghi | 8.811379 | 1.169700 |
| 16 reads/write, có gate + phí ghi | 8.591122 | 1.140461 |

**Insight:** cache hit cao chưa chắc có lợi khi reuse thấp. Chi phí tăng so với gốc 8.484623 USD/ngày vì bổ sung writes, không phải savings mới.

**Extension 4 — Ngân sách reasoning.** M2 tách request/token/USD/Wh; M5 tổng hợp điện/carbon. Reasoning: **201/2,400 request (8.375%)**, **1,241,156 token (16.476%)**, **1.400556 USD (15.895%)**, **29,787.744 Wh (94.041%)** mỗi ngày. Non-reasoning: 2,199 request, 6,291,871 token, 7.410823 USD, 1,887.561 Wh/ngày.

Cap **10%** không đổi traffic: trước/sau đều **8.811379 USD, 31,675.305 Wh/ngày**; savings **0 USD, 0 Wh**. Hệ số reasoning 80× và output dài 6× thuộc mô hình lab. Nếu vượt cap, mô phỏng chuyển phần dư sang non-reasoning, giữ input/model, output chia 6; cần kiểm tra chất lượng.

**Insight:** ít request có thể chi phối năng lượng. Trung bình: **13.20 Wh/query**, **5.015 gCO2e/query** ở us-east-1. Sạch nhất: europe-north1; điện rẻ nhất: us-east-wa. Cân nhắc thêm latency khi chọn vùng.

## 5. Ba hành động đầu tiên của FinOps lead

1. **Xác minh purchasing:** tính thời gian job/giờ cam kết thực tế; thử spot có checkpoint cho job interruptible, kiểm tra deadline.
2. **Tối ưu inference:** kiểm tra chất lượng cascade, đo reads/prefix/phí ghi, batch cho offline; reasoning khi cần, theo dõi cap 10%.
3. **Loại idle và profile:** tắt 8 giờ idle của gpu-h100-5; benchmark hai GPU bị flag trước khi right-size.

## Checklist đã kiểm tra

- [x] `python verify.py`: **11/11 checks passed**.
- [x] `pytest -q`: **15 passed** (chạy bằng Python trong `.venv` Day25).
- [x] [report.md](report.md): đủ baseline/optimized, savings từng lever, điện và CO₂.
- [x] [savings.png](savings.png): tồn tại, đọc được, hiển thị bốn lever.
- [x] [focus_export.csv](focus_export.csv): tồn tại, 50 dòng mẫu; có BilledCost/team/project.
- [x] Hai extension có code chạy được và kết quả định lượng trên cùng dữ liệu.

Bộ nộp gồm ba output trên và bài viết này. Chưa push lên GitHub.
