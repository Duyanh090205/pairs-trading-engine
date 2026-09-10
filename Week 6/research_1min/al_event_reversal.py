"""
EVENT STUDY — hoi-co-dieu-kien sau cu giat residual (tu duy MINUTE-NATIVE)

Cau hoi: sau khi residual X_i (da tru 5 PCA factor) giat manh trong 5 phut
(|dX_5min| > k*sigma, sigma trailing khong look-ahead), gia co HOI trong
5/15/30/60/120 phut tiep theo khong, trung binh bao nhieu bps?

Khac phieu cu (tu duy daily): khong doi quan he can bang 3 thang; chi do
phan ung SAU SU KIEN — dung cai mid-freq desk trade.

Thiet ke chong bias:
  - residual OUT-OF-FIT (W fit nua dau quy, do nua sau) — nhu robustness sweep
  - sigma trailing 2 ngay, shift 1 bar (chi dung qua khu)
  - bo 30 phut dau phien; su kien phai con >=120 bar trong phien (cung event set
    cho moi horizon); refractory 30 phut/ma (khong dem cascade)
  - quet TAT CA 14 cua so quy 2022Q1-2025Q2 (duoi OOS van khoa)

So sanh: reversion bps vs phi round-trip thuc ~12-16bps.
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
OUT = ROOT / "Week 6" / "research_1min" / "results" / "al_event_reversal"

KS = [3.0, 4.0, 5.0]
HORIZONS = [5, 15, 30, 60, 120]
SIG_WIN = 780          # trailing 2 phien cho sigma cua dX_1min
WARMUP = 30            # bo 30 phut dau phien
REFRACT = 30           # phut giua 2 su kien cung ma
SHOCK_LAG = 5          # cu giat do tren 5 phut

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

def collect_events(x: pd.Series, results: dict):
    """x: residual log-price 1-min. Ghi (shock_bps, rev_bps per horizon) vao results[k]."""
    arr = x.values
    n = len(arr)
    if n < SIG_WIN + 200:
        return
    dates = x.index.date
    # vi tri bat dau/ket thuc phien
    day_change = np.empty(n, dtype=bool)
    day_change[0] = True
    day_change[1:] = dates[1:] != dates[:-1]
    day_start_idx = np.where(day_change)[0]
    day_start = np.maximum.accumulate(np.where(day_change, np.arange(n), 0))
    day_end = np.empty(n, dtype=np.int64)
    ends = np.append(day_start_idx[1:] - 1, n - 1)
    for s0, e0 in zip(day_start_idx, ends):
        day_end[s0:e0 + 1] = e0

    d1 = np.diff(arr, prepend=arr[0])
    sig1 = pd.Series(d1).rolling(SIG_WIN, min_periods=390).std().shift(1).values
    sig5 = sig1 * np.sqrt(SHOCK_LAG)
    r5 = arr - np.roll(arr, SHOCK_LAG)
    r5[:SHOCK_LAG] = np.nan
    # cu giat khong duoc vat qua dem: t-5 cung phien
    same_day = day_start == np.roll(day_start, SHOCK_LAG)
    z = np.abs(r5) / sig5
    ok = (np.isfinite(z) & same_day
          & (np.arange(n) - day_start >= WARMUP + SHOCK_LAG)
          & (day_end - np.arange(n) >= HORIZONS[-1]))
    for k in KS:
        idxs = np.where(ok & (z > k))[0]
        last = -10**9
        for i in idxs:
            if i - last < REFRACT:
                continue
            last = i
            sgn = np.sign(r5[i])
            row = [abs(r5[i]) * 1e4]
            for h in HORIZONS:
                row.append(float(-sgn * (arr[i + h] - arr[i]) * 1e4))
            results[k].append(row)

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

    results = {k: [] for k in KS}
    for wname, ws, we in QUARTERS:
        mid = (pd.Timestamp(ws) + (pd.Timestamp(we) - pd.Timestamp(ws)) / 2).strftime("%Y-%m-%d")
        formation = {t: df.loc[ws:mid] for t, df in d5.items() if len(df.loc[ws:mid]) > 100}
        try:
            W, ftickers, _, diag = fit_factor_model(formation, n_components=5)
        except ValueError as e:
            say(f"[{wname}] fit fail: {e}")
            continue
        trading = {}
        for tck in ftickers:
            sl = d1[tck].loc[mid:we]
            if len(sl) > 500:
                trading[tck] = pd.DataFrame({"log_close": sl})
        resid = project_residual(trading, W, ftickers)
        n_ev_before = len(results[KS[0]])
        for tck, x in resid.items():
            if tck not in ETFS:
                collect_events(x, results)
        say(f"[{wname}] +{len(results[KS[0]]) - n_ev_before:,} su kien k=3 ({time.time()-t0:.0f}s)")

    say("")
    say("========== EVENT STUDY: HOI SAU CU GIAT RESIDUAL (14 quy, out-of-fit) ==========")
    say("(rev > 0 = HOI ve; rev < 0 = tiep tuc truot. SE = sai so chuan cua mean)")
    say(f"{'k':>4} {'N su kien':>10} {'shock median':>13} | " +
        " | ".join(f"{'rev@'+str(h)+'p':>18}" for h in HORIZONS))
    rows_csv = []
    for k in KS:
        arr = np.array(results[k])
        if len(arr) == 0:
            say(f"{k:>4} {'0':>10}")
            continue
        n = len(arr)
        shock_med = np.median(arr[:, 0])
        cells = []
        for j, h in enumerate(HORIZONS):
            rev = arr[:, 1 + j]
            m, se = rev.mean(), rev.std() / np.sqrt(n)
            pos = 100 * (rev > 0).mean()
            cells.append(f"{m:+7.2f}±{se:4.2f} ({pos:2.0f}%+)")
            rows_csv.append({"k": k, "h": h, "n": n, "mean_rev_bps": m, "se": se,
                             "pct_pos": pos, "shock_med_bps": shock_med})
        say(f"{k:>4} {n:>10,} {shock_med:>10.1f}bp | " + " | ".join(f"{c:>18}" for c in cells))
    pd.DataFrame(rows_csv).to_csv(OUT / "event_reversal_summary.csv", index=False)
    say("")
    say("Tham chieu: phi round-trip thuc (1 ma + hedge) ~ 12-16 bps.")
    say(f"tong: {time.time()-t0:.0f}s")
    (OUT / "report.txt").write_text("\n".join(rep), encoding="utf-8")

if __name__ == "__main__":
    main()
