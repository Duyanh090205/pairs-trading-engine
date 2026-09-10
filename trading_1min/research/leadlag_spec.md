# Lead-lag scan — spec PRE-COMMIT (khóa 2026-07-23, TRƯỚC khi chạy)

## Câu hỏi

Residual return (đã lột yếu tố thị trường) của mã A tại phút t có dự báo residual
return của mã B tại phút t+k (k = 1..30) đủ mạnh để giao dịch B **vượt phí** không?

Đây là họ alpha cuối cùng chưa test được với cấu trúc phí hiện có. Johansen (đã
đóng) test quan hệ ĐỒNG THỜI; bài này test quan hệ DỰ BÁO CÓ TRỄ — câu hỏi khác.

**Kỳ vọng công bố trước (honest prior):** lead-lag phút trên large-cap Mỹ bị cày
kỹ; khả năng cao EDGE << phí → kết cục dự kiến là ĐÓNG HỌ. Test để biết chắc.

## Dữ liệu & tiền xử lý

- Universe: top-100 spread hẹp nhất (như track chính) — cả vai leader lẫn follower
  (follower phải giao dịch được với phí của ta; leader ngoài universe không mở rộng
  ở tier-0).
- Kỳ THĂM DÒ (data đã cháy): H2/2024. Fit = 2024-07-01→2024-09-30;
  out-of-fit (OOF) = 2024-10-01→2024-12-31. KHÔNG đụng data sạch (2022–2023)
  và vùng khóa 2025-07→2026-03.
- Return 1-phút = diff log(close); return đầu phiên (qua đêm) loại bỏ; cặp (t, t+k)
  chỉ tính TRONG cùng phiên.
- NaN: ffill close trong phiên (quy ước engine). ⚠ Caveat ghi trước: bar ffill tạo
  return 0 + catch-up → có thể tạo lead-lag giả (stale price). Universe 99%+
  coverage nên ảnh hưởng nhỏ; economic stage vào lệnh t+1 close xử một phần.
- Residual hóa: r_mkt = mean đồng trọng số của 100 mã; β_i fit bằng OLS trên
  cửa sổ FIT (dùng chung cho cả OOF — không lookahead); resid_i = r_i − β_i·r_mkt.
- ⚠ Caveat ghi trước: không demean theo phút-trong-ngày ở tier-0 (periodicity có
  thể lẫn vào — nếu có survivor sẽ kiểm lại bằng demean trước khi tin).

## Thống kê

- ρ_k(A→B) = corr(resid_A(t), resid_B(t+k)), k = 1..30, mọi cặp có hướng A≠B
  (9.900 cặp × 30 lag = 297.000 test/cửa sổ). Chuẩn hóa trong từng cửa sổ
  (correlation không phụ thuộc scale); tích chéo gom trong-phiên.
- p-value xấp xỉ normal: p = 2·Φ(−|ρ|·√n_k); FDR Benjamini–Hochberg q = 0.05
  trên toàn bộ 297.000 test của cửa sổ FIT.
- **Null calibration bắt buộc:** lặp 20 lần bài scan trên dữ liệu đã hoán vị
  khối-ngày độc lập từng mã (giữ autocorrelation + seasonality nội mã, phá
  alignment cặp) → phân bố số "survivor giả". Số survivor thật phải được đọc
  so với phân bố null này.

## Luật phán quyết (KHÓA — không sửa sau khi thấy số)

1. **Detection (FIT):** survivor = (cặp, lag) qua BH-FDR q=0.05.
2. **Confirmation (OOF):** survivor xác nhận nếu ρ_oof cùng dấu VÀ |ρ_oof| ≥ 50%
   |ρ_fit| (kỷ luật giống funnel cũ).
3. **Economic (OOF):** với từng CẶP có ≥1 lag xác nhận:
   EDGE = |Σ_{k=2..30} ρ_k_oof(A→B)| × σ_B(1-phút, resid, OOF, bp).
   (Bắt đầu từ k=2: tín hiệu phút t, vào lệnh close t+1, hưởng từ t+2 — chống
   bounce/stale y như kỷ luật lag cũ.)
   Sàn phí: cost_floor(B) = 2 × half_B (median_bps/2, cả kỳ 2022–26, bảo thủ).
4. **HỌ 2 CÒN NGỎ** ⇔ ≥ 10 cặp xác nhận có EDGE > cost_floor(B).
   Ngược lại → **ĐÓNG HỌ 2 VĨNH VIỄN** ở cấu trúc phí hiện tại (ghi memory,
   không mua lại vé). Nếu còn ngỏ → bước kế: kiểm demean phút-trong-ngày +
   xác nhận trên data sạch 2022–2023 (spec mới, hỏi user trước).

## Tiered testing

- Khói-test: 10 ngày fit + 10 ngày OOF + 3 null reps — kiểm pipeline + null
  calibration (survivor null ≈ q·297k? Không — BH kiểm soát FDR, survivor null
  kỳ vọng ~0–vài chục; đọc bằng phân bố thực nghiệm).
- Full: như spec. Toàn bộ < 10 phút compute (nhân ma trận).
