"""
TRACK REGIME — Tier-0: Dampener 3 nấc vs composite nhị phân
============================================================
Implements LOCKED spec `Week 6/engine_rebuild/REGIME_dampener_tier0_spec.md`.

Phases:
    V0 — replication gate: rebuild composite features on the SAME caches the
         backtest/replay used, reproduce all 39 fold halt booleans exactly and
         match recorded stress_z (12 halted folds + 4 replay months, |d|<=0.02).
         FAIL -> stop, ask user. No dampener number is computed in this phase.
    S  — scoring (run only after user go): size_multiplier_for_fold on 43 months,
         dampener P&L = mult x would-have, criteria (a)(b)(c), sensitivity
         0.25/0.75 (report-only).

Usage: python tier0_dampener.py --phase V0|S
"""
from __future__ import annotations

import argparse
import importlib.util
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
RESULTS = ROOT / "Week 6" / "results" / "v4" / "regime_dampener_tier0"
COMPOSITE_FOLDS = ROOT / "Week 6" / "results" / "v4" / "z30_composite" / "fold_metrics.csv"
REPLAY_FOLDS = ROOT / "Week 6" / "results" / "v4" / "replay_2026" / "replay_folds.csv"
JM_SCORECARD = ROOT / "Week 6" / "results" / "v4" / "regime_jm_tier0" / "scorecard_43mo.csv"
RD_PATH = ROOT / "Week 6" / "engine_daily" / "regime_detector.py"

FOLD_MONTHS = pd.period_range("2023-01", "2026-03", freq="M")     # backtest folds 1-39
REPLAY_MONTHS = pd.period_range("2026-04", "2026-07", freq="M")   # replay segment
TOL_SZ = 0.02

# Locked pass/fail thresholds (spec section 3)
CRIT_A_MONTHS = ["2025-12", "2026-01", "2026-02", "2026-03"]
CRIT_A_MIN = -0.0075          # total return floor, Dec25-Mar26
CRIT_B_MIN = 3400.0           # USD floor, replay 2026-04..07
CRIT_C_MIN = 0.0180           # total return floor, folds 1-39


