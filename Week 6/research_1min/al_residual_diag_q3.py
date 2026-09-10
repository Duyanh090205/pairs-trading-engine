"""
Diagnostic Avellaneda-Lee single-name residual — Q3/2024 (2026-07-08)

Câu hỏi: residual X_i (log-price đã trừ 5 PCA factor) của TỪNG MÃ có
mean-revert ở thang phút-giờ với biên độ đáng tiền không? KHÔNG có cặp,
KHÔNG có cointegration test.

Chống bias in-sample: 2 pass —
  OUT-OF-FIT (số trung thực): fit W trên NỬA ĐẦU Q3 (5-min), đo X_i trên NỬA SAU (1-min)
  IN-FIT     (trần lạc quan): fit W trên CẢ Q3, đo trên CẢ Q3

Per mã: HL robust (log-ACF slope k=1..10, đơn vị phút) trên X_i thô;
biên độ & số lần cắt so với ROLLING MEAN 390 bar (1 ngày) — mô phỏng cách
s-score dùng cửa sổ cuốn chiếu; phí tham chiếu = 2*half_spread + 3bps hedge.
(half_spread lấy từ spread_summary toàn kỳ — hơi đắt hơn Q3 thật, hướng bảo thủ.)
"""
import os
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
OUT = ROOT / "Week 6" / "research_1min" / "results" / "al_residual_diag_q3"

Q3_START, Q3_END = "2024-07-01", "2024-09-30"
H1_END, H2_START = "2024-08-15", "2024-08-16"
ROLL = 390          # 1 phien
HEDGE_BPS = 3.0     # phí chân hedge tham chiếu (ETF/basket)
HL_MIN, HL_MAX = 2.0, 390.0

ETFS = {"SPY","QQQ","IWM","DIA","GLD","SLV","TLT","HYG","LQD","EEM","EFA","VNQ","IYR",
        "XLK","XLF","XLE","XLV","XLY","XLP","XLI","XLU","XLB","XLRE","XLC",
        "VGT","VTI","VOO","IVV","SMH","SOXX","KRE","KBE","XOP","MDY","RSP","XBI","IBB"}

def robust_hl_minutes(x):
    xc = x - x.mean()
    c = [np.dot(xc[:-k] if k else xc, xc[k:] if k else xc) / len(xc) for k in range(11)]
    ck = np.array(c[1:11])
    if np.any(ck <= 0):
        return np.nan
    phi = np.exp(np.polyfit(np.arange(1, 11), np.log(ck), 1)[0])
    return -np.log(2) / np.log(phi) if 0 < phi < 1 else np.nan

def per_name_metrics(x: pd.Series):
    v = x.values
    hl = robust_hl_minutes(v)
    rm = x.rolling(ROLL, min_periods=60).mean()
    dev = (x - rm).dropna()
    if len(dev) < 1000:
        return hl, np.nan, np.nan, np.nan
    d = dev.values
    n_days = len(np.unique(dev.index.date))
    amp_std = float(d.std() * 1e4)
    amp_p95 = float(np.percentile(np.abs(d), 95) * 1e4)
    crossings = float((np.diff(np.sign(d)) != 0).sum()) / max(n_days, 1)
    return hl, amp_std, amp_p95, crossings

