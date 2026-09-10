"""
v4_exec_simulator.py — replay the V4 ledger under two fill variants (OFFLINE)
============================================================================

Bước 1 (exec-sim core) + Bước 2 (live-account anchor). No live orders, no
network. Replays every trade in
`trading_1min/results/v4_exec_sim/trades_z30_composite.csv` under:

  V-close  = idealized backtest fill. Per-leg fill = the price the engine
             assumed (its decision/close reference). Slippage = 0.
             cost = model half-spread + commission + borrow.

  V-open   = realistic/live fill. Per-leg fill = the OPEN of the execution
             session + REAL L1 half-spread (buy: open*(1+hs), sell:
             open*(1-hs)). cost = slippage + commission + borrow.

  V-open-mid = optimistic bound of V-open. SAME fill session/timing as
             V-open, but fill = the RAW open (NO +/- half-spread). Gives a
             per-trade bracket [V-open-mid .. V-open]; width = the real L1
             half-spread crossed at the open.

  V-1530   = execute at 15:30 of the SAME fill session as V-open. decision
             reference identical to V-open (close[idx-1] etc.); fill = the
             15:30 price of that session (open of the 15:30 bar, minute 930;
             nearest bar in 15:30-15:45 if that exact minute is missing).
             Bracket:
               V-1530-mid  = fill at raw 15:30 price (no spread) [optimistic].
               V-1530      = fill at 15:30 price +/- the 15:30 L1 half-spread
                             (buy +, sell -) [conservative/taker].
             cost = slippage + commission + borrow. Passive-fill realism is
             DEFERRED to probe calibration; the [mid..spread] bracket already
             brackets passive(~mid) <-> taker(~spread).

  Experiment: V-1530 trades a cheaper 15:30 spread for the open->15:30
  intraday drift (fills ~6h later than V-open). Decompose:
    (v1530 mid slippage - vopen mid slippage) = intraday-drift difference;
    (open half-spread - 15:30 half-spread)    = spread saving;
    (V-1530 cost - V-open cost)               = drift_diff - spread_saving.

Impact (kappa*sigma) is DROPPED from all variant costs (locked decision D2);
it is still read from cost_engine and reported as context (the official
backtest net = ledger net INCLUDES impact).

--------------------------------------------------------------------------
TIMING CONVENTION (determined from engine_daily.engine_daily, verified vs the
live order path in live/main.py):

  The daily engine sets position[t] = signal[t-1] and books
  daily_pnl[t] = position[t]*(spread[t]-spread[t-1]). Telescoping a trade's
  P&L shows the position is economically established at close[entry_idx-1]
  (the DECISION close, one bar BEFORE the ledger's entry_date) and, for a
  natural exit, released at close[exit_idx-1]. live/main.py confirms this:
  decision_price = exp(log_close.iloc[-1]) = the last completed daily close
  (= close[entry_idx-1]); the market order then fills at the NEXT session's
  open. So live's realized slippage = open[entry_idx] - close[entry_idx-1].

  Therefore, faithfully:
    ENTRY (all trades): decision = close of the trading session BEFORE
        entry_date; V-open fill = open of entry_date + real L1 spread.
    EXIT zero_cross/hard_sl: decision = close of session BEFORE exit_date;
        V-open fill = open of exit_date + real L1 spread.
    EXIT open_at_eom (~90%): the engine HOLDS through eng_exit_date's close
        (last bar), so decision = close of eng_exit_date; V-open fill = open
        of eng_exit_date + real L1 spread (same session — matches D4).

  This deviates from a literal "V-open = open of the same session as the
  V-close close" only for entries + natural exits, where the engine's 1-bar
  lag puts the decision close and the execution open on ADJACENT days — which
  is exactly what live does and what live records as realized_cost_bps.

LEG SIZING (D3) — matches live/main.py:407-408 (BETA-SCALED, not equal):
    qty_a = notional / decision_price_a
    qty_b = notional * |beta| / decision_price_b
  i.e. leg-A dollar notional = N, leg-B dollar notional = N*|beta|. (Live
  floors qty to int shares >=1; we keep continuous shares — negligible at
  backtest notional scale and slippage_bps is scale-invariant.)

SLIPPAGE (matches live/monitor/cost_overlay.compute_realized_cost_usd):
    per leg  buy : qty*(fill - decision);  sell : qty*(decision - fill)
    slippage_bps = sum_legs slippage_usd / sum_legs (qty*decision) * 1e4
--------------------------------------------------------------------------

CLI:
    python trading_1min/research/v4_exec_simulator.py --smoke   # 2 pairs, verbose
    python trading_1min/research/v4_exec_simulator.py           # all trades
"""

from __future__ import annotations

import os as _os

for _var in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
             "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"):
    _os.environ[_var] = "1"

import argparse
import bisect
import sqlite3
import sys
import time
from datetime import date as _date
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")   # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8")   # type: ignore[attr-defined]
except (AttributeError, Exception):
    pass

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
WEEK6 = REPO_ROOT / "Week 6"
sys.path.insert(0, str(WEEK6))

from engine_daily import cost_engine
from engine_daily.cost_engine import compute_pair_trade_cost
# Bước 2: the live realized-cost function itself (Gate 2 formula equivalence).
from live.monitor.cost_overlay import compute_realized_cost_usd

# ---- Paths ----
EXEC_DIR = REPO_ROOT / "trading_1min" / "results" / "v4_exec_sim"
LEDGER_PATH = EXEC_DIR / "trades_z30_composite.csv"
DAILY_PNL_PATH = EXEC_DIR / "daily_pnl_by_fold.csv"
COST_OUT = EXEC_DIR / "cost_by_variant.csv"
SHARPE_OUT = EXEC_DIR / "sharpe_by_variant.csv"
REPORT_OUT = EXEC_DIR / "report.txt"

TOTAL_CAPITAL = 1_000_000.0        # same as run_v4_pipeline
SESSION_MIN_LO = 570               # 09:30 ET
SESSION_MIN_HI = 959               # 15:59 ET
MIN_1530_LO = 930                  # 15:30 ET (the V-1530 fill bar)
MIN_1530_HI = 945                  # nearest bar within 15:30-15:45 if 15:30 missing


# ============================================================================
# Rename-aware path resolution (Quant Program -> Pairs Trading Strategy)
# ============================================================================

def resolve_paths() -> dict[str, Path]:
    out: dict[str, Path] = {}
    px = REPO_ROOT / "Week 4" / "data" / "validated" / "1min_phase2"
    out["prices_1min"] = px
    out["spreads_1min"] = REPO_ROOT / "Week 5" / "data" / "microstructure" / "spreads_1min.parquet"
    cache = cost_engine._DEFAULT_CACHE
    if not cache.exists():
        cache = REPO_ROOT / "Week 6" / "cost" / "daily_spread_cache.parquet"
    out["cost_cache"] = cache
    summ = cost_engine._WEEK5_SUMMARY
    if not summ.exists():
        summ = REPO_ROOT / "Week 5" / "data" / "microstructure" / "spread_summary.parquet"
    out["cost_summary"] = summ
    return out


# ============================================================================
# Per-ticker market data store (compact per-session maps; big frames discarded)
# ============================================================================

