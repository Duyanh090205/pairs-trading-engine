# Phễu chọn cặp 1-phút — SPEC ĐÃ CHỐT (2026-07-08)

> Track backtest 1-phút, build lại từ đầu. Mọi lựa chọn dưới đây đều được chốt cùng user
> sau thảo luận + thí nghiệm; cột "bằng chứng" trỏ về thí nghiệm trong session 2026-07-08
> (script trong scratchpad: synth_eg_test.py, synth_hl_fix.py, synth_johansen_test.py,
> synth_splitgate_test.py, johansen_goog_example.py, johansen_span_vs_freq.py — seed 42).

## Cửa sổ

- **Formation sandbox: 2024-07-01 → 2024-09-30** (Q3/2024, 3 tháng).
- **KHÓA out-of-sample: 2025-07 → 2026-03** — không ai được đụng cho tới khi design đóng băng.
- 3 tháng là quy ước có lý (đủ chu kỳ cho HL ≤ 1 phiên; đồng thời tự đuổi cặp HL nhiều-ngày —
  đã demo: GOOGL/GOOG rớt ở 3 tháng, đậu ở 6–9 tháng). Ablation độ dài formation = việc tier-2.

## Các bước

```
BƯỚC 0  UNIVERSE
        coverage ≥95% số phút giao dịch (~324 mã), GIỮ ETF, KHÔNG trần spread
        (lọc toàn vẹn dữ liệu, không phải lọc kinh tế)

BƯỚC 1  JOHANSEN trên bar 5-PHÚT — TẤT CẢ cặp (~52k)
        det_order=0, k_ar_diff=12; p-value/trace r=0
        + BH-FDR q=0.05 trên toàn bộ
        Ghi lại (không lọc): α, β (eigenvector), corr, a₁/a₂
        [5-phút vì: chính xác = 1-phút (synthetic FP/TP giống hệt; ca thật GOOGL/GOOG
         1-min chỉ +1.6 trace, vẫn rớt) mà rẻ máy ~5×. Johansen thay EG vì: đối xứng
         (khỏi chọn hướng, khỏi nhân đôi FDR) + nhanh hơn EG ~4× + code W4 có sẵn.]

BƯỚC 2  SPLIT-SAMPLE GATE
        Cắt đôi formation → Johansen từng nửa → phải đậu CẢ HAI ở ngưỡng 90% (p≤0.1, quy ước V4)
        [Đã đo: FP 13.3%→5.0%; giữ 100% cặp HL 30ph–2h; mất ~60% cặp HL≈1 phiên —
         chấp nhận, nhóm đó kém giá trị nhất cho 1-phút. User chốt GIỮ NGUYÊN.]

BƯỚC 3  HALF-LIFE trên bar 1-PHÚT — ESTIMATOR KHÁNG NHIỄU
        phi = độ dốc OLS của log(ACF_k) trên k=1..10 của spread 1-phút; HL = -ln2/ln(phi)
        Giữ: HL ∈ [2 phút, 1 phiên (390 phút)] + đếm số lần cắt mean/ngày
        [KHÔNG dùng naive c1/c0: bounce ±5bps làm HL thật 30ph/2h/1ngày đều đo ra ~9–13ph.
         Robust estimator phục hồi 28/111/420 vs thật 30/120/390.]
        [Sàn 2 phút (hạ từ 10 phút, quyết 2026-07-08, synth_hl_floor_test.py): estimator đo
         chính xác tới HL=2ph; lag 1 bar vẫn giữ 74% edge ở HL=2ph (vượt gate 60%); cặp nhanh
         trade 6–25× nhiều hơn/ngày. Dưới 2ph = bar 1-phút không phân giải nổi (giới hạn vật lý).
         ⚠️ GHI CHÚ USER: HL sẽ được XEM XÉT KỸ Ở CÁC BƯỚC SAU — con số 74% là trần lạc quan
         (synthetic chưa mô phỏng queue/adverse selection ở thang siêu nhanh); fill-sim và
         backtest net-cost sẽ là trọng tài cuối cho nhóm HL ngắn.]

ĐO & XẾP HẠNG, KHÔNG LỌC (user xem phân bố rồi quyết sau — quyết 2026-07-08):
        - XẾP HẠNG CHÍNH: tỷ lệ biên-độ / phí round-trip của chính cặp
          (phí = spread thật Week 5 half_spread_l1_bps per-bar + impact + borrow)
          → data tự trả lời "spread tối đa còn lời = ? bps"
          [Ngưỡng 2× KHÔNG lọc ở phễu — nó trở về đúng chỗ pre-commit gốc:
           luật phán quyết KẾT QUẢ BACKTEST Q1 (edge gộp thực tế ≥ 2× phí).]
        - phân bố β  (→ có cần chặn β>0, |β|≤5 không)
        - số cặp mỗi mã, đặc biệt ETF (→ có cần cap ≤2 không)
        - corr (→ có đáng bật lại làm shortcut compute cho walk-forward không)
        - số lần cắt mean/ngày
```

