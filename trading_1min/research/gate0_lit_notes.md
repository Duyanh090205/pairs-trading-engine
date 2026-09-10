# Gate 0 — ghi chú văn liệu (2026-07-23, kiểm chứng web từng bài)

Mục đích: rà 6 bài user dẫn cho họ lead-lag + bổ sung nhóm bài **đúng cho tầng
thực thi** (Gate 0 là bài đo THỰC THI, không phải đo tín hiệu). Mỗi bài ghi rõ:
đã kiểm chứng chưa, và nó ĐỔI GÌ trong thiết kế Gate 0.

## A. 6 bài user dẫn — vai trò với Gate 0

| Bài | Trạng thái kiểm chứng | Dùng cho Gate 0? |
|---|---|---|
| Cartea/Cucuringu/Jin (SSRN 4599565, 10/2023) | Phiên 2026-07-23 đã kiểm: **bar NGÀY** (1963–2022), replication độc lập không trừ phí → >20%/năm không phải bằng chứng thang phút | Không (signal-side). Không cần săn PDF cho Gate 0; nếu cần cho Spec 2 sẽ nhờ user |
| Bennett/Cucuringu/Reinert (arXiv 2201.08283, ML 2022) | Thật, bản arXiv miễn phí | Không — network clustering là nâng cấp v2 của Spec 2 (gộp nhiều leader) |
| DeltaLag (arXiv 2511.00390, 2025) | Thật | Không — lead-lag động/deep là v2+, roadmap đã ghi |
| Tick futures TQ (arXiv 2501.03171, 2025) | Thật, chợ khác | Gián tiếp: nhắc rằng ở thang tick, lead-lag bị tốc độ gặt — cùng thông điệp Huth–Abergel |
| Stoll & Whaley 1990 (index futures dẫn cổ phiếu) | Kinh điển | **Có**: cơ chế index-arb diffusion → đỡ cho quyết định "hướng vào lệnh = theo chiều leader (chase)" |
| Huth & Abergel (arXiv 1111.7103, JEF 2014) | Kinh điển | **Có — cảnh báo trung tâm của Gate 0**: mã thanh khoản cao dẫn mã kém, và edge thuộc về hạ tầng NHANH → tại phút tín hiệu, lệnh chờ của ta nằm trên "thực đơn" của người nhanh. Đây chính là adverse selection cần đo |

## B. Bổ sung cho pipeline Gate 0 (đều đã kiểm chứng web 2026-07-23)

**Khung lý thuyết adverse selection của lệnh chờ:**
1. **Copeland & Galai 1983** — *Information Effects on the Bid-Ask Spread*, J. Finance 38(5), 1457–69. Lệnh chờ = viết free option cho trader có thông tin. → Lý do tồn tại của thành phần 2 (adverse selection) và của loss-cut S4 (cắt sớm = cắt bớt payoff của option mình đã viết).
2. **Handa & Schwartz 1996** — *Limit Order Trading*, J. Finance 51, 1835–61. Hai rủi ro của lệnh chờ: (i) khớp đúng lúc tin xấu, (ii) không khớp đúng lúc tin tốt — **chính là thành phần 2 và 3 của Gate 0**. Empirics: lệnh chờ có thể thắng lệnh thị trường với trader kiên nhẫn → Gate 0 không phải nhiệm vụ vô vọng tiên nghiệm.

**Chuẩn đo lường:**
3. **Huang & Stoll 1996** — JFE 41, 313–357. Effective spread = realized spread + price impact, đo bằng **markout mid tại t+τ sau khớp**. → Amendment spec: thêm markout sau-KHỚP Δ∈{1,5,15}' (maker giữ được bao nhiêu half-spread sau khi giá điều chỉnh).
4. **Harris & Hasbrouck 1996** — *Market vs. Limit Orders: the SuperDOT Evidence*, JFQA 31(2), 213–232. Thước đo hiệu năng lệnh có **phạt lệnh không khớp** (precommitted trader) — cùng tinh thần công thức cost_eff = f×IS + (1−f)×edge_ref của ta. Kết quả họ: limit tại/tốt hơn quote thắng market order kể cả sau phạt — nhưng chiến lược cạnh tranh cung cấp thanh khoản vô điều kiện thì KHÔNG có lời → đừng kỳ vọng ăn spread free.

**Queue position (vì sao phải bracket through/touch):**
5. **Moallemi & Yuan 2016/17** — *A Model for Queue Position Valuation in a Limit Order Book* (Columbia/SSRN 2996221). Adverse selection TĂNG theo vị trí sau trong queue; với cổ phiếu tick-lớn, giá trị vị trí queue **cùng cỡ spread**. → Data bar không thấy queue ⇒ mọi point-estimate fill đều sai theo một hướng nào đó ⇒ spec dùng bracket THROUGH (bảo thủ) / TOUCH (lạc quan) thay vì một con số.

**Vì sao phút tín hiệu là phút độc (control bắt buộc):**
6. **Budish, Cramton & Shim 2015** — QJE 130(4), 1547–1621. Arbitrage ES–SPY tồn tại ở thang ms và bị cày bởi cuộc đua tốc độ; tương quan sụp ở horizon ngắn. → Lead-lag 1-phút của ta là phần CÒN SÓT sau cuộc đua ms; ai đó nhanh hơn đang hành động đúng phút leader nổ → phải đo IS tại phút tín hiệu SO VỚI control matched (mục 2c spec), không được đo phí trung bình rồi suy ra.

**Cho Spec 2 (không thuộc Gate 0):**
7. **Avellaneda & Stoikov 2008** — *High-frequency trading in a limit order book*, Quant. Finance 8(3), 217–224. Khung quote tối ưu theo inventory/risk — bản học thuật của intensity→aggressiveness mà Sam mô tả (S2). Để dành khi thiết kế mapping ở Spec 2.

## C. Kết luận rà soát → thay đổi spec (amendment trước-khi-chạy)

1. Thêm markout sau-KHỚP chuẩn Huang–Stoll vào mục adverse selection.
2. Ghi rõ: commission 0, maker rebate 0 (Alpaca retail) — không cộng khống.
3. Caveat queue dẫn Moallemi–Yuan (bracket là bắt buộc, không phải lựa chọn).
4. Ghi chú cost_eff khớp chuẩn phạt-lệnh-không-khớp Harris–Hasbrouck.

Không thay đổi nào đụng đến LUẬT ĐẬU/RỚT đã chốt (1,5bp / ≥30 mã / f≥25% /
bracket 3 mức) — chỉ thêm thước đo báo cáo + ghi chú cơ sở.

## Nguồn (kiểm chứng 2026-07-23)

- Handa & Schwartz 1996: https://onlinelibrary.wiley.com/doi/10.1111/j.1540-6261.1996.tb05228.x
- Huang & Stoll 1996 (JFE 41): https://www.acsu.buffalo.edu/~keechung/MGF743/Readings/F1.pdf
- Moallemi & Yuan: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2996221 ; PDF: https://moallemi.com/ciamac/papers/queue-value-2016.pdf
- Harris & Hasbrouck 1996: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7758
- Copeland & Galai 1983: https://onlinelibrary.wiley.com/doi/10.1111/j.1540-6261.1983.tb03834.x
- Budish, Cramton & Shim 2015: https://academic.oup.com/qje/article/130/4/1547/1916146
- Avellaneda & Stoikov 2008: https://ideas.repec.org/a/taf/quantf/v8y2008i3p217-224.html
