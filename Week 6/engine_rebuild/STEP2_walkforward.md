# BƯỚC 2 — FORMATION WINDOW + WALK-FORWARD — **DRAFT (đang verify)**

Nối tiếp `STEP1_universe.md`. Cùng phong cách: mọi quyết định phải kiểm chứng bằng
data thật, sẵn sàng bác. Trạng thái từng mục ở mục 0.

---

## 0. Checklist trạng thái

| Hạng mục | Giá trị đề xuất | Trạng thái |
|---|---|---|
| Cấu trúc walk-forward (test 1m, 39 fold, re-discovery hàng tháng) | xem mục 1 | ✅ **KHỚP CODE** |
| Độ dài formation | 12 tháng lịch | ✅ **CHỐT GIỮ 12m** (subset: <12m ra 0 cặp) |
| Carry-forward / EOM flatten | OFF → EOM flatten | ✅ **CHỐT** (thắng ở cả Z=3.0 và Z=2.0) |
| Pair jitter / turnover (angle 2) | đo độ ổn định cặp giữa fold | ✅ **ĐÃ ĐO** (~12% cặp sống/tháng) |
| Cờ mẫu nhỏ / power (angle 4) | disclosure | ✅ ghi nhận (mục 5) |

**Kết luận nhanh:** Bước 2 ✅ **ĐÃ XONG** — mọi tham số đã kiểm chứng/chốt. Sẵn sàng Bước 3.

---

## 1. Cấu trúc walk-forward — ✅ KHỚP CODE

Đối chiếu `run_v4_pipeline.py:79-101` (`_build_fold_schedule_v4`):

| Tham số | Giá trị | Xác nhận |
|---|---|---|
| Formation | 12 tháng **lịch** (`DateOffset(years=1)`), ~250–253 phiên (dao động theo lễ) | ✓ |
| Trượt | 1 tháng/fold | ✓ |
| Test | 1 tháng/fold (`MonthEnd(0)`) | ✓ |
| Số fold | 39 (2023-01 → 2026-03) | ✓ |
| Tái khám phá | MỖI fold: hard screens + PCA (5 comp) + Johansen + BH-FDR + HL[5,30] + β>0 + \|β\|≤5 chạy lại | ✓ |

**Chính xác hoá:** β đóng băng từ formation; **α refit** trên 60 phiên cuối tại đầu cửa
sổ test (`alpha_lookback=60` + Path A re-anchor, `run_v4_pipeline.py:220-228`). Discovery
1 fold ≈ **35 giây** (đo thật).

---

## 2. Độ dài formation (12 tháng) — ✅ CHỐT (giữ 12m)