class MarketData:
    """Lazily loads, per ticker, a compact per-session table:
        date -> (open_0930, close_last, half_spread_l1_bps)
    from 1min_phase2 (prices) + spreads_1min (real L1). Caches only the small
    per-date maps, never the raw 1-min frames."""

    def __init__(self, prices_dir: Path, spreads_path: Path):
        self.prices_dir = prices_dir
        self.spreads_path = spreads_path
        self._cache: dict[str, dict] = {}     # ticker -> {dates, open, close, hs}

    def _load(self, ticker: str) -> dict | None:
        if ticker in self._cache:
            return self._cache[ticker]
        pf = self.prices_dir / f"{ticker}.parquet"
        if not pf.exists():
            self._cache[ticker] = None
            return None
        px = pd.read_parquet(pf)
        mins = px.index.hour * 60 + px.index.minute
        sess = px[(mins >= SESSION_MIN_LO) & (mins <= SESSION_MIN_HI)]
        if len(sess) == 0:
            self._cache[ticker] = None
            return None
        day = [t.date() for t in sess.index]
        sess_min = (sess.index.hour * 60 + sess.index.minute).to_numpy()
        g = pd.DataFrame({"open": sess["open"].values, "close": sess["close"].values,
                          "min": sess_min},
                         index=pd.Index(day, name="d"))
        opens = g.groupby(level=0)["open"].first()
        closes = g.groupby(level=0)["close"].last()

        # 15:30 price = open of the first bar with minute in [930, 945] (at/after
        # 15:30). Matches V-open's use of the OPEN field for the execution price.
        gw = g[(g["min"] >= MIN_1530_LO) & (g["min"] <= MIN_1530_HI)].reset_index()
        gw = gw.sort_values(["d", "min"])
        px1530 = gw.groupby("d")["open"].first()
        px1530_map = {d: float(v) for d, v in px1530.items()}

        # Real L1 half-spread: first VALID bar at/after 09:30 (open) and at/after
        # 15:30 (the V-1530 fill) for each session.
        hs_map: dict[_date, float] = {}
        hs1530_map: dict[_date, float] = {}
        try:
            sp = pd.read_parquet(self.spreads_path,
                                 filters=[("ticker", "==", ticker)],
                                 columns=["timestamp_et", "is_valid", "half_spread_l1_bps"])
            if len(sp):
                smins = sp["timestamp_et"].dt.hour * 60 + sp["timestamp_et"].dt.minute
                sp = sp[(smins >= SESSION_MIN_LO) & (smins <= SESSION_MIN_HI) & sp["is_valid"]]
                sp = sp[np.isfinite(sp["half_spread_l1_bps"].values)]
                sp = sp.sort_values("timestamp_et")
                sp["d"] = sp["timestamp_et"].dt.date
                first = sp.groupby("d")["half_spread_l1_bps"].first()
                hs_map = {d: float(v) for d, v in first.items()}
                sp["min"] = sp["timestamp_et"].dt.hour * 60 + sp["timestamp_et"].dt.minute
                sp15 = sp[(sp["min"] >= MIN_1530_LO) & (sp["min"] <= MIN_1530_HI)]
                first15 = sp15.groupby("d")["half_spread_l1_bps"].first()
                hs1530_map = {d: float(v) for d, v in first15.items()}
        except Exception:
            hs_map = {}
            hs1530_map = {}

        rec = {
            "dates": list(opens.index),      # sorted python dates
            "open": {d: float(v) for d, v in opens.items()},
            "close": {d: float(v) for d, v in closes.items()},
            "hs": hs_map,
            "px1530": px1530_map,
            "hs1530": hs1530_map,
        }
        self._cache[ticker] = rec
        return rec

    def close_on(self, ticker: str, d: _date) -> float | None:
        rec = self._load(ticker)
        if rec is None:
            return None
        return rec["close"].get(d)

    def prior_close(self, ticker: str, d: _date) -> float | None:
        """Close of the trading session strictly before `d` (= close[idx-1])."""
        rec = self._load(ticker)
        if rec is None:
            return None
        dates = rec["dates"]
        i = bisect.bisect_left(dates, d)
        if i == 0:
            return None
        return rec["close"].get(dates[i - 1])

    def open_on(self, ticker: str, d: _date) -> float | None:
        rec = self._load(ticker)
        if rec is None:
            return None
        return rec["open"].get(d)

    def half_spread_bps_on(self, ticker: str, d: _date) -> float | None:
        rec = self._load(ticker)
        if rec is None:
            return None
        return rec["hs"].get(d)

    def price_1530_on(self, ticker: str, d: _date) -> float | None:
        """Price at 15:30 = open of the first bar in [15:30, 15:45] on `d`."""
        rec = self._load(ticker)
        if rec is None:
            return None
        return rec["px1530"].get(d)

    def half_spread_1530_bps_on(self, ticker: str, d: _date) -> float | None:
        """Real L1 half-spread of the first valid bar in [15:30, 15:45] on `d`."""
        rec = self._load(ticker)
        if rec is None:
            return None
        return rec["hs1530"].get(d)


# ============================================================================
# Slippage (replicated cost_overlay convention) — used for V-open
# ============================================================================

def leg_slippage_usd(side: str, qty: float, fill: float, decision: float) -> float:
    """buy filled higher than decision -> positive cost; sell filled lower -> positive."""
    if side == "buy":
        return qty * (fill - decision)
    return qty * (decision - fill)


# ============================================================================
# Gate 2 — formula equivalence with live cost_overlay.compute_realized_cost_usd
# ============================================================================

