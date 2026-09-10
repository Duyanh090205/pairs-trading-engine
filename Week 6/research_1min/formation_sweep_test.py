"""
SWEEP DO DAI FORMATION — tu NUA NGAY toi 20 ngay: cua so nao cho tin hieu
tuan-ke-tiep tot nhat?

Bien the ngan (0.5/1/2 ngay): Johansen tren bar 1-PHUT (du diem quan sat).
Bien the dai (3/5/10/15/20 ngay): Johansen tren bar 5-PHUT.
(Da chung minh synthetic: do chinh xac EG/Johansen bat bien theo thang bar.)

Cung tuan trade (5 ngay ke tiep, sim 1-min, |z|>2 vao lag-1, z cat 0 ra),
cung control boc tham. Vong tham do H1/2025.
LUAT PRE-COMMIT: chi bien the dat t>=2 VA t_diff>=2 vs control moi vao
vong xac nhan H2/2024. DU DOAN KHAI TRUOC: cua so ngan se chon cap co
"day thun lam bang nhieu bounce" -> trong-cua-so dep, tuan sau ~ control.
"""
import os
import time
from concurrent.futures import ProcessPoolExecutor
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(r"d:\Quant Finance\Pairs Trading Strategy")
B5 = ROOT / "Week 4" / "data" / "validated" / "5min_phase1"
B1 = ROOT / "Week 4" / "data" / "validated" / "1min_phase2"
SS = ROOT / "Week 5" / "data" / "microstructure" / "spread_summary.parquet"
OUT = ROOT / "Week 6" / "research_1min" / "results" / "formation_sweep"
M5_PATH, M1_PATH = OUT / "m5.parquet", OUT / "m1.parquet"

START, END = "2025-01-01", "2025-06-30"
# (ten, so_ngay, freq, so_bar_formation_neu_1min)
VARIANTS = [("0.5d", 0.5, "1min", 195), ("1d", 1, "1min", 390), ("2d", 2, "1min", 780),
            ("3d", 3, "5min", None), ("5d", 5, "5min", None), ("10d", 10, "5min", None),
            ("15d", 15, "5min", None), ("20d", 20, "5min", None)]
TRADE_DAYS = 5
N_UNIV = 100
K_AR = 12
Z_ENTRY = 2.0
N_CONTROL = 150
LAG = 1

_M = {}
_C = {}

def _init(p5, p1):
    global _M, _C
    for key, p in [("5min", p5), ("1min", p1)]:
        df = pd.read_parquet(p)
        _C[key] = {c: i for i, c in enumerate(df.columns)}
        _M[key] = df.to_numpy()

def _jo_chunk(args):
    from statsmodels.tsa.vector_ar.vecm import coint_johansen
    pairs, freq, i0, i1 = args
    M, C = _M[freq], _C[freq]
    out = []
    for ta, tb in pairs:
        a = M[i0:i1, C[ta]]
        b = M[i0:i1, C[tb]]
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

