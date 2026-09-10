# S2/S4 INTENSITY EXECUTION — spec PRE-COMMIT (chờ user duyệt)

Cùng kỷ luật Gate 0 / exec-sim: **khóa luật + số calibration TRƯỚC khi thấy kết quả.**
Đây là nâng cấp "Phase 4" của `v4_exec_simulator` (đã ghi ở
[v4_exec_simulator_spec.md:150](v4_exec_simulator_spec.md#L150)).

---

## Câu hỏi

Ý Sam (S2: intensity→aggressiveness; S4: thuận→passive, ngược→aggressive) **cắt được
bao nhiêu bp phí thực thi**, và **có làm đổi lựa chọn entry Z** (2.0 vs 2.5 vs 3.0) không?

## Bối cảnh — bằng chứng đã có (không giả định)

- **Probe live hôm nay** (Alpaca paper, 253 lệnh): **taker khớp ~100% khi gửi, ~1,5bp**;
  **passive khớp ~60% khi gửi, ăn ~1,9bp**; **~15–23% báo giá IEX rác** (không gửi nổi).
- Engine đã mã hóa **thuận/ngược** qua `exit_reason`: `zero_cross`=thuận, `hard_sl`=ngược,
  `open_at_eom`=theo lịch.
- Sổ lệnh 3 Z (matched: hard_sl=5.0, regime OFF, dyncost, EOM) đang sinh — script `zsweep.py`.

## Luật gán kiểu khớp (KHÓA) — S2 + S4

Mỗi **chân lệnh** (entry hoặc exit) được gán 1 style:

| Sự kiện | Style | Nguồn |
|---|---|---|
| **Vào lệnh**, \|Z_entry\| ∈ [Z, Z+1) | PASSIVE-rồi-taker | S2 (intensity thấp) |
| **Vào lệnh**, \|Z_entry\| ∈ [Z+1, Z+2) | PASSIVE-rồi-taker | S2 |
| **Vào lệnh**, \|Z_entry\| ≥ Z+2 | TAKER | S2 (intensity cao → chộp) |
| **Thoát `zero_cross`** (thuận) | PASSIVE-rồi-taker | S4 |
| **Thoát `hard_sl`** (ngược) | TAKER ngay | S4 |
| **Thoát `open_at_eom`** (lịch) | PASSIVE @15:30 → taker trước close | S4 + slot rẻ |

(PASSIVE-rồi-taker = thử đặt chờ trong cửa sổ W; không khớp → taker.)

## Mô hình fill + calibration (KHÓA — số từ probe, chọn BẢO THỦ)

Cho một chân gán "thử passive", với **half-spread** h (từ Week 5 L1 tại phiên đó):

| Kết cục | Xác suất | Phí chân đó |
|---|---|---|
| Passive khớp | (1−q)·p | **0** (được giá mình đặt, không trả h) |
| Passive miss → taker | (1−q)·(1−p) | **h + δ** (trả spread + trượt do chờ) |
| Báo giá rác → ép taker | q | **h** |

- **p = 0,55** (fill-rate passive; **bảo thủ dưới probe 60%** vì probe là paper).
- **q = 0,20** (tỷ lệ báo giá rác → ép taker; giữa 15–23% probe).
- **δ = 0,5bp** (phạt trượt khi chờ rồi phải taker — adverse selection).
- Chân gán **TAKER** = trả **h** (y như base). Base hiện tại = **TAKER cho MỌI chân**.
- S2/S4 chỉ đụng **thành phần spread**; impact/commission/borrow giữ nguyên.
- **Sensitivity bắt buộc**: p ∈ {0,45 / 0,55 / 0,65}, q ∈ {0,10 / 0,20}, δ ∈ {0 / 0,5 / 1,0}.

Kỳ vọng tiết kiệm/chân passive = h·(1−q)·p − (1−q)(1−p)·δ ≈ (h·0,44 − 0,18bp) ở base.

## Đo gì

Chạy đồng hồ đo phí **2 lần** trên CÙNG 3 sổ lệnh:
1. **BASE**: taker mọi chân (mô hình dyncost hiện tại).
2. **S2/S4**: gán style theo bảng trên + mô hình fill trên.

Xuất, cho mỗi Z ∈ {2.0, 2.5, 3.0}:
- `cost_bps_base` vs `cost_bps_s2s4` (round-trip) → **tiết kiệm bp**.
- Phân rã tiết kiệm theo nguồn: entry / zero_cross / EOM (kỳ vọng EOM là chính).
- **Net Sharpe mới** (gross − phí S2/S4) per Z → so ranking base vs S2/S4.

## Luật phán quyết (KHÓA trước khi thấy số)

- **S2/S4 "đáng giữ"** nếu: tiết kiệm **≥ 1,0bp round-trip** (median qua fold) ở p=0,55
  **VÀ** không làm net Sharpe của bất kỳ Z nào **tệ đi** (passive-miss không phản đòn).
- **Câu chốt**: *có làm đổi best-Z không* — báo rõ nếu ranking Z theo net Sharpe **lật**
  giữa base và S2/S4 (đặc biệt: Z=2.0 từ thua thành cạnh tranh).
- **RỚT** nếu tiết kiệm < 1,0bp hoặc chỉ dương ở p lạc quan (0,65) mà âm ở bảo thủ (0,45).

## Caveats (ghi trước)

1. **Paper**: p=0,55 vẫn có thể lạc quan; sensitivity p=0,45 là kịch bản thật xấu.
2. **EOM bắt buộc taker-fallback** trước close → tiết kiệm EOM bị chặn trên (không giữ qua đêm).
3. Đây là mô phỏng phí **từ bar/L1**, không phải paper-live — trọng tài cuối vẫn là probe thật.
4. Half-spread theo giờ: dùng slot_map (15:30 rẻ ~5×) cho nhánh EOM.

## Deliverables

- Code: mở rộng `v4_exec_simulator.py` thêm variant `s2s4` (không sửa base).
- Kết quả: `trading_1min/results/v4_exec_sim/s2s4_cost_by_z.csv`,
  `s2s4_sensitivity.csv`, `s2s4_net_sharpe_by_z.csv`.
- Seed cố định cho mọi bốc thăm passive-fill (tái lập được).

## TRẠNG THÁI: ✅ KHÓA (user duyệt 2026-07-24) — build sau khi Z-sweep ra sổ lệnh
