# Prompt cho session mới — Thiết kế & build engine backtest 1-phút trên data có sẵn

> Copy toàn bộ phần dưới đây dán vào chat mới. (Auto-memory của project sẽ tự load kèm — prompt này là bản tóm tắt tự đủ, nếu mâu thuẫn thì ưu tiên memory mới hơn.)

---

Ta tiếp tục dự án pairs-trading (repo này). Session trước đã chốt xong phần **data sourcing** cho pivot 1-phút; session này chuyển sang **thiết kế + build engine backtest 1-phút** trên data đã có trên đĩa. Đọc auto-memory trước (đặc biệt `week6_1min_data_feasibility`, `week6_rejected_approaches`, `quant_decision_rules`).

## Bối cảnh đã chốt — KHÔNG bàn lại

1. **V4 daily engine đang live (Alpaca paper) — không đụng vào.** Nhánh 1-phút là track nghiên cứu song song, do Sam (mentor) đẩy; verify empirically, không tin lời.
2. **Sàn giao dịch tối thiểu = 1 phút.** Không làm sub-minute (cần L2/L3 thật + hạ tầng HFT — không có). Execution research chỉ ở **L1** (L2/L3 trong orderbook.parquet là SYNTHETIC — đã chứng minh: bid_sz==ask_sz 100%, L2=2×L1 cố định).
3. **Backtest = $0, data có sẵn — KHÔNG cần mua/kéo gì.** Live real-time quote là chuyện SAU: lựa chọn thực tế duy nhất là Alpaca SIP $99/tháng, CHỈ mua nếu backtest hứa hẹn (user không có SSN → IBKR/Schwab bất khả; Finazon đã bỏ — không mua được plan; Databento RT bị loại — EQUS.MAX chưa có real-time). Kế hoạch 3 chặng: (1) backtest $0 → (2) paper plumbing bars free → (3) live $99.
4. Các thí nghiệm 1-min trước đây (2b/3b/3c ngày 2026-07-04) chạy trên **IEX free rác** (chỉ ~71/150 mã đủ phủ) → số liệu KHÔNG tin được, chỉ dùng làm tham khảo toolchain. Data Polygon on-disk mới là nền móng thật.
5. Phương pháp làm việc: **tiered testing** (analytical → subset 5–10 cặp → full), pre-committed decision rules TRƯỚC khi chạy, honest disclosure (chấp nhận kết quả âm, flag mẫu nhỏ), hỏi trước khi chạy job >25 phút. User quant-literate nhưng không phải SWE — giải thích bằng tiếng Việt đơn giản.

## Data trên đĩa (đã verify schema 2026-07-08)

| Data | Path | Chi tiết |
|---|---|---|
| **Giá 1-min** | `Week 4/data/validated/1min_phase2/*.parquet` | 528 mã (1 file/mã), cols `open,high,low,close,volume` + index `timestamp_et` (tz-aware ET), 2022-01-03 09:30 → 2026-03-19 16:00, ~410k dòng/mã, ~99% coverage. Cũng có `5min_phase1/`, `daily_phase3/` |
| **Spread L1 THẬT** | `Week 5/data/microstructure/spreads_1min.parquet` | 195,252,716 dòng (8GB), cols: `timestamp_et, ticker, is_valid, full_spread_l1_bps, half_spread_l1_bps, full_spread_l2_bps, full_spread_l3_bps, liquidity_l1, spread_std_1d, raw_spread_mean_1d`. Row-aligned với giá. **Chỉ L1 tin được** |
| Thống kê spread | `Week 5/data/microstructure/spread_summary.parquet` (526 mã: median/p95/p99), `spread_seasonality.parquet` (theo bucket giờ-trong-ngày — nguyên liệu cho intensity score), `spread_rolling.parquet` | |
| Orderbook | `Week 5/data/orderbook.parquet` (213M dòng, L1–L3) | ⚠️ L2/L3 synthetic, chỉ L1 thật |
| **Cost model code** | `Week 5/src/plan1_cost_model/` | 3 thành phần: spread (half_spread_l1_bps) + impact (κ × spread_std_1d; κ theo tier 0.3/0.5/0.8) + borrow (50bps/yr trên chân short). Tái dùng |
| **Engine Week 4** | `Week 4/src/phase2_execution/` (engine.py, kalman.py), `phase3_backtest/` (pnl, latency, metrics) | Gốc daily; tái dùng mảnh ghép. Spec ở `Week 4/CLAUDE.md` |
| Databento | User có account + **$125 credit (CHỈ historical)** | Dùng cross-check chất lượng Polygon (Reddit tố dup-rows/wrong-splits) + kéo NBBO lịch sử mẫu nếu cần validate spread Week 5 |

Lưu ý: data kết thúc 2026-03-19 (~3.5 tháng cũ) — không sao cho backtest.

## Nhiệm vụ session này

Thiết kế trước, code sau (bàn thiết kế → chốt → mới build). Hai câu hỏi lõi:

**Q1 — Tín hiệu:** Có tồn tại edge mean-reversion 1-phút trên universe của ta không, gross và net? Gates đã pre-commit từ session trước:
- Edge gộp/round-trip ≥ **2× chi phí** (chi phí ≈ 4 nửa-spread ≈ 12–20bps tùy cặp; lấy từ spread THẬT Week 5, per-bar chứ không phẳng). 1–2× = mong manh (chỉ execution thông minh cứu được), <1× = chết.
- ≥ **30–50 round-trip/cặp** trong cửa sổ test (mẫu nhỏ hơn = không kết luận).
- **Trễ 1 bar** phải giữ ≥60% edge (retail luôn chậm).

**Q2 — Execution (ý "intensity score" của Sam — điểm được học thuật ủng hộ nhất, nền tảng Cartea/Jaimungal arXiv 1210.1625):** Build + backtest **intensity score v0 (1–100) = f(|z|, half-life cặp, regime, trạng thái spread)** để gate cách vào lệnh: score cao → cross spread (trả taker, chắc khớp); score thấp → limit passive (capture spread, chấp nhận không khớp). Cần **fill simulator L1**: quy tắc fill đơn giản tại touch (giá xuyên qua mức limit → khớp), khai báo rõ caveat lạc quan (bỏ qua queue priority + adverse selection). Trả lời câu của Sam: *"execution của mình tốt tới đâu?"* — so sánh net P&L của 3 policy: always-aggressive / always-passive / intensity-gated.

**Việc nền (làm trước, rẻ):** data-quality check trên giá 1-min Polygon — dup rows, split sai (đối chiếu vài mã với Databento credit), phút trống, lọc RTH 09:30–16:00.

## Yêu cầu thiết kế engine

- Event-driven trên bar 1-phút, **không look-ahead** (quyết định tại bar t chỉ dùng dữ liệu ≤ t; fill sớm nhất tại bar t+1).
- Cost per-bar từ spreads_1min (join theo `timestamp_et + ticker`), không dùng cost phẳng.
- Walk-forward, tách in/out-of-sample rõ; báo cáo trung thực (gross vs net, phân rã chi phí, negative control).
- Bắt đầu subset: chọn 5–10 cặp thanh khoản cao từ universe (hoặc tái dùng cặp V4 làm điểm xuất phát) trước khi mở full.
- RAM: file spread 8GB — đọc theo cột/filter theo ticker (pyarrow), đừng load nguyên file.

Bắt đầu bằng: (1) xác nhận đã đọc memory + prompt này, (2) đề xuất kiến trúc engine + kế hoạch tiered test, (3) hỏi những gì còn mơ hồ TRƯỚC khi viết code.
