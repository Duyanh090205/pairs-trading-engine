"""
periodicity_scan.py — Tier-0 test HO 1 (HKS periodicity) + ban do thuc thi.
Spec: periodicity_spec.md (PRE-COMMIT — luat khoa truoc khi chay).

Chay:  python -m trading_1min.research.periodicity_scan            # full
       python -m trading_1min.research.periodicity_scan --smoke    # khoi-test
"""
import argparse
import time

import numpy as np
import pandas as pd

from trading_1min.engine import data as dmod

N_SLOTS = 13
LOOKBACK = 20
MIN_LB = 15
MIN_NAMES = 60
N_DECILE = 10
N_SPREAD_NAMES = 20

OUT = dmod.ROOT / "trading_1min" / "results" / "periodicity"
SPREADS = dmod.ROOT / "Week 5" / "data" / "microstructure" / "spreads_1min.parquet"


def halfhour_panel(m1c):
    """Panel return nua-gio: MultiIndex (date, slot) x ticker (bp thang log)."""
    r = m1c.diff()
    day = np.array([d for d in m1c.index.date])
    new_day = np.r_[True, day[1:] != day[:-1]]
    r.values[new_day, :] = np.nan                       # bo return qua dem
    mins = m1c.index.hour * 60 + m1c.index.minute
    slot = np.clip((mins - 570) // 30, 0, N_SLOTS - 1)
    g = r.groupby([pd.Index(day, name="date"), pd.Index(slot, name="slot")])
    return g.sum(min_count=1)


def daily_cluster_t(series_by_dayslot):
    """Gom cum theo NGAY: mean trong ngay -> t tren cac ngay."""
    per_day = series_by_dayslot.groupby(level=0).mean().dropna()
    n = len(per_day)
    if n < 30:
        return np.nan, np.nan, n
    m = per_day.mean()
    se = per_day.std(ddof=1) / np.sqrt(n)
    return m, m / se if se > 0 else np.nan, n


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
    end = "2024-03-31" if args.smoke else "2025-06-30"
    say(f"===== PERIODICITY SCAN ({tag}) — spec pre-commit periodicity_spec.md =====")

    univ, half = dmod.load_universe(100)
    mats = dmod.load_log_prices(univ, "2024-01-02", end, ["close", "volume"])
    m1c = mats["close"].ffill()
    m1v = mats["volume"]
    univ = list(m1c.columns)
    cost_rt = pd.Series({t: 2 * half[t] for t in univ})   # khu hoi = full spread

    hh = halfhour_panel(m1c)                              # (date,slot) x ticker, log
    dates = hh.index.get_level_values(0).unique().sort_values()
    say(f"universe {len(univ)} | {len(dates)} phien | {len(hh):,} (ngay,khung)")

    # --- predictor A (same-slot) va B (other-slot) ---
    A = {}
    Rj = {}
    for j in range(N_SLOTS):
        rj = hh.xs(j, level=1).reindex(dates)
        Rj[j] = rj
        A[j] = rj.rolling(LOOKBACK, min_periods=MIN_LB).mean().shift(1)
    M = hh.groupby(level=0).mean().reindex(dates)         # mean 13 khung moi ngay
    B = {}
    for j in range(N_SLOTS):
        m_excl = (M * N_SLOTS - Rj[j]) / (N_SLOTS - 1)
        B[j] = m_excl.rolling(LOOKBACK, min_periods=MIN_LB).mean().shift(1)

    # --- Fama-MacBeth cross-section + decile L-S ---
    rows = []
    for j in range(N_SLOTS):
        rj, aj, bj = Rj[j], A[j], B[j]
        for d in dates:
            y = rj.loc[d]
            xa = aj.loc[d]
            xb = bj.loc[d]
            ok = y.notna() & xa.notna() & xb.notna()
            if ok.sum() < MIN_NAMES:
                continue
            yv = y[ok].values
            xav = xa[ok].values
            xbv = xb[ok].values

            def z(v):
                s = v.std()
                return (v - v.mean()) / s if s > 0 else v * 0

            yz, az, bz = z(yv), z(xav), z(xbv)
            X = np.column_stack([az, bz])
            try:
                coef, *_ = np.linalg.lstsq(X, yz, rcond=None)
            except np.linalg.LinAlgError:
                continue
            ga, gb = coef
            # decile L-S theo A (return tho, bp)
            order = np.argsort(xav)
            names_lo = ok[ok].index[order[:N_DECILE]]
            names_hi = ok[ok].index[order[-N_DECILE:]]
            ls_bp = (yv[order[-N_DECILE:]].mean() - yv[order[:N_DECILE]].mean()) * 1e4
            floor = cost_rt[list(names_lo) + list(names_hi)].mean()
            rows.append((d, j, ga, gb, ga - gb, ls_bp, floor))

    fm = pd.DataFrame(rows, columns=["date", "slot", "gA", "gB", "gA_minus_gB",
                                     "ls_bp", "floor_bp"]).set_index(["date", "slot"])
    fm.to_csv(OUT / f"fm_{tag}.csv")

    mA, tA, nd = daily_cluster_t(fm["gA"])
    mD, tD, _ = daily_cluster_t(fm["gA_minus_gB"])
    mL, tL, _ = daily_cluster_t(fm["ls_bp"])
    floor_mean = fm["floor_bp"].mean()
    say("")
    say(f"[FM]   gamma_A (same-slot)      = {mA:+.4f}  t_ngay = {tA:+.2f}  ({nd} ngay)")
    say(f"[FM]   gamma_A - gamma_B        = {mD:+.4f}  t_ngay = {tD:+.2f}")
    say(f"[econ] decile L-S gross         = {mL:+.2f} bp/luot  t_ngay = {tL:+.2f}")
    say(f"[econ] san phi danh muc (mean)  = {floor_mean:.2f} bp")

    # gamma_A theo khung gio (chan doan, khong verdict)
    say("")
    say("[chan doan] gamma_A theo khung nua-gio:")
    for j in range(N_SLOTS):
        sub = fm.xs(j, level=1)["gA"]
        mj, tj, nj = daily_cluster_t(sub)
        lbl = f"{9*60+30+30*j:>4d}"
        hhmm = f"{(570+30*j)//60:02d}:{(570+30*j)%60:02d}"
        say(f"  khung {j:>2} ({hhmm}) gamma_A {mj:+.4f} (t {tj:+.1f}, {nj} ngay)")

    # --- ban do thuc thi (chi run full) ---
    if not args.smoke:
        say("")
        say("[ban do] ho so 13 khung nua-gio (universe 100, 2024-01->2025-06):")
        absr = hh.abs().groupby(level=1).mean().mean(axis=1) * 1e4
        mins2 = m1v.index.hour * 60 + m1v.index.minute
        slot2 = np.clip((mins2 - 570) // 30, 0, N_SLOTS - 1)
        day2 = np.array([d for d in m1v.index.date])
        vday = m1v.groupby(pd.Index(day2)).transform("sum")
        vshare = (m1v / vday).groupby(pd.Index(slot2)).sum().mean(axis=1) \
            / len(set(day2)) * 100
        # spread that: 20 ma dai dien theo bac phi
        ss = pd.read_parquet(dmod.SS)
        ok = ss[ss["n_obs"] >= 0.95 * ss["n_obs"].max()].nsmallest(100, "median_bps")
        by_cost = list(ok.sort_values("median_bps")["ticker"])
        reps = by_cost[::5][:N_SPREAD_NAMES]
        sp_rows = []
        for t in reps:
            df = pd.read_parquet(SPREADS, filters=[("ticker", "==", t)],
                                 columns=["timestamp_et", "half_spread_l1_bps",
                                          "is_valid"])
            df = df[df["is_valid"]]
            df = df[(df["timestamp_et"] >= "2024-01-01") &
                    (df["timestamp_et"] < "2025-01-01")]
            if not len(df):
                continue
            m3 = df["timestamp_et"].dt.hour * 60 + df["timestamp_et"].dt.minute
            s3 = np.clip((m3 - 570) // 30, 0, N_SLOTS - 1)
            sp_rows.append(df.groupby(s3)["half_spread_l1_bps"].median().rename(t))
        sp = pd.concat(sp_rows, axis=1)
        sp_med = sp.median(axis=1)
        map_df = pd.DataFrame({"abs_ret_bp": absr, "vol_share_pct": vshare,
                               "half_spread_bp": sp_med})
        map_df.to_csv(OUT / "slot_map.csv")
        for j in range(N_SLOTS):
            hhmm = f"{(570+30*j)//60:02d}:{(570+30*j)%60:02d}"
            say(f"  {hhmm}  |r| {absr.get(j, np.nan):5.1f}bp  "
                f"vol {vshare.get(j, np.nan):5.2f}%  "
                f"half-spread {sp_med.get(j, np.nan):5.2f}bp")

    # --- phan quyet ---
    say("")
    if args.smoke:
        say("KHOI-TEST xong — chua ap luat.")
    else:
        cond_a = (tA >= 2) and (tD >= 2)
        cond_b = (mL > floor_mean) and (tL >= 2)
        say("*" * 70)
        say(f"(a) dau vet HKS:  t(gA)={tA:+.2f}, t(gA-gB)={tD:+.2f}  "
            f"-> {'DAT' if cond_a else 'TRUOT'}")
        say(f"(b) an duoc phi:  gross {mL:+.2f} vs san {floor_mean:.2f} bp, "
            f"t={tL:+.2f}  -> {'DAT' if cond_b else 'TRUOT'}")
        if cond_a and cond_b:
            say("NHANH ALPHA HO 1 CON NGO -> buoc ke: xac nhan 2022-23 (hoi user).")
        elif cond_a:
            say("PHAN QUYET: dau vet HKS co that nhung KHONG an duoc phi ->"
                " dong nhanh alpha; ghi nhan cho execution.")
        else:
            say("PHAN QUYET: hieu ung HKS khong con dau vet dat chuan tren data ta"
                " -> dong nhanh alpha.")
        say("Ban do thuc thi (slot_map.csv) giao nguyen ven trong moi kich ban.")
        say("*" * 70)

    say(f"tong: {time.time() - t0:.0f}s")
    (OUT / f"report_{tag}.txt").write_text("\n".join(rep), encoding="utf-8")


if __name__ == "__main__":
    main()
