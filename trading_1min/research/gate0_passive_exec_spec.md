# GATE 0 — Passive execution feasibility — spec PRE-COMMIT

**Trạng thái: KHÓA 2026-07-23** — user duyệt bản nháp (5 quyết định thiết kế giữ
nguyên; DNA rủi ro: chốt sau, báo cáo 2 kịch bản).
**Amendment 2026-07-23 (TRƯỚC khi chạy bất kỳ số nào** — từ vòng rà văn liệu,
chi tiết `gate0_lit_notes.md`): (1) thêm markout sau-KHỚP chuẩn realized-spread
Huang–Stoll vào mục adverse selection; (2) ghi rõ không giả định maker rebate;
(3) caveat queue dẫn Moallemi–Yuan; (4) ghi chú cost_eff khớp chuẩn phạt-lệnh-
không-khớp Harris–Hasbrouck. Không amendment nào đụng luật đậu/rớt.

## Câu hỏi

Đặt lệnh chờ (maker) trên follower trong 1–2 phút sau tín hiệu leader, **phí thực
round-trip hiệu dụng là bao nhiêu bp**? So với trần edge đã đo 1–1,6bp (scan H2/2024),
track lead-lag chỉ sống nếu phí thực ≤ ~1,5bp/vòng.

Đây là bài đo THỰC THI, không phải claim alpha — sự kiện tín hiệu chỉ là cái cớ
để đo phí đúng tại những phút ta sẽ cần giao dịch.

## Input từ Sam (4 điểm, user liệt kê 2026-07-23) — ánh xạ vào thiết kế

| # | Sam nói | Vào Gate 0 | Để Spec 2 |
|---|---|---|---|
| S1 | Tận dụng market-making: đặt gần mid, chấp nhận không khớp ngay | 3 biến thể giá đặt: bid / mid−¼spread / mid | — |
| S2 | Intensity score 1–100: cao → sweep/cross; thấp → make market, đừng vội | Bảng kết quả phân tầng theo z-bucket [3,4), [4,6), [6,∞) | Mapping intensity→aggressiveness |
| S3 | Mid-freq: quyết định ≤ ~1 phút; phải chạy SIMULATION đánh giá thực thi | Cửa sổ khớp W=2' (sens. 1/2/5); toàn bộ bài này = simulation Sam yêu cầu | — |
| S4 | Thoát bất đối xứng: ngược → cắt lỗ aggressive; thuận → passive, đừng thoát dễ | Loss-cut taker ngay khi ngược ≥3σ; exit kế hoạch = passive-rồi-taker | Repricing liên tục theo dải z |

Ghi chú S4: Gate 0 chỉ mô phỏng dạng "lite" (loss-cut aggressive + exit passive);
repricing liên tục / dải aggressiveness đầy đủ là nâng cấp Spec 2.

## Dữ liệu — CHỈ 2024 (đã cháy)

- Bar 1-phút: `Week 4/data/validated/1min_phase2/{TICKER}.parquet` (OHLC, index timestamp_et).
- L1 thật: `Week 5/data/microstructure/spreads_1min.parquet` (half_spread_l1_bps, is_valid).
- Universe: `trading_1min.engine.data.load_universe(100)` — tất định, y hệt scan lead-lag.
- KHÔNG đụng 2022–2023 (sạch) và 2025-07→2026-03 (két sắt).

## Thiết kế mô phỏng

### Sự kiện tín hiệu (proxy, chỉ để đo thực thi)

- **Leader** = mọi ETF nằm trong universe-100 (dự kiến SPY, QQQ, XL*…; danh sách
  in ra ở bước khói, cố định từ universe — không chọn tay).
- Return 1-phút = diff log(close), trong-phiên (bỏ overnight), ffill theo quy ước engine.
- σ động = std mẫu (ddof=1) rolling 60 phút gần nhất của leader, trong phiên, tối thiểu 30 obs.
- **Sự kiện**: |r_t| ≥ 3σ (z = |r|/σ). Refractory 5 phút/leader. Nhiều leader nổ cùng
  phút → gộp thành 1 phút-tín-hiệu, hướng theo leader có |z| lớn nhất.
- Loại: 10 phút đầu phiên (σ chưa đủ obs, auction nhiễu) và sự kiện sau 15:38
  (không đủ giờ hoàn tất round-trip trước close).
- **Hướng vào lệnh (primary): THEO CHIỀU leader** (chase) — cơ chế index-arb
  diffusion; trục ETF→mã lẻ trong scan có ρ dương. Fade (ngược chiều) = diagnostic
  phụ, không gate.

### Follower & attempt