def run_pass(name, fit_start, fit_end, meas_start, meas_end, l1_cache, say):
    from engine.phase1_cointegration.factor_residual import fit_factor_model, project_residual
    ss = pd.read_parquet(SPREAD_SUMMARY)
    cov_ok = sorted(ss.loc[ss["n_obs"] >= 0.95 * ss["n_obs"].max(), "ticker"])
    formation = {}
    for tck in cov_ok:
        f = B5 / f"{tck}.parquet"
        if f.exists():
            df = pd.read_parquet(f).loc[fit_start:fit_end]
            if len(df) > 0:
                formation[tck] = df
    W, ftickers, _, diag = fit_factor_model(formation, n_components=5)
    say(f"[{name}] fit W: T={diag['n_obs']} bar 5-min, {diag['n_tickers_kept']} ma, cum_var={diag['cumulative_variance_explained']:.3f}")

    trading = {}
    for tck in ftickers:
        s = l1_cache.get(tck)
        if s is None:
            continue
        sl = s.loc[meas_start:meas_end]
        if len(sl) > 0:
            trading[tck] = pd.DataFrame({"log_close": sl})
    resid = project_residual(trading, W, ftickers)
    say(f"[{name}] residual 1-min: {len(resid)} ma, T={len(next(iter(resid.values())))}")

    rows = []
    for tck, x in resid.items():
        hl, a_s, a_p, xd = per_name_metrics(x)
        rows.append((tck, hl, a_s, a_p, xd))
    df = pd.DataFrame(rows, columns=["ticker", "hl_min", "amp_std_bps", "amp_p95_bps", "crossings_day"])

    half = dict(zip(ss["ticker"], ss["median_bps"] / 2.0))
    df["half_bps"] = df["ticker"].map(half)
    df["cost_rt_bps"] = 2 * df["half_bps"] + HEDGE_BPS
    df["ratio_std"] = df["amp_std_bps"] / df["cost_rt_bps"]
    df["etf"] = df["ticker"].isin(ETFS)
    df["hl_band"] = (df["hl_min"] >= HL_MIN) & (df["hl_min"] <= HL_MAX)
    return df

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    rep = []
    def say(s):
        print(s, flush=True)
        rep.append(s)

    ss = pd.read_parquet(SPREAD_SUMMARY)
    cov_ok = sorted(ss.loc[ss["n_obs"] >= 0.95 * ss["n_obs"].max(), "ticker"])
    say(f"nap 1-min cho {len(cov_ok)} ma ...")
    l1 = {}
    for tck in cov_ok:
        f = B1 / f"{tck}.parquet"
        if f.exists():
            s = pd.read_parquet(f, columns=["close"])["close"].loc[Q3_START:Q3_END]
            if len(s) > 0:
                l1[tck] = np.log(s)
    say(f"nap xong {len(l1)} ma ({time.time()-t0:.0f}s)")

    oof = run_pass("OUT-OF-FIT", Q3_START, H1_END, H2_START, Q3_END, l1, say)
    inf = run_pass("IN-FIT", Q3_START, Q3_END, Q3_START, Q3_END, l1, say)
    oof.to_csv(OUT / "out_of_fit.csv", index=False)
    inf.to_csv(OUT / "in_fit.csv", index=False)

    say("")
    say("=========== DIAGNOSTIC A-L SINGLE-NAME RESIDUAL, Q3/2024 ===========")
    for name, df in [("OUT-OF-FIT (so trung thuc)", oof), ("IN-FIT (tran lac quan)", inf)]:
        stk = df[~df["etf"]]
        say(f"--- {name}: {len(stk)} co phieu (ETF tach rieng: {df['etf'].sum()}) ---")
        say(f"  HL: p25 {stk['hl_min'].quantile(.25):.0f}p | median {stk['hl_min'].median():.0f}p | p75 {stk['hl_min'].quantile(.75):.0f}p | NaN/drift: {stk['hl_min'].isna().sum()}")
        say(f"  HL trong [2,390p]: {int(stk['hl_band'].sum())}/{len(stk)} ma")
        say(f"  bien do (std vs rolling-mean 1 ngay): median {stk['amp_std_bps'].median():.1f} bps | p75 {stk['amp_std_bps'].quantile(.75):.1f}")
        say(f"  cat mean/ngay: median {stk['crossings_day'].median():.1f}")
        say(f"  phi tham chieu: median {stk['cost_rt_bps'].median():.1f} bps")
        say(f"  RATIO amp/cost: >=2x: {(stk['ratio_std']>=2).sum()} ma | 1-2x: {((stk['ratio_std']>=1)&(stk['ratio_std']<2)).sum()} | <1x: {(stk['ratio_std']<1).sum()}")
        band = stk[stk["hl_band"]]
        say(f"  TRONG HL-BAND: {len(band)} ma — ratio>=2x: {(band['ratio_std']>=2).sum()} | 1-2x: {((band['ratio_std']>=1)&(band['ratio_std']<2)).sum()}")
        say("")

    stk = oof[~oof["etf"]]
    good = stk[stk["hl_band"]].sort_values("ratio_std", ascending=False)
    say("TOP 20 (out-of-fit, trong HL band, theo ratio):")
    say(good.head(20)[["ticker", "hl_min", "amp_std_bps", "crossings_day", "cost_rt_bps", "ratio_std"]].to_string(
        index=False, formatters={"hl_min": "{:.0f}".format, "amp_std_bps": "{:.1f}".format,
                                 "crossings_day": "{:.1f}".format, "cost_rt_bps": "{:.1f}".format,
                                 "ratio_std": "{:.2f}".format}))
    say(f"\ntong: {time.time()-t0:.0f}s")
    (OUT / "report.txt").write_text("\n".join(rep), encoding="utf-8")

if __name__ == "__main__":
    main()
