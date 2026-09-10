# Nghiên cứu: Các firm chạy chiến lược intraday ~1-phút như thế nào (2026-07-08)

> Bước 1 của track backtest 1-phút (rebuild từ đầu, từng bước nhỏ). Nguồn: search thường (không deep-research, tiết kiệm token). Lưu ý trung thực: **cách firm làm thật là bí mật thương mại** — cái public được là (a) paper học thuật, (b) sách practitioner (Ernest Chan), (c) backtest công khai (QuantConnect), (d) bài viết marketing (độ tin thấp, có gắn cờ). Không nguồn nào là "sổ tay nội bộ" thật.

## 1. Tín hiệu (signal) ở thang intraday

- **Chuẩn mực học thuật gốc: Avellaneda & Lee (2008)** — stat-arb trên US equities bằng **factor-residual reversion**: tách return mỗi mã thành phần "hệ thống" (PCA factors hoặc sector ETF) + phần dư (residual/idiosyncratic), model phần dư như quá trình mean-reverting (OU), trade theo **s-score** (z-score của residual). Cửa sổ ước lượng residual **60 ngày**; chỉ trade khi tốc độ hồi quy đủ nhanh (lọc theo mean-reversion time < ½ chu kỳ). Sharpe **1.44 net cost giai đoạn 1997–2007** — nhưng đây là **rebalance theo NGÀY**, không phải 1-phút, và edge suy giảm dần sau 2002–2007 (crowding). [SSRN 1153505](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1153505)
- **Phiên bản intraday công khai gần nhất với ta: QuantConnect "Intraday Dynamic Pairs Trading"** — bar **10-phút** (gộp từ 1-phút), 20 mã ngân hàng Mỹ (190 cặp khả dĩ), chọn cặp 2 tầng: **correlation ≥ 0.9 → cointegration p ≤ 0.05**; formation **3 tháng** rolling; entry **±2.33σ**, exit **±0.5σ**, stop **±4σ**; tối đa 10 cặp chia đều vốn. Kết quả ví dụ (Sep 2013): CAR ~26.9%, Sharpe ~3.0, beta 0.23. **Caveat: cost/slippage không được model chi tiết; kết quả 1 giai đoạn ngắn → lạc quan.** [QuantConnect](https://www.quantconnect.com/learning/articles/investment-strategy-library/intraday-dynamic-pairs-trading-using-correlation-and-cointegration-approach), paper gốc [Miao 2014](https://www.researchgate.net/publication/312702610_High_Frequency_and_Dynamic_Pairs_Trading_Based_on_Statistical_Arbitrage_Using_a_Two-Stage_Correlation_and_Cointegration_Approach)
- Các nghiên cứu tần suất cao hơn cho thấy **tần suất cao hơn → tín hiệu gộp nhiều hơn** (ví dụ 5-min > daily rõ rệt trong crypto/equity studies) nhưng đồng thời **cost ăn tỷ lệ thuận với số lần trade** — lợi thế gộp chỉ có nghĩa nếu sống sót qua cost. [Springer](https://link.springer.com/article/10.1007/s10614-023-10539-4)
- Bài học chung: ở thang phút, họ **không** dùng cointegration kiểu daily nguyên bản — họ trade **residual so với factor/cặp** với cửa sổ ước lượng NGÀY–THÁNG nhưng tín hiệu tính trên bar phút.

## 2. Chọn universe / cặp

- Thanh khoản là điều kiện tiên quyết tuyệt đối: mã phải có **spread hẹp** (cost = spread là chi phí chính ở thang này) + volume đủ. Nghiên cứu retail đồng thanh: "chọn tài sản thanh khoản, spread hẹp, phí thấp — nếu không thì toán học không còn đúng". [Quant Matter](https://quantmatter.com/retail-algorithmic-trading/)
- Cách làm phổ biến: nhóm cùng ngành (banks, energy...) → lọc correlation cao → test cointegration → giới hạn số cặp đồng thời (concentration cap).

## 3. Qua đêm hay flatten?

**Phụ thuộc vào half-life của tín hiệu — không có quy tắc chung "firm luôn làm X":**
- Ernest Chan mô tả hệ intraday điển hình: **vào lệnh trong ngày, đóng hết vị thế ở close** — giết hoàn toàn overnight gap risk; nếu muốn giữ qua đêm thì phải xử lý bar qua đêm khác đi (nhân variance lên). [About Trading — Machine Trading takeaways](https://abouttrading.substack.com/p/my-key-takeaways-from-machine-trading), [epchan blog](http://epchan.blogspot.com/2016/04/mean-reversion-momentum-and-volatility.html)
- Desk stat-arb giữ 150–300 vị thế mỗi chiều thì **giữ qua đêm** (horizon nhiều ngày) — nhưng đó là chiến lược daily-rebalance kiểu Avellaneda-Lee, không phải 1-phút. [algotradingdesk (⚠️ marketing, độ tin thấp)](https://algotradingdesk.com/inside-arbitrage-desk/)
- Lý do cấu trúc để flatten ở Mỹ: **day-trading buying power 4× intraday vs 2× overnight** — flatten cho phép leverage gấp đôi trên cùng vốn; cộng thêm không ăn gap qua đêm, không borrow qua đêm.
- **Kết luận vận hành: horizon phút–giờ → flatten cuối ngày là chuẩn mực; horizon nhiều ngày → giữ.** Quyết định của ta nên chờ đo half-life thực tế của spread 1-phút trên data của ta.

## 4. Execution: passive limit vs aggressive cross

- **Dòng nghiên cứu Cartea–Jaimungal chính là lời giải hàn lâm cho câu hỏi của Sam**: bài toán tối ưu trộn **limit order** (giá tốt hơn nhưng không chắc khớp + dính adverse selection — bị khớp đúng lúc giá chạy ngược) và **market order** (chắc khớp nhưng trả spread), điều tiết theo **độ khẩn cấp** (urgency) của tín hiệu và trạng thái order book. Tức là "intensity score" = phiên bản heuristic 1–100 của khung này — có nền tảng học thuật vững. [SSRN 2397805 — Optimal Execution with Limit and Market Orders](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2397805), [danh mục paper Jaimungal](https://sebastian.statistics.utoronto.ca/research-papers/)
- Về cost thực tế: nghiên cứu "Mean Reversion Pays, but Costs" — với linear transaction cost, **phần lớn giá trị bị trả vào việc cross bid-offer trừ khi có "buffer"** (giá phải đi đủ xa mới trade). Đây đúng là logic Z-threshold + gate của ta. [arXiv 1103.4934](https://arxiv.org/pdf/1103.4934)
- Caveat mọi fill-simulator: giả định "chạm giá là khớp" bỏ qua **queue priority** (xếp hàng) và **adverse selection** → lạc quan có hệ thống cho nhánh passive. Phải khai báo rõ khi báo cáo.

## 5. Risk controls đặc thù intraday

- **Né đầu phiên**: 15–30 phút đầu spread rộng, hướng nhiễu, imbalance từ đêm trước — đa số professional chờ ~10:00–10:15 mới vào. (Khớp với `_SESSION_WARMUP_BARS=30` mà Week 4 đã làm, và với spread_seasonality Week 5.) [TradingSim](https://www.tradingsim.com/blog/6-reasons-not-to-trade-during-the-first-30-minutes)
- **Né cuối phiên / auction đóng cửa**: flatten trước close 10–25 phút (broker RMS cũng auto-square-off tầm đó).
- Giới hạn vị thế: mỗi mã **1–3% gross exposure**; beta portfolio giữ trong **±0.10**; **event filter** (mã có corporate action / news → restricted list); daily stop-loss cấp portfolio; stop cấp cặp (ví dụ ±4σ). [Quantt guide](https://www.quantt.co.uk/resources/statistical-arbitrage-guide), [QuantConnect](https://www.quantconnect.com/learning/articles/investment-strategy-library/intraday-dynamic-pairs-trading-using-correlation-and-cointegration-approach)

## 6. Retail (hoàn cảnh của ta) làm được gì?

- **Ở horizon phút–giờ, tốc độ KHÔNG phải rào cản chính — cost mới là.** Colocation/tick data chỉ bắt buộc ở sub-second. Với bar 1-phút + quote L1, phần **nghiên cứu/backtest làm được đầy đủ**; sống hay chết là ở **cost-to-edge ratio**. [Quant Matter](https://quantmatter.com/retail-algorithmic-trading/), [Quantt](https://www.quantt.co.uk/resources/statistical-arbitrage-guide)
- Mean-reversion tần suất cao = nhiều trade × lợi nhuận nhỏ mỗi trade → "nếu cost cao thì cost ăn sạch alpha" là mode chết phổ biến nhất được ghi nhận. Điều này **trùng khớp với gate đã pre-commit của ta: edge ≥ 2× cost**.
- Những con số Sharpe 3–8 trong backtest công khai đều thiếu cost model tử tế hoặc ở thị trường khác (crypto) — **không lấy làm kỳ vọng.**

## 7. Kỳ vọng hiệu năng thực tế

- Mốc tham chiếu trung thực nhất: Avellaneda-Lee **Sharpe 1.44 net** ở thời hoàng kim 1997–2007, **suy giảm sau đó** vì crowding — thị trường 2015+ cạnh tranh hơn nhiều.
- Backtest intraday công khai (Sharpe ~3) = lạc quan do thiếu cost. Kỳ vọng hợp lý cho ta: **nếu net edge dương và giữ được sau lag 1 bar đã là kết quả đáng giá**; con số Sharpe tuyệt đối trong backtest chưa nói lên gì cho tới khi cost per-bar thật (Week 5) được tính đủ.

## Ý nghĩa cho thiết kế engine của ta

1. Tín hiệu nên là **residual reversion** (theo cặp hoặc theo factor) với cửa sổ ước lượng dài (ngày–tháng), tín hiệu tính trên bar phút — không phải "cointegration daily thu nhỏ".
2. Quyết định overnight/flatten nên **đợi đo half-life thực tế** trên data của ta — đó là số liệu quyết định, chưa nên chốt trước.
3. Intensity score của Sam có nền tảng (Cartea–Jaimungal); fill-sim L1 phải khai báo caveat lạc quan (queue + adverse selection).
4. Risk control tối thiểu ngay từ v0: bỏ 15–30 phút đầu phiên, flatten/không-vào-lệnh gần close, stop cấp cặp, cap số cặp.
5. Cost per-bar từ spread thật Week 5 là **linh hồn của backtest** — mọi kết quả gross đều vô nghĩa ở thang này.
