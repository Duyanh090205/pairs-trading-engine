# V4 EXEC SIMULATOR — spec PRE-COMMIT

**Trạng thái: DRAFT — chờ user duyệt TRƯỚC khi viết code.**
(Cùng khuôn kỷ luật như `gate0_passive_exec_spec.md`: khóa luật trước khi thấy số;
honest disclosure; không cherry-pick; tiered testing.)

---

## 0. Câu hỏi

Backtest V4 daily giả định fill LÝ TƯỞNG tại giá đóng cửa (close) — cùng cây nến
sinh ra tín hiệu. Live thực tế fill tại **mở cửa hôm sau + spread L1 thật** → lệch
(bằng chứng: cú CRWD +3,6% qua lễ 4/7 — vào lệnh ở close trước lễ, khớp ở open sau lễ).

**Câu hỏi:** thực thi THỰC TẾ ăn mất bao nhiêu phí / Sharpe của V4, và khung
**15:30 passive** (spread rẻ ~5×: slot_map 0,94bp vs 4,56bp đầu phiên) có gỡ lại
được không — **với TÍN HIỆU GIỮ BẤT BIẾN**.

Đây là bài đo **THỰC THI**, không đụng alpha. Nguyên tắc vàng (memory
`v4_daily_resonant_frequency`): data phút phục vụ trục THỰC THI + RỦI RO, KHÔNG
phải trục TÍN HIỆU. Đồng hồ alpha vẫn là NGÀY; ta chỉ đổi CÁCH và GIỜ khớp lệnh.

---

## 1. Nguyên tắc bất biến (invariant — KHÓA)

1. **Tín hiệu đóng băng.** entry_date, exit_date, direction, beta, notional của
   MỌI lệnh = y hệt backtest z30_composite. Simulator KHÔNG được đổi lệnh nào vào,
   lệnh nào ra, hay ngày nào.
2. **Nhân quả thời gian.** Tín hiệu chỉ biết SAU close ngày D → khớp sớm nhất =
   phiên D+1. ⟹ **V-close là "hư cấu backtest"** (không đạt được live vì bạn không
   thể giao dịch tại chính cái close bạn đang dùng để quyết định); nó là BASELINE
   để đo khoảng cách, không phải mục tiêu.
3. **Math live phải khớp backtest** (memory `week6_live_invariants`): std mẫu ddof=1;
   model phí = `engine_daily.cost_engine.compute_pair_trade_cost` (DÙNG THẲNG, không
   viết lại); Sharpe tính y hệt `fold_metrics.csv` (per-fold rồi gộp).

---

## 2. Ba biến thể fill (cùng tín hiệu — chỉ khác execution)

| | Thời điểm khớp | Giá khớp mỗi chân | Nguồn spread | Đạt được live? |
|---|---|---|---|---|
| **V-close** | close ngày D (hư cấu) | = decision_price (close_D) → trượt = 0 | model phí ngày (`cost_engine`) | KHÔNG — baseline backtest |
| **V-open** | open phiên D+1 | open_{D+1} × (1 ± hs_L1) | L1 thật @ 09:30 | CÓ — = live đang làm |
| **V-1530** | passive khung 15:30 phiên D+1 | máy fill Gate 0 (through/touch), fallback taker | L1 thật @ 15:30 | CÓ — mục tiêu rẻ hơn |

**Quy ước trượt giá mỗi chân (KHÓA — khớp `cost_overlay.py` của live):**
- `decision_price` = **close ngày ra tín hiệu** (close_{D_entry} cho vào, close_{D_exit} cho ra).
- `slippage_usd_leg` = BUY: `qty × (fill − decision)`; SELL: `qty × (decision − fill)`
  (dương = tệ hơn). Chuẩn hóa theo notional giao dịch → bps.
- Đây CHÍNH XÁC là công thức `realized_cost_bps` live tự ghi (commit 2f143bc) →
  cho phép validation ở Phase 3.

**Phân rã phí toàn phần mỗi biến thể (chống double-count spread):**