def sim_z(sp, mu, sd):
    z = (sp - mu) / sd
    n = len(z)
    trades, pos, entry = [], 0, 0.0
    for t in range(n - LAG - 1):
        if pos == 0:
            if z[t] > Z_ENTRY:
                pos, entry = -1, sp[t + LAG]
            elif z[t] < -Z_ENTRY:
                pos, entry = 1, sp[t + LAG]
        elif (pos == -1 and z[t] <= 0) or (pos == 1 and z[t] >= 0):
            trades.append(pos * (sp[t + LAG] - entry) * 1e4)
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

    m5 = pd.DataFrame({t: pd.read_parquet(B5 / f"{t}.parquet")["log_close"].loc[START:END]
                       for t in univ if (B5 / f"{t}.parquet").exists()}).dropna(how="all")
    m1 = pd.DataFrame({t: np.log(pd.read_parquet(B1 / f"{t}.parquet", columns=["close"])["close"].loc[START:END])
                       for t in univ if (B1 / f"{t}.parquet").exists()})
    univ = [t for t in univ if t in m5.columns and t in m1.columns]
    m5, m1 = m5[univ], m1[univ]
    m5.to_parquet(M5_PATH)
    m1.to_parquet(M1_PATH)
    days = sorted(set(m5.index.date))
    all_pairs = list(combinations(univ, 2))
    d5 = np.array([d for d in m5.index.date])
    d1 = np.array([d for d in m1.index.date])
    say(f"universe {len(univ)} | {len(days)} ngay | {len(all_pairs):,} cap")

    rng = np.random.default_rng(42)
    summary = []
    CH = 400
    MAX_F_DAYS = 20
    with ProcessPoolExecutor(max_workers=max(2, (os.cpu_count() or 8) - 2),
                             initializer=_init, initargs=(str(M5_PATH), str(M1_PATH))) as ex:
        for name, Fd, freq, fbars in VARIANTS:
            tF = time.time()
            sel_trades, ctl_trades = [], []
            n_sel_total = 0
            # cac tuan trade dong bo giua moi bien the: bat dau sau MAX_F_DAYS ngay
            starts = list(range(MAX_F_DAYS, len(days) - TRADE_DAYS + 1, TRADE_DAYS))
            for s in starts:
                tdays = days[s:s + TRADE_DAYS]
                tm1 = np.isin(d1, tdays)
                first_trade_pos1 = np.where(tm1)[0][0]
                if freq == "5min":
                    fdays = days[s - int(Fd):s]
                    fm = np.isin(d5, fdays)
                    idx = np.where(fm)[0]
                    i0, i1 = idx[0], idx[-1] + 1
                else:
                    i1 = first_trade_pos1
                    i0 = max(0, i1 - fbars)
                chunks = [(all_pairs[i:i + CH], freq, i0, i1) for i in range(0, len(all_pairs), CH)]
                sel = []
                for r in ex.map(_jo_chunk, chunks, chunksize=2):
                    sel.extend(r)
                n_sel_total += len(sel)

                # formation 1-min slice (de tinh mu/sd + beta control)
                f1 = m1.iloc[max(0, first_trade_pos1 - (fbars or int(Fd) * 390)):first_trade_pos1]
                t1 = m1[tm1]

                ctl_idx = rng.choice(len(all_pairs), N_CONTROL, replace=False)
                ctl = []
                for j in ctl_idx:
                    ta, tb = all_pairs[j]
                    va = f1[ta].diff().values
                    vb = f1[tb].diff().values
                    mm = np.isfinite(va) & np.isfinite(vb)
                    if mm.sum() < 100:
                        continue
                    b_ = np.polyfit(vb[mm], va[mm], 1)[0]
                    if 0 < abs(b_) <= 5:
                        ctl.append((ta, tb, float(abs(b_))))

                for group, sink in [(sel, sel_trades), (ctl, ctl_trades)]:
                    for ta, tb, beta in group:
                        spf = (f1[ta] - beta * f1[tb]).dropna().values
                        if len(spf) < 100:
                            continue
                        sp = (t1[ta] - beta * t1[tb]).ffill().bfill().values
                        if not np.all(np.isfinite(sp)):
                            continue
                        cost = 2 * (half.get(ta, np.nan) + beta * half.get(tb, np.nan))
                        sink.extend((g, cost) for g in sim_z(sp, spf.mean(), spf.std()))

            g = np.array([x[0] for x in sel_trades])
            c = np.array([x[0] for x in ctl_trades])
            if len(g) > 10 and len(c) > 10:
                mg, sg = g.mean(), g.std() / np.sqrt(len(g))
                mc, sc = c.mean(), c.std() / np.sqrt(len(c))
                tdiff = (mg - mc) / np.sqrt(sg**2 + sc**2)
                costm = np.nanmedian([x[1] for x in sel_trades])
                summary.append(dict(F=name, freq=freq, n=len(g), gross=mg, se=sg,
                                    t=mg / sg, ctl=mc, t_diff=tdiff, cost=costm,
                                    net=mg - costm, sel=n_sel_total))
                say(f"[F={name:>5} {freq}] chon {n_sel_total:>6,} | N={len(g):>6,} | "
                    f"gop {mg:+6.2f}±{sg:.2f} (t={mg/sg:+.1f}) | ctl {mc:+6.2f} | "
                    f"t_diff {tdiff:+.1f} | net {mg-costm:+6.1f} ({time.time()-tF:.0f}s)")
            else:
                say(f"[F={name:>5}] khong du trade (sel={n_sel_total})")

    say("")
    say("========= SWEEP FORMATION 0.5d -> 20d (tham do H1/2025) =========")
    say(f"{'F':>6} {'bar':>6} {'N':>7} {'gop bp':>12} {'t':>6} {'ctl':>7} {'t_diff':>7} {'NET':>7}")
    for r in summary:
        say(f"{r['F']:>6} {r['freq']:>6} {r['n']:>7,} {r['gross']:>+9.2f}±{r['se']:.2f} "
            f"{r['t']:>+6.1f} {r['ctl']:>+7.2f} {r['t_diff']:>+7.1f} {r['net']:>+7.1f}")
    winners = [r["F"] for r in summary if r["t"] >= 2 and r["t_diff"] >= 2]
    say(f"\nLUAT PRE-COMMIT (t>=2 va t_diff>=2): dat chuan = {winners if winners else 'KHONG BIEN THE NAO'}")
    pd.DataFrame(summary).to_csv(OUT / "sweep_summary.csv", index=False)
    say(f"tong: {time.time()-t0:.0f}s")
    (OUT / "report.txt").write_text("\n".join(rep), encoding="utf-8")

if __name__ == "__main__":
    main()
