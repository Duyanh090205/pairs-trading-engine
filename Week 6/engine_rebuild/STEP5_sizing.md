# BƯỚC 5 — SIZING — **CHỐT 2026-07-24**

Nối tiếp `STEP1_universe.md` + `STEP2_walkforward.md`. Cùng phong cách: mọi quyết định
kiểm chứng bằng data thật, sẵn sàng bác. Đây là **TRỤC SIZING** (song song có trục
execution S2/S4 + Z-sweep — trục khác, không đụng).

**Kết luận một dòng:** Sizing hiện tại (vol-target per-pair + regime sizer) **đã đủ
dynamic**. Trần tập trung được **phân tích kỹ nhưng KHÔNG xây** — lợi ích đo được ~0,
lợi ích thật không chứng minh nổi, cùng họ rủi ro "gom vốn" đã bác. Phơi nhiễm ròng
long-ngân-hàng lúc khủng hoảng được **ghi nhận như rủi ro đã khai báo**, không chặn bằng
máy móc chưa chứng minh.

---

## 0. Sizing baseline (giữ nguyên — để đối chiếu)

| Thành phần | Cơ chế | Trạng thái |
|---|---|---|
| Vol-target per-pair | `notional = $200 / σ_ngày(Δspread)`, kẹp [$10k, $40k] | ✅ đã dynamic theo biến động từng cặp |
| Dollar-neutral | mỗi chân = 0.5 × notional | giữ (xem mục 4) |
| Regime sizer | `size_mult` 100/50/0% theo stress_z (q67/q85 trailing 252d) | ✅ đã có + đã cắm dây (`--use-composite-sizer`) |
| Trần ĐẾM per-ticker | ≤ 5 cặp/mã (xếp Johansen p-value) | ✅ đã có (`portfolio.apply_ticker_concentration_cap`) |
| Trần ĐÔ-LA / NGÀNH cấp danh mục | — | ❌ **không có** (Step 4 xác nhận thiếu) |

Code: `engine_daily/engine_daily.py` (vol-target, dollar-neutral, `fold_size_mult`),
`engine_daily/regime_detector.py::size_multiplier_for_fold`,
`engine_daily/portfolio.py::apply_ticker_concentration_cap`.

---

## 1. Năm trục "dynamic hơn" — disposition từng cái

| # | Trục | Quyết | Lý do |
|---|---|---|---|
| 1 | Conviction-weight (size to khi \|Z\|/coint mạnh) | **KHÔNG** | Cùng họ top-K đã bác (`week6_rejected_approaches`): dồn vốn vào ít bet, tăng fold-level variance. Bằng chứng bác đã đủ mạnh, không redo. |
| 2 | Regime-dampen (giảm size khi stress) | **ĐÃ CÓ, giữ** | Đã cắm dây. ⚠️ có **điểm mù** (mục 3.4): KHÔNG dampen tháng SVB. Ghi nhận, không sửa ở bước này. |
| 3 | **Concentration caps (per-name + per-sector NET)** | **PHÂN TÍCH → KHÔNG XÂY** | Mục 2–3 dưới đây. Deliverable = số phơi nhiễm + rủi ro khai báo, không phải code. |
| 4 | Leg-sizing 50/50 vs beta-weighted | **KHÔNG đổi** | P&L đã ở spread-space với β nằm trong định nghĩa spread (`spread = resid_a − α − β·resid_b`). Đổi leg-sizing chỉ đổi đô-la **danh nghĩa** mỗi chân, không đổi phơi nhiễm rủi ro thật (đã beta-adjust qua spread). Danh nghĩa ≠ thật → không đáng đổi. |
| 5 | Edge/half-life weight (phân bổ theo EV/tốc độ hồi) | **KHÔNG** (deferred) | Chưa test. Cảnh báo: HL ngắn ≠ EV cao (adverse selection ở carry đã thấy, STEP2 mục 3.2). Không có bằng chứng ủng hộ; không mở nếu chưa có lý do. |

