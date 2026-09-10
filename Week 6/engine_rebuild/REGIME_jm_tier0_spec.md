# TRACK REGIME — Tier-0: Jump Model đấu composite stress_z — SPEC PRE-COMMIT

**Trạng thái: ĐÃ DUYỆT + ĐÃ CHẠY 2026-07-24 — verdict: JM RỚT (luật a: 0/4), track ĐÓNG.**
Kết quả đầy đủ: `Week 6/results/v4/regime_jm_tier0/VERDICT.md`. Luật dưới đây giữ nguyên
như lúc khóa trước khi chạy.
Luật đậu/rớt khóa TRƯỚC khi nhìn bất kỳ kết quả JM nào (kiểu Gate 0 của track lead-lag).

## 0. Câu hỏi & phạm vi

Composite stress_z (vol − corr + dispersion, tháng nào stress > q67 trailing thì nghỉ
nguyên tháng) là tầng cứu OOS (fold 31–39: −2.07% → +0.49%) nhưng có 3 tật đã khai báo:
**nhị phân** (0/100%), **hạt tháng** (bỏ nguyên tháng), **nhả chậm** (replay 2026 halt
3/4 tháng, né $0.6k lỗ nhưng bỏ lỡ ~$13.3k lãi Jun+Jul).

Tier-0 hỏi đúng MỘT câu: **Statistical Jump Model (Shu–Yu–Mulvey, arXiv 2402.05272)
làm DETECTOR có phân loại tháng tốt hơn composite không?** — chấm trên lịch sử 43 tháng,
KHÔNG đụng engine, KHÔNG đụng live, KHÔNG đổi tầng quyết định (tháng→ngày là việc riêng,
chỉ bàn nếu Tier-0 đậu).

## 1. LUẬT ĐẬU/RỚT (khóa)

JM **ĐẬU** Tier-0 khi đủ CẢ 3:

| # | Luật | Vận hành hóa |
|---|---|---|
| (a) | Bear tại t* của **≥3/4 tháng Dec25–Mar26** (khúc composite cứu đúng) | Trạng thái JM tại t* của các tháng {2025-12, 2026-01, 2026-02, 2026-03} = bear ở ≥3 tháng |
| (b) | Bull tại t* của **CẢ Jun-2026 VÀ Jul-2026** (khúc composite kẹt) | Trạng thái JM tại t* (2026-05-29 và 2026-06-30) = bull ở cả 2 |
| (c) | 2023-01→2025-11 (35 tháng): **số tháng-có-lãi bị báo bear ≤ composite** (không nhát hơn) | Tháng-có-lãi = `total_return > 0` trong foldmetrics_z30 (run regime-OFF). Đếm JM-bear trong nhóm đó ≤ đếm composite-halt trong nhóm đó |

**RỚT bất kỳ luật nào** → ghi kết quả đầy đủ, **ĐÓNG track JM**, giữ composite (tật đã
khai báo), chuyển hướng cân nhắc sửa TẦNG QUYẾT ĐỊNH thay vì detector.

Luật vận hành phụ (khóa luôn):
- JM phải cho ra trạng thái ở **đủ 43/43 tháng** (2023-01→2026-07). Tháng nào không tính
  được (NaN, không đủ data) → coi như RỚT về mặt vận hành, không du di.
- t* = phiên giao dịch cuối cùng **trước** ngày 1 của tháng chấm — trùng định nghĩa
  composite (`halt_for_fold` trong `engine_daily/regime_detector.py`).
- Không có luật nào dựa trên tổng $ — chỉ dựa trạng thái + dấu P&L tháng, để miễn nhiễm
  lệch cost-basis giữa 2 nguồn P&L (mục 4).

## 2. Data — index EW daily log-return 528 mã

- **Công thức**: return ngày của index = trung bình cross-sectional (bỏ NaN) của
  log-return từng mã — **khớp đúng** `eq_returns = R.mean(axis=1)` trong
  `regime_detector.build_features` để so sánh táo-với-táo.
