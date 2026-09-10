"""
TANG 1 — Quet min formation window tren H2/2024 (data DA CHAY, dung de tham do)

6 bien the, TAT CA tren bar 1-phut:
  fixed 390 (1d) / 585 (1.5d) / 780 (2d) / 1170 (3d) / 1560 (4d)
  + ADAPTIVE: 780 * (vol_126phien / vol_10phien), kep [390, 1560]
    (vol = median toan universe cua std(returns 1-min) * sqrt(390), nhat hoa)

Cung pipeline: Johansen cv95 (0<beta<=5) tren cua so hoc -> tuan ke tiep trade
z-score (|z|>2 vao lag-1-close, z cat 0 ra) + control boc tham.
LUAT: xep theo NET; can t>=2 & t_diff>=2; hoa -> chon cua so dai hon.
"""
import os
import time
from concurrent.futures import ProcessPoolExecutor
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(r"d:\Quant Finance\Pairs Trading Strategy")
B1 = ROOT / "Week 4" / "data" / "validated" / "1min_phase2"
SS = ROOT / "Week 5" / "data" / "microstructure" / "spread_summary.parquet"
OUT = ROOT / "Week 6" / "research_1min" / "results" / "window_opt_stage1"
M1_PATH = OUT / "m1c.parquet"

HIST_START = "2024-01-02"       # du runway cho vol baseline (126 phien)
TRADE_START, END = "2024-07-01", "2024-12-31"
FIXED = [390, 585, 780, 1170, 1560]
CLIP_LO, CLIP_HI = 390, 1560
TRADE_DAYS = 5
N_UNIV = 100
K_AR = 12
Z_ENTRY = 2.0
N_CONTROL = 150

_M = None
_C = None

def _init(path):
    global _M, _C
    df = pd.read_parquet(path)
    _C = {c: i for i, c in enumerate(df.columns)}
    _M = df.to_numpy()

def _jo_chunk(args):
    from statsmodels.tsa.vector_ar.vecm import coint_johansen
    pairs, i0, i1 = args
    out = []
    for ta, tb in pairs:
        a = _M[i0:i1, _C[ta]]
        b = _M[i0:i1, _C[tb]]
        m = np.isfinite(a) & np.isfinite(b)
        if m.sum() < 0.8 * (i1 - i0):
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

