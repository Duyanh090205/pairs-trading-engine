"""
build_v4_ledger.py — trade-level ledger for the V4 daily ship config
====================================================================

The V4 pipeline (`Week 6/scripts/run_v4_pipeline.py`) emits only FOLD-level
metrics (`results/v4/z30_composite/fold_metrics.csv`). There is no per-trade
file for the shipped config. This script reconstructs one, OFFLINE, by
reusing the exact production machinery — no live orders, no network.

Ship config (z30_composite), the command that produced fold_metrics.csv:
    run_v4_pipeline.py --folds all --use-dynamic-cost \
        --entry-z 3.0 --hard-sl-z 5.0 --use-composite-filter
  => entry_z=3.0, hard_sl_z=5.0, z_window=60, hl=[5, 30],
     dynamic cost ON, composite regime FILTER ON, no carry-forward, no sizer.

What it does (mirrors run_v4_pipeline.main() ship-config path):
    1. Load daily cache + Week 5 dynamic-cost data.
    2. Build composite regime features ONCE.
    3. For each selected fold: apply halt_for_fold (skip halted folds exactly
       as main() does), else run_fold_v4 with the ship config.
    4. Walk entry->exit transitions in each per-pair bar DataFrame (adapted
       from `Week 6/audits/audit_v4_negative_sharpe.py::_extract_trades`) and
       emit one row per trade.

Validation gate (smoke): per-fold n_trades and avg_net_bps reconstructed from
the ledger MUST match the existing fold_metrics.csv (folds 1-3).

    avg_net_bps definition (engine_daily/metrics_daily.py::aggregate_fold_metrics):
        total_net             = sum of net P&L over all traded pairs
        total_notional_traded = sum over pairs of n_trades * notional(pair)
        avg_net_bps           = total_net / total_notional_traded * 10000
    Reproduced from the ledger as:
        sum(net_pnl_backtest) / sum(2 * notional_per_leg) * 10000
    (per-pair notional == 2 * notional_per_leg; see engine_daily.py:313).

Data-path note: run_v4_pipeline.DATA_DAILY and cost_engine paths hardcode the
OLD repo name "Quant Program". The repo was renamed to "Pairs Trading
Strategy". This script checks .exists() and falls back to the new location,
reporting which path resolved.

CLI:
    python trading_1min/research/build_v4_ledger.py            # smoke: folds 1-3
    python trading_1min/research/build_v4_ledger.py --folds 1-5
"""

from __future__ import annotations

import os as _os

# Single-thread BLAS (determinism + Johansen LAPACK noise) — set BEFORE numpy.
for _var in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
             "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"):
    _os.environ[_var] = "1"

import argparse
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")   # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8")   # type: ignore[attr-defined]
except (AttributeError, Exception):
    pass

import numpy as np
import pandas as pd

# ---- Repo layout / import path wiring --------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]        # Pairs Trading Strategy
WEEK6 = REPO_ROOT / "Week 6"
sys.path.insert(0, str(WEEK6))                         # engine_daily, engine
sys.path.insert(0, str(WEEK6 / "scripts"))            # run_v4_pipeline

import run_v4_pipeline as v4
# Machinery reused from the production pipeline. run_fold_v4 internally uses
# _slice_daily / TOTAL_CAPITAL; DATA_DAILY is read via the `v4` module handle.
from run_v4_pipeline import FOLD_SCHEDULE, run_fold_v4, _load_all_daily
from engine_daily import cost_engine
from engine_daily.regime_detector import (
    build_features as regime_build_features,
    compute_stress_zscore,
    halt_for_fold,
)

OUT_DIR = REPO_ROOT / "trading_1min" / "results" / "v4_exec_sim"
OUT_PATH = OUT_DIR / "trades_z30_composite.csv"
FOLD_METRICS_REF = WEEK6 / "results" / "v4" / "z30_composite" / "fold_metrics.csv"

# ---- Ship config (z30_composite) -------------------------------------------
ENTRY_Z = 3.0
HARD_SL_Z = 5.0
Z_WINDOW = 60
HL_MIN = 5.0
HL_MAX = 30.0