## Những gì cố ý CHƯA quyết (chờ kết quả phễu)

- Số cặp lấy cuối cùng; cap mỗi mã; chặn β.
- Qua đêm hay flatten cuối phiên (chờ phân bố HL thật); bỏ bao nhiêu phút đầu/cuối phiên.
- Trading window + nhịp roll walk-forward.
- Nhóm 1 (tín hiệu): loại β cho engine (static/PCA/Kalman), z-window, ngưỡng Z.

## Kiểm chứng đã hoàn tất (Phần 2, 2026-07-08 — part2_realdata_validation.py, seed 42)

- **Chứng âm** (200 cặp khác-ngành thật, Q3/2024): Johansen cv95 một mình đậu nhầm **11.0%**
  (khớp dự đoán synthetic 10–13% — test "hào phóng" trên cả data thật); thêm split-gate →
  **0.5%** (1/200, có thể là cặp liên quan thật — số đo là cận trên). Gate làm việc vượt kỳ vọng.
- **Chứng dương bán tổng hợp** (5 mã thật × HL cài 15/60/240 phút): **15/15 PASS** cả Johansen
  + gate; HL đo trên 1-phút phục hồi tốt (15m: 14.5–16.2; 60m: 55–62; 240m: 162–250 —
  HL dài lệch xuống nhẹ do ít chu kỳ, hướng lệch an toàn).
- Tốc độ: 200 cặp ≈ 7s → ước tính full ~52k cặp ≈ **25–35 phút** đơn tiến trình (song song hóa được).

## KẾT QUẢ CHẠY #1 — Q3/2024 (2026-07-08): ÂM TÍNH LỚN

Code: `Week 6/research_1min/funnel_q3_2024.py` (176s, 14 workers). Kết quả:
**52.326 cặp → raw p≤0.05: 3.623 (6.9%) → BH-FDR: 3 cặp (toàn rác thống kê:
DXCM/EW corr 0.007, AVGO/SCHW β=15.2, BAC/CRWD corr 0.17) → split-gate: 0.**
Phân bố p-value ≈ uniform. Ô quyết định: 59 cặp corr ≥0.8 (anh em kinh tế thật —
DHI/LEN, CFG/TFC, XLB/XLI...) chỉ 2 đậu marginal → **cặp cổ phiếu Mỹ thanh khoản
co-move từng phút nhưng spread KHÔNG mean-revert được ở cửa sổ intraday 3 tháng** —
cointegration stock-stock sống ở thang ngày-tuần (khớp thí nghiệm span GOOGL/GOOG,
khớp W4/V4 chỉ tìm được cặp ở formation 6 tháng với HL theo ngày, khớp nghiên cứu
firm-practice: desk intraday trade FACTOR-RESIDUAL, không phải stock-stock pairs).

Caveat trước khi đóng kết luận: mới 1 cửa sổ; k_ar_diff=12 (W4 dùng 1). Robustness
re-run ~3 phút/cửa sổ.

## KẾT QUẢ CHẠY #2 — RESIDUAL PAIRS (nấc a) — CŨNG TRỐNG

Code: `funnel_q3_2024_residual.py` (156s). Thêm tầng factor-strip của V4 (PCA 5 factor
trên returns 5-phút, cum_var=0.635) rồi chạy phễu y nguyên trên residual log-prices:
**raw p≤0.05: 6.395 (12.2%) — nhưng BH-FDR: 0 cặp** (không cặp nào đạt p<~1e-6).
Excess thô cao hơn giá thô (12.2% vs 6.9%) nhưng khuếch tán — một phần có thể là
artifact fit PCA in-sample. **Kết luận phủ cả 2 cách dựng: khái niệm CẶP (tổ hợp
2 chân cố định phải dừng suốt 3 tháng) chết ở thang intraday trên universe này.**

## KẾT QUẢ CHẠY #3 — A-L SINGLE-NAME RESIDUAL — HL THANG NGÀY

Code: `al_residual_diag_q3.py` (36s). X_i per-stock (PCA-5 stripped), out-of-fit
(W fit nửa đầu Q3, đo nửa sau trên 1-min): **median HL = 1.331 phút ≈ 3.4 phiên;
chỉ 7/304 mã trong band [2, 390 phút] — toàn bộ nằm sát mép trên (187–387 phút)**.
Biên độ KHÔNG phải vấn đề (median 62bps vs phí 14.3bps — ratio ≥2 ở 294/304 mã):
độ lệch đủ rộng nhưng KHÔNG hồi trong ngày. In-fit: median HL 2.158 phút, 0/304.

