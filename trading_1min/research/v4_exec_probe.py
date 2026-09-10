"""v4_exec_probe.py — live fill-measurement probe on the PAPER account #2.

Traces the intraday slippage / fill-timing curve, stratified by liquidity tier,
to calibrate the exec simulator's fill model (spec: v4_exec_simulator_spec.md, Nhanh 2).

Each cycle, for every basket ticker:
  - MARKET round-trip (buy -> flatten sell): taker slippage vs submit mid + latency.
  - PASSIVE buy limit at the bid: how long until it fills (or unfilled within W);
    if filled, flatten with a market sell. This is the "wait to fill" measurement.
All positions are flattened every cycle and at exit. Appends rows to probe_fills.csv.

Data-quality guard: the free IEX quote feed intermittently prints garbage (e.g. a
$19 spread on a $331 stock). Any quote whose relative spread exceeds
MAX_REL_SPREAD_BPS is treated as unreliable — we skip trading it that cycle and log
a `bad_quote` row instead of polluting the curve with a garbage fill.

Hard safety: PAPER account #2 only; api_key must differ from production Week 6/.env.
Never prints secrets. Every broker call is wrapped so one failure never stops the loop.

Run:
  python trading_1min/research/v4_exec_probe.py --once            # one cycle (smoke)
  python trading_1min/research/v4_exec_probe.py --until 16:00     # loop until 16:00 ET
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]
PROBE_ENV = ROOT / "Week 6" / ".env.probe"
PROD_ENV = ROOT / "Week 6" / ".env"
CLIENT_PY = ROOT / "Week 6" / "live" / "broker" / "alpaca_client.py"
OUT = ROOT / "trading_1min" / "results" / "v4_exec_sim"
FILLS_CSV = OUT / "probe_fills.csv"
ET = ZoneInfo("America/New_York")

# Liquidity-stratified basket (median L1 half-spread bps from Week 5 spread_summary).
# CTRA dropped: inactive/delisted on Alpaca. NVR dropped: ~$8k/share.
BASKET = [
    ("AAPL", "tight"), ("MSFT", "tight"), ("WST", "tight"),
    ("NVDA", "medium"), ("AMZN", "medium"), ("ZTS", "medium"), ("WYNN", "medium"),
    ("HPE", "wide"), ("WBD", "wide"),
]

NOTIONAL = 1000.0          # target $ per order (whole shares)
PASSIVE_WAIT_S = 120.0     # how long a passive limit may sit before we cancel
POLL_S = 1.0
FILL_TIMEOUT_S = 20.0      # market-order fill poll cap
MAX_REL_SPREAD_BPS = 300.0 # reject garbage quotes above this relative spread
MAX_ORDERS = 4000          # unattended safety cap

FIELDS = [
    "cycle", "ticker", "tier", "side", "style", "submit_ts", "fill_ts",
    "ref_px", "fill_px", "fill_qty", "rel_spread_bps", "slippage_bps",
    "time_to_fill_s", "filled", "slot_hhmm_et", "note",
]

_orders_placed = 0


def _load_client_module():
    spec = importlib.util.spec_from_file_location("alpaca_client", CLIENT_PY)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _cfg(mod, vals):
    return mod.AlpacaConfig(
        api_key=vals["ALPACA_API_KEY"], secret_key=vals["ALPACA_SECRET_KEY"],
        base_url=vals.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets"),
        data_url=vals.get("ALPACA_DATA_URL", "https://data.alpaca.markets"),
        paper=str(vals.get("ALPACA_PAPER", "true")).lower() == "true",
    )


def _safety(probe_vals, cfg):
    ak = probe_vals.get("ALPACA_API_KEY", "")
    if (not ak) or ("PASTE_" in ak):
        return ".env.probe still has placeholder keys."
    if "paper-api" not in cfg.base_url:
        return f"base_url not paper ({cfg.base_url})."
    if PROD_ENV.exists():
        prod = dotenv_values(PROD_ENV)
        if prod.get("ALPACA_API_KEY") and prod["ALPACA_API_KEY"] == ak:
            return "probe api_key == production api_key (need a separate account)."
    return None


def _quote(data_client, ticker):
    """(bid, ask, mid) from latest quote; (None,None,last_trade) fallback."""
    try:
        from alpaca.data.requests import StockLatestQuoteRequest
        q = data_client.get_stock_latest_quote(
            StockLatestQuoteRequest(symbol_or_symbols=ticker))[ticker]
        bid, ask = float(q.bid_price or 0), float(q.ask_price or 0)
        if bid > 0 and ask > 0:
            return bid, ask, (bid + ask) / 2.0
    except Exception:  # noqa: BLE001
        pass
    try:
        from alpaca.data.requests import StockLatestTradeRequest
        t = data_client.get_stock_latest_trade(
            StockLatestTradeRequest(symbol_or_symbols=ticker))[ticker]
        return None, None, float(t.price)
    except Exception:  # noqa: BLE001
        return None, None, None


def _rel_spread_bps(bid, ask):
    if not bid or not ask or bid <= 0 or ask <= 0:
        return None
    return (ask - bid) / ((ask + bid) / 2.0) * 1e4


def _qty_for(price):
    if not price or price <= 0:
        return 1
    return max(1, round(NOTIONAL / price))


def _ttf(submitted_at, filled_at):
    """Time-to-fill from Alpaca's own timestamps (no local clock skew)."""
    if submitted_at is None or filled_at is None:
        return None
    try:
        return (filled_at - submitted_at).total_seconds()
    except Exception:  # noqa: BLE001
        return None


