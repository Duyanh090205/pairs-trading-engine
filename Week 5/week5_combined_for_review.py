"""
Week 5 — Combined source for AI code review.
All modules concatenated in pipeline order: Plan 0 → Plan 1 → Plan 2 → Plan 3 → Pipeline entry.
Not intended to be run directly.
"""

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  PLAN 0 — DATA GATEWAY                                                      ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

# ── src/plan0_gateway/ingest.py ───────────────────────────────────────────────

import pandas as pd

def process_orderbook(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ingests raw orderbook data, localizes timestamps to US/Eastern,
    applies session filtering (09:30-15:59 ET), and flags invalid quotes.
    """
    df = df.copy()

    if df['timestamp'].dt.tz is None:
        df['timestamp_et'] = df['timestamp'].dt.tz_localize('UTC').dt.tz_convert('US/Eastern')
    else:
        df['timestamp_et'] = df['timestamp'].dt.tz_convert('US/Eastern')

    times = df['timestamp_et'].dt.time
    session_mask = (times >= pd.to_datetime('09:30:00').time()) & (times <= pd.to_datetime('15:59:59').time())
    df_filtered = df[session_mask].copy()

    # Flag (but DO NOT DROP) invalid quotes.
    # Reason: Dropping breaks 1-min timeline alignment with Week 4 trades.
    df_filtered['is_valid'] = (df_filtered['l1_ask_px'] > df_filtered['l1_bid_px']) & (df_filtered['l1_bid_px'] > 0)

    return df_filtered


# ── src/plan0_gateway/features.py ────────────────────────────────────────────

def compute_microstructure_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Computes per ticker, per bar microstructure features:
    mid_px, full_spread_l1_bps, half_spread_l1_bps,
    full_spread_l2_bps, full_spread_l3_bps, liquidity_l1.
    """
    df = df.copy()

    df['mid_px'] = (df['l1_bid_px'] + df['l1_ask_px']) / 2

    # Clip at 0: crossed-quote bars would produce negative bps (negative cost = revenue),
    # violating the monotonicity contract. Clamp rather than drop to preserve row count.
    df['full_spread_l1_bps'] = (
        ((df['l1_ask_px'] - df['l1_bid_px']) / df['mid_px']) * 10000
    ).clip(lower=0.0)
    df['half_spread_l1_bps'] = df['full_spread_l1_bps'] / 2

    df['full_spread_l2_bps'] = (
        ((df['l2_ask_px'] - df['l2_bid_px']) / df['mid_px']) * 10000
    ).clip(lower=0.0)

    df['full_spread_l3_bps'] = (
        ((df['l3_ask_px'] - df['l3_bid_px']) / df['mid_px']) * 10000
    ).clip(lower=0.0)

    df['liquidity_l1'] = df['l1_bid_sz'] * df['mid_px']

    return df


# ── src/plan0_gateway/seasonality.py ─────────────────────────────────────────

def compute_intraday_seasonality(df: pd.DataFrame) -> pd.DataFrame:
    """
    Computes per ticker, per 30-min bucket spread aggregates (mean, median, p95).

    No-Lookahead Rule: Seasonality medians must be estimated ONLY on the
    formation window of each fold. This function assumes the input `df`
    is ALREADY filtered to only contain formation window data.
    """
    valid_df = df[df['is_valid']].copy()

    valid_df['time'] = valid_df['timestamp_et'].dt.time

    bins = [pd.to_datetime(f"09:30:00").time()]
    for h in range(10, 16):
        bins.append(pd.to_datetime(f"{h}:00:00").time())
        bins.append(pd.to_datetime(f"{h}:30:00").time())
    bins.append(pd.to_datetime(f"16:00:00").time())

    labels = []
    for i in range(len(bins)-1):
        t1_str = bins[i].strftime("%H:%M")
        t2_str = bins[i+1].strftime("%H:%M")
        if t2_str == "16:00":
            t2_str = "15:59"
        labels.append(f"{t1_str}-{t2_str}")

    common_date = pd.Timestamp('2000-01-01')
    seconds = (
        valid_df['timestamp_et'].dt.hour * 3600
        + valid_df['timestamp_et'].dt.minute * 60
        + valid_df['timestamp_et'].dt.second
    )
    temp_dt = common_date + pd.to_timedelta(seconds, unit='s')
    dt_bins = [
        common_date + pd.Timedelta(hours=t.hour, minutes=t.minute, seconds=t.second)
        for t in bins
    ]

    valid_df['bucket'] = pd.cut(temp_dt, bins=dt_bins, labels=labels, right=False, include_lowest=True)

    def p95(x):
        return x.quantile(0.95)

    seasonality = valid_df.groupby(['ticker', 'bucket'], observed=False)['full_spread_l1_bps'].agg(
        ['mean', 'median', p95]
    ).reset_index()

    return seasonality


# ── src/plan0_gateway/rolling.py ──────────────────────────────────────────────

import numpy as np

def compute_rolling_instability(df: pd.DataFrame, seasonality_df: pd.DataFrame) -> pd.DataFrame:
    """
    Computes rolling spread instability (390-bar rolling standard deviation)
    on the seasonality-adjusted spread.
    """
    df = df.copy()

    bins = [pd.to_datetime(f"09:30:00").time()]
    for h in range(10, 16):
        bins.append(pd.to_datetime(f"{h}:00:00").time())
        bins.append(pd.to_datetime(f"{h}:30:00").time())
    bins.append(pd.to_datetime(f"16:00:00").time())

    labels = []
    for i in range(len(bins)-1):
        t1_str = bins[i].strftime("%H:%M")
        t2_str = bins[i+1].strftime("%H:%M")
        if t2_str == "16:00":
            t2_str = "15:59"
        labels.append(f"{t1_str}-{t2_str}")

    common_date = pd.Timestamp('2000-01-01')
    seconds = (
        df['timestamp_et'].dt.hour * 3600
        + df['timestamp_et'].dt.minute * 60
        + df['timestamp_et'].dt.second
    )
    temp_dt = common_date + pd.to_timedelta(seconds, unit='s')
    dt_bins = [
        common_date + pd.Timedelta(hours=t.hour, minutes=t.minute, seconds=t.second)
        for t in bins
    ]

    df['bucket'] = pd.cut(temp_dt, bins=dt_bins, labels=labels, right=False, include_lowest=True)

    medians = seasonality_df[['ticker', 'bucket', 'median']].copy()
    df = df.merge(medians, on=['ticker', 'bucket'], how='left')

    df['adj_spread_bps'] = np.nan
    mask = df['is_valid'] & df['median'].notna()
    df.loc[mask, 'adj_spread_bps'] = df.loc[mask, 'full_spread_l1_bps'] - df.loc[mask, 'median']

    df = df.sort_values(['ticker', 'timestamp_et'])

    # 390 bars = 1 trading day; min_periods=390 enforces burn-in
    df['spread_std_1d'] = df.groupby('ticker')['adj_spread_bps'].transform(
        lambda x: x.rolling(window=390, min_periods=390).std()
    )

    # Pre-mask invalid bars before computing rolling mean
    df['_spread_valid'] = df['full_spread_l1_bps'].where(df['is_valid'])
    df['raw_spread_mean_1d'] = df.groupby('ticker')['_spread_valid'].transform(
        lambda x: x.rolling(window=390, min_periods=390).mean()
    )

    df = df.drop(columns=['bucket', 'median', 'adj_spread_bps', '_spread_valid'])

    return df


# ── src/plan0_gateway/run_real_data.py ───────────────────────────────────────
"""
Plan 0 real-data runner.

Two-pass strategy (optimised for 16-core / 3.9 GB free RAM):

Pass 1 — sequential single-scan (2-3 min)
  Read each of 204 row groups once.
  Apply session filter + microstructure features.
  Flush per-ticker interim parquets every FLUSH_EVERY row groups.
  Peak RAM: ~1.5 GB (one accumulation batch).

Pass 2 — parallel per-ticker compute (3-5 min)
  ProcessPoolExecutor(MAX_WORKERS).
  Each worker: load ticker's interim files, compute seasonality +
  rolling, write output temp parquet.
  Peak RAM per worker: ~100 MB.

Assembly — concat all output temps into 4 final parquets (~1 min).

Total expected: 7-10 min vs ~44 min for 526 per-ticker full-file scans.
"""

import gc
import os
import shutil
import sys
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pyarrow.parquet as pq

WEEK5_ROOT = Path(__file__).resolve().parent if '__file__' in dir() else Path('.')

ORDERBOOK  = WEEK5_ROOT / "data" / "orderbook.parquet"
MICRO_DIR  = WEEK5_ROOT / "data" / "microstructure"
TMP_TICKER = MICRO_DIR / "_tmp_ticker"
TMP_OUT    = MICRO_DIR / "_tmp_out"

FLUSH_EVERY  = 50
MAX_WORKERS  = 4

FORMATION_END = pd.Timestamp("2022-06-30 23:59:59", tz="UTC")

READ_COLS = [
    "timestamp", "ticker",
    "l1_bid_px", "l1_ask_px",
    "l2_bid_px", "l2_ask_px",
    "l3_bid_px", "l3_ask_px",
    "l1_bid_sz",
]

INTERIM_COLS = [
    "timestamp_et", "ticker", "is_valid",
    "full_spread_l1_bps", "half_spread_l1_bps",
    "full_spread_l2_bps", "full_spread_l3_bps",
    "liquidity_l1",
]

OUT_COLS = [
    "timestamp_et", "ticker", "is_valid",
    "full_spread_l1_bps", "half_spread_l1_bps",
    "full_spread_l2_bps", "full_spread_l3_bps",
    "liquidity_l1", "spread_std_1d", "raw_spread_mean_1d",
]


def _flush_ticker_buffers(buffers: dict, batch_idx: int) -> int:
    total = 0
    for ticker, chunks in buffers.items():
        if not chunks:
            continue
        ticker_dir = TMP_TICKER / ticker
        ticker_dir.mkdir(parents=True, exist_ok=True)
        df = pd.concat(chunks, ignore_index=True)
        df.to_parquet(ticker_dir / f"batch_{batch_idx:03d}.parquet",
                      compression="snappy", index=False)
        total += len(df)
    return total


def run_pass1(pf: pq.ParquetFile) -> list:
    n_groups = pf.metadata.num_row_groups
    TMP_TICKER.mkdir(parents=True, exist_ok=True)

    buffers = defaultdict(list)
    all_tickers = set()
    total_rows_written = 0
    batch_idx = 0
    t_start = time.time()

    for i in range(n_groups):
        rg_df = pf.read_row_group(i, columns=READ_COLS).to_pandas()
        df_clean = process_orderbook(rg_df)
        del rg_df
        df_feat = compute_microstructure_features(df_clean)
        del df_clean
        df_interim = df_feat[INTERIM_COLS].copy()
        del df_feat

        for ticker, grp in df_interim.groupby("ticker", sort=False):
            buffers[ticker].append(grp.reset_index(drop=True))
            all_tickers.add(ticker)
        del df_interim

        if (i + 1) % FLUSH_EVERY == 0:
            rows = _flush_ticker_buffers(buffers, batch_idx)
            total_rows_written += rows
            buffers.clear()
            gc.collect()
            batch_idx += 1
            elapsed = time.time() - t_start
            pct = (i + 1) / n_groups * 100
            eta = elapsed / (i + 1) * (n_groups - i - 1)
            print(f"  Pass 1 | RG {i+1:3d}/{n_groups} ({pct:.0f}%) | "
                  f"batch {batch_idx} flushed | elapsed {elapsed:.0f}s | ETA {eta:.0f}s")

    if any(buffers.values()):
        rows = _flush_ticker_buffers(buffers, batch_idx)
        total_rows_written += rows
        buffers.clear()
        gc.collect()

    elapsed = time.time() - t_start
    print(f"  Pass 1 done: {total_rows_written:,} interim rows, {len(all_tickers)} tickers, {elapsed:.1f}s")
    return sorted(all_tickers)


def _process_ticker_worker(ticker: str) -> dict:
    week5 = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(week5))

    tmp_ticker = week5 / "data" / "microstructure" / "_tmp_ticker"
    tmp_out    = week5 / "data" / "microstructure" / "_tmp_out"
    tmp_out.mkdir(parents=True, exist_ok=True)

    form_end = pd.Timestamp("2022-06-30 23:59:59", tz="UTC")
    out_cols = [
        "timestamp_et", "ticker", "is_valid",
        "full_spread_l1_bps", "half_spread_l1_bps",
        "full_spread_l2_bps", "full_spread_l3_bps",
        "liquidity_l1", "spread_std_1d", "raw_spread_mean_1d",
    ]

    try:
        ticker_dir = tmp_ticker / ticker
        batch_files = sorted(ticker_dir.glob("batch_*.parquet"))
        if not batch_files:
            return {"ticker": ticker, "ok": False, "error": "no interim files"}

        df = pd.concat(
            [pd.read_parquet(f) for f in batch_files],
            ignore_index=True,
        ).sort_values("timestamp_et")

        form_mask = df["timestamp_et"].dt.tz_convert("UTC") <= form_end
        df_seas = compute_intraday_seasonality(df[form_mask])
        df_roll = compute_rolling_instability(df, df_seas)
        del df, df_seas

        df_out = df_roll[out_cols].copy()
        del df_roll

        out_path = tmp_out / f"{ticker}.parquet"
        df_out.to_parquet(out_path, compression="snappy", index=False)

        stats = {
            "ticker": ticker,
            "ok": True,
            "n_rows": int(len(df_out)),
            "median_l1_bps": float(df_out.loc[df_out["is_valid"], "full_spread_l1_bps"].median()),
            "pct_std_valid": float(df_out["spread_std_1d"].notna().mean() * 100),
        }
        del df_out
        gc.collect()
        return stats

    except Exception as exc:
        return {"ticker": ticker, "ok": False, "error": str(exc)}


