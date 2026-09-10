"""
Z-sweep, discovery-once / engine-3-Z. Matched config to LIVE:
  hard_sl_z=5.0, z_window=60, hl=[5,30], dynamic cost ON, regime OFF, no carry.
Discovery + residual projection computed ONCE per fold (the bottleneck),
engine (run_fold_daily) run for entry_z in {2.0, 2.5, 3.0} on the same discovery.
Dumps per-Z: fold_metrics, trade ledger, daily_pnl.
Windows-safe: all execution under __main__ guard (discovery uses mp spawn).
"""
import os as _os
for _v in ("OMP_NUM_THREADS","MKL_NUM_THREADS","OPENBLAS_NUM_THREADS",
           "VECLIB_MAXIMUM_THREADS","NUMEXPR_NUM_THREADS"):
    _os.environ[_v] = "1"

import sys, time
from pathlib import Path
import numpy as np
import pandas as pd

REPO = Path(r"d:/Quant Finance/Pairs Trading Strategy")
WEEK6 = REPO / "Week 6"
sys.path.insert(0, str(WEEK6))
sys.path.insert(0, str(WEEK6 / "scripts"))
sys.path.insert(0, str(REPO / "trading_1min" / "research"))

import run_v4_pipeline as v4
from run_v4_pipeline import _load_all_daily, _slice_daily, FOLD_SCHEDULE, TOTAL_CAPITAL
from engine_daily import discovery_daily, cost_engine
from engine_daily.engine_daily import run_fold_daily
from engine_daily.metrics_daily import aggregate_fold_metrics
from engine.phase1_cointegration.factor_residual import project_residual
from build_v4_ledger import extract_trades_for_pair, LEDGER_COLS

OUT = Path(r"C:/Users/nguye/AppData/Local/Temp/claude/d--Quant-Finance-Pairs-Trading-Strategy/5d0b2e03-5bc5-44d4-8ed9-7c78d24ffe50/scratchpad/sweep")
ENTRY_Z_VALUES = [2.0, 2.5, 3.0]
HARD_SL_Z = 5.0
Z_WINDOW = 60
HL_MIN, HL_MAX = 5.0, 30.0


