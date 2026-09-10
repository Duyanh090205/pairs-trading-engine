"""
Phễu chọn cặp 1-phút — BẢN RESIDUAL (nấc a của pivot, 2026-07-08)

Khác funnel_q3_2024.py đúng MỘT tầng: trước khi test cặp, trừ bỏ phần factor chung
(PCA 5 components fit trên returns 5-phút toàn universe — tái dùng V4
engine/phase1_cointegration/factor_residual.py). Johansen/gate chạy trên
RESIDUAL log-prices thay vì giá thô. HL 1-phút: residual chiếu bằng project_residual.

So sánh trực tiếp với kết quả giá thô: 52,326 cap -> FDR 3 -> gate 0.
"""
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(r"d:\Quant Finance\Pairs Trading Strategy")
sys.path.insert(0, str(ROOT / "Week 6"))

B5 = ROOT / "Week 4" / "data" / "validated" / "5min_phase1"
B1 = ROOT / "Week 4" / "data" / "validated" / "1min_phase2"
SPREAD_SUMMARY = ROOT / "Week 5" / "data" / "microstructure" / "spread_summary.parquet"
SPREADS_1MIN = ROOT / "Week 5" / "data" / "microstructure" / "spreads_1min.parquet"
OUT = ROOT / "Week 6" / "research_1min" / "results" / "funnel_q3_2024_residual"
ALIGNED_PATH = OUT / "aligned_residual_5min.parquet"

START, END = "2024-07-01", "2024-09-30"
K_AR_DIFF, DET = 12, 0
FDR_Q = 0.05
HL_MIN, HL_MAX = 2.0, 390.0
MIN_OVERLAP = 0.90
N_WORKERS = max(2, (os.cpu_count() or 8) - 2)
CHUNK = 250
N_FACTORS = 5

ETFS = {"SPY","QQQ","IWM","DIA","GLD","SLV","TLT","HYG","LQD","EEM","EFA","VNQ","IYR",
        "XLK","XLF","XLE","XLV","XLY","XLP","XLI","XLU","XLB","XLRE","XLC",
        "VGT","VTI","VOO","IVV","SMH","SOXX","KRE","KBE","XOP","MDY","RSP","XBI","IBB"}

_M = None
_COLS = None

def _init_worker(path):
    global _M, _COLS
    df = pd.read_parquet(path)
    _COLS = {c: i for i, c in enumerate(df.columns)}
    _M = df.to_numpy()

def _johansen(mat):
    from statsmodels.tsa.vector_ar.vecm import coint_johansen
    return coint_johansen(mat, det_order=DET, k_ar_diff=K_AR_DIFF)

def _test_chunk(args):
    from scipy.stats import chi2
    pairs, min_bars = args
    out = []
    for ta, tb in pairs:
        a = _M[:, _COLS[ta]]
        b = _M[:, _COLS[tb]]
        m = np.isfinite(a) & np.isfinite(b)
        n = int(m.sum())
        if n < min_bars:
            out.append((ta, tb, n) + (np.nan,) * 4)
            continue
        aa, bb = a[m], b[m]
        try:
            res = _johansen(np.column_stack([aa, bb]))
            trace = float(res.lr1[0])
            v = res.evec[:, 0]
            beta = float(-v[1] / v[0]) if abs(v[0]) > 1e-12 else np.nan
            pval = float(1.0 - chi2.cdf(trace, df=8))
            corr = float(np.corrcoef(np.diff(aa), np.diff(bb))[0, 1])
            out.append((ta, tb, n, trace, pval, beta, corr))
        except Exception:
            out.append((ta, tb, n) + (np.nan,) * 4)
    return out

def _gate_chunk(pairs):
    out = []
    for ta, tb in pairs:
        a = _M[:, _COLS[ta]]
        b = _M[:, _COLS[tb]]
        m = np.isfinite(a) & np.isfinite(b)
        aa, bb = a[m], b[m]
        h = len(aa) // 2
        try:
            r1 = _johansen(np.column_stack([aa[:h], bb[:h]]))
            ok1 = r1.lr1[0] > r1.cvt[0, 0]
            ok2 = False
            if ok1:
                r2 = _johansen(np.column_stack([aa[h:], bb[h:]]))
                ok2 = r2.lr1[0] > r2.cvt[0, 0]
            out.append((ta, tb, bool(ok1 and ok2)))
        except Exception:
            out.append((ta, tb, False))
    return out

def bh_fdr(pvals, q):
    p = np.asarray(pvals, dtype=float)
    n = len(p)
    order = np.argsort(p)
    ranked = p[order]
    ok = ranked <= q * np.arange(1, n + 1) / n
    if not ok.any():
        return np.zeros(n, dtype=bool)
    cut = ranked[np.max(np.nonzero(ok)[0])]
    return p <= cut

def robust_hl_minutes(x):
    xc = x - x.mean()
    c = [np.dot(xc[:-k] if k else xc, xc[k:] if k else xc) / len(xc) for k in range(11)]
    ck = np.array(c[1:11])
    if np.any(ck <= 0):
        return np.nan
    phi = np.exp(np.polyfit(np.arange(1, 11), np.log(ck), 1)[0])
    return -np.log(2) / np.log(phi) if 0 < phi < 1 else np.nan

