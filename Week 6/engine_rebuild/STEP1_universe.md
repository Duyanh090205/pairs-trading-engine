# BƯỚC 1 — UNIVERSE (rổ giao dịch) — **CHỐT 2026-07-24**

Bước đầu của lần dựng-lại/chốt engine cho hướng Z=2.0 + ý tưởng Sam. Mọi quyết định
dưới đây đã kiểm chứng bằng data thật, không phải "thực hành tốt" suông.

---

## 1. Định nghĩa rổ (GIỮ NGUYÊN)

- **528 mã** trong `Week 4/data/validated/daily_phase3/*.parquet` — **KHÔNG top-N**
  (nạp cả rổ; top-K concentration đã bị bác trước đây).
- Giá ngày = **log-close của bar 5-phút cuối phiên**.
- ⚠️ **Rổ có ~25 ETF** (SPY, QQQ, các SPDR ngành XLF/XLK/XLE…, một số thematic) —
  KHÔNG thuần cổ phiếu đơn. Ảnh hưởng thiết kế trần tập trung (mục 5).

## 2. Bộ lọc cứng (GIỮ NGUYÊN — đã xác nhận sạch)

Áp **per-fold, trên formation window** (dữ liệu quá khứ) → **KHÔNG look-ahead**
(đã đọc code `_apply_hard_screens` xác nhận):

| Lọc | Ngưỡng |
|---|---|
| Giá median | ≥ $5 |
| ADV$ (mean) | ≥ $1M |
| Độ đầy đủ bar | ≥ 90% |
| Tỷ lệ return = 0 | < 50% |

Cộng các chốt chặn trong discovery: **β-cap ≤ 5**, **factor-residual (5 PCA)** trước
cointegration, **BH-FDR q=0.05**, **HL ∈ [5, 30] ngày**.

## 3. Ba chỉnh đề xuất — **ĐÃ BÁC** (kiểm chứng bằng data)

| Chỉnh | Kết quả kiểm chứng | Quyết |
|---|---|---|
| Siết zero-return 50%→25% | max zero-return cả rổ = **1,90%** → **0/528** mã đổi | **BÁC** (thừa) |
| ADV mean→median | min ADV = **$12M** (12× ngưỡng) → **0/528** mã đổi | **BÁC** (thừa) |
| Thêm lọc spread | cặp spread **RỘNG** lời NHIỀU nhất: net **$321 vs $13**, win **67% vs 53%** (gross edge scale theo spread; cost model đã trừ phí) | **BÁC** (có HẠI — cắt đúng phần lời) |

**Bài học:** 4 lọc hiện tại là rào an toàn cho rổ *rộng/nhiều rác*. Rổ này **đã
tiền-lọc thành large-cap thanh khoản**, và chiến lược mean-reversion **kiếm tiền nhiều
hơn nơi spread/biến động lớn** → đừng thêm lọc "dọn rổ". **Không thêm bộ lọc nào.**

## 4. Survivorship bias — **CAVEAT** (không vá được data)

- Rổ **chỉ mã sống sót** (quy tắc 12-tháng của Week 1 loại 192 mã;
  `Week 1/data/intermediate/universe_completeness.parquet`). SVB/FRC/SBNY/PACW/ATVI/VMW
  **vắng mặt**; 0/528 mã kết thúc trước 2026. Data delist **chưa từng được kéo về**
  (data thô Week 1 = 318 mã sống sót, 2022) và **không có Polygon** để vá.
- **Crash-test (`scratchpad/survivorship_crashtest.py`):** cấy ngân hàng-sập giả (SVB:
  −60% gap → halt → ~0) vào các cặp ngân hàng THẬT engine đã trade. 03/2023 engine giữ
  **15 cặp ngân hàng, TẤT CẢ long** (bắt dao rơi). Đuôi ẩn ước tính **−4% đến −7% vốn
  trong 1 tháng** (chặn trên −17,35%) — vs tháng thường <0,5%. **Vắng khỏi mọi số backtest.**
- **Stop-loss KHÔNG đỡ** (cú −60% là gap qua đêm + halt → không thoát được; cứu ≤40%,
  thực tế ~0). **Composite regime filter KHÔNG halt** 03/2023 (ledger trade xuyên qua).
- **Xử lý:** KHÔNG dự đoán mã nào sập (bẫy curve-fit). Phòng thủ ở **tầng sizing** (mục 5).
  Xem memory `week6_survivorship_bias_tail`.

## 5. Nhãn ngành (MỚI thêm — hạ tầng cho trần tập trung)

- **File:** `Week 6/engine_rebuild/sector_map_528.json` — **526/528 có nhãn**
  (chỉ MRSH, Q = "Unknown" → chỉ chịu trần-mỗi-tên). Gộp `Week 4/data/sector_cache.json`
  + `Week 1/.../sector_mapping.parquet` + điền tay ETF/cổ phiếu.
- Cụm lớn nhất: **Financial Services = 71 mã** (gồm ngân hàng — cụm đã cắn ở 03/2023).
  Technology 83, Industrials 74, Healthcare 63.
- ETF ngành (XLF…) map theo ngành; ETF broad (SPY/QQQ) = bucket riêng ("Broad Index").

## 6. Cam kết cho BƯỚC SIZING (không phải Bước 1 — ghi để không quên)

- **Trần mỗi TÊN** ≤ ~3% vốn (gross) — chặn blowup đơn danh.
- **Trần mỗi NGÀNH** ≤ ~10–12% vốn (gross) — neo vào con số 17% ngân hàng 03/2023
  (trị số cuối do user chốt theo khẩu vị rủi ro).
- ⚠️ **Cap-design lưu ý:** cặp *stock vs sector-ETF* (vd long bank / short XLF) là **HEDGE**
  → trần ngành phải tính **NET theo ngành**, không phải gross thô. Chi tiết ở bước sizing.

---

## TRẠNG THÁI: ✅ CHỐT

Rổ + lọc **giữ nguyên** (đã kiểm chứng). **Không thêm lọc.** Thêm: nhãn ngành 528 +
caveat survivorship. Phòng thủ đuôi = trần tập trung (bước sizing). **Sẵn sàng sang Bước 2.**
