# Pairs Trading Engine & Backtest

A statistical arbitrage pipeline built end to end between March and July 2026, and the
evidence that it does not work. **The headline result is negative twice over.** The 2022
cointegration screen produced zero tradable pairs. The one configuration that later did
report a profit was traced, by me, back to an arithmetic artifact and withdrawn.

The pipeline is the point: raw data ingestion, pair discovery, signal generation, a
backtest engine with look-ahead bias injected on purpose to measure how much it inflates
Sharpe, a friction model, a live paper-trading deployment on Alpaca, and an audit trail
that ends by retracting the project's own best number.

## Corrections

Earlier versions of this README carried figures that do not survive their own source files.
They are listed here rather than quietly deleted, because the corrections are a large part
of what this repository is for. The full audit is in
[`Week 6/documents/log.md`](Week%206/documents/log.md).

| Withdrawn claim | What is true |
|---|---|
| "Static OLS β drifts by 25.5%" | Withdrawn, not corrected. No denominator in the source run produces 25.5%, the figure was typed into markdown rather than computed, it describes a single pair (CMS/DUK), and most of the divergence was already present at the end of the formation window, so it is not drift during trading. |
| "20 flawed datasets", "5 contamination levels" | 24 datasets, 6 contamination levels. |
| "45-fold walk-forward" | 45 folds were configured; **25** produced results. |
| "213M-row limit order book" | A 213M-row minute-level L1 quote panel over 526 tickers, **constructed here** from close prices plus a modelled spread series. There is no vendor order book in this repository, and the L2/L3 columns are synthetic: `bid_sz == ask_sz` in 100% of rows, and the L2 spread is exactly twice the L1 spread. |
| "2-D Kalman filter with auto-selected δ" | The δ selector exists but never runs. `run_final_pipeline.py` sets `FIXED_DELTA = 1e-7`, which reduces the filter to a static spread. |
| "intentional 5-minute API disconnect" | `test_disconnect_5min.py` is five `NotImplementedError` stubs. The drill that does exist simulates the disconnect by manipulating stream state directly and prints `SIMULATED`; no network is involved. |
| H4 normalization leak is "nearly impossible to detect" | It is the easiest of the four to detect. Z-scoring the close column drives roughly 47% of prices negative, and the crudest OHLC consistency check flags it at all six contamination levels. |
| Week 6 is an "architecture specification phase" | The engine traded live on Alpaca paper from 2026-05-28 and lost money. It has since been stopped. |

## Quickstart

**The scan cannot be re-run from this repository.** The raw 1-minute price panel is
several gigabytes and is not committed, so the cointegration screen has no input here.
Saying so is cheaper than shipping a command that fails.

What is committed, and what to read instead:

| Where | What it shows |
|---|---|
| [`Week 6/documents/log.md`](Week%206/documents/log.md) | The decisive document. Supersedes the Week 4 whitepaper and every week README where they disagree. |
| [`Week 1/Week1_Pairs_Selection_Report.ipynb`](Week%201/Week1_Pairs_Selection_Report.ipynb) | The pair-discovery write-up: the filter funnel and the zero survivors at the end of it. Markdown only, no saved cell outputs. |
| [`Week 3/`](Week%203/) | The look-ahead bias study: injection scripts and run logs |
| [`Week 4/results/`](Week%204/results/) | The walk-forward output, 25 of 45 folds. The whitepaper there opens with a retraction notice. |
| [`Week 6/`](Week%206/) | The live paper-trading engine, cost model, and the audits that took the strategy apart |

Every week folder has its own README describing what was built and what it found.

---

## Pipeline Architecture

```
Week 0             Week 1            Week 2           Week 3             Week 4          Week 5          Week 6
The Crash    →  The Foundation  →  The Signal  →  The Verification →  The Defense  →  The Friction →  Going Live
──────────      ──────────────     ───────────    ────────────────    ───────────     ────────────    ──────────
1987 Break       Universe &         Z-Score        Backtest Engine     Multi-Regime    Cost Model      Paper Trading
Detection        Pair Discovery     Signal Engine  + Bias Injection    Walk-Forward    (Friction)      + Self-Audit
```

---

## Weekly Progression

### [Week 0 — Crash Autopsy 1987](Week%200/)
Multivariate PELT changepoint detection on 1-minute S&P 500 futures across October 16–21,
1987, run on three microstructure dysfunction features: staleness, lag-1 return
autocorrelation, and jump share. Halted sessions are skipped rather than forward-filled.
A parallel strategy track reads the Brady Report, the CFTC final report, and Shiller's NBER
chapter to work out how portfolio insurance turned a decline into a cascade.

