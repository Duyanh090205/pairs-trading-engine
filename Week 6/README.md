# Week 6 — V3.0 Engine Scaffold

**Theme:** Fix the patchwork. Make the engine tell *one* story before going live.

## Thesis

> Trade idiosyncratic mean reversion on factor-residual spreads, only when no factor
> momentum is leading, with a real safety net if reversion fails.

V2.0 (Week 4 + Week 5) was diagnosed by deep review as a **patchwork research artifact**:
misnamed Kalman (δ=1e-7 = static spread), no factor orthogonalization (16.7% β<0 trades
were silent factor exposure), kill zones traded anyway, no stop-loss in Late Bull regime,
Z-threshold optimized at the wrong cost level. V3.0 fixes the five integration failures
without inventing anything new — it's an honest re-implementation of Avellaneda-Lee 2010
factor-residual pairs trading with explicit safety nets.

## What V3.0 changes vs V2.0

| Tag | Change |
|---|---|
| R1–R3 | CORR25 filter removed (verified zero marginal effect) |
| R4    | Kalman wrapper replaced by explicit `static_spread.py` (honest naming) |
| R5    | β<0 pairs hard-filtered in discovery (V2.0 had 16.7% co-trending "pairs") |
| R6    | Redundant HL cap removed (single source: discovery [1, 6d]) |
| F1    | PCA factor model (5 components) projected out before Johansen |
| F2    | Z entry can be **Fixed / Vol-conditional / HL-conditional** (A/B tested) |
| F3    | HL filter consolidated at [1, 6d] |
| F4    | Static spread replaces Kalman (`compute_static_spread`) |
| A1    | Time-of-day mask — blocks entries 11:00–11:59 + 15:30–15:59 ET |
| A2    | Hard stop-loss at |Z|≥5.5, signed catastrophic widen direction |
| A3    | Z-velocity gate — blocks entry when |dZ/dt| ≥ 0.05 per bar |
| A4    | Vol-target sizing — $200/day per pair, $10k–$40k floor/cap |

Everything else (45-fold walk-forward, persistence gate, BH-FDR, per-ticker concentration
cap, Phase 3 metrics, Phase 4 defense, Week 5 cost overlay) is KEPT unchanged.

## Directory structure

```
Week 6/
├── engine/                              # V3.0 strategy code
│   ├── phase0_data_gateway/             # reused from Week 4
│   ├── phase1_cointegration/
│   │   ├── discovery.py                 # MODIFIED: factor_residual + β>0 + HL=6d
│   │   └── factor_residual.py           # NEW (F1)
│   ├── phase2_execution/
│   │   ├── engine.py                    # MODIFIED: static spread, time-mask, hard SL, Z-velocity, vol-target, dynamic Z
│   │   └── static_spread.py             # NEW (F4)
│   ├── phase3_backtest/                 # reused from Week 4
│   ├── phase4_defense/                  # reused from Week 4
│   ├── utils/                           # reused from Week 4
│   ├── z_strategies.py                  # NEW (F2 — fixed/vol/hl router)
│   ├── z_sweep.py                       # NEW — fixed-Z grid sweep
│   ├── z_strategy_compare.py            # NEW — 3-way A/B
│   ├── run_diagnostics.py               # NEW — V2-vs-V3 reports
│   ├── delta_logger.py                  # NEW — per-step comparison CSV
│   └── smoke_tests/                     # NEW — 12 standalone assertion tests
├── cost/                                # Week 5 cost overlay (read-only reuse)
├── data/                                # symlinks to Week 4/5 sources
├── results/v3/                          # V3.0 backtest outputs
├── reports/                             # V3.0 reports
├── run_v3_pipeline.py                   # V3.0 entry point (rewritten)
└── README.md                            # this file
```

## Environment notes — cold-import latency on this Windows env

Cold-import wall times measured on this dev env (likely Windows Defender real-time
scanning every DLL):

| Module | Cold import | Notes |
|---|---|---|
| `sklearn` | 1241s (~21 min) | Removed entirely; `factor_residual.py` uses numpy SVD instead |
| `numba`   | 1257s (~21 min) | Made opt-in via `USE_NUMBA=1`; `_state_machine` runs as pure Python by default |
| `statsmodels.tsa` | 5-20+ min | Deferred to function scope in `discovery.py` and `run_v3_pipeline.py`; pays the cost on first Johansen call only |
| `pyarrow` (via pandas) | seconds | Fine after first call |

