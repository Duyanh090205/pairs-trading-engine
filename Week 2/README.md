# Week 2 — Z-Score Signal Engine

**Theme:** The Signal.

> **Correction notice.** Some figures on this page were withdrawn after later checking.
> The list of what was withdrawn and why is in the [root README](../README.md#corrections),
> and the current conclusions are in [`Week 6/documents/log.md`](../Week%206/documents/log.md).


## Objective

Build a vectorized, stateful Z-score signal engine that translates cointegrated spreads into actionable entry/exit signals, validated on candidate pairs from Week 1.

## Deliverable

A **Signal Logic Document** specifying the complete rules of engagement: spread construction, Z-score normalization, state machine logic, threshold selection, and execution conventions — ready for the backtest engine in Week 3.

## Scope

- Construct log-price spreads using OLS hedge ratios estimated on the formation period (Jan–Jun 2022).
- Implement a rolling Z-score engine with half-life-derived window sizes.
- Build a Numba-compiled state machine for path-dependent position tracking.
- Validate signal behavior through distribution diagnostics, threshold sensitivity, and rolling regime monitoring.
- Introduce a Rolling Kalman Filter for dynamic hedge ratio estimation (sizing upgrade for
  Week 3+). See the correction notice above on what this estimator turned out to be.

> **Important:** This week is strictly for signal generation and trade timing validation. It is *not* a profitability backtest. Transaction costs, stop-losses, and overnight gap handling are deferred to Week 3.

## Data

- **Source:** Same 1-minute OHLCV data as Week 1 (`close` column, nanosecond epoch timestamps).
- **Formation Period:** Jan–Jun 2022 → hedge ratio, half-life, Hurst, quantile thresholds.
- **Trading Period:** Jul–Dec 2022 → Z-scores, signals, all evaluation.
- **Pairs:** Primary (CMS/DUK, EG t = −5.268) + Secondary (DOW/LYB, EG t = −4.861) from Week 1 near-misses.

## Method

### Spread & Z-Score Construction
- **Spread:** `S(t) = ln(A_t) − α − β·ln(B_t)`, with α and β from formation-period OLS.
- **Rolling Z-Score:** Window = OU half-life (clamped to [10, 2000] bars), burn-in = window//2, ddof = 1.
- **Session Warmup:** First 30 bars per session forced to NaN.

### State Machine (Numba @njit)
- **Entry:** Z < −2.0 → LONG spread | Z > +2.0 → SHORT spread.
- **Exit:** Z crosses 0.0 → FLAT.
- **NaN-Safety:** `fastmath=False`; NaN Z-scores hold current state without triggering orders.
- **Execution Lag:** `position_executed[t] = position[t−1]` (lookahead prevention for Week 3 PnL).

### Diagnostics
- Empirical coverage table (±1σ through ±3σ vs. Normal theory).
- QQ-plot, skewness, excess kurtosis.
- Cross-pair comparison (β, half-life, Hurst, trade count).
- Threshold sensitivity sweep: fixed ±2.0 vs. adaptive (|Z| 95th percentile from formation).
- Rolling Hurst exponent for regime monitoring.
- Kalman Filter analysis, as originally reported: a 25.5% static β drift motivating dynamic
  rebalancing. **Withdrawn.** The percentage was typed into markdown rather than computed, no
  denominator in the source run reproduces it, it covers a single pair, and most of the
  divergence was already present at the end of the formation window. Week 6 also established
  that the production path fixes δ at 1e-7, which makes this a static spread, not a Kalman one.

## Directory Structure

```
Week 2/
├── week2_signal_engine/
│   ├── src/              # Core signal engine modules
│   ├── configs/          # Run parameters
│   ├── scripts/          # Pipeline execution
│   ├── tests/            # Unit tests
│   ├── docs/             # Methodology + Signal Logic Document
│   └── outputs/          # Diagnostic figures and tables
├── research/             # Mathematical foundations, plan documents
└── readings/             # Reference literature
```