def load_rd():
    spec = importlib.util.spec_from_file_location("regime_detector", RD_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_cache(data_dir: Path) -> dict[str, pd.DataFrame]:
    cache = {}
    for p in sorted(data_dir.glob("*.parquet")):
        cache[p.stem] = pd.read_parquet(p, columns=["log_close"])
    return cache


def build_feats(rd, data_dir: Path, label: str) -> pd.DataFrame:
    print(f"  building composite features on {label} cache ...")
    cache = load_cache(data_dir)
    feats = rd.compute_stress_zscore(rd.build_features(cache))
    print(f"    {len(feats)} days ({feats.index[0].date()} -> {feats.index[-1].date()})")
    return feats


def phase_v0() -> None:
    print("== Gate V0: replication check ==")
    rd = load_rd()
    lines = []

    # --- Folds 1-39 on Polygon cache ---
    feats_poly = build_feats(rd, POLY_DIR, "Polygon")
    comp = pd.read_csv(COMPOSITE_FOLDS, dtype={"regime_halt": str})
    comp["halt_rec"] = comp["regime_halt"].fillna("").str.strip() == "True"
    comp = comp.set_index("trading_month")

    n_halt_ok = n_sz_ok = n_sz_cmp = 0
    mismatches = []
    for m in FOLD_MONTHS:
        ms = str(m)
        halt, diag = rd.halt_for_fold(feats_poly, m.to_timestamp())
        rec_halt = bool(comp.loc[ms, "halt_rec"])
        ok = halt == rec_halt
        n_halt_ok += ok
        row = f"{ms}: halt calc={halt} rec={rec_halt} {'OK' if ok else '** MISMATCH **'}"
        rec_sz = comp.loc[ms, "stress_z"]
        if pd.notna(rec_sz) and str(rec_sz).strip() != "":
            n_sz_cmp += 1
            d = abs(float(diag.get("stress_z", np.nan)) - float(rec_sz))
            sz_ok = d <= TOL_SZ
            n_sz_ok += sz_ok
            row += (f" | stress_z calc={diag.get('stress_z'):.4f} rec={float(rec_sz):.4f} "
                    f"d={d:.4f} {'OK' if sz_ok else '** OFF **'}")
        if not ok:
            mismatches.append(row)
        lines.append(row)
    print(f"  folds 1-39: halt match {n_halt_ok}/39, "
          f"stress_z match {n_sz_ok}/{n_sz_cmp} (tol {TOL_SZ})")

    # --- Replay months on Alpaca cache ---
    feats_alp = build_feats(rd, ALPACA_DIR, "Alpaca")
    rep = pd.read_csv(REPLAY_FOLDS, dtype={"halt": str}).set_index("month")
    n_rep_ok = 0
    for m in REPLAY_MONTHS:
        ms = str(m)
        halt, diag = rd.halt_for_fold(feats_alp, m.to_timestamp())
        rec_halt = rep.loc[ms, "halt"].strip() == "True"
        d = abs(float(diag.get("stress_z", np.nan)) - float(rep.loc[ms, "stress_z"]))
        ok = (halt == rec_halt) and d <= TOL_SZ
        n_rep_ok += ok
        row = (f"{ms}: halt calc={halt} rec={rec_halt} | stress_z "
               f"calc={diag.get('stress_z'):.4f} rec={float(rep.loc[ms, 'stress_z']):.4f} "
               f"d={d:.4f} {'OK' if ok else '** MISMATCH **'}")
        if not ok:
            mismatches.append(row)
        lines.append(row)
    print(f"  replay 2026-04..07: {n_rep_ok}/4 OK")

    gate = (n_halt_ok == 39) and (n_sz_ok == n_sz_cmp) and (n_rep_ok == 4)
    lines.append(f"GATE V0: {'PASS' if gate else 'FAIL'} "
                 f"(halt {n_halt_ok}/39, stress_z {n_sz_ok}/{n_sz_cmp}, replay {n_rep_ok}/4)")
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "replication_check.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    feats_poly.to_pickle(RESULTS / "_feats_poly.pkl")
    feats_alp.to_pickle(RESULTS / "_feats_alp.pkl")
    print(f"  GATE V0: {'PASS' if gate else 'FAIL'} -> replication_check.txt")
    if not gate:
        for r in mismatches:
            print("  " + r)
        sys.exit(2)


def phase_s() -> None:
    print("== Phase S: dampener scoring (per locked spec) ==")
    rd = load_rd()
    feats_poly = pd.read_pickle(RESULTS / "_feats_poly.pkl")
    feats_alp = pd.read_pickle(RESULTS / "_feats_alp.pkl")
    sc = pd.read_csv(JM_SCORECARD, index_col=0)[
        ["composite_halt", "pnl", "pnl_unit", "pnl_source"]]

    rows = []
    for m in list(FOLD_MONTHS) + list(REPLAY_MONTHS):
        ms = str(m)
        feats = feats_poly if m in FOLD_MONTHS else feats_alp
        mult, diag = rd.size_multiplier_for_fold(feats, m.to_timestamp())
        rows.append({"month": ms, "stress_z": diag.get("stress_z"),
                     "q67": diag.get("q67_trailing"), "q85": diag.get("q85_trailing"),
                     "regime": diag.get("regime"), "mult": mult})
    dm = pd.DataFrame(rows).set_index("month").join(sc)
    dm["pnl_damp"] = dm["mult"] * dm["pnl"]
    dm.to_csv(RESULTS / "scorecard_dampener_43mo.csv")

    f = dm[dm.pnl_unit == "return_frac"]
    r = dm[dm.pnl_unit == "usd"]

    a_val = f.loc[CRIT_A_MONTHS, "pnl_damp"].sum()
    b_val = r["pnl_damp"].sum()
    c_val = f["pnl_damp"].sum()
    crit_a, crit_b, crit_c = a_val >= CRIT_A_MIN, b_val >= CRIT_B_MIN, c_val >= CRIT_C_MIN
    verdict = crit_a and crit_b and crit_c

    halted = dm[dm.composite_halt]
    n_half = int((halted["mult"] == 0.5).sum())
    n_zero = int((halted["mult"] == 0.0).sum())
    n_full = int((halted["mult"] == 1.0).sum())

    out = []
    out.append(f"(a) Dec25-Mar26 dampener = {a_val:+.4%} (floor {CRIT_A_MIN:+.2%}) -> "
               f"{'PASS' if crit_a else 'FAIL'}")
    out.append(f"(b) replay 2026 dampener = ${b_val:+,.0f} (floor +${CRIT_B_MIN:,.0f}) -> "
               f"{'PASS' if crit_b else 'FAIL'}")
    out.append(f"(c) folds 1-39 dampener = {c_val:+.4%} (floor {CRIT_C_MIN:+.2%}) -> "
               f"{'PASS' if crit_c else 'FAIL'}")
    out.append(f"VERDICT: {'PASS' if verdict else 'FAIL'}")
    out.append(f"of 15 composite-halt months: {n_half} at mult 0.5, {n_zero} at 0.0, "
               f"{n_full} at 1.0(boundary)")
    # 3-scenario totals per segment (report-only)
    out.append(f"folds 1-39: nofilter={f.pnl.sum():+.4%} "
               f"composite={f.loc[~f.composite_halt, 'pnl'].sum():+.4%} damp={c_val:+.4%}")
    out.append(f"replay usd: nofilter={r.pnl.sum():+,.0f} "
               f"composite={r.loc[~r.composite_halt, 'pnl'].sum():+,.0f} damp={b_val:+,.0f}")
    # sensitivity: mid-tier 0.25 / 0.75 (report-only)
    for alt in (0.25, 0.75):
        mult_alt = dm["mult"].replace({0.5: alt})
        pa = (mult_alt * dm["pnl"])[dm.pnl_unit == "return_frac"]
        pb = (mult_alt * dm["pnl"])[dm.pnl_unit == "usd"]
        va = pa.loc[CRIT_A_MONTHS].sum() >= CRIT_A_MIN
        vb = pb.sum() >= CRIT_B_MIN
        vc = pa.sum() >= CRIT_C_MIN
        out.append(f"sensitivity mid={alt}: a={'P' if va else 'F'} b={'P' if vb else 'F'} "
                   f"c={'P' if vc else 'F'} -> {'PASS' if va and vb and vc else 'FAIL'}")

    txt = "\n".join(out)
    print("  " + txt.replace("\n", "\n  "))
    (RESULTS / "verdict_raw.txt").write_text(txt + "\n", encoding="utf-8")
    print("  saved scorecard_dampener_43mo.csv, verdict_raw.txt")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["V0", "S"], required=True)
    if ap.parse_args().phase == "V0":
        phase_v0()
    else:
        phase_s()
    return 0


if __name__ == "__main__":
    sys.exit(main())
