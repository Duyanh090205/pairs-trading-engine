# PROMPT SESSION MỚI — PRESENTATION "3 TÀI SẢN" (không bán alpha)

(Dán nguyên khối dưới vào session mới. Auto-memory + CLAUDE.md tự nạp.)

---

PRESENTATION — đóng gói chương trình quant thành bài trình bày "3 tài sản"

── POSITIONING (user ĐÃ QUYẾT 2026-07-24 — không bàn lại) ──
KHÔNG bán alpha của engine V4 (gross mỏng; cả 3 Z âm OOS khi regime OFF; live paper
−$458 — nói thẳng trong bài, đó là điểm TRUNG THỰC, không giấu). Bài bán 3 tài sản:

1. **BỘ ĐO SỰ THẬT THỰC THI** (execution-truth stack) — alpha-agnostic, đo được:
   - Probe live 2026-07-24: 253 lệnh thật (Alpaca paper): taker 100% khớp/~1,3s/+1,5bp;
     passive 60% khớp/median 17s/ăn −1,9bp; 15–23% quote IEX rác.
     File: trading_1min/results/v4_exec_sim/probe_fills.csv
   - L1 spread THẬT (Week 5, row-aligned): Week 5/data/microstructure/spreads_1min.parquet
   - Bản đồ phí theo giờ: 15:30 half-spread ~0,94bp vs 9:30 ~4,56bp (~5×) — slot_map
   - Simulator probe-calibrated + phát hiện ĐỔI QUYẾT ĐỊNH: backtest tính ~20bp/vòng
     vs probe thật ~6bp — lệch có thể lật ranking Z (audit đang treo)
2. **THƯ VIỆN KẾT QUẢ ÂM ĐÃ KIỂM CHỨNG** (kill-list) — mỗi dòng = giờ công + compute
   người khác phải trả để học lại; tất cả pre-commit rồi mới chạy:
   - Carry-forward: full 39-fold −18,55% (gate Johansen +66pp signal thật mà vẫn lỗ)
   - Z=2.0: gross ÂM trước phí (−$5.5k/2336 lệnh) — execution không cứu được
   - Top-K concentration: mọi K<500 tệ hơn | Z≥3.5: đói lệnh
   - Intensity TĨNH không tách thắng/thua carry (cặp carry đẹp p=0.0056/HL 8.3d vẫn lỗ)
   - S2/S4 asym execution (ý Sam): ĐO $178/4 tháng → đóng có số liệu
   - Concentration caps (Step 5): lợi đo được ~0 → không xây
   - Lead-lag 1-phút: đóng Gate 0 (phí passive thật 1,92–2,16bp > trần 1,5bp, 1/89 đậu)
   - Kalman dynamic-β: bác ở ship config | Survivorship tail: khai báo −4~7% (SVB crash-test)
3. **INSIGHT KIẾN TRÚC: edge nằm ở TẦNG RỦI RO, không phải tín hiệu**
   - OOS (fold 31-39) regime OFF: Z2.0 −9.0% / Z2.5 −4.9% / Z3.0 −2.1% — CẢ BA ÂM
   - Regime filter ON: −2.07% → +0.49% (monthly Sharpe +1.01)
   - TRUNG THỰC 2 mặt: filter có 3 tật (nhị phân/hạt tháng/nhả chậm) — replay 2026
     halt 3/4 tháng, né $0.6k lỗ nhưng bỏ lỡ +$13.3k; caveat thiết-kế-có-hindsight
Meta-frame xuyên suốt: món hàng thật = QUY TRÌNH (spec pre-commit STEP1-3+5, tiered
testing, honest OOS, dám giết giả thuyết của mình trong 1 buổi khi số nói vậy).

── SLOT CHỜ: JUMP MODEL TIER-0 ──
User đang chạy JM (detector regime, λ-penalty) ở session khác. TRƯỚC KHI dựng bài:
kiểm auto-memory xem có kết quả JM Tier-0 chưa (tìm memory mới về JM/regime).
- ĐẬU (bear Dec25–Mar26 + bull Jun-Jul26 + không nhát hơn 2023-25) → thêm vào điểm 3:
  "và đây là hướng nâng cấp detector đã kiểm chứng sơ bộ".
- RỚT → thêm vào kill-list điểm 2 (một dòng giết-giả-thuyết nữa — vẫn là selling point).
- CHƯA CÓ → dựng bài không có JM, chừa 1 slide "đang kiểm chứng".

── NGUỒN SỐ LIỆU (mọi số trong bài PHẢI truy được về file) ──
- Specs: Week 6/engine_rebuild/STEP1_universe.md, STEP2_walkforward.md, STEP3_signal.md,
  STEP5 (xem memory week6_step5_sizing), gate0_passive_exec_spec.md,
  s2s4_intensity_exec_spec.md
- Kết quả: Week 6/results/v4/zsweep_sl50_regimeoff/ (foldmetrics+ledger 3 Z),
  Week 6/results/v4/replay_2026/, Week 6/results/v4/carry_forward/,
  trading_1min/results/v4_exec_sim/ (probe, report), Week 5/reports/
- Live thật (điểm trung thực + năng lực engineering): engine deploy Render/Alpaca paper
  từ 2026-05-25, equity −$458; reconcile two-strike, kill-switch, orphan-flatten,
  dashboard — kể như bằng chứng vận hành, không phải thành tích P&L.

── HỎI USER TRƯỚC KHI DỰNG (4 câu, rồi mới làm) ──
1. Khán giả: Sam / nhà tuyển dụng / công khai (LinkedIn-GitHub)? → đổi giọng + độ sâu.
2. Ngôn ngữ: English (chuẩn ngành) hay tiếng Việt?
3. Định dạng: slide HTML (Artifact), markdown deck, hay tài liệu dài?
4. Thời lượng: pitch 5' / trình bày 20' / tài liệu đọc?

── CÁCH LÀM ──
- Cấu trúc gợi ý: mở bằng câu "alpha là hàng dễ hỏng — chúng tôi bán cái thước":
  1 slide thú nhận alpha mỏng (số thật) → 3 tài sản → quy trình → JM slot → kết.
- Mọi claim gắn số + file path. Caveat (mẫu nhỏ, paper account, survivorship) hiển thị
  CHỦ ĐỘNG — trung thực là điểm khác biệt của bài, không phải phụ lục.
- Nếu làm slide HTML: load skill dataviz trước khi vẽ chart.
- Giải thích với user bằng tiếng Việt trong chat; sản phẩm theo ngôn ngữ user chọn ở câu 2.
