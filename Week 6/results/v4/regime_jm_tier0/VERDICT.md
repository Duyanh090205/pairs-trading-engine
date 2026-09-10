# VERDICT — Tier-0: Jump Model đấu composite stress_z

**Kết luận: JM RỚT Tier-0 → ĐÓNG track JM-detector** (theo đúng luật pre-commit khóa
trong `Week 6/engine_rebuild/REGIME_jm_tier0_spec.md` TRƯỚC khi chạy số).
Chạy 2026-07-24. λ đóng băng = 100 (chọn trên 2022–24, tie-break λ lớn).

## Chấm 3 luật (λ=100)

| Luật | Yêu cầu | Kết quả | Đậu? |
|---|---|---|---|
| (a) | bear ≥3/4 tháng Dec25–Mar26 (khúc composite cứu OOS đúng) | **0/4** — JM bull suốt | ❌ **RỚT** |
| (b) | bull cả Jun+Jul 2026 (khúc composite kẹt) | bull cả 2 | ✅ |
| (c) | tháng-lãi bị báo bear ≤ composite (35 tháng 2023-01→2025-11) | JM 3 ≤ composite 5 (trên 22 tháng lãi) | ✅ |

**Sensitivity (bắt buộc theo spec, chỉ báo cáo):** λ=31.6 → RỚT (a) 0/4; λ=316 → RỚT
cả (a) 0/4 lẫn (c) 8>5. **Verdict không phụ thuộc λ** — kể cả λ có fit 2-state lành
mạnh (31.6) vẫn rớt y hệt.

## Số liệu nền (scorecard 43 tháng, `scorecard_43mo.csv`)

| Kịch bản | Fold 1–39 (return, dyncost ~20bp) | Replay 2026-04→07 (USD, probe ~6bp) |
|---|---|---|
| Không filter | +0.84% | +$11,304 |
| Composite | **+2.32%** | −$1,189 |
| JM (λ=100) | **−0.09%** | **+$11,304** |

- Composite halt 15/43 tháng; JM halt 4/43 (2023-01, 2025-05/06/07); **overlap = 0 tháng**
  — hai detector nhìn hai loại "stress" hoàn toàn khác nhau. Agree 24/43 (56%).
- Trên 39 fold lịch sử, JM còn **tệ hơn không-filter** (−0.09% vs +0.84%): nó bỏ đúng
  mấy tháng có lãi giữa-2025 và trade xuyên các tháng sập Dec25–Mar26.
- Trên khúc replay 2026, JM thắng tuyệt đối (+$11.3k vs −$1.2k) — đúng cái composite kẹt.

## Vì sao rớt (lý do cấu trúc, không phải tuning)

Đúng cảnh báo pre-commit #4 của spec: **stress Q1-2026 là corr-crash + dispersion spike
với vol index THẤP** (đã biết từ hồ sơ B3: filter vol-only cũng trượt cả 3 fold 2026).
Features JM theo paper (downside-dev + Sortino) tính từ **một chuỗi index-return duy
nhất** → JM về bản chất là máy dò "index đang sụt" — mà index không hề sụt trong khúc
đó. Cái giết pairs book là đứt gãy cấu trúc CHÉO giữa các mã, chỉ hiện trên corr/dispersion
cross-sectional (thứ composite có, JM không). JM đậu (b) gần như miễn phí (bull 39/43
tháng) — không đủ bù (a).

Ghi chú phụ: bear 2023-01 là artifact warm-up (fit window chỉ có 2022, fit 1-state);
bear 2025-05→07 là tín hiệu index-drawdown thật nhưng vô ích cho pairs (2/3 tháng đó lãi).

## Caveat giữ nguyên từ spec

1. Hindsight chọn detector sau khi biết composite sai ở đâu — verdict RỚT nên rủi ro
   này không thành vấn đề (không có model mới được nhận).
2. λ leakage một phần 2023–24 (không đổi kết cục — rớt ở khúc 2025–26).
3. Mẫu nhỏ: khúc quyết định (a)+(b) chỉ 6 tháng; cờ giữ nguyên.
4. Hai khúc P&L khác cost-basis (20bp vs 6bp) — không cộng xuyên khúc, chỉ dùng dấu.
5. Polygon thực tế hết 2026-03-19 (spec giả định 31/3) → nối Alpaca từ 2026-03-20,
   index-return level, corr overlap 0.9927/median 4.84bp.

## Hệ quả (theo kết cục pre-commit)

- **ĐÓNG track JM-detector.** Không thử thêm biến thể feature index-level.
- **Giữ composite** với 3 tật đã khai báo (nhị phân / hạt tháng / nhả chậm).
- Hướng đi tiếp hợp lý nhất (đúng nhánh "RỚT" của spec): **sửa TẦNG QUYẾT ĐỊNH** —
  tháng→ngày / dampener 3 nấc đã có sẵn trong `regime_detector.size_multiplier_for_fold`
  (built-not-wired) — thay vì thay detector. Đây là việc riêng, đụng live invariants,
  cần spec pre-commit mới.
- Nếu mai sau muốn thử JM lần nữa: phải là JM trên **features cross-sectional**
  (corr/dispersion) — tức một thí nghiệm MỚI với spec mới, và phải khai báo rủi ro
  hindsight-thêm-một-lần.
- Trọng tài cuối vẫn là các tháng live paper sắp tới.

Files: `index_returns.csv`, `index_validation.txt`, `lambda_grid.csv`,
`scorecard_43mo.csv`, `sensitivity.json`, `verdict_raw.txt`,
script `Week 6/scripts/research/regime_jm/tier0_jm.py`.