**Workaround used**: pure-numpy SVD for PCA, no-op `@njit` decorator fallback, deferred
statsmodels imports inside functions that need them. After these changes, the full
smoke suite (11 tests) runs in **~10 seconds**.

**For the user to truly fix**: add `D:\Quant Finance` and your Python install path
to Windows Defender exclusions, OR reinstall via conda (which often produces faster
imports than pip wheels on Windows).

```bash
# Example conda fix:
conda install -c conda-forge scipy statsmodels numba scikit-learn --force-reinstall
```

## How to run

```bash
# 1. Smoke test all 12 standalone modules
python -m engine.smoke_tests.run_all_smokes

# 2. Single-fold smoke run
python run_v3_pipeline.py --folds 1 --smoke

# 3. Full 45-fold backtest (default: fixed Z=3.5)
python run_v3_pipeline.py --folds all

# 4. Cost overlay (run after backtest)
python cost/plan2_backtester/orchestrator.py \
    --trade-log results/v3/trade_log.csv \
    --rebalance-log results/v3/rebalance_log.csv \
    --out results/v3/cost_log.parquet

# 5a. Fixed Z sweep (pick winning Z_base)
python engine/z_sweep.py --z-grid 3.0,3.25,3.5,3.75

# 5b. 3-way A/B at winning Z_base
python run_v3_pipeline.py --folds all --z-strategy fixed --z-base <winner>
python run_v3_pipeline.py --folds all --z-strategy vol   --z-base <winner>
python run_v3_pipeline.py --folds all --z-strategy hl    --z-base <winner>

# 5c. Compare
python engine/z_strategy_compare.py --z-base <winner>

# 6. Diagnostics + reports
python engine/run_diagnostics.py
```

## Go-live gates (must hit ALL before paper trading)

| # | Gate | Threshold |
|---|---|---|
| G1 | Net Sharpe (mean across 4 regimes) | ≥ 1.0 |
| G2 | Late Bull 2025–26 net Sharpe | ≥ 0 |
| G3 | Worst-fold MaxDD | ≥ −5% |
| G4 | n_trades total | ≥ 90 (V2.0 baseline) or written justification if lower |
| G5 | DSR p-value | ≤ 0.05 |
| G6 | β<0 trades in trade log | = 0 (R5 enforcement) |
| G7 | No single trade > 10% of any fold's gross P&L | strict |
| G8 | Zero entries in masked time windows | strict |
| G9 | Cost overlay schema validation | True |
| G10 | All 12 smoke tests pass | exit 0 |

## Known limitations (FLAG, not fix)

These are documented gaps. V3.0 ships with them; future weeks may address.

1. **Survivorship bias.** Universe = current S&P 500 (~528 tickers). ~40–60 names
   removed during 2022–2026 (SIVB, FRC, ATVI, SPLK, PXD, etc.) are absent from the
   data. Expected Sharpe inflation: 0.1–0.3. The hard SL (A2) partially caps the
   worst-case scenario this bias hides (e.g., March 2023 regional bank co-collapse).

2. **Latency convention.** Decide-at-close, fill-at-close — aggressive vs realistic
   50–200ms latency. Deferred to Week 7+.

3. **10:00–10:30 concentration risk.** V2.0 had 68% of trades in this 30-min window.
   V3.0 inherits this. Risk: liquidity regime change at NYSE open wipes 68% of alpha.

4. **DSR n_trials accounting.** Effective n ≈ 7 (fixed-Z sweep 4 + V3 architecture 1
   + vol-conditional 1 + HL-conditional 1). With ~4.25 years of data, this is
   borderline — see `reports/v3_dsr_pbo.md` after running diagnostics.

## What V3.0 is NOT

- Not a new pipeline. ~70% is standard Avellaneda-Lee, ~25% is V2.0 engineering kept
  intact, ~5% is honest re-naming. The novelty is *integration coherence*, not method.
- Not point-in-time. Universe is today's S&P 500; bias flagged above.
- Not live. Broker integration, paper trading dashboard, drift monitor, and live
  factor exposure monitor are deferred to Week 7+, contingent on V3.0 backtest
  clearing all 10 go-live gates.

## Status

Scaffold + modifications complete. Pending: smoke test verification, single-fold smoke
run, full 45-fold backtest, A/B test, diagnostics. Then evaluate against go-live gates.

For the full plan (audit findings, per-function hard stops, per-step deltas), see
`C:\Users\nguye\.claude\plans\oke-now-pull-me-piped-hopcroft.md`.
