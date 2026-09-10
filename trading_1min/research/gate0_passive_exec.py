"""
gate0_passive_exec.py — GATE 0 (Spec 1): passive execution feasibility.
Spec: gate0_passive_exec_spec.md (PRE-COMMIT — luat khoa 2026-07-23 truoc khi chay).

Chay:  python -m trading_1min.research.gate0_passive_exec --smoke   # khoi-test
       python -m trading_1min.research.gate0_passive_exec           # full 2024

Khung do: su kien = phut leader (ETF) co |r 1-phut| >= KAPPA*sigma; moi phut
tin hieu -> thu dat lenh cho tren MOI follower; do fill rate / adverse selection
/ chi phi co hoi; so voi paper trade (mid, khop chac chan, cung luat).
"""
import argparse
import time
import zlib
from types import SimpleNamespace

import numpy as np
import pandas as pd

from trading_1min.engine import data as dmod

# --- tham so KHOA theo spec (khong sua sau khi thay so) ---
KAPPA = 3.0            # nguong su kien |r| >= KAPPA*sigma (sens: 2.5, 4)
SIG_WIN, SIG_MIN = 60, 30
REFRACT = 5            # phut refractory / leader; control cach tin hieu > REFRACT
W_FILL = 2             # cua so khop entry, bar (sens: 1, 5)
H_STAR = 15            # hold ke hoach, bar (sens: 5, 30)
W_EXIT = 2             # cua so khop exit passive, bar
LC_K, LC_FLOOR = 3.0, 10.0   # loss-cut = max(3*sigma_f, 10bp) so voi gia khop
EDGE_REF = 1.5         # bp — chi phi co hoi moi lenh truot (kho a spec)
COST_GATE = 1.5        # bp — nguong dau cost_eff
F_MIN = 0.25           # fill rate toi thieu (chong dau suy bien)
MIN_ATT = 200          # follower du dieu kien (chi ap o full)
MAX_INVALID = 0.20     # tran ty le bo-vi-L1-invalid
N_PASS_NEED = 30       # so follower dau de mo Gate 1
TICK = 0.01            # $; through = gia phai xuyen qua lenh 1 tick
SEED = 42
HEDGE_BP = 0.3         # kich ban hedge SPY (bao cao, khong gate)
T_START = 570 + 10     # bo 10 phut dau phien
T_CUTOFF = 15 * 60 + 38  # su kien muon nhat 15:38
T_CLOSE = 15 * 60 + 58   # ep dong muon nhat 15:58
MK_D = (1, 5, 15)      # markout / drift (phut)

VARIANTS = ("bid", "mid-1/4", "mid")
MODES = ("through", "touch")

# ETF ung vien (giao voi universe-100 -> danh sach leader, in ra o smoke)
ETF_CANDS = {
    "SPY", "QQQ", "DIA", "IWM", "MDY", "RSP", "VTI", "VOO", "IVV", "IWB",
    "IWF", "IWD", "VUG", "VTV", "XLB", "XLC", "XLE", "XLF", "XLI", "XLK",
    "XLP", "XLRE", "XLU", "XLV", "XLY", "SMH", "SOXX", "XBI", "IBB", "KRE",
    "XOP", "XRT", "XHB", "GDX", "GLD", "SLV", "USO", "TLT", "IEF", "SHY",
    "HYG", "LQD", "AGG", "BND", "EEM", "EFA", "VEA", "VWO", "FXI", "EWZ",
    "VNQ", "IYR", "ARKK", "DXJ",
}

OUT = dmod.ROOT / "trading_1min" / "results" / "gate0_passive"
SPREADS = dmod.ROOT / "Week 5" / "data" / "microstructure" / "spreads_1min.parquet"


# ---------------- nap du lieu ----------------

def load_bars(t, start, end, cols=("high", "low", "close")):
    f = dmod.B1 / f"{t}.parquet"
    if not f.exists():
        return None
    df = pd.read_parquet(f, columns=list(cols)).loc[start:end]
    if not len(df):
        return None
    mins = df.index.hour * 60 + df.index.minute
    return df[(mins >= 570) & (mins <= 959)]