def run_pass2(tickers: list) -> list:
    TMP_OUT.mkdir(parents=True, exist_ok=True)
    results = []
    done = 0
    t_start = time.time()

    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(_process_ticker_worker, t): t for t in tickers}
        for future in as_completed(futures):
            stats = future.result()
            results.append(stats)
            done += 1
            if not stats["ok"]:
                print(f"  [WARN] {stats['ticker']}: {stats.get('error','unknown error')}")
            if done % 50 == 0 or done == len(tickers):
                elapsed = time.time() - t_start
                eta = elapsed / done * (len(tickers) - done)
                print(f"  Pass 2 | {done}/{len(tickers)} tickers | elapsed {elapsed:.0f}s | ETA {eta:.0f}s")

    return results


def assemble_outputs() -> dict:
    import pyarrow as pa
    import pyarrow.parquet as pq_writer

    MICRO_DIR.mkdir(parents=True, exist_ok=True)
    t_start = time.time()

    out_files = sorted(TMP_OUT.glob("*.parquet"))
    if not out_files:
        raise RuntimeError("No output temp files found — Pass 2 may have failed.")

    print(f"  Assembly: streaming {len(out_files)} ticker files -> 4 parquets ...")

    roll_cols = ["timestamp_et", "ticker", "spread_std_1d", "raw_spread_mean_1d"]

    schema_full  = pq_writer.read_schema(out_files[0])
    schema_roll  = pa.schema([schema_full.field(c) for c in roll_cols])

    p_full = MICRO_DIR / "spreads_1min.parquet"
    p_roll = MICRO_DIR / "spread_rolling.parquet"

    total_rows = 0
    n_tickers  = 0
    seas_chunks = []
    summary_rows = []

    with pq_writer.ParquetWriter(str(p_full), schema_full, compression="snappy") as w_full, \
         pq_writer.ParquetWriter(str(p_roll), schema_roll, compression="snappy") as w_roll:

        for fp in out_files:
            df = pd.read_parquet(fp)
            total_rows += len(df)
            n_tickers  += 1

            tbl = pa.Table.from_pandas(df, schema=schema_full, preserve_index=False)
            w_full.write_table(tbl)
            w_roll.write_table(tbl.select(roll_cols))

            form_valid = df[
                df["is_valid"]
                & (df["timestamp_et"].dt.tz_convert("UTC") <= FORMATION_END)
            ]
            if not form_valid.empty:
                seas_chunks.append(form_valid[["ticker", "timestamp_et",
                                               "full_spread_l1_bps", "is_valid"]].copy())

            valid = df[df["is_valid"]]["full_spread_l1_bps"]
            if not valid.empty:
                summary_rows.append({
                    "ticker":     df["ticker"].iloc[0],
                    "n_obs":      int(len(valid)),
                    "mean_bps":   float(valid.mean()),
                    "median_bps": float(valid.median()),
                    "p95_bps":    float(valid.quantile(0.95)),
                    "p99_bps":    float(valid.quantile(0.99)),
                    "std_bps":    float(valid.std()),
                })

            del df, tbl
            if n_tickers % 100 == 0:
                gc.collect()
                print(f"    {n_tickers}/{len(out_files)} tickers streamed ...")

    gc.collect()
    df_form = pd.concat(seas_chunks, ignore_index=True)
    del seas_chunks
    df_seas = compute_intraday_seasonality(df_form)
    del df_form
    p = MICRO_DIR / "spread_seasonality.parquet"
    df_seas.to_parquet(p, compression="snappy", index=False)

    df_summary = pd.DataFrame(summary_rows)
    p = MICRO_DIR / "spread_summary.parquet"
    df_summary.to_parquet(p, compression="snappy", index=False)

    elapsed = time.time() - t_start
    print(f"  Assembly done in {elapsed:.1f}s")

    return {"total_rows": total_rows, "n_tickers": n_tickers, "summary": df_summary}


def run_plan0_real(cleanup_tmp: bool = True, max_workers: int = MAX_WORKERS) -> dict:
    global MAX_WORKERS
    MAX_WORKERS = max_workers

    t_wall = time.time()

    for d in (TMP_TICKER, TMP_OUT):
        if d.exists():
            shutil.rmtree(d)

    pf = pq.ParquetFile(str(ORDERBOOK))
    tickers = run_pass1(pf)
    del pf

    stats_list = run_pass2(tickers)

    failed  = [s for s in stats_list if not s["ok"]]
    ok_stats = [s for s in stats_list if s["ok"]]

    summary = assemble_outputs()

    if cleanup_tmp:
        shutil.rmtree(TMP_TICKER, ignore_errors=True)
        shutil.rmtree(TMP_OUT,    ignore_errors=True)

    total_elapsed = time.time() - t_wall

    return {
        "tickers": tickers,
        "ok_count": len(ok_stats),
        "failed_count": len(failed),
        "failed_tickers": [s["ticker"] for s in failed],
        "total_rows": summary["total_rows"],
        "elapsed_s": total_elapsed,
        "per_ticker_stats": {s["ticker"]: s for s in ok_stats},
    }


# ── src/plan0_gateway/smoke_test.py ──────────────────────────────────────────

def run_plan0_smoke_test():
    print("--- Running Plan 0 Smoke Test ---")

    tickers = ['SPY', 'AAPL', 'MSFT', 'VTRS', 'XOM']
    dates = pd.date_range('2022-01-03 09:00:00', '2022-01-05 16:30:00', freq='1min', tz='UTC')

    df_list = []
    for ticker in tickers:
        n_rows = len(dates)
        base_px = {'SPY': 450, 'AAPL': 170, 'MSFT': 330, 'VTRS': 15, 'XOM': 65}[ticker]
        px = base_px * np.cumprod(1 + np.random.normal(0, 0.0001, n_rows))
        half_spread_bps = {'SPY': 2, 'AAPL': 3, 'MSFT': 3, 'VTRS': 15, 'XOM': 4}[ticker]
        spread_usd = px * (half_spread_bps / 10000)
        l1_bid = px - spread_usd
        l1_ask = px + spread_usd
        invalid_idx = np.random.choice(n_rows, size=5, replace=False)
        df_ticker = pd.DataFrame({
            'timestamp': dates, 'ticker': ticker,
            'l1_bid_px': l1_bid, 'l1_ask_px': l1_ask,
            'l1_bid_sz': np.random.randint(100, 1000, n_rows),
            'l1_ask_sz': np.random.randint(100, 1000, n_rows),
            'l2_bid_px': l1_bid - spread_usd, 'l2_ask_px': l1_ask + spread_usd,
            'l2_bid_sz': np.random.randint(100, 1000, n_rows),
            'l2_ask_sz': np.random.randint(100, 1000, n_rows),
            'l3_bid_px': l1_bid - 2 * spread_usd, 'l3_ask_px': l1_ask + 2 * spread_usd,
            'l3_bid_sz': np.random.randint(100, 1000, n_rows),
            'l3_ask_sz': np.random.randint(100, 1000, n_rows),
        })
        df_ticker.loc[invalid_idx[0:2], 'l1_bid_px'] = df_ticker.loc[invalid_idx[0:2], 'l1_ask_px'] + 0.10
        df_ticker.loc[invalid_idx[2:5], 'l1_bid_px'] = 0.0
        df_list.append(df_ticker)

    df = pd.concat(df_list, ignore_index=True)
    df_clean = process_orderbook(df)
    df_features = compute_microstructure_features(df_clean)
    df_seasonality = compute_intraday_seasonality(df_features)
    df_final = compute_rolling_instability(df_features, df_seasonality)

    assert str(df_final['timestamp_et'].dt.tz) == 'US/Eastern'
    times_out = df_final['timestamp_et'].dt.time
    assert times_out.min() >= pd.to_datetime('09:30:00').time()
    assert times_out.max() <= pd.to_datetime('15:59:59').time()
    assert np.allclose(df_final['half_spread_l1_bps'], df_final['full_spread_l1_bps'] / 2, equal_nan=True)
    valid_rows = df_final[df_final['is_valid']]
    assert (valid_rows['full_spread_l1_bps'] >= 0).all()
    assert (~df_final['is_valid']).sum() > 0
    buckets = df_seasonality['bucket'].unique()
    assert len(buckets) == 13

    print("Plan 0 Smoke Test Passed.")
    return True


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  PLAN 1 — COST MODEL                                                        ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

# ── src/plan1_cost_model/spread_cost.py ──────────────────────────────────────

def calculate_spread_cost(half_spread_l1_bps: float, notional_dollars: float) -> float:
    """C_spread(t) = half_spread_l1_bps(t) * notional_dollars."""
    effective_bps = max(half_spread_l1_bps, 0.0)
    return notional_dollars * (effective_bps / 10000.0)


# ── src/plan1_cost_model/impact_cost.py ──────────────────────────────────────

def assign_kappa_tier(median_full_spread_bps: float) -> float:
    """
    Assigns impact coefficient (κ) based on formation-window median spread.
    Tier 1 (<8 bps): κ=0.3 | Tier 2 (8-20 bps): κ=0.5 | Tier 3 (>20 bps): κ=0.8
    """
    if median_full_spread_bps < 8.0:
        return 0.3
    elif median_full_spread_bps <= 20.0:
        return 0.5
    else:
        return 0.8


def calculate_impact_cost(kappa: float, spread_std_1d: float, notional_dollars: float, multiplier: float = 1.0) -> float:
    """C_impact(t) = κ * spread_std_1d(t) * notional_dollars."""
    if pd.isna(spread_std_1d):
        # Conservative 15 bps fallback during 390-bar burn-in
        impact_bps = 15.0 * multiplier
    else:
        impact_bps = kappa * spread_std_1d * multiplier
    return notional_dollars * (impact_bps / 10000.0)