def discover_and_project(fold_n, fs, fe, tm, cache):
    """Steps 1-4 of run_fold_v4 (entry_z-INDEPENDENT). Copied verbatim from
    run_v4_pipeline.run_fold_v4 so results match the pipeline exactly."""
    formation_daily = _slice_daily(cache, fs, fe)
    if not formation_daily:
        return None
    pairs_df, factor_state = discovery_daily.run(
        formation_data=formation_daily, hl_min=HL_MIN, hl_max=HL_MAX)
    if pairs_df.empty or not factor_state:
        return None
    trade_start = tm + "-01"
    trade_end = (pd.Timestamp(trade_start) + pd.offsets.MonthEnd(0)).strftime("%Y-%m-%d")
    trading_daily_raw = _slice_daily(cache, trade_start, trade_end)
    if not trading_daily_raw:
        return None
    loadings_W = factor_state["loadings_W"]
    factor_tickers = factor_state["tickers"]
    resid_form_df = factor_state["residual_log_prices"]
    resid_trade_dict = project_residual(trading_daily_raw, loadings_W, factor_tickers, min_obs=10)
    for tk in list(resid_trade_dict.keys()):
        if tk not in resid_form_df.columns:
            continue
        s_form_tk = resid_form_df[tk].dropna()
        if len(s_form_tk) == 0 or len(resid_trade_dict[tk]) == 0:
            continue
        shift = float(s_form_tk.iloc[-1]) - float(resid_trade_dict[tk].iloc[0])
        resid_trade_dict[tk] = resid_trade_dict[tk] + shift
    resid_trade_df = pd.concat(resid_trade_dict, axis=1)
    return pairs_df, resid_form_df, resid_trade_df


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    print(f"loading daily cache from {v4.DATA_DAILY} ...", flush=True)
    cache = _load_all_daily(v4.DATA_DAILY)
    print(f"  loaded {len(cache)} tickers in {time.time()-t0:.1f}s", flush=True)
    print("loading dynamic cost data ...", flush=True)
    cost_data = cost_engine.load_cost_data()
    print(f"  cost data loaded ({time.time()-t0:.1f}s). Config: hard_sl={HARD_SL_Z}, "
          f"regime OFF, dyncost ON, EOM. Z={ENTRY_Z_VALUES}", flush=True)

    # accumulators per entry_z
    ledger = {z: [] for z in ENTRY_Z_VALUES}
    foldrows = {z: [] for z in ENTRY_Z_VALUES}
    daily = {z: [] for z in ENTRY_Z_VALUES}

    for fold_n, fs, fe, tm in FOLD_SCHEDULE:
        tf = time.time()
        dp = discover_and_project(fold_n, fs, fe, tm, cache)
        if dp is None:
            print(f"  fold {fold_n:02d} [{tm}]: no discovery -> skip all Z", flush=True)
            for z in ENTRY_Z_VALUES:
                foldrows[z].append({"fold": fold_n, "trading_month": tm, "n_pairs": 0,
                                    "n_trades": 0, "sharpe": 0.0, "total_return": 0.0,
                                    "n_zero_cross": 0, "n_hard_sl": 0, "n_open_at_eom": 0})
            continue
        pairs_df, resid_form_df, resid_trade_df = dp
        msg = [f"fold {fold_n:02d} [{tm}]: {len(pairs_df)} pairs"]
        for z in ENTRY_Z_VALUES:
            pr = run_fold_daily(
                pairs_df=pairs_df.copy(), resid_form=resid_form_df, resid_trade=resid_trade_df,
                alpha_lookback=60, entry_z=z, z_window=Z_WINDOW, hard_sl_z=HARD_SL_Z,
                cost_data=cost_data, carry_state_in=None, current_fold_n=fold_n, fold_size_mult=1.0)
            fm = aggregate_fold_metrics(pr, total_capital=TOTAL_CAPITAL)
            eb = fm.get("exit_breakdown", {})
            foldrows[z].append({
                "fold": fold_n, "trading_month": tm, "n_pairs": len(pairs_df),
                "n_trades": fm.get("n_trades", 0), "sharpe": fm.get("sharpe", 0.0),
                "total_return": fm.get("total_return", 0.0), "max_dd": fm.get("max_dd", 0.0),
                "win_rate": fm.get("win_rate", 0.0), "avg_net_bps": fm.get("avg_net_bps", 0.0),
                "n_zero_cross": eb.get("zero_cross", 0), "n_hard_sl": eb.get("hard_sl", 0),
                "n_open_at_eom": eb.get("open_at_eom", 0)})
            # ledger
            beta_lookup = {(r["ticker_a"], r["ticker_b"]): float(r["beta_pca"])
                           for _, r in pairs_df.iterrows()}
            for (ta, tb), pdf in pr.items():
                beta = beta_lookup.get((ta, tb), float("nan"))
                npl = float(pdf.attrs.get("notional", 0.0)) * 0.5
                ledger[z].extend(extract_trades_for_pair(pdf, ta, tb, fold_n, tm, beta, npl))
            # daily pnl
            g = pd.DataFrame({f"{a}/{b}": d["daily_pnl_gross"] for (a, b), d in pr.items()}).fillna(0.0).sum(axis=1)
            nser = pd.DataFrame({f"{a}/{b}": d["daily_pnl_net"] for (a, b), d in pr.items()}).fillna(0.0).sum(axis=1)
            for dt in g.index:
                daily[z].append({"fold": fold_n, "trading_month": tm, "date": dt.strftime("%Y-%m-%d"),
                                 "gross_pnl": float(g.loc[dt]), "net_pnl": float(nser.loc[dt])})
            msg.append(f"Z{z}:tr={fm.get('n_trades',0)}")
        print("  " + " | ".join(msg) + f"  ({time.time()-tf:.0f}s)", flush=True)

    for z in ENTRY_Z_VALUES:
        tag = f"z{int(z*10):02d}"
        pd.DataFrame(foldrows[z]).to_csv(OUT / f"foldmetrics_{tag}.csv", index=False)
        pd.DataFrame(ledger[z], columns=LEDGER_COLS).to_csv(OUT / f"ledger_{tag}.csv", index=False)
        pd.DataFrame(daily[z]).to_csv(OUT / f"dailypnl_{tag}.csv", index=False)
        df = pd.DataFrame(foldrows[z]); tr = df[df["n_trades"] > 0]
        print(f"[{tag}] wrote: {len(ledger[z])} trades | sum_ret {df['total_return'].sum():+.4f} | "
              f"mean_sharpe {tr['sharpe'].mean():+.3f} | traded {len(tr)}/39", flush=True)

    print(f"\nTOTAL {time.time()-t0:.0f}s (~{(time.time()-t0)/60:.1f} min)", flush=True)
    (OUT / "DONE").write_text("done")


if __name__ == "__main__":
    import multiprocessing as mp
    mp.freeze_support()
    main()
