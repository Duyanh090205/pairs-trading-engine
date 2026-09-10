"""probe_conn_check.py — verify the SEPARATE paper account #2 for the exec probe.

Reads Week 6/.env.probe (account #2) and confirms, WITHOUT ever printing secrets:
  - the file has real keys (not the placeholder template),
  - base_url is the PAPER endpoint (never live),
  - credentials authenticate (round-trip get_account),
  - it is NOT the production V4 account — different api_key AND different account id
    than Week 6/.env — so the probe can never pollute production reconcile.

Prints an account summary (account id, status, equity, cash, buying power).

Run:  python trading_1min/research/probe_conn_check.py
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]
PROBE_ENV = ROOT / "Week 6" / ".env.probe"
PROD_ENV = ROOT / "Week 6" / ".env"
_CLIENT = ROOT / "Week 6" / "live" / "broker" / "alpaca_client.py"

_PLACEHOLDERS = ("PASTE_", "PKxxxx", "xxxxxxxx")


def _load_client_module():
    """Load production's alpaca_client.py by path (no package/sys.path fuss)."""
    spec = importlib.util.spec_from_file_location("alpaca_client", _CLIENT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # needed so @dataclass can resolve __module__
    spec.loader.exec_module(mod)
    return mod


def _cfg(mod, vals: dict):
    return mod.AlpacaConfig(
        api_key=vals["ALPACA_API_KEY"],
        secret_key=vals["ALPACA_SECRET_KEY"],
        base_url=vals.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets"),
        data_url=vals.get("ALPACA_DATA_URL", "https://data.alpaca.markets"),
        paper=str(vals.get("ALPACA_PAPER", "true")).lower() == "true",
    )


def _is_placeholder(s: str | None) -> bool:
    return not s or any(p in s for p in _PLACEHOLDERS)


def main() -> int:
    if not PROBE_ENV.exists():
        print(f"[x] {PROBE_ENV} not found. Fill the template with account #2 keys first.")
        return 1

    probe_vals = dotenv_values(PROBE_ENV)
    if _is_placeholder(probe_vals.get("ALPACA_API_KEY")) or _is_placeholder(probe_vals.get("ALPACA_SECRET_KEY")):
        print("[x] .env.probe still holds the placeholder keys.")
        print("    Open Week 6/.env.probe and paste your PAPER account #2 Key ID + Secret,")
        print("    then re-run this check.")
        return 1

    mod = _load_client_module()
    probe_cfg = _cfg(mod, probe_vals)

    if "paper-api" not in probe_cfg.base_url:
        print(f"[x] base_url is NOT the paper endpoint ({probe_cfg.base_url}). Refusing.")
        return 1

    # ---- hard safety: must NOT be the production account ----
    if PROD_ENV.exists():
        prod_vals = dotenv_values(PROD_ENV)
        if prod_vals.get("ALPACA_API_KEY") and prod_vals["ALPACA_API_KEY"] == probe_vals["ALPACA_API_KEY"]:
            print("[x] FATAL: .env.probe uses the SAME api_key as production Week 6/.env.")
            print("    The probe MUST be a separate paper account. Aborting.")
            return 2

    try:
        acct = mod.check_auth(probe_cfg)
    except Exception as e:  # noqa: BLE001
        print(f"[x] Auth failed: {type(e).__name__}: {e}")
        print("    Check the Key ID / Secret were pasted correctly (no stray spaces/newlines).")
        return 1

    warn = []
    if PROD_ENV.exists():
        prod_vals = dotenv_values(PROD_ENV)
        if not _is_placeholder(prod_vals.get("ALPACA_API_KEY")):
            try:
                prod_acct = mod.check_auth(_cfg(mod, prod_vals))
                if prod_acct["id"] == acct["id"]:
                    print("[x] FATAL: probe account id == production account id. "
                          "Separate account required. Aborting.")
                    return 2
            except Exception:  # noqa: BLE001
                warn.append("could not verify production account id (prod auth failed) — check manually")

    print("[OK] Probe account #2 connected (PAPER).")
    print(f"     account id   : {acct['id']}")
    print(f"     status       : {acct['status']}")
    print(f"     equity       : ${acct['equity']:,.2f}")
    print(f"     cash         : ${acct['cash']:,.2f}")
    print(f"     buying_power : ${acct['buying_power']:,.2f}")
    print(f"     PDT flag     : {acct['pattern_day_trader']}")
    print(f"     base_url     : {probe_cfg.base_url}")
    if abs(acct["equity"] - 100_000) < 1.0:
        print("     (equity ~= $100k -> looks like a fresh paper account, good)")
    for w in warn:
        print(f"     [!] {w}")
    print("\nNext: wire the daily probe (v4_exec_probe.py) against THIS account.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
