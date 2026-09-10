"""
TEST EDGE 1-PHUT HO THU HAI: INTRADAY MOMENTUM (Gao-Han-Li-Zhou 2018 JFE)

Tin hieu: return 30 phut dau phien (2 bien the: co gap qua dem / khong)
Trade:    15:30 vao lenh theo DAU cua tin hieu, 16:00 dong -> 1 trade/ngay
Cong cu:  SPY, QQQ, IWM (spread hep nhat thi truong)
Data:     1-min validated 2022-01 -> 2026-03 (~1060 ngay)

Phi: 2 kich ban — median full-spread tu Week 5 (bao thu) va 1bps (thuc te
SPY thuong quote 1 cent ~ 0.2-0.5bps; so Week 5 co the phong dai voi ETF).

Ghi chu phuong phap: KHONG toi uu tham so — dung dung spec cua paper
(first 30min -> last 30min). Bao cao gross/net, hit rate, t-stat, theo nam.
"""
import numpy as np
import pandas as pd
from pathlib import Path

ROOT = Path(r"d:\Quant Finance\Pairs Trading Strategy")
B1 = ROOT / "Week 4" / "data" / "validated" / "1min_phase2"
SS = ROOT / "Week 5" / "data" / "microstructure" / "spread_summary.parquet"
OUT = ROOT / "Week 6" / "research_1min" / "results" / "intraday_momentum"
OUT.mkdir(parents=True, exist_ok=True)

ss = pd.read_parquet(SS)
full_spread = dict(zip(ss["ticker"], ss["median_bps"]))

def daily_bars(tkr):
    px = pd.read_parquet(B1 / f"{tkr}.parquet", columns=["close"])["close"]
    df = px.to_frame("close")
    df["date"] = df.index.date
    df["t"] = df.index.time
    return df

def run(tkr):
    df = daily_bars(tkr)
    piv = {}
    for label, tt in [("c0930", "09:30"), ("c1000", "10:00"),
                      ("c1530", "15:30"), ("c1559", "15:59")]:
        t = pd.to_datetime(tt).time()
        s = df[df["t"] == t].set_index("date")["close"]
        piv[label] = s
    d = pd.DataFrame(piv).dropna()
    d["prev_close"] = d["c1559"].shift(1)
    d = d.dropna()

    # tin hieu
    d["sig_gap"] = d["c1000"] / d["prev_close"] - 1          # gom gap qua dem (spec goc)
    d["sig_intra"] = d["c1000"] / d["c0930"] - 1             # chi trong phien
    # return 30 phut cuoi
    d["r_last30"] = d["c1559"] / d["c1530"] - 1

    res = {}
    for sig in ["sig_gap", "sig_intra"]:
        pos = np.sign(d[sig])
        r = (pos * d["r_last30"]).dropna()
        n = len(r)
        gross_bp = r.mean() * 1e4
        t = r.mean() / (r.std() / np.sqrt(n))
        hit = (r > 0).mean() * 100
        sharpe = r.mean() / r.std() * np.sqrt(252)
        yearly = (r.groupby(pd.to_datetime(r.index).year).mean() * 1e4).round(2)
        res[sig] = dict(n=n, gross_bp=gross_bp, t=t, hit=hit, sharpe=sharpe, yearly=yearly)
    return d, res

lines = []
def say(s):
    print(s, flush=True)
    lines.append(s)

say("===== INTRADAY MOMENTUM: 30p dau -> 30p cuoi (1 trade/ngay) =====")
for tkr in ["SPY", "QQQ", "IWM"]:
    d, res = run(tkr)
    cost_w5 = full_spread.get(tkr, np.nan)          # round-trip ~ full spread (2 x half)
    say(f"\n--- {tkr}  ({len(d)} ngay; phi Week5 ~{cost_w5:.1f}bp/vong, phi thuc te ETF ~1bp) ---")
    for sig, tag in [("sig_gap", "gom gap qua dem"), ("sig_intra", "chi trong phien")]:
        r = res[sig]
        say(f"  [{tag}] gross {r['gross_bp']:+.2f} bp/trade | t={r['t']:+.2f} | hit {r['hit']:.1f}% | Sharpe(gross) {r['sharpe']:+.2f}")
        say(f"      net(Week5 {cost_w5:.1f}bp): {r['gross_bp']-cost_w5:+.2f} bp/trade | net(1bp): {r['gross_bp']-1.0:+.2f} bp/trade")
        say(f"      theo nam (bp/trade): " + ", ".join(f"{y}:{v:+.1f}" for y, v in r["yearly"].items()))

say("\nDoi chieu paper goc (Gao et al, du lieu 1993-2013): ~6-7bp/trade gross tren SPY.")
(OUT / "report.txt").write_text("\n".join(lines), encoding="utf-8")