def _submit_market(mod, tc, ticker, qty, side):
    global _orders_placed
    from alpaca.trading.requests import MarketOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce
    _orders_placed += 1
    req = MarketOrderRequest(symbol=ticker, qty=qty,
                             side=OrderSide.BUY if side == "buy" else OrderSide.SELL,
                             time_in_force=TimeInForce.DAY)
    return str(tc.submit_order(req).id)


def _submit_limit_buy(mod, tc, ticker, qty, limit_px):
    global _orders_placed
    from alpaca.trading.requests import LimitOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce
    _orders_placed += 1
    req = LimitOrderRequest(symbol=ticker, qty=qty, side=OrderSide.BUY,
                            time_in_force=TimeInForce.DAY, limit_price=round(limit_px, 2))
    return str(tc.submit_order(req).id)


def _await_fill(tc, oid, timeout_s):
    """Poll until filled or timeout. Returns (filled_px, filled_qty, filled_at, submitted_at)."""
    deadline = time.time() + timeout_s
    o = None
    while time.time() < deadline:
        o = tc.get_order_by_id(oid)
        status = str(getattr(o, "status", "")).lower()
        if "filled" in status and "partially" not in status:
            return (float(o.filled_avg_price) if o.filled_avg_price else None,
                    float(o.filled_qty) if o.filled_qty else None,
                    o.filled_at, getattr(o, "submitted_at", None))
        time.sleep(POLL_S)
    return None, None, None, getattr(o, "submitted_at", None) if o else None


def _row(cycle, ticker, tier, side, style, submit_ts, ref_px, fill_px, fill_qty,
         filled_at, ttf, rel_spread, note):
    slip = None
    if fill_px and ref_px:
        sgn = 1.0 if side == "buy" else -1.0
        slip = sgn * (fill_px - ref_px) / ref_px * 1e4
    return {
        "cycle": cycle, "ticker": ticker, "tier": tier, "side": side, "style": style,
        "submit_ts": submit_ts.isoformat(),
        "fill_ts": filled_at.isoformat() if (fill_px and filled_at is not None) else "",
        "ref_px": f"{ref_px:.4f}" if ref_px else "",
        "fill_px": f"{fill_px:.4f}" if fill_px else "",
        "fill_qty": f"{fill_qty:g}" if fill_qty else "",
        "rel_spread_bps": f"{rel_spread:.1f}" if rel_spread is not None else "",
        "slippage_bps": f"{slip:+.2f}" if slip is not None else "",
        "time_to_fill_s": f"{ttf:.3f}" if ttf is not None else "",
        "filled": bool(fill_px), "slot_hhmm_et": submit_ts.astimezone(ET).strftime("%H:%M"),
        "note": note,
    }