def gate2_formula_equivalence() -> tuple[bool, str]:
    """Build an in-memory `orders` table, insert synthetic filled legs, call the
    REAL live function, and confirm our slippage arithmetic yields identical
    (slip_usd, notional, bps)."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE orders (pair_id TEXT, bar_ts TEXT, status TEXT, side TEXT, "
        "qty REAL, fill_qty REAL, fill_price REAL, decision_price REAL)"
    )
    # synthetic legs: (side, qty, fill, decision) across an entry bar + exit bar
    legs = [
        ("ENT", "buy", 100.0, 50.10, 50.00),
        ("ENT", "sell", 63.0, 79.90, 80.00),
        ("EXT", "sell", 100.0, 49.95, 50.05),
        ("EXT", "buy", 63.0, 80.20, 80.00),
    ]
    for bar, side, qty, fill, dec in legs:
        conn.execute(
            "INSERT INTO orders VALUES ('PZ', ?, 'filled', ?, ?, ?, ?, ?)",
            (bar, side, qty, qty, fill, dec),
        )
    live_slip, live_notional = compute_realized_cost_usd(conn, "PZ", "ENT", "EXT")
    live_bps = live_slip / live_notional * 1e4 if live_notional > 0 else 0.0

    my_slip = sum(leg_slippage_usd(side, qty, fill, dec) for _, side, qty, fill, dec in legs)
    my_notional = sum(qty * dec for _, _, qty, _, dec in legs)
    my_bps = my_slip / my_notional * 1e4 if my_notional > 0 else 0.0

    ok = (abs(live_slip - my_slip) < 1e-9 and abs(live_notional - my_notional) < 1e-9
          and abs(live_bps - my_bps) < 1e-9)
    msg = (f"live=(slip={live_slip:.6f}, notl={live_notional:.4f}, bps={live_bps:.6f}) | "
           f"mine=(slip={my_slip:.6f}, notl={my_notional:.4f}, bps={my_bps:.6f}) | "
           f"max|Δ|={max(abs(live_slip-my_slip), abs(live_notional-my_notional), abs(live_bps-my_bps)):.2e}")
    conn.close()
    return ok, msg


# ============================================================================
# Per-trade simulation
# ============================================================================

def entry_sides(direction: int) -> tuple[str, str]:
    # direction +1 => long spread => buy A / sell B ; -1 => sell A / buy B
    return ("buy", "sell") if direction > 0 else ("sell", "buy")


def exit_sides(direction: int) -> tuple[str, str]:
    return ("sell", "buy") if direction > 0 else ("buy", "sell")


def simulate_trade(row: pd.Series, md: MarketData, cost_data) -> dict:
    ta, tb = row["ticker_a"], row["ticker_b"]
    direction = int(row["direction"])
    beta = float(row["beta"])
    npl = float(row["notional_per_leg"])            # ledger per-leg notional
    N = 2.0 * npl                                    # per-pair notional
    N_a, N_b = N, N * abs(beta)                      # BETA-SCALED leg notionals (live)
    gross = float(row["gross_pnl_spread"])
    is_eom = (row["exit_reason"] == "open_at_eom")

    entry_d = pd.Timestamp(row["entry_date"]).date()
    exit_fill_d = pd.Timestamp(row["eng_exit_date"]).date()   # fill session for exit

    out: dict = {
        "fold": int(row["fold"]), "trading_month": row["trading_month"],
        "pair_id": row["pair_id"], "ticker_a": ta, "ticker_b": tb,
        "direction": direction, "beta": beta, "exit_reason": row["exit_reason"],
        "entry_date": row["entry_date"], "eng_exit_date": row["eng_exit_date"],
        "gross_pnl_spread": gross, "cost_backtest_ledger": float(row["cost_backtest"]),
    }

    # ---- Backtest cost model (Gate 1 + components; impact reported, excluded) ----
    c = compute_pair_trade_cost(
        cost_data, ta, tb,
        entry_date=pd.Timestamp(entry_d), exit_date=pd.Timestamp(exit_fill_d),
        notional_per_leg=npl, side_a=direction,
    )
    spread_entry = c["spread_entry_$"]; spread_exit = c["spread_exit_$"]
    impact_entry = c["impact_entry_$"]; impact_exit = c["impact_exit_$"]
    comm_entry = c["commission_entry_$"]; comm_exit = c["commission_exit_$"]
    borrow = c["borrow_$"]
    model_spread = spread_entry + spread_exit
    impact = impact_entry + impact_exit
    commission = comm_entry + comm_exit
    out["cost_engine_total"] = c["total_$"]
    out["gate1_absdiff"] = abs(c["total_$"] - float(row["cost_backtest"]))
    out["impact_usd"] = impact
    out["commission_usd"] = commission
    out["borrow_usd"] = borrow
    out["model_spread_usd"] = model_spread

    # Day-booking components (entry_date vs eng_exit_date), matching the engine's
    # booking bars. Backtest + V-close need cost_engine only -> ALWAYS available.
    out["_entry_bt"] = spread_entry + impact_entry + comm_entry
    out["_exit_bt"] = spread_exit + impact_exit + comm_exit + borrow
    out["_entry_vclose"] = spread_entry + comm_entry
    out["_exit_vclose"] = spread_exit + comm_exit + borrow

    # ---- Decision (V-close) prices ----
    dpa_e = md.prior_close(ta, entry_d)           # entry decision = prior close
    dpb_e = md.prior_close(tb, entry_d)
    dpa_x = md.close_on(ta, exit_fill_d) if is_eom else md.prior_close(ta, exit_fill_d)
    dpb_x = md.close_on(tb, exit_fill_d) if is_eom else md.prior_close(tb, exit_fill_d)

    # ---- V-open fill prices (open + real L1 spread) ----
    opa_e = md.open_on(ta, entry_d); opb_e = md.open_on(tb, entry_d)
    opa_x = md.open_on(ta, exit_fill_d); opb_x = md.open_on(tb, exit_fill_d)
    hsa_e = md.half_spread_bps_on(ta, entry_d); hsb_e = md.half_spread_bps_on(tb, entry_d)
    hsa_x = md.half_spread_bps_on(ta, exit_fill_d); hsb_x = md.half_spread_bps_on(tb, exit_fill_d)

    needed = [dpa_e, dpb_e, dpa_x, dpb_x, opa_e, opb_e, opa_x, opb_x,
              hsa_e, hsb_e, hsa_x, hsb_x]
    missing = [x is None or (isinstance(x, float) and not np.isfinite(x)) for x in needed]
    out["vopen_ok"] = not any(missing)

    # V-close cost is ALWAYS computable (cost_engine only) — no market data needed.
    vclose_cost = model_spread + commission + borrow
    out["vclose_cost_usd"] = vclose_cost
    out["net_vclose"] = gross - vclose_cost

    if not out["vopen_ok"]:
        # Fall back to V-close for the V-open fields (flagged); reported as skipped.
        for k in ("slippage_usd", "slippage_entry_usd", "slippage_exit_usd",
                  "vopen_cost_usd", "net_vopen", "slippage_bps", "vclose_cost_bps",
                  "vopen_cost_bps", "vopen_extra_bps", "overnight_gap_bps",
                  "traded_notional",
                  # new-variant fields (all fall back to V-close when skipped)
                  "vopenmid_cost_bps", "net_vopenmid",
                  "slippage_mid_usd", "slippage_mid_bps", "halfspread_open_bps",
                  "v1530mid_cost_bps", "net_v1530mid", "v1530_cost_bps", "net_v1530",
                  "slippage_1530_usd", "slippage_1530_bps",
                  "slippage_1530mid_usd", "slippage_1530mid_bps",
                  "halfspread_1530_bps", "drift_diff_bps", "spread_saving_bps"):
            out[k] = np.nan
        out["vopen_cost_usd"] = vclose_cost     # fallback for daily reconstruction
        out["net_vopen"] = gross - vclose_cost
        out["vopenmid_cost_usd"] = vclose_cost
        out["net_vopenmid"] = gross - vclose_cost
        out["v1530mid_cost_usd"] = vclose_cost
        out["net_v1530mid"] = gross - vclose_cost
        out["v1530_cost_usd"] = vclose_cost
        out["net_v1530"] = gross - vclose_cost
        out["v1530_ok"] = False
        out["v1530_skip_reason"] = "missing_market_data"
        out["skip_reason"] = "missing_market_data"
        return out
    out["skip_reason"] = ""

    a_e_side, b_e_side = entry_sides(direction)
    a_x_side, b_x_side = exit_sides(direction)

    # qty from DECISION price (= live: notional / decision_price), beta-scaled
    qty_a = N_a / dpa_e
    qty_b = N_b / dpb_e

    # V-open fills
    fa_e = opa_e * (1 + hsa_e / 1e4) if a_e_side == "buy" else opa_e * (1 - hsa_e / 1e4)
    fb_e = opb_e * (1 + hsb_e / 1e4) if b_e_side == "buy" else opb_e * (1 - hsb_e / 1e4)
    fa_x = opa_x * (1 + hsa_x / 1e4) if a_x_side == "buy" else opa_x * (1 - hsa_x / 1e4)
    fb_x = opb_x * (1 + hsb_x / 1e4) if b_x_side == "buy" else opb_x * (1 - hsb_x / 1e4)

    slip_a_e = leg_slippage_usd(a_e_side, qty_a, fa_e, dpa_e)
    slip_b_e = leg_slippage_usd(b_e_side, qty_b, fb_e, dpb_e)
    slip_a_x = leg_slippage_usd(a_x_side, qty_a, fa_x, dpa_x)
    slip_b_x = leg_slippage_usd(b_x_side, qty_b, fb_x, dpb_x)
    slip_entry = slip_a_e + slip_b_e
    slip_exit = slip_a_x + slip_b_x
    slippage = slip_entry + slip_exit

    traded_notional = qty_a * (dpa_e + dpa_x) + qty_b * (dpb_e + dpb_x)
    out["traded_notional"] = traded_notional
    out["slippage_entry_usd"] = slip_entry
    out["slippage_exit_usd"] = slip_exit
    out["slippage_usd"] = slippage

    vopen_cost = slippage + commission + borrow
    out["vopen_cost_usd"] = vopen_cost
    out["net_vopen"] = gross - vopen_cost

    denom = traded_notional if traded_notional > 0 else 1.0
    out["slippage_bps"] = slippage / denom * 1e4
    out["vclose_cost_bps"] = vclose_cost / denom * 1e4
    out["vopen_cost_bps"] = vopen_cost / denom * 1e4
    out["vopen_extra_bps"] = (vopen_cost - vclose_cost) / denom * 1e4

    # overnight-gap magnitude at entry (open vs prior close), notional-weighted bps
    gap_num = qty_a * abs(opa_e - dpa_e) + qty_b * abs(opb_e - dpb_e)
    gap_den = qty_a * dpa_e + qty_b * dpb_e
    out["overnight_gap_bps"] = gap_num / gap_den * 1e4 if gap_den > 0 else np.nan

    # V-open day-booking components (entry_date vs eng_exit_date). backtest +
    # V-close components were stored earlier (cost_engine only, always available).
    out["_entry_vopen"] = slip_entry + comm_entry
    out["_exit_vopen"] = slip_exit + comm_exit + borrow

    # ---- VARIANT A: V-open-mid (optimistic bound of V-open: raw open, NO spread) ----
    slip_a_e_mid = leg_slippage_usd(a_e_side, qty_a, opa_e, dpa_e)
    slip_b_e_mid = leg_slippage_usd(b_e_side, qty_b, opb_e, dpb_e)
    slip_a_x_mid = leg_slippage_usd(a_x_side, qty_a, opa_x, dpa_x)
    slip_b_x_mid = leg_slippage_usd(b_x_side, qty_b, opb_x, dpb_x)
    slip_entry_mid = slip_a_e_mid + slip_b_e_mid
    slip_exit_mid = slip_a_x_mid + slip_b_x_mid
    slippage_mid = slip_entry_mid + slip_exit_mid
    vopenmid_cost = slippage_mid + commission + borrow
    out["slippage_mid_usd"] = slippage_mid
    out["slippage_mid_bps"] = slippage_mid / denom * 1e4
    out["vopenmid_cost_usd"] = vopenmid_cost
    out["net_vopenmid"] = gross - vopenmid_cost
    out["vopenmid_cost_bps"] = vopenmid_cost / denom * 1e4
    # bracket width at the open = the real L1 half-spread crossed (>= 0)
    out["halfspread_open_bps"] = (vopen_cost - vopenmid_cost) / denom * 1e4
    out["_entry_vopenmid"] = slip_entry_mid + comm_entry
    out["_exit_vopenmid"] = slip_exit_mid + comm_exit + borrow

    # ---- VARIANT B: V-1530 (fill at 15:30 of the SAME fill session as V-open) ----
    p1530_a_e = md.price_1530_on(ta, entry_d); p1530_b_e = md.price_1530_on(tb, entry_d)
    p1530_a_x = md.price_1530_on(ta, exit_fill_d); p1530_b_x = md.price_1530_on(tb, exit_fill_d)
    h15_a_e = md.half_spread_1530_bps_on(ta, entry_d); h15_b_e = md.half_spread_1530_bps_on(tb, entry_d)
    h15_a_x = md.half_spread_1530_bps_on(ta, exit_fill_d); h15_b_x = md.half_spread_1530_bps_on(tb, exit_fill_d)
    need15 = [p1530_a_e, p1530_b_e, p1530_a_x, p1530_b_x, h15_a_e, h15_b_e, h15_a_x, h15_b_x]
    miss15 = [x is None or (isinstance(x, float) and not np.isfinite(x)) for x in need15]
    out["v1530_ok"] = not any(miss15)
    if not out["v1530_ok"]:
        for k in ("v1530mid_cost_bps", "net_v1530mid", "v1530_cost_bps", "net_v1530",
                  "slippage_1530_usd", "slippage_1530_bps",
                  "slippage_1530mid_usd", "slippage_1530mid_bps",
                  "halfspread_1530_bps", "drift_diff_bps", "spread_saving_bps"):
            out[k] = np.nan
        # daily reconstruction falls back to V-close for the 15:30 variants
        out["v1530mid_cost_usd"] = vclose_cost; out["net_v1530mid"] = gross - vclose_cost
        out["v1530_cost_usd"] = vclose_cost; out["net_v1530"] = gross - vclose_cost
        out["v1530_skip_reason"] = "missing_1530_bar"
        return out
    out["v1530_skip_reason"] = ""

    # V-1530-mid fills (raw 15:30 price, no spread)
    slip_a_e_15m = leg_slippage_usd(a_e_side, qty_a, p1530_a_e, dpa_e)
    slip_b_e_15m = leg_slippage_usd(b_e_side, qty_b, p1530_b_e, dpb_e)
    slip_a_x_15m = leg_slippage_usd(a_x_side, qty_a, p1530_a_x, dpa_x)
    slip_b_x_15m = leg_slippage_usd(b_x_side, qty_b, p1530_b_x, dpb_x)
    slip_entry_15m = slip_a_e_15m + slip_b_e_15m
    slip_exit_15m = slip_a_x_15m + slip_b_x_15m
    slippage_1530mid = slip_entry_15m + slip_exit_15m

    # V-1530 conservative fills (15:30 price +/- the 15:30 L1 half-spread)
    f15_a_e = p1530_a_e * (1 + h15_a_e / 1e4) if a_e_side == "buy" else p1530_a_e * (1 - h15_a_e / 1e4)
    f15_b_e = p1530_b_e * (1 + h15_b_e / 1e4) if b_e_side == "buy" else p1530_b_e * (1 - h15_b_e / 1e4)
    f15_a_x = p1530_a_x * (1 + h15_a_x / 1e4) if a_x_side == "buy" else p1530_a_x * (1 - h15_a_x / 1e4)
    f15_b_x = p1530_b_x * (1 + h15_b_x / 1e4) if b_x_side == "buy" else p1530_b_x * (1 - h15_b_x / 1e4)
    slip_a_e_15 = leg_slippage_usd(a_e_side, qty_a, f15_a_e, dpa_e)
    slip_b_e_15 = leg_slippage_usd(b_e_side, qty_b, f15_b_e, dpb_e)
    slip_a_x_15 = leg_slippage_usd(a_x_side, qty_a, f15_a_x, dpa_x)
    slip_b_x_15 = leg_slippage_usd(b_x_side, qty_b, f15_b_x, dpb_x)
    slip_entry_15 = slip_a_e_15 + slip_b_e_15
    slip_exit_15 = slip_a_x_15 + slip_b_x_15
    slippage_1530 = slip_entry_15 + slip_exit_15

    v1530mid_cost = slippage_1530mid + commission + borrow
    v1530_cost = slippage_1530 + commission + borrow
    out["slippage_1530mid_usd"] = slippage_1530mid
    out["slippage_1530mid_bps"] = slippage_1530mid / denom * 1e4
    out["slippage_1530_usd"] = slippage_1530
    out["slippage_1530_bps"] = slippage_1530 / denom * 1e4
    out["v1530mid_cost_usd"] = v1530mid_cost
    out["net_v1530mid"] = gross - v1530mid_cost
    out["v1530mid_cost_bps"] = v1530mid_cost / denom * 1e4
    out["v1530_cost_usd"] = v1530_cost
    out["net_v1530"] = gross - v1530_cost
    out["v1530_cost_bps"] = v1530_cost / denom * 1e4
    # bracket width at 15:30 = the real L1 half-spread crossed at 15:30 (>= 0)
    out["halfspread_1530_bps"] = (v1530_cost - v1530mid_cost) / denom * 1e4
    # decomposition: drift (mid vs mid) vs spread saving (open hs - 15:30 hs)
    out["drift_diff_bps"] = (slippage_1530mid - slippage_mid) / denom * 1e4
    out["spread_saving_bps"] = out["halfspread_open_bps"] - out["halfspread_1530_bps"]
    out["_entry_v1530mid"] = slip_entry_15m + comm_entry
    out["_exit_v1530mid"] = slip_exit_15m + comm_exit + borrow
    out["_entry_v1530"] = slip_entry_15 + comm_entry
    out["_exit_v1530"] = slip_exit_15 + comm_exit + borrow

    # Per-leg debug (smoke only; not written to CSV).
    out["_dbg_legs"] = [
        {"name": "A_entry", "side": a_e_side, "qty": qty_a, "decision": dpa_e,
         "open": opa_e, "px1530": p1530_a_e, "hs_open": hsa_e, "hs1530": h15_a_e,
         "fill_vopen": fa_e, "fill_v1530": f15_a_e,
         "slip_vopen": slip_a_e, "slip_mid": slip_a_e_mid,
         "slip_1530": slip_a_e_15, "slip_1530mid": slip_a_e_15m},
        {"name": "B_entry", "side": b_e_side, "qty": qty_b, "decision": dpb_e,
         "open": opb_e, "px1530": p1530_b_e, "hs_open": hsb_e, "hs1530": h15_b_e,
         "fill_vopen": fb_e, "fill_v1530": f15_b_e,
         "slip_vopen": slip_b_e, "slip_mid": slip_b_e_mid,
         "slip_1530": slip_b_e_15, "slip_1530mid": slip_b_e_15m},
        {"name": "A_exit", "side": a_x_side, "qty": qty_a, "decision": dpa_x,
         "open": opa_x, "px1530": p1530_a_x, "hs_open": hsa_x, "hs1530": h15_a_x,
         "fill_vopen": fa_x, "fill_v1530": f15_a_x,
         "slip_vopen": slip_a_x, "slip_mid": slip_a_x_mid,
         "slip_1530": slip_a_x_15, "slip_1530mid": slip_a_x_15m},
        {"name": "B_exit", "side": b_x_side, "qty": qty_b, "decision": dpb_x,
         "open": opb_x, "px1530": p1530_b_x, "hs_open": hsb_x, "hs1530": h15_b_x,
         "fill_vopen": fb_x, "fill_v1530": f15_b_x,
         "slip_vopen": slip_b_x, "slip_mid": slip_b_x_mid,
         "slip_1530": slip_b_x_15, "slip_1530mid": slip_b_x_15m},
    ]
    return out


# ============================================================================
# Sharpe / metrics reconstruction (metrics_daily convention)
# ============================================================================

def _sharpe(daily_returns: np.ndarray) -> float:
    if len(daily_returns) > 1 and np.std(daily_returns, ddof=1) > 1e-12:
        return float(np.mean(daily_returns) / np.std(daily_returns, ddof=1) * np.sqrt(252))
    return 0.0


def _monthly_ann_sharpe(totrets: pd.Series) -> float:
    """run_v4_pipeline 'standard backtest figure': annualize per-fold monthly
    total returns (traded folds only)."""
    r = totrets[totrets != 0.0]
    if len(r) > 1 and r.std(ddof=1) > 1e-12:
        return float(r.mean() / r.std(ddof=1) * np.sqrt(12))
    return 0.0


def sharpe_conventions(per_fold: pd.DataFrame, pooled: dict,
                       traded_folds: set[int]) -> dict[str, dict]:
    """Three conventions x three variants. mean-per-fold (the ship '+1.28'
    headline), monthly-annualized (run_v4_pipeline), and pooled-daily."""
    pf = per_fold[per_fold["fold"].isin(traded_folds)]
    out: dict[str, dict] = {}
    for v in ("backtest", "vclose", "vopen", "vopenmid", "v1530mid", "v1530"):
        out[v] = {
            "mean_perfold": float(pf[f"sharpe_{v}"].mean()),
            "monthly_ann": _monthly_ann_sharpe(pf[f"totret_{v}"]),
            "pooled_daily": float(pooled[f"sharpe_{v}"]),
        }
    return out


def reconstruct_sharpe(sim_rows: list[dict], daily_pnl: pd.DataFrame) -> tuple[pd.DataFrame, dict, dict]:
    """Rebuild per-fold daily net under each variant = daily_gross - variant_cost
    booked on the engine's booking days (entry_date, eng_exit_date), then apply
    the metrics_daily Sharpe formula. Returns (per_fold_df, pooled, internal_check)."""
    # gross[(fold,date)] and captured net (for internal check)
    gross = {(int(r.fold), r.date): float(r.gross_pnl) for r in daily_pnl.itertuples()}
    net_cap = {(int(r.fold), r.date): float(r.net_pnl) for r in daily_pnl.itertuples()}

    # per-day cost bookings on the engine's booking bars (entry_date, eng_exit_date).
    # backtest + V-close components are always present; V-open falls back to V-close
    # for trades skipped on missing market data.
    book_bt: dict[tuple[int, str], float] = {}
    book_vc: dict[tuple[int, str], float] = {}
    book_vo: dict[tuple[int, str], float] = {}
    book_vom: dict[tuple[int, str], float] = {}     # V-open-mid
    book_v15m: dict[tuple[int, str], float] = {}    # V-1530-mid
    book_v15: dict[tuple[int, str], float] = {}     # V-1530
    for s in sim_rows:
        f = s["fold"]
        ed = s["entry_date"]; xd = s["eng_exit_date"]
        entry_vo = s.get("_entry_vopen", s["_entry_vclose"])   # fallback if skipped
        exit_vo = s.get("_exit_vopen", s["_exit_vclose"])
        entry_vom = s.get("_entry_vopenmid", s["_entry_vclose"])
        exit_vom = s.get("_exit_vopenmid", s["_exit_vclose"])
        entry_v15m = s.get("_entry_v1530mid", s["_entry_vclose"])
        exit_v15m = s.get("_exit_v1530mid", s["_exit_vclose"])
        entry_v15 = s.get("_entry_v1530", s["_entry_vclose"])
        exit_v15 = s.get("_exit_v1530", s["_exit_vclose"])
        book_bt[(f, ed)] = book_bt.get((f, ed), 0.0) + s["_entry_bt"]
        book_bt[(f, xd)] = book_bt.get((f, xd), 0.0) + s["_exit_bt"]
        book_vc[(f, ed)] = book_vc.get((f, ed), 0.0) + s["_entry_vclose"]
        book_vc[(f, xd)] = book_vc.get((f, xd), 0.0) + s["_exit_vclose"]
        book_vo[(f, ed)] = book_vo.get((f, ed), 0.0) + entry_vo
        book_vo[(f, xd)] = book_vo.get((f, xd), 0.0) + exit_vo
        book_vom[(f, ed)] = book_vom.get((f, ed), 0.0) + entry_vom
        book_vom[(f, xd)] = book_vom.get((f, xd), 0.0) + exit_vom
        book_v15m[(f, ed)] = book_v15m.get((f, ed), 0.0) + entry_v15m
        book_v15m[(f, xd)] = book_v15m.get((f, xd), 0.0) + exit_v15m
        book_v15[(f, ed)] = book_v15.get((f, ed), 0.0) + entry_v15
        book_v15[(f, xd)] = book_v15.get((f, xd), 0.0) + exit_v15

    folds = sorted({k[0] for k in gross})
    rows = []
    pooled_bt, pooled_vc, pooled_vo = [], [], []
    pooled_vom, pooled_v15m, pooled_v15 = [], [], []
    max_recon_diff = 0.0
    for f in folds:
        days = [k[1] for k in gross if k[0] == f]
        days.sort()
        r_bt, r_vc, r_vo = [], [], []
        r_vom, r_v15m, r_v15 = [], [], []
        for d in days:
            g = gross[(f, d)]
            net_bt = g - book_bt.get((f, d), 0.0)
            net_vc = g - book_vc.get((f, d), 0.0)
            net_vo = g - book_vo.get((f, d), 0.0)
            net_vom = g - book_vom.get((f, d), 0.0)
            net_v15m = g - book_v15m.get((f, d), 0.0)
            net_v15 = g - book_v15.get((f, d), 0.0)
            r_bt.append(net_bt); r_vc.append(net_vc); r_vo.append(net_vo)
            r_vom.append(net_vom); r_v15m.append(net_v15m); r_v15.append(net_v15)
            max_recon_diff = max(max_recon_diff, abs(net_bt - net_cap[(f, d)]))
        ret_bt = np.array(r_bt) / TOTAL_CAPITAL
        ret_vc = np.array(r_vc) / TOTAL_CAPITAL
        ret_vo = np.array(r_vo) / TOTAL_CAPITAL
        ret_vom = np.array(r_vom) / TOTAL_CAPITAL
        ret_v15m = np.array(r_v15m) / TOTAL_CAPITAL
        ret_v15 = np.array(r_v15) / TOTAL_CAPITAL
        pooled_bt.extend(r_bt); pooled_vc.extend(r_vc); pooled_vo.extend(r_vo)
        pooled_vom.extend(r_vom); pooled_v15m.extend(r_v15m); pooled_v15.extend(r_v15)
        rows.append({
            "fold": f,
            "sharpe_backtest": _sharpe(ret_bt),
            "sharpe_vclose": _sharpe(ret_vc),
            "sharpe_vopen": _sharpe(ret_vo),
            "sharpe_vopenmid": _sharpe(ret_vom),
            "sharpe_v1530mid": _sharpe(ret_v15m),
            "sharpe_v1530": _sharpe(ret_v15),
            "totret_backtest": float(np.sum(r_bt) / TOTAL_CAPITAL),
            "totret_vclose": float(np.sum(r_vc) / TOTAL_CAPITAL),
            "totret_vopen": float(np.sum(r_vo) / TOTAL_CAPITAL),
            "totret_vopenmid": float(np.sum(r_vom) / TOTAL_CAPITAL),
            "totret_v1530mid": float(np.sum(r_v15m) / TOTAL_CAPITAL),
            "totret_v1530": float(np.sum(r_v15) / TOTAL_CAPITAL),
        })
    per_fold = pd.DataFrame(rows)
    pooled = {
        "sharpe_backtest": _sharpe(np.array(pooled_bt) / TOTAL_CAPITAL),
        "sharpe_vclose": _sharpe(np.array(pooled_vc) / TOTAL_CAPITAL),
        "sharpe_vopen": _sharpe(np.array(pooled_vo) / TOTAL_CAPITAL),
        "sharpe_vopenmid": _sharpe(np.array(pooled_vom) / TOTAL_CAPITAL),
        "sharpe_v1530mid": _sharpe(np.array(pooled_v15m) / TOTAL_CAPITAL),
        "sharpe_v1530": _sharpe(np.array(pooled_v15) / TOTAL_CAPITAL),
        "totret_backtest": float(np.sum(pooled_bt) / TOTAL_CAPITAL),
        "totret_vclose": float(np.sum(pooled_vc) / TOTAL_CAPITAL),
        "totret_vopen": float(np.sum(pooled_vo) / TOTAL_CAPITAL),
        "totret_vopenmid": float(np.sum(pooled_vom) / TOTAL_CAPITAL),
        "totret_v1530mid": float(np.sum(pooled_v15m) / TOTAL_CAPITAL),
        "totret_v1530": float(np.sum(pooled_v15) / TOTAL_CAPITAL),
    }
    return per_fold, pooled, {"max_recon_vs_captured_diff": max_recon_diff}


# ============================================================================
# Main
# ============================================================================

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true",
                    help="Verbose per-trade breakdown for the first ~2 pairs only.")
    args = ap.parse_args()

    print("=" * 80)
    print("V4 EXEC SIMULATOR — V-close (idealized) vs V-open (live/open+realL1) — OFFLINE")
    print("=" * 80)

    paths = resolve_paths()
    print("Paths:")
    for k, v in paths.items():
        print(f"  {k:14}: {v}  [{'ok' if v.exists() else 'MISSING'}]")

    if not LEDGER_PATH.exists():
        print(f"\nERROR: ledger not found at {LEDGER_PATH}. Run build_v4_ledger.py --folds all first.")
        return 1
    ledger = pd.read_csv(LEDGER_PATH)
    print(f"\nLedger: {len(ledger)} trades, folds {sorted(ledger.fold.unique())}")

    cost_data = cost_engine.load_cost_data(
        daily_cache_path=paths["cost_cache"], summary_path=paths["cost_summary"])
    md = MarketData(paths["prices_1min"], paths["spreads_1min"])

    # ---------- Gate 2 first (fast, no market data) ----------
    g2_ok, g2_msg = gate2_formula_equivalence()
    print("\n" + "-" * 80)
    print(f"GATE 2 (live cost_overlay formula equivalence): {'PASS' if g2_ok else 'FAIL'}")
    print(f"  {g2_msg}")

    if args.smoke:
        sub = ledger.head(5).copy()
        print(f"\nSMOKE: first {len(sub)} trades (per-variant per-leg breakdown)\n")
        for _, row in sub.iterrows():
            r = simulate_trade(row, md, cost_data)
            print(f"[{r['pair_id']}] {r['exit_reason']}  dir={r['direction']:+d}  "
                  f"beta={r['beta']:+.4f}  entry={r['entry_date']} exit_fill={r['eng_exit_date']}")
            if not r["vopen_ok"]:
                print(f"    SKIPPED V-open ({r['skip_reason']}); V-close net=${r['net_vclose']:+.2f}\n")
                continue
            print(f"    gross=${r['gross_pnl_spread']:+.2f}  "
                  f"overnight_gap={r['overnight_gap_bps']:.1f}bps  "
                  f"realL1_slip_bps={r['slippage_bps']:+.2f}")
            # --- UNCHANGED V-close / V-open lines (formula unchanged) ---
            print(f"    V-close: cost=${r['vclose_cost_usd']:.2f} "
                  f"({r['vclose_cost_bps']:.1f}bps)  net=${r['net_vclose']:+.2f}   |   "
                  f"V-open: cost=${r['vopen_cost_usd']:.2f} "
                  f"({r['vopen_cost_bps']:.1f}bps)  net=${r['net_vopen']:+.2f}")
            print(f"    components: model_spread=${r['model_spread_usd']:.2f} "
                  f"comm=${r['commission_usd']:.2f} borrow=${r['borrow_usd']:.2f} "
                  f"impact(excl)=${r['impact_usd']:.2f} | slippage=${r['slippage_usd']:+.2f} "
                  f"(entry ${r['slippage_entry_usd']:+.2f} / exit ${r['slippage_exit_usd']:+.2f})")
            print(f"    gate1 |cost_engine-ledger|={r['gate1_absdiff']:.2e}")
            # --- NEW: per-trade cost bracket (bps) ---
            v15ok = bool(r.get("v1530_ok", False))
            v15txt = (f"V-1530[mid {r['v1530mid_cost_bps']:+.2f} .. consv {r['v1530_cost_bps']:+.2f}]"
                      f" hs15={r['halfspread_1530_bps']:.2f}") if v15ok else \
                     f"V-1530 SKIPPED ({r.get('v1530_skip_reason','')})"
            print(f"    BRACKET bps/trade: V-close={r['vclose_cost_bps']:+.2f} | "
                  f"V-open[mid {r['vopenmid_cost_bps']:+.2f} .. consv {r['vopen_cost_bps']:+.2f}] "
                  f"hs_open={r['halfspread_open_bps']:.2f} | {v15txt}")
            if v15ok:
                print(f"    decomp: drift_diff={r['drift_diff_bps']:+.2f}bps  "
                      f"spread_saving={r['spread_saving_bps']:+.2f}bps  =>  "
                      f"V1530-Vopen(consv)={r['v1530_cost_bps']-r['vopen_cost_bps']:+.2f}bps")
            # --- NEW: per-leg table (eyeball-checkable) ---
            if "_dbg_legs" in r:
                print(f"      {'leg':8}{'side':5}{'qty':>10}{'decision':>11}{'open':>11}"
                      f"{'px1530':>11}{'hs_o':>7}{'hs_15':>7}{'slipMID':>10}{'slipVO':>10}"
                      f"{'slip15m':>10}{'slip15':>10}")
                for L in r["_dbg_legs"]:
                    print(f"      {L['name']:8}{L['side']:5}{L['qty']:>10.2f}"
                          f"{L['decision']:>11.4f}{L['open']:>11.4f}{L['px1530']:>11.4f}"
                          f"{L['hs_open']:>7.2f}{L['hs1530']:>7.2f}{L['slip_mid']:>+10.2f}"
                          f"{L['slip_vopen']:>+10.2f}{L['slip_1530mid']:>+10.2f}{L['slip_1530']:>+10.2f}")
            print()
        return 0

    # ---------- Full run ----------
    t0 = time.time()
    sim_rows = [simulate_trade(row, md, cost_data) for _, row in ledger.iterrows()]
    sim = pd.DataFrame(sim_rows)
    print(f"\nSimulated {len(sim)} trades in {time.time()-t0:.1f}s "
          f"({len(md._cache)} tickers loaded)")

    # ---------- Gate 1 ----------
    g1_max = float(sim["gate1_absdiff"].max())
    g1_ok = g1_max < 1e-6
    print("-" * 80)
    print(f"GATE 1 (compute_pair_trade_cost total_$ == ledger cost_backtest): "
          f"{'PASS' if g1_ok else 'FAIL'}  max|Δ|={g1_max:.2e}")

    # ---------- Coverage ----------
    n_skip = int((~sim["vopen_ok"]).sum())
    print("-" * 80)
    print(f"COVERAGE: {len(sim)-n_skip}/{len(sim)} trades priced for V-open "
          f"({n_skip} skipped = {100*n_skip/len(sim):.1f}%)")
    if n_skip:
        by_reason = sim[~sim["vopen_ok"]]["skip_reason"].value_counts()
        for k, v in by_reason.items():
            print(f"    {k}: {v}")

    # ---------- Write per-trade cost_by_variant ----------
    cost_cols = [
        "fold", "trading_month", "pair_id", "ticker_a", "ticker_b", "direction",
        "beta", "exit_reason", "entry_date", "eng_exit_date", "gross_pnl_spread",
        "vopen_ok", "skip_reason", "overnight_gap_bps",
        "model_spread_usd", "impact_usd", "commission_usd", "borrow_usd",
        "slippage_usd", "slippage_entry_usd", "slippage_exit_usd", "traded_notional",
        "vclose_cost_usd", "vopen_cost_usd", "net_vclose", "net_vopen",
        "slippage_bps", "vclose_cost_bps", "vopen_cost_bps", "vopen_extra_bps",
        "cost_backtest_ledger", "cost_engine_total", "gate1_absdiff",
        # ---- new fill variants (appended; first 33 cols above are unchanged) ----
        "v1530_ok", "v1530_skip_reason",
        "slippage_mid_usd", "slippage_mid_bps",
        "vopenmid_cost_usd", "vopenmid_cost_bps", "net_vopenmid", "halfspread_open_bps",
        "slippage_1530mid_usd", "slippage_1530mid_bps",
        "slippage_1530_usd", "slippage_1530_bps", "halfspread_1530_bps",
        "v1530mid_cost_usd", "v1530mid_cost_bps", "net_v1530mid",
        "v1530_cost_usd", "v1530_cost_bps", "net_v1530",
        "drift_diff_bps", "spread_saving_bps",
    ]
    sim[cost_cols].to_csv(COST_OUT, index=False)
    print(f"\nWrote {COST_OUT}")

    # ---------- Sharpe reconstruction ----------
    daily_pnl = pd.read_csv(DAILY_PNL_PATH)
    per_fold, pooled, chk = reconstruct_sharpe(sim_rows, daily_pnl)
    # append pooled row
    pooled_row = {"fold": "POOLED", **pooled}
    sharpe_df = pd.concat([per_fold, pd.DataFrame([pooled_row])], ignore_index=True)
    sharpe_df.to_csv(SHARPE_OUT, index=False)
    print(f"Wrote {SHARPE_OUT}")
    print(f"  internal check (reconstructed backtest net vs engine-captured net): "
          f"max|Δ|={chk['max_recon_vs_captured_diff']:.2e}/day")

    # ---------- Headline numbers ----------
    priced = sim[sim["vopen_ok"]]
    net_vc = float(sim["net_vclose"].sum())
    net_vo = float(sim["net_vopen"].sum())
    notl = float((2.0 * ledger["notional_per_leg"]).sum())
    avg_bps_vc = net_vc / notl * 1e4
    avg_bps_vo = net_vo / notl * 1e4
    mean_extra = float(priced["vopen_extra_bps"].mean())
    med_extra = float(priced["vopen_extra_bps"].median())

    traded_folds = set(int(f) for f in ledger["fold"].unique())
    sh_conv = sharpe_conventions(per_fold, pooled, traded_folds)

    print("\n" + "=" * 80)
    print("HEADLINE")
    print("=" * 80)
    print(f"  avg_net_bps  V-close={avg_bps_vc:+.2f}   V-open={avg_bps_vo:+.2f}   "
          f"delta={avg_bps_vo-avg_bps_vc:+.2f} bps")
    print(f"  V-open extra cost/trade: mean={mean_extra:+.2f} bps  median={med_extra:+.2f} bps")
    print("  Sharpe (backtest / V-close / V-open  |  V-close->V-open delta):")
    for label, key in (("mean per-fold [ship '+1.28' convention]", "mean_perfold"),
                       ("monthly-annualized [run_v4_pipeline std]", "monthly_ann"),
                       ("pooled-daily [metrics_daily]", "pooled_daily")):
        b, vc, vo = sh_conv["backtest"][key], sh_conv["vclose"][key], sh_conv["vopen"][key]
        print(f"    {label:44}: {b:+.3f} / {vc:+.3f} / {vo:+.3f}  (delta {vo-vc:+.3f})")

    # ---------- New-variant aggregates + bracket + verdict ----------
    n15_ok = int(sim["v1530_ok"].sum())
    cov15 = 100.0 * n15_ok / len(sim)
    both = sim[sim["vopen_ok"] & sim["v1530_ok"]]

    def _avg_net_bps(col: str) -> float:
        return float(sim[col].sum()) / notl * 1e4

    bracket = build_bracket(sim, priced, sh_conv, notl)

    print("\n" + "=" * 80)
    print("BRACKET — execution cost (bps/trade) and Sharpe (3 conventions)")
    print("=" * 80)
    print(f"  {'variant':16}{'cost_bps mean':>14}{'median':>9}{'avg_net_bps':>13}"
          f"{'Sh(mpf)':>9}{'Sh(mon)':>9}{'Sh(pool)':>10}")
    for label, key, costcol in bracket["order"]:
        b = bracket[key]
        print(f"  {label:16}{b['cost_mean']:>14.2f}{b['cost_med']:>9.2f}"
              f"{b['avg_net']:>13.2f}{b['sh_mpf']:>9.3f}{b['sh_mon']:>9.3f}{b['sh_pool']:>10.3f}")

    # V-1530 vs V-open decomposition (apples-to-apples set: both priced)
    mean_drift = float(both["drift_diff_bps"].mean())
    mean_saving = float(both["spread_saving_bps"].mean())
    net_15_vs_o = float((both["v1530_cost_bps"] - both["vopen_cost_bps"]).mean())
    verdict = ("V-1530 CHEAPER than V-open" if net_15_vs_o < 0
               else "V-1530 COSTLIER than V-open")
    print("\nV-1530 vs V-open (conservative/taker, on the {} trades priced in BOTH):"
          .format(len(both)))
    print(f"  spread saving (open hs - 15:30 hs) = {mean_saving:+.2f} bps/trade")
    print(f"  intraday-drift diff (v1530 mid - vopen mid) = {mean_drift:+.2f} bps/trade")
    print(f"  net cost diff (V-1530 - V-open) = drift - saving = "
          f"{mean_drift:+.2f} - {mean_saving:+.2f} = {net_15_vs_o:+.2f} bps  =>  {verdict}")
    print(f"  15:30 coverage: {n15_ok}/{len(sim)} = {cov15:.1f}%")

    # ---------- VALIDATION: per-trade mid <= conservative ----------
    eps = 1e-9
    viol_vo = sim[(sim["vopen_ok"]) &
                  (sim["vopenmid_cost_usd"] > sim["vopen_cost_usd"] + eps)]
    viol_15 = sim[(sim["v1530_ok"]) &
                  (sim["v1530mid_cost_usd"] > sim["v1530_cost_usd"] + eps)]
    print("\nVALIDATION (mid <= conservative, per trade):")
    print(f"  V-open-mid <= V-open : {len(viol_vo)} violation(s)"
          f"{'' if len(viol_vo)==0 else ' -> ' + ', '.join(viol_vo['pair_id'])}")
    print(f"  V-1530-mid <= V-1530 : {len(viol_15)} violation(s)"
          f"{'' if len(viol_15)==0 else ' -> ' + ', '.join(viol_15['pair_id'])}")
    valid_ok = (len(viol_vo) == 0 and len(viol_15) == 0)

    # ---------- Overnight-gap stratification ----------
    strat = _stratify_gap(priced)
    print("\nV-open extra cost by overnight-gap size:")
    print(strat.to_string(index=False))

    _write_report(sim, sh_conv, chk, g1_ok, g1_max, g2_ok, g2_msg,
                  n_skip, strat, avg_bps_vc, avg_bps_vo, mean_extra, med_extra,
                  bracket, mean_drift, mean_saving, net_15_vs_o, verdict,
                  n15_ok, cov15, len(both), valid_ok, len(viol_vo), len(viol_15))
    print(f"\nWrote {REPORT_OUT}")
    return 0


def build_bracket(sim: pd.DataFrame, priced: pd.DataFrame,
                  sh_conv: dict, notl: float) -> dict:
    """Assemble the 5-point bracket: cost bps mean/median (over each variant's
    coverage set), portfolio avg_net_bps, and the 3 Sharpe conventions."""
    order = [
        ("V-close (point)", "vclose",   "vclose_cost_bps"),
        ("V-open-mid",      "vopenmid", "vopenmid_cost_bps"),
        ("V-open (consv)",  "vopen",    "vopen_cost_bps"),
        ("V-1530-mid",      "v1530mid", "v1530mid_cost_bps"),
        ("V-1530 (consv)",  "v1530",    "v1530_cost_bps"),
    ]
    v15 = sim[sim["v1530_ok"]]
    out: dict = {"order": order}
    for label, key, costcol in order:
        subset = v15 if key.startswith("v1530") else priced
        out[key] = {
            "cost_mean": float(subset[costcol].mean()),
            "cost_med": float(subset[costcol].median()),
            "avg_net": float(sim[f"net_{key}"].sum()) / notl * 1e4,
            "sh_mpf": sh_conv[key]["mean_perfold"],
            "sh_mon": sh_conv[key]["monthly_ann"],
            "sh_pool": sh_conv[key]["pooled_daily"],
        }
    return out


def _stratify_gap(priced: pd.DataFrame) -> pd.DataFrame:
    bins = [0, 10, 25, 50, 100, np.inf]
    labels = ["0-10", "10-25", "25-50", "50-100", ">100"]
    g = priced.copy()
    g["gap_bucket"] = pd.cut(g["overnight_gap_bps"], bins=bins, labels=labels, right=False)
    agg = g.groupby("gap_bucket", observed=False).agg(
        n=("vopen_extra_bps", "count"),
        mean_gap_bps=("overnight_gap_bps", "mean"),
        mean_vopen_extra_bps=("vopen_extra_bps", "mean"),
        median_vopen_extra_bps=("vopen_extra_bps", "median"),
        mean_slippage_bps=("slippage_bps", "mean"),
    ).reset_index()
    return agg


def _write_report(sim, sh_conv, chk, g1_ok, g1_max, g2_ok, g2_msg,
                  n_skip, strat, avg_bps_vc, avg_bps_vo, mean_extra, med_extra,
                  bracket=None, mean_drift=None, mean_saving=None, net_15_vs_o=None,
                  verdict=None, n15_ok=None, cov15=None, n_both=None,
                  valid_ok=None, n_viol_vo=None, n_viol_15=None) -> None:
    lines = []
    lines.append("V4 EXEC SIMULATOR REPORT — V-close vs V-open vs V-1530 (OFFLINE)")
    lines.append("=" * 70)
    lines.append("")
    lines.append("(1) LEG SIZING (D3): BETA-SCALED (live/main.py:407-408).")
    lines.append("      qty_a = notional / dp_a ; qty_b = notional*|beta| / dp_b")
    lines.append("      leg-A $notional = N ; leg-B $notional = N*|beta|.")
    lines.append("      (live floors to int shares >=1; sim uses continuous shares —")
    lines.append("       slippage_bps is scale-invariant so this does not move bps.)")
    lines.append("")
    lines.append("(2) TIMING CONVENTION (faithful to engine 1-bar lag + live order path):")
    lines.append("      ENTRY: decision = close of session BEFORE entry_date (=close[idx-1],")
    lines.append("             = engine fill = live decision_price); V-open fill = open of")
    lines.append("             entry_date + real L1 half-spread.")
    lines.append("      EXIT zero_cross/hard_sl: decision = close of session BEFORE exit_date;")
    lines.append("             V-open fill = open of exit_date + real L1.")
    lines.append("      EXIT open_at_eom: decision = close of eng_exit_date (engine holds")
    lines.append("             through last bar); V-open fill = open of eng_exit_date + real L1.")
    lines.append("")
    lines.append(f"(3) HEADLINE  V-close -> V-open:")
    lines.append(f"      avg_net_bps: {avg_bps_vc:+.2f} -> {avg_bps_vo:+.2f}  (delta {avg_bps_vo-avg_bps_vc:+.2f} bps)")
    lines.append(f"      V-open extra cost/trade: mean {mean_extra:+.2f} bps, median {med_extra:+.2f} bps")
    lines.append("      Sharpe (backtest / V-close / V-open  |  V-close->V-open delta):")
    for label, key in (("mean per-fold [ship '+1.28' convention]", "mean_perfold"),
                       ("monthly-annualized [run_v4_pipeline std]", "monthly_ann"),
                       ("pooled-daily [metrics_daily]", "pooled_daily")):
        b = sh_conv["backtest"][key]; vc = sh_conv["vclose"][key]; vo = sh_conv["vopen"][key]
        lines.append(f"        {label:42}: {b:+.3f} / {vc:+.3f} / {vo:+.3f}  (delta {vo-vc:+.3f})")
    lines.append("")
    lines.append("(4) VALIDATION GATES:")
    lines.append(f"      Gate 1 (compute_pair_trade_cost total_$ == ledger cost_backtest): "
                 f"{'PASS' if g1_ok else 'FAIL'}  max|Δ|={g1_max:.2e}")
    lines.append(f"      Gate 2 (formula == live cost_overlay.compute_realized_cost_usd): "
                 f"{'PASS' if g2_ok else 'FAIL'}")
    lines.append(f"          {g2_msg}")
    lines.append(f"      Internal (reconstructed backtest daily net vs engine-captured): "
                 f"max|Δ|={chk['max_recon_vs_captured_diff']:.2e}/day")
    lines.append("      NOTE: live's real closed trades are 2026-05..07 (outside on-disk data")
    lines.append("      <=2026-03), so a real-data realized-cost comparison comes later as")
    lines.append("      live accumulates fills; Gate 2 proves the FORMULA matches now.")
    lines.append("")
    lines.append(f"(5) COVERAGE: {len(sim)-n_skip}/{len(sim)} trades priced for V-open "
                 f"({100*n_skip/len(sim):.1f}% skipped for missing next-session/open/L1 data).")
    lines.append("")
    lines.append("(6) V-OPEN EXTRA COST BY OVERNIGHT-GAP SIZE:")
    for ln in strat.to_string(index=False).splitlines():
        lines.append("      " + ln)
    lines.append("")

    if bracket is not None:
        lines.append("(7) BRACKET TABLE — execution cost (bps/trade) + Sharpe (3 conventions)")
        lines.append("    cost_bps = mean/median of that variant's own per-trade execution")
        lines.append("    cost over its coverage set; avg_net_bps = portfolio sum(net)/sum(notional).")
        lines.append("    Sharpe: mpf=mean-per-fold (ship '+1.28'), mon=monthly-annualized")
        lines.append("    (run_v4_pipeline), pool=pooled-daily (metrics_daily).")
        lines.append("")
        hdr = (f"      {'variant':16}{'cost_mean':>10}{'cost_med':>10}{'avg_net':>10}"
               f"{'Sh(mpf)':>9}{'Sh(mon)':>9}{'Sh(pool)':>10}")
        lines.append(hdr)
        lines.append("      " + "-" * (len(hdr) - 6))
        for label, key, _cc in bracket["order"]:
            b = bracket[key]
            lines.append(f"      {label:16}{b['cost_mean']:>10.2f}{b['cost_med']:>10.2f}"
                         f"{b['avg_net']:>10.2f}{b['sh_mpf']:>9.3f}{b['sh_mon']:>9.3f}"
                         f"{b['sh_pool']:>10.3f}")
        lines.append("")
        lines.append("      Reading: V-close is a POINT (idealized). V-open and V-1530 are")
        lines.append("      BRACKETS [mid (optimistic, no spread) .. consv (taker, +/- real L1)].")
        lines.append("      Bracket width = the real L1 half-spread crossed (open vs 15:30).")
        lines.append("      CAVEAT: each row's cost_mean/median, avg_net_bps and Sharpe are over")
        lines.append("      that variant's OWN coverage (V-open 424, V-1530 392 trades); the")
        lines.append("      V-1530 avg_net/Sharpe blend a V-close fallback on the 8.4% of trades")
        lines.append("      with no 15:30 bar, which FLATTERS them. For the clean apples-to-apples")
        lines.append("      V-1530-vs-V-open read use the both-set decomposition in section (8).")
        lines.append("")
        lines.append("(8) V-1530 vs V-OPEN VERDICT + DECOMPOSITION")
        lines.append(f"      (conservative/taker, on the {n_both} trades priced in BOTH variants)")
        lines.append(f"      spread saving (open hs - 15:30 hs)      = {mean_saving:+.2f} bps/trade")
        lines.append(f"      intraday-drift diff (v1530mid - vopenmid) = {mean_drift:+.2f} bps/trade")
        lines.append(f"      net cost diff (V-1530 - V-open) = drift - saving")
        lines.append(f"                    = {mean_drift:+.2f} - ({mean_saving:+.2f}) = {net_15_vs_o:+.2f} bps")
        lines.append(f"      VERDICT: {verdict}.")
        if net_15_vs_o is not None and net_15_vs_o >= 0:
            lines.append("      => The cheaper 15:30 spread does NOT overcome the extra open->15:30")
            lines.append("         intraday drift; executing at the open is cheaper on average.")
        else:
            lines.append("      => The cheaper 15:30 spread MORE than overcomes the extra drift;")
            lines.append("         delaying to 15:30 is cheaper on average.")
        lines.append(f"      15:30 COVERAGE: {n15_ok}/{len(sim)} = {cov15:.1f}% "
                     f"(sessions with a 15:30-15:45 bar for all four legs).")
        lines.append("")
        lines.append("      NOTE (deferred): passive-fill realism is NOT modelled here. No")
        lines.append("      OHLC/Gate-0 machine estimates a 15:30 limit-order fill probability;")
        lines.append("      that is deferred to probe calibration. The [mid..consv] bracket")
        lines.append("      already brackets passive(~mid) <-> taker(~spread).")
        lines.append("")
        lines.append("(9) VALIDATION — per-trade mid <= conservative (spread crossing >= 0):")
        lines.append(f"      V-open-mid <= V-open : {n_viol_vo} violation(s)")
        lines.append(f"      V-1530-mid <= V-1530 : {n_viol_15} violation(s)")
        lines.append(f"      => {'PASS' if valid_ok else 'FAIL'}")
        lines.append("      V-close/V-open/Gate1/Gate2 computations are UNCHANGED by the new")
        lines.append("      variants (additive only); sections (3)-(5) above re-print them.")
        lines.append("")

    lines.append("Exit-reason mix:")
    for k, v in sim["exit_reason"].value_counts().items():
        lines.append(f"      {k}: {v}")
    REPORT_OUT.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
