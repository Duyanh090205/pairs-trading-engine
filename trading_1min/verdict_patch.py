"""
verdict_patch.py — BAN VA DO LUONG: doc 20 cell, ap luat PRE-COMMIT, in phan quyet.

LUAT DA KHOA TRUOC KHI CHAY (2026-07-15, khong sua sau khi thay so):
  Tin hieu "CON SONG" neu — xet RIENG tung cua so hoc {390, 780}, va phai dat
  tren CA HAI ky {H2/2024, H1/2024}:
    (a) median cua 5 moc chia: weekly-clustered t (hieu sel - control) >= 2, VA
    (b) hieu sel - control DUONG o >= 4/5 moc chia.
  Tin hieu song neu IT NHAT MOT cua so dat; ca hai truot -> ha cap
  "CHUA CHUNG MINH", dung xay them, bao cao trung thuc.

Sanity check kem theo: cell H2/offset0/780 phai tai lap run #11 (+5.98, N=64,837).
Chay: python -m trading_1min.verdict_patch
"""
import numpy as np
import pandas as pd

from trading_1min.engine import data as dmod
from trading_1min.engine import stats as st

RES = dmod.ROOT / "trading_1min" / "results"
PERIODS = [("patch_h2_2024", "H2/2024"), ("patch_h1_2024", "H1/2024 (moi tinh)")]
OFFSETS = [0, 1, 2, 3, 4]
VARIANTS = ["390", "780"]

rep = []


def say(s):
    print(s, flush=True)
    rep.append(s)


rows = []
for pname, plabel in PERIODS:
    for o in OFFSETS:
        f = RES / f"{pname}_o{o}" / "trades.parquet"
        tr = pd.read_parquet(f)
        for v in VARIANTS:
            sel = tr[(tr["variant"] == v) & (tr["mode"] == "lag1_close") & (tr["group"] == "sel")]
            ctl = tr[(tr["variant"] == v) & (tr["mode"] == "lag1_close") & (tr["group"] == "ctl")]
            n, mg, sg, _ = st.pooled(sel["bps"].values)
            wm, wse, wt, nw = st.weekly_t(st.weekly_means(sel).values)
            dm, dse, dt, ndw = st.weekly_diff_t(sel, ctl)
            rows.append(dict(period=pname, plabel=plabel, offset=o, variant=v,
                             n_trades=n, gross=mg, se=sg, weekly_mean=wm,
                             weekly_t=wt, n_weeks=nw, diff_mean=dm, diff_t=dt))
df = pd.DataFrame(rows)
df.to_csv(RES / "verdict_patch_cells.csv", index=False)

say("=" * 78)
say("BAN VA DO LUONG — 2 cua so x 2 ky x 5 moc chia | thuoc do: t gom theo tuan")
say("=" * 78)
for pname, plabel in PERIODS:
    say("")
    say(f"--- {plabel} ---")
    say(f"{'F':>4} {'moc':>4} {'N_lenh':>8} {'gop bp':>8} {'tuan':>5} "
        f"{'mean/tuan':>10} {'t_tuan':>7} {'hieu-ctl':>9} {'t_hieu':>7}")
    for v in VARIANTS:
        for o in OFFSETS:
            r = df[(df.period == pname) & (df.variant == v) & (df.offset == o)].iloc[0]
            say(f"{v:>4} {o:>4} {r.n_trades:>8,} {r.gross:>+8.2f} {r.n_weeks:>5} "
                f"{r.weekly_mean:>+10.2f} {r.weekly_t:>+7.2f} {r.diff_mean:>+9.2f} "
                f"{r.diff_t:>+7.2f}")

# sanity check: H2 offset0 780 = run #11
say("")
r11 = df[(df.period == "patch_h2_2024") & (df.offset == 0) & (df.variant == "780")].iloc[0]
ok11 = (r11.n_trades == 64837) and abs(r11.gross - 5.98) <= 0.0051
say(f"Sanity (cell H2/o0/780 vs run #11): engine {r11.gross:+.2f} N={r11.n_trades:,} "
    f"| dich +5.98 N=64,837 -> {'KHOP' if ok11 else 'LECH — dung lai tim bug!'}")

say("")
say("=" * 78)
say("AP LUAT PRE-COMMIT (median t_hieu >= 2  VA  hieu duong >= 4/5 moc, CA HAI ky)")
say("=" * 78)
alive_any = False
for v in VARIANTS:
    ok_both = True
    detail = []
    for pname, plabel in PERIODS:
        sub = df[(df.variant == v) & (df.period == pname)]
        med_t = sub["diff_t"].median()
        n_pos = int((sub["diff_mean"] > 0).sum())
        ok = (med_t >= 2.0) and (n_pos >= 4)
        ok_both &= ok
        detail.append(f"  {plabel}: median t_hieu = {med_t:+.2f} (can >=2) | "
                      f"hieu duong {n_pos}/5 moc (can >=4) -> {'DAT' if ok else 'TRUOT'}")
    say(f"[cua so {v} bar]")
    for d in detail:
        say(d)
    say(f"  => cua so {v}: {'SONG' if ok_both else 'TRUOT'}")
    alive_any |= ok_both

say("")
say("*" * 78)
if alive_any:
    say("PHAN QUYET: TIN HIEU CON SONG — it nhat mot cua so dat luat tren ca hai ky.")
else:
    say("PHAN QUYET: TIN HIEU HA CAP VE 'CHUA CHUNG MINH' — dung xay them,")
    say("bao cao trung thuc. (Luat da khoa truoc khi chay, khong thuong luong lai.)")
say("*" * 78)
say("")
say("Ghi chu flag: ky H1/2024 dung vai phien cuoi 12/2023 lam runway formation")
say("(chi Johansen + mean/std; khong do lenh nao tren 2023).")

(RES / "verdict_patch_report.txt").write_text("\n".join(rep), encoding="utf-8")