def sim_z(z, sp):
    n = len(z)
    trades, pos, entry = [], 0, 0.0
    for t in range(n - 2):
        if pos == 0:
            if z[t] > Z_ENTRY:
                pos, entry = -1, sp[t + 1]
            elif z[t] < -Z_ENTRY:
                pos, entry = 1, sp[t + 1]
        elif (pos == -1 and z[t] <= 0) or (pos == 1 and z[t] >= 0):
            trades.append(pos * (sp[t + 1] - entry) * 1e4)
            pos = 0
    if pos != 0:
        trades.append(pos * (sp[-1] - entry) * 1e4)
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

    m1 = pd.DataFrame({t: np.log(pd.read_parquet(B1 / f"{t}.parquet", columns=["close"])["close"].loc[HIST_START:END])
                       for t in univ if (B1 / f"{t}.parquet").exists()})
    univ = list(m1.columns)
    m1.to_parquet(M1_PATH)
    days = sorted(set(m1.index.date))
    d1 = np.array([d for d in m1.index.date])
    all_pairs = list(combinations(univ, 2))

    # vol nhat hoa moi phien (median universe)
    rets = m1.diff()
    daily_vol = rets.groupby(d1).std().median(axis=1) * np.sqrt(390)
    daily_vol.index = pd.Index(sorted(set(d1)))
    say(f"universe {len(univ)} | {len(days)} phien (co runway) | {len(all_pairs):,} cap")

    trade_days_all = [d for d in days if d >= pd.Timestamp(TRADE_START).date()]
    first_trade_day_idx = days.index(trade_days_all[0])
    starts = list(range(first_trade_day_idx, len(days) - TRADE_DAYS + 1, TRADE_DAYS))

    rng = np.random.default_rng(42)
    CH = 400
    res = {}
    adapt_windows = []
    VARIANTS = [(str(f), f) for f in FIXED] + [("adaptive", None)]
    for name, _ in VARIANTS:
        res[(name, "sel")] = []
        res[(name, "ctl")] = []

    with ProcessPoolExecutor(max_workers=max(2, (os.cpu_count() or 8) - 2),
                             initializer=_init, initargs=(str(M1_PATH),)) as ex:
        for s in starts:
            tdays = days[s:s + TRADE_DAYS]
            tm = np.isin(d1, tdays)
            first = np.where(tm)[0][0]
            t1 = m1[tm]

            # adaptive window cho tuan nay (chi dung qua khu)
            past_days = [d for d in days if d < tdays[0]]
            v10 = daily_vol.loc[past_days[-10:]].median()
            v126 = daily_vol.loc[past_days[-126:]].median()
            wa = int(np.clip(780 * (v126 / v10), CLIP_LO, CLIP_HI))
            adapt_windows.append(wa)

            # control chung (beta tu 780 bar)
            fwin = m1.iloc[max(0, first - 780):first]
            ctl_idx = rng.choice(len(all_pairs), N_CONTROL, replace=False)
            ctl = []
            for j in ctl_idx:
                ta, tb = all_pairs[j]
                va, vb = fwin[ta].diff().values, fwin[tb].diff().values
                mm = np.isfinite(va) & np.isfinite(vb)
                if mm.sum() < 100:
                    continue
                b_ = np.polyfit(vb[mm], va[mm], 1)[0]
                if 0 < abs(b_) <= 5:
                    ctl.append((ta, tb, float(abs(b_))))

            for name, fbars in VARIANTS:
                nb = wa if fbars is None else fbars
                i0 = max(0, first - nb)
                chunks = [(all_pairs[i:i + CH], i0, first) for i in range(0, len(all_pairs), CH)]
                sel = []
                for r in ex.map(_jo_chunk, chunks, chunksize=2):
                    sel.extend(r)
                f1 = m1.iloc[i0:first]
                for group, tag in [(sel, "sel"), (ctl, "ctl")]:
                    for ta, tb, beta in group:
                        spf = (f1[ta] - beta * f1[tb]).dropna().values
                        if len(spf) < 100:
                            continue
                        sp = (t1[ta] - beta * t1[tb]).ffill().bfill().values
                        if not np.all(np.isfinite(sp)):
                            continue
                        z = (sp - spf.mean()) / spf.std()
                        cost = 2 * (half.get(ta, np.nan) + beta * half.get(tb, np.nan))
                        res[(name, tag)].extend((g, cost) for g in sim_z(z, sp))
            say(f"[{tdays[0]}] adaptive={wa} bar | xong 6 bien the ({time.time()-t0:.0f}s)")

    say("")
    say("========= TANG 1: QUET MIN WINDOW (H2/2024, bar 1-min) =========")
    say(f"{'window':>9} {'N':>7} {'gop bp':>12} {'t':>6} {'ctl':>7} {'t_diff':>7} {'NET':>7}")
    rows = []
    for name, _ in VARIANTS:
        g = np.array([x[0] for x in res[(name, "sel")]])
        c = np.array([x[0] for x in res[(name, "ctl")]])
        if len(g) < 10:
            say(f"{name:>9} khong du trade")
            continue
        mg, sg = g.mean(), g.std() / np.sqrt(len(g))
        mc, sc = c.mean(), c.std() / np.sqrt(len(c))
        tdiff = (mg - mc) / np.sqrt(sg**2 + sc**2)
        costm = np.nanmedian([x[1] for x in res[(name, "sel")]])
        net = mg - costm
        rows.append(dict(window=name, n=len(g), gross=mg, se=sg, t=mg / sg,
                         t_diff=tdiff, cost=costm, net=net))
        say(f"{name:>9} {len(g):>7,} {mg:>+9.2f}±{sg:.2f} {mg/sg:>+6.1f} {mc:>+7.2f} {tdiff:>+7.1f} {net:>+7.1f}")
    aw = np.array(adapt_windows)
    say(f"\nadaptive da chon window: min {aw.min()} | median {np.median(aw):.0f} | max {aw.max()} bar")
    qual = [r for r in rows if r["t"] >= 2 and r["t_diff"] >= 2]
    if qual:
        best = sorted(qual, key=lambda r: (-r["net"], -({"390":390,"585":585,"780":780,"1170":1170,"1560":1560,"adaptive":0}[r["window"]])))[0]
        say(f"LUAT (net cao nhat, du t>=2 & t_diff>=2): QUAN QUAN TANG 1 = {best['window']} (net {best['net']:+.1f})")
    else:
        say("LUAT: khong bien the nao dat chuan")
    pd.DataFrame(rows).to_csv(OUT / "stage1_summary.csv", index=False)
    say(f"tong: {time.time()-t0:.0f}s")
    (OUT / "report.txt").write_text("\n".join(rep), encoding="utf-8")

if __name__ == "__main__":
    main()