Mỗi phút-tín-hiệu (đã gộp) → 1 attempt trên **MỌI follower** (~90 mã non-ETF của
universe-100). Estimand = phí passive của từng mã tại phút tín hiệu — thuộc tính
microstructure của mã, KHÔNG lệ thuộc pair set → không dính lookahead chọn cặp,
dùng được cả năm 2024.

Bỏ attempt nếu L1 follower tại phút quyết định invalid/NaN (báo cáo tỷ lệ bỏ).

### Máy fill ENTRY (proxy OHLC + L1)

Quyết định tại close bar t (phút tín hiệu); lệnh nằm trên sổ từ bar t+1 (kỷ luật
lag, khớp latency mid-freq S3). Mid proxy = close; bid = close×(1−hs); ask = close×(1+hs),
hs = half_spread_l1_bps/10⁴ tại phút t.

Ba biến thể giá đặt (mua; bán đối xứng):
- **V1 "bid"**: p_lim = close_t×(1−hs) — earn full half-spread, khó khớp nhất.
- **V2 "mid−¼"**: p_lim = close_t×(1−hs/2).
- **V3 "mid"**: p_lim = close_t — kiểu Sam "trade close to the middle".

Điều kiện khớp trong bar u ∈ (t, t+W], W = 2 phút (base):
- **THROUGH (bảo thủ — chuẩn gate chính)**: low_u ≤ p_lim − 1 tick ($0.01) — giá
  phải xuyên qua lệnh, không cần đoán queue.
- **TOUCH (lạc quan)**: low_u ≤ p_lim — chạm là khớp; chỉ dùng cho cận trên bracket.
- Giá khớp = p_lim (không bao giờ tốt hơn). Không khớp trong W → hủy (missed).

### Máy exit (S4 lite)

- Hold kế hoạch h* = 15 phút từ bar khớp (sens. 5/15/30 — báo cáo, gate ở 15).
- Tại bar khớp+h*: đặt thoát passive tại far touch (bán: close×(1+hs)); cửa sổ
  W_exit = 2 phút, cùng quy ước through/touch với entry; không khớp → **taker**
  (bán tại bid, trả full half-spread).
