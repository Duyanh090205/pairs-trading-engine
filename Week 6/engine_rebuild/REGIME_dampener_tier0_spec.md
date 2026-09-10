# TRACK REGIME — Tier-0: Dampener 3 nấc đấu composite nhị phân — SPEC PRE-COMMIT

**Trạng thái: ĐÃ DUYỆT + ĐÃ CHẠY 2026-07-24 — verdict: RỚT luật (b) thiếu $31
(+$3,369 vs sàn +$3,400); (a)(c) đậu. Nhánh ĐÓNG theo luật.**
Kết quả: `Week 6/results/v4/regime_dampener_tier0/VERDICT.md`. Luật giữ nguyên như lúc khóa.
Nối tiếp nhánh "RỚT" của JM Tier-0 (`REGIME_jm_tier0_spec.md` — JM detector đóng):
giữ nguyên DETECTOR composite stress_z, sửa TẦNG QUYẾT ĐỊNH.

## 0. Câu hỏi & xuất xứ (quan trọng cho tính pre-commit)

Composite nhị phân: stress_z(t*) > q67 trailing → bỏ NGUYÊN tháng (0/100%).
Dampener 3 nấc: **< q67 → size 100% · [q67, q85) → size 50% · ≥ q85 → halt hẳn (0%)**.

Xuất xứ: config này **đã khóa trong code từ 2026-05-25** (`engine_daily/regime_detector.py::
size_multiplier_for_fold`, theo research HMM Regime Detection §5.2) — TRƯỚC khi replay
2026 (chạy 2026-07-24) phát hiện composite bỏ lỡ ~$13.3k Jun+Jul. Tức tham số dampener
KHÔNG được thiết kế sau khi thấy lỗi — chỉ CHƯA TỪNG được backtest. Tier-0 này là lần
backtest đầu tiên. KHÔNG tune q67/q85/0.5 — dùng y nguyên số đã khóa; nếu rớt thì rớt.

Phạm vi: chỉ sửa tật **nhị phân**. Hai tật còn lại (hạt tháng, nhả chậm) thuộc thay đổi
granularity tháng→ngày — việc RIÊNG, không thuộc Tier-0 này.

## 1. Phương pháp (rẻ, không chạy lại engine)

Vì dưới q67 dampener = composite (mult 1.0), toàn bộ khác biệt nằm ở các tháng composite
halt: tháng nào [q67, q85) được trade lại ở HALF size, tháng nào ≥ q85 vẫn nghỉ.

P&L dampener tháng M = mult(M) × P&L would-have full-size của M:
- Fold 1–39: would-have = `zsweep_sl50_regimeoff/foldmetrics_z30.csv` (regime OFF).
- Replay 2026-04→07: would-have = Σ `net_base` theo tháng từ `replay_2026/replay_ledger.csv`
  (replay trade cả tháng halt nên ledger là full-size would-have).
- Nguồn giống hệt scorecard JM Tier-0 (`regime_jm_tier0/scorecard_43mo.csv`) — tái dùng.

⚠️ **Xấp xỉ tuyến tính khai báo**: mult 0.5 ⇒ P&L × 0.5 đúng khi cost theo bps và sizing
tuyến tính; bỏ qua hiệu ứng làm tròn lô/β-cap/min-notional. Nếu ĐẬU → Tier-1 chạy lại
engine thật với sizing 0.5 trên các tháng bị ảnh hưởng để kiểm chứng xấp xỉ (~20', hỏi
trước khi chạy).

mult(M) lấy từ **chính module production** `size_multiplier_for_fold(feats, trade_start)`:
- Fold 1–39: feats build từ cache Polygon daily_phase3 (528 mã, RAW — giống backtest gốc).
- Replay 2026-04→07: feats build từ Alpaca replay cache (giống replay gốc).
- Mọi phép tính trailing/causal như production (đã audit 2026-05-25).

## 2. GATE V0 — kiểm định tái lập (precondition, fail → DỪNG hỏi user)

Trước khi nhìn bất kỳ số dampener nào:
1. Halt boolean tái tính (`halt_for_fold`) phải khớp **đúng 39/39 fold** với
   `z30_composite/fold_metrics.csv` (12 halt + 27 trade).
2. stress_z tái tính tại t* phải khớp giá trị đã ghi: 12 fold halt + 4 tháng replay,
   sai số |Δ| ≤ 0.02 (biết trước: code dùng `>` trong halt_for_fold nhưng `>=` trong
   size_multiplier_for_fold ở đúng biên q67 — đo lường bằng 0, ghi nhận nếu đụng).

Ý nghĩa: chứng minh pipeline feature tái lập đúng cái composite đã dùng, thì cột mult
mới đáng tin.