def load_hs(t, start, end, index):
    """Half-spread L1 THAT (fraction); NaN = invalid/thieu."""
    df = pd.read_parquet(SPREADS, filters=[("ticker", "==", t)],
                         columns=["timestamp_et", "half_spread_l1_bps", "is_valid"])
    df = df[(df["timestamp_et"] >= start) & (df["timestamp_et"] <= end + " 23:59")]
    df = df.set_index("timestamp_et")
    hs = df["half_spread_l1_bps"].where(df["is_valid"])
    hs = hs[~hs.index.duplicated()]
    return (hs.reindex(index) / 1e4).values


def within_day_ret(ln, day):
    r = np.diff(ln, prepend=np.nan)
    r[np.r_[True, day[1:] != day[:-1]]] = np.nan   # bo return qua dem
    return r


def roll_sigma_bp(r):
    """Sigma dong: std mau (ddof=1) 60 bar gan nhat, >=30 obs, shift(1)
    (nguong biet TRUOC bar tin hieu)."""
    return pd.Series(r).rolling(SIG_WIN, min_periods=SIG_MIN).std().shift(1).values * 1e4


def day_end_positions(day, mod):
    """Vi tri bar cuoi cung cua ngay co phut <= T_CLOSE (diem ep dong)."""
    dend = np.empty(len(day), dtype=int)
    i, n = 0, len(day)
    while i < n:
        j = i
        while j + 1 < n and day[j + 1] == day[i]:
            j += 1
        seg = np.nonzero(mod[i:j + 1] <= T_CLOSE)[0]
        dend[i:j + 1] = i + (seg[-1] if len(seg) else 0)
        i = j + 1
    return dend


def prep(t, start, end, half_frac):
    """Goi du lieu 1 follower thanh cac mang numpy dung chung cho moi sim."""
    df = load_bars(t, start, end)
    if df is None:
        return None
    A = SimpleNamespace(ticker=t, idx=df.index)
    A.close = df["close"].values.astype(float)
    A.high = df["high"].values.astype(float)
    A.low = df["low"].values.astype(float)
    A.ln = np.log(A.close)
    A.day = np.array([d.toordinal() for d in df.index.date])
    A.mod = (df.index.hour * 60 + df.index.minute).values
    A.sig = roll_sigma_bp(within_day_ret(A.ln, A.day))
    A.dend = day_end_positions(A.day, A.mod)
    A.hs = load_hs(t, start, end, df.index)
    hs_ff = pd.Series(A.hs).groupby(A.day).ffill().values
    A.hs_ff = np.where(np.isfinite(hs_ff), hs_ff, half_frac)  # fallback: median ca ky
    return A


# ---------------- su kien leader ----------------

def leader_events(t, start, end, kappa=KAPPA):
    df = load_bars(t, start, end, cols=("close",))
    if df is None:
        return [], 0
    ln = np.log(df["close"].values)
    day = np.array([d.toordinal() for d in df.index.date])
    mod = (df.index.hour * 60 + df.index.minute).values
    r = within_day_ret(ln, day)
    sig = pd.Series(r).rolling(SIG_WIN, min_periods=SIG_MIN).std().shift(1).values
    with np.errstate(invalid="ignore", divide="ignore"):
        z = np.abs(r) / sig
    ok = np.isfinite(z) & (z >= kappa) & (mod >= T_START) & (mod <= T_CUTOFF)
    evs, last_day, last_mod = [], None, -999
    for i in np.nonzero(ok)[0]:
        if day[i] == last_day and mod[i] - last_mod < REFRACT:
            continue
        evs.append((df.index[i], 1 if r[i] > 0 else -1, float(z[i])))
        last_day, last_mod = day[i], mod[i]
    return evs, int(ok.sum())


def dedup_events(all_evs):
    """Nhieu leader no cung phut -> 1 phut tin hieu, huong theo |z| lon nhat."""
    best = {}
    for ts, side, z, ldr in all_evs:
        if ts not in best or z > best[ts][1]:
            best[ts] = (side, z, ldr)
    return [(ts, s, z, l) for ts, (s, z, l) in sorted(best.items())]


# ---------------- may mo phong ----------------

def paper_pnl(A, pos, side, L, h_star):
    """Paper: vao mid close t+1, cung luat loss-cut tren mid, ra mid t+1+h*."""
    e = pos + 1
    dend = A.dend[pos]
    ln_in = A.ln[e]
    stop = min(e + h_star, dend)
    for v in range(e + 1, stop + 1):
        if 1e4 * side * (A.ln[v] - ln_in) < -L:
            return 1e4 * side * (A.ln[v] - ln_in)
    return 1e4 * side * (A.ln[stop] - ln_in)


