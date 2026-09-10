"""
TEST DO BEN CUC BO (local persistence) — thang 1-phut, walk-forward TUAN
Cau hoi: quan he hoc tu 5 ngay gan nhat co con song o 5 ngay ke tiep khong?

3 nhanh, cung data (2025-01 -> 2025-06, ~24 tuan, top-100 ma thanh khoan + ETF):
  (a) COINT-TUAN : Johansen tren tuan formation (5-min) -> tuan sau trade z-score
  (b) TWIN-EVENT : twin = corr 1-min cao nhat tuan formation -> tuan sau trade
                   su kien spread giat >3sigma, giu 60 phut
  (c) CONTROL    : cap boc tham ngau nhien, trade y het (a) va (b)

Thuoc do: bps GOP moi trade o tuan KE TIEP (out-of-window, lag 1 bar).
Neu (a)/(b) ~ (c): do ben cuc bo = 0 -> moi engine adaptive chi duoi nhieu.
"""
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(r"d:\Quant Finance\Pairs Trading Strategy")
sys.path.insert(0, str(ROOT / "Week 6"))
B5 = ROOT / "Week 4" / "data" / "validated" / "5min_phase1"
B1 = ROOT / "Week 4" / "data" / "validated" / "1min_phase2"
SS = ROOT / "Week 5" / "data" / "microstructure" / "spread_summary.parquet"
OUT = ROOT / "Week 6" / "research_1min" / "results" / "adaptive_persistence"
M5_PATH = OUT / "m5.parquet"

START, END = "2025-01-01", "2025-06-30"
N_UNIV = 100
K_AR = 12
Z_ENTRY, Z_EXIT = 2.0, 0.0
EVENT_K, EVENT_HOLD = 3.0, 60
N_CONTROL = 150
LAG = 1
rng = np.random.default_rng(42)

_M5 = None
_C5 = None

def _init(path):
    global _M5, _C5
    df = pd.read_parquet(path)
    _C5 = {c: i for i, c in enumerate(df.columns)}
    _M5 = df.to_numpy()

def _jo_chunk(args):
    """Johansen tren lat cua so formation [i0:i1) cho chunk cap."""
    from statsmodels.tsa.vector_ar.vecm import coint_johansen
    pairs, i0, i1 = args
    out = []
    for ta, tb in pairs:
        a = _M5[i0:i1, _C5[ta]]
        b = _M5[i0:i1, _C5[tb]]
        m = np.isfinite(a) & np.isfinite(b)
        if m.sum() < 300:
            continue
        try:
            r = coint_johansen(np.column_stack([a[m], b[m]]), det_order=0, k_ar_diff=K_AR)
            if r.lr1[0] > r.cvt[0, 1]:
                v = r.evec[:, 0]
                if abs(v[0]) > 1e-12:
                    beta = -v[1] / v[0]
                    if 0 < beta <= 5:
                        out.append((ta, tb, float(beta)))
        except Exception:
            pass
    return out

def sim_zscore(spread_1m, mu, sd, day_ids):
    """Vao |z|>2 (fill lag 1 bar), ra z cat 0 hoac het tuan. Tra list bps gop."""
    z = (spread_1m - mu) / sd
    n = len(z)
    trades, pos, entry = [], 0, 0.0
    for t in range(n - LAG - 1):
        if pos == 0:
            if z[t] > Z_ENTRY:
                pos, entry = -1, spread_1m[t + LAG]
            elif z[t] < -Z_ENTRY:
                pos, entry = 1, spread_1m[t + LAG]
        else:
            if (pos == -1 and z[t] <= Z_EXIT) or (pos == 1 and z[t] >= -Z_EXIT):
                trades.append(pos * (spread_1m[t + LAG] - entry) * 1e4)
                pos = 0
    if pos != 0:
        trades.append(pos * (spread_1m[-1] - entry) * 1e4)
    return trades

