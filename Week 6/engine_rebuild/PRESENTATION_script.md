# PRESENTATION — "Fake Money, Real Lessons" (final script v1, 2026-07-24)

**Audience:** Sam (mentor) · **Language:** English, zero jargon (mọi khái niệm có ví dụ đời thường; bp → $ trên mỗi $1.000/$10.000) · **Length:** 9 slides ≈ 13'20 (trần 15') · **Tone:** dry, tự trào, số thật.
**Đây là nguồn duy nhất để generate deck HTML** (speech = speaker notes từng slide; load skill dataviz trước khi vẽ chart). Nguồn số liệu từng con số: xem `PROMPT_presentation.md` + memory `week6_*`.

*[Ngoặc vuông in nghiêng] = chỉ dẫn sân khấu, không đọc.*

---

## S1 — Fake Money, Real Lessons *(~20s)*

**On slide:** Title + subtitle: *"The receipt for our robot's $458 tuition."*

**Speech:**
Hi Sam. Today I want to show you what I got for four hundred and fifty-eight dollars — of fake money. My trading robot lost it, honestly and in public. This talk is the receipt: what that loss actually paid for.

## S2 — The Honest Scoreboard *(~1')*

**On slide:**
- Robot watches ~500 US stocks, finds "twins" (like Google's two share classes), bets on the hug.
- Live with pretend money since May 25. Score today: **−$458**.
- On data it had never seen: **all three versions lose** — when the safety switch is off.
- **Finding #0: the edge itself is not the product.** (Only P&L slide in the deck.)

**Speech:**
First, the confession. I built a robot that watches about five hundred US stocks and looks for twins — stocks that normally move together, like Google's two share classes. When the twins drift apart, the robot bets they'll hug again. Since May twenty-fifth, it has been trading live with pretend money — real market, fake dollars. The score today: *[point at the red number]* minus four hundred and fifty-eight.

And it gets worse. When I tested the strategy on data it had never seen before, all three versions of it lost money — as long as its safety switch was off. Remember that switch; it comes back later.

So, finding number zero: the trading edge itself is not the product. This is the only slide about profit and loss, and it's red. Everything from here on is what that red number bought.

## S3 — What the $458 Bought *(~40s)*

**On slide:**
- **A ruler** — what trading *really* costs, measured with real orders.
- **A graveyard map** — 15 ideas tested, killed, labeled.
- **A switch** — the money was never in picking trades; it was in knowing when *not* to trade.
- House rule: **the pass/fail line is written down BEFORE every test runs.**

**Speech:**
So what did it buy? Three things — and none of them depend on this particular robot.

First, a **ruler**: I measured what trading really costs, with real orders, instead of trusting assumptions. Second, a **graveyard map**: fifteen ideas tested, killed, and labeled, so nobody has to pay to learn them twice. And third, a **switch**: proof that the money was never in picking trades — it was in knowing when *not* to trade.

One house rule sits behind all three: the pass-or-fail line is written down *before* every test runs. That way, I can't move the goalposts after seeing the result.

## S4 — The Ruler ①: 253 Real Orders, Like Sonar Pings *(~1'30)*

**On slide:**
- Experiment: 253 small **real** orders through the robot's own pipes.
- **Impatience costs, patience pays:** now → 100% filled, ~1.3s, pay ~**15¢ per $1,000** · wait → 60% filled, ~17s, **get paid ~19¢ per $1,000**.
- **The free price feed lies:** ~1 in 5 quotes stale/junk.
- Changed: simulator runs on **measured** prices; junk quotes filtered out.

**Speech:**
Let's start with the ruler. Here's the problem it solves: every trading idea looks great until you subtract costs — and most people *guess* their costs. I didn't want to guess. So I ran an experiment: two hundred and fifty-three small, real orders, fired through the exact same pipes my robot uses. Think of them as sonar pings — you send them out just to see what bounces back.

Two findings. First: impatience costs money, and patience gets paid. If you demand your trade *right now*, you always get it, in about one second — and it costs you about fifteen cents for every thousand dollars traded. But if you're willing to wait in line, you only get your trade sixty percent of the time, after about seventeen seconds — and the market actually *pays you* about nineteen cents per thousand. The market tips patient people.

Second finding: the free price feed lies. Roughly one in five price quotes was stale or junk — like a menu where twenty percent of the prices are from last year.

So what changed? The robot's practice simulator now runs on these *measured* prices instead of assumptions, and junk quotes get thrown out before any decision is made.

## S5 — We Budgeted a $20 Toll. The Real Toll Is $6. *(~2')*

**On slide:**
- Backtest charged itself ~**$20 per $10,000** per round trip. Measured: ~**$6**. Overcharged 3× → old "too expensive" verdicts being re-scored.
- **Time of day has a price tag:** 9:30 open ≈ $4.50 per $10k · 3:30pm ≈ 90¢ — **5× cheaper**. *"The open is Black Friday; the close is a quiet Tuesday."*
- Tested the obvious fix — "shop at 3:30" — **it LOST**: prices drift while you wait; drift eats the discount. Killed same week.
- The robot shops at the open — now a **measured decision**, not a habit.

**Speech:**
Now, the second thing the ruler caught — and this one is a little embarrassing. All along, my rehearsal system — the backtest, basically a replay of the past — had been charging itself about twenty dollars in trading costs for every ten thousand dollars of buying and selling. The measured reality? About six dollars. In other words, I had been overcharging myself three times over. And that matters, because some ideas I rejected as "too expensive to trade" were judged with the wrong price tag. Those verdicts are being re-scored right now, with the real bill.

The ruler also found something nice: time of day has a price tag. Trading right at the open — nine thirty in the morning — costs about four dollars fifty per ten thousand. The same trade at three thirty in the afternoon: about ninety cents. Five times cheaper. The open is Black Friday; the close is a quiet Tuesday.

So, naturally, I tested the obvious improvement: shop at three thirty! And it *lost*. Because while you wait all day for the discount, prices drift away from you — and on average, that drift eats more than the discount saves. It's like driving across town to save on gas, and burning more gas on the way. I killed the idea the same week, with real data.

And here's the part I like: the robot already trades at the open. But now that's not a habit — it's a measured decision.

## S6 — The Graveyard: 15 Ideas Killed On Purpose *(~2'20)*

**On slide:**
- Every tombstone: **epitaph written before the funeral** (test + pass line pre-registered).
- *Ride month to month:* −**$18.50 of every $100** over 3 years. Killed.
- *Smaller moves, more trades:* −**$5,500** across 2,336 trades **even if trading were free**. Killed.
- *Smarter order tricks* (your idea 🙂): worth **$178 / 4 months** — one nice dinner per quarter. Closed with a number.
- *Trade the minute scale* (3 attempts): entry ticket > maximum prize. Died at the door — but built the ruler.
- **Bonus finding: twins hug back in DAYS, not minutes** — faster trading just pays more tolls; the robot thinks in days on purpose.
- Declared blind spot: survivor-only history (WWII bomber problem) — could cost extra **$4–7 per $100** in a bank panic. Declared & capped.
- Full 15-row list → appendix. Two graves are brand new (this week) — saved for the end.

**Speech:**
Which brings us to the graveyard. Fifteen ideas are buried here, and every one of them had its epitaph written *before* the funeral — meaning: I wrote down the test and the pass line first, then ran it, then accepted the answer. Let me give you the quick tour of the expensive ones.

"Let positions ride month to month instead of resetting." Over the full three-year replay, that lost eighteen dollars and fifty cents out of every hundred. Killed.

"React to smaller moves and trade more often." That one lost five and a half thousand dollars across more than two thousand trades — *even if trading were completely free*. No discount can rescue a strategy that loses before fees. Killed.

"Use smarter order tricks." That was actually your suggestion, Sam — so it got the full treatment. Measured worth: one hundred and seventy-eight dollars per four months. That's one nice dinner per quarter. Closed — with a number, not an opinion.

"Trade at the minute scale." Three separate attempts. Each time, the entry ticket cost more than the maximum prize. All three died at the door — but checking that door is exactly what produced the ruler you just saw. Nothing was wasted.

And the minute-scale deaths taught us something positive, too: we measured how fast the twins actually hug back — and the answer is days, not minutes. Trading faster doesn't catch more hugs; it just pays more tolls. That's why the robot thinks in days — on purpose, not by default.

And one blind spot I'll declare myself: my historical data only contains companies that *survived* — the World War Two bomber problem: you only study the planes that made it home. In a bank-panic year, that blind spot could cost an extra four to seven dollars per hundred. It's declared, and capped, but it can't be fully fixed.

The full list of all fifteen, with numbers, is in the appendix. And notice — two of these graves are brand new, dug just this week. They belong to the story of the switch, so I'm saving them for the end.

## S7 — The Switch: Where the Money Actually Was *(~1'30)*

**On slide:**
- Same robot, same signals ± one **market-health switch** ("don't trade this month").
- Switch OFF: all three versions lose **$2–$9 of every $100** (unseen data). Switch ON: worst flips to **+50¢ per $100**, much calmer ride. *(for quants: monthly Sharpe +1.01)*
- **The big finding: the money was in the OFF switch** — knowing when to sit out beat knowing what to buy.

**Speech:**
Now for the punchline of the whole project. Remember the safety switch from the beginning? Same robot, same signals, one difference: a market-health switch that's allowed to say, "don't trade this month."

With the switch off, all three versions of the strategy lose money — between two and nine dollars of every hundred, on data they had never seen. With the switch on, the worst of them flips from a two-dollar loss into a small gain — about fifty cents per hundred — and the ride gets much calmer. For the quants in the room, that's the monthly Sharpe ratio — the calmness score — improving by a full point. For everyone else: same robot, fewer sleepless nights.

And that's the big finding. I spent months polishing the *signal* — the part that picks trades. The money was in the *off switch* the whole time. Knowing when to sit out beat knowing what to buy. Risk control wasn't the boring chapter I had to write — it turned out to be the whole book.

## S8 — The Switch Is Annoying — and There's a Bounty on Its Head *(~1'15)*

**On slide:**
- The switch is a **nervous smoke alarm**: 2026 replay → shut down **3 of 4 months**, dodged ~$600 of losses, canceled ~**$13,300** of gains. *It stops the fire — and cancels the barbecue.*
- 3 bad habits: all-or-nothing (no dimmer) · thinks in whole months (slow) · slow to say "all clear."
- **Bounty on its head:** the $13,300 is the prize. Any challenger must beat a bar **written down before it runs**.

**Speech:**
But I have to be honest about the switch too — honesty is the brand here. My switch is a nervous smoke alarm. In a replay of early twenty twenty-six, it shut the robot down three months out of four. That dodged about six hundred dollars of losses… and canceled about thirteen thousand dollars of gains. It stops the fire — and cancels the barbecue.

Its three bad habits, in plain words: it's all-or-nothing — no dimmer; it thinks in whole months, so it reacts slowly; and once it panics, it takes too long to say "all clear."

So there is now a bounty on this alarm's head: those thirteen thousand canceled dollars are the prize. Any smarter alarm that wants the job has to beat the old one — against a bar that's written down *before* it runs. Same house rule as everything else. And how that contest is going… is exactly where I want to end.

## S9 — The Ask *(~1'30)*

**On slide:**
- **Alpha spoils. Rulers appreciate.** Every future strategy pays the same tolls — measurements get reused forever. This ruler already changed two decisions.
- **The graveyard compounds:** 15 pre-registered kills; every future test joins the map. Honest negative results — nobody will sell you these.
- **The alarm's upside has a price tag:** ~$13,300 / 4 replayed months. This week **two challengers died** chasing it — one by **$31**. *The bar was the bar.* The ceiling stands.
- **The ask:** 1 hour when the next verdict lands · **$99** (one month of professional-grade price data) · an introduction or two.
- **PAID: $458 (fake). FOR SALE: everything it taught us.**

**Speech:**
So — why should any of this earn your next hour, or your next dollar? Three reasons.

First: alpha spoils. Any edge starts rotting the moment the market notices it. But a ruler appreciates — every future strategy, mine or yours, walks through the same door and pays the same tolls, so the measurements get reused forever. And this ruler already paid for itself: it caught me overcharging myself three-to-one, and it reversed one "obvious" improvement before that mistake cost real money. A tool that changes decisions has a return; an opinion doesn't.

Second: the graveyard compounds. Fifteen honest kills now — each with its test written down in advance — and every experiment from here joins the same map. Honest negative results are the one kind of research nobody will ever sell you.

Third: the alarm's upside has a price tag. The nervous alarm left about thirteen thousand dollars on the table in just four replayed months. That's a measured ceiling — and this week, two challengers died chasing it, one of them by thirty-one dollars, because the bar was the bar. The ceiling still stands. The next attempt will have its pass-or-fail line on paper before it runs — like everything else here.

So the ask is small. One hour of your time when that next verdict lands. Ninety-nine dollars — one month of professional-grade price data — to upgrade the ruler from practice-grade to production-grade. And if the process has earned your trust… an introduction or two.

Paid: four hundred and fifty-eight dollars, fake. For sale: everything it taught us. Thank you, Sam.

---

# APPENDIX (backup slides — dựng khi generate deck)

- **B1 — Full kill-list, 15 rows** (số + file path từng dòng). Hai bia mới: **JM detector** — *"a fancier smoke detector — but this year's fire had no smoke"* (rớt luật (a) 0/4, bền qua λ; corr-crash với index êm) · **Dampener (the dimmer)** — *"lost by $31 — the bar was the bar."*
- **B2 — Probe methodology:** cách bắn 253 lệnh, lọc 15–23% quote rác.
- **B3 — Cost-by-hour map** đầy đủ + nguồn L1 spread thật (Week 5, row-aligned).
- **B4 — Survivorship crash-test** (kịch bản SVB; + SVB month net-long banks +28% mà switch không thấy).
- **B5 — Numbers ledger:** mọi con số trong deck → file nguồn.
- **Parked cho Q&A** (user quyết không nói thành tiếng): live chưa cắm regime filter (fix #1, $0); corr-crash "fire with no smoke"; −$888→−$458 broker-truth; DELL_PYPL −$292 earnings gap; Kalman "fancy steering wheel"; HKS tuyệt chủng; twins churn ~12%/tháng, formation tối thiểu 12 tháng.

**Việc còn lại:** (1) generate deck HTML (Artifact, load dataviz; 3 chart đinh: scorecard speed-vs-patience, bar phí theo giờ, cột đỏ/xanh của switch; speech nhúng speaker notes) — chờ user gật; (2) bộ Q&A — user hoãn, tính sau.
