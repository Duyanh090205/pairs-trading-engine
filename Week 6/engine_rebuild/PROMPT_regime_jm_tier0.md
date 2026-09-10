# PROMPT SESSION MỚI — TRACK REGIME: Jump Model Tier-0

(Dán nguyên khối dưới vào session mới. Auto-memory + CLAUDE.md tự nạp.)

---

TRACK REGIME — Tier-0: Jump Model đấu composite stress_z

── BỐI CẢNH ──
Đọc auto-memory (nhất là week6_zsweep_step3, week6_shadow_replay_2026,
week6_rejected_approaches) + spec Week 6/engine_rebuild/STEP3_signal.md.
Bước 1-3 rebuild ĐÃ CHỐT (universe 528 / walk-forward 12m+EOM / Z=3.0+SL5.0).
Phát hiện then chốt: cả 3 Z đều ÂM OOS khi regime OFF → edge sống nhờ regime layer,
NHƯNG composite filter có 3 tật: NHỊ PHÂN (0/100%), HẠT THÁNG (bỏ nguyên tháng),
NHẢ CHẬM (halt lết sang tháng hồi). Bằng chứng 2 mặt:
- Đúng: halt Dec25–Mar26 cứu OOS (−2.07% → +0.49%).
- Sai: replay 2026 halt 3/4 tháng, né $0.6k lỗ nhưng BỎ LỠ ~$13.3k lãi (Jun+Jul 2026).
User muốn thử THAY detector bằng Statistical Jump Model (Shu-Yu-Mulvey, Princeton,
arXiv 2402.05272; công thức k-means + λ-penalty đổi trạng thái; package `jumpmodels`
của tác giả, có predict_online). JM từng bị HOÃN vì "39 obs tháng quá ít" — phản đối
đó giảm khi fit trên DATA NGÀY (~1000+ ngày), nhưng cờ mẫu-nhỏ vs paper 33 năm GIỮ NGUYÊN.

── NHIỆM VỤ TIER-0 (rẻ, chưa đụng engine) ──
1. Spec pre-commit TRƯỚC khi thấy số (kiểu Gate 0): luật đậu/rớt bên dưới, khóa rồi mới chạy.
2. Build index EW daily log-return của 528 mã. Data: Polygon daily_phase3 (2022→2026-03,
   ⚠️ RAW chưa adjust split — với INDEX EW 528 mã, lỗi split 1 mã pha loãng 1/528, chấp
   nhận được nhưng PHẢI khai báo; kiểm tra outlier return >5% của index) + nối Alpaca
   re-pull cho 2026-04→nay (script Week 6/scripts/research/replay/pull_replay_cache.py,
   12 giây; nối ở mức INDEX-RETURN chứ không nối giá từng mã).
3. Fit JM 2-state trên 3 feature paper (downside-dev EWM hl=10; Sortino hl=20; Sortino
   hl=60), inference ONLINE (không nhìn tương lai), λ chọn trên 2022–2024 rồi ĐÓNG BĂNG.
4. Chấm điểm trên TOÀN BỘ 43 tháng (2023-01→2026-07): trạng thái JM tại t* (phiên cuối
   trước tháng) vs quyết định composite vs P&L tháng đó (foldmetrics
   Week 6/results/v4/zsweep_sl50_regimeoff/foldmetrics_z30.csv + replay_2026/replay_folds.csv;
   tháng composite-halt lấy P&L "would-have" từ run regime-OFF).

── LUẬT ĐẬU/RỚT (khóa trước khi chạy) ──
JM ĐẬU Tier-0 nếu ĐỦ 3:
(a) bear tại t* của ≥3/4 tháng Dec25–Mar26 (khúc composite cứu đúng);
(b) bull tại t* của Jun-2026 VÀ Jul-2026 (khúc composite kẹt);
(c) trên 2023-01→2025-11: số tháng-có-lãi bị JM báo bear ≤ composite (không nhát hơn).
RỚT bất kỳ → ghi kết quả, ĐÓNG track JM, giữ composite (tật đã khai báo), cân nhắc
sửa TẦNG QUYẾT ĐỊNH thay vì detector.

── CẢNH BÁO PRE-COMMIT ──
- Ta chọn detector SAU khi biết composite sai ở đâu → cùng loại rủi ro hindsight như
  composite (chốt 2026-05 sau khi thấy Q1-2026). Vì vậy: chấm cả 43 tháng, không chỉ
  6 tháng đã biết đáp án; λ đóng băng từ 2022–2024; trọng tài cuối = các tháng live tới.
- JM thay DETECTOR không tự sửa tật "bỏ nguyên tháng" (tầng quyết định). Đổi tầng quyết
  định tháng→ngày = việc RIÊNG, đụng live invariants, chỉ bàn nếu Tier-0 đậu.
- Đã bác/đóng — ĐỪNG redo: carry-forward, top-K, Z=2.0 (gross âm), Z>3.5, Kalman-β,
  HMM monthly, S2/S4 (đo xong $178/4mo — quá nhỏ).

── VIỆC TỒN KHÁC (không thuộc Tier-0, nhắc để khỏi quên) ──
1. ⚠️ LIVE OPS: daily_cache + rổ cặp live stale từ 2026-05; regime chưa cắm main.py;
   fix = 1 scheduler tháng (refresh cache → decide_month → discovery → deploy).
2. Audit lệch phí: backtest 20bp/vòng vs probe 6bp — có thể lật ranking 2.5-vs-3.0.
3. Sizing dynamic (prompt riêng đã đưa user trong chat 2026-07-24 — trục #3 concentration
   caps trước).

── CÁCH LÀM ──
Tiered testing; hỏi trước job >15'. ⚠️ Windows: script gọi discovery/multiprocessing PHẢI
có `if __name__ == "__main__"` (fork bomb đã dính 1 lần). Giải thích tiếng Việt dễ hiểu,
gloss thuật ngữ. Thật lòng: chấp nhận kết quả tiêu cực, cờ mẫu nhỏ.

── BẮT ĐẦU BẰNG ──
Viết spec pre-commit (luật trên, thêm chi tiết kỹ thuật λ-grid/CV) trình user duyệt,
RỒI mới code.
