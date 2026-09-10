# BƯỚC 3 — SIGNAL (vào/ra/dừng lỗ) — **CHỐT 2026-07-24**

Nối tiếp STEP1 (universe) + STEP2 (walk-forward). Mọi số dưới đây từ **Z-sweep matched
39-fold** chạy 2026-07-24 (discovery-once-3-Z, hard_sl=5.0, regime OFF, dyncost Week-5,
EOM; script `Week 6/scripts/research/replay/zsweep.py`, kết quả
`Week 6/results/v4/zsweep_sl50_regimeoff/` gồm cả **trade ledger per-Z**).

## Quyết định

| Tham số | Chốt | Căn cứ |
|---|---|---|
| Entry | **\|Z\| ≥ 3.0** (flat-only) | bảng dưới |
| Exit | Z về 0 (zero-cross) | giữ nguyên |
| Hard SL | **\|Z\| ≥ 5.0** | khớp live; sweep chạy ở 5.0. ⚠️ backtest default = 4.0 ≠ live 5.0 — luôn chỉ định rõ |
| Time-stop | **KHÔNG thêm** | EOM flatten đã đóng vai trò (STEP2) |
| Regime filter | **CẦN nhưng có 3 tật** — track riêng (JM Tier-0) | mục dưới |

## Bằng chứng Z (matched 39-fold)

| Z | sum_ret | monthlySh | trades | gross$ | phí$ | phí/vòng | train→OOS |
|---|---|---|---|---|---|---|---|
| 2.0 | −6.27% | −0.44 | 2336 | **−5.464** | 57.228 | 19,8bp | +2.7% → **−9.0%** |
| 2.5 | +1.30% | +0.13 | 1360 | +45.454 | 32.450 | 20,2bp | +6.2% → **−4.9%** |
| **3.0** | +0.84% | +0.14 | 686 | +24.126 | 15.694 | 20,4bp | +2.9% → **−2.1%** |

- **Z=2.0 BÁC TUYỆT ĐỐI: gross ÂM trước phí** → không cải tiến execution nào cứu được.
  (Subset 16-fold từng cho +6% → bài học: subset chọn tay đánh lừa, phải full 39.)
- **2.5 vs 3.0**: 2.5 thắng in-sample nhưng sụp OOS mạnh hơn (−4.9% vs −2.1%) → 3.0
  ít overfit hơn. KHÔNG phải vì "Sharpe full cao hơn".
- ⚠️ **Cả 3 Z đều ÂM OOS (fold 31-39) khi regime OFF** → edge sống nhờ regime layer.

## Regime filter — cần, nhưng 3 tật (bằng chứng 2 mặt)

- ✅ Cứu OOS: fold 31-39 OFF −2.07% → ON +0.49% (halt đúng Dec25–Mar26).
- ❌ Replay 2026-04..07 (thuần Alpaca, `results/v4/replay_2026/`): halt 3/4 tháng gần
  nhất, **né $0.6k lỗ nhưng bỏ lỡ ~$13.3k lãi** (Jun+Jul 2026).
- 3 tật: **nhị phân** (0/100%), **hạt tháng** (bỏ nguyên tháng), **nhả chậm** sau stress.
- + caveat thiết kế-có-hindsight (composite chọn 2026-05 sau khi thấy Q1-2026 sập kiểu corr).
- → Track kế: **Jump Model Tier-0** (prompt bàn giao riêng). Tầng quyết định (tháng→ngày)
  là việc tách biệt với tầng detector.

## ⚠️ Lệch mô hình phí — audit riêng (ưu tiên cao)

Week-5 dynamic tính ~**20bp/vòng** (ăn 65–71% gross). **Probe live 2026-07-24** (253 lệnh
thật Alpaca paper): taker ~**1,5bp/chân** → ~6bp/vòng; passive khớp 60% ăn 1,9bp.
Nếu phí thật gần probe → net thật TỐT hơn backtest nhiều và **ranking 2.5-vs-3.0 có thể
đổi** (2.5 net ước +$36k vs 3.0 +$19.5k ở 6bp). Chưa kết luận — cần audit đối chiếu
(Week-5 L1 spread vs probe vs realized_cost_bps live).

## S2/S4 (intensity execution của Sam) — ĐO XONG, ĐÓNG

Spec khóa `trading_1min/research/s2s4_intensity_exec_spec.md`. Đo trên replay 2026:
tiết kiệm **$178/4 tháng** (~62 lệnh) — thật nhưng quá nhỏ để ưu tiên. Đóng hồ sơ với
số liệu; mở lại chỉ khi trade count tăng ~10×.

## Cờ mẫu nhỏ

39 fold (~37 trade), OOS 9 fold, replay 4 fold. Không tuyên bố significant.
Trọng tài cuối = live paper các tháng tới.

## TRẠNG THÁI: ✅ CHỐT (Z=3.0, SL=5.0, no time-stop) — regime track mở riêng
