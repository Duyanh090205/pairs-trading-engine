"""
run.py — config -> chay walk-forward -> report chuan + trades.parquet co metadata.

Chay tu goc repo:
    python -m trading_1min.engine.run trading_1min/configs/repro_run10.py
Tuy chon:
    --max-weeks N   chi chay N tuan dau (nghiem thu tang 1)
    --tag _xxx      hau to thu muc ket qua (de khong de len ket qua chinh)

Vong lap moi tuan (giu dung thu tu cua script cu de tai lap chuoi ngau nhien):
  1. boc control (1 lan goi rng / tuan)
  2. moi variant: Johansen chon cap tren cua so hoc -> mo phong tuan trade
  3. ghi tung lenh kem metadata (tuan, cap, beta, thoi diem, forced, phi)
"""
import argparse
import importlib.util
import json
import os
import time
from concurrent.futures import ProcessPoolExecutor
from itertools import combinations

import numpy as np
import pandas as pd

from . import data as dmod
from . import selection as smod
from . import stats as st
from .simulate import simulate_week


def load_config(path):
    spec = importlib.util.spec_from_file_location("cfg_module", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.CONFIG, getattr(mod, "ACCEPT", {}), getattr(mod, "BONUS", {})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("config")
    ap.add_argument("--max-weeks", type=int, default=None)
    ap.add_argument("--tag", default="")
    ap.add_argument("--offset", type=int, default=None,
                    help="ghi de weeks.offset_days (quet moc chia tuan)")
    args = ap.parse_args()
    cfg, accept, bonus = load_config(args.config)
    if args.offset is not None:
        cfg["weeks"]["offset_days"] = args.offset

    out = dmod.ROOT / "trading_1min" / "results" / (cfg["name"] + args.tag)
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    rep = []

    def say(s):
        print(s, flush=True)
        rep.append(s)

    # --- du lieu ---
    univ, half = dmod.load_universe(cfg.get("n_univ", 100))
    cols = cfg["data"]["columns"]
    mats = dmod.load_log_prices(univ, cfg["data"]["start"], cfg["data"]["end"], cols)
    m1c = mats["close"]
    m1o = mats.get("open")
    univ = list(m1c.columns)
    m1c_path = out / "m1c.parquet"
    m1c.to_parquet(m1c_path)
    days, d1 = dmod.day_index(m1c)
    all_pairs = list(combinations(univ, 2))
    say(f"universe {len(univ)} | {len(days)} phien | {len(all_pairs):,} cap")

    starts = smod.schedule_weeks(days, cfg["weeks"])
    if args.max_weeks:
        starts = starts[:args.max_weeks]
    say(f"{len(starts)} tuan trade: {days[starts[0]]} -> {days[starts[-1]]}")

    simc = cfg["sim"]
    ctlc = cfg["control"]
    min_form = cfg.get("min_formation_obs", 100)
    joint_open = m1o is not None
    rng = np.random.default_rng(ctlc["seed"])
    td = cfg["weeks"]["trade_days"]
    rows = []

    with ProcessPoolExecutor(max_workers=max(2, (os.cpu_count() or 8) - 2),
                             initializer=smod._init, initargs=(str(m1c_path),)) as ex:
        for s in starts:
            tdays = days[s:s + td]
            tm = np.isin(d1, tdays)
            first = np.where(tm)[0][0]
            t1c = m1c[tm]
            t1o = m1o[tm] if joint_open else None

            ctl = smod.draw_control(rng, m1c, all_pairs, first,
                                    ctlc["n"], ctlc["beta_bars"])

            for vname, fbars in cfg["variants"]:
                i0 = max(0, first - fbars)
                sel = smod.johansen_select(ex, all_pairs, i0, first, cfg.get("k_ar", 12))
                f1 = m1c.iloc[i0:first]
                for group, tag in [(sel, "sel"), (ctl, "ctl")]:
                    for ta, tb, beta in group:
                        spf = (f1[ta] - beta * f1[tb]).dropna().values
                        if len(spf) < min_form:
                            continue
                        spc = (t1c[ta] - beta * t1c[tb]).ffill().bfill().values
                        if joint_open:
                            spo = (t1o[ta] - beta * t1o[tb]).ffill().bfill().values
                            if not (np.all(np.isfinite(spc)) and np.all(np.isfinite(spo))):
                                continue
                        else:
                            spo = None
                            if not np.all(np.isfinite(spc)):
                                continue
                        z = (spc - spf.mean()) / spf.std()
                        cost = dmod.pair_cost_bps(half, ta, tb, beta)
                        for mname, src, lag in cfg["modes"]:
                            fill = spc if src == "close" else spo
                            for et, xt, side, bps, forced in simulate_week(
                                    z, fill, lag, simc["z_entry"],
                                    simc["convention"], simc.get("max_shift", 3)):
                                rows.append((vname, mname, tag, str(tdays[0]),
                                             ta, tb, beta, et, xt, side, bps,
                                             cost, forced))
            say(f"[tuan bat dau {tdays[0]}] xong ({time.time() - t0:.0f}s)")

    tr = pd.DataFrame(rows, columns=["variant", "mode", "group", "week", "ta", "tb",
                                     "beta", "entry_t", "exit_t", "side", "bps",
                                     "cost", "forced"])
    tr.to_parquet(out / "trades.parquet")
    with open(out / "config.json", "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, default=str)

    # --- bang pooled kieu legacy (doi chieu report cu) ---
    say("")
    say(f"========== {cfg['name']}{args.tag} ==========")
    say(f"{'F':>5} {'mode':>11} {'N':>7} {'gop bp':>12} {'t':>6} {'ctl':>7} {'t_diff':>7} {'NET':>7}")
    summary_rows = []
    verdicts = []
    for vname, _ in cfg["variants"]:
        for mname, _, _ in cfg["modes"]:
            gsel = tr[(tr["variant"] == vname) & (tr["mode"] == mname) & (tr["group"] == "sel")]
            gctl = tr[(tr["variant"] == vname) & (tr["mode"] == mname) & (tr["group"] == "ctl")]
            n, mg, sg, tstat = st.pooled(gsel["bps"].values)
            if n < 10:
                say(f"{vname:>5} {mname:>11} khong du trade")
                continue
            nc, mc, sc, _ = st.pooled(gctl["bps"].values)
            tdiff = st.t_diff_pooled(mg, sg, mc, sc) if nc >= 10 else np.nan
            costm = np.nanmedian(gsel["cost"].values)
            say(f"{vname:>5} {mname:>11} {n:>7,} {mg:>+9.2f}±{sg:.2f} {tstat:>+6.1f} "
                f"{mc:>+7.2f} {tdiff:>+7.1f} {mg - costm:>+7.1f}")
            # thuoc do mac dinh: t gom theo tuan
            wm, wse, wt, nw = st.weekly_t(st.weekly_means(gsel).values)
            dm, dse, dt, ndw = st.weekly_diff_t(gsel, gctl) if nc >= 10 else (np.nan,) * 4
            summary_rows.append(dict(variant=vname, mode=mname, n=n, gross=mg, se=sg,
                                     t_trade=tstat, ctl=mc, t_diff=tdiff,
                                     net=mg - costm, weekly_mean=wm, weekly_se=wse,
                                     weekly_t=wt, n_weeks=nw,
                                     weekly_diff=dm, weekly_diff_t=dt))
            key = (vname, mname)
            if key in accept or key in bonus:
                target = accept.get(key) or bonus.get(key)
                ok = st.check_target(mg, sg, n, target)
                kind = "NGHIEM THU" if key in accept else "bonus"
                verdicts.append((kind, vname, mname, ok, (mg, sg, n), target))

    # --- thuoc do mac dinh: t gom theo tuan (lag1_close) ---
    say("")
    say("----- T GOM THEO TUAN (thuoc do mac dinh; per-trade t o tren chi de doi chieu) -----")
    for r in summary_rows:
        if r["mode"] != "lag1_close":
            continue
        say(f"{r['variant']:>5}: weekly mean {r['weekly_mean']:+.2f}±{r['weekly_se']:.2f} bp "
            f"(t={r['weekly_t']:+.1f}, {r['n_weeks']} tuan) | "
            f"hieu-so-control {r['weekly_diff']:+.2f} (t={r['weekly_diff_t']:+.1f})")

    # --- bang theo tuan (lag1_close) de soi tuan xau ---
    say("")
    say("----- MEAN BPS THEO TUAN (lag1_close, sel) -----")
    for vname, _ in cfg["variants"]:
        gsel = tr[(tr["variant"] == vname) & (tr["mode"] == "lag1_close") & (tr["group"] == "sel")]
        if len(gsel) == 0:
            continue
        wk = gsel.groupby("week")["bps"].agg(["mean", "size"])
        line = " | ".join(f"{w}: {m:+.0f} (n={int(sz)})" for w, (m, sz) in wk.iterrows())
        say(f"[{vname}] {line}")

    # --- phan quyet nghiem thu ---
    if verdicts:
        say("")
        say("----- CUA NGHIEM THU (N khop tuyet doi; mean/se khop toi ±0.01) -----")
        all_ok = True
        for kind, vname, mname, ok, got, tgt in verdicts:
            gm, gs, gn = got
            tm_, ts_, tn_ = tgt
            mark = "KHOP" if ok else "LECH  <- DUNG LAI TIM BUG"
            if kind == "NGHIEM THU" and not ok:
                all_ok = False
            say(f"[{kind}] {vname}/{mname}: engine {gm:+.2f}+-{gs:.2f} N={gn:,} "
                f"| dich {tm_:+.2f}+-{ts_:.2f} N={tn_:,} -> {mark}")
        say("")
        say("KET LUAN NGHIEM THU: " + ("DAT — engine tai lap dung so cu."
                                       if all_ok else "KHONG DAT — co bug, dung moi viec khac."))

    pd.DataFrame(summary_rows).to_csv(out / "summary.csv", index=False)
    say(f"tong: {time.time() - t0:.0f}s")
    (out / "report.txt").write_text("\n".join(rep), encoding="utf-8")


if __name__ == "__main__":
    main()
