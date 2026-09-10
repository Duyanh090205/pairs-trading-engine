# Prompt cho session mới — Build ENGINE V0 cho track trading 1-phút

> Copy toàn bộ phần dưới đây dán vào chat mới. Auto-memory của project sẽ tự load kèm
> (đọc kỹ `week6_1min_backtest_track` — nếu mâu thuẫn thì ưu tiên memory mới hơn).
> Lịch sử đầy đủ 11 thí nghiệm: `Week 6/documents/funnel_1min_spec.md`.

---

Ta tiếp nối track nghiên cứu 1-phút (repo này). Session trước (2026-07-08→10) đã chạy **11 thí nghiệm** và tìm ra **một tín hiệu sống sót qua kiểm định** nhưng kèm **một quả mìn đo lường** phải xử trước tiên. Session này: build **Engine v0** — gom mọi script rời rạc về một engine walk-forward chuẩn, nghiệm thu bằng tái lập số cũ, rồi chạy bản vá đo lường.

## Bối cảnh đã chốt — KHÔNG bàn lại, KHÔNG chạy lại

1. **V4 daily engine đang live — không đụng.**
2. **Các ngõ cụt ĐÃ CHẾT (đủ bằng chứng, đừng redo):** cointegration formation 3 tháng (giá thô: 52k cặp → 0; residual: FDR 0); Avellaneda-Lee single-name s-score (HL residual ~3–4.5 phiên, không phải phút); event-reversal sau cú giật (+0.91bp — thật nhưng dưới phí 15×); intraday momentum SPY (decayed về 0); adaptive window theo vol (không thêm giá trị); formation 0.5 ngày (rớt xác nhận); formation ≥3 ngày (suy giảm, 4 ngày âm nặng).
3. **TÍN HIỆU SỐNG SÓT — spec chính xác (không sửa khi tái lập):**
   - Universe: **top-100 mã median spread hẹp nhất** trong nhóm coverage ≥95% (`spread_summary.parquet`, cột `n_obs` ≥ 0.95×max; xếp theo `median_bps` tăng dần), giữ ETF.
   - Mỗi tuần (5 ngày giao dịch, roll 5 ngày): **Johansen** (det_order=0, k_ar_diff=12) trên **390–780 bar 1-phút cuối** (1–2 phiên — cao nguyên phẳng, không phân định được trong vùng này); giữ cặp **trace > cv95** và **0 < β ≤ 5** (β = −v[1]/v[0] từ eigenvector). ~500–1.800 cặp/tuần.
   - Tuần kế tiếp: spread = logA − β·logB (close 1-phút); z = (spread − mean_formation)/std_formation; **vào |z|>2** fill close bar kế (lag 1); **ra z cắt 0**; **ép đóng cuối tuần**.
   - Kết quả đã đo: thăm dò H1/2025 +8.79±1.78; xác nhận H2/2024 **+10.80±1.38** (t per-trade 7.8, N=59.455); chịu trễ: lag2/3 giữ 94%/87%; open-fill giữ 95% (sạch bounce); **NET −2.9bp** với phí bảo thủ 13.7bp.
   - Giải phẫu: hit 73%, thắng TB +137bp / thua TB −334bp; **31.5% lệnh bị ép đóng cuối tuần (TB −268bp)** — luật thoát là bài toán mở lớn nhất. HL cặp được chọn: 23 phút in-window (selection bias) → 212 phút out-of-window.
4. **QUẢ MÌN ĐO LƯỜNG (lý do engine v0 tồn tại):** hai script cùng spec 780 bar, cùng H2/2024, chỉ khác **mốc chia tuần** (~10 ngày + 2 tuần đầu) → gộp lệch 44% (+10.80 vs +5.98). Trades cùng tuần chịu chung cú sốc thị trường (vd 05/08/2024) → **t per-trade bị thổi phồng; đơn vị độc lập thật ≈ TUẦN (~23/nửa năm)**.
5. **Data đã cháy cho chiến lược này:** H1/2025 (thăm dò), H2/2024 (xác nhận + sweep). **Còn sạch: 2022, 2023, H1/2024.** **KHÓA TUYỆT ĐỐI: 2025-07 → 2026-03** (out-of-sample cuối, chưa ai nhìn).
6. **Phí:** cost_rt = 2×(half_A + β·half_B), half = `median_bps`/2 từ spread_summary (median cả kỳ 2022–2026 — bảo thủ vì 2022 giãn rộng). Tính phí đúng-kỳ từ `spreads_1min.parquet` = việc treo (user bảo để sau). Passive execution / intensity score của Sam = quân bài phí, chưa đụng.
7. User có **4 điểm dặn từ cuộc nói chuyện với Sam** (về intensity score + thoát/đặt lệnh khi thị trường đi ngược) **chưa được ghi vào sổ** — khi đụng bài toán exit, HỎI user liệt kê lại trước khi thiết kế.