**Key finding:** The structural break lands at 09:42 on October 19, eight minutes into the
crash, and the 15-minute and 30-minute windows agree to within one minute. The write-up
states what the data cannot support: with futures prices alone there is no way to measure
the cash basis, spreads, or volume.

---

### [Week 1 — Pair Discovery & Universe Construction](Week%201/)
Build a log-transformed 5-minute price panel from raw 1-minute OHLCV, screen the universe
through liquidity and quality filters, and run an all-pairs Engle-Granger cointegration
scan with Benjamini-Hochberg false-discovery control. 509 tickers were pulled, 254 survived
the filters, giving **32,131 pairs** tested.

**Key finding: zero pairs survived** — at q=0.05, and also at the relaxed q=0.10 fallback
tier the code runs automatically when the strict tier empties. The smallest adjusted
p-value across all 32,131 pairs is 0.198. Dropping the five ETFs and rescanning still
returns zero. `approved_pairs.parquet` is a real, empty table.

One caveat the universe carries: 187 of 192 tickers were dropped because the January
download truncated at the letter N. The 254-name universe is partly a consequence of a
data-fetch bug, not only of design.

---

### [Week 2 — Z-Score Signal Engine](Week%202/)
Translate spreads into positions: a Numba-compiled state machine for path-dependent
position tracking, and rolling z-score normalization with half-life-derived windows.

**Key finding:** this week has the strongest test suite in the repository, 40 tests
including two that check for look-ahead directly, asserting that a future bar cannot move a
past score and that rolling statistics read only past values. The hedge-ratio work here was
labelled a Kalman filter; Week 6 established that the production path fixes δ at 1e-7,
which makes the estimated spread static. The name was wrong, and the earlier "25.5% drift"
figure built on it has been withdrawn.

There is no stop-loss and no position sizing in this week's code. Both arrive in Week 6.

---

### [Week 3 — Bias Injection & Data Integrity](Week%203/)
Inject four classes of look-ahead bias (future-close leakage, timestamp backdating,
spread-level contamination, full-sample normalization) into **24 corrupted datasets** across
**6 contamination levels**, then run each through a verified backtest engine with daily
mark-to-market P&L and negative-control pairs.

**Key finding, and the limit of it:** the audit flags 24 of 24, but it detects *traces of
injection*, not bias. Its four checks are OHLC consistency, duplicate timestamps,
out-of-session timestamps, and column naming. Nothing recomputes a value from source or
compares against a clean copy, so H3 is caught only because the injected column is named
`spread_biased`; renaming it to `close` would pass all four. That limitation is written into
the deliverable rather than left for a reader to find.

Second finding, from the zero-cost column, which is the honest place to look because
friction is a drag independent of signal quality: only H1 raises Sharpe. H2, H3 and H4 all
lower it.

---

### [Week 4 — Multi-Regime Defense, and its retraction](Week%204/)
Johansen cointegration with PCA hedge ratios, a monthly rolling walk-forward across
2022–2026, sensitivity analysis and overfitting diagnostics, written up as a strategy
whitepaper. 45 folds were configured and **25 produced results**, reporting a **mean fold
Sharpe of +0.995**.

**Key finding: the headline does not survive its own trade log, and Week 6 withdrew it.**

- Median fold Sharpe is **+0.000**, and 48% of folds are positive.
- Sharpe was annualized from exit-date observations only, between 3 and 21 days per fold.
  The correlation between a fold's observation count and its Sharpe is −0.417, so the
  headline is produced by the folds that traded least. A sibling configuration reports mean
  Sharpe +1.706 while losing 17.65% of capital.
- Across all 90 trades the real compounded return is **+3.01% over 3.66 years**, and three
  trades in April 2025 account for **128%** of net P&L. Remove them and the strategy loses
  money. No total-return figure appears anywhere in the original deliverables.
- Those three trades come from an unbounded hedge ratio. There is no cap on |β| anywhere in
  the Week 4 code; across Phase-1 pairs it ranges from −2,406 to +2,143. The largest winner
  ran at β = −24.04 with both legs long, which is a directional semiconductor bet booked as
  a market-neutral pair.
- The economic-logic filter Week 1 applied (β > 0, same GICS sector) was dropped here.
  Trades with β < 0 are 16.7% of the log and carry 90.1% of the profit. Under Week 1's own
  rules they would not exist.

The whitepaper is kept in place, with a retraction notice at the top, because the sequence
is the record.

---

### [Week 5 — Friction & Cost Modeling](Week%205/)
Replace the flat 60 bps cost assumption with a three-component model: empirical half-spread,
instability-scaled market impact, and borrow cost, calibrated against a **213M-row
minute-level L1 quote panel over 526 tickers**. That panel was constructed for this project
from close prices plus a modelled spread series; it is not vendor quote data, and its L2/L3
columns are synthetic.

