"""
data.py — nap du lieu 1-min, universe, phi. MOI quy uoc nap du lieu o MOT cho.

Quy uoc ke thua tu script cu (Week 6/research_1min) — KHONG doi khi tai lap:
- universe = top-100 ma median_bps hep nhat trong nhom n_obs >= 0.95*max, sap xep alphabet
- gia = log(close) / log(open) bar 1-phut, index timestamp_et
- ma khong co file hoac rong trong khoang ngay -> loai khoi universe
- half-spread (phi mot chieu) = median_bps / 2 tu spread_summary (median ca ky 2022-2026)
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
B1 = ROOT / "Week 4" / "data" / "validated" / "1min_phase2"
SS = ROOT / "Week 5" / "data" / "microstructure" / "spread_summary.parquet"


def load_universe(n_univ=100, coverage=0.95):
    """Tra ve (danh sach ma sap xep alphabet, dict ma -> half-spread bps)."""
    ss = pd.read_parquet(SS)
    ok = ss[ss["n_obs"] >= coverage * ss["n_obs"].max()].nsmallest(n_univ, "median_bps")
    univ = sorted(ok["ticker"])
    half = dict(zip(ss["ticker"], ss["median_bps"] / 2.0))
    return univ, half


def load_log_prices(univ, start, end, columns=("close",)):
    """Ma tran log-gia 1-phut cho tung cot gia (close/open), index hop nhat.

    Tra ve dict {ten_cot: DataFrame} — cac DataFrame co CUNG danh sach ma
    (ma phai co file va co it nhat 1 bar trong [start, end]).
    """
    series = {c: {} for c in columns}
    for t in univ:
        f = B1 / f"{t}.parquet"
        if not f.exists():
            continue
        df = pd.read_parquet(f, columns=list(columns)).loc[start:end]
        if len(df) == 0:
            continue
        for c in columns:
            series[c][t] = np.log(df[c])
    return {c: pd.DataFrame(series[c]) for c in columns}


def day_index(df):
    """(danh sach ngay giao dich, mang ngay-cua-tung-bar) — dung chia tuan."""
    days = sorted(set(df.index.date))
    d1 = np.array([d for d in df.index.date])
    return days, d1


def pair_cost_bps(half, ta, tb, beta):
    """Phi round-trip bao thu: 2 chieu x (half A + beta*half B)."""
    return 2.0 * (half.get(ta, np.nan) + beta * half.get(tb, np.nan))