def taker_px(A, v, side):
    return A.close[v] * (1 - side * A.hs_ff[v])


def real_exit(A, fill, side, p_in, L, thr, h_star, w_exit):
    """Exit S4-lite: loss-cut taker ngay khi nguoc >= L (gom ca bar khop —
    worst ordering); den gio: passive far touch w_exit bar roi taker."""
    ln_in = np.log(p_in)
    dend = A.dend[fill]
    stop = min(fill + h_star, dend)
    for v in range(fill, stop + 1):
        if 1e4 * side * (A.ln[v] - ln_in) < -L:
            return taker_px(A, v, side), "losscut"
    if stop >= dend:
        return taker_px(A, dend, side), "eod"
    p_x = A.close[stop] * (1 + side * A.hs_ff[stop])
    last = min(stop + w_exit, dend)
    for u in range(stop + 1, last + 1):
        if 1e4 * side * (A.ln[u] - ln_in) < -L:
            return taker_px(A, u, side), "losscut"
        hit = (A.high[u] >= p_x + thr) if side > 0 else (A.low[u] <= p_x - thr)
        if hit:
            return p_x, "passive"
    return taker_px(A, last, side), "taker"


def attempt(A, pos, side, mode, vi, w_fill=W_FILL, h_star=H_STAR, w_exit=W_EXIT):
    """Mot attempt tai phut quyet dinh pos. Tra ve dict co 'st'."""
    n = len(A.close)
    if pos < 0:
        return {"st": "no_bar"}
    if not np.isfinite(A.hs[pos]):
        return {"st": "invalid_l1"}
    nx = pos + 1
    if nx >= n or A.day[nx] != A.day[pos]:
        return {"st": "no_next"}
    p0, hs0 = A.close[pos], A.hs[pos]
    if vi == 0:
        plim = p0 * (1 - side * hs0)          # dat tai bid/ask (earn full half)
    elif vi == 1:
        plim = p0 * (1 - side * hs0 / 2)      # mid -1/4 spread
    else:
        plim = p0                              # join mid (kieu Sam S1)
    L = max(LC_K * (A.sig[pos] if np.isfinite(A.sig[pos]) else 0.0), LC_FLOOR)
    ppnl = paper_pnl(A, pos, side, L, h_star)
    thr = TICK if mode == "through" else 0.0
    fill = -1
    for u in range(nx, min(pos + w_fill, n - 1) + 1):
        if A.day[u] != A.day[pos]:
            break
        hit = (A.low[u] <= plim - thr) if side > 0 else (A.high[u] >= plim + thr)
        if hit:
            fill = u
            break
    base = {"day": A.day[pos], "pos": pos, "side": side, "paper": ppnl}
    if fill < 0:
        return {"st": "unfilled", **base}
    px_out, xtype = real_exit(A, fill, side, plim, L, thr, h_star, w_exit)
    rpnl = 1e4 * side * (np.log(px_out) - np.log(plim))
    return {"st": "filled", "fill": fill, "plim": plim, "real": rpnl,
            "is": ppnl - rpnl, "xtype": xtype, **base}


# ---------------- thong ke ----------------

def day_cluster(vals, days):
    """Gom cum theo ngay: mean trong ngay -> mean/t tren cac ngay."""
    s = pd.Series(vals, index=days, dtype=float).dropna()
    if not len(s):
        return np.nan, np.nan, 0
    per = s.groupby(level=0).mean()
    n = len(per)
    m = per.mean()
    se = per.std(ddof=1) / np.sqrt(n) if n > 1 else np.nan
    return m, (m / se if se and se > 0 else np.nan), n


def summarize(recs):
    att = [r for r in recs if r["st"] in ("unfilled", "filled")]
    fil = [r for r in recs if r["st"] == "filled"]
    n_att, n_fil = len(att), len(fil)
    if n_att == 0:
        return None
    f = n_fil / n_att
    is_m, is_t, nd = day_cluster([r["is"] for r in fil], [r["day"] for r in fil])
    cost = f * is_m + (1 - f) * EDGE_REF if np.isfinite(is_m) else np.nan
    out = dict(n_att=n_att, n_fill=n_fil, f=f, is_mean=is_m, is_t=is_t,
               n_days=nd, cost_eff=cost)
    for k in ("losscut", "passive", "taker", "eod"):
        out[f"x_{k}"] = (sum(1 for r in fil if r["xtype"] == k) / n_fil
                         if n_fil else np.nan)
    return out


