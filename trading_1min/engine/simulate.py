"""
simulate.py — may trang thai lenh cua 1 tuan trade, tham so hoa de tai lap
ca 2 quy uoc legacy lan chay chuan v0.

Tin hieu: z tinh tu CLOSE (mean/std hoc tu formation, dong bang);
vao khi |z| > z_entry, ra khi z cat 0, ep dong cuoi tuan.
Fill: gia spread tai bar t+lag (close hoac open) sau tin hieu tai bar t.

convention:
  "v0"       — CHUAN moi (quyet dinh 2026-07-15): xet tin hieu toi bar cuoi
               cho phep theo lag (t < n-1-lag), ep dong tai bar CUOI tuan.
               Voi lag=1 fill close, trung khop hoan toan run #11.
  "legacy11" — alias cua "v0" (window_opt_stage1.py chi chay lag=1).
  "legacy10" — quy uoc confirmation_test.py: ngung xet tin hieu tai
               t < n - max_shift - 1 (max_shift=3 bat ke lag), ep dong tai
               fill[n - max_shift - 1 + lag]. Chi dung de tai lap run #10.
"""
import numpy as np


def simulate_week(z, fill, lag, z_entry=2.0, convention="v0", max_shift=3):
    """Tra ve list (entry_t, exit_t, side, bps, forced) cua 1 tuan, 1 cap, 1 mode."""
    n = len(z)
    if convention == "legacy10":
        sig_end = n - max_shift - 1
        forced_i = n - max_shift - 1 + lag
    elif convention in ("v0", "legacy11"):
        sig_end = n - 1 - lag
        forced_i = n - 1
    else:
        raise ValueError(f"convention la? {convention}")

    trades = []
    pos, entry, entry_t = 0, 0.0, -1
    for t in range(sig_end):
        f = fill[t + lag]
        if not np.isfinite(f):
            continue
        if pos == 0:
            if z[t] > z_entry:
                pos, entry, entry_t = -1, f, t
            elif z[t] < -z_entry:
                pos, entry, entry_t = 1, f, t
        elif (pos == -1 and z[t] <= 0) or (pos == 1 and z[t] >= 0):
            trades.append((entry_t, t, pos, pos * (f - entry) * 1e4, False))
            pos = 0
    if pos != 0:
        last = fill[forced_i]
        if np.isfinite(last):
            trades.append((entry_t, forced_i - lag, pos, pos * (last - entry) * 1e4, True))
    return trades