## 3. LUẬT ĐẬU/RỚT (khóa TRƯỚC khi tính mult — số neo lấy từ scorecard JM đã có)

Dampener **ĐẬU** Tier-0 khi đủ CẢ 3:

| # | Luật | Ngưỡng khóa | Neo đã biết (từ scorecard cũ, không phải số mới) |
|---|---|---|---|
| (a) **Giữ phòng thủ khủng hoảng** | Tổng return Dec25–Mar26 (4 tháng) của dampener ≥ **−0.75%** | composite = 0.00% (halt cả 4); no-filter = −2.56% → giữ ≥ ~70% mức bảo vệ |
| (b) **Vợt lại upside 2026** | Tổng USD replay 2026-04→07 của dampener ≥ **+$3,400** | = 30% của no-filter +$11,304; composite = −$1,189 |
| (c) **Không phá cửa sổ dài** | Tổng return 39 fold của dampener ≥ **+1.80%** | composite = +2.32% → chấp nhận trả ≤ 0.5pp "bảo hiểm"; no-filter = +0.84% |

RỚT bất kỳ → **giữ composite nhị phân**, đóng nhánh dampener với số liệu; lựa chọn còn
lại của tầng quyết định là granularity tháng→ngày (spec riêng nếu muốn).

Các ngưỡng −0.75% / $3,400 / 1.80% là lựa chọn chủ quan — khai báo thẳng — nhưng KHÓA
trước khi thấy bất kỳ cột mult nào. Không xê dịch sau khi thấy số.

Lưu ý minh bạch: (a)+(c) cùng cost-basis dyncost ~20bp; (b) cost-basis probe ~6bp.
Không cộng $ xuyên khúc. Luật đánh trên từng khúc riêng.

## 4. Báo cáo phụ (không có quyền quyết định)

- Bảng 43 tháng: month, stress_z(t*), q67, q85, mult, would-have P&L, P&L dampener.
- Trong 15 tháng composite-halt: bao nhiêu tháng rơi vào nấc 0.5 vs nấc 0.
- 3 kịch bản (no-filter / composite / dampener) trên từng khúc + fold 31–39 OOS.
- Sensitivity CHỈ BÁO CÁO (không đổi verdict, không tune): verdict nếu nấc giữa là
  0.25 và 0.75 thay vì 0.5 (đo độ nhạy với tham số đã khóa duy nhất có thể tranh cãi).

## 5. Cờ pre-commit giữ nguyên

1. Mẫu nhỏ: khúc quyết định (a) 4 tháng, (b) 4 tháng (Jul partial tới 24/7). Cờ giữ nguyên.
2. Xấp xỉ tuyến tính (mục 1) — Tier-1 kiểm chứng bằng engine thật nếu đậu.
3. RAW-split Polygon trong features cross-sectional: giống hệt backtest gốc (cùng data,
   cùng code) → lỗi nếu có thì đã nằm trong cả composite lẫn dampener, công bằng khi so.
4. Trọng tài cuối = các tháng live paper tới (dampener phải cắm qua live invariants
   + cross-path test trước khi lên live — ngoài phạm vi Tier-0).
5. Đã bác/đóng — không redo: JM index-features, carry-forward, top-K, Z=2.0, Z>3.5,
   Kalman-β, HMM monthly, B3 vol-only.

## 6. Kế hoạch chạy (tổng <10')

| Bước | Việc | Thời gian |
|---|---|---|
| V0 | Build feats 2 cache (Polygon + Alpaca) bằng regime_detector, tái lập 39 halt + 16 stress_z | ~3–5' |
| S | Tính mult 43 tháng, ghép scorecard, chấm (a)(b)(c), sensitivity 0.25/0.75 | ~1' |

- Script: `Week 6/scripts/research/regime_dampener/tier0_dampener.py`
  (`if __name__ == "__main__"` — quy tắc Windows; không multiprocessing).
- Kết quả: `Week 6/results/v4/regime_dampener_tier0/` — `replication_check.txt`,
  `scorecard_dampener_43mo.csv`, `VERDICT.md`.

## 7. Kết cục

- **ĐẬU cả 3** → Tier-1: re-run engine thật với sizing 0.5 trên các tháng ảnh hưởng
  (kiểm chứng tuyến tính, ~20', hỏi trước) → nếu giữ verdict → spec cắm live
  (đụng [[week6-live-invariants]], cross-path test bắt buộc).
- **RỚT** → giữ composite nhị phân; nhánh tầng-quyết-định còn lại = granularity
  tháng→ngày (chỉ mở nếu user muốn).
- Cả hai: cập nhật auto-memory.