def drift_bp(A, pos, side, d):
    q = pos + d
    if q < len(A.ln) and A.day[q] == A.day[pos]:
        return 1e4 * side * (A.ln[q] - A.ln[pos])
    return np.nan


def markout_bp(A, rec, d):
    q = rec["fill"] + d
    if q < len(A.ln) and A.day[q] == A.day[rec["fill"]]:
        return 1e4 * rec["side"] * (A.ln[q] - np.log(rec["plim"]))
    return np.nan


# ---------------- control khop-phut ----------------

def control_positions(A, sig_list, sig_by_day, rng, max_try=20):
    """Voi moi su kien: boc phut matched (cung phut-trong-ngay, ngay khac,
    cach moi tin hieu > REFRACT phut). Huong boc ngau nhien +-1 (doi xung)."""
    pos_map = {(d, m): p for p, (d, m) in enumerate(zip(A.day, A.mod))}
    all_days = sorted(set(A.day))
    out = []
    for pos, _side, _z in sig_list:
        if pos < 0:
            continue
        d0, m = A.day[pos], A.mod[pos]
        for _ in range(max_try):
            d = all_days[rng.integers(len(all_days))]
            if d == d0:
                continue
            p = pos_map.get((d, m))
            if p is None:
                continue
            sigs = sig_by_day.get(d)
            if sigs is not None and len(sigs) and np.min(np.abs(sigs - m)) <= REFRACT:
                continue
            out.append((p, 1 if rng.random() < 0.5 else -1, np.nan))
            break
    return out


# ---------------- chay 1 combo tren toan bo follower ----------------

def run_combo(A_list, sig_lists, vi, mode, w_fill=W_FILL, h_star=H_STAR,
              w_exit=W_EXIT, flip=False, day_lo=None, day_hi=None):
    """Pooled (equal-weight follower) f / IS / cost_eff cho 1 to hop tham so."""
    fs, iss, costs = [], [], []
    for A, sl in zip(A_list, sig_lists):
        recs = []
        for pos, side, _z in sl:
            if day_lo is not None and (A.day[pos] < day_lo if pos >= 0 else True):
                continue
            if day_hi is not None and (A.day[pos] >= day_hi if pos >= 0 else True):
                continue
            recs.append(attempt(A, pos, -side if flip else side, mode, vi,
                                w_fill, h_star, w_exit))
        s = summarize(recs)
        if s and s["n_att"] > 0:
            fs.append(s["f"])
            iss.append(s["is_mean"])
            costs.append(s["cost_eff"])
    return (np.nanmean(fs) if fs else np.nan,
            np.nanmean(iss) if iss else np.nan,
            np.nanmean(costs) if costs else np.nan)


