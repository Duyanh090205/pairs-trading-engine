"""
TRACK REGIME — Tier-0: Jump Model vs composite stress_z
========================================================
Implements the LOCKED spec `Week 6/engine_rebuild/REGIME_jm_tier0_spec.md`.
Pass/fail rules were pre-committed BEFORE any JM number was produced.

Tiers:
    A — build EW-index daily log-return (Polygon RAW 2022-01..2026-03 spliced with
        Alpaca split-adjusted 2026-04..now, splice at INDEX-RETURN level) + 3 data
        validations (hard-fail on overlap corr <= 0.99).
    B — lambda grid on 2022-2024 (fit 2022-23, online-validate 2024, index-timing
        Sharpe criterion, degeneracy guards, tie -> larger lambda). Freeze lambda.
    C — walk-forward 43 monthly refits (expanding, causal) -> scorecard vs composite
        -> criteria (a)(b)(c) -> verdict + lambda +/-1-step sensitivity.

Usage:  python tier0_jm.py --tier A|B|C|all
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(r"d:/Quant Finance/Pairs Trading Strategy")
POLY_DIR = ROOT / "Week 4" / "data" / "validated" / "daily_phase3"
ALPACA_DIR = Path(
    r"C:/Users/nguye/AppData/Local/Temp/claude/d--Quant-Finance-Pairs-Trading-Strategy"
    r"/5d0b2e03-5bc5-44d4-8ed9-7c78d24ffe50/scratchpad/replay_cache"
)
RESULTS = ROOT / "Week 6" / "results" / "v4" / "regime_jm_tier0"
COMPOSITE_FOLDS = ROOT / "Week 6" / "results" / "v4" / "z30_composite" / "fold_metrics.csv"
REGIMEOFF_FOLDS = (
    ROOT / "Week 6" / "results" / "v4" / "zsweep_sl50_regimeoff" / "foldmetrics_z30.csv"
)
REPLAY_FOLDS = ROOT / "Week 6" / "results" / "v4" / "replay_2026" / "replay_folds.csv"
REPLAY_LEDGER = ROOT / "Week 6" / "results" / "v4" / "replay_2026" / "replay_ledger.csv"

# --- Locked config (spec section 2-3) ---
POLY_START, POLY_END = "2022-01-01", "2026-03-31"
# NOTE (declared deviation): Polygon actually ends 2026-03-19, not 03-31 as the
# spec assumed. Splice point = first Alpaca day AFTER Polygon's true last date,
# so the index has no gap. Still an index-return-level splice.
OVERLAP_START, OVERLAP_END = "2024-10-02", "2026-03-31"
MIN_TICKERS = 400          # declare days with fewer tickers
OUTLIER_ABS = 0.05         # |index ret| > 5% -> investigate
CORR_MIN = 0.99            # hard fail below this
FEATURE_WARMUP = 21        # drop first 21 trading days of features (EWM warm-up;
                           # implementation detail declared in verdict)
LAMBDA_GRID = [0.0, 0.1, 0.316, 1.0, 3.16, 10.0, 31.6, 100.0, 316.0, 1000.0]
TRAIN_END = "2023-12-31"   # lambda-selection fit window end
VAL_START, VAL_END = "2024-01-01", "2024-12-31"
BEAR_SHARE_RANGE = (0.05, 0.60)
MIN_AVG_DURATION = 5.0     # days
SHARPE_TIE = 0.05
SCORE_MONTHS = pd.period_range("2023-01", "2026-07", freq="M")
CRIT_A_MONTHS = ["2025-12", "2026-01", "2026-02", "2026-03"]
CRIT_B_MONTHS = ["2026-06", "2026-07"]
CRIT_C_START, CRIT_C_END = "2023-01", "2025-11"


# ----------------------------------------------------------------------------
# Tier A — index build + validation
# ----------------------------------------------------------------------------

def _load_index_returns(data_dir: Path, label: str) -> tuple[pd.Series, pd.Series]:
    """EW index log-return = cross-sectional mean of per-ticker log-return.

    Matches regime_detector.build_features: R = diff(log_close); eq = R.mean(axis=1).
    Returns (index_ret, n_tickers_per_day).
    """
    rets = {}
    for p in sorted(data_dir.glob("*.parquet")):
        df = pd.read_parquet(p, columns=["log_close"])
        rets[p.stem] = df["log_close"].diff()
    R = pd.DataFrame(rets).sort_index()
    idx_ret = R.mean(axis=1).dropna()
    n_tickers = R.notna().sum(axis=1).reindex(idx_ret.index)
    print(f"  {label}: {R.shape[1]} tickers, {len(idx_ret)} days "
          f"({idx_ret.index[0].date()} -> {idx_ret.index[-1].date()})")
    return idx_ret, n_tickers


def tier_a() -> pd.DataFrame:
    print("== Tier A: build EW index + validations ==")
    poly_ret, poly_n = _load_index_returns(POLY_DIR, "Polygon RAW")
    alp_ret, alp_n = _load_index_returns(ALPACA_DIR, "Alpaca adj")

    poly_seg = poly_ret.loc[POLY_START:POLY_END]
    splice_from = poly_seg.index[-1] + pd.Timedelta(days=1)
    alp_seg = alp_ret.loc[splice_from:]
    print(f"  splice: Polygon ends {poly_seg.index[-1].date()}, "
          f"Alpaca segment starts {alp_seg.index[0].date()}")

    # Validation 1 — overlap correlation Polygon vs Alpaca index returns
    ov = pd.DataFrame({"poly": poly_ret, "alp": alp_ret}).loc[
        OVERLAP_START:OVERLAP_END].dropna()
    corr = ov["poly"].corr(ov["alp"])
    med_bp = (ov["poly"] - ov["alp"]).abs().median() * 1e4
    max_bp = (ov["poly"] - ov["alp"]).abs().max() * 1e4
    v1 = (f"V1 overlap {OVERLAP_START}..{OVERLAP_END}: n={len(ov)}, corr={corr:.6f}, "
          f"median|diff|={med_bp:.2f}bp, max|diff|={max_bp:.1f}bp "
          f"[{'PASS' if corr > CORR_MIN else 'FAIL'} @ >{CORR_MIN}]")
    print("  " + v1)

    # Validation 2 — outlier days on the spliced index
    spliced = pd.concat([poly_seg, alp_seg])
    assert spliced.index.is_monotonic_increasing and not spliced.index.duplicated().any()
    outliers = spliced[spliced.abs() > OUTLIER_ABS]
    v2 = [f"V2 outliers |ret|>{OUTLIER_ABS:.0%}: {len(outliers)} day(s)"]
    for d, v in outliers.items():
        v2.append(f"    {d.date()}: {v:+.4f}")
    print("  " + "\n  ".join(v2))

    # Validation 3 — thin days (fewer than MIN_TICKERS with a return)
    n_all = pd.concat([poly_n.loc[poly_seg.index], alp_n.loc[alp_seg.index]])
    thin = n_all[n_all < MIN_TICKERS]
    v3 = [f"V3 days with <{MIN_TICKERS}/528 tickers: {len(thin)} day(s)"]
    for d, v in thin.items():
        v3.append(f"    {d.date()}: n={int(v)}")
    print("  " + "\n  ".join(v3))

    RESULTS.mkdir(parents=True, exist_ok=True)
    out = pd.DataFrame({
        "ret": spliced,
        "n_tickers": n_all.astype(int),
        "source": ["polygon_raw"] * len(poly_seg) + ["alpaca_adj"] * len(alp_seg),
    })
    out.index.name = "date"
    out.to_csv(RESULTS / "index_returns.csv")
    (RESULTS / "index_validation.txt").write_text(
        "\n".join([v1] + v2 + v3) + "\n", encoding="utf-8")
    print(f"  saved {len(out)} days -> index_returns.csv")

    if corr <= CORR_MIN:
        print("HARD FAIL: overlap corr <= 0.99 — stop per spec, ask user.")
        sys.exit(2)
    return out


# ----------------------------------------------------------------------------
# Features (locked: DD hl=10, Sortino hl=20, Sortino hl=60)
# ----------------------------------------------------------------------------

def build_features(ir: pd.Series) -> pd.DataFrame:
    feats = {}
    feats["DD_hl10"] = np.sqrt((ir.clip(upper=0) ** 2).ewm(halflife=10).mean())
    for hl in (20, 60):
        dd = np.sqrt((ir.clip(upper=0) ** 2).ewm(halflife=hl).mean())
        feats[f"sortino_hl{hl}"] = ir.ewm(halflife=hl).mean() / dd
    F = pd.DataFrame(feats).iloc[FEATURE_WARMUP:]
    F = F.replace([np.inf, -np.inf], np.nan)
    if F.isna().any().any():
        raise RuntimeError("NaN/inf in features after warmup — investigate before fitting")
    return F


def _fit_jm(X: pd.DataFrame, ir: pd.Series, lam: float):
    """Fit clipper+scaler+JM on window X (causal: everything fit on X only).

    Returns (jm, labels, bull_label, X_processed).
    Bull mapping is decided by in-window cumulative return per label (does not
    rely on package sort convention; logged if it disagrees with label 0).
    """
    from jumpmodels.jump import JumpModel
    from jumpmodels.preprocess import DataClipperStd, StandardScalerPD

    clipper = DataClipperStd(mul=3.0)
    scaler = StandardScalerPD()
    Xp = scaler.fit_transform(clipper.fit_transform(X))
    jm = JumpModel(n_components=2, jump_penalty=lam, cont=False)
    r = ir.reindex(X.index)
    jm.fit(Xp, ret_ser=r, sort_by="cumret")
    labels = pd.Series(np.asarray(jm.labels_).ravel(), index=X.index)
    cum0 = r[labels == 0].sum()
    cum1 = r[labels == 1].sum()
    bull = 0 if cum0 >= cum1 else 1
    if bull != 0:
        print(f"    note: bull label={bull} (package sort_by=cumret gave label0 "
              f"cum={cum0:+.4f} < label1 cum={cum1:+.4f})")
    return jm, labels, bull, Xp, clipper, scaler


def _regime_stats(labels: pd.Series, bull: int) -> tuple[float, float]:
    """(bear share, avg regime duration in days)."""
    bear_share = float((labels != bull).mean())
    runs = (labels != labels.shift()).cumsum()
    avg_dur = float(labels.groupby(runs).size().mean())
    return bear_share, avg_dur


# ----------------------------------------------------------------------------
# Tier B — lambda grid, frozen selection
# ----------------------------------------------------------------------------

def tier_b() -> float:
    print("== Tier B: lambda grid on 2022-2024 ==")
    ir = pd.read_csv(RESULTS / "index_returns.csv", index_col=0, parse_dates=True)["ret"]
    F = build_features(ir)

    X_train = F.loc[:TRAIN_END]
    X_trval = F.loc[:VAL_END]
    rows = []
    for lam in LAMBDA_GRID:
        jm, _, bull, _, clipper, scaler = _fit_jm(X_train, ir, lam)
        # Online inference over train+val with train-fitted preprocessing;
        # continuity preserved, only the 2024 part is scored.
        Xp_trval = scaler.transform(clipper.transform(X_trval))
        states = pd.Series(
            np.asarray(jm.predict_online(Xp_trval)).ravel(), index=X_trval.index)
        bear_share, avg_dur = _regime_stats(states, bull)
        guard = BEAR_SHARE_RANGE[0] <= bear_share <= BEAR_SHARE_RANGE[1] \
            and avg_dur >= MIN_AVG_DURATION

        # Index-timing overlay on validation 2024: pos(t+1) = 1{state(t)==bull}
        pos = (states == bull).astype(float).shift(1)
        strat = (pos * ir.reindex(X_trval.index)).loc[VAL_START:VAL_END].dropna()
        sd = strat.std(ddof=1)
        sharpe = float(strat.mean() / sd * np.sqrt(252)) if sd > 1e-12 else float("-inf")
        rows.append({"lam": lam, "sharpe_val": sharpe, "bear_share": bear_share,
                     "avg_dur": avg_dur, "guard_pass": guard})
        print(f"  lam={lam:>7}: Sharpe(val24)={sharpe:+.3f} bear={bear_share:.1%} "
              f"dur={avg_dur:.1f}d guard={'ok' if guard else 'REJECT'}")

    grid = pd.DataFrame(rows)
    ok = grid[grid["guard_pass"]]
    if ok.empty:
        print("No lambda passes degeneracy guards — stop per spec, ask user.")
        sys.exit(3)
    best = ok["sharpe_val"].max()
    chosen = ok[ok["sharpe_val"] >= best - SHARPE_TIE]["lam"].max()  # tie -> larger lam
    grid["chosen"] = grid["lam"] == chosen
    grid.to_csv(RESULTS / "lambda_grid.csv", index=False)
    print(f"  FROZEN lambda = {chosen} (best Sharpe {best:+.3f}, tie-band {SHARPE_TIE})")
    return float(chosen)


# ----------------------------------------------------------------------------
# Tier C — walk-forward 43 months, scorecard, criteria
# ----------------------------------------------------------------------------

def walkforward_states(ir: pd.Series, F: pd.DataFrame, lam: float) -> pd.Series:
    """For each scored month: refit on expanding window ..t*, state at t*."""
    states = {}
    for m in SCORE_MONTHS:
        month_start = m.to_timestamp()
        idx = F.index[F.index < month_start]
        if len(idx) == 0:
            raise RuntimeError(f"no data before {m}")
        t_star = idx[-1]
        Xw = F.loc[:t_star]
        _, labels, bull, _, _, _ = _fit_jm(Xw, ir, lam)
        states[str(m)] = "bear" if labels.iloc[-1] != bull else "bull"
    return pd.Series(states, name="jm_state")


def load_composite_and_pnl() -> pd.DataFrame:
    comp = pd.read_csv(COMPOSITE_FOLDS, dtype={"regime_halt": str})
    comp["halt"] = comp["regime_halt"].fillna("").str.strip() == "True"
    comp = comp.set_index("trading_month")["halt"]

    off = pd.read_csv(REGIMEOFF_FOLDS).set_index("trading_month")["total_return"]

    rep = pd.read_csv(REPLAY_FOLDS, dtype={"halt": str}).set_index("month")
    rep_halt = rep["halt"].str.strip() == "True"
    led = pd.read_csv(REPLAY_LEDGER)
    rep_pnl = led.groupby("trading_month")["net_base"].sum()

    rows = []
    for m in SCORE_MONTHS:
        ms = str(m)
        if ms in comp.index:
            rows.append({"month": ms, "composite_halt": bool(comp[ms]),
                         "pnl": float(off[ms]), "pnl_unit": "return_frac",
                         "pnl_source": "foldmetrics_z30_regimeoff(dyncost~20bp)"})
        elif ms in rep_halt.index:
            rows.append({"month": ms, "composite_halt": bool(rep_halt[ms]),
                         "pnl": float(rep_pnl.get(ms, 0.0)), "pnl_unit": "usd",
                         "pnl_source": "replay_ledger_net_base(probe~6bp)"})
        else:
            raise RuntimeError(f"no composite decision for {ms}")
    return pd.DataFrame(rows).set_index("month")


def evaluate(sc: pd.DataFrame) -> dict:
    a_bear = int((sc.loc[CRIT_A_MONTHS, "jm_state"] == "bear").sum())
    crit_a = a_bear >= 3
    crit_b = bool((sc.loc[CRIT_B_MONTHS, "jm_state"] == "bull").all())
    w = sc.loc[CRIT_C_START:CRIT_C_END]
    prof = w[w["pnl"] > 0]
    jm_c = int((prof["jm_state"] == "bear").sum())
    comp_c = int(prof["composite_halt"].sum())
    crit_c = jm_c <= comp_c
    return {"a_bear_of_4": a_bear, "crit_a": crit_a, "crit_b": crit_b,
            "jm_bear_profitable": jm_c, "comp_halt_profitable": comp_c,
            "crit_c": crit_c, "n_profitable_23_2511": len(prof),
            "PASS": crit_a and crit_b and crit_c}


def tier_c() -> None:
    print("== Tier C: walk-forward 43 months + scorecard ==")
    ir = pd.read_csv(RESULTS / "index_returns.csv", index_col=0, parse_dates=True)["ret"]
    F = build_features(ir)
    grid = pd.read_csv(RESULTS / "lambda_grid.csv")
    lam = float(grid.loc[grid["chosen"], "lam"].iloc[0])
    print(f"  frozen lambda = {lam}")

    jm_states = walkforward_states(ir, F, lam)
    base = load_composite_and_pnl()
    sc = base.join(jm_states)
    sc["pnl_sign"] = np.sign(sc["pnl"]).astype(int)
    sc["jm_halt"] = sc["jm_state"] == "bear"
    sc["agree"] = sc["jm_halt"] == sc["composite_halt"]
    sc.to_csv(RESULTS / "scorecard_43mo.csv")

    res = evaluate(sc)
    print(f"  (a) bear in Dec25-Mar26: {res['a_bear_of_4']}/4  -> "
          f"{'PASS' if res['crit_a'] else 'FAIL'}")
    print(f"  (b) bull Jun+Jul 2026: {'PASS' if res['crit_b'] else 'FAIL'} "
          f"({sc.loc[CRIT_B_MONTHS, 'jm_state'].tolist()})")
    print(f"  (c) profitable months flagged bear, 2023-01..2025-11: "
          f"JM={res['jm_bear_profitable']} vs composite={res['comp_halt_profitable']} "
          f"(of {res['n_profitable_23_2511']} profitable) -> "
          f"{'PASS' if res['crit_c'] else 'FAIL'}")
    print(f"  VERDICT: {'PASS — JM dau Tier-0' if res['PASS'] else 'FAIL — dong track JM'}")

    # Sensitivity: verdict at one grid step below/above frozen lambda (report-only)
    gi = LAMBDA_GRID.index(lam)
    sens = {}
    for j in (gi - 1, gi + 1):
        if 0 <= j < len(LAMBDA_GRID):
            lam2 = LAMBDA_GRID[j]
            print(f"  sensitivity: rerun at lambda={lam2}")
            st2 = walkforward_states(ir, F, lam2)
            sc2 = base.join(st2)
            sens[lam2] = evaluate(sc2)
            sens[lam2]["states"] = st2.to_dict()
    pd.Series({str(k): {kk: vv for kk, vv in v.items() if kk != "states"}
               for k, v in sens.items()}).to_json(RESULTS / "sensitivity.json", indent=2)

    lines = [f"lambda_frozen={lam}", str(res)]
    for k, v in sens.items():
        lines.append(f"sensitivity lambda={k}: "
                     + str({kk: vv for kk, vv in v.items() if kk != 'states'}))
    (RESULTS / "verdict_raw.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("  saved scorecard_43mo.csv, sensitivity.json, verdict_raw.txt")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier", choices=["A", "B", "C", "all"], default="all")
    t = ap.parse_args().tier
    if t in ("A", "all"):
        tier_a()
    if t in ("B", "all"):
        tier_b()
    if t in ("C", "all"):
        tier_c()
    return 0


if __name__ == "__main__":
    sys.exit(main())