Trục #3 là trọng tâm bước này (Step 1 mục 6 đã hứa). Kết quả: **không xây**. Chi tiết:

---

## 2. Trần MỖI-TÊN — **BÁC (thừa)**

**Analytical (gross, cả 39 fold, `quick_test_concentration_step5.csv`):**
cổ phiếu đơn to nhất **trung vị chỉ 4.3% rổ**. Con số cao (24.9% BALL, 17.8% WMT) chỉ ở
tháng rổ tí hon (4–14 cặp, tổng tiền ~$0) → nhiễu mẫu nhỏ.

**Subset (bar-level, tháng SVB 2023-03, `step5_sizing_netexp/daily_net_exposure.csv`):**
ngày rổ to nhất ($435k), tên đơn to nhất = **CFG 4.6%**; những ngày bận rộn median 5.8%,
max 7.4%. "25%" chỉ ở ngày đầu tháng khi mới 1–2 lệnh mở.

**Vì sao thừa:** vol-target kẹp [$10k,$40k] + trần đếm ≤5 cặp/mã **đã** giữ mọi cái tên ở
vài % của rổ đa dạng. Trần 3% per-name chỉ ràng buộc ở tháng rổ tí hon — nơi tiền tuyệt
đối đã bé sẵn. **Không xây trần per-name.**

---

## 3. Trần MỖI-NGÀNH (NET) — **PHÂN TÍCH → KHÔNG XÂY**

### 3.1 Bằng chứng gross (analytical, 39 fold)
Ngành Tài chính thường xuyên **~20–24% rổ** (trung vị ngành to nhất = 20.7%), gồm **22% ở
đúng tháng SVB** (39/95 cặp dính một cổ phiếu tài chính). Nhưng gross đếm cả 2 chân → **trần
trên**, không phải rủi ro thật (cặp bank-vs-bank tự hedge).

### 3.2 Bằng chứng NET (subset bar-level, fold 1–4, Z=3.0, FLAT cost)
Quy ước: position=+1 → long A/short B; leg = 0.5·notional; NET ngành = tổng đô-la **có dấu**.

| Fold | Tháng | Rổ đỉnh | Fin NET %rổ (TB / đỉnh) | dir-ratio | Ghi chú |
|---|---|---|---|---|---|
| 1 | 2023-01 | $128k | −9.4% / −20.9% | −1.0 | rổ nhỏ, $7k — nhiễu |
| 2 | 2023-02 | $173k | +10.6% / +50.0% | +1.0 | đỉnh $11k — nhiễu mẫu nhỏ |
| **3** | **2023-03 (SVB)** | **$435k** | **+28.5% / +35.6%** | **+0.71** | **rổ thật; net-LONG bank 21/21 ngày; đỉnh $110k** |
| 4 | 2023-04 | $26k | −43.4% / −50.0% | −1.0 | 2 lệnh, $5k — nhiễu |

**Chốt hạ (fold 3 = duy nhất là rổ thật):** tháng SVB, rổ **net-long ngân hàng suốt 21/21
ngày**, trung bình **+28.5% rổ**, dir-ratio 0.71 (**một chiều, KHÔNG tự hedge**), đỉnh net
long **$110k / $435k**. Đúng kịch bản Bước 1 ("15 cặp bank tất cả long, bắt dao rơi"), nay
đo được bằng số. Tháng đó lỗ (−1.2% dyncost / −1.65% flat, 12 lệnh cắt lỗ).

### 3.3 Vì sao vẫn KHÔNG xây
1. **Lợi ích đo được ~0:** tháng tệ nhất chỉ −1.2% *trên data survivor*; tháng thường không
   đụng. Không phải cải thiện lợi nhuận — là bảo hiểm thuần.
2. **Lợi ích thật không chứng minh nổi:** cái đuôi −4% đến −7% (Bước 1) đến từ ngân hàng
   **huỷ niêm yết** (SVB/FRC/SBNY) **không có trong 528-universe**. Không đo được cap cứu bao
   nhiêu → không dám tuyên bố.