LEDGER_COLS = [
    "fold", "trading_month", "pair_id", "ticker_a", "ticker_b",
    "entry_date", "exit_date", "eng_exit_date", "direction", "beta",
    "notional_per_leg", "entry_z", "exit_reason", "duration_bars",
    "duration_days", "gross_pnl_spread", "cost_backtest", "net_pnl_backtest",
]
DAILY_PNL_PATH = OUT_DIR / "daily_pnl_by_fold.csv"


# ============================================================================
# Path resolution (handle the "Quant Program" -> "Pairs Trading Strategy" rename)
# ============================================================================

def _resolve_paths() -> tuple[Path, Path, Path, dict[str, str]]:
    """Return (data_daily, cost_cache, cost_summary, report) using new-repo
    fallbacks when the hardcoded OLD 'Quant Program' paths are missing."""
    report: dict[str, str] = {}

    data_daily = v4.DATA_DAILY
    if not data_daily.exists():
        data_daily = REPO_ROOT / "Week 4" / "data" / "validated" / "daily_phase3"
        report["data_daily"] = f"FALLBACK -> {data_daily} (hardcoded OLD path missing)"
    else:
        report["data_daily"] = f"OK -> {data_daily} (hardcoded path resolved)"

    cost_cache = cost_engine._DEFAULT_CACHE
    if not cost_cache.exists():
        cost_cache = REPO_ROOT / "Week 6" / "cost" / "daily_spread_cache.parquet"
        report["cost_cache"] = f"FALLBACK -> {cost_cache} (hardcoded OLD path missing)"
    else:
        report["cost_cache"] = f"OK -> {cost_cache} (hardcoded path resolved)"

    cost_summary = cost_engine._WEEK5_SUMMARY
    if not cost_summary.exists():
        cost_summary = REPO_ROOT / "Week 5" / "data" / "microstructure" / "spread_summary.parquet"
        report["cost_summary"] = f"FALLBACK -> {cost_summary} (hardcoded OLD path missing)"
    else:
        report["cost_summary"] = f"OK -> {cost_summary} (hardcoded path resolved)"

    return data_daily, cost_cache, cost_summary, report


# ============================================================================
# Per-trade extraction (adapted from audit_v4_negative_sharpe._extract_trades)
# ============================================================================