- **Nguồn ghép 2 khúc, nối ở mức INDEX-RETURN (không nối giá từng mã)**:
  - 2022-01-03 → 2026-03-31: Polygon `Week 4/data/validated/daily_phase3/` (528 parquet).
    ⚠️ **RAW chưa adjust split** — khai báo: 1 mã split 5:1 tạo log-return giả ~−1.61,
    pha loãng 1/528 → nhiễu ~−0.3% trên index tại ngày split. Chấp nhận có kiểm soát.
  - 2026-04-01 → 2026-07-24: Alpaca replay cache (split-adjusted, sẵn 529 file kéo
    2026-07-24, window 2024-10→nay; nếu mất thì re-pull 12s bằng
    `scripts/research/replay/pull_replay_cache.py` sửa OUT sang scratchpad phiên hiện tại).
    Ngày đầu khúc Alpaca dùng close Alpaca cho cả 2 vế phép trừ — không trộn giá 2 vendor.
- **Kiểm định bắt buộc trước khi fit** (fail → dừng, báo user):
  1. Overlap 2024-10→2026-03: corr(index-ret Polygon, index-ret Alpaca) **> 0.99**;
     báo cáo median |lệch| (kỳ vọng ~8.5bp theo audit cũ).
  2. Quét outlier: liệt kê mọi ngày |index-ret| > 5%; nếu có → truy mã gây ra, khai báo.
  3. Ngày nào < 400/528 mã có return → liệt kê (lễ/thiếu data).

## 3. Jump Model — fit & inference

- **Package**: `jumpmodels` (của tác giả paper; cần `pip install jumpmodels` — chưa cài).
- **Model**: JM 2-state, rời rạc (`cont=False`), jump penalty λ.
- **Features (khóa theo paper, tính từ chuỗi index-return duy nhất)**:
  1. Downside deviation EWM halflife 10
  2. Sortino EWM halflife 20 (EWM-mean return / EWM downside-dev, cùng hl)
  3. Sortino EWM halflife 60
- **Chuẩn hóa causal**: clip 3σ + standardize, scaler fit CHỈ trên data ≤ t* của lần fit đó.
- **Gán nhãn trạng thái**: sort theo cumulative return trong cửa sổ fit — trạng thái
  cumret cao = **bull**, thấp = **bear** (convention `sort_by="cumret"` của package).
- **Inference ONLINE, walk-forward thật**: với TỪNG tháng M trong 43 tháng:
  refit JM trên expanding window 2022-01→t*(M) với λ đóng băng; trạng thái của M =
  trạng thái ngày t* trong fit đó. Không có điểm nào nhìn thấy data sau t*.
  (43 lần refit × vài giây = vô hại.)

### λ: grid + tiêu chí chọn + đóng băng

- **Grid**: λ ∈ {0, 0.1, 0.316, 1, 3.16, 10, 31.6, 100, 316, 1000} (nửa-decade log,
  0 = k-means thuần làm sanity floor).
- **Chọn trên 2022–2024 rồi ĐÓNG BĂNG** (đúng đề bài): fit 2022-01→2023-12,
  inference online 2024-01→2024-12 (validation).
- **Tiêu chí**: Sharpe của overlay index-timing trên validation — bull thì long index,
  bear thì cash, quyết định tại t áp dụng t+1. Đây là tiêu chí của chính paper, KHÔNG
  đụng P&L pairs → không tự tay tune detector vào đáp án cần chấm.
- **Guard chống suy biến** (loại λ trước khi so Sharpe): trên 2022–2024, tỷ trọng ngày
  bear phải trong [5%, 60%] và duration trung bình mỗi regime ≥ 5 ngày.
- **Tie-break**: Sharpe chênh < 0.05 → chọn λ LỚN hơn (bền hơn, ít nhảy).
- **Sensitivity (chỉ báo cáo, không đổi verdict)**: chạy lại verdict ở λ một nấc trên +
  một nấc dưới λ chọn; ghi rõ verdict có lật hay không.

## 4. Nguồn chấm điểm (43 tháng, 2023-01→2026-07)

| Khúc | Quyết định composite | P&L tháng ("would-have" khi halt) | Cost-basis |
|---|---|---|---|
| Fold 1–39 (2023-01→2026-03) | `results/v4/z30_composite/fold_metrics.csv` cột `regime_halt` (trống = trade) | `results/v4/zsweep_sl50_regimeoff/foldmetrics_z30.csv` cột `total_return` (regime OFF → có số cả tháng halt) | dyncost Week-5 ~20bp/vòng |
| 2026-04→07 (replay) | `results/v4/replay_2026/replay_folds.csv` cột `halt` | Σ `net_base` theo tháng từ `replay_ledger.csv` | probe ~6bp/vòng |

