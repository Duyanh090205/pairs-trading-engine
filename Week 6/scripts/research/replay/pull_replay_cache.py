"""
Phase A — pull Alpaca split-adjusted daily bars for the 528 universe into a
REPLAY cache (separate dir; never touches live/state/daily_cache).
Batched 50 symbols/request. Window: 2024-10-01 -> today (covers 12m formation
before fold 2026-04 + ~312 trading days for regime z-window fidelity).
Adapted from Week 6/scripts/build_live_daily_cache.py.
"""
from __future__ import annotations
import os, sys, time, json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv

ROOT = Path(r"d:/Quant Finance/Pairs Trading Strategy")
WEEK6 = ROOT / "Week 6"
sys.path.insert(0, str(WEEK6))
load_dotenv(WEEK6 / ".env")

from live.broker.alpaca_client import AlpacaConfig, build_data_client

POLY = ROOT / "Week 4" / "data" / "validated" / "daily_phase3"
OUT = Path(r"C:/Users/nguye/AppData/Local/Temp/claude/d--Quant-Finance-Pairs-Trading-Strategy/5d0b2e03-5bc5-44d4-8ed9-7c78d24ffe50/scratchpad/replay_cache")

START = datetime(2024, 10, 1, tzinfo=timezone.utc)
END = datetime.now(timezone.utc)
BATCH = 50


def main() -> int:
    tickers = sorted(p.stem for p in POLY.iterdir() if p.suffix == ".parquet")
    print(f"universe: {len(tickers)} tickers | window {START.date()} -> {END.date()}")
    OUT.mkdir(parents=True, exist_ok=True)

    cfg = AlpacaConfig.from_env()
    client = build_data_client(cfg)
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    t0 = time.time()
    ok = empty = 0
    for i in range(0, len(tickers), BATCH):
        chunk = tickers[i:i + BATCH]
        req = StockBarsRequest(
            symbol_or_symbols=chunk, timeframe=TimeFrame.Day,
            start=START, end=END, feed="iex", adjustment="split",
        )
        resp = client.get_stock_bars(req)
        data = resp.data if hasattr(resp, "data") else {}
        for tk in chunk:
            bars = data.get(tk, [])
            rows = [{"date": b.timestamp.astimezone(timezone.utc).date(),
                     "close": float(b.close), "volume": float(b.volume)} for b in bars]
            if not rows:
                empty += 1
                print(f"  {tk}: EMPTY", flush=True)
                continue
            df = pd.DataFrame(rows)
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date").sort_index()
            df = df[~df.index.duplicated(keep="last")]
            df["log_close"] = np.log(df["close"])
            df[["log_close", "volume"]].to_parquet(OUT / f"{tk}.parquet")
            ok += 1
        print(f"  batch {i//BATCH+1}/{(len(tickers)+BATCH-1)//BATCH}: ok={ok} empty={empty} "
              f"({time.time()-t0:.0f}s)", flush=True)

    print(f"\nDone {time.time()-t0:.0f}s | saved={ok} empty={empty}")
    # sanity
    s = pd.read_parquet(OUT / "AAPL.parquet")
    print(f"AAPL: {len(s)} bars, {s.index.min().date()} -> {s.index.max().date()}")
    (OUT / "_DONE").write_text("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
