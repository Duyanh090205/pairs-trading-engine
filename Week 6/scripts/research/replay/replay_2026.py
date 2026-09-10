"""
Phase B — shadow replay 2026-04..07 "như live" on pure-Alpaca replay cache.
Per month: 12m-formation discovery + regime decide_month math + ship engine
(Z=3.0, hard_sl=5.0, EOM flatten). July = PARTIAL (through 07-24, flagged).
Engine runs with cost_data=None (flat 30bps legacy) but we IGNORE engine cost:
ledger gross P&L is re-costed with PROBE-calibrated numbers (Phase B2, per
locked s2s4_intensity_exec_spec.md):
  BASE-taker : 1.5bp per leg-side (probe median market slippage), x4 = 6bp RT
               + borrow 50bps/yr on short leg (calendar days). Commission 0
               (Alpaca retail).
  S2/S4      : entry passive-then-taker unless |Z|>=entry+2; zero_cross exit
               passive-then-taker; hard_sl taker; EOM passive@1530-then-taker.
               p=0.55, q=0.20, delta=0.5bp; passive fill earns 1.9bp/leg-side.
               EXPECTED-VALUE costing (no RNG -> deterministic).
Windows-safe: everything under __main__ (discovery uses mp spawn).
"""
import os as _os
for _v in ("OMP_NUM_THREADS","MKL_NUM_THREADS","OPENBLAS_NUM_THREADS",
           "VECLIB_MAXIMUM_THREADS","NUMEXPR_NUM_THREADS"):
    _os.environ[_v] = "1"
import sys, time
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(r"d:/Quant Finance/Pairs Trading Strategy")
WEEK6 = ROOT / "Week 6"
sys.path.insert(0, str(WEEK6)); sys.path.insert(0, str(WEEK6 / "scripts"))
sys.path.insert(0, str(ROOT / "trading_1min" / "research"))

from run_v4_pipeline import _slice_daily
from engine_daily import discovery_daily
from engine_daily.engine_daily import run_fold_daily
from engine_daily.metrics_daily import aggregate_fold_metrics
from engine_daily.regime_detector import (build_features, compute_stress_zscore,
                                          halt_for_fold)
from engine.phase1_cointegration.factor_residual import project_residual
from build_v4_ledger import extract_trades_for_pair, LEDGER_COLS

SCRATCH = Path(r"C:/Users/nguye/AppData/Local/Temp/claude/d--Quant-Finance-Pairs-Trading-Strategy/5d0b2e03-5bc5-44d4-8ed9-7c78d24ffe50/scratchpad")
CACHE_DIR = SCRATCH / "replay_cache"
OUT = SCRATCH / "replay_out"

ENTRY_Z, HARD_SL_Z, Z_WINDOW = 3.0, 5.0, 60
MONTHS = ["2026-04", "2026-05", "2026-06", "2026-07"]   # 07 = partial (to 07-24)

# probe-calibrated cost constants (bp) — see spec
TAKER_BP = 1.5          # per leg-side, market order (probe median slippage)
PASSIVE_EARN_BP = 1.9   # per leg-side when passive fills (probe median, sign=earn)
P_FILL, Q_BAD, DELTA_BP = 0.55, 0.20, 0.5
BORROW_BPS_YR = 50.0

def leg_side_cost_taker(): return TAKER_BP
def leg_side_cost_passive_try():
    # EV per leg-side (bp): fill -> -earn; miss -> taker+delta; badquote -> taker
    return ((1-Q_BAD)*P_FILL*(-PASSIVE_EARN_BP)
            + (1-Q_BAD)*(1-P_FILL)*(TAKER_BP+DELTA_BP)
            + Q_BAD*TAKER_BP)

def cost_trade_bp(row, mode):
    """Round-trip cost in bp of per-leg notional (2 legs x 2 sides)."""
    ez = abs(row["entry_z"]) if pd.notna(row["entry_z"]) else ENTRY_Z
    if mode == "base":
        entry = 2*leg_side_cost_taker(); exit_ = 2*leg_side_cost_taker()
    else:
        entry = 2*(leg_side_cost_taker() if ez >= ENTRY_Z+2 else leg_side_cost_passive_try())
        r = row["exit_reason"]
        if r == "hard_sl": exit_ = 2*leg_side_cost_taker()
        else:              exit_ = 2*leg_side_cost_passive_try()   # zero_cross & EOM
    return entry + exit_