def sim_event(spread_1m, sig5, day_start, day_end):
    """Vao nguoc cu giat >3sigma (lag 1), giu 60 phut hoac het ngay."""
    n = len(spread_1m)
    r5 = spread_1m - np.roll(spread_1m, 5)
    r5[:5] = np.nan
    trades, last = [], -10**9
    for t in range(n - LAG - 1):
        if t - last < 30 or not np.isfinite(r5[t]) or sig5 <= 0:
            continue
        if t - day_start[t] < 35 or day_end[t] - t < EVENT_HOLD + LAG:
            continue
        if abs(r5[t]) > EVENT_K * sig5:
            last = t
            sgn = -np.sign(r5[t])
            e_in = spread_1m[t + LAG]
            e_out = spread_1m[min(t + LAG + EVENT_HOLD, day_end[t])]
            trades.append(sgn * (e_out - e_in) * 1e4)
    return trades

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    rep = []
    def say(s):
        print(s, flush=True)
        rep.append(s)

    ss = pd.read_parquet(SS)
    ok = ss[ss["n_obs"] >= 0.95 * ss["n_obs"].max()].nsmallest(N_UNIV, "median_bps")
    univ = sorted(ok["ticker"])
    half = dict(zip(ss["ticker"], ss["median_bps"] / 2.0))

    m5 = pd.DataFrame({t: pd.read_parquet(B5 / f"{t}.parquet")["log_close"].loc[START:END]
                       for t in univ if (B5 / f"{t}.parquet").exists()}).dropna(how="all")
    m1 = pd.DataFrame({t: np.log(pd.read_parquet(B1 / f"{t}.parquet", columns=["close"])["close"].loc[START:END])
                       for t in univ if (B1 / f"{t}.parquet").exists()})
    univ = [t for t in univ if t in m5.columns and t in m1.columns]
    m5, m1 = m5[univ], m1[univ]
    m5.to_parquet(M5_PATH)
    say(f"universe {len(univ)} ma | 5-min {len(m5)} bar | 1-min {len(m1)} bar")

    # tuan giao dich
    days = sorted(set(m5.index.date))
    weeks = [days[i:i + 5] for i in range(0, len(days) - 9, 5)]
    say(f"{len(weeks)} cua so tuan (formation) -> trade tuan ke tiep")

    d1dates = np.array([d for d in m1.index.date])
    day_pos = {}
    for i, d in enumerate(d1dates):
        day_pos.setdefault(d, [i, i])[1] = i

    all_pairs = list(combinations(univ, 2))
    CH = 400
    res = {"coint": [], "twin": [], "ctl_z": [], "ctl_ev": []}
    n_sel = {"coint": 0, "twin": 0}

    with ProcessPoolExecutor(max_workers=max(2, (os.cpu_count() or 8) - 2),
                             initializer=_init, initargs=(str(M5_PATH),)) as ex:
        for w, fdays in enumerate(weeks):
            tdays = days[days.index(fdays[-1]) + 1: days.index(fdays[-1]) + 6]
            if len(tdays) < 3:
                break
            f_mask5 = np.isin(m5.index.date, fdays)
            i0, i1 = np.where(f_mask5)[0][[0, -1]]
            f_mask1 = np.isin(m1.index.date, fdays)
            t_mask1 = np.isin(m1.index.date, tdays)

            # ---- (a) coint tuan ----
            chunks = [(all_pairs[i:i + CH], i0, i1 + 1) for i in range(0, len(all_pairs), CH)]
            sel = []
            for r in ex.map(_jo_chunk, chunks, chunksize=2):
                sel.extend(r)
            n_sel["coint"] += len(sel)

            # ---- (b) twin theo corr 1-min formation ----
            f1 = m1[f_mask1]
            rets = f1.diff()
            corr = rets.corr(min_periods=300)
            np.fill_diagonal(corr.values, np.nan)
            twins = []
            seen = set()
            for tck in univ:
                if tck not in corr.columns:
                    continue
                best = corr[tck].idxmax()
                if pd.isna(best):
                    continue
                key = tuple(sorted((tck, best)))
                if key in seen:
                    continue
                seen.add(key)
                va, vb = rets[key[0]].values, rets[key[1]].values
                mm = np.isfinite(va) & np.isfinite(vb)
                if mm.sum() < 300:
                    continue
                beta = np.polyfit(vb[mm], va[mm], 1)[0]
                if 0 < beta <= 5:
                    twins.append((key[0], key[1], float(beta)))
            n_sel["twin"] += len(twins)

            # ---- (c) control ----
            ctl_idx = rng.choice(len(all_pairs), N_CONTROL, replace=False)
            ctl = []
            for j in ctl_idx:
                ta, tb = all_pairs[j]
                va, vb = rets[ta].values, rets[tb].values
                mm = np.isfinite(va) & np.isfinite(vb)
                if mm.sum() < 300:
                    continue
                beta = np.polyfit(vb[mm], va[mm], 1)[0]
                if 0 < abs(beta) <= 5:
                    ctl.append((ta, tb, float(abs(beta))))

            # ---- sim tuan ke tiep ----
            t1 = m1[t_mask1]
            tdates = np.array([d for d in t1.index.date])
            uniq = sorted(set(tdates))
            ds = np.zeros(len(t1), dtype=np.int64)
            de = np.zeros(len(t1), dtype=np.int64)
            for d in uniq:
                w_ = np.where(tdates == d)[0]
                ds[w_] = w_[0]
                de[w_] = w_[-1]

            def run_group(group, mode, sink):
                for ta, tb, beta in group:
                    fa, fb = m1.loc[f_mask1, ta].values, m1.loc[f_mask1, tb].values
                    sa, sb = t1[ta].values, t1[tb].values
                    mm = np.isfinite(sa) & np.isfinite(sb)
                    if mm.sum() < 0.7 * len(sa):
                        continue
                    sp_f = fa - beta * fb
                    sp_f = sp_f[np.isfinite(sp_f)]
                    if len(sp_f) < 300:
                        continue
                    sp = np.where(mm, sa - beta * sb, np.nan)
                    sp = pd.Series(sp).ffill().bfill().values
                    cost = 2 * (half.get(ta, np.nan) + beta * half.get(tb, np.nan))
                    if mode == "z":
                        trades = sim_zscore(sp, sp_f.mean(), sp_f.std(), None)
                    else:
                        s5 = np.diff(sp_f)
                        sig5 = np.nanstd(s5) * np.sqrt(5)
                        trades = sim_event(sp, sig5, ds, de)
                    sink.extend((g, cost) for g in trades)

            run_group(sel, "z", res["coint"])
            run_group(twins, "ev", res["twin"])
            run_group(ctl, "z", res["ctl_z"])
            run_group(ctl, "ev", res["ctl_ev"])
            say(f"[tuan {w+1:02d}] coint {len(sel):>4} cap | twin {len(twins):>3} | "
                f"trades luy ke: a={len(res['coint'])}, b={len(res['twin'])}, "
                f"c_z={len(res['ctl_z'])}, c_ev={len(res['ctl_ev'])} ({time.time()-t0:.0f}s)")

    say("")
    say("===== DO BEN CUC BO — bps GOP moi trade o tuan KE TIEP =====")
    say(f"{'nhanh':>28} {'N trade':>8} {'gop bp/trade':>13} {'t-stat':>7} {'hit%':>6} {'phi median':>11} {'NET bp':>8}")
    for name, key in [("(a) coint-tuan -> z-score", "coint"),
                      ("(c) control cung luat (a)", "ctl_z"),
                      ("(b) twin-corr -> event", "twin"),
                      ("(c) control cung luat (b)", "ctl_ev")]:
        rows = res[key]
        if not rows:
            say(f"{name:>28} {'0':>8}")
            continue
        g = np.array([r[0] for r in rows])
        c = np.array([r[1] for r in rows])
        m, se = g.mean(), g.std() / np.sqrt(len(g))
        say(f"{name:>28} {len(g):>8,} {m:>+10.2f}±{se:.2f} {m/se:>+7.1f} "
            f"{100*(g>0).mean():>5.1f}% {np.nanmedian(c):>9.1f}bp {m-np.nanmedian(c):>+8.1f}")
    say(f"\n(a) chon {n_sel['coint']:,} luot cap coint / {len(weeks)} tuan | (b) {n_sel['twin']:,} luot twin")
    say(f"tong: {time.time()-t0:.0f}s")
    (OUT / "report.txt").write_text("\n".join(rep), encoding="utf-8")

if __name__ == "__main__":
    main()