# ── src/plan1_cost_model/borrow_cost.py ──────────────────────────────────────

def calculate_borrow_cost(short_notional: float, entry_ts: pd.Timestamp, exit_ts: pd.Timestamp, borrow_rate_bps_annual: float = 50.0) -> float:
    """
    Total borrow cost for a short position.
    Day-count convention: Actual/365. Borrow accrues on every calendar day
    (including weekends — short cannot be returned Saturday/Sunday), so annual
    rate is divided by 365, not 252. Intraday shorts have zero borrow cost.
    """
    if entry_ts.date() == exit_ts.date():
        return 0.0
    holding_days = (exit_ts.date() - entry_ts.date()).days
    borrow_cost_daily = (borrow_rate_bps_annual / 10000.0) / 365.0 * short_notional
    return borrow_cost_daily * holding_days


# ── src/plan1_cost_model/round_trip.py ───────────────────────────────────────

def calculate_round_trip_cost(
    entry_cost_A: float,
    entry_cost_B: float,
    exit_cost_A: float,
    exit_cost_B: float,
    borrow_cost: float,
) -> float:
    """Total round-trip execution cost for a pair trade in dollars."""
    return entry_cost_A + entry_cost_B + exit_cost_A + exit_cost_B + borrow_cost


def calculate_static_round_trip_cost(
    notional_A_entry: float,
    notional_B_entry: float,
    notional_A_exit: float,
    notional_B_exit: float,
    tc_bps_per_leg: float = 30.0,
) -> float:
    """
    Week 4 static cost baseline: fixed bps per leg regardless of market conditions.
    Default 30 bps/leg = 60 bps per side = 120 bps total round-trip notional-weighted.
    Matches Week 4 pnl.py: tc_rate * (notional_A + notional_B) applied at entry and exit.
    """
    entry_cost = (notional_A_entry + notional_B_entry) * (tc_bps_per_leg / 10000.0)
    exit_cost  = (notional_A_exit  + notional_B_exit)  * (tc_bps_per_leg / 10000.0)
    return entry_cost + exit_cost


# ── src/plan1_cost_model/interface_contract.py ───────────────────────────────

TRADE_LOG_SCHEMA = {
    'trade_id': 'string', 'fold_id': 'int', 'pair_id': 'string',
    'ticker_A': 'string', 'ticker_B': 'string',
    'side_A': 'int', 'side_B': 'int',
    'entry_ts': 'datetime64[ns, US/Eastern]',
    'exit_ts': 'datetime64[ns, US/Eastern]',
    'notional_A_entry': 'float', 'notional_B_entry': 'float',
    'notional_A_exit': 'float', 'notional_B_exit': 'float',
    'gross_pnl_dollars': 'float', 'allocated_capital': 'float',
}

REBALANCE_LOG_SCHEMA = {
    'trade_id': 'string', 'fold_id': 'int', 'pair_id': 'string',
    'ticker': 'string', 'rebalance_ts': 'datetime64[ns, US/Eastern]',
    'delta_shares': 'float', 'price_at_rebalance': 'float',
    'notional_rebalanced': 'float',
}

COST_LOG_SCHEMA = {
    'trade_id': 'string', 'spread_cost_dollars': 'float',
    'impact_cost_dollars': 'float', 'borrow_cost_dollars': 'float',
    'rebalance_cost_dollars': 'float', 'total_cost_dollars': 'float',
    'net_pnl_dollars': 'float', 'net_return': 'float',
}


def _validate_schema(df: pd.DataFrame, schema: dict, schema_name: str) -> bool:
    if not isinstance(df, pd.DataFrame):
        raise TypeError(f"{schema_name} must be a pandas DataFrame.")
    missing_cols = set(schema.keys()) - set(df.columns)
    if missing_cols:
        raise ValueError(f"{schema_name} is missing required columns: {missing_cols}")
    return True


def validate_trade_log(df: pd.DataFrame) -> bool:
    return _validate_schema(df, TRADE_LOG_SCHEMA, "Trade Log")


def validate_rebalance_log(df: pd.DataFrame) -> bool:
    return _validate_schema(df, REBALANCE_LOG_SCHEMA, "Rebalance Log")


def validate_cost_log(df: pd.DataFrame) -> bool:
    return _validate_schema(df, COST_LOG_SCHEMA, "Cost Log")


# ── src/plan1_cost_model/smoke_test.py ───────────────────────────────────────

def run_plan1_smoke_test():
    print("--- Running Plan 1 Smoke Test ---")

    assert assign_kappa_tier(4.7)  == 0.3
    assert assign_kappa_tier(7.99) == 0.3
    assert assign_kappa_tier(8.0)  == 0.5
    assert assign_kappa_tier(10.0) == 0.5
    assert assign_kappa_tier(20.0) == 0.5
    assert assign_kappa_tier(32.0) == 0.8
    print("[PASS] assign_kappa_tier boundaries correct.")

    test_notional = 100_000.0
    kappa = assign_kappa_tier(10.0)
    cost_0_5x = calculate_impact_cost(kappa, 5.0, test_notional, multiplier=0.5)
    cost_1_0x = calculate_impact_cost(kappa, 5.0, test_notional, multiplier=1.0)
    cost_1_5x = calculate_impact_cost(kappa, 5.0, test_notional, multiplier=1.5)
    assert cost_0_5x < cost_1_0x < cost_1_5x
    print("[PASS] Sensitivity grid monotonic.")

    static_cost = calculate_static_round_trip_cost(100_000, 100_000, 100_000, 100_000, tc_bps_per_leg=30.0)
    expected_static = 4 * 100_000.0 * (30.0 / 10000.0)
    assert abs(static_cost - expected_static) < 1e-8
    print(f"[PASS] Static 60bps formula: 4 legs × 30bps × $100k = ${expected_static:.2f}")

    print("Plan 1 Smoke Test Passed.")
    return True


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  PLAN 2 — COST APPLICATION                                                  ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

# ── src/plan2_backtester/walk_forward.py ─────────────────────────────────────

from typing import NamedTuple


class FoldSpec(NamedTuple):
    fold_id: int
    formation_start: pd.Timestamp
    formation_end: pd.Timestamp
    trading_start: pd.Timestamp
    trading_label: str


def _build_fold_schedule() -> list:
    """Reproduces Week 4's 45-fold schedule."""
    folds = []
    base = pd.Timestamp("2022-01-01")
    for i in range(45):
        fold_n = i + 1
        form_start = base + pd.DateOffset(months=i)
        if fold_n == 1:
            form_start = pd.Timestamp("2022-01-03")
        anchor = pd.Timestamp(form_start.year, form_start.month, 1)
        form_end = anchor + pd.DateOffset(months=6) - pd.DateOffset(days=1)
        trade_start = pd.Timestamp(form_end.year, form_end.month, 1) + pd.DateOffset(months=1)
        folds.append(FoldSpec(
            fold_id=fold_n,
            formation_start=form_start.tz_localize("US/Eastern"),
            formation_end=(form_end + pd.Timedelta(hours=23, minutes=59, seconds=59)).tz_localize("US/Eastern"),
            trading_start=trade_start.tz_localize("US/Eastern"),
            trading_label=trade_start.strftime("%Y-%m"),
        ))
    return folds


FOLD_SCHEDULE = _build_fold_schedule()
FOLD_BY_ID    = {f.fold_id: f for f in FOLD_SCHEDULE}


def calibrate_fold(
    fold_id: int,
    formation_start: pd.Timestamp,
    formation_end: pd.Timestamp,
    trading_start: pd.Timestamp,
    tickers: list,
    spreads_df: pd.DataFrame,
) -> dict:
    """
    Returns {ticker: kappa}. Uses ONLY [formation_start, formation_end] data.
    Raises ValueError if formation_end >= trading_start (lookahead guard).
    """
    if formation_end >= trading_start:
        raise ValueError(
            f"Lookahead violation in fold {fold_id}: "
            f"formation_end {formation_end} >= trading_start {trading_start}"
        )

    formation_slice = spreads_df[
        (spreads_df["timestamp_et"] >= formation_start)
        & (spreads_df["timestamp_et"] <= formation_end)
        & (spreads_df["is_valid"])
        & (spreads_df["ticker"].isin(tickers))
    ]

    medians = formation_slice.groupby("ticker")["full_spread_l1_bps"].median()

    # Tickers without formation data: assign Tier 2 (κ=0.5) as neutral default
    kappa_map = {}
    for t in tickers:
        med = medians.get(t)
        if pd.isna(med) or med is None:
            kappa_map[t] = 0.5
        else:
            kappa_map[t] = assign_kappa_tier(float(med))
    return kappa_map


# ── src/plan2_backtester/hooks.py ────────────────────────────────────────────

_FALLBACK_HALF_SPREAD_BPS = 30.0
_FALLBACK_SIGMA_BPS = float("nan")  # triggers Plan 1's 15-bps impact fallback


def _lookup_at(spreads_idx: pd.DataFrame, ticker: str, ts: pd.Timestamp) -> tuple:
    """
    Returns (half_spread_l1_bps, spread_std_1d) for the bar at-or-before ts.
    spreads_idx: MultiIndex [ticker, timestamp_et], sorted.
    Returns conservative fallback if no bar exists at-or-before ts for that ticker.
    """
    try:
        ticker_slice = spreads_idx.loc[ticker]
    except KeyError:
        return _FALLBACK_HALF_SPREAD_BPS, _FALLBACK_SIGMA_BPS

    sub = ticker_slice.loc[:ts]
    if sub.empty:
        return _FALLBACK_HALF_SPREAD_BPS, _FALLBACK_SIGMA_BPS

    row = sub.iloc[-1]
    hs    = float(row["half_spread_l1_bps"]) if not pd.isna(row["half_spread_l1_bps"]) else _FALLBACK_HALF_SPREAD_BPS
    sigma = float(row["spread_std_1d"])      if not pd.isna(row["spread_std_1d"])      else _FALLBACK_SIGMA_BPS
    return hs, sigma


def trade_dynamic_cost(trade_row, spreads_idx: pd.DataFrame, kappa_map: dict, borrow_rate_bps_annual: float = 50.0) -> dict:
    """Dynamic-cost dollars for one round-trip pair trade. Returns {spread_$, impact_$, borrow_$, total_$}."""
    hsa_in,  sa_in  = _lookup_at(spreads_idx, trade_row.ticker_A, trade_row.entry_ts)
    hsb_in,  sb_in  = _lookup_at(spreads_idx, trade_row.ticker_B, trade_row.entry_ts)
    hsa_out, sa_out = _lookup_at(spreads_idx, trade_row.ticker_A, trade_row.exit_ts)
    hsb_out, sb_out = _lookup_at(spreads_idx, trade_row.ticker_B, trade_row.exit_ts)

    kA = kappa_map.get(trade_row.ticker_A, 0.5)
    kB = kappa_map.get(trade_row.ticker_B, 0.5)

    e_sp_A = calculate_spread_cost(hsa_in,  trade_row.notional_A_entry)
    e_sp_B = calculate_spread_cost(hsb_in,  trade_row.notional_B_entry)
    e_im_A = calculate_impact_cost(kA, sa_in,  trade_row.notional_A_entry)
    e_im_B = calculate_impact_cost(kB, sb_in,  trade_row.notional_B_entry)
    x_sp_A = calculate_spread_cost(hsa_out, trade_row.notional_A_exit)
    x_sp_B = calculate_spread_cost(hsb_out, trade_row.notional_B_exit)
    x_im_A = calculate_impact_cost(kA, sa_out, trade_row.notional_A_exit)
    x_im_B = calculate_impact_cost(kB, sb_out, trade_row.notional_B_exit)

    spread_total = e_sp_A + e_sp_B + x_sp_A + x_sp_B
    impact_total = e_im_A + e_im_B + x_im_A + x_im_B

    if trade_row.side_A == -1 and trade_row.side_B == 1:
        short_notional = trade_row.notional_A_entry
    elif trade_row.side_B == -1 and trade_row.side_A == 1:
        short_notional = trade_row.notional_B_entry
    else:
        short_notional = 0.0  # degenerate: both legs same side

    borrow = calculate_borrow_cost(short_notional, trade_row.entry_ts, trade_row.exit_ts, borrow_rate_bps_annual)
    total  = spread_total + impact_total + borrow
    return {"spread_$": spread_total, "impact_$": impact_total, "borrow_$": borrow, "total_$": total}