```
cost^V  =  [ trượt-fill  NẾU biến thể có fill thật   |  model_spread NẾU V-close ]
         +  model_impact  (κ×σ — không quan sát được trong lịch sử, GIỮ NGUYÊN mọi biến thể)
         +  commission (2bp/side/leg)
         +  borrow (50bp/yr chân short, calendar days)
```

- **V-close:** trượt = 0 ⟹ dùng `model_spread` ⟹ tổng = `compute_pair_trade_cost` y hệt backtest. ✔
- **V-open / V-1530:** giá fill ĐÃ chứa spread thật + gap ⟹ "trượt-fill" THAY thế
  `model_spread` (không cộng lại spread model để khỏi đếm 2 lần); giữ impact + commission + borrow.

**P&L ròng mỗi biến thể (telescoping — chứng minh trong spec):**
```
Net^V  =  Gross_intended (close→close, BẤT BIẾN từ ledger)  −  cost^V
```
Gross_intended = P&L dự định tại giá quyết định (close→close) = gross của backtest.
Chênh lệch giữa "P&L thực fill-to-fill" và "P&L close-to-close" telescope đúng bằng
tổng trượt-fill vào + ra ⟹ trừ cost^V là hạch toán ĐÚNG, không phải xấp xỉ.

---

## 2.5 Kiến trúc 2 nhánh (thứ tự build — QUYẾT 2026-07-24)

Mục tiêu bao trùm (user làm rõ): **simulator phải fill GIỐNG live**, và cách fill đó
KHÔNG đoán — mà **đo thật rồi nạp ngược vào** (calibration, không chỉ validation).

- **Nhánh 1 — Simulator lịch sử (làm NGAY, chỉ dùng data đĩa).** Ledger Phase 0 +
  replay 3 biến thể; model fill BAN ĐẦU = proxy OHLC Gate 0 + L1 thật. → ra số đầu
  tiên ngay, không chờ gì.
- **Nhánh 2 — Live probe chủ động (song song, forward).** Đặt lệnh test thật hằng
  ngày để ĐO timing + slippage → hiệu chỉnh model fill của Nhánh 1 khi dữ liệu đủ →
  chạy lại Nhánh 1 = con số "y như live". Chi tiết §7.
