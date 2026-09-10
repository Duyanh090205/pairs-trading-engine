# Lead-lag strategy — BẢN ĐỒ SPEC (khởi thảo 2026-07-23)

> **PHÁN QUYẾT 2026-07-23: RỚT GATE 0 → TRACK ĐÓNG THEO LUẬT.**
> Phí passive thực (V1 bid, bracket through/touch) = 2,16 / 1,92 bp/vòng > trần
> 1,5bp; follower đậu 1/89 (through), 6/89 (touch) — cần 30. Rớt bền qua mọi
> sensitivity (W, h*, κ, fade, H1/H2). Phí nền passive ~2bp cả ở phút ngẫu
> nhiên (độc-phút-tín-hiệu chỉ +0,24bp). Data sạch 2022–23 + két sắt còn nguyên.
> Kết quả: `trading_1min/results/gate0_passive/` · spec: `gate0_passive_exec_spec.md`
> · văn liệu: `gate0_lit_notes.md`. Spec 2–5 bên dưới KHÔNG BAO GIỜ chạy — giữ
> làm hồ sơ phương pháp.

Quyết định user 2026-07-23: track 1-phút tập trung vào **lead-lag đa cặp**
(bỏ Johansen). Kết hợp research (Cartea C1/Lévy-area, Bennett network,
DeltaLag, signature execution) nhưng phát triển riêng cho pipeline của ta.

**Hiện trạng làm nền:** cấu trúc lead-lag CÓ THẬT (H2/2024: 13.530 detection
vs ~3.768 null; 1.881 cặp xác nhận out-of-fit) nhưng EDGE 1–1,6bp < phí taker
4,4–9bp. → Chuỗi sống còn của chiến lược, theo thứ tự CỐ ĐỊNH:

```
GATE 0: phí thực ≤ ~1,5bp?  ──rớt──► ĐÓNG track (không đốt data sạch)
   │ đạt
GATE 1: tín hiệu sống trên 2022+2023?  ──rớt──► ĐÓNG track
   │ đạt
GATE 2: engine walk-forward + danh mục, NET dương day-clustered t≥2?
   │ đạt
GATE 3: két sắt 2025-07→2026-03 (một phát duy nhất) → paper-live
```

Kỳ vọng công bố trước (honesty): đây là chiến lược rìa-mỏng (net ~1–3bp/lệnh
kịch trần), sống chết nằm ở CHẤT LƯỢNG THỰC THI, không phải ở model. Xác suất
qua cả 4 gate: thấp-vừa. Mỗi gate rớt = kết quả nghiên cứu hợp lệ, dừng đúng luật.

---

## SPEC 1 — Passive execution feasibility (GATE 0) — LÀM ĐẦU TIÊN

**Câu hỏi:** đặt lệnh chờ (limit/maker) trên follower trong 1–2 phút sau tín
hiệu leader, phí thực round-trip là bao nhiêu? Phải gồm đủ 3 thành phần:
1. **Fill rate** — xác suất được khớp trong cửa sổ h phút (proxy OHLC:
   lệnh mua chờ tại bid ≈ close − half_spread khớp nếu low các bar sau chạm);
2. **Adverse selection** — CHẤT ĐỘC CHÍNH: lệnh chờ hay khớp đúng lúc giá
   chạy ngược; đo bằng drift sau-khớp của nhóm được-khớp vs không-khớp,
   ĐO RIÊNG tại các phút leader phát tín hiệu (spread follower có giãn ra
   đúng lúc đó không?);
3. **Chi phí cơ hội** — tín hiệu nổ mà không được khớp = mất lệnh; quy về
   bp trên tổng danh mục.
**Data:** Week 5 `spreads_1min.parquet` (L1 THẬT: half_spread, liquidity_l1)
+ bar 1-phút, chạy trên 2024 (data cháy — không tốn data sạch).
**Input cần từ user:** 4 điểm dặn của Sam về intensity score (liệt kê từ
trí nhớ — không cần hỏi Sam mới).
**Luật GATE 0 (khóa trước khi chạy):** phí thực hiệu dụng (gộp 3 thành phần)
≤ **1,5bp/round-trip** trên ≥ nhóm follower đủ rộng (≥30 mã) → ĐẠT.
Ngược lại → đóng track, báo cáo trung thực.
**Cỡ việc:** 1–2 buổi. ⚠ Giới hạn ghi trước: mô phỏng fill từ OHLC+L1 là
xấp xỉ lạc quan (không thấy queue position) — nếu GATE 0 đạt sát nút thì
phải flag "cần kiểm bằng paper-live trước khi tin".

## SPEC 2 — Định nghĩa tín hiệu & danh mục (khóa TRƯỚC Gate 1)