## PHÁN QUYẾT 3 TẦNG NHẤT QUÁN (Q3/2024, 324 mã thanh khoản)

| Cách dựng tín hiệu | Kết quả |
|---|---|
| Cặp giá thô (Johansen+FDR+gate) | 3 fluke → 0 |
| Cặp residual (V4-style) | FDR 0 |
| Single-name residual (A-L) | HL ~3-5 phiên, không phải phút-giờ |

**Mean-reversion trên universe này TỒN TẠI nhưng sống ở thang NHIỀU NGÀY — đúng nơi
V4 daily đang trade.** Khớp: A-L gốc cũng rebalance daily; Week 4 EOS-flatten thảm họa
(+3.7 Sharpe khi bỏ EOS); firm-practice (reversion nhanh intraday = trò chơi HFT/queue
— đã loại từ đầu vì không có L2/L3 + colocation).

## KẾT QUẢ CHẠY #4 — ROBUSTNESS 14 CỬA SỔ QUÝ (2022Q1→2025Q2) — VERDICT ĐÓNG

Code: `al_residual_robustness.py` (83s). Mọi quý, mọi chế độ thị trường:
**HL median 1.238–1.788 phút giao dịch (3.2–4.6 phiên)** — không quý nào tiến gần
thang phút-giờ. Số mã lọt band [2,390p]: 1–12/304 mỗi quý, TÊN THAY ĐỔI LIÊN TỤC
(75 mã vào band đúng 1 lần; chỉ 9 mã ≥2/14 lần, cao nhất ETR 3/14); 7 mã mép-band
Q3/2024 nhảy loạn ở các quý khác (AMD 349→6.478p) = tail noise của estimator,
KHÔNG có nhóm mã hồi-nhanh ổn định. Đuôi OOS 2025-07→2026-03 chưa hề bị đụng.

## VERDICT CUỐI CÙNG (2026-07-08)

**Mean-reversion thang phút–giờ KHÔNG tồn tại như một lớp tín hiệu khai thác được
trên cổ phiếu Mỹ thanh khoản** — 3 cách dựng × 14 cửa sổ × mọi chế độ thị trường,
âm tính đồng loạt. Biên độ chưa bao giờ là vấn đề (57–86bps vs phí 14bps) — vấn đề
là CHÂN TRỜI: reversion của phần dư riêng sống ở ~3–4.5 PHIÊN, sát cạnh vùng
V4 daily (HL 5–30 ngày) đang trade.

**Giá trị còn lại của track 1-phút:** (a) xác nhận reversion thang-ngày bền qua mọi
regime — V4 đang câu đúng ao; (b) toolchain đã validate (HL estimator kháng nhiễu,
phễu, factor projection 1-min); (c) hạ tầng 1-min chuyển hướng dùng cho
**EXECUTION-TIMING của engine daily** — intensity score của Sam vẫn có đất sống
ở tầng thực thi lệnh (chọn thời điểm/cách khớp trong ngày cho tín hiệu daily),
không cần alpha intraday.

## KẾT QUẢ CHẠY #5 — EVENT STUDY MINUTE-NATIVE (đóng track alpha 1-phút)

User thách thức verdict: "các test trên là tư duy daily; tư duy minute-native
(event-conditional, cửa sổ ngắn cuốn chiếu) sẽ khác". Đúng — và event study
(`al_event_reversal.py`, 34.596 sự kiện k=3σ, 14 quý, out-of-fit, no-lookahead σ):

| k | N | shock median | rev@5p | rev@30p | rev@120p |
|---|---|---|---|---|---|
| 3σ | 34.596 | 46 bps | **+0.91±0.14** | +0.89±0.27 | +1.18±0.42 |
| 4σ | 6.834 | 63 bps | +0.84±0.49 | +0.32±0.81 | −0.51±1.17 |
| 5σ | 1.812 | 84 bps | −1.72±1.46 | −0.11±2.18 | −0.09±2.92 |

**Tín hiệu minute-scale CÓ THẬT và cực kỳ chắc chắn thống kê (t≈6.5) — trị giá ~1 bps/sự kiện.**
Trùng khớp độc lập với Press 2023 (edge 0.75–1.25bps/vòng, cần phí ≤1bp = ghế
market-maker). Cú giật 5σ không hồi (informed move). So phí thật 12–16bps → gap 10×+
là gap CẤU TRÚC PHÍ, không phải gap tín hiệu — không thiết kế lại chiến lược nào
đóng được. Bức tranh 2 lăng kính hoàn chỉnh: daily lens = to+chậm (V4 đang ăn);
minute lens = nhanh+bé ~1bp (market-maker ăn). KHÔNG có ô to+nhanh — xác nhận
trên chính data của ta ở CẢ HAI tư duy. **Track alpha 1-phút ĐÓNG.**