def q3_median_half_spread(ticker):
    t = pq.read_table(
        SPREADS_1MIN,
        columns=["timestamp_et", "is_valid", "half_spread_l1_bps"],
        filters=[("ticker", "==", ticker)],
    ).to_pandas()
    t = t[(t["timestamp_et"] >= pd.Timestamp(START, tz="US/Eastern"))
          & (t["timestamp_et"] <= pd.Timestamp(END, tz="US/Eastern") + pd.Timedelta(days=1))
          & (t["is_valid"])]
    return float(t["half_spread_l1_bps"].median()) if len(t) else np.nan

def main():
    from engine.phase1_cointegration.factor_residual import fit_factor_model, project_residual
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    rep = []
    def say(s):
        print(s, flush=True)
        rep.append(s)

    # ---- Buoc 0: universe + factor model + residual matrix ----
    ss = pd.read_parquet(SPREAD_SUMMARY)
    cov_ok = sorted(ss.loc[ss["n_obs"] >= 0.95 * ss["n_obs"].max(), "ticker"])
    formation = {}
    for tck in cov_ok:
        f = B5 / f"{tck}.parquet"
        if f.exists():
            df = pd.read_parquet(f).loc[START:END]
            if len(df) > 0:
                formation[tck] = df
    say(f"BUOC 0: {len(formation)} ma vao factor model ...")
    W, ftickers, resid5, diag = fit_factor_model(formation, n_components=N_FACTORS)
    say(f"        PCA {N_FACTORS} factors: aligned T={diag['n_obs']} bar 5-min, "
        f"{diag['n_tickers_kept']} ma, cum_var={diag['cumulative_variance_explained']:.3f}")
    resid5.to_parquet(ALIGNED_PATH)
    keep = list(resid5.columns)
    pairs = list(combinations(keep, 2))
    say(f"        so cap = {len(pairs):,}")
    expected = len(resid5)
    min_bars = int(MIN_OVERLAP * expected)

    # ---- Buoc 1: Johansen tren residual ----
    say(f"BUOC 1: Johansen 5-min tren RESIDUAL, {N_WORKERS} workers ...")
    chunks = [(pairs[i:i + CHUNK], min_bars) for i in range(0, len(pairs), CHUNK)]
    rows = []
    with ProcessPoolExecutor(max_workers=N_WORKERS, initializer=_init_worker,
                             initargs=(str(ALIGNED_PATH),)) as ex:
        for ci, res in enumerate(ex.map(_test_chunk, chunks, chunksize=4)):
            rows.extend(res)
            if (ci + 1) % 40 == 0:
                say(f"        {min((ci+1)*CHUNK, len(pairs)):,}/{len(pairs):,} ({time.time()-t0:.0f}s)")
    df = pd.DataFrame(rows, columns=["ta", "tb", "n_bars", "trace", "pval", "beta", "corr"])
    tested = df["pval"].notna()
    say(f"        test duoc {tested.sum():,} cap")

    df["fdr_pass"] = False
    dft = df[tested]
    df.loc[dft.index, "fdr_pass"] = bh_fdr(dft["pval"].values, FDR_Q)
    n_fdr = int(df["fdr_pass"].sum())
    say(f"        dau p<=0.05 tho: {(dft['pval']<=0.05).sum():,} | dau BH-FDR q=0.05: {n_fdr:,}")

    # ---- Buoc 2: split gate ----
    gate_pairs = list(df.loc[df["fdr_pass"], ["ta", "tb"]].itertuples(index=False, name=None))
    say(f"BUOC 2: split-sample gate tren {len(gate_pairs):,} cap ...")
    gmap = {}
    if gate_pairs:
        gchunks = [gate_pairs[i:i + CHUNK] for i in range(0, len(gate_pairs), CHUNK)]
        with ProcessPoolExecutor(max_workers=N_WORKERS, initializer=_init_worker,
                                 initargs=(str(ALIGNED_PATH),)) as ex:
            for res in ex.map(_gate_chunk, gchunks, chunksize=2):
                for ta, tb, ok in res:
                    gmap[(ta, tb)] = ok
    df["gate_pass"] = df.apply(lambda r: gmap.get((r["ta"], r["tb"]), False), axis=1)
    n_gate = int(df["gate_pass"].sum())
    say(f"        dau ca 2 nua cv90: {n_gate:,} cap ({time.time()-t0:.0f}s)")

    # ---- Buoc 3: HL 1-min tren residual (project bang W formation) ----
    surv = df[df["gate_pass"]].copy()
    if len(surv):
        say(f"BUOC 3: project residual 1-min (nap {len(ftickers)} ma) ...")
        trading = {}
        for tck in ftickers:
            f = B1 / f"{tck}.parquet"
            if f.exists():
                s = pd.read_parquet(f, columns=["close"])["close"].loc[START:END]
                if len(s) > 0:
                    trading[tck] = pd.DataFrame({"log_close": np.log(s)})
        resid1 = project_residual(trading, W, ftickers)
        say(f"        residual 1-min: {len(resid1)} ma, T={len(next(iter(resid1.values())))}")
        hl_l, xd_l, amp_s, amp_p = [], [], [], []
        for r in surv.itertuples():
            pair_df = pd.concat({"a": resid1[r.ta], "b": resid1[r.tb]}, axis=1).dropna()
            sp = pair_df["a"].values - r.beta * pair_df["b"].values
            n_days = len(np.unique(pair_df.index.date))
            spc = sp - sp.mean()
            hl_l.append(robust_hl_minutes(sp))
            xd_l.append(float((np.diff(np.sign(spc)) != 0).sum()) / max(n_days, 1))
            amp_s.append(float(spc.std() * 1e4))
            amp_p.append(float(np.percentile(np.abs(spc), 95) * 1e4))
        surv["hl_min"] = hl_l
        surv["crossings_day"] = xd_l
        surv["amp_std_bps"] = amp_s
        surv["amp_p95_bps"] = amp_p
        surv["hl_band"] = (surv["hl_min"] >= HL_MIN) & (surv["hl_min"] <= HL_MAX)
        say(f"        HL trong [2, 390] phut: {int(surv['hl_band'].sum()):,}/{len(surv):,} cap")
    else:
        surv["hl_min"] = []
        surv["hl_band"] = []
        say("BUOC 3: khong co cap nao — bo qua")

    final = surv[surv.get("hl_band", pd.Series(dtype=bool)) == True].copy() if len(surv) else surv
    if len(final):
        cost_tickers = sorted(set(final["ta"]) | set(final["tb"]))
        say(f"        doc phi Q3 cho {len(cost_tickers)} ma ...")
        half = {t: q3_median_half_spread(t) for t in cost_tickers}
        final["half_A_bps"] = final["ta"].map(half)
        final["half_B_bps"] = final["tb"].map(half)
        final["cost_rt_bps"] = 2 * (final["half_A_bps"] + final["beta"].abs() * final["half_B_bps"])
        final["ratio_std"] = final["amp_std_bps"] / final["cost_rt_bps"]
        final["ratio_p95"] = final["amp_p95_bps"] / final["cost_rt_bps"]
        final["etf_leg"] = final["ta"].isin(ETFS) | final["tb"].isin(ETFS)
        final = final.sort_values("ratio_std", ascending=False)

    df.to_parquet(OUT / "pairs_all.parquet", index=False)
    final.to_csv(OUT / "survivors_ranked.csv", index=False)

    say("")
    say("============ KET QUA PHEU RESIDUAL Q3/2024 ============")
    say(f"(doi chieu gia tho:  52,326 -> FDR 3 -> gate 0)")
    say(f"residual: {tested.sum():,} cap -> FDR: {n_fdr:,} -> gate: {n_gate:,} -> HL band: {len(final):,}")
    if len(final):
        b = final["beta"]
        say(f"BETA: min {b.min():.2f} | median {b.median():.2f} | max {b.max():.2f} | beta<0: {(b<0).sum()} | |beta|>5: {(b.abs()>5).sum()}")
        say(f"CORR (residual returns): median {final['corr'].median():.2f}")
        say(f"HL: median {final['hl_min'].median():.0f}p | p5 {final['hl_min'].quantile(.05):.0f} | p95 {final['hl_min'].quantile(.95):.0f}")
        say(f"CAT MEAN/NGAY: median {final['crossings_day'].median():.1f}")
        say(f"RATIO std/cost: >=2x: {(final['ratio_std']>=2).sum()} | 1-2x: {((final['ratio_std']>=1)&(final['ratio_std']<2)).sum()} | <1x: {(final['ratio_std']<1).sum()}")
        viable = final[final["ratio_std"] >= 2]
        if len(viable):
            mx = pd.concat([viable["half_A_bps"], viable["half_B_bps"]]).max()
            say(f"SPREAD TOI DA con loi (ratio>=2): {mx:.1f} bps per-leg")
        cnt = pd.concat([final["ta"], final["tb"]]).value_counts()
        say("SO CAP MOI MA (top 10): " + ", ".join(f"{t}:{c}{'(ETF)' if t in ETFS else ''}" for t, c in cnt.head(10).items()))
        say(f"Cap co chan ETF: {int(final['etf_leg'].sum())}/{len(final)}")
        say("")
        say("TOP 20 theo ratio_std:")
        cols = ["ta", "tb", "beta", "hl_min", "crossings_day", "amp_std_bps", "cost_rt_bps", "ratio_std", "corr"]
        say(final[cols].head(20).to_string(index=False,
            formatters={"beta": "{:.2f}".format, "hl_min": "{:.0f}".format,
                        "crossings_day": "{:.1f}".format, "amp_std_bps": "{:.1f}".format,
                        "cost_rt_bps": "{:.1f}".format, "ratio_std": "{:.2f}".format,
                        "corr": "{:.2f}".format}))
    say(f"\ntong thoi gian: {time.time()-t0:.0f}s")
    (OUT / "report.txt").write_text("\n".join(rep), encoding="utf-8")

if __name__ == "__main__":
    main()