**Lập luận:** ~250 phiên đủ power cho Johansen/cointegration; đủ dài để β bớt nhiễu.
**Phản biện:** ngắn (6–9m) → β nhiễu, cặp bất ổn; dài (18–24m) → quan hệ cũ + **ít fold
độc lập = ít power OOS** (nối thẳng vào angle #4).

**Analytical (đã chạy):** jitter β = std/|mean| qua cửa sổ trượt, 402 cặp thật —
median: 6m=1.85 · 12m=1.36 · 24m=0.89. **Đúng hướng** (dài hơn = ổn định hơn) nhưng
**CV>1 = vô nghĩa tuyệt đối** vì đo **giá thô**, không phải PCA residual (không gian β
thật của V4). ⇒ Proxy KHÔNG đủ quyết.

**✅ SUBSET (chạy 2026-07-24, discovery thật, 3 mốc × 5 độ dài, số cặp tìm được):**

| mốc \ độ dài | 6m | 9m | 12m | 18m | 24m |
|---|---|---|---|---|---|
| 2024-06 | 0 | 0 | 195 | 148 | 120 |
| 2025-03 | 0 | 0 | 187 | 143 | 138 |
| 2025-12 | 0 | 0 | 3 | 204 | 108 |
| Jaccard vs 12m | — | — | 1.00 | ~0.02 | ~0.01 |
| β drift vs 12m | — | — | 0 | 0.11–0.20 | 0.28–0.36 |

**Phát hiện:**
1. **6m & 9m = 0 cặp** (cả 3 mốc) → discovery cần ≥~12m mới ra cặp. **12m = mức TỐI THIỂU
   khả dụng**, không rút ngắn được.
2. 18m/24m tìm ra **rổ cặp gần như khác hẳn** (Jaccard vs 12m ~0.02) + **β drift** tăng
   (0.11→0.36) → "dài hơn" KHÔNG phải "12m nhưng ổn định hơn" mà là **rổ khác + hedge lệch**.
3. n_pairs 12m: 2/3 mốc nhiều nhất (195, 187); 1 mốc dị thường (2025-12 = 3) → có tháng
   ít cặp bất thường (rủi ro đuôi tập trung — ghi nhận, không đổi quyết).

**QUYẾT: GIỮ 12m.** Mức tối thiểu khả dụng + thường cho nhiều cặp nhất + đang là config
ship. Không có bằng chứng OOS nào cho thấy dài hơn tốt hơn (chưa chạy full length-sweep —
cờ mẫu nhỏ). Muốn đổi phải có OOS Sharpe chứng minh; hiện không có. *(Analytical proxy
giá-thô lúc đầu inconclusive — subset residual-space này mới là bằng chứng quyết.)*

---

## 3. Carry-forward OFF / EOM flatten — ✅ CHỐT (Z=3.0 và Z=2.0)

### 3.1 Làm rõ logic thoát (gỡ hiểu lầm)
Engine có **3 cửa thoát**; 2 trong đó chính là "chạy hết ngưỡng" và "thoát lúc xấu":

| Cửa | Ý nghĩa |
|---|---|
| `zero_cross` (Z→0) | chạy hết ngưỡng — hồi về mean, chốt lời |
| `hard_sl` (\|Z\|≥4) | thoát lúc xấu — cắt lỗ |
| `open_at_eom` | **chỉ** cho lệnh chưa chạm cửa nào tới cuối tháng |

→ EOM **không thay** 2 luật kia. Lựa chọn thật: lệnh còn treo cuối tháng → **đóng luôn
(EOM)** hay **ôm sang tháng (carry)**.

### 3.2 Bằng chứng Z=3.0 (ledger `trades_z30_composite.csv`, 428 lệnh, 26/39 fold trade)

Exit-mix + P&L:

| exit_reason | Số | Tỷ lệ | Tổng net | TB/lệnh |
|---|---|---|---|---|
| `open_at_eom` | 385 | 90% | **−$372** | −$1 (≈0) |
| `zero_cross` | 31 | 7% | **+$40.145** | +$1.295 |
| `hard_sl` | 12 | 3% | **−$16.597** | −$1.383 |

**Carry-forward full 39-fold (đã chạy, `carry_forward/fold_metrics.csv`):**
sum return **−18,55%**, mean Sharpe **−0,66**, 1.876 carry, 1.041 bị gate cắt → **tệ hơn
baseline (baseline dương)**.

**Vì sao đóng (EOM) > ôm (carry):**
1. **Adverse selection:** reverter nhanh đã thoát bằng `zero_cross` sớm; còn treo cuối
   tháng = đám lì. Ôm = cố giữ đúng nhóm tệ.
2. **Đuôi trái bất đối xứng:** ôm tiếp = phơi ra `hard_sl` (−$1.383) trong khi phần thắng
   đã cạn.
3. **Chồng đòn bẩy + thêm phí.**
   Bằng chứng gián tiếp: cặp bị carry trông **xuất sắc trên statics** (median Johansen
   p=0,0056; HL 8,3d < 11,1d trung bình) mà vẫn lỗ → intensity *tĩnh* (cường độ coint,
   HL) **không tách được thắng/thua** ⇒ "intensity score" kiểu đó không cứu được carry.
   Gate p<0.05 vốn ĐÃ là intensity filter mạnh (78% vs 11,7% ngẫu nhiên) mà vẫn −18,5%.

**EOM là hệ quả tự nhiên của re-discovery hàng tháng** (mỗi fold factor model đổi → Z
định nghĩa lại; ôm qua tháng = ôm bằng hệ toạ độ cũ). Không phải luật gắn thêm.

### 3.3 Bằng chứng Z=2.0 — ✅ ĐÃ CHỐT

Exit-mix **không phụ thuộc cost** (do quỹ đạo Z) → đọc được từ grid:

| Z | zero | sl | **eom** |
|---|---|---|---|
| 1.5 | 26% | 4% | 70% |
| **2.0** | 17% | 5% | **77%** |
| 2.5 | 11% | 4% | 86% |
| 3.0 | 7% | 3% | 90% |

Z thấp → EOM ít hơn (vào gần mean → hồi kịp nhiều hơn). Ở Z=2.0 vẫn 77% (đa số).
**Nhưng carry-vs-EOM P&L ở Z=2.0 CHƯA có** → đang chạy subset 2 khối (fold 1–8 stress +
25–32 êm), dynamic cost, EOM vs carry.

**KẾT QUẢ (subset chạy 2026-07-24, Z=2.0 dyncost, EOM vs carry):**

| Khối | EOM sum_ret / Sharpe | CARRY sum_ret / Sharpe | carry turnover |
|---|---|---|---|
| A (2023 stress, 03/2023) | **+0.25% / +2.11** | −0.56% / +0.19 | +78% lệnh |
| B (2025 êm) | +5.77% / **+1.65** | +6.26% / +1.21 | +62% lệnh |
| **Gộp return** | **EOM +6.03%** | carry +5.70% | |

**Kết luận:** ✅ **EOM thắng ở Z=2.0.** Thắng Sharpe ở CẢ 2 regime; thắng return gộp;
chịu stress tốt hơn hẳn (2023 carry lỗ). Carry chỉ nhỉnh raw-return trong thị trường êm
(+0.48pp) nhưng đổi bằng +62% turnover + Sharpe thấp hơn. Thiết kế còn thiên vị *nhẹ có
lợi cho carry* (fold cuối carry-out không hiện thực hoá) mà carry vẫn thua → kết luận vững.
Khớp phát hiện Z=3.0 (carry full-run −18.5%). **EOM flatten = CHỐT cho ship.**

---

## 4. Pair jitter / turnover (angle 2) — ✅ ĐÃ ĐO

**Đo 2026-07-24 (6 cặp tháng liên tiếp @ 12m, 2024-06→12):**
Chỉ **~12,5% cặp sống sang tháng sau** (median month-to-month Jaccard = 0.063; range
0.02–0.34). Tức mỗi tháng **~87% rổ cặp là MỚI**.

**Ý nghĩa:**
- Turnover cặp **cao** → khớp `week6_orphan_flatten` (tái khám phá gây jitter → orphan vị
  thế khi deploy). Cần EOM flatten + orphan-recovery (đã có).
- **Củng cố EOM flatten (mục 3):** rổ cặp đổi ~87%/tháng → ôm vị thế sang tháng sau (carry)
  vào một universe gần như khác = vô lý → thêm một lý do carry thua.
- **Live:** cặp cố định trong `discovered_pairs.parquet` (divergence #5) lệch nhanh khỏi
  backtest → phải chạy discovery hàng tháng đều (hiện làm tay, chưa có scheduler).

---

## 5. Cờ mẫu nhỏ / power (angle 4) — disclosure

39 fold nhưng **~26–27 có trade**; t-stat V-open ≈ **0,85** (chưa significant sau phí
thực). Mọi kết luận Bước 2 phải treo cờ này: độ dài formation & số fold ăn thẳng vào
power. **Không tuyên bố "significant" ở cỡ mẫu này.**

---

## 6. Còn thiếu gì để sang Bước 3 — ✅ XONG CẢ 3

1. ✅ **EOM @ Z=2.0** — EOM thắng carry (mục 3.3).
2. ✅ **Độ dài formation** — giữ 12m (mục 2).
3. ✅ **Pair jitter** — đo xong, ~12%/tháng (mục 4).

→ **Bước 2 CHỐT.** Sang Bước 3 (Signal): quyết entry Z, hard SL, time-stop.

---

## 7. Cross-ref (không thuộc Bước 2, ghi để không quên)
- Survivorship bias + trần tập trung ngành → **bước sizing** (đã cam kết ở STEP1 mục 6).
- Carry-forward + concentration + Z>3.5 = đã bác (memory `week6_rejected_approaches`).

## TRẠNG THÁI: ✅ CHỐT (2026-07-24)

Cấu trúc walk-forward giữ nguyên (khớp code): formation **12m** (mức tối thiểu khả dụng),
test 1m, 39 fold, re-discovery hàng tháng, **EOM flatten** (thắng carry ở cả Z=3.0 & Z=2.0).
Pair jitter cao (~12%/tháng) — ghi nhận cho khâu live. Không đổi tham số nào. Sang Bước 3.