def extract_trades_for_pair(
    pair_df: pd.DataFrame,
    ta: str, tb: str,
    fold_n: int, trading_month: str,
    beta: float, notional_per_leg: float,
) -> list[dict]:
    """One row per trade. Walks position transitions exactly like the audit /
    metrics extractor: entry = pos flips 0 -> non-zero; exit = pos flips
    non-zero -> 0; a position still open at end-of-window is an open_at_eom
    trade. Exit reason from exit_code[i-1] (1-bar execution lag)."""
    idx = pair_df.index
    pos = pair_df["position"].values
    zscore = pair_df["zscore"].values
    pnl_gross = pair_df["daily_pnl_gross"].values
    pnl_net = pair_df["daily_pnl_net"].values
    cost_e = pair_df["cost_entry"].values
    cost_x = pair_df["cost_exit"].values
    borrow = pair_df["borrow_cost"].values
    exit_code = pair_df["exit_code"].values

    pos_prev = np.zeros_like(pos)
    pos_prev[1:] = pos[:-1]
    is_entry = (pos != 0) & (pos_prev == 0)
    is_exit_close = (pos == 0) & (pos_prev != 0)
    n = len(pos)

    def _row(entry_idx: int, exit_idx: int | None, exit_reason: str) -> dict:
        if exit_idx is None:                       # open at end-of-month
            sl = slice(entry_idx, n)
            duration_bars = n - entry_idx
            exit_date: object = ""                 # blank for open_at_eom
            duration_days: object = ""
            # eng_exit_date = the engine's force-close bar (last bar of window).
            # Authoritative exit-session date the exec simulator + cost model use.
            eng_exit_date = idx[n - 1].strftime("%Y-%m-%d")
        else:
            sl = slice(entry_idx, exit_idx + 1)    # inclusive of exit bar
            duration_bars = exit_idx - entry_idx
            exit_date = idx[exit_idx].strftime("%Y-%m-%d")
            eng_exit_date = exit_date
            duration_days = int((idx[exit_idx].normalize()
                                 - idx[entry_idx].normalize()).days)
        entry_z = float(zscore[entry_idx - 1]) if entry_idx >= 1 else float("nan")
        return {
            "fold": fold_n,
            "trading_month": trading_month,
            "pair_id": f"{ta}_{tb}",
            "ticker_a": ta,
            "ticker_b": tb,
            "entry_date": idx[entry_idx].strftime("%Y-%m-%d"),
            "exit_date": exit_date,
            "eng_exit_date": eng_exit_date,        # force-close bar for open_at_eom
            "direction": int(pos[entry_idx]),      # side_a: +1 long A / -1 short A
            "beta": float(beta),
            "notional_per_leg": float(notional_per_leg),
            "entry_z": entry_z,
            "exit_reason": exit_reason,
            "duration_bars": int(duration_bars),
            "duration_days": duration_days,
            "gross_pnl_spread": float(pnl_gross[sl].sum()),
            "cost_backtest": float(cost_e[sl].sum() + cost_x[sl].sum() + borrow[sl].sum()),
            "net_pnl_backtest": float(pnl_net[sl].sum()),
        }

    rows: list[dict] = []
    cur_entry = -1
    for i in range(n):
        if is_entry[i]:
            cur_entry = i
        elif is_exit_close[i] and cur_entry >= 0:
            code = exit_code[i - 1] if i >= 1 else 0
            reason = ("zero_cross" if code == 1
                      else "hard_sl" if code == 2 else "unknown")
            rows.append(_row(cur_entry, i, reason))
            cur_entry = -1
    if cur_entry >= 0:                              # trade still open at EOM
        rows.append(_row(cur_entry, None, "open_at_eom"))
    return rows


# ============================================================================
# Validation gate
# ============================================================================

def validate_against_fold_metrics(ledger: pd.DataFrame, folds: list[int]) -> bool:
    """Compare ledger-derived n_trades and avg_net_bps vs fold_metrics.csv."""
    ref = pd.read_csv(FOLD_METRICS_REF).set_index("fold")

    print("\n" + "=" * 78)
    print("VALIDATION GATE — ledger vs Week 6/results/v4/z30_composite/fold_metrics.csv")
    print("=" * 78)
    header = (f"{'fold':>4} {'month':>8} | {'n_trd(led)':>10} {'n_trd(ref)':>10} "
              f"{'ok':>3} | {'bps(led)':>13} {'bps(ref)':>13} {'absΔ':>10} {'ok':>3}")
    print(header)
    print("-" * len(header))

    all_ok = True
    for f in folds:
        sub = ledger[ledger["fold"] == f]
        n_led = int(len(sub))
        if f in ref.index:
            n_ref = int(ref.loc[f, "n_trades"])
            bps_ref = float(ref.loc[f, "avg_net_bps"])
            month = str(ref.loc[f, "trading_month"])
        else:
            n_ref, bps_ref, month = -1, float("nan"), "?"

        notional_traded = float((2.0 * sub["notional_per_leg"]).sum())
        net_sum = float(sub["net_pnl_backtest"].sum())
        bps_led = (net_sum / notional_traded * 10000.0) if notional_traded > 0 else 0.0

        n_ok = (n_led == n_ref)
        bps_absdiff = abs(bps_led - bps_ref)
        bps_ok = bps_absdiff < 1e-4          # match within rounding
        all_ok = all_ok and n_ok and bps_ok
        print(f"{f:>4} {month:>8} | {n_led:>10} {n_ref:>10} {'Y' if n_ok else 'N':>3} | "
              f"{bps_led:>13.6f} {bps_ref:>13.6f} {bps_absdiff:>10.2e} "
              f"{'Y' if bps_ok else 'N':>3}")

    print("-" * len(header))
    print(f"GATE: {'PASS — ledger reconciles with fold_metrics' if all_ok else 'FAIL — discrepancy (see above)'}")
    return all_ok