def borrow_cost(row):
    d = row["duration_bars"] if row["duration_days"] in ("", None) or pd.isna(row["duration_days"]) else max(float(row["duration_days"]),1)
    return float(row["notional_per_leg"]) * (BORROW_BPS_YR/1e4) * (float(d)/365.0)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    cache = {p.stem: pd.read_parquet(p) for p in CACHE_DIR.glob("*.parquet")}
    print(f"replay cache: {len(cache)} tickers", flush=True)

    # regime features once on full replay cache
    feats = compute_stress_zscore(build_features(cache))
    v = feats["stress_z"].dropna()
    print(f"stress_z valid from {v.index[0].date()} to {v.index[-1].date()} ({len(v)} d)", flush=True)

    ledger_rows, foldrows = [], []
    for i, tm in enumerate(MONTHS):
        trade_start = pd.Timestamp(tm + "-01")
        form_start = (trade_start - pd.DateOffset(years=1)).strftime("%Y-%m-%d")
        form_end = (trade_start - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        halt, diag = halt_for_fold(feats, trade_start)
        print(f"\n== {tm}: formation {form_start}..{form_end} | REGIME "
              f"{'HALT' if halt else 'ok'} (stress_z={diag.get('stress_z',float('nan')):+.2f} "
              f"q67={diag.get('q67_trailing',float('nan')):+.2f}) ==", flush=True)

        form = _slice_daily(cache, form_start, form_end)
        pairs_df, fstate = discovery_daily.run(formation_data=form, hl_min=5.0, hl_max=30.0)
        if pairs_df.empty:
            foldrows.append({"month": tm, "halt": halt, "n_pairs": 0, "n_trades": 0}); continue
        te = (trade_start + pd.offsets.MonthEnd(0)).strftime("%Y-%m-%d")
        raw = _slice_daily(cache, tm + "-01", te)
        rt = project_residual(raw, fstate["loadings_W"], fstate["tickers"], min_obs=10)
        rf = fstate["residual_log_prices"]
        for tk in list(rt.keys()):
            if tk not in rf.columns: continue
            sf = rf[tk].dropna()
            if len(sf) == 0 or len(rt[tk]) == 0: continue
            rt[tk] = rt[tk] + (float(sf.iloc[-1]) - float(rt[tk].iloc[0]))
        rt_df = pd.concat(rt, axis=1)
        pr = run_fold_daily(pairs_df=pairs_df, resid_form=rf, resid_trade=rt_df,
                            alpha_lookback=60, entry_z=ENTRY_Z, z_window=Z_WINDOW,
                            hard_sl_z=HARD_SL_Z, cost_data=None, carry_state_in=None,
                            current_fold_n=40 + i, fold_size_mult=1.0)
        fm = aggregate_fold_metrics(pr, total_capital=1_000_000.0)
        beta_lu = {(r["ticker_a"], r["ticker_b"]): float(r["beta_pca"]) for _, r in pairs_df.iterrows()}
        n_led0 = len(ledger_rows)
        for (ta, tb), pdf in pr.items():
            npl = float(pdf.attrs.get("notional", 0.0)) * 0.5
            ledger_rows.extend(extract_trades_for_pair(pdf, ta, tb, 40 + i, tm,
                                                       beta_lu.get((ta, tb), float("nan")), npl))
        eb = fm.get("exit_breakdown", {})
        foldrows.append({"month": tm, "halt": halt, "stress_z": diag.get("stress_z"),
                         "n_pairs": len(pairs_df), "n_trades": fm.get("n_trades", 0),
                         "gross_ret": None,  # filled from ledger below
                         "zero": eb.get("zero_cross", 0), "sl": eb.get("hard_sl", 0),
                         "eom": eb.get("open_at_eom", 0),
                         "n_ledger": len(ledger_rows) - n_led0,
                         "partial": tm == "2026-07"})
        print(f"   {len(pairs_df)} pairs, {fm.get('n_trades',0)} trades "
              f"(z/sl/eom={eb.get('zero_cross',0)}/{eb.get('hard_sl',0)}/{eb.get('open_at_eom',0)})", flush=True)

    led = pd.DataFrame(ledger_rows, columns=LEDGER_COLS)
    # ---- Phase B2: probe-calibrated costing on the ledger ----
    for mode in ("base", "s2s4"):
        led[f"cost_{mode}"] = led.apply(
            lambda r: r["notional_per_leg"] * cost_trade_bp(r, mode) / 1e4 + borrow_cost(r), axis=1)
        led[f"net_{mode}"] = led["gross_pnl_spread"] - led[f"cost_{mode}"]
    led.to_csv(OUT / "replay_ledger.csv", index=False)

    print("\n" + "=" * 70)
    print("REPLAY 2026-04..07 (ship Z=3.0/SL5.0, probe-calibrated costs)")
    print("=" * 70)
    for tm in MONTHS:
        sub = led[led["trading_month"] == tm]
        fr = next(f for f in foldrows if f["month"] == tm)
        tag = " HALT" if fr["halt"] else ""
        tag += " PARTIAL" if fr.get("partial") else ""
        if len(sub) == 0:
            print(f"{tm}{tag}: 0 trades"); continue
        print(f"{tm}{tag}: {len(sub)} trades | gross ${sub['gross_pnl_spread'].sum():+,.0f} | "
              f"net_base ${sub['net_base'].sum():+,.0f} | net_s2s4 ${sub['net_s2s4'].sum():+,.0f} | "
              f"exits z/sl/eom={fr['zero']}/{fr['sl']}/{fr['eom']}")
    traded = led[~led["trading_month"].isin([f["month"] for f in foldrows if f["halt"]])]
    print("-" * 70)
    for scope, sub in [("ALL(incl halted-as-zero)", led), ("traded months only", traded)]:
        print(f"{scope}: gross ${sub['gross_pnl_spread'].sum():+,.0f} | "
              f"net_base ${sub['net_base'].sum():+,.0f} | net_s2s4 ${sub['net_s2s4'].sum():+,.0f} | "
              f"s2s4 saves ${ (sub['cost_base']-sub['cost_s2s4']).sum():+,.0f}")
    pd.DataFrame(foldrows).to_csv(OUT / "replay_folds.csv", index=False)
    print(f"\nTOTAL {time.time()-t0:.0f}s")
    (OUT / "_DONE").write_text("done")


if __name__ == "__main__":
    import multiprocessing as mp
    mp.freeze_support()
    main()