def _append(rows):
    OUT.mkdir(parents=True, exist_ok=True)
    exists = FILLS_CSV.exists()
    with FILLS_CSV.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if not exists:
            w.writeheader()
        for r in rows:
            w.writerow(r)


def _flatten_all(mod, tc):
    """Close any open positions with market orders; cancel open orders first."""
    try:
        tc.cancel_orders()
    except Exception:  # noqa: BLE001
        pass
    try:
        for p in tc.get_all_positions():
            side = "sell" if float(p.qty) > 0 else "buy"
            try:
                _submit_market(mod, tc, p.symbol, abs(float(p.qty)), side)
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001
        pass


def run_cycle(mod, tc, dc, cycle):
    rows = []
    # ---- MARKET round-trips (fast, sequential) ----
    for ticker, tier in BASKET:
        try:
            bid, ask, mid = _quote(dc, ticker)
            rs = _rel_spread_bps(bid, ask)
            ts = datetime.now(timezone.utc)
            if rs is not None and rs > MAX_REL_SPREAD_BPS:
                rows.append(_row(cycle, ticker, tier, "buy", "market", ts, mid,
                                 None, None, None, None, rs, f"bad_quote_{rs:.0f}bp"))
                continue
            qty = _qty_for(mid)
            oid = _submit_market(mod, tc, ticker, qty, "buy")
            fp, fq, fat, sub = _await_fill(tc, oid, FILL_TIMEOUT_S)
            rows.append(_row(cycle, ticker, tier, "buy", "market", ts, mid, fp, fq,
                             fat, _ttf(sub, fat), rs, f"bid{bid}/ask{ask}"))
            # flatten (place regardless to stay flat)
            ts2 = datetime.now(timezone.utc)
            b2, a2, mid2 = _quote(dc, ticker)
            oid2 = _submit_market(mod, tc, ticker, qty, "sell")
            fp2, fq2, fat2, sub2 = _await_fill(tc, oid2, FILL_TIMEOUT_S)
            rows.append(_row(cycle, ticker, tier, "sell", "market", ts2, mid2, fp2, fq2,
                             fat2, _ttf(sub2, fat2), _rel_spread_bps(b2, a2), "flatten"))
        except Exception as e:  # noqa: BLE001
            print(f"    [!] market {ticker}: {type(e).__name__}: {e}", flush=True)

    # ---- PASSIVE buy limits (placed together, polled together) ----
    pending = []
    for ticker, tier in BASKET:
        try:
            bid, ask, mid = _quote(dc, ticker)
            rs = _rel_spread_bps(bid, ask)
            if not bid:
                continue
            if rs is not None and rs > MAX_REL_SPREAD_BPS:
                rows.append(_row(cycle, ticker, tier, "buy", "passive",
                                 datetime.now(timezone.utc), mid, None, None, None,
                                 None, rs, f"bad_quote_{rs:.0f}bp"))
                continue
            qty = _qty_for(mid)
            ts = datetime.now(timezone.utc)
            oid = _submit_limit_buy(mod, tc, ticker, qty, bid)
            pending.append(dict(ticker=ticker, tier=tier, oid=oid, ts=ts,
                                ref=mid, qty=qty, rs=rs))
        except Exception as e:  # noqa: BLE001
            print(f"    [!] passive submit {ticker}: {type(e).__name__}: {e}", flush=True)

    deadline = time.time() + PASSIVE_WAIT_S
    done = {}
    while pending and time.time() < deadline:
        for p in list(pending):
            try:
                o = tc.get_order_by_id(p["oid"])
                status = str(getattr(o, "status", "")).lower()
                if "filled" in status and "partially" not in status:
                    done[p["ticker"]] = (float(o.filled_avg_price), float(o.filled_qty),
                                         o.filled_at, getattr(o, "submitted_at", None), p)
                    pending.remove(p)
                elif status in ("canceled", "rejected", "expired"):
                    pending.remove(p)
                    rows.append(_row(cycle, p["ticker"], p["tier"], "buy", "passive",
                                     p["ts"], p["ref"], None, None, None, None,
                                     p["rs"], f"dead:{status}"))
            except Exception:  # noqa: BLE001
                pass
        time.sleep(POLL_S)

    # unfilled -> cancel + record as missed
    for p in pending:
        try:
            tc.cancel_order_by_id(p["oid"])
        except Exception:  # noqa: BLE001
            pass
        rows.append(_row(cycle, p["ticker"], p["tier"], "buy", "passive", p["ts"],
                         p["ref"], None, None, None, None, p["rs"],
                         f"unfilled_{int(PASSIVE_WAIT_S)}s"))
    # filled -> record (Alpaca-clock ttf) + flatten
    for ticker, (fp, fq, fat, sub, p) in done.items():
        rows.append(_row(cycle, ticker, p["tier"], "buy", "passive", p["ts"],
                         p["ref"], fp, fq, fat, _ttf(sub, fat), p["rs"], "passive_fill"))
        try:
            oid = _submit_market(mod, tc, ticker, p["qty"], "sell")
            _await_fill(tc, oid, FILL_TIMEOUT_S)
        except Exception:  # noqa: BLE001
            pass

    _append(rows)
    _flatten_all(mod, tc)
    n_mkt = sum(1 for r in rows if r["style"] == "market" and r["side"] == "buy" and r["filled"])
    n_pass_fill = sum(1 for r in rows if r["style"] == "passive" and r["filled"])
    n_pass = sum(1 for r in rows if r["style"] == "passive")
    n_bad = sum(1 for r in rows if r["note"].startswith("bad_quote"))
    return rows, n_mkt, n_pass_fill, n_pass, n_bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="run a single cycle then exit")
    ap.add_argument("--until", default="16:00", help="stop time HH:MM ET (loop mode)")
    ap.add_argument("--interval-min", type=float, default=15.0)
    args = ap.parse_args()

    if not PROBE_ENV.exists():
        print(f"[x] {PROBE_ENV} not found."); return 1
    probe_vals = dotenv_values(PROBE_ENV)
    mod = _load_client_module()
    cfg = _cfg(mod, probe_vals)
    err = _safety(probe_vals, cfg)
    if err:
        print(f"[x] SAFETY: {err} Aborting."); return 2

    tc = mod.build_trading_client(cfg)
    dc = mod.build_data_client(cfg)
    acct = mod.check_auth(cfg)
    print(f"[ok] probe account {acct['id']} | equity ${acct['equity']:,.0f} | PAPER", flush=True)

    hh, mm = (int(x) for x in args.until.split(":"))
    cycle = 0
    try:
        while True:
            now_et = datetime.now(ET)
            clock = tc.get_clock()
            if not bool(getattr(clock, "is_open", False)):
                print(f"[stop] market closed at {now_et:%H:%M ET}."); break
            cycle += 1
            print(f"\n=== cycle {cycle} @ {now_et:%H:%M:%S ET} "
                  f"(orders so far: {_orders_placed}) ===", flush=True)
            _, n_mkt, n_pf, n_p, n_bad = run_cycle(mod, tc, dc, cycle)
            print(f"    market filled: {n_mkt} | passive filled: {n_pf}/{n_p} "
                  f"| bad_quote skips: {n_bad}", flush=True)
            if args.once:
                break
            if _orders_placed > MAX_ORDERS:
                print(f"[stop] order cap {MAX_ORDERS} reached."); break
            stop_et = now_et.replace(hour=hh, minute=mm, second=0, microsecond=0)
            if datetime.now(ET) >= stop_et:
                print(f"[stop] reached {args.until} ET."); break
            time.sleep(args.interval_min * 60)
    finally:
        _flatten_all(mod, tc)
        try:
            pos = tc.get_all_positions()
            print(f"\n[{'ok' if not pos else '!!'}] final positions: "
                  f"{'FLAT' if not pos else [p.symbol for p in pos]}", flush=True)
        except Exception:  # noqa: BLE001
            pass
    print(f"[done] {cycle} cycle(s), {_orders_placed} orders. -> {FILLS_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