- **Loss-cut (S4 "ngược → aggressive")**: nếu trước đó mid đi ngược ≥ L so với giá
  khớp entry, L = 3×σ_follower (rolling 60' tại phút vào, sàn 10bp) → taker NGAY
  tại bar vi phạm.
- Bar vừa khớp entry vừa chạm loss-cut → thứ tự XẤU NHẤT (khớp trước, cắt sau).
- Ép đóng taker muộn nhất 15:58.

### Benchmark & công thức phí (KHÓA)

Paper trade (không ma sát, khớp chắc chắn, CÙNG luật quyết định trên mid):
vào mid close_{t+1}; loss-cut cùng luật trên mid; ngược lại ra mid close bar
thoát kế hoạch.

- **IS** (implementation shortfall, bp/round-trip hoàn tất) = PnL_paper − PnL_real,
  chỉ trên các attempt ĐÃ khớp entry. Gộp trong IS: half-spread kiếm được (âm),
  adverse selection (dương), taker fallback + loss-cut (dương).
- **f** = fill rate entry trong W.
- Phí ngoài spread: commission 0, **maker rebate 0** (Alpaca retail không có
  rebate) — không cộng khống lợi thế maker.
- **cost_eff (số GATE, bp/attempt)** = f×IS + (1−f)×edge_ref, **edge_ref = 1,5bp khóa**
  (cận trên dải edge đo được 1–1,6bp).
  Ý nghĩa: cost_eff = hao hụt alpha paper→thực per tín hiệu. Đại số: net/attempt
  = f×(edge−IS) ≥ edge − cost_eff với mọi edge ≤ edge_ref ⇒ cost_eff ≤ 1,5 và
  edge = 1,5 ⇒ net ≥ 0.
- Điều kiện phụ chống suy biến (f→0 cho cost_eff→1,5 rỗng nghĩa): **f ≥ 25%**.
- Cấu trúc "phạt lệnh không khớp" cùng tinh thần thước đo precommitted-trader
  của Harris–Hasbrouck (1996).
- SE/t: gom cụm theo NGÀY cho IS và mọi drift; CI 95% báo cáo.

## Ba thành phần bắt buộc (roadmap) — cách đo

1. **Fill rate**: f theo biến thể × through/touch × z-bucket × giờ-trong-ngày.
2. **Adverse selection**:
   (a) drift mid Δ ∈ {1,5,15}' sau quyết định: nhóm khớp vs không-khớp, t day-clustered;
   (b) spread follower TẠI phút tín hiệu vs baseline matched cùng-phút-trong-ngày
       (spread có giãn đúng lúc cần vào không?);
   (c) **control khớp-phút (null analog)**: chạy CÙNG máy fill tại N phút ngẫu nhiên
       matched (cùng mã, cùng phút-trong-ngày, ngày khác, cách mọi tín hiệu ≥5',
       seed 42, N = số sự kiện thật) → IS_signal − IS_control = phần độc RIÊNG
       của phút tín hiệu;
   (d) **markout sau-KHỚP** (chuẩn realized-spread Huang–Stoll 1996):
       side×(mid_{fill+Δ} − p_fill) theo bp, Δ ∈ {1,5,15}' — maker còn giữ được
       bao nhiêu half-spread sau khi giá điều chỉnh.
3. **Chi phí cơ hội**: (1−f)×edge_ref per mã + quy đổi bp danh mục; kèm kiểm tra
   "lệnh trượt có phải lệnh ngon nhất": drift sau-quyết-định của nhóm không-khớp.

## Luật phán quyết GATE 0 (KHÓA khi user duyệt — không sửa sau khi thấy số)

Chọn **MỘT biến thể giá đặt chung** cho mọi mã = biến thể có nhiều follower đậu
nhất ở chuẩn THROUGH (biến thể đó thành config khóa cho Spec 2 — Gate 1/2 sẽ
tái kiểm nó trên data sạch; 3 biến thể là thiết kế thực thi, không phải sweep alpha).

Follower **đủ điều kiện**: ≥200 attempts & tỷ lệ bỏ-vì-L1-invalid < 20%.
Follower **ĐẬU** = đủ điều kiện & cost_eff ≤ 1,5bp & f ≥ 25% (trên biến thể chung).

| Kết cục | Điều kiện | Hành động |
|---|---|---|
| **ĐẠT chắc** | ≥30 follower đậu ở chuẩn **THROUGH** | Mở Gate 1 |
| **ĐẠT sát nút** | <30 ở through nhưng ≥30 ở **TOUCH** | Mở Gate 1 + cờ ĐỎ bắt buộc: "phải kiểm paper-live trước khi tin" — ghi memory, không gỡ |
| **RỚT** | <30 follower đậu kể cả ở touch | **ĐÓNG track lead-lag.** Báo cáo trung thực. Không thương lượng. |

## Báo cáo thêm (không gate)

- Bảng intensity (S2): f / IS / cost_eff theo z-bucket → input mapping Spec 2.
- Kịch bản hedge SPY (DNA rủi ro, user chốt sau): cột cost_eff + 0,3bp.
- Sensitivity: W∈{1,2,5}; h*∈{5,15,30}; κ∈{2.5,3,4}; H1-2024 vs H2-2024; theo giờ
  (đối chiếu slot_map.csv); fade direction.

## Tiered testing

1. **Khói**: leaders SPY+QQQ, 12 follower đầu bảng alphabet, 4 tuần Jan-2024:
   in số sự kiện, f theo biến thể, IS thô, tỷ lệ invalid — **trình user duyệt số
   trước khi chạy full**.
2. **Full 2024**: ước lượng < 10' (vectorized); nếu dự kiến > 25' → hỏi user trước.

## Caveats ghi trước (honest disclosure)

1. Proxy OHLC không thấy queue position → touch lạc quan; xử bằng bracket
   through/touch + luật "đạt sát nút" ở trên. Cơ sở văn liệu: giá trị vị trí
   queue có thể CÙNG CỠ spread với cổ phiếu tick-lớn (Moallemi–Yuan) — nên
   bracket là bắt buộc, không phải lựa chọn. Kể cả ĐẠT chắc: mô phỏng từ bar
   1-phút vẫn là xấp xỉ — paper-live là trọng tài cuối (Gate 3).
2. Mid proxy = close (giá khớp cuối) → nhiễu bid-ask bounce; đối xứng giữa các
   nhóm so sánh, drift đo trên cùng proxy.
3. 2024 = regime vol thấp-vừa; phí 2022 có thể cao hơn — nếu Gate 0 đạt, báo cáo
   kèm bảng half-spread theo năm 2022–2024 để định cỡ rủi ro regime.
4. Sự kiện 3σ là proxy; tín hiệu thật chốt ở Spec 2 — cost ít nhạy với định nghĩa
   event, có sensitivity κ.
5. Latency: thấy tín hiệu ở close t, lệnh hiệu lực từ bar t+1 — giả định hợp lý
   mid-freq (S3), ghi rõ.
6. Sample nhỏ: follower <200 attempts không được đếm vào gate (vẫn báo cáo tham khảo).

## Deliverables

- Code: `trading_1min/research/gate0_passive_exec.py` (script nghiên cứu; tích hợp
  engine là việc Spec 4).
- Kết quả: `trading_1min/results/gate0_passive/` — report_smoke.txt, report_full.txt,
  cost_by_follower.csv, intensity_table.csv, control_comparison.csv, sensitivity.csv.
- Seed cố định 42 cho mọi bốc thăm (control matching).