## Nhiệm vụ session này: ENGINE V0

**Vị trí (quyết định của user): folder MỚI `trading_1min/` ở GỐC REPO** — không nằm trong Week nào. Code cũ ở `Week 6/research_1min/` chỉ để đối chiếu, không sửa.

```
trading_1min/
├── engine/
│   ├── data.py       # nạp 1-min/5-min, universe, phí — MỌI quy ước ở một chỗ
│   ├── selection.py  # chọn cặp mỗi kỳ (Johansen window ngắn; cắm biến thể sau)
│   ├── simulate.py   # máy trạng thái lệnh: vào/ra/lag/fill-mode/ép-đóng — tham số hóa
│   ├── stats.py      # ★ t-stat GOM THEO TUẦN mặc định + quét mốc chia + control tự động
│   └── run.py        # config → chạy → report chuẩn (gộp/net/theo-tuần/phân bố đuôi)
├── configs/          # mỗi thí nghiệm = 1 file config, không copy-paste script
└── results/
```

**CỬA NGHIỆM THU (bắt buộc trước mọi thứ khác — bài học `week6_live_invariants`):** engine phải **tái lập bằng số** hai run cũ khi cho đúng config:
- Run #10 (`Week 6/research_1min/confirmation_test.py`): 780 bar, H2/2024, tuần anchor tại index 10 của danh sách ngày H2-only → **+10.80±1.38, N=59.455** (lag1_close).
- Run #11 (`Week 6/research_1min/window_opt_stage1.py`): 780 bar, H2/2024, tuần anchor từ ngày trade đầu ≥2024-07-01 (data runway từ 2024-01) → **+5.98±1.72, N=64.837**.
Lệch = có bug, dừng lại tìm. Khớp cả hai = engine đúng, và đã tự chứng minh nó xử lý được đúng cái khác biệt anchor từng gây ra quả mìn.

**NHIỆM VỤ #1 sau nghiệm thu — BẢN VÁ ĐO LƯỜNG (pre-commit ngay từ giờ):**
- Chạy {390, 780} bar × {H2/2024, H1/2024 (kỳ MỚI TINH)} × **5 mốc chia tuần** (offset 0–4 ngày), control bốc thăm mỗi cell.
- Thước đo: **t-stat gom theo tuần** (mỗi tuần 1 quan sát = mean bps của tuần) trên gộp và trên hiệu-so-control.
- **Luật phán quyết (khóa trước khi chạy):** tín hiệu "còn sống" nếu weekly-clustered t ≥ 2 cho hiệu-so-control, dấu dương ở ≥4/5 mốc chia, trên CẢ HAI kỳ. Không đạt → hạ cấp tín hiệu về "chưa chứng minh", dừng xây thêm, báo cáo trung thực.

## Cách làm việc (giữ nguyên từ session trước)

- **Từng bước nhỏ — user quyết trước mỗi bước.** Không batch quyết định.
- **Pre-commit luật trước khi chạy**; honest disclosure (chấp nhận kết quả âm, flag mẫu nhỏ); không sweep tham số rồi chọn cái đẹp.
- Hỏi trước khi chạy job >25 phút. Tiered testing: nghiệm thu nhỏ → chạy thật.
- User quant-literate nhưng **không phải SWE** — giải thích bằng tiếng Việt đơn giản (skill `/explain`).

## Đường dẫn dữ liệu

| Thứ | Đường dẫn |
|---|---|
| Giá 1-min (528 mã, 2022→2026-03) | `Week 4/data/validated/1min_phase2/{TICKER}.parquet` — cols open/high/low/close/volume, index `timestamp_et` tz ET |
| Giá 5-min (log_close) | `Week 4/data/validated/5min_phase1/{TICKER}.parquet` |
| Thống kê spread (phí) | `Week 5/data/microstructure/spread_summary.parquet` — `median_bps` = FULL spread |
| Spread per-bar THẬT (8GB, row-group/mã) | `Week 5/data/microstructure/spreads_1min.parquet` |
| Script cũ đối chiếu | `Week 6/research_1min/*.py` + `results/` |
| Lịch sử & verdict 11 run | `Week 6/documents/funnel_1min_spec.md` |

Bắt đầu bằng: (1) xác nhận đã đọc memory + prompt này, (2) đề xuất thứ tự build 5 module + kế hoạch nghiệm thu, (3) hỏi những gì còn mơ hồ TRƯỚC khi viết code.