# ---------------- main ----------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    rep = []

    def say(s):
        print(s, flush=True)
        rep.append(s)

    tag = "smoke" if args.smoke else "full"
    say(f"===== GATE 0 PASSIVE EXEC ({tag}) — spec gate0_passive_exec_spec.md =====")

    univ, half = dmod.load_universe(100)
    etfs = sorted(set(univ) & ETF_CANDS)
    followers_all = [t for t in univ if t not in ETF_CANDS]
    if args.smoke:
        leaders = [t for t in ("QQQ", "SPY") if t in etfs]
        n_fol, start, end = 12, "2024-01-02", "2024-01-26"
    else:
        leaders = etfs
        n_fol, start, end = len(followers_all), "2024-01-02", "2024-12-31"
    say(f"universe {len(univ)} | ETF trong universe: {', '.join(etfs)}")
    say(f"leaders ({tag}): {', '.join(leaders)} | ky: {start} -> {end}")

    # --- su kien leader ---
    all_evs = []
    for ldr in leaders:
        evs, raw = leader_events(ldr, start, end)
        all_evs += [(ts, s, z, ldr) for ts, s, z in evs]
        say(f"[events] {ldr:>4}: raw {raw:>5} -> sau refractory {len(evs):>5}")
    evts = dedup_events(all_evs)
    if not evts:
        say("KHONG co su kien — dung.")
        return
    n_days_ev = len({ts.date() for ts, *_ in evts})
    zs = np.array([z for _, _, z, _ in evts])
    say(f"[events] dedup: {len(evts):,} phut tin hieu / {n_days_ev} phien "
        f"(~{len(evts) / n_days_ev:.1f}/phien)")
    say(f"[z-bucket] [3,4): {int((zs < 4).sum())}  [4,6): "
        f"{int(((zs >= 4) & (zs < 6)).sum())}  [6+): {int((zs >= 6).sum())}")
    sig_by_day = {}
    for ts, *_ in evts:
        sig_by_day.setdefault(ts.date().toordinal(), []).append(
            ts.hour * 60 + ts.minute)
    sig_by_day = {d: np.sort(np.array(v)) for d, v in sig_by_day.items()}
    ev_ts = pd.DatetimeIndex([ts for ts, *_ in evts])
    ev_sides = np.array([s for _, s, _, _ in evts])
    ev_z = zs

    # --- nap follower + sim 6 combo ---
    A_list, sig_lists, skip_stats, summaries = [], [], [], {}
    for i, t in enumerate(followers_all):
        if len(A_list) >= n_fol:
            break
        A = prep(t, start, end, half.get(t, np.nan) / 1e4)
        if A is None:
            continue
        pos_arr = A.idx.get_indexer(ev_ts)
        sl = list(zip(pos_arr, ev_sides, ev_z))
        n_nobar = int((pos_arr < 0).sum())
        n_inv = sum(1 for p in pos_arr if p >= 0 and not np.isfinite(A.hs[p]))
        with_bar = len(sl) - n_nobar
        skip_stats.append(dict(ticker=t, n_events=len(sl), no_bar=n_nobar,
                               invalid_l1=n_inv,
                               inv_share=n_inv / with_bar if with_bar else np.nan))
        for vi in range(3):
            for mode in MODES:
                recs = [attempt(A, p, s, mode, vi) for p, s, _ in sl]
                summaries[(t, vi, mode)] = summarize(recs)
        A_list.append(A)
        sig_lists.append(sl)
        if (len(A_list) % 10 == 0) or len(A_list) == n_fol:
            say(f"  ... {len(A_list)} follower xong ({time.time() - t0:.0f}s)")
    fols = [A.ticker for A in A_list]
    say(f"[followers] {len(fols)} ma co du lieu | skip no_bar trung binh "
        f"{np.mean([s['no_bar'] for s in skip_stats]):.1f}/ma | "
        f"invalid L1 trung binh "
        f"{100 * np.nanmean([s['inv_share'] for s in skip_stats]):.1f}%")

    # --- bang pooled 6 combo ---
    say("")
    say("[pooled] equal-weight follower — f | IS (bp) | cost_eff (bp):")
    pool = {}
    for vi in range(3):
        for mode in MODES:
            ss = [summaries[(t, vi, mode)] for t in fols
                  if summaries.get((t, vi, mode))]
            f_m = np.nanmean([s["f"] for s in ss])
            is_m = np.nanmean([s["is_mean"] for s in ss])
            c_m = np.nanmean([s["cost_eff"] for s in ss])
            pool[(vi, mode)] = (f_m, is_m, c_m)
            say(f"  V{vi + 1} {VARIANTS[vi]:<7} {mode:<7}: f {f_m:5.1%} | "
                f"IS {is_m:+6.2f} | cost_eff {c_m:5.2f}")

    # --- chon bien the chung (nhieu follower dau nhat o THROUGH; tie -> V1) ---
    def n_pass(vi, mode, eligible_only):
        cnt = 0
        for t, st in zip(fols, skip_stats):
            s = summaries.get((t, vi, mode))
            if not s:
                continue
            if eligible_only and (s["n_att"] < MIN_ATT
                                  or st["inv_share"] >= MAX_INVALID):
                continue
            if (np.isfinite(s["cost_eff"]) and s["cost_eff"] <= COST_GATE
                    and s["f"] >= F_MIN):
                cnt += 1
        return cnt

    elig = not args.smoke                    # smoke: chua ap nguong MIN_ATT
    pass_thr = [n_pass(vi, "through", elig) for vi in range(3)]
    vi_star = int(np.argmax(pass_thr))
    pass_tou = [n_pass(vi, "touch", elig) for vi in range(3)]
    say("")
    say(f"[gate] follower dau (cost<={COST_GATE}bp, f>={F_MIN:.0%}"
        f"{', >=200 att' if elig else ' — smoke: chua ap san attempts'}):")
    for vi in range(3):
        say(f"  V{vi + 1} {VARIANTS[vi]:<7}: through {pass_thr[vi]:>3} | "
            f"touch {pass_tou[vi]:>3}")
    say(f"[gate] bien the chung (max through): V{vi_star + 1} {VARIANTS[vi_star]}")

    # --- diagnostics + control tren bien the chung ---
    rng_master = np.random.default_rng(SEED)
    rows, ctl_pool = [], {m: [] for m in MODES}
    dr_fil, dr_unf, mo_pool = [], [], {d: [] for d in MK_D}
    hs_sig_all, hs_ctl_all = [], []
    ib_stats = {b: [] for b in ("[3,4)", "[4,6)", "[6+)")}
    for A, sl, st in zip(A_list, sig_lists, skip_stats):
        rng = np.random.default_rng([SEED, zlib.crc32(A.ticker.encode())])
        ctl = control_positions(A, sl, sig_by_day, rng)
        rec_m, ctl_m = {}, {}
        for mode in MODES:
            rec_m[mode] = [attempt(A, p, s, mode, vi_star) for p, s, _ in sl]
            ctl_m[mode] = [attempt(A, p, s, mode, vi_star) for p, s, _ in ctl]
            cs = summarize(ctl_m[mode])
            if cs:
                ctl_pool[mode].append(cs)
        recs = rec_m["through"]
        # adverse selection: drift sau quyet dinh (filled vs unfilled), markout
        for r in recs:
            if r["st"] == "filled":
                dr_fil.append(drift_bp(A, r["pos"], r["side"], 15))
                for d in MK_D:
                    mo_pool[d].append(markout_bp(A, r, d))
            elif r["st"] == "unfilled":
                dr_unf.append(drift_bp(A, r["pos"], r["side"], 15))
        # spread gian tai phut tin hieu vs control minutes
        sig_hs = [A.hs[p] for p, _, _ in sl if p >= 0 and np.isfinite(A.hs[p])]
        ctl_hs = [A.hs[p] for p, _, _ in ctl if np.isfinite(A.hs[p])]
        if sig_hs:
            hs_sig_all.append(1e4 * np.mean(sig_hs))
        if ctl_hs:
            hs_ctl_all.append(1e4 * np.mean(ctl_hs))
        # intensity bucket (S2) tren gate combo
        for r, (_p, _s, z) in zip(recs, sl):
            if r["st"] not in ("unfilled", "filled") or not np.isfinite(z):
                continue
            b = "[3,4)" if z < 4 else ("[4,6)" if z < 6 else "[6+)")
            ib_stats[b].append((r["st"] == "filled",
                                r.get("is", np.nan), r["day"]))
        # bang per-follower (CSV)
        row = dict(ticker=A.ticker, n_events=st["n_events"], no_bar=st["no_bar"],
                   invalid_l1=st["invalid_l1"], inv_share=st["inv_share"])
        for vi in range(3):
            for mode in MODES:
                s = summaries.get((A.ticker, vi, mode))
                pre = f"V{vi + 1}_{mode[:3]}"
                if s:
                    row[f"{pre}_f"] = s["f"]
                    row[f"{pre}_is"] = s["is_mean"]
                    row[f"{pre}_cost"] = s["cost_eff"]
        s_thr = summaries.get((A.ticker, vi_star, "through"))
        if s_thr:
            row["gate_cost"] = s_thr["cost_eff"]
            row["gate_cost_hedge"] = (s_thr["cost_eff"] + HEDGE_BP
                                      if np.isfinite(s_thr["cost_eff"]) else np.nan)
            row["gate_f"] = s_thr["f"]
            row["x_losscut"] = s_thr["x_losscut"]
            row["x_passive"] = s_thr["x_passive"]
            row["x_taker"] = s_thr["x_taker"]
        rows.append(row)
    pd.DataFrame(rows).to_csv(OUT / f"cost_by_follower_{tag}.csv", index=False)

    say("")
    say(f"[adverse] drift 15' sau quyet dinh (V{vi_star + 1} through, pooled): "
        f"filled {np.nanmean(dr_fil):+.2f}bp (n={sum(np.isfinite(dr_fil))}) | "
        f"unfilled {np.nanmean(dr_unf):+.2f}bp (n={sum(np.isfinite(dr_unf))})")
    say("[adverse] markout sau-KHOP (Huang-Stoll): " + " | ".join(
        f"{d}': {np.nanmean(mo_pool[d]):+.2f}bp" for d in MK_D))
    say(f"[adverse] half-spread tai phut tin hieu {np.nanmean(hs_sig_all):.2f}bp"
        f" vs control {np.nanmean(hs_ctl_all):.2f}bp")
    for mode in MODES:
        ss = ctl_pool[mode]
        if ss:
            say(f"[control] {mode:<7}: f {np.nanmean([s['f'] for s in ss]):5.1%} | "
                f"IS {np.nanmean([s['is_mean'] for s in ss]):+6.2f}bp "
                f"(vs signal IS {pool[(vi_star, mode)][1]:+6.2f}bp)")
    say(f"[intensity] (V{vi_star + 1} through) bucket: f | IS | n:")
    for b, lst in ib_stats.items():
        if not lst:
            continue
        fb = np.mean([x[0] for x in lst])
        ism, _, _ = day_cluster([x[1] for x in lst if x[0]],
                                [x[2] for x in lst if x[0]])
        say(f"  z {b:<6}: f {fb:5.1%} | IS {ism:+6.2f}bp | n {len(lst)}")

    # --- sensitivity (chi full) ---
    if not args.smoke:
        say("")
        say(f"[sensitivity] (V{vi_star + 1} through) f | IS | cost_eff:")
        sens = [("base", {}), ("W=1", dict(w_fill=1)), ("W=5", dict(w_fill=5)),
                ("h*=5", dict(h_star=5)), ("h*=30", dict(h_star=30)),
                ("fade", dict(flip=True))]
        jul = pd.Timestamp("2024-07-01").date().toordinal()
        sens += [("H1/2024", dict(day_hi=jul)), ("H2/2024", dict(day_lo=jul))]
        srows = []
        for name, kw in sens:
            f_m, is_m, c_m = run_combo(A_list, sig_lists, vi_star, "through", **kw)
            say(f"  {name:<8}: f {f_m:5.1%} | IS {is_m:+6.2f} | cost {c_m:5.2f}")
            srows.append(dict(name=name, f=f_m, is_mean=is_m, cost_eff=c_m))
        for kap in (2.5, 4.0):
            all_e = []
            for ldr in leaders:
                evs, _ = leader_events(ldr, start, end, kappa=kap)
                all_e += [(ts, s, z, ldr) for ts, s, z in evs]
            evk = dedup_events(all_e)
            ek_ts = pd.DatetimeIndex([ts for ts, *_ in evk])
            ek_s = np.array([s for _, s, _, _ in evk])
            ek_z = np.array([z for _, _, z, _ in evk])
            sls = [list(zip(A.idx.get_indexer(ek_ts), ek_s, ek_z)) for A in A_list]
            f_m, is_m, c_m = run_combo(A_list, sls, vi_star, "through")
            say(f"  k={kap:<6}: f {f_m:5.1%} | IS {is_m:+6.2f} | cost {c_m:5.2f} "
                f"({len(evk):,} su kien)")
            srows.append(dict(name=f"kappa={kap}", f=f_m, is_mean=is_m,
                              cost_eff=c_m))
        pd.DataFrame(srows).to_csv(OUT / "sensitivity.csv", index=False)

    # --- phan quyet ---
    say("")
    if args.smoke:
        say("KHOI-TEST xong — chua ap luat. TRINH USER truoc khi chay full.")
    else:
        n_thr, n_tou = pass_thr[vi_star], pass_tou[vi_star]
        say("*" * 70)
        say(f"GATE 0: bien the V{vi_star + 1} ({VARIANTS[vi_star]}) | "
            f"dau THROUGH: {n_thr} | dau TOUCH: {n_tou} | can {N_PASS_NEED}")
        if n_thr >= N_PASS_NEED:
            say("PHAN QUYET: DAT CHAC (chuan through) -> mo Gate 1.")
        elif n_tou >= N_PASS_NEED:
            say("PHAN QUYET: DAT SAT NUT (chi du o touch) -> mo Gate 1 kem "
                "CO DO: PHAI kiem paper-live truoc khi tin — ghi memory, khong go.")
        else:
            say("PHAN QUYET: ROT GATE 0 -> DONG track lead-lag. "
                "Bao cao trung thuc. Khong thuong luong.")
        say("*" * 70)

    say(f"tong: {time.time() - t0:.0f}s")
    (OUT / f"report_{tag}.txt").write_text("\n".join(rep), encoding="utf-8")


if __name__ == "__main__":
    main()