Các nút vặn phải CHỐT MỘT LẦN trước khi nhìn data sạch (chống chọn-số-đẹp):
- **Leader set:** đề xuất = ETF chỉ số/ngành (SPY, QQQ, XL*) + top-k mã lớn —
  bằng chứng H2/2024 cho thấy ETF→mã lẻ là trục mạnh nhất, cơ chế rõ
  (index-arb diffusion). Không quét mọi-cặp-làm-leader (nhiễu + đa so sánh).
- **Follower set:** mã phí rẻ nhất universe (sàn phí quyết định sống chết).
- **Sự kiện tín hiệu:** |return 1-phút leader| ≥ ngưỡng σ động (rolling) —
  event-based; KHÔNG dùng tín hiệu liên tục ở v1 (đơn giản trước).
- **Gộp nhiều leader cho 1 follower:** trung bình có trọng số ρ của tín hiệu
  các leader đang nổ (v1 đơn giản); network clustering kiểu Bennett = v2.
- **Vào/ra:** vào close bar t+1 (kỷ luật lag quen thuộc, chống bounce);
  ra theo time-stop cố định h* phút (chọn từ response curve ĐÃ CÓ của
  H2/2024 — không fit lại trên data sạch); ép đóng cuối phiên (không qua đêm).
- **Danh mục:** nhiều cặp đồng thời; equal-weight per signal; cap tổng
  exposure; cap per-follower; QUYẾT ĐỊNH MỞ cho user: có hedge chân thị
  trường (short SPY tương ứng) không — hedge làm sạch DNA rủi ro nhưng
  tốn thêm ~0,2–0,4bp/vòng.
- **Ước lượng ρ/lag:** cửa sổ tĩnh 3 tháng, cập nhật theo quý (như scan);
  DeltaLag/dynamic = nâng cấp sau, không phải v1.

## SPEC 3 — Xác nhận trên data sạch (GATE 1; chỉ chạy nếu Gate 0 ĐẠT)

**Data:** 2022 và 2023 — hai kỳ độc lập, regime khác hẳn nhau (2022 gấu +
vol cao; 2023 hồi phục) và khác 2024. Protocol y hệ scan cũ: fit nửa đầu
năm → confirm nửa cuối năm, TỪNG năm riêng.
**Luật GATE 1 (khóa trước):** trên CẢ 2022 VÀ 2023:
(a) detection vượt null (cùng quy trình 20 lần xáo trộn);
(b) tập cặp xác nhận chồng lấp có ý nghĩa với 2024 (ổn định cấu trúc —
    ngưỡng: ≥30% cặp top-100 của 2024 tái xuất hiện trong top-300 của năm đó);
(c) EDGE danh mục top-N (N chốt ở Spec 2) > phí thực từ Gate 0, t gom-theo-ngày ≥ 2.
Rớt bất kỳ điều nào ở bất kỳ năm nào → đóng track.

## SPEC 4 — Tích hợp engine v0 (GATE 2)

- Module mới: `selection_leadlag.py` (ước lượng ρ/lag theo quý),
  `simulate_event.py` (máy trạng thái event-driven: vào t+1, time-stop,
  fill model passive từ Spec 1), dùng lại `stats.py` (t gom cụm) + config/.
- **Cửa nghiệm thu kiểu cũ:** engine phải tái lập bằng số kết quả scan
  standalone (kỷ luật bitwise như đợt Johansen).
- Walk-forward trên 2022→2024 (đã đốt cả rồi ở gate trước — hợp lệ để build),
  đo NET danh mục sau phí thực + phân bố đuôi + capacity ước lượng
  (khối lượng khớp được ở quy mô vốn nhỏ).
- **Luật GATE 2 (khóa trước khi chạy walk-forward):** NET > 0 với
  day-clustered t ≥ 2 trên giai đoạn walk-forward gộp, và không năm nào
  âm nặng (min năm > −5bp/lệnh trung bình).

## SPEC 5 — Két sắt + đường ra live (GATE 3)

- 2025-07→2026-03 chỉ mở khi: engine đóng băng, mọi tham số khóa, luật
  đậu/rớt viết sẵn. MỘT phát duy nhất, không sửa sau khi thấy.
- Sau két sắt: paper-live cần quote real-time → quyết định SIP ~$99/tháng
  (memory `week6_1min_data_feasibility`) — quyết định TIỀN của user, để đến lúc đó.

---

## Việc user cần cho giai đoạn tới

1. **Liệt kê 4 điểm dặn của Sam** (intensity score / thoát khi ngược) → input Spec 1.
2. **Duyệt thứ tự:** Spec 1 chạy trước (trên data cháy), Spec 2 chốt nút vặn,
   rồi mới đụng data sạch.
3. **Quyết định DNA rủi ro** (Spec 2): chấp nhận vị thế 1 chân có hướng trong
   vài chục phút, hay bắt buộc hedge chân SPY?