⚠️ **Hai khúc KHÁC cost-basis** — vì vậy luật (a)(b)(c) chỉ dùng **trạng thái + dấu**,
không bao giờ cộng $ xuyên khúc. Bảng phụ lục có thể trình tổng $ TÁCH RIÊNG từng khúc.
⚠️ 2026-07 là tháng partial (tới 24/7) — cờ sẵn trong replay, khai báo lại.

Số đã biết trước (ghi để minh bạch, không phải kết quả JM): composite halt 12/39 fold
(2023-06; 2024-02→05, 07, 08, 10; 2025-12→2026-03) + replay halt 2026-05/06/07.
Số "composite-halt-trúng-tháng-lãi" của luật (c) sẽ tính LÚC CHẤM, không tính trước.

**Bảng scorecard** (43 dòng): `month, jm_state_t_star, composite_halt, pnl_sign,
pnl_value, pnl_source, agree`. Metrics phụ (báo cáo thôi, không vào luật): agreement
rate, số tháng halt mỗi bên, tổng return per-khúc theo 3 kịch bản (no-filter /
composite / JM).

## 5. Cảnh báo pre-commit (giữ nguyên khi viết kết quả)

1. **Hindsight chọn detector**: ta đi tìm detector SAU khi biết composite sai ở đâu —
   cùng loại rủi ro với chính composite (chốt 2026-05 sau khi thấy Q1-2026). Giảm nhẹ:
   chấm cả 43 tháng chứ không chỉ 6 tháng có đáp án; λ chọn bằng tiêu chí index-timing
   không đụng P&L pairs; **trọng tài cuối = các tháng live tới**.
2. **λ leakage một phần**: λ chọn trên 2022–2024 nhưng luật (c) chấm cả 2023–2024 →
   các tháng 2023–24 trong scorecard KHÔNG sạch tuyệt đối với λ. Khúc sạch thật =
   2025-01→2026-07. Khai báo trong verdict.
3. **Mẫu nhỏ**: 43 tháng, trong đó các khúc quyết định (a)+(b) chỉ 6 tháng; paper gốc
   fit 33 năm. Cờ mẫu-nhỏ GIỮ NGUYÊN dù fit trên ~1.130 ngày.
4. **JM thấy ÍT thông tin hơn composite**: features JM chỉ từ index-return (1 chuỗi);
   composite có thêm corr + dispersion cross-sectional. Nếu JM rớt (a) vì stress 2026-Q1
   là corr-crash không hiện trên index vol → ghi nhận là lý do cấu trúc, không cứu bằng
   cách thêm feature (đó là Tier-1, nếu có).
5. **Đậu detector ≠ hết tật hạt-tháng**: JM thay detector không tự sửa "bỏ nguyên tháng".
   Đổi tầng quyết định = việc riêng, đụng live invariants.
6. **Đã bác/đóng — không redo trong track này**: carry-forward, top-K, Z=2.0, Z>3.5,
   Kalman-β, HMM monthly, S2/S4.

## 6. Kế hoạch chạy (tiered, tổng <15')

| Tier | Việc | Thời gian ước |
|---|---|---|
| A | Build index 2 khúc + 3 kiểm định mục 2 | ~1–2' |
| B | λ-grid 10 điểm trên 2022–24 (fit + validate 2024) + guard + chọn λ | ~3–5' |
| C | Walk-forward 43 refit → scorecard → chấm (a)(b)(c) → verdict + sensitivity | ~3–5' |

- Script: `Week 6/scripts/research/regime_jm/tier0_jm.py` (+ `build_index.py` nếu tách).
  Có `if __name__ == "__main__"` (quy tắc Windows). Không multiprocessing.
- Kết quả: `Week 6/results/v4/regime_jm_tier0/` — `index_returns.csv`,
  `index_validation.txt`, `lambda_grid.csv`, `scorecard_43mo.csv`, `VERDICT.md`.
- Cần cài: `pip install jumpmodels` (một lần).
- Fail bất kỳ kiểm định data nào ở Tier A → DỪNG, hỏi user, không fit tiếp.

## 7. Kết cục

- **ĐẬU cả 3** → mở thảo luận Tier-1 (detector JM + câu hỏi tầng quyết định) — vẫn chưa
  đụng engine/live cho tới khi có spec riêng.
- **RỚT** → đóng track JM với số liệu đầy đủ trong VERDICT.md, giữ composite, cân nhắc
  track "sửa tầng quyết định" (tháng→ngày / dampener) làm hướng thay thế.
- Cả hai trường hợp: cập nhật auto-memory.