def trade_static_cost(trade_row, tc_bps_per_leg: float = 30.0) -> float:
    return calculate_static_round_trip_cost(
        trade_row.notional_A_entry, trade_row.notional_B_entry,
        trade_row.notional_A_exit,  trade_row.notional_B_exit,
        tc_bps_per_leg=tc_bps_per_leg,
    )


def rebalance_dynamic_cost(reb_row, spreads_idx: pd.DataFrame, kappa_map: dict) -> float:
    """One-sided spread+impact at rebalance_ts on notional_rebalanced."""
    hs, sigma = _lookup_at(spreads_idx, reb_row.ticker, reb_row.rebalance_ts)
    k  = kappa_map.get(reb_row.ticker, 0.5)
    sp = calculate_spread_cost(hs, abs(reb_row.notional_rebalanced))
    im = calculate_impact_cost(k, sigma, abs(reb_row.notional_rebalanced))
    return sp + im


# ── src/plan2_backtester/orchestrator.py ─────────────────────────────────────

WEEK4_INPUTS = Path('.') / "data" / "week4_inputs"
MICRO_DIR_P2 = Path('.') / "data" / "microstructure"


def _parse_ts_column(series: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(series, utc=True)
    return parsed.dt.tz_convert("US/Eastern")


def load_trade_log(path=None) -> pd.DataFrame:
    path = Path(path) if path else WEEK4_INPUTS / "trade_log.csv"
    df = pd.read_csv(path)
    df["entry_ts"] = _parse_ts_column(df["entry_ts"])
    df["exit_ts"]  = _parse_ts_column(df["exit_ts"])
    validate_trade_log(df)
    return df


def load_rebalance_log(path=None) -> pd.DataFrame:
    path = Path(path) if path else WEEK4_INPUTS / "rebalance_log.csv"
    df = pd.read_csv(path)
    df["rebalance_ts"] = _parse_ts_column(df["rebalance_ts"])
    validate_rebalance_log(df)
    return df


def load_spread_lookup(micro_dir=None, tickers=None) -> tuple:
    """
    Loads spreads_1min.parquet filtered to traded tickers only.
    Returns (spreads_indexed, spreads_flat).
    spreads_indexed: MultiIndex [ticker, timestamp_et] for hooks._lookup_at.
    spreads_flat:    flat DataFrame for calibrate_fold.
    """
    micro_dir = Path(micro_dir) if micro_dir else MICRO_DIR_P2
    parquet_path = micro_dir / "spreads_1min.parquet"

    filters = [("ticker", "in", tickers)] if tickers else None
    spreads = pd.read_parquet(parquet_path, filters=filters)

    if "spread_std_1d" not in spreads.columns:
        rolling_path = micro_dir / "spread_rolling.parquet"
        if rolling_path.exists():
            rolling = pd.read_parquet(rolling_path, filters=filters)
            spreads = spreads.merge(rolling, on=["timestamp_et", "ticker"], how="left")
        else:
            spreads["spread_std_1d"] = float("nan")

    indexed = spreads.set_index(["ticker", "timestamp_et"]).sort_index()
    return indexed, spreads


def run_plan2(trade_log_path=None, rebalance_log_path=None, micro_dir=None, out_dir=None, borrow_rate_bps_annual: float = 50.0) -> tuple:
    """Main entry point. Returns (cost_log, kappa_audit) and writes both as parquet."""
    out_dir = Path(out_dir) if out_dir else Path('.') / "data"
    out_dir.mkdir(parents=True, exist_ok=True)

    trade_log     = load_trade_log(trade_log_path)
    rebalance_log = load_rebalance_log(rebalance_log_path)

    traded_tickers = sorted(set(trade_log["ticker_A"].tolist() + trade_log["ticker_B"].tolist()))
    spreads_idx, spreads_flat = load_spread_lookup(micro_dir, tickers=traded_tickers)

    cost_rows  = []
    kappa_rows = []

    for fold in FOLD_SCHEDULE:
        fold_trades = trade_log[trade_log["fold_id"] == fold.fold_id]
        if fold_trades.empty:
            continue

        tickers = pd.concat([fold_trades["ticker_A"], fold_trades["ticker_B"]]).unique().tolist()
        kappa_map = calibrate_fold(
            fold.fold_id, fold.formation_start, fold.formation_end, fold.trading_start,
            tickers, spreads_flat,
        )
        for t, k in kappa_map.items():
            kappa_rows.append({"fold_id": fold.fold_id, "ticker": t, "kappa": k})

        fold_rebals = rebalance_log[rebalance_log["fold_id"] == fold.fold_id]

        for trade in fold_trades.itertuples():
            d   = trade_dynamic_cost(trade, spreads_idx, kappa_map, borrow_rate_bps_annual)
            stc = trade_static_cost(trade)

            trade_rebals = fold_rebals[fold_rebals["trade_id"] == trade.trade_id]
            reb_dollars  = sum(rebalance_dynamic_cost(r, spreads_idx, kappa_map) for r in trade_rebals.itertuples())

            total_dyn = d["total_$"] + reb_dollars
            net_pnl   = trade.gross_pnl_dollars - total_dyn

            cost_rows.append({
                "trade_id":              trade.trade_id,
                "spread_cost_dollars":   d["spread_$"],
                "impact_cost_dollars":   d["impact_$"],
                "borrow_cost_dollars":   d["borrow_$"],
                "rebalance_cost_dollars": reb_dollars,
                "total_cost_dollars":    total_dyn,
                "net_pnl_dollars":       net_pnl,
                "net_return":            net_pnl / trade.allocated_capital if trade.allocated_capital else 0.0,
                "total_cost_static":     stc,
                "total_cost_gross":      0.0,
                "net_pnl_static":        trade.gross_pnl_dollars - stc,
                "gross_pnl_dollars":     trade.gross_pnl_dollars,
            })

    cost_log    = pd.DataFrame(cost_rows)
    kappa_audit = pd.DataFrame(kappa_rows)

    validate_cost_log(cost_log)

    cost_log.to_parquet(out_dir / "cost_log.parquet")
    kappa_audit.to_parquet(out_dir / "kappa_per_fold.parquet")

    return cost_log, kappa_audit


# ── src/plan2_backtester/_analyze.py  (one-shot debug script) ────────────────
# (Not part of pipeline; kept for reference)
#
# tl = pd.read_csv("data/week4_inputs/trade_log.csv")
# cl = pd.read_parquet("data/cost_log.parquet")
# Prints 11 sections of cost analysis to stdout.
# Full source omitted here — see _analyze.py.


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  PLAN 3 — VALIDATION & REPORT                                               ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

# ── src/plan3_validation/red_flags.py ────────────────────────────────────────

def check_dynamic_cost_blowup(mean_rt_cost_bps: float) -> bool:
    """Trigger: Mean RT cost > 150 bps any fold."""
    return mean_rt_cost_bps > 150.0


def check_cost_exceeds_alpha(net_sharpe: float, gross_sharpe: float) -> bool:
    """Trigger: Net Sharpe < 0 AND Gross Sharpe > 1.0."""
    return net_sharpe < 0.0 and gross_sharpe > 1.0


def check_spread_data_gap(missing_pct: float) -> bool:
    """Trigger: > 5% missing spread observations in trading window."""
    return missing_pct > 0.05


def check_kappa_instability(tier_changes_count: int) -> bool:
    """Trigger: κ tier changes > 2× across consecutive folds for same ticker."""
    return tier_changes_count > 2


def check_nc_leak(nc_dynamic_sharpe: float) -> bool:
    """Trigger: NC Sharpe under dynamic model > 0.5."""
    return nc_dynamic_sharpe > 0.5


def check_dsr_degradation(failure_prob_net: float, failure_prob_gross: float) -> bool:
    """
    Trigger: net DSR < 0.90 (failure_prob > 0.10) while gross DSR > 0.95 (failure_prob < 0.05).
    Inputs are 1 - DSR, not DSR itself.
    """
    return failure_prob_net > 0.10 and failure_prob_gross < 0.05


def check_math_violation(total_cost_dollars: float, net_pnl_dollars: float, gross_pnl_dollars: float) -> bool:
    """Trigger: total_cost_dollars < 0 OR net_pnl_dollars > gross_pnl_dollars."""
    return total_cost_dollars < 0.0 or net_pnl_dollars > gross_pnl_dollars


def check_outlier_pnl(gross_pnl_bps: float, threshold_bps: float = 1000.0) -> bool:
    """
    D1 guard: flag any trade whose gross PnL exceeds threshold_bps of allocated capital.
    A single-trade gross PnL > 1000 bps is physically unusual for mean-reversion on S&P 500 pairs.
    Common causes: corporate-action price gap, stale mid-price, notional mis-denomination.
    """
    return gross_pnl_bps > threshold_bps


# ── src/plan3_validation/sharpe_net.py ───────────────────────────────────────

DEFAULT_COST_LOG_P3   = Path('.') / "data" / "cost_log.parquet"
DEFAULT_TRADE_LOG_P3  = Path('.') / "data" / "week4_inputs" / "trade_log.csv"
DEFAULT_EQUITY_DIR    = Path('.') / "data" / "week4_inputs" / "equities"
DEFAULT_FOLD_METRICS  = Path('.') / "data" / "week4_inputs" / "fold_metrics.csv"


def _annualised_sharpe(daily_returns: np.ndarray) -> float:
    arr = daily_returns[~np.isnan(daily_returns)]
    if len(arr) < 2:
        return float("nan")
    sd = arr.std(ddof=1)
    if sd < 1e-12:
        return float("nan")
    return float(arr.mean() / sd * np.sqrt(252))


def _max_dd(equity: np.ndarray) -> float:
    eq = equity[~np.isnan(equity)]
    if len(eq) == 0:
        return float("nan")
    running = np.maximum.accumulate(eq)
    return float((eq / running - 1.0).min())


def _cagr(equity: np.ndarray, n_calendar_days: int) -> float:
    """
    CAGR annualised over the full calendar span (365-day year).
    n_calendar_days should be (last_date - first_date).days across the whole
    backtest window, NOT the count of active trading days. Using active days
    only would overstate CAGR by the ratio of full_span / active_days
    (≈ 950 / 432 ≈ 2.2× for this dataset).
    """
    eq = equity[~np.isnan(equity)]
    if len(eq) == 0 or n_calendar_days <= 0 or eq[-1] <= 0:
        return float("nan")
    return float(eq[-1] ** (365.0 / n_calendar_days) - 1.0)


def _load_gross_daily_returns(equity_dir: Path) -> pd.Series:
    """
    Combine all fold equity parquets into a single daily gross-return series.
    Week 4 equity curves are 1-minute bar-level. Resampling to end-of-business-day
    gives the true daily return including intra-day position moves.
    """
    pieces = []
    for f in sorted(equity_dir.glob("*.parquet")):
        eq = pd.read_parquet(f)
        eq.index = pd.to_datetime(eq.index, utc=True).tz_convert("US/Eastern")
        daily_eq  = eq["equity"].resample("B").last().dropna()
        daily_ret = daily_eq.pct_change().dropna()
        pieces.append(daily_ret)
    if not pieces:
        return pd.Series(dtype=float)
    combined = pd.concat(pieces).sort_index()
    return combined[~combined.index.duplicated(keep="first")]


def reconstruct_daily_returns(cost_log: pd.DataFrame, trade_log: pd.DataFrame, cost_col: str, equity_dir: Path = DEFAULT_EQUITY_DIR) -> pd.Series:
    """
    Build a daily-return series for one cost regime.
    Gross returns come from Week 4's bar-level fold equity curves (mark-to-market
    on every 1-minute bar). Cost is applied as an exit-day debit.
    """
    gross_daily = _load_gross_daily_returns(equity_dir)
    if gross_daily.empty:
        return _reconstruct_from_exits(cost_log, trade_log, cost_col)

    aum = trade_log["allocated_capital"].sum()
    if aum <= 0:
        return pd.Series(dtype=float)

    if cost_col == "total_cost_gross":
        return gross_daily

    merged = cost_log.merge(trade_log[["trade_id", "exit_ts"]], on="trade_id")
    merged["exit_dt"] = (
        pd.to_datetime(merged["exit_ts"], utc=True)
        .dt.tz_convert("US/Eastern")
        .dt.normalize()
    )
    cost_series = (
        merged["total_cost_static"] if cost_col == "total_cost_static"
        else merged["total_cost_dollars"]
    )
    cost_by_day = merged.assign(cost=cost_series).groupby("exit_dt")["cost"].sum() / aum
    cost_adj    = cost_by_day.reindex(gross_daily.index, fill_value=0.0)

    return gross_daily - cost_adj


def _reconstruct_from_exits(cost_log: pd.DataFrame, trade_log: pd.DataFrame, cost_col: str) -> pd.Series:
    """Fallback: exit-date-only reconstruction with zero-fill (used when equity parquets absent)."""
    merged = cost_log.merge(
        trade_log[["trade_id", "exit_ts", "gross_pnl_dollars", "allocated_capital"]],
        on="trade_id", suffixes=("", "_tl"),
    )
    merged["exit_date"] = pd.to_datetime(merged["exit_ts"], utc=True).dt.tz_convert("US/Eastern").dt.date
    if cost_col == "total_cost_gross":
        merged["net_pnl"] = merged["gross_pnl_dollars"]
    elif cost_col == "total_cost_static":
        merged["net_pnl"] = merged["gross_pnl_dollars"] - merged["total_cost_static"]
    else:
        merged["net_pnl"] = merged["gross_pnl_dollars"] - merged["total_cost_dollars"]
    aum = trade_log["allocated_capital"].sum()
    if aum <= 0:
        return pd.Series(dtype=float)
    daily = merged.groupby("exit_date")["net_pnl"].sum().sort_index() / aum
    if len(daily) >= 2:
        full_idx = pd.bdate_range(
            start=pd.Timestamp(daily.index.min()),
            end=pd.Timestamp(daily.index.max()),
        )
        daily = daily.reindex(full_idx, fill_value=0.0)
    return daily


def generate_before_after_table(cost_log_path=DEFAULT_COST_LOG_P3, trade_log_path=DEFAULT_TRADE_LOG_P3) -> pd.DataFrame:
    """
    Produces the 8-row × 3-column Before vs After table.
    Rows: Sharpe, CAGR, MaxDD, Calmar, Win Rate, Avg Trades/Fold, Avg RT Cost (bps), % Folds Profitable.
    Cols: Gross, Static60bps, Dynamic.
    """
    cost_log  = pd.read_parquet(cost_log_path)
    trade_log = pd.read_csv(trade_log_path)

    regimes = {"Gross": "total_cost_gross", "Static60bps": "total_cost_static", "Dynamic": "total_cost_dollars"}
    rows = {}

    for label, cost_col in regimes.items():
        daily  = reconstruct_daily_returns(cost_log, trade_log, cost_col)
        sharpe = _annualised_sharpe(daily.to_numpy())

        eq_curve   = (1.0 + daily).cumprod().to_numpy() if len(daily) else np.array([1.0])
        max_dd     = _max_dd(eq_curve)
        n_calendar = int((daily.index[-1] - daily.index[0]).days) if len(daily) >= 2 else 0
        cagr       = _cagr(eq_curve, n_calendar) if n_calendar > 0 else float("nan")
        calmar     = cagr / abs(max_dd) if not np.isnan(max_dd) and max_dd < 0 else float("nan")

        if cost_col == "total_cost_gross":
            wins = (cost_log["gross_pnl_dollars"] > 0).sum()
        elif cost_col == "total_cost_static":
            wins = ((cost_log["gross_pnl_dollars"] - cost_log["total_cost_static"]) > 0).sum()
        else:
            wins = ((cost_log["gross_pnl_dollars"] - cost_log["total_cost_dollars"]) > 0).sum()
        win_rate = wins / len(cost_log) if len(cost_log) else float("nan")

        n_folds = trade_log["fold_id"].nunique()
        avg_trades_per_fold = len(trade_log) / n_folds if n_folds else float("nan")

        merged_cap = cost_log.merge(trade_log[["trade_id", "allocated_capital"]], on="trade_id")
        if cost_col == "total_cost_gross":
            cost_per_trade = pd.Series(0.0, index=merged_cap.index)
        else:
            cost_per_trade = merged_cap[cost_col]
        avg_rt_cost_bps = (cost_per_trade / merged_cap["allocated_capital"]).mean() * 10000

        fold_net = merged_cap.copy()
        fold_net["net_pnl"] = fold_net["gross_pnl_dollars"] - cost_per_trade
        fold_pnls = fold_net.merge(trade_log[["trade_id", "fold_id"]], on="trade_id").groupby("fold_id")["net_pnl"].sum()
        pct_folds_profitable = (fold_pnls > 0).mean()

        rows[label] = {
            "Sharpe (annual)":     sharpe,
            "CAGR":                cagr,
            "MaxDD (bar)":         max_dd,
            "Calmar":              calmar,
            "Win Rate":            win_rate,
            "Avg Trades / Fold":   avg_trades_per_fold,
            "Avg RT Cost (bps)":   avg_rt_cost_bps,
            "% Folds Profitable":  pct_folds_profitable,
        }

    return pd.DataFrame(rows).round(4)


# ── src/plan3_validation/cost_waterfall.py ───────────────────────────────────

def _bps(dollars: pd.Series, capital: pd.Series) -> pd.Series:
    return (dollars / capital) * 10_000.0


def generate_cost_waterfall(cost_log_path=DEFAULT_COST_LOG_P3, trade_log_path=DEFAULT_TRADE_LOG_P3) -> pd.DataFrame:
    """
    Returns DataFrame indexed by ['Overall', 'Bear 2022', 'Bull 2023+'].
    Cost columns are reported as negative (consumed alpha).
    """
    cost_log  = pd.read_parquet(cost_log_path)
    trade_log = pd.read_csv(trade_log_path)
    df = cost_log.merge(trade_log[["trade_id", "fold_id", "allocated_capital"]], on="trade_id")
    df["regime"] = df["fold_id"].apply(lambda f: "Bear 2022" if f <= 6 else "Bull 2023+")

    rows = []
    for label, sub in [("Overall", df), ("Bear 2022", df[df["regime"] == "Bear 2022"]), ("Bull 2023+", df[df["regime"] == "Bull 2023+"])]:
        if sub.empty:
            rows.append({"regime": label, "n_trades": 0, "gross_bps": 0.0, "spread_bps": 0.0,
                         "impact_bps": 0.0, "borrow_bps": 0.0, "rebalance_bps": 0.0, "net_bps": 0.0})
            continue
        cap    = sub["allocated_capital"]
        gross  = _bps(sub["gross_pnl_dollars"],      cap).mean()
        spread = _bps(sub["spread_cost_dollars"],    cap).mean()
        impact = _bps(sub["impact_cost_dollars"],    cap).mean()
        borrow = _bps(sub["borrow_cost_dollars"],    cap).mean()
        rebal  = _bps(sub["rebalance_cost_dollars"], cap).mean()
        net    = gross - spread - impact - borrow - rebal
        rows.append({
            "regime": label, "n_trades": len(sub),
            "gross_bps":     round(gross, 2),
            "spread_bps":    round(-spread, 2),
            "impact_bps":    round(-impact, 2),
            "borrow_bps":    round(-borrow, 2),
            "rebalance_bps": round(-rebal,  2),
            "net_bps":       round(net,    2),
        })
    return pd.DataFrame(rows).set_index("regime")


# ── src/plan3_validation/regime_costs.py ─────────────────────────────────────

DEFAULT_SPREADS_P3 = Path('.') / "data" / "microstructure" / "spreads_1min.parquet"

REGIME_MAP = {
    "Late Bear 2022":         range(1, 7),
    "Early Bull 2023":        range(7, 19),
    "Mid Bull 2024":          range(19, 31),
    "Late Bull 2025-Q12026":  range(31, 46),
}


def _fold_to_regime(fold_id: int) -> str:
    for name, rng in REGIME_MAP.items():
        if fold_id in rng:
            return name
    return "Unknown"


def analyze_regime_costs(cost_log_path=DEFAULT_COST_LOG_P3, trade_log_path=DEFAULT_TRADE_LOG_P3, spreads_path=DEFAULT_SPREADS_P3) -> pd.DataFrame:
    """Returns DataFrame indexed by regime name with n_trades, avg_l1_spread_bps, avg_dyn_rt_cost_bps, sharpe_gross, sharpe_dynamic, delta_sharpe."""
    cost_log  = pd.read_parquet(cost_log_path)
    trade_log = pd.read_csv(trade_log_path)
    df = cost_log.merge(trade_log[["trade_id", "fold_id", "allocated_capital", "exit_ts"]], on="trade_id")
    df["regime"]    = df["fold_id"].apply(_fold_to_regime)
    df["exit_date"] = pd.to_datetime(df["exit_ts"], utc=True).dt.tz_convert("US/Eastern").dt.date

    all_traded = pd.concat([trade_log["ticker_A"], trade_log["ticker_B"]]).unique().tolist()
    spreads = pd.read_parquet(spreads_path, columns=["ticker", "full_spread_l1_bps"],
                              filters=[("ticker", "in", all_traded)])

    aum  = trade_log["allocated_capital"].sum()
    rows = []

    for regime in REGIME_MAP:
        sub = df[df["regime"] == regime]
        if sub.empty:
            rows.append({"regime": regime, "n_trades": 0,
                         "avg_l1_spread_bps": float("nan"), "avg_dyn_rt_cost_bps": float("nan"),
                         "sharpe_gross": float("nan"), "sharpe_dynamic": float("nan"), "delta_sharpe": float("nan")})
            continue

        avg_cost_bps = (sub["total_cost_dollars"] / sub["allocated_capital"]).mean() * 10_000

        sub_with_net = sub.assign(net_pnl=sub["gross_pnl_dollars"] - sub["total_cost_dollars"])
        d_gross = sub.groupby("exit_date")["gross_pnl_dollars"].sum() / aum
        d_dyn   = sub_with_net.groupby("exit_date")["net_pnl"].sum() / aum

        # C2: zero-fill within regime span so std() is not computed over ~10-50 exit dates only
        if len(d_gross) >= 2:
            regime_idx = pd.bdate_range(start=pd.Timestamp(d_gross.index.min()), end=pd.Timestamp(d_gross.index.max()))
            d_gross = d_gross.reindex(regime_idx, fill_value=0.0)
            d_dyn   = d_dyn.reindex(regime_idx, fill_value=0.0)

        sharpe_gross = _annualised_sharpe(d_gross.to_numpy())
        sharpe_dyn   = _annualised_sharpe(d_dyn.to_numpy())

        regime_tickers = pd.concat([
            trade_log.loc[trade_log["fold_id"].isin(REGIME_MAP[regime]), "ticker_A"],
            trade_log.loc[trade_log["fold_id"].isin(REGIME_MAP[regime]), "ticker_B"],
        ]).unique()
        sp_slice = spreads[spreads["ticker"].isin(regime_tickers)]
        avg_l1   = sp_slice["full_spread_l1_bps"].mean() if len(sp_slice) else float("nan")

        rows.append({
            "regime":             regime,
            "n_trades":           len(sub),
            "avg_l1_spread_bps":  round(avg_l1, 2) if not np.isnan(avg_l1) else float("nan"),
            "avg_dyn_rt_cost_bps": round(avg_cost_bps, 2),
            "sharpe_gross":       round(sharpe_gross, 3) if not np.isnan(sharpe_gross) else float("nan"),
            "sharpe_dynamic":     round(sharpe_dyn, 3)   if not np.isnan(sharpe_dyn)   else float("nan"),
            "delta_sharpe":       round(sharpe_dyn - sharpe_gross, 3)
                                   if not (np.isnan(sharpe_dyn) or np.isnan(sharpe_gross)) else float("nan"),
        })

    return pd.DataFrame(rows).set_index("regime")


# ── src/plan3_validation/impact_validation.py ────────────────────────────────

DEFAULT_ROLLING_P3 = Path('.') / "data" / "microstructure" / "spread_rolling.parquet"


def _ols_with_pvalue(x: np.ndarray, y: np.ndarray) -> dict:
    """Simple OLS y = a + b*x. Returns alpha, beta, r2, p_value (two-sided t-test on beta)."""
    from scipy import stats
    mask = ~(np.isnan(x) | np.isnan(y))
    x, y = x[mask], y[mask]
    n = len(x)
    if n < 3 or np.std(x) < 1e-12:
        return {"alpha": float("nan"), "beta": float("nan"), "r2": float("nan"), "p_value": float("nan"), "n": n}
    x_mean, y_mean = x.mean(), y.mean()
    sx2  = ((x - x_mean) ** 2).sum()
    sxy  = ((x - x_mean) * (y - y_mean)).sum()
    beta = sxy / sx2
    alpha = y_mean - beta * x_mean
    y_hat  = alpha + beta * x
    ss_res = ((y - y_hat) ** 2).sum()
    ss_tot = ((y - y_mean) ** 2).sum()
    r2     = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    se_beta = np.sqrt(ss_res / (n - 2) / sx2) if n > 2 else float("nan")
    if not pd.isna(se_beta) and se_beta > 0:
        t_stat = beta / se_beta
        p = 2 * (1 - stats.t.cdf(abs(t_stat), df=n - 2))
    else:
        p = float("nan")
    return {"alpha": float(alpha), "beta": float(beta), "r2": float(r2), "p_value": float(p), "n": int(n)}


def validate_impact_prediction(spreads_path=DEFAULT_SPREADS_P3, rolling_path=DEFAULT_ROLLING_P3, max_rows: int = 2_000_000) -> dict:
    """
    Cross-sectional OLS: future_cost_proxy ~ spread_std_1d.
    future_cost_proxy = full_spread_l2_bps - full_spread_l1_bps (depth decay).
    Diagnostic only — no pass/fail gate.
    """
    needed_cols = ["timestamp_et", "ticker", "full_spread_l1_bps", "full_spread_l2_bps", "spread_std_1d"]
    kappa_path = Path(spreads_path).parent.parent / "kappa_per_fold.parquet"
    if kappa_path.exists():
        traded_tickers = pd.read_parquet(kappa_path)["ticker"].unique().tolist()
        ticker_filter  = [("ticker", "in", traded_tickers)]
    else:
        ticker_filter  = None
    try:
        spreads = pd.read_parquet(spreads_path, columns=needed_cols, filters=ticker_filter)
    except Exception:
        spreads = pd.read_parquet(spreads_path, filters=ticker_filter)
    if len(spreads) > max_rows:
        spreads = spreads.sample(n=max_rows, random_state=42)
    if "full_spread_l2_bps" not in spreads.columns:
        return {"beta": float("nan"), "r2": float("nan"), "p_value": float("nan"), "n": 0, "alpha": float("nan"),
                "note": "L2 spread column not present; diagnostic skipped."}
    if "spread_std_1d" not in spreads.columns:
        rolling = pd.read_parquet(rolling_path) if Path(rolling_path).exists() else None
        if rolling is not None and "spread_std_1d" in rolling.columns:
            spreads = spreads.merge(rolling[["timestamp_et", "ticker", "spread_std_1d"]], on=["timestamp_et", "ticker"], how="left")
        else:
            spreads["spread_std_1d"] = float("nan")

    merged = spreads.dropna(subset=["full_spread_l2_bps", "full_spread_l1_bps", "spread_std_1d"])
    proxy  = (merged["full_spread_l2_bps"] - merged["full_spread_l1_bps"]).to_numpy()
    sigma  = merged["spread_std_1d"].to_numpy()

    result = _ols_with_pvalue(sigma, proxy)
    result["note"] = "Diagnostic only. No pass/fail gate per workflow."
    return result


# ── src/plan3_validation/kill_zone.py ────────────────────────────────────────

DEFAULT_KAPPA_P3 = Path('.') / "data" / "kappa_per_fold.parquet"

_BUCKET_LABELS = [
    "09:30-10:00", "10:00-10:30", "10:30-11:00", "11:00-11:30",
    "11:30-12:00", "12:00-12:30", "12:30-13:00", "13:00-13:30",
    "13:30-14:00", "14:00-14:30", "14:30-15:00", "15:00-15:30", "15:30-15:59",
]


def _bucket_for_ts(ts: pd.Timestamp) -> str:
    h, m = ts.hour, ts.minute
    minutes = h * 60 + m
    start = 9 * 60 + 30
    idx = (minutes - start) // 30
    if idx < 0:
        return _BUCKET_LABELS[0]
    if idx >= len(_BUCKET_LABELS):
        return _BUCKET_LABELS[-1]
    return _BUCKET_LABELS[int(idx)]


def analyze_kill_zone(
    cost_log_path=DEFAULT_COST_LOG_P3,
    trade_log_path=DEFAULT_TRADE_LOG_P3,
    spreads_path=DEFAULT_SPREADS_P3,
    kappa_path=DEFAULT_KAPPA_P3,
) -> tuple:
    """
    Returns (seasonality_table, kill_zone_table).
    seasonality_table: index=bucket, columns=Tier1/Tier2/Tier3, values=avg_spread_bps.
    kill_zone_table:   index=bucket, columns=[n_trades, gross_bps, cost_bps, net_bps, kill_zone].
    """
    kappa = pd.read_parquet(kappa_path)
    traded_tickers = kappa["ticker"].unique().tolist()
    spreads = pd.read_parquet(
        spreads_path, columns=["timestamp_et", "ticker", "full_spread_l1_bps"],
        filters=[("ticker", "in", traded_tickers)],
    )

    # Part A: U-shape — vectorised bucket assignment (avoids 40M-row Python apply)
    ts      = pd.to_datetime(spreads["timestamp_et"])
    minutes = ts.dt.hour * 60 + ts.dt.minute
    idx     = ((minutes - (9 * 60 + 30)) // 30).clip(0, len(_BUCKET_LABELS) - 1).to_numpy()
    labels  = np.array(_BUCKET_LABELS)
    spreads["bucket"] = labels[idx]

    # Mode tie handled: DGX has equal kappa=0.3 and 0.5 across folds; iloc[0] picks
    # the smaller κ (more liquid tier) consistently on a tie.
    ticker_kappa = kappa.groupby("ticker")["kappa"].agg(
        lambda s: s.mode().iloc[0] if len(s.mode()) > 0 else s.iloc[0]
    )
    spreads["tier"] = spreads["ticker"].map(ticker_kappa).map(
        {0.3: "Tier1_Tight", 0.5: "Tier2_Medium", 0.8: "Tier3_Wide"}
    )

    seasonality = (
        spreads.dropna(subset=["tier"])
        .groupby(["bucket", "tier"])["full_spread_l1_bps"]
        .mean()
        .unstack("tier")
        .reindex(_BUCKET_LABELS)
        .round(2)
    )

    # Part B: kill zones from trades
    cost_log  = pd.read_parquet(cost_log_path)
    trade_log = pd.read_csv(trade_log_path)
    df = cost_log.merge(trade_log[["trade_id", "entry_ts", "allocated_capital"]], on="trade_id")
    df["entry_ts"] = pd.to_datetime(df["entry_ts"], utc=True).dt.tz_convert("US/Eastern")
    df["bucket"]   = df["entry_ts"].apply(_bucket_for_ts)
    df["gross_bps"] = (df["gross_pnl_dollars"]  / df["allocated_capital"]) * 10_000
    df["cost_bps"]  = (df["total_cost_dollars"]  / df["allocated_capital"]) * 10_000
    df["net_bps"]   = df["gross_bps"] - df["cost_bps"]

    kill = (
        df.groupby("bucket")
        .agg(n_trades=("trade_id", "count"),
             gross_bps=("gross_bps", "mean"),
             cost_bps=("cost_bps", "mean"),
             net_bps=("net_bps", "mean"))
        .reindex(_BUCKET_LABELS)
        .round(2)
    )
    kill["kill_zone"] = kill["net_bps"] < 0

    return seasonality, kill


# ── src/plan3_validation/negative_control.py ─────────────────────────────────

DEFAULT_FOLD_METRICS_P3 = Path('.') / "data" / "week4_inputs" / "fold_metrics.csv"


def run_dynamic_negative_control(fold_metrics_path=DEFAULT_FOLD_METRICS_P3) -> pd.DataFrame:
    """
    Reports Week 4's existing NC discrimination results. Dynamic-cost NC is
    deferred (Option B) because Week 4 stores only aggregate NC Sharpe, not
    per-trade logs that could be re-priced through Plan 2 hooks.
    """
    fm = pd.read_csv(fold_metrics_path)
    if "nc_pass" not in fm.columns:
        return pd.DataFrame([{"n_folds": len(fm), "nc_pass_count": 0,
                               "nc_pass_rate": float("nan"), "note": "fold_metrics.csv has no nc_pass column."}])

    pass_count = int(fm["nc_pass"].sum())
    n_folds    = (fm["n_trades"] > 0).sum() if "n_trades" in fm.columns else len(fm)

    return pd.DataFrame([{
        "n_traded_folds":         int(n_folds),
        "nc_pass_count_static":   pass_count,
        "nc_pass_rate_static":    pass_count / n_folds if n_folds else float("nan"),
        "nc_dynamic_status":      "DEFERRED",
        "note": (
            "Dynamic-cost NC requires re-running Week 4 NC pairs through Plan 2 hooks "
            "with synthetic NC trade timestamps. Week 4 stores only aggregate NC Sharpe, "
            "not per-trade logs. Plan 3 reports Week 4 static-cost NC results above and "
            "flags this as a Week 6 follow-up. (Option B per workflow.)"
        ),
    }])


# ── src/plan3_validation/overfitting_net.py ──────────────────────────────────

import itertools
import random
from scipy import stats as scipy_stats


def _expected_max_sharpe(n_trials: int) -> float:
    if n_trials <= 1:
        return 0.0
    p = 1.0 - 1.0 / n_trials
    return float(scipy_stats.norm.ppf(p))


def deflated_sharpe_ratio(
    sharpe_obs: float,
    n_obs: int,
    n_trials: int,
    skew: float = 0.0,
    kurt_excess: float = 0.0,
    sharpe_benchmark: float = 0.0,
) -> float:
    if n_obs < 5 or n_trials < 1 or np.isnan(sharpe_obs):
        return float("nan")
    e_max_sr = _expected_max_sharpe(n_trials)
    sr_var = (
        1.0 + 0.5 * sharpe_obs ** 2
        - skew * sharpe_obs
        + (kurt_excess / 4.0) * sharpe_obs ** 2
    ) / max(n_obs - 1, 1)
    sr_std = np.sqrt(max(sr_var, 1e-12))
    return float(scipy_stats.norm.cdf(
        (sharpe_obs - max(e_max_sr, sharpe_benchmark)) / sr_std
    ))


def _daily_returns_for_regime(cost_log: pd.DataFrame, trade_log: pd.DataFrame, cost_col: str) -> pd.Series:
    df = cost_log.merge(trade_log[["trade_id", "exit_ts", "fold_id", "allocated_capital"]], on="trade_id")
    df["exit_date"] = pd.to_datetime(df["exit_ts"], utc=True).dt.tz_convert("US/Eastern").dt.date
    if cost_col == "total_cost_gross":
        df["net_pnl"] = df["gross_pnl_dollars"]
    elif cost_col == "total_cost_static":
        df["net_pnl"] = df["gross_pnl_dollars"] - df["total_cost_static"]
    else:
        df["net_pnl"] = df["gross_pnl_dollars"] - df["total_cost_dollars"]
    aum = trade_log["allocated_capital"].sum()
    if aum <= 0:
        return pd.Series(dtype=float)
    daily = df.groupby("exit_date")["net_pnl"].sum().sort_index() / aum
    # C2: zero-fill every business day so std() covers the full holding period,
    # not just the ~90 exit dates.
    if len(daily) >= 2:
        full_idx = pd.bdate_range(start=pd.Timestamp(daily.index.min()), end=pd.Timestamp(daily.index.max()))
        daily = daily.reindex(full_idx, fill_value=0.0)
    return daily


def _per_fold_sharpe(cost_log: pd.DataFrame, trade_log: pd.DataFrame, cost_col: str) -> dict:
    df = cost_log.merge(trade_log[["trade_id", "exit_ts", "fold_id", "allocated_capital"]], on="trade_id")
    df["exit_date"] = pd.to_datetime(df["exit_ts"], utc=True).dt.tz_convert("US/Eastern").dt.date
    if cost_col == "total_cost_gross":
        df["net_pnl"] = df["gross_pnl_dollars"]
    elif cost_col == "total_cost_static":
        df["net_pnl"] = df["gross_pnl_dollars"] - df["total_cost_static"]
    else:
        df["net_pnl"] = df["gross_pnl_dollars"] - df["total_cost_dollars"]

    out = {}
    for fold_id, sub in df.groupby("fold_id"):
        aum_fold = sub["allocated_capital"].sum()
        if aum_fold <= 0:
            out[int(fold_id)] = float("nan")
            continue
        daily = sub.groupby("exit_date")["net_pnl"].sum() / aum_fold
        if len(daily) >= 2:
            full_idx = pd.bdate_range(start=pd.Timestamp(daily.index.min()), end=pd.Timestamp(daily.index.max()))
            daily = daily.reindex(full_idx, fill_value=0.0)
        if len(daily) < 2 or daily.std(ddof=1) < 1e-12:
            out[int(fold_id)] = float("nan")
            continue
        out[int(fold_id)] = float(daily.mean() / daily.std(ddof=1) * np.sqrt(252))
    return out


def _compute_pbo(per_fold_sharpe: dict, n_splits: int = 4) -> float:
    valid = {f: s for f, s in per_fold_sharpe.items() if not np.isnan(s)}
    folds = list(valid.keys())
    n = len(folds)
    if n < 4:
        return float("nan")
    k   = max(2, n // n_splits)
    rng = random.Random(42)
    combos = list(itertools.combinations(range(n), k))
    if len(combos) > 5_000:
        combos = rng.sample(combos, 5_000)
    n_overfit = 0
    n_total   = 0
    for is_combo in combos:
        is_set   = set(is_combo)
        oos_idx  = [i for i in range(n) if i not in is_set]
        if not oos_idx:
            continue
        is_sharpes  = [valid[folds[i]] for i in is_combo]
        oos_sharpes = [valid[folds[i]] for i in oos_idx]
        is_best_idx  = int(np.argmax(is_sharpes))
        is_best_fold = folds[is_combo[is_best_idx]]
        is_best_sharpe = valid[is_best_fold]
        oos_median = float(np.median(oos_sharpes))
        if is_best_sharpe < oos_median:
            n_overfit += 1
        n_total += 1
    return n_overfit / n_total if n_total else float("nan")


def compute_overfitting_diagnostics(
    cost_log_path=DEFAULT_COST_LOG_P3,
    trade_log_path=DEFAULT_TRADE_LOG_P3,
    n_strategy_variants: int = 50,
) -> pd.DataFrame:
    """
    Returns DataFrame with rows ['Raw Sharpe', 'DSR p-value', 'PBO'] and columns ['Gross', 'Static', 'Dynamic'].

    n_strategy_variants: number of independent strategy configurations tested over the full
    research process (Weeks 1-5). Bailey & Lopez de Prado (2014) define this as the number
    of *strategies* tried, NOT the number of walk-forward folds. Using fold count (≈22)
    underestimates E[max_SR] and inflates DSR. Default 50 is a conservative estimate.
    """
    cost_log  = pd.read_parquet(cost_log_path)
    trade_log = pd.read_csv(trade_log_path)

    regimes = {"Gross": "total_cost_gross", "Static": "total_cost_static", "Dynamic": "total_cost_dollars"}
    out = {}
    for label, col in regimes.items():
        # Use the same equity-curve-based return series as the headline Sharpe table
        daily = reconstruct_daily_returns(cost_log, trade_log, col).to_numpy()
        if len(daily) < 2:
            out[label] = {"Raw Sharpe": float("nan"), "DSR p-value": float("nan"), "PBO": float("nan")}
            continue
        sd = daily.std(ddof=1)
        sharpe = float(daily.mean() / sd * np.sqrt(252)) if sd >= 1e-12 else float("nan")
        skew   = float(scipy_stats.skew(daily))
        kurt   = float(scipy_stats.kurtosis(daily, fisher=True))
        per_fold = _per_fold_sharpe(cost_log, trade_log, col)
        dsr  = deflated_sharpe_ratio(sharpe_obs=sharpe, n_obs=len(daily), n_trials=n_strategy_variants,
                                     skew=skew, kurt_excess=kurt)
        pbo  = _compute_pbo(per_fold)
        out[label] = {
            "Raw Sharpe":  round(sharpe, 4) if not np.isnan(sharpe) else float("nan"),
            "DSR p-value": round(dsr,    4) if not np.isnan(dsr)    else float("nan"),
            "PBO":         round(pbo,    4) if not np.isnan(pbo)    else float("nan"),
        }
    return pd.DataFrame(out)


# ── src/plan3_validation/sensitivity_oat.py ──────────────────────────────────

def _net_sharpe_after_perturb(cost_log: pd.DataFrame, trade_log: pd.DataFrame, impact_mult: float = 1.0, borrow_mult: float = 1.0) -> float:
    gross_daily = _load_gross_daily_returns(DEFAULT_EQUITY_DIR)
    if gross_daily.empty:
        return float("nan")

    aum = trade_log["allocated_capital"].sum()
    if aum <= 0:
        return float("nan")

    df = cost_log.merge(trade_log[["trade_id", "exit_ts"]], on="trade_id")
    df["exit_dt"] = (pd.to_datetime(df["exit_ts"], utc=True).dt.tz_convert("US/Eastern").dt.normalize())
    perturbed_cost = (
        df["spread_cost_dollars"]
        + df["impact_cost_dollars"]   * impact_mult
        + df["borrow_cost_dollars"]   * borrow_mult
        + df["rebalance_cost_dollars"]
    )
    cost_by_day = df.assign(cost=perturbed_cost).groupby("exit_dt")["cost"].sum() / aum
    cost_adj    = cost_by_day.reindex(gross_daily.index, fill_value=0.0)
    daily = (gross_daily - cost_adj).to_numpy()
    if len(daily) < 2:
        return float("nan")
    sd = daily.std(ddof=1)
    if sd < 1e-12:
        return float("nan")
    return float(daily.mean() / sd * np.sqrt(252))


def run_oat_sensitivity(cost_log_path=DEFAULT_COST_LOG_P3, trade_log_path=DEFAULT_TRADE_LOG_P3) -> pd.DataFrame:
    """
    9 OAT runs: kappa multiplier {0.5, 1.0, 1.5} × borrow rate {30, 50, 100} bps.
    L2 spread level deferred (symmetric LOB limitation).
    Re-aggregation strategy — no re-loop over trades; scales components linearly.
    """
    cost_log  = pd.read_parquet(cost_log_path)
    trade_log = pd.read_csv(trade_log_path)

    baseline_sharpe = _net_sharpe_after_perturb(cost_log, trade_log, 1.0, 1.0)

    rows = []
    for k_mult in (0.5, 1.0, 1.5):
        for borrow in (30.0, 50.0, 100.0):
            borrow_mult = borrow / 50.0
            sh = _net_sharpe_after_perturb(cost_log, trade_log, k_mult, borrow_mult)
            rows.append({
                "kappa_mult":        k_mult,
                "borrow_bps":        borrow,
                "spread_level":      "L1",
                "net_sharpe":        round(sh, 4) if not np.isnan(sh) else float("nan"),
                "delta_vs_baseline": round(sh - baseline_sharpe, 4)
                                      if not (np.isnan(sh) or np.isnan(baseline_sharpe)) else float("nan"),
            })

    rows.append({"kappa_mult": float("nan"), "borrow_bps": float("nan"),
                 "spread_level": "L2", "net_sharpe": float("nan"), "delta_vs_baseline": float("nan")})
    return pd.DataFrame(rows)


# ── src/plan3_validation/report_builder.py ───────────────────────────────────

DEFAULT_OUTPUT_P3 = Path('.') / "reports" / "net_of_fees_report.md"


def _md_table(df: pd.DataFrame) -> str:
    return df.to_markdown()


def assemble_report(output_path=DEFAULT_OUTPUT_P3) -> dict:
    """Builds the 12-section report. Returns dict of section outputs for numerical inspection."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cost_log = pd.read_parquet(Path('.') / "data" / "cost_log.parquet")
    kappa    = pd.read_parquet(Path('.') / "data" / "kappa_per_fold.parquet")

    sec4  = generate_before_after_table()
    sec5  = generate_cost_waterfall()
    sec6  = analyze_regime_costs()
    sec7  = validate_impact_prediction()
    sec8a, sec8b = analyze_kill_zone()
    sec9  = run_dynamic_negative_control()
    sec10 = compute_overfitting_diagnostics()
    sec11 = run_oat_sensitivity()

    mean_rt_bps      = (cost_log["total_cost_dollars"] / 20_000).mean() * 10_000
    flag_blowup      = check_dynamic_cost_blowup(mean_rt_bps)
    neg_costs        = (cost_log["total_cost_dollars"] < 0).any()
    net_gt_gross     = (cost_log["net_pnl_dollars"] > cost_log["gross_pnl_dollars"]).any()
    flag_math        = bool(neg_costs or net_gt_gross)
    ticker_kappa_changes = (kappa.groupby("ticker")["kappa"].nunique() > 1).sum()
    flag_kappa       = check_kappa_instability(int(ticker_kappa_changes))

    sharpe_gross = float(sec4.loc["Sharpe (annual)", "Gross"])
    sharpe_dyn   = float(sec4.loc["Sharpe (annual)", "Dynamic"])
    flag_cost_exceeds = check_cost_exceeds_alpha(sharpe_dyn, sharpe_gross)

    dsr_gross = float(sec10.loc["DSR p-value", "Gross"])   if "Gross"   in sec10.columns else float("nan")
    dsr_dyn   = float(sec10.loc["DSR p-value", "Dynamic"]) if "Dynamic" in sec10.columns else float("nan")
    flag_dsr  = check_dsr_degradation(1 - dsr_dyn   if not pd.isna(dsr_dyn)   else 1.0,
                                       1 - dsr_gross if not pd.isna(dsr_gross) else 1.0)

    n_strategy_variants = 50
    e_max_sr = _expected_max_sharpe(n_strategy_variants)

    if flag_cost_exceeds:
        verdict = "Strategy alpha is real but untradeable: net Sharpe < 0 under dynamic costs."
    elif sharpe_dyn > 0:
        verdict = f"Strategy survives friction. Dynamic net Sharpe = {sharpe_dyn:.3f}."
    elif sharpe_dyn <= 0 and sharpe_gross <= 0:
        verdict = "Strategy underperforms even before costs; friction is not the limiting factor."
    else:
        verdict = f"Strategy degraded by friction. Dynamic Sharpe = {sharpe_dyn:.3f}."

    # Pre-extract values used in key-findings blocks
    kt = kappa["kappa"].value_counts().sort_index().rename("count").to_frame()
    tier1_pct = kt.loc[0.3, "count"] / len(kappa) * 100 if 0.3 in kt.index else 0.0
    tier3_pct = kt.loc[0.8, "count"] / len(kappa) * 100 if 0.8 in kt.index else 0.0
    ols_r2    = sec7.get("r2", float("nan"))

    cost_dyn_bps    = float(sec4.loc["Avg RT Cost (bps)", "Dynamic"])
    cost_static_bps = float(sec4.loc["Avg RT Cost (bps)", "Static60bps"])
    folds_gross_pct  = float(sec4.loc["% Folds Profitable", "Gross"])        * 100
    folds_dyn_pct    = float(sec4.loc["% Folds Profitable", "Dynamic"])      * 100
    folds_static_pct = float(sec4.loc["% Folds Profitable", "Static60bps"]) * 100
    wr_gross_pct  = float(sec4.loc["Win Rate", "Gross"])        * 100
    wr_static_pct = float(sec4.loc["Win Rate", "Static60bps"]) * 100
    wr_dyn_pct    = float(sec4.loc["Win Rate", "Dynamic"])      * 100

    _overall      = sec5.loc["Overall"]
    _spread_abs   = abs(float(_overall["spread_bps"]))
    _impact_abs   = abs(float(_overall["impact_bps"]))
    _borrow_abs   = abs(float(_overall["borrow_bps"]))
    _reb_abs      = abs(float(_overall.get("rebalance_bps", 0)))
    _total_abs    = _spread_abs + _impact_abs + _borrow_abs + _reb_abs
    impact_share_pct = _impact_abs / _total_abs * 100 if _total_abs else 0.0
    borrow_bps_avg   = _borrow_abs

    eb_gross = float(sec6.loc["Early Bull 2023", "sharpe_gross"])    if "Early Bull 2023"        in sec6.index else float("nan")
    eb_dyn   = float(sec6.loc["Early Bull 2023", "sharpe_dynamic"])  if "Early Bull 2023"        in sec6.index else float("nan")
    lb_rt    = float(sec6.loc["Late Bull 2025-Q12026", "avg_dyn_rt_cost_bps"]) if "Late Bull 2025-Q12026" in sec6.index else float("nan")
    lb_delta = float(sec6.loc["Late Bull 2025-Q12026", "delta_sharpe"])        if "Late Bull 2025-Q12026" in sec6.index else float("nan")

    _kz_valid = sec8b.dropna(subset=["n_trades"])
    if not _kz_valid.empty:
        _dom_idx     = _kz_valid["n_trades"].idxmax()
        _dom_trades  = int(_kz_valid.loc[_dom_idx, "n_trades"])
        _total_trades_kz = int(_kz_valid["n_trades"].sum())
        _dom_pct     = _dom_trades / _total_trades_kz * 100
    else:
        _dom_trades, _dom_pct, _total_trades_kz = 0, 0.0, 0

    nc_pass_rate = float(sec9.loc[0, "nc_pass_rate_static"]) if "nc_pass_rate_static" in sec9.columns else float("nan")
    pbo_val      = float(sec10.loc["PBO", "Dynamic"]) if "PBO" in sec10.index and "Dynamic" in sec10.columns else float("nan")

    _valid_sens  = sec11["net_sharpe"].dropna()
    sh_sens_range = float(_valid_sens.max() - _valid_sens.min()) if len(_valid_sens) > 1 else float("nan")
    _b30   = sec11.loc[(sec11["kappa_mult"] == 1.0) & (sec11["borrow_bps"] == 30.0),  "net_sharpe"]
    _b100  = sec11.loc[(sec11["kappa_mult"] == 1.0) & (sec11["borrow_bps"] == 100.0), "net_sharpe"]
    borrow_delta = float(abs(_b30.iloc[0] - _b100.iloc[0])) if (len(_b30) and len(_b100)) else float("nan")

    _t1_open = float(sec8a.loc["09:30-10:00", "Tier1_Tight"]) if "09:30-10:00" in sec8a.index else float("nan")
    _t1_peak = float(sec8a.loc["10:00-10:30", "Tier1_Tight"]) if "10:00-10:30" in sec8a.index else float("nan")
    _t3_open = float(sec8a.loc["09:30-10:00", "Tier3_Wide"])  if "09:30-10:00" in sec8a.index else float("nan")
    open_ratio = _t1_open / _t1_peak if _t1_peak else float("nan")

    # Compose markdown (abbreviated here; full section text mirrors actual report_builder.py)
    md_lines = [
        "# Net-of-Fees Performance Report — Week 5", "",
        "## 1. Executive Summary", "",
        f"**Verdict:** {verdict}", "",
        f"- Trades evaluated: {len(cost_log)}",
        f"- Mean dynamic RT cost: ~{mean_rt_bps:.1f} bps",
        f"- Sharpe (Gross): {sharpe_gross:.3f}",
        f"- Sharpe (Dynamic): {sharpe_dyn:.3f}", "",
        "## 4. Before/After Table", "", _md_table(sec4), "",
        "## 5. Cost Waterfall", "", _md_table(sec5), "",
        "## 6. Regime-Conditional Costs", "", _md_table(sec6), "",
        "## 8. Kill Zone + Seasonality", "", _md_table(sec8b), "",
        "## 10. Overfitting Diagnostics (Net)", "", _md_table(sec10), "",
        "## 11. Sensitivity Analysis", "", _md_table(sec11), "",
        "## 12. Verdict", "", f"**{verdict}**", "",
        f"- `dynamic_cost_blowup`: {flag_blowup}",
        f"- `cost_exceeds_alpha`:  {flag_cost_exceeds}",
        f"- `kappa_instability`:   {flag_kappa}",
        f"- `dsr_degradation`:     {flag_dsr}",
        f"- `math_violation`:      {flag_math}",
    ]

    output_path.write_text("\n".join(md_lines), encoding="utf-8")

    return {
        "before_after": sec4, "waterfall": sec5, "regime_costs": sec6,
        "impact_validation": sec7, "kill_zone_part_a": sec8a, "kill_zone_part_b": sec8b,
        "neg_control": sec9, "overfitting": sec10, "sensitivity": sec11,
        "verdict": verdict,
        "red_flags": {
            "dynamic_cost_blowup": flag_blowup, "cost_exceeds_alpha": flag_cost_exceeds,
            "kappa_instability": flag_kappa, "dsr_degradation": flag_dsr, "math_violation": flag_math,
        },
        "output_path": str(output_path),
    }


# ── src/plan3_validation/smoke_test.py ───────────────────────────────────────

def run_plan3_smoke_test():
    print("--- Plan 3 Smoke Test (requires real data artefacts) ---")
    ba = generate_before_after_table()
    assert set(ba.columns) == {"Gross", "Static60bps", "Dynamic"}
    assert ba.shape == (8, 3)
    print("[PASS] Before/After table 8x3")

    wf = generate_cost_waterfall()
    assert "Overall" in wf.index
    overall = wf.loc["Overall"]
    summed = overall["gross_bps"] + overall["spread_bps"] + overall["impact_bps"] + overall["borrow_bps"] + overall["rebalance_bps"]
    assert abs(summed - overall["net_bps"]) < 0.5
    print("[PASS] Waterfall sums to net within rounding")

    assert check_dynamic_cost_blowup(160) is True
    assert check_dynamic_cost_blowup(50)  is False
    assert check_cost_exceeds_alpha(net_sharpe=-0.5, gross_sharpe=1.5) is True
    assert check_cost_exceeds_alpha(net_sharpe=0.5,  gross_sharpe=1.5) is False
    assert check_kappa_instability(3) is True
    assert check_kappa_instability(1) is False
    assert check_dsr_degradation(0.20, 0.02) is True
    assert check_dsr_degradation(0.04, 0.02) is False
    assert check_math_violation(-1.0, 0.0, 0.0) is True
    assert check_math_violation(1.0, 100.0, 50.0) is True
    assert check_math_violation(1.0, 50.0, 100.0) is False
    print("[PASS] All 5 red flag triggers fire correctly on synthetic inputs")

    print("Plan 3 Smoke Test Passed.")


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  PIPELINE ENTRY POINT — run_pipeline.py                                     ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

import argparse

MICRO_FILES = [
    Path('.') / "data" / "microstructure" / "spreads_1min.parquet",
    Path('.') / "data" / "microstructure" / "spread_rolling.parquet",
    Path('.') / "data" / "microstructure" / "spread_seasonality.parquet",
    Path('.') / "data" / "microstructure" / "spread_summary.parquet",
]


def _section(title: str) -> None:
    print("\n" + "=" * 65)
    print(f"  {title}")
    print("=" * 65)


def _run_plan0(force: bool = False) -> None:
    missing = [f for f in MICRO_FILES if not f.exists()]
    if not force and not missing:
        _section("Plan 0 — SKIPPED (microstructure parquets already exist)")
        return
    _section("Plan 0 — Running")
    t0 = time.time()
    result = run_plan0_real()
    print(f"  Plan 0 done: {result['ok_count']} tickers, {result['total_rows']:,} rows, {(time.time()-t0)/60:.1f} min")


def _run_plan2_pipeline() -> tuple:
    _section("Plan 2 — Cost application")
    t0 = time.time()
    cost_log, kappa = run_plan2()
    print(f"  Trades priced: {len(cost_log)}")
    print(f"  Elapsed: {time.time()-t0:.1f}s")
    return cost_log, kappa


def _run_plan3_pipeline() -> dict:
    _section("Plan 3 — Validation & report")
    t0 = time.time()
    result = assemble_report()
    print(f"  Report: {result['output_path']} ({time.time()-t0:.1f}s)")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force0", action="store_true")
    args = parser.parse_args()

    wall_start = time.time()
    _run_plan0(force=args.force0)
    _run_plan2_pipeline()
    result = _run_plan3_pipeline()

    _section(f"Pipeline complete — {(time.time()-wall_start)/60:.1f} min total")
    print(f"  Verdict: {result['verdict']}")
    print(f"  Red flags: {result['red_flags']}")


if __name__ == "__main__":
    main()