# ============================================================================
# Main
# ============================================================================

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--folds", default="1-3",
                    help="'all', range '1-5', or comma list '1,2,3' (default smoke 1-3)")
    ap.add_argument("--out", default=str(OUT_PATH))
    args = ap.parse_args()

    if args.folds == "all":
        fold_nums = [s[0] for s in FOLD_SCHEDULE]
    elif "-" in args.folds:
        lo, hi = args.folds.split("-")
        fold_nums = list(range(int(lo), int(hi) + 1))
    else:
        fold_nums = [int(x) for x in args.folds.split(",")]
    selected = [s for s in FOLD_SCHEDULE if s[0] in fold_nums]

    print("=" * 78)
    print("V4 trade-level ledger builder (z30_composite ship config) — OFFLINE")
    print("=" * 78)
    print(f"Config: entry_z={ENTRY_Z}, hard_sl_z={HARD_SL_Z}, z_window={Z_WINDOW}, "
          f"hl=[{HL_MIN}, {HL_MAX}], dynamic-cost=ON, composite-filter=ON")
    print(f"Folds selected: {[s[0] for s in selected]}")

    # ---- Resolve data/cost paths (rename-aware) ----
    data_daily, cost_cache, cost_summary, path_report = _resolve_paths()
    print("\nPath resolution:")
    for k, v in path_report.items():
        print(f"  {k:12}: {v}")

    t0 = time.time()

    # ---- Load daily cache ----
    print(f"\nLoading daily cache from {data_daily} ...")
    t = time.time()
    cache_daily = _load_all_daily(data_daily)
    t_cache = time.time() - t
    print(f"  loaded {len(cache_daily)} tickers in {t_cache:.1f}s")

    # ---- Load Week 5 dynamic-cost data ----
    print("Loading Week 5 spread cache + kappa map...")
    t = time.time()
    cost_data = cost_engine.load_cost_data(
        daily_cache_path=cost_cache, summary_path=cost_summary,
    )
    t_cost = time.time() - t
    print(f"  loaded {len(cost_data.daily_spread)} daily spread rows, "
          f"{len(cost_data.kappa_map)} tickers in kappa map ({t_cost:.1f}s)")

    # ---- Build composite regime features ONCE ----
    print("Building composite regime features (vol_60d + corr_60d + dispersion_20d)...")
    t = time.time()
    regime_feats = regime_build_features(cache_daily)
    regime_feats = compute_stress_zscore(regime_feats)
    valid = regime_feats["stress_z"].dropna()
    t_regime = time.time() - t
    print(f"  features built in {t_regime:.1f}s; "
          f"valid stress_z from {valid.index[0].date() if len(valid) else 'n/a'}")

    fixed_overhead = time.time() - t0
    print(f"\nFixed overhead (cache+cost+regime): {fixed_overhead:.1f}s")

    # ---- Per-fold ----
    all_rows: list[dict] = []
    daily_rows: list[dict] = []      # per-fold daily portfolio P&L (for variant Sharpe)
    fold_times: dict[int, float] = {}
    n_halted = 0
    for fold_n, fs, fe, tm in selected:
        # Regime FILTER (binary halt) — exactly as run_v4_pipeline.main() (~L395)
        trade_start_ts = pd.Timestamp(tm + "-01")
        halt, diag = halt_for_fold(regime_feats, trade_start_ts)
        if halt:
            n_halted += 1
            print(f"  Fold {fold_n:02d} [{tm}]: REGIME HALT "
                  f"(stress_z={diag.get('stress_z', float('nan')):+.3f} > "
                  f"q67={diag.get('q67_trailing', float('nan')):+.3f}); skip")
            fold_times[fold_n] = 0.0
            continue

        t = time.time()
        res = run_fold_v4(
            fold_n=fold_n, formation_start=fs, formation_end=fe,
            trading_month=tm, cache_daily=cache_daily, out_dir=OUT_DIR,
            entry_z=ENTRY_Z, z_window=Z_WINDOW, hard_sl_z=HARD_SL_Z,
            hl_max=HL_MAX, hl_min=HL_MIN,
            cost_data=cost_data,
            carry_state_in=None,       # ship config: no carry-forward
            fold_size_mult=1.0,        # ship config: no sizer (filter, not sizer)
        )
        fold_times[fold_n] = time.time() - t
        if res is None:
            print(f"  Fold {fold_n:02d} [{tm}]: run_fold_v4 returned None (no pairs); skip")
            continue

        # beta lookup from the fold's discovery pairs_df (frozen hedge ratio)
        pairs_df = res["pairs_df"]
        beta_lookup = {
            (r["ticker_a"], r["ticker_b"]): float(r["beta_pca"])
            for _, r in pairs_df.iterrows()
        }

        for (ta, tb), pdf in res["pair_results"].items():
            beta = beta_lookup.get((ta, tb), float("nan"))
            notional_per_leg = float(pdf.attrs.get("notional", 0.0)) * 0.5
            all_rows.extend(extract_trades_for_pair(
                pdf, ta, tb, fold_n, tm, beta, notional_per_leg,
            ))

        # ---- Per-fold daily portfolio P&L (same construction as metrics_daily:
        #      outer-join per-pair series, fillna(0), sum across pairs). Used by
        #      the exec simulator to reconstruct variant daily Sharpe. ----
        pr = res["pair_results"]
        gross_ser = pd.DataFrame(
            {f"{a}/{b}": d["daily_pnl_gross"] for (a, b), d in pr.items()}
        ).fillna(0.0).sum(axis=1)
        net_ser = pd.DataFrame(
            {f"{a}/{b}": d["daily_pnl_net"] for (a, b), d in pr.items()}
        ).fillna(0.0).sum(axis=1)
        for dt in gross_ser.index:
            daily_rows.append({
                "fold": fold_n, "trading_month": tm,
                "date": dt.strftime("%Y-%m-%d"),
                "gross_pnl": float(gross_ser.loc[dt]),
                "net_pnl": float(net_ser.loc[dt]),
            })

    ledger = pd.DataFrame(all_rows, columns=LEDGER_COLS)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = Path(args.out)
    ledger.to_csv(out_path, index=False)
    print(f"\nWrote {out_path} ({len(ledger)} trade rows)")

    daily_df = pd.DataFrame(daily_rows,
                            columns=["fold", "trading_month", "date", "gross_pnl", "net_pnl"])
    daily_df.to_csv(DAILY_PNL_PATH, index=False)
    print(f"Wrote {DAILY_PNL_PATH} ({len(daily_df)} fold-day rows)")

    # ---- Validation gate ----
    ran_folds = [s[0] for s in selected]
    validate_against_fold_metrics(ledger, ran_folds)

    # ---- Runtime summary + full-run projection ----
    run_secs = [v for v in fold_times.values() if v > 0]
    avg_fold = float(np.mean(run_secs)) if run_secs else 0.0
    total_smoke = time.time() - t0
    # Full run: 39 folds; 12 are regime-halted (near-zero); 27 execute run_fold_v4.
    n_full_run_folds = 27
    proj_full = fixed_overhead + n_full_run_folds * avg_fold
    print("\n" + "=" * 78)
    print("RUNTIME")
    print("=" * 78)
    print(f"  Smoke total ({len(selected)} folds, {n_halted} halted): {total_smoke:.1f}s")
    print(f"  Fixed overhead                                : {fixed_overhead:.1f}s")
    print(f"  Avg per executed fold                         : {avg_fold:.1f}s")
    print(f"  Projected full 39-fold run (27 executed)      : "
          f"~{proj_full:.0f}s (~{proj_full/60:.1f} min)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
