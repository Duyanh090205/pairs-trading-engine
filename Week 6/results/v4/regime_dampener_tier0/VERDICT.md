# VERDICT — Tier-0: Dampener 3 nấc đấu composite nhị phân

**Kết luận theo luật đã khóa: RỚT — rớt luật (b) thiếu $31 (+$3,369 vs sàn +$3,400).**
Chạy 2026-07-24 theo spec `Week 6/engine_rebuild/REGIME_dampener_tier0_spec.md`
(ngưỡng khóa + user duyệt TRƯỚC khi tính bất kỳ số dampener nào; Gate V0 tái lập
đậu 39/39 halt + 16/16 stress_z trước đó).

## Chấm 3 luật

| Luật | Sàn khóa | Dampener | Neo | Đậu? |
|---|---|---|---|---|
| (a) Giữ phòng thủ Dec25–Mar26 | ≥ −0.75% | **−0.62%** (giữ 76% mức bảo vệ) | composite 0.00% / no-filter −2.56% | ✅ |
| (b) Vợt upside replay 2026 | ≥ +$3,400 | **+$3,369** | composite −$1,189 / no-filter +$11,304 | ❌ **thiếu $31** |
| (c) Không phá 39 fold | ≥ +1.80% | **+2.14%** (trả 0.18pp "bảo hiểm") | composite +2.32% / no-filter +0.84% | ✅ |

Sensitivity nấc giữa (chỉ báo cáo): 0.25 → rớt (b) nặng hơn; 0.75 → rớt (a).
**Nấc 0.5 đã khóa là điểm gần đậu nhất — không tồn tại nấc giữa nào đậu cả 3.**

## Cơ chế — toàn bộ verdict quy về MỘT tháng

Trong 15 tháng composite-halt: 8 tháng rơi nấc 0.5, 7 tháng nấc 0 (halt hẳn), 0 tháng
chạm biên. Phân loại đúng hướng rõ rệt: Feb/Mar-2026 + 2024-03/07 (các tháng sập nặng)
đều vào nấc 0; Jun-2026 (+$9.8k would-have) vào nấc 0.5 → vợt được +$4.9k.

Luật (b) rớt vì đúng một quyết định: **Jul-2026 bị xếp extreme** (stress_z 2.079 tại
t*=2026-06-30 ≥ q85=1.908, cách biên 0.17σ) → mult 0 → bỏ nguyên +$3.4k would-have của
tháng 7. Nếu Jul rơi nấc 0.5 như Jun thì (b) = +$5.1k, đậu thoải mái. Một tháng, một
biên phân vị, quyết định cả verdict.

## Đọc kết quả cho trung thực

- **Theo kỷ luật pre-commit: RỚT là RỚT.** Sàn $3,400 do ta tự chọn và tự khóa; xê dịch
  sau khi thấy số = đúng cái bệnh mà toàn bộ quy trình này sinh ra để chặn (Z=2.0 từng
  bị giết cùng cách). Nhánh dampener ĐÓNG theo spec; composite nhị phân GIỮ NGUYÊN.
- Đồng thời khai báo đủ: khoảng thiếu $31 = 0.9% của sàn, trên mẫu 4 fold một-đường-đời;
  sai số của chính phép xấp-xỉ-tuyến-tính (bỏ qua làm tròn lô/β-cap) chắc chắn lớn hơn
  $31 nhiều. Tier-0 này KHÔNG đủ phân giải để phân biệt "+$3,369" với "+$3,400".
- Hai luật còn lại đậu có biên: dampener giữ được 76% phòng thủ khủng hoảng và chỉ trả
  0.18pp trên 39 fold để đổi lấy +$4.6k vợt lại ở 2026 (so composite). Cấu trúc 3 nấc
  làm đúng chức năng thiết kế ở 42/43 tháng; điểm gãy duy nhất là biên q85 tháng 7.

## Hệ quả

- **Nhánh dampener Tier-0: ĐÓNG (RỚT).** Không tune q67/q85/0.5 để "cứu" — đã khóa là khóa.
- **Composite nhị phân giữ nguyên** làm regime layer chính thức (3 tật đã khai báo từ trước).
- Nhánh tầng-quyết-định còn lại theo spec: **granularity tháng→ngày** — chỉ mở nếu user
  muốn, spec pre-commit riêng.
- Nếu user muốn mở lại câu hỏi dampener: con đường hợp lệ duy nhất là một thí nghiệm MỚI
  đăng ký trước — ví dụ Tier-1 engine thật (đo trực tiếp, hết phụ thuộc xấp xỉ tuyến tính)
  với luật mới khóa trước khi chạy, và PHẢI khai báo đây là lần thử thứ hai sau một lần
  rớt sát nút (multiple-testing risk). Quyết định đó thuộc về user, không tự động.
- Trọng tài cuối, như mọi khi: các tháng live paper tới.

Files: `replication_check.txt`, `scorecard_dampener_43mo.csv`, `verdict_raw.txt`,
script `Week 6/scripts/research/regime_dampener/tier0_dampener.py`.
