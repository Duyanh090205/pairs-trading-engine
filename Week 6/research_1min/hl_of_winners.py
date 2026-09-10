"""
HL CUA CAC CAP DUOC CHON boi bien the 2-NGAY (quan quan vong xac nhan) — H2/2024

Do 3 thu cho moi cap duoc chon moi tuan:
  1. HL (estimator khang nhieu, log-ACF k=1..10) tren CUA SO HOC (780 bar 1-min)
  2. HL tren TUAN TRADE ke tiep (out-of-window) — con so trung thuc
  3. Thoi gian giu lenh thuc te cua tung trade (vao |z|>2, ra z cat 0, lag 1)
     + ty le lenh bi ep dong cuoi tuan (chua kip hoi)
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
OUT = ROOT / "Week 6" / "research_1min" / "results" / "hl_of_winners"
M1_PATH = OUT / "m1c.parquet"

START, END = "2024-07-01", "2024-12-31"
FBARS = 780
TRADE_DAYS = 5
N_UNIV = 100
K_AR = 12
Z_ENTRY = 2.0

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

def robust_hl(x):
    xc = x - x.mean()
    c = [np.dot(xc[:-k] if k else xc, xc[k:] if k else xc) / len(xc) for k in range(11)]
    ck = np.array(c[1:11])
    if np.any(ck <= 0):
        return np.nan
    phi = np.exp(np.polyfit(np.arange(1, 11), np.log(ck), 1)[0])
    return -np.log(2) / np.log(phi) if 0 < phi < 1 else np.nan

def sim_durations(z, sp):
    """Tra ve (pnl_bps, duration_min, forced) cho tung trade."""
    n = len(z)
    out, pos, entry, t_in = [], 0, 0.0, 0
    for t in range(n - 2):
        if pos == 0:
            if z[t] > Z_ENTRY:
                pos, entry, t_in = -1, sp[t + 1], t
            elif z[t] < -Z_ENTRY:
                pos, entry, t_in = 1, sp[t + 1], t
        elif (pos == -1 and z[t] <= 0) or (pos == 1 and z[t] >= 0):
            out.append((pos * (sp[t + 1] - entry) * 1e4, t - t_in, 0))
            pos = 0
    if pos != 0:
        out.append((pos * (sp[-1] - entry) * 1e4, n - 1 - t_in, 1))
    return out

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
    m1 = pd.DataFrame({t: np.log(pd.read_parquet(B1 / f"{t}.parquet", columns=["close"])["close"].loc[START:END])
                       for t in univ if (B1 / f"{t}.parquet").exists()})
    univ = list(m1.columns)
    m1.to_parquet(M1_PATH)
    days = sorted(set(m1.index.date))
    d1 = np.array([d for d in m1.index.date])
    all_pairs = list(combinations(univ, 2))
    say(f"universe {len(univ)} | {len(days)} ngay | bien the 2d (780 bar)")

    hl_form, hl_trade, durs, pnls, forced = [], [], [], [], []
    CH = 400
    with ProcessPoolExecutor(max_workers=max(2, (os.cpu_count() or 8) - 2),
                             initializer=_init, initargs=(str(M1_PATH),)) as ex:
        starts = list(range(10, len(days) - TRADE_DAYS + 1, TRADE_DAYS))
        for s in starts:
            tdays = days[s:s + TRADE_DAYS]
            tm = np.isin(d1, tdays)
            first = np.where(tm)[0][0]
            i0 = max(0, first - FBARS)
            chunks = [(all_pairs[i:i + CH], i0, first) for i in range(0, len(all_pairs), CH)]
            sel = []
            for r in ex.map(_jo_chunk, chunks, chunksize=2):
                sel.extend(r)
            f1 = m1.iloc[i0:first]
            t1 = m1[tm]
            for ta, tb, beta in sel:
                spf = (f1[ta] - beta * f1[tb]).dropna().values
                if len(spf) < 100:
                    continue
                spt = (t1[ta] - beta * t1[tb]).ffill().bfill().values
                if not np.all(np.isfinite(spt)):
                    continue
                hl_form.append(robust_hl(spf))
                hl_trade.append(robust_hl(spt))
                z = (spt - spf.mean()) / spf.std()
                for pnl, dur, fc in sim_durations(z, spt):
                    pnls.append(pnl)
                    durs.append(dur)
                    forced.append(fc)
            say(f"[{tdays[0]}] chon {len(sel)} cap ({time.time()-t0:.0f}s)")

    hf = np.array(hl_form)
    ht = np.array(hl_trade)
    du = np.array(durs, dtype=float)
    pn = np.array(pnls)
    fc = np.array(forced)
    say("")
    say("========== HL & THOI GIAN GIU LENH — bien the 2d, H2/2024 ==========")
    q = lambda a, p: np.nanpercentile(a, p)
    say(f"HL spread TRONG CUA SO HOC (780 bar):  p25 {q(hf,25):.0f}p | median {q(hf,50):.0f}p | p75 {q(hf,75):.0f}p | NaN {np.isnan(hf).mean()*100:.0f}%")
    say(f"HL spread O TUAN TRADE (out-of-win):   p25 {q(ht,25):.0f}p | median {q(ht,50):.0f}p | p75 {q(ht,75):.0f}p | NaN {np.isnan(ht).mean()*100:.0f}%")
    say("")
    say(f"THOI GIAN GIU LENH ({len(du):,} trades):")
    say(f"  p25 {q(du,25):.0f} phut | median {q(du,50):.0f} phut | p75 {q(du,75):.0f} phut | p95 {q(du,95):.0f} phut")
    say(f"  lenh bi ep dong cuoi tuan (chua hoi kip): {100*fc.mean():.1f}%")
    say(f"  pnl lenh tu-hoi: {pn[fc==0].mean():+.2f} bp | pnl lenh bi ep dong: {pn[fc==1].mean():+.2f} bp")
    win = pn > 0
    say(f"  hit rate: {100*win.mean():.1f}% | thang tb {pn[win].mean():+.1f} bp | thua tb {pn[~win].mean():+.1f} bp")
    say(f"\ntong: {time.time()-t0:.0f}s")
    (OUT / "report.txt").write_text("\n".join(rep), encoding="utf-8")

if __name__ == "__main__":
    main()
