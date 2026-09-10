"""
EVENT STUDY — MO RIENG DUOI PHAN BO: cu giat cang LON thi sao?

Nhu al_event_reversal.py nhung ghi z-score cua tung su kien, roi bucket:
  [3,4) | [4,5) | [5,7) | [7,10) | [10,+inf)
Do reversion 5/15/30/60/120 phut cho TUNG nac rieng biet.
14 quy 2022Q1-2025Q2, residual out-of-fit, sigma trailing, refractory 30p.
"""
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(r"d:\Quant Finance\Pairs Trading Strategy")
sys.path.insert(0, str(ROOT / "Week 6"))

B5 = ROOT / "Week 4" / "data" / "validated" / "5min_phase1"
B1 = ROOT / "Week 4" / "data" / "validated" / "1min_phase2"
SPREAD_SUMMARY = ROOT / "Week 5" / "data" / "microstructure" / "spread_summary.parquet"
OUT = ROOT / "Week 6" / "research_1min" / "results" / "al_event_reversal_tails"

HORIZONS = [5, 15, 30, 60, 120]
SIG_WIN, WARMUP, REFRACT, SHOCK_LAG = 780, 30, 30, 5
BUCKETS = [(3, 4), (4, 5), (5, 7), (7, 10), (10, np.inf)]

ETFS = {"SPY","QQQ","IWM","DIA","GLD","SLV","TLT","HYG","LQD","EEM","EFA","VNQ","IYR",
        "XLK","XLF","XLE","XLV","XLY","XLP","XLI","XLU","XLB","XLRE","XLC",
        "VGT","VTI","VOO","IVV","SMH","SOXX","KRE","KBE","XOP","MDY","RSP","XBI","IBB"}

QUARTERS = []
for y in [2022, 2023, 2024, 2025]:
    for q, (s, e) in enumerate([("01-01", "03-31"), ("04-01", "06-30"),
                                ("07-01", "09-30"), ("10-01", "12-31")], 1):
        if y == 2025 and q > 2:
            break
        QUARTERS.append((f"{y}Q{q}", f"{y}-{s}", f"{y}-{e}"))

def collect(x: pd.Series, sink: list, tkr: str, wname: str):
    arr = x.values
    n = len(arr)
    if n < SIG_WIN + 200:
        return
    dates = x.index.date
    day_change = np.empty(n, dtype=bool)
    day_change[0] = True
    day_change[1:] = dates[1:] != dates[:-1]
    day_start = np.maximum.accumulate(np.where(day_change, np.arange(n), 0))
    day_start_idx = np.where(day_change)[0]
    day_end = np.empty(n, dtype=np.int64)
    ends = np.append(day_start_idx[1:] - 1, n - 1)
    for s0, e0 in zip(day_start_idx, ends):
        day_end[s0:e0 + 1] = e0

    d1 = np.diff(arr, prepend=arr[0])
    sig1 = pd.Series(d1).rolling(SIG_WIN, min_periods=390).std().shift(1).values
    sig5 = sig1 * np.sqrt(SHOCK_LAG)
    r5 = arr - np.roll(arr, SHOCK_LAG)
    r5[:SHOCK_LAG] = np.nan
    same_day = day_start == np.roll(day_start, SHOCK_LAG)
    z = np.abs(r5) / sig5
    ok = (np.isfinite(z) & same_day
          & (np.arange(n) - day_start >= WARMUP + SHOCK_LAG)
          & (day_end - np.arange(n) >= HORIZONS[-1]))
    idxs = np.where(ok & (z > 3.0))[0]
    last = -10**9
    for i in idxs:
        if i - last < REFRACT:
            continue
        last = i
        sgn = np.sign(r5[i])
        revs = [float(-sgn * (arr[i + h] - arr[i]) * 1e4) for h in HORIZONS]
        sink.append((wname, tkr, float(z[i]), float(abs(r5[i]) * 1e4), *revs))

def main():
    from engine.phase1_cointegration.factor_residual import fit_factor_model, project_residual
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    rep = []
    def say(s):
        print(s, flush=True)
        rep.append(s)

    ss = pd.read_parquet(SPREAD_SUMMARY)
    cov_ok = sorted(ss.loc[ss["n_obs"] >= 0.95 * ss["n_obs"].max(), "ticker"])
    say(f"nap data {len(cov_ok)} ma ...")
    d5, d1 = {}, {}
    for tck in cov_ok:
        f5, f1 = B5 / f"{tck}.parquet", B1 / f"{tck}.parquet"
        if f5.exists() and f1.exists():
            d5[tck] = pd.read_parquet(f5)
            d1[tck] = np.log(pd.read_parquet(f1, columns=["close"])["close"])
    say(f"nap xong ({time.time()-t0:.0f}s)")

    sink = []
    for wname, ws, we in QUARTERS:
        mid = (pd.Timestamp(ws) + (pd.Timestamp(we) - pd.Timestamp(ws)) / 2).strftime("%Y-%m-%d")
        formation = {t: df.loc[ws:mid] for t, df in d5.items() if len(df.loc[ws:mid]) > 100}
        try:
            W, ftickers, _, _ = fit_factor_model(formation, n_components=5)
        except ValueError as e:
            say(f"[{wname}] fit fail: {e}")
            continue
        trading = {}
        for tck in ftickers:
            sl = d1[tck].loc[mid:we]
            if len(sl) > 500:
                trading[tck] = pd.DataFrame({"log_close": sl})
        resid = project_residual(trading, W, ftickers)
        before = len(sink)
        for tck, x in resid.items():
            if tck not in ETFS:
                collect(x, sink, tck, wname)
        say(f"[{wname}] +{len(sink)-before:,} su kien ({time.time()-t0:.0f}s)")

    cols = ["window", "ticker", "z", "shock_bps"] + [f"rev{h}" for h in HORIZONS]
    df = pd.DataFrame(sink, columns=cols)
    df.to_parquet(OUT / "events_all.parquet", index=False)

    say("")
    say("===== REVERSION THEO NAC CU GIAT (14 quy, out-of-fit) =====")
    say(f"{'nac z':>10} {'N':>8} {'shock med':>10} | " +
        " | ".join(f"{'rev@'+str(h)+'p':>15}" for h in HORIZONS))
    for lo, hi in BUCKETS:
        b = df[(df["z"] >= lo) & (df["z"] < hi)]
        if len(b) == 0:
            say(f"[{lo},{hi}) : 0 su kien")
            continue
        n = len(b)
        cells = []
        for h in HORIZONS:
            rev = b[f"rev{h}"]
            m, se = rev.mean(), rev.std() / np.sqrt(n)
            cells.append(f"{m:+7.2f}±{se:5.2f}")
        say(f"[{lo:>2},{'inf' if np.isinf(hi) else int(hi):>3}) {n:>8,} {b['shock_bps'].median():>8.1f}bp | " +
            " | ".join(f"{c:>15}" for c in cells))
    big = df[df["z"] >= 10].nlargest(12, "shock_bps")
    if len(big):
        say("")
        say("12 cu giat z>=10 LON NHAT (soi tay xem co phai glitch/tin that):")
        say(big[["window", "ticker", "z", "shock_bps", "rev5", "rev30", "rev120"]].to_string(
            index=False, formatters={"z": "{:.1f}".format, "shock_bps": "{:.0f}".format,
                                     "rev5": "{:+.0f}".format, "rev30": "{:+.0f}".format,
                                     "rev120": "{:+.0f}".format}))
    say(f"\ntong: {time.time()-t0:.0f}s")
    (OUT / "report.txt").write_text("\n".join(rep), encoding="utf-8")

if __name__ == "__main__":
    main()
