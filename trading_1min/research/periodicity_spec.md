# Periodicity scan (HKS) — spec PRE-COMMIT (khóa 2026-07-23, TRƯỚC khi chạy)

## Câu hỏi

1. **Alpha:** hiệu ứng HKS (Heston–Korajczyk–Sadka 2010) — return của mã i ở khung
   nửa-giờ j hôm nay lặp lại ở ĐÚNG khung j các ngày sau — còn sống trên data
   của ta không, và có ăn được phí không?
2. **Bản đồ thực thi (giá trị chắc chắn, không cần verdict):** hồ sơ 13 khung
   nửa-giờ: độ biến động, tỷ trọng volume, spread THẬT trung bình — input cho
   tầng execution-timing (Họ 3) bất kể alpha sống hay chết.

**Kỳ vọng công bố trước:** hiệu ứng HKS trên large-cap sau 2010 đã suy giảm theo
văn liệu; kỳ vọng dấu vết thống kê yếu, kinh tế không qua phí → giá trị chính là
bản đồ. Test để biết chắc.

## Dữ liệu

- Universe: top-100 spread hẹp nhất (như track). Cross-section 100 mã là NHỎ so
  với HKS gốc (hàng nghìn mã CRSP) — flag: test yếu hơn bản gốc.
- Kỳ THĂM DÒ (toàn bộ là data đã cháy): 2024-01-02 → 2025-06-30 (~370 phiên).
  KHÔNG đụng data sạch 2022–2023, KHÔNG đụng vùng khóa 2025-07→2026-03.
- Return nửa-giờ (t, j, i) = tổng return 1-phút trong-phiên của khung j
  (13 khung: 9:30–10:00 ... 15:30–16:00); return qua đêm loại bỏ.
- Spread map: 20 mã đại diện (mỗi bậc 5 của universe xếp theo phí), năm 2024,
  `half_spread_l1_bps` với `is_valid` — từ spreads_1min.parquet (L1 THẬT).

## Phương pháp (khóa)

- **Predictor A (same-slot):** mean return khung j của 20 ngày trước (min 15),
  shift 1 ngày — không lookahead.
- **Predictor B (control):** mean return các khung KHÁC j cùng 20 ngày
  (xấp xỉ (13·M − R_j)/12; sai số ngày rút gọn ~3 ngày/năm chấp nhận).
  B tách "lặp đúng khung giờ" (chữ ký HKS) khỏi momentum/reversal chung của mã.
- **Fama–MacBeth:** mỗi (ngày, khung): z-score cross-section y, A, B (cần ≥60 mã
  hợp lệ); OLS đồng thời y ~ γA·A + γB·B. Gom cụm THEO NGÀY (bài học đo lường):
  mean các slope trong ngày → 1 quan sát/ngày → t trên ~350 ngày.
- **Kinh tế:** mỗi (ngày, khung): danh mục decile theo A — long top-10, short
  bottom-10, giữ đúng khung nửa-giờ; gross bp/lượt (mỗi bên). Sàn phí =
  mean(median_bps) của 20 mã trong danh mục (khứ hồi mỗi mã = full spread,
  taker, bảo thủ). Gom cụm theo ngày.

## Luật phán quyết (KHÓA — không sửa sau khi thấy số)

- **(a) Dấu vết HKS:** t_ngày(γA) ≥ 2 VÀ t_ngày(γA − γB) ≥ 2.
- **(b) Ăn được phí:** mean gross decile L-S > mean sàn phí VÀ t_ngày(gross) ≥ 2.
- **Nhánh alpha Họ 1 CÒN NGỎ ⇔ (a) VÀ (b).** Chỉ (a) → "dấu vết có, không ăn
  được phí" → đóng nhánh alpha, ghi nhận cho execution. Không (a) → hiệu ứng
  chết trên data ta → đóng. Bản đồ thực thi được giao NGUYÊN VẸN trong mọi
  kịch bản.
- Nếu (a)+(b) cùng đạt → bước kế: xác nhận trên data sạch 2022–2023 (spec mới,
  hỏi user trước).

## Tiered

- Khói: 2024-01→2024-03, bỏ spread map — kiểm pipeline.
- Full: đủ 18 tháng + spread map. Ước tính < 5 phút compute.
