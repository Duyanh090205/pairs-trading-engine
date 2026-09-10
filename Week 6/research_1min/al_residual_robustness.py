"""
Robustness sweep — A-L single-name residual diagnostic tren TAT CA cua so quy
2022Q1 -> 2025Q2 (14 cua so; DUOI 2025-07 -> 2026-03 DA KHOA, khong dung).

Moi cua so: fit W (PCA 5) tren NUA DAU (5-min returns) -> project residual
NUA SAU (1-min, out-of-fit) -> per-stock: HL robust, bien do vs rolling-mean
1 ngay, so lan cat, ratio vs phi tham chieu.

Theo doi rieng 7 ma mep-band cua Q3/2024: TGT NFLX AMD UBER PCAR MMM SRE.
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
OUT = ROOT / "Week 6" / "research_1min" / "results" / "al_residual_robustness"

ROLL = 390
HEDGE_BPS = 3.0
HL_MIN, HL_MAX = 2.0, 390.0
WATCH = ["TGT", "NFLX", "AMD", "UBER", "PCAR", "MMM", "SRE"]

ETFS = {"SPY","QQQ","IWM","DIA","GLD","SLV","TLT","HYG","LQD","EEM","EFA","VNQ","IYR",
        "XLK","XLF","XLE","XLV","XLY","XLP","XLI","XLU","XLB","XLRE","XLC",
        "VGT","VTI","VOO","IVV","SMH","SOXX","KRE","KBE","XOP","MDY","RSP","XBI","IBB"}

QUARTERS = []
for y in [2022, 2023, 2024, 2025]:
    for q, (s, e) in enumerate([("01-01", "03-31"), ("04-01", "06-30"),
                                ("07-01", "09-30"), ("10-01", "12-31")], 1):
        if y == 2025 and q > 2:
            break  # duoi 2025-07+ da khoa
        QUARTERS.append((f"{y}Q{q}", f"{y}-{s}", f"{y}-{e}"))

def robust_hl_minutes(v):
    xc = v - v.mean()
    c = [np.dot(xc[:-k] if k else xc, xc[k:] if k else xc) / len(xc) for k in range(11)]
    ck = np.array(c[1:11])
    if np.any(ck <= 0):
        return np.nan
    phi = np.exp(np.polyfit(np.arange(1, 11), np.log(ck), 1)[0])
    return -np.log(2) / np.log(phi) if 0 < phi < 1 else np.nan

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
    half = dict(zip(ss["ticker"], ss["median_bps"] / 2.0))

    say(f"nap toan bo 5-min + 1-min cho {len(cov_ok)} ma ...")
    d5, d1 = {}, {}
    for tck in cov_ok:
        f5, f1 = B5 / f"{tck}.parquet", B1 / f"{tck}.parquet"
        if f5.exists() and f1.exists():
            d5[tck] = pd.read_parquet(f5)
            s = pd.read_parquet(f1, columns=["close"])["close"]
            d1[tck] = np.log(s)
    say(f"nap xong {len(d5)} ma ({time.time()-t0:.0f}s)")

    summary, watch_rows, band_names = [], [], {}
    per_window_frames = []
    for wname, ws, we in QUARTERS:
        mid = (pd.Timestamp(ws) + (pd.Timestamp(we) - pd.Timestamp(ws)) / 2).strftime("%Y-%m-%d")
        formation = {}
        for tck, df in d5.items():
            sl = df.loc[ws:mid]
            if len(sl) > 100:
                formation[tck] = sl
        if len(formation) < 50:
            say(f"[{wname}] bo qua — thieu ma ({len(formation)})")
            continue
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

        rows = []
        for tck, x in resid.items():
            if tck in ETFS:
                continue
            v = x.values
            hl = robust_hl_minutes(v)
            rm = x.rolling(ROLL, min_periods=60).mean()
            dev = (x - rm).dropna()
            if len(dev) < 1000:
                continue
            d = dev.values
            nd = len(np.unique(dev.index.date))
            amp = float(d.std() * 1e4)
            xd = float((np.diff(np.sign(d)) != 0).sum()) / max(nd, 1)
            h = half.get(tck, np.nan)
            cost = 2 * h + HEDGE_BPS if np.isfinite(h) else np.nan
            rows.append((wname, tck, hl, amp, xd, cost, amp / cost if cost else np.nan))
        wdf = pd.DataFrame(rows, columns=["window", "ticker", "hl_min", "amp_std_bps",
                                          "crossings_day", "cost_rt_bps", "ratio_std"])
        per_window_frames.append(wdf)
        band = wdf[(wdf["hl_min"] >= HL_MIN) & (wdf["hl_min"] <= HL_MAX)]
        for tck in band["ticker"]:
            band_names.setdefault(tck, []).append(wname)
        summary.append({
            "window": wname, "cum_var": round(diag["cumulative_variance_explained"], 3),
            "n_stocks": len(wdf), "hl_p25": wdf["hl_min"].quantile(.25),
            "hl_median": wdf["hl_min"].median(), "hl_p75": wdf["hl_min"].quantile(.75),
            "n_band": len(band), "band_ratio_ge2": int((band["ratio_std"] >= 2).sum()),
            "amp_median": wdf["amp_std_bps"].median(),
        })
        for tck in WATCH:
            r = wdf[wdf["ticker"] == tck]
            watch_rows.append((wname, tck, float(r["hl_min"].iloc[0]) if len(r) else np.nan))
        say(f"[{wname}] {len(wdf)} ma | HL median {wdf['hl_min'].median():.0f}p | trong band: {len(band)} | cum_var {diag['cumulative_variance_explained']:.2f} ({time.time()-t0:.0f}s)")

    sm = pd.DataFrame(summary)
    all_windows = pd.concat(per_window_frames, ignore_index=True)
    all_windows.to_parquet(OUT / "per_name_all_windows.parquet", index=False)
    sm.to_csv(OUT / "summary_by_window.csv", index=False)

    say("")
    say("========== ROBUSTNESS 14 CUA SO (out-of-fit, stocks only) ==========")
    say(sm.to_string(index=False, formatters={
        "hl_p25": "{:.0f}".format, "hl_median": "{:.0f}".format,
        "hl_p75": "{:.0f}".format, "amp_median": "{:.1f}".format}))
    say("")
    say(f"tong so ma tung vao band [2,390p]: {len(band_names)} (tren {sm['n_stocks'].max()} ma x {len(sm)} cua so)")
    stable = {t: ws for t, ws in band_names.items() if len(ws) >= 2}
    say(f"ma vao band >=2 cua so: {len(stable)}")
    for t, ws in sorted(stable.items(), key=lambda kv: -len(kv[1]))[:15]:
        say(f"  {t}: {len(ws)} lan — {', '.join(ws)}")
    say("")
    say("7 ma mep-band Q3/2024 — HL (phut) qua cac cua so:")
    wdf = pd.DataFrame(watch_rows, columns=["window", "ticker", "hl_min"])
    piv = wdf.pivot(index="ticker", columns="window", values="hl_min")
    say(piv.to_string(float_format=lambda v: f"{v:.0f}" if np.isfinite(v) else "-"))
    say(f"\ntong: {time.time()-t0:.0f}s")
    (OUT / "report.txt").write_text("\n".join(rep), encoding="utf-8")

if __name__ == "__main__":
    main()