3. **Cùng họ rủi ro đã bác:** mọi ràng buộc gom-vốn (top-K) đều tăng fold-level variance và
   **có hại** (`week6_rejected_approaches`). Thêm code chưa chứng minh vào đúng vùng nguy hiểm.
4. **Mẫu n=1:** chỉ 1 tháng khủng hoảng thật (fold 3); folds 1/2/4 là rổ tí hon. Không đủ
   power để tuyên bố cap giúp.

### 3.4 ⚠️ RỦI RO ĐÃ KHAI BÁO (thay cho việc xây cap)
- **Regime sizer bỏ sót SVB:** kiểm số — `z30_sizer` fold 3 **giống HỆT** baseline `z30_dyncost`
  (−1.21%, 41 lệnh) → `size_mult = 1.0`, sizer **không nhận ra** tháng SVB là stress (bộ đo
  vol/corr/dispersion chưa kịp vượt q85 khi SVB sập đột ngột). Điểm mù có thật.
- **Độ nghiêng ròng long-bank +28% lúc khủng hoảng KHÔNG được tầng sizing nào chặn** hiện nay.
  Vol-target lo per-name (được), regime sizer lo cả-rổ (bỏ sót crisis), **không tầng nào lo độ
  nghiêng ròng theo ngành**.
- Xử lý = **khai báo** (như Bước 1 làm với survivorship), KHÔNG dự đoán/curve-fit. Nếu sau này
  muốn phòng thủ đuôi này: hướng đúng là **overlay NET theo ngày** (~10–12% net/ngành), phải
  chạy full 39-fold để định giá phí Sharpe trước khi ship. Chưa làm.

---

## 4. Leg-sizing (50/50 vs beta) — **KHÔNG đổi**
Spread đã định nghĩa `resid_a − α − β·resid_b`; P&L = `position × Δspread × notional` → **β đã
nằm trong rủi ro**. Đổi chân sang beta-weighted chỉ đổi đô-la danh nghĩa, không đổi phơi nhiễm
thật. Giữ dollar-neutral 50/50.

---

## 5. Cờ mẫu nhỏ / disclosure
- Chỉ **1 tháng khủng hoảng thật** (fold 3) trong subset; folds 1/2/4 rổ tí hon → mọi số net
  ngoài fold 3 là nhiễu.
- Data **survivor-only** → cái đuôi thật (delisted banks) vô hình trong mọi số backtest.
- Không tuyên bố "significant" cho bất kỳ quyết định sizing nào ở cỡ mẫu này.

---

## 6. Quyết đạt/trượt (pre-committed)
Không có tiêu chí "ĐẠT/TRƯỢT" kiểu Sharpe vì **không chạy A/B cap** (quyết không xây). Quyết
là **DEFERRAL có chủ đích** dựa trên: (a) lợi ích đo được ~0, (b) lợi ích thật không chứng
minh nổi, (c) cùng vùng rủi ro đã bác. Deliverable = **số phơi nhiễm + rủi ro khai báo**
(mục 2–3), không phải code cap.

**Muốn lật quyết này phải có:** bằng chứng OOS rằng cap NET không hại Sharpe/return (full
39-fold A/B) — hiện chưa có, và chưa ưu tiên.

---

## Files
- `results/v4/quick_test_concentration_step5.csv` — gross per-fold, 39 fold.
- `results/v4/step5_sizing_netexp/daily_net_exposure.csv` — net bar-level, fold 1–4.
- `results/v4/step5_sizing_netexp/fold_net_summary.csv` — net summary, fold 1–4.

## TRẠNG THÁI: ✅ CHỐT (2026-07-24)
Sizing baseline (vol-target + regime sizer + trần đếm) **giữ nguyên, đủ dynamic**. Concentration
cap **phân tích xong, không xây** (lợi ích ~0 + không chứng minh nổi + cùng họ đã bác). Điểm mù
regime-sizer-bỏ-sót-SVB + độ nghiêng ròng long-bank +28% = **rủi ro đã khai báo**. Không đổi
tham số/code sizing nào. Sẵn sàng bước tiếp.