**Key finding: costs are not what killed this strategy.** Modelled round-trip friction is
45.3 bps against the 90.9 bps a static assumption implies, so Week 4's assumption was
roughly twice as conservative as reality.

**And a correction that cost more than the cost model saved.** Week 4's reported Sharpe of
1.978 was computed on roughly 90 exit-date daily returns and then scaled by √252, inflating
it by about √(432/90) ≈ 2.2×. Rebuilt properly it is **0.5031 gross, 0.4428 net**. The
deflated-Sharpe trial count was also being set to the number of folds rather than the number
of variants tested; corrected, the DSR p-value goes to 0.0000 against an E[max SR] threshold
of 2.05, which is the strategy failing its own significance screen. The negative control
passes in only 8 of 22 folds, and this week's report names that as the most significant open
gap in the validation suite.

---

### [Week 6 — Live Deployment & Self-Audit](Week%206/)
Rebuild the engine (V3 intraday, then V4 daily), deploy it to Alpaca paper trading on
Render, and audit it against itself. This is where the project's conclusions actually live:
[`documents/log.md`](Week%206/documents/log.md).

**Key finding: the reported edge was an artifact of unbounded hedge ratios.** Auditing V4's
P&L back to source found **27 pairs with |β| between 50 and 2,708 generating 103% of total
P&L**. Capping |β| at 5 moves annualized Sharpe from **+0.66 to −0.45** and the summed return
from +248.6% to −6.6%. The log's own conclusion: no alpha on liquid S&P 500 names over
2023–2026 under realistic costs.

**Why it loses, with numbers.** A ten-test diagnostic found gross edge already negative
before costs. 75.2% of pairs lose cointegration during the very window they are traded in,
77% of pairs appear in only one fold, and 81% of trades are force-closed at month end before
they can revert; that group lost $565k while the 10% that did revert made $541k. The 21-day
trading window is shorter than the reversion the half-life filter admits.

**A regime filter that worked in backtest and failed live.** The best configuration reaches
+1.279 mean fold Sharpe, but only after halting 31% of months, of which 6 halts were right
and 6 were false alarms. Replayed against April–July 2026 the filter returned **−$1,189
where trading unfiltered returned +$11,304**.

**Live results.** First fill 2026-05-28. Week one: five trades, all closed at month end,
**−$313.05** on a $100,000 paper account. Running P&L to 2026-07-24: **−$457.99**, matching
the broker to eight cents after a multi-lifecycle P&L contamination bug was found and fixed.
Thirteen sessions were frozen from 2026-07-06 by a stale-reconcile halt. The engine has since
been stopped.

**Retracted here as well.** A regime improvement reported at +1.37 Sharpe was withdrawn after
two compounded look-ahead errors were found in it: a volatility input drawn from the month
being traded, and a quantile boundary fitted across the full sample. Rebuilt forward-only it
reaches +0.42, behind the +0.69 of not filtering at all. The log records that all prior
claims for it should be discarded.

---

## Technical Stack

- **Language:** Python 3.x
- **Core Libraries:** NumPy, pandas, SciPy, statsmodels, `ruptures` (PELT)
- **Performance:** Numba `@njit` for stateful execution loops
- **Data Format:** Apache Parquet
- **Statistical Methods:** Engle-Granger and Johansen cointegration, BH-FDR, PCA factor
  residuals, Ornstein-Uhlenbeck half-life, PELT changepoint detection, Deflated Sharpe
  Ratio, PBO
- **Live:** Alpaca paper trading (IEX), deployed on Render

A note on the Kalman filter, which appears throughout the Week 2 and Week 4 code and in
earlier descriptions of this project: the production path sets δ to a fixed 1e-7 and never
calls the selector, so the spread it produces is static. Week 6 renamed the module
accordingly. Treat any Kalman result in the earlier weeks as a static-spread result.

---

## Repository Structure

```
Pairs Trading Strategy/
├── Week 0/         # Crash Autopsy 1987
├── Week 1/         # Pair Discovery & Universe Construction
├── Week 2/         # Z-Score Signal Engine
├── Week 3/         # Bias Injection & Data Integrity
├── Week 4/         # Multi-Regime Defense, and its retraction
├── Week 5/         # Friction & Cost Modeling
├── Week 6/         # Live Deployment & Self-Audit
├── trading_1min/   # 1-minute execution simulator and lead-lag scan
├── Readings/       # Reference literature
└── .gitignore
```

Week folders are numbered in the order the work happened and are deliberately not renamed.
Week 4 publishes a positive result and Week 6 proves it was an artifact; that is only
readable as a sequence.

> **Note:** Large datasets (`data/`, `Big Dataset/`, `*.parquet`, `*.csv`) are excluded from
> version control via `.gitignore`.
