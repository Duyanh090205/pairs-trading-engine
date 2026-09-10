# Week 5 — Microstructure Reality (Net-of-Fees Backtest)

**Theme:** The Friction.

> **Correction notice.** Some figures on this page were withdrawn after later checking.
> The list of what was withdrawn and why is in the [root README](../README.md#corrections),
> and the current conclusions are in [`Week 6/documents/log.md`](../Week%206/documents/log.md).


## Objective

Determine whether the Week 4 strategy's alpha survives when the static 60 bps cost assumption is replaced with empirical bid-ask spreads that widen during spread instability. Does alpha survive — or was it an illusion eaten by friction?

## Deliverable

A **Net-of-Fees Performance Report** presenting side-by-side comparisons across three cost regimes (Gross, Static 60 bps, Dynamic), with cost decomposition waterfalls, regime-conditional analysis, kill-zone identification, and overfitting diagnostics on net returns.

## Scope

This week **measures** friction on the existing strategy. We do **NOT** modify the strategy itself (no sizing changes, no new entry/exit gates, no regime suppression). Same signals, same positions — different cost model.

The pipeline is structured as four plans:
- **Plan 0 — Data Gateway:** Orderbook ingestion, spread extraction, rolling instability computation.
- **Plan 1 — Cost Model:** Three-component dynamic cost function (spread + impact + borrow).
- **Plan 2 — Cost Application:** Per-trade post-processing pass over Week 4's trade log (no re-execution).
- **Plan 3 — Validation & Report:** 11-section performance report with diagnostics.

## Data

| Property | Value |
|---|---|
| **File** | `orderbook.parquet` |
| **Total Rows** | 212,975,144 |
| **Frequency** | 1-minute (dominant; some 2–5 min gaps) |
| **Tickers** | 504 (2022-01) → 526 (2026-03) |
| **Date Range** | 2022-01-03 09:00 → 2026-03-19 23:59 |
| **Structure** | 3 quote levels (L1/L2/L3 bid/ask price + size). **Not a vendor order book** — see the data-provenance note below. |
| **L1 Spread** | Universe median ~10 bps; SPY ~4.7 bps; max > 150 bps (stress) |
| **Provenance** | Constructed for this project from close prices plus a modelled spread series |

**Data provenance, and the limits it puts on this week.** This panel was built for the project
rather than bought: L1 quotes are reconstructed from close prices plus a modelled spread
series, and the deeper levels are generated from L1. It is not measured market microstructure,
and nothing here should be described as such.

The generated structure is visible in the file. `bid_sz == ask_sz` in 100% of rows at every
level, the L2 spread is exactly twice the L1 spread, L3 sits on a few discrete multiples, and
the L1 mid equals the close to within 1e-6 in 82.3% of AAPL bars. No order-flow imbalance
signal can be derived from it, and the cost model below should be read as a spread *model*
calibrated to a plausible spread series, not as an empirical measurement of what execution
would have cost.

## Method

### Three-Component Dynamic Cost Model

$$C_{total}(t) = C_{spread}(t) + C_{impact}(t) + C_{borrow}(t)$$

| Component | Formula | Description |
|-----------|---------|-------------|
| **Spread Cost** | `half_spread_l1_bps(t)` | From the modelled L1 series, varies per ticker per bar |
| **Market Impact** | `κ × spread_std_1d(t)` | Spread-instability-scaled; κ pre-assigned by liquidity tier |
| **Borrow Cost** | `(rate / 10,000) / 365 × short_notional` | Daily accrual on short leg (50 bps/yr default; calendar-day convention) |

### Impact Coefficient (κ) Tiers
| Tier | Median L1 Spread | κ |
|------|-----------------|---|
| Tight (< 8 bps) | SPY, AAPL, MSFT | 0.3 |
| Medium (8–20 bps) | Most S&P 500 | 0.5 |
| Wide (> 20 bps) | VTRS, T, UBER | 0.8 |

### Report Sections
1. Executive Summary (verdict)
2. Empirical Spread Profile (median, p95, p99 by tier and regime)
3. Slippage Model Specification
4. The Before/After Table (Sharpe Gross vs. Net across all three regimes)
5. Cost Waterfall (where gross alpha goes)
6. Regime-Conditional Costs (Bear vs. Bull)
7. Spread-Vol Correlation (empirical proof spreads widen with volatility)
8. Kill Zone + Intraday Seasonality (time-of-day net alpha heatmap)
9. Negative Control under Dynamic Costs
10. Overfitting Diagnostics on Net Returns (DSR/PBO)
11. OAT Sensitivity (κ, borrow rate, spread level)
12. Honest Verdict

## Directory Structure

```
Week 5/
├── src/
│   ├── plan0_gateway/      # Orderbook ingestion, spread extraction, rolling stats
│   ├── plan1_cost_model/   # Three-component cost model + interface contract
│   ├── plan2_backtester/   # Per-trade cost application over Week 4 trade log
│   └── plan3_validation/   # 11 validation/report modules
├── workflows/              # Pipeline specs, methodology docs
├── reports/                # Generated performance reports
├── run_pipeline.py         # Master pipeline orchestrator
└── data/                   # Microstructure artifacts (gitignored)
```
