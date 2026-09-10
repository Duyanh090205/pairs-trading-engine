"""
VONG XAC NHAN — thi lai 3 mon cho tin hieu coint-cua-so-ngan (0.5d/1d/2d, 1-min)

Mon 1: DATA MOI H2/2024 (2024-07-01 -> 2024-12-31), y nguyen tham so vong tham do
       -> phai dat lai t>=2 va t_diff>=2 (lag1, fill close)
Mon 2: LAG 2 va 3 bar -> phai giu >=60% lai gop so voi lag1 (gate da pre-commit)
Mon 3: FILL bang gia MO CUA bar ke tiep -> phai giu >=60% so voi fill close
       (rot mon nay = lai la artifact nhieu bounce qua gia dong cua)

Khong chinh tham so. Control boc tham chay qua CUNG 4 che do fill.
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
OUT = ROOT / "Week 6" / "research_1min" / "results" / "confirmation_h2_2024"
M1_PATH = OUT / "m1c.parquet"

START, END = "2024-07-01", "2024-12-31"
VARIANTS = [("0.5d", 195), ("1d", 390), ("2d", 780)]
MODES = ["lag1_close", "lag2_close", "lag3_close", "lag1_open"]
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

def sim(z, fills, max_shift):
    """Vao |z|>2, fill = fills[t] (da dich san theo mode); ra z cat 0."""
    n = len(z)
    trades, pos, entry = [], 0, 0.0
    for t in range(n - max_shift - 1):
        if not np.isfinite(fills[t]):
            continue
        if pos == 0:
            if z[t] > Z_ENTRY:
                pos, entry = -1, fills[t]
            elif z[t] < -Z_ENTRY:
                pos, entry = 1, fills[t]
        elif (pos == -1 and z[t] <= 0) or (pos == 1 and z[t] >= 0):
            trades.append(pos * (fills[t] - entry) * 1e4)
            pos = 0
    if pos != 0:
        last = fills[n - max_shift - 1]
        if np.isfinite(last):
            trades.append(pos * (last - entry) * 1e4)
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

    mc, mo = {}, {}
    for t in univ:
        f = B1 / f"{t}.parquet"
        if f.exists():
            df = pd.read_parquet(f, columns=["open", "close"]).loc[START:END]
            if len(df) > 0:
                mc[t] = np.log(df["close"])
                mo[t] = np.log(df["open"])
    m1c = pd.DataFrame(mc)
    m1o = pd.DataFrame(mo)
    univ = list(m1c.columns)
    m1c.to_parquet(M1_PATH)
    days = sorted(set(m1c.index.date))
    d1 = np.array([d for d in m1c.index.date])
    all_pairs = list(combinations(univ, 2))
    say(f"universe {len(univ)} | {len(days)} ngay H2/2024 | {len(all_pairs):,} cap")

    rng = np.random.default_rng(42)
    CH = 400
    results = {}   # (variant, mode, group) -> list (bps, cost)
    for v, _ in VARIANTS:
        for md in MODES:
            results[(v, md, "sel")] = []
            results[(v, md, "ctl")] = []

    with ProcessPoolExecutor(max_workers=max(2, (os.cpu_count() or 8) - 2),
                             initializer=_init, initargs=(str(M1_PATH),)) as ex:
        starts = list(range(10, len(days) - TRADE_DAYS + 1, TRADE_DAYS))
        for s in starts:
            tdays = days[s:s + TRADE_DAYS]
            tm = np.isin(d1, tdays)
            first_pos = np.where(tm)[0][0]
            t1c, t1o = m1c[tm], m1o[tm]

            # control chung cho moi variant (beta tu 780 bar cuoi)
            fwin = m1c.iloc[max(0, first_pos - 780):first_pos]
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

            for vname, fbars in VARIANTS:
                i1 = first_pos
                i0 = max(0, i1 - fbars)
                chunks = [(all_pairs[i:i + CH], i0, i1) for i in range(0, len(all_pairs), CH)]
                sel = []
                for r in ex.map(_jo_chunk, chunks, chunksize=2):
                    sel.extend(r)
                f1 = m1c.iloc[i0:i1]

                for group, tag in [(sel, "sel"), (ctl, "ctl")]:
                    for ta, tb, beta in group:
                        spf = (f1[ta] - beta * f1[tb]).dropna().values
                        if len(spf) < 100:
                            continue
                        spc = (t1c[ta] - beta * t1c[tb]).ffill().bfill().values
                        spo = (t1o[ta] - beta * t1o[tb]).ffill().bfill().values
                        if not (np.all(np.isfinite(spc)) and np.all(np.isfinite(spo))):
                            continue
                        z = (spc - spf.mean()) / spf.std()
                        cost = 2 * (half.get(ta, np.nan) + beta * half.get(tb, np.nan))
                        n = len(spc)
                        fills = {
                            "lag1_close": np.append(spc[1:], np.nan),
                            "lag2_close": np.append(spc[2:], [np.nan] * 2),
                            "lag3_close": np.append(spc[3:], [np.nan] * 3),
                            "lag1_open": np.append(spo[1:], np.nan),
                        }
                        for md in MODES:
                            trades = sim(z, fills[md], 3)
                            results[(vname, md, tag)].extend((g, cost) for g in trades)
            say(f"[tuan bat dau {tdays[0]}] xong ({time.time()-t0:.0f}s)")

    say("")
    say("========== VONG XAC NHAN H2/2024 ==========")
    say(f"{'F':>5} {'mode':>11} {'N':>7} {'gop bp':>12} {'t':>6} {'ctl':>7} {'t_diff':>7} {'NET':>7}")
    summary = {}
    for vname, _ in VARIANTS:
        for md in MODES:
            g = np.array([x[0] for x in results[(vname, md, "sel")]])
            c = np.array([x[0] for x in results[(vname, md, "ctl")]])
            if len(g) < 10:
                say(f"{vname:>5} {md:>11} khong du trade")
                continue
            mg, sg = g.mean(), g.std() / np.sqrt(len(g))
            mcm, scm = c.mean(), c.std() / np.sqrt(len(c))
            tdiff = (mg - mcm) / np.sqrt(sg**2 + scm**2)
            costm = np.nanmedian([x[1] for x in results[(vname, md, "sel")]])
            summary[(vname, md)] = (mg, sg, tdiff)
            say(f"{vname:>5} {md:>11} {len(g):>7,} {mg:>+9.2f}±{sg:.2f} {mg/sg:>+6.1f} "
                f"{mcm:>+7.2f} {tdiff:>+7.1f} {mg-costm:>+7.1f}")

    say("")
    say("----- CHAM DIEM (luat pre-commit) -----")
    for vname, _ in VARIANTS:
        base = summary.get((vname, "lag1_close"))
        if not base:
            continue
        mg, sg, tdiff = base
        m1_pass = (mg / sg >= 2) and (tdiff >= 2)
        l2 = summary.get((vname, "lag2_close"), (np.nan,) * 3)[0]
        l3 = summary.get((vname, "lag3_close"), (np.nan,) * 3)[0]
        m2_pass = np.isfinite(l2) and mg > 0 and (l2 >= 0.6 * mg)
        op = summary.get((vname, "lag1_open"), (np.nan,) * 3)[0]
        m3_pass = np.isfinite(op) and mg > 0 and (op >= 0.6 * mg)
        say(f"{vname}: Mon1(data moi) {'DAU' if m1_pass else 'ROT'} "
            f"| Mon2(lag2 giu {100*l2/mg if mg else 0:.0f}%, lag3 {100*l3/mg if mg else 0:.0f}%) {'DAU' if m2_pass else 'ROT'} "
            f"| Mon3(open-fill giu {100*op/mg if mg else 0:.0f}%) {'DAU' if m3_pass else 'ROT'}")
    say(f"\ntong: {time.time()-t0:.0f}s")
    (OUT / "report.txt").write_text("\n".join(rep), encoding="utf-8")

if __name__ == "__main__":
    main()