- **Nhánh 1 KHÔNG chờ Nhánh 2.** Prerequisite (tài khoản paper #2) chỉ chặn Nhánh 2.

## 3. Nguồn "độ thật" (data — KHÓA, đừng lấy nhầm)

| Thành phần | Nguồn | Ghi chú |
|---|---|---|
| Giá cổ phiếu 1-phút | `Week 4/data/validated/1min_phase2/{TICKER}.parquet` | close_D = bar cuối ngày D; open_{D+1} = bar 09:30 D+1; cửa 15:30 = bar 15:30–15:59 D+1 |
| Spread L1 THẬT | `Week 5/data/microstructure/spreads_1min.parquet` | `half_spread_l1_bps`, `is_valid` (row-aligned) |
| Model phí V4 | `engine_daily.cost_engine.compute_pair_trade_cost` | spread ngày + impact + commission + borrow — **dùng thẳng** |
| Máy fill passive | `trading_1min/research/gate0_passive_exec.py` (`attempt`/`real_exit`/`taker_px`) | tái dùng cho V-1530; through(bảo thủ)/touch(lạc quan) |
| Timing/gap thật (validation) | live paper (`realized_cost_bps`, commit 2f143bc) HOẶC tài khoản Alpaca paper THỨ 2 | **KHÔNG** dùng tài khoản production làm lab |

⚠️ **Fill của Alpaca paper là simulator CỦA HỌ** (khớp gần mid, không queue) → chỉ
đo được TIMING. **Spread thật phải lấy từ L1 trên đĩa.** Đừng nhầm.

Dữ liệu chỉ ≤ 2026-03 (đã có trên đĩa). KHÔNG cần data mới.

---

## 4. Phase 0 — Trade ledger z30_composite (XÂY TRƯỚC — chưa có sẵn)

**Vấn đề:** z30_composite CHỈ có `fold_metrics.csv`; KHÔNG có file trade-level. Engine
chạy trong không gian SPREAD (không lưu giá từng chân), giữ `pair_results` trong RAM
rồi vứt. `audit_trades.csv` có sẵn KHÔNG dùng được (config khác: Z=2.5, flat cost,
không composite filter).

**Việc:**
1. Re-run `Week 6/scripts/run_v4_pipeline.py` với **ship config**:
   `--entry-z 3.0 --hard-sl-z 5.0 --use-dynamic-cost --use-composite-filter`
   (đối chiếu `Week 6/documents/log.md:51`), có instrument trích trade — tái dùng
   logic `_extract_trades` từ `audits/audit_v4_negative_sharpe.py:83-151` (đã dựng
   đúng schema per-trade), bổ sung **calendar date + tickers + beta**.
2. Output: `trading_1min/results/v4_exec_sim/trades_z30_composite.csv`, schema:
   ```
   fold, trading_month, pair_id, ticker_a, ticker_b, entry_date, exit_date,
   direction(side_a ±1), beta, notional_per_leg, entry_z, exit_reason,
   duration_days, gross_pnl_spread, cost_backtest_$, net_pnl_backtest
   ```
   (entry_date/exit_date = `index[entry_idx]`/`index[exit_idx]` — calendar, KHÔNG phải bar-idx).

**⏱ Runtime ~20 phút** (36 fold × ~35s theo `elapsed_s` trong fold_metrics). >15 phút
→ **chạy smoke 1–2 fold trước, trình user số, rồi mới full** (luật job dài).

**GATE tự-nhất-quán (KHÓA — không đạt thì DỪNG):** tổng `net_pnl_backtest` và Sharpe
per-fold tái tạo từ ledger phải KHỚP `fold_metrics.csv` có sẵn (n_trades, avg_net_bps,
sharpe mỗi tháng). Thêm: `cost_backtest_$` mỗi trade phải khớp `cost_entry+cost_exit+borrow`
engine đã booking. Lệch → ledger sai → sửa trước khi đi tiếp.

---

## 5. Phase 1 — Simulator core

Với mỗi trade trong ledger × mỗi biến thể × mỗi chân (A, B):
1. Kéo giá cổ phiếu từ 1-phút: `decision_price` (close_D), `fill_price^V`
   (V-open: open_{D+1}×(1±hs); V-1530: qua máy Gate 0; V-close: = decision).
2. Tính `slippage_usd` mỗi chân; `cost^V` theo §2 (impact/commission/borrow từ model).
3. `Net^V = gross_pnl_spread(ledger) − cost^V`.

**V-1530 chi tiết (tái dùng Gate 0):** đặt lệnh chờ passive tại bar 15:30 phiên D+1,
cửa sổ W (base = 2 bar, sens 1/5), luật through/touch trên high/low; **không khớp
trong cửa → taker tại 15:58** (trả full half-spread). Hướng: BUY chân long / SELL chân
short. (S4-asymmetric intensity của Sam = nâng cấp Phase 4, chưa cắm ở bản base.)

**Sanity giá:** nếu bar 09:30 hoặc 15:30 của D+1 thiếu / L1 invalid → ghi nhận
`fill_status=missing`, fallback theo quy ước KHÓA (dùng model_spread cho trade đó,
đánh cờ) và **báo cáo tỷ lệ**. Không im lặng bỏ.

---

## 6. Phase 2 — Báo cáo (KHÓA — báo mọi biến thể, không cherry-pick)

- `cost_by_variant.csv`: mỗi trade × 3 biến thể — trượt-fill, spread, impact,
  commission, borrow, cost tổng (bps + $).
- `sharpe_by_variant.csv`: Sharpe / avg_net_bps / total_return / max_dd / win_rate
  per-fold VÀ gộp, cho **cả 3 biến thể** (tính y hệt `metrics_daily`).
- **Delta chính:** V-close → V-open → V-1530: mất/gỡ bao nhiêu bp/trade và bao nhiêu
  điểm Sharpe. Đây là câu trả lời.
- Phân tầng theo z-bucket [3,4)/[4,6)/[6+) (bản đồ intensity cho Sam) và theo
  gap-overnight (|open−close|) để thấy V-open đau ở đâu.

---

## 7. Phase 3 — LIVE PROBE chủ động (đo thật → hiệu chỉnh) + validation

**Đổi vai trò của live:** không chỉ kiểm chứng — live là **NGUỒN HIỆU CHỈNH** cho
model fill. Ta đặt lệnh probe thật, đo timing + slippage, nạp NGƯỢC vào simulator để
nó fill giống live. (Quyết 2026-07-24: chọn **probe chủ động**, không phải thu hoạch thụ động.)

### 7.1 Tài khoản (PREREQUISITE — chặn Nhánh 2, user phải cấp)
- Dùng **tài khoản Alpaca paper THỨ 2, RIÊNG** (phòng lab). API key/secret riêng
  (vd `Week 6/.env.probe`, gitignored).
- ⚠️ **TUYỆT ĐỐI không** đặt probe lên tài khoản **production V4** — reconcile loop
  sẽ thấy vị thế/lệnh lạ → **false halt** (đúng bug vừa vá 2f143bc). Tách account là bắt buộc.

### 7.2 Probe đặt gì (mỗi phiên)
- Rổ ~10–20 mã trải nhiều tầng thanh khoản (lấy từ universe V4).
- 2 kiểu lệnh khớp đúng 2 biến thể cần đo, **cả BUY và SELL**, notional ~$1000 (cỡ V4 thật):
  - **kiểu Open (đo V-open):** lúc mở cửa, lệnh marketable → đo giá khớp vs close hôm
    trước (tham chiếu quyết định) + độ trễ submit→fill.
  - **kiểu 1530 (đo V-1530):** lúc 15:30, lệnh chờ passive tại/gần bid(mua)/ask(bán) →
    đo **bao lâu thì khớp** trong cửa 15:30→close, khớp/không-khớp, giá khớp vs tham chiếu.

### 7.3 Ghi gì mỗi lệnh (probe_fills.csv, tích lũy)
`ticker, side, kiểu, submit_ts, ack_ts, fill_ts|cancel_ts, limit_px, ref_px, fill_px,
fill_qty, slippage_bps, time_to_fill_s, filled(bool), slot_giờ, tầng_thanh_khoản`.

### 7.4 Nạp NGƯỢC gì vào simulator (điểm cốt lõi của user)
Phân phối thực nghiệm theo (kiểu × slot-giờ × tầng-thanh-khoản):
**P(khớp trong cửa)**, phân phối **time-to-fill**, phân phối **slippage**. → model fill
V-open/V-1530 của Nhánh 1 rút số từ đây, thay cho (hoặc trộn với) proxy OHLC Gate 0.

### 7.5 Validation
Ghép sim ↔ probe: slippage V-open sim ≈ slippage probe đo được. Và (khi production tích
đủ) so tiếp với `realized_cost_bps` mà production tự ghi (commit 2f143bc, deploy 2026-07-24).

### 7.6 ⚠️ Cận LẠC QUAN (honest disclosure — bắt buộc dán nhãn)
Alpaca paper khớp **ngay khi giá chạm**, bỏ qua **hàng đợi (queue)** → P(khớp) cao hơn
thực, time-to-fill thấp hơn thực. ⟹ mọi số simulator hiệu-chỉnh-bằng-paper = **best-case**;
tiền thật sẽ **tệ hơn**. Không được trình như số cuối. (Chứng nhận real-money = Gate xa hơn,
cần tài khoản thật — user chưa có SSN, xem [[week6_1min_data_feasibility]].)

---

## 8. Luật pre-commit (KHÓA trước khi chạy số)

1. Tín hiệu đóng băng (ledger z30_composite ship config, đã qua GATE §4).
2. Báo cáo **cả 3 biến thể** + delta live-vs-sim. KHÔNG cherry-pick (mọi cặp, mọi biến thể).
3. **Tiered:** khói (vài lệnh, 1 cặp) → full. Job >15' hỏi trước (§4).
4. Data chỉ ≤ 2026-03 trên đĩa.
5. Sharpe/metric tính y hệt `metrics_daily`; t-stat gom cụm ngày/tuần khi báo drift.
6. Honest disclosure: sample validation nhỏ (§7); đánh đổi V-1530 (§9) nêu rõ, không giấu.

---

## 9. Quyết định thiết kế cần USER xác nhận (⚠️ điểm cốt lõi)

**D0 — Vai trò live (ĐÃ QUYẾT 2026-07-24):** live = **nguồn hiệu chỉnh** (calibration),
không chỉ validation; chọn **probe chủ động** (Cách A) trên **tài khoản paper #2 riêng**.
Chi tiết §7. Còn chờ user cấp: API key/secret của account paper #2.

**D1 — Thời điểm V-1530 (quan trọng nhất).** Theo invariant §1.2, tín hiệu chỉ biết
sau close_D ⟹ V-1530 khớp **15:30 của phiên D+1** (không phải 15:30 ngày D). Hệ quả:
V-1530 được spread rẻ ~5× NHƯNG chịu **thêm ~1 phiên trôi giá** so với V-open (khớp
09:30 D+1). Thí nghiệm sẽ ĐO xem spread rẻ có thắng phần trôi thêm không — **không
giả định trước**.
> Phương án thay thế "V-1530-anticipate" (khớp 15:30 NGÀY D, tính Z bằng giá 15:30
> làm proxy close) sẽ né được gap qua đêm NHƯNG **vi phạm invariant** (tín hiệu tính
> trước close) ⟹ để riêng làm thí nghiệm tương lai, KHÔNG nằm trong bản base này.
> **Đề xuất của tôi: giữ D+1 (tôn trọng invariant).** Bạn xác nhận hoặc đổi.

**D2 — Xử lý impact.** Impact (κ×σ) không quan sát được trong lịch sử → tôi **giữ
nguyên model cho cả 3 biến thể** (nó triệt tiêu khi so sánh delta, không thiên vị).
Xác nhận cách này ổn, hay muốn set impact=0 cho V-open/V-1530 (giả định lệnh nhỏ
không tác động)?

**D3 — Phạm vi ledger.** Full 2023-01→2026-03 (~20') hay smoke vài fold trước để
duyệt cơ chế? (Đề xuất: smoke trước.)

---

## 10. Caveats ghi trước (honest disclosure)

1. OHLC 1-phút không thấy queue → V-1530 lạc quan; xử bằng bracket through/touch như Gate 0.
2. Impact = proxy model, không quan sát được → giữ đồng nhất mọi biến thể (D2).
3. Sample validation live mỏng & mới (§7) — báo n, mạnh dần forward.
4. V-1530 thêm ~1 phiên trôi giá vs V-open (D1) — đo, không giả định.
5. Alpaca paper khớp gần mid (không queue) → chỉ TIMING thật từ live; spread từ L1 đĩa.
6. `daily_spread_cache` (median ngày, model) vs L1 intraday (thật) có thể lệch — báo cả hai.
7. **Số hiệu chỉnh bằng Alpaca paper = best-case** (paper bỏ qua queue) — tiền thật tệ hơn;
   dán nhãn rõ mọi output từ Nhánh 2 (§7.6).

---

## 11. Deliverables

**Nhánh 1 (simulator lịch sử):**
- Code: `trading_1min/research/v4_exec_simulator.py` (+ extractor ledger Phase 0).
- Kết quả: `trading_1min/results/v4_exec_sim/` — `trades_z30_composite.csv`,
  `cost_by_variant.csv`, `sharpe_by_variant.csv`, `report.txt`.

**Nhánh 2 (live probe):**
- Code: `trading_1min/research/v4_exec_probe.py` (chạy hằng ngày, tài khoản paper #2).
- Data: `trading_1min/results/v4_exec_sim/probe_fills.csv` (tích lũy) + phân phối fill
  hiệu chỉnh nạp lại Nhánh 1; `live_vs_sim_validation.csv`.

- Seed cố định 42 cho mọi bốc thăm (nếu cần control matching kiểu Gate 0).
