"""
leadlag_scan.py — Tier-0 test HO 2 (lead-lag thang phut). Spec: leadlag_spec.md
(PRE-COMMIT — luat da khoa truoc khi chay, khong sua sau khi thay so).

Chay:  python -m trading_1min.research.leadlag_scan            # full H2/2024
       python -m trading_1min.research.leadlag_scan --smoke    # khoi-test
"""
import argparse
import time

import numpy as np
import pandas as pd

from trading_1min.engine import data as dmod

MAX_LAG = 30
FDR_Q = 0.05
N_NULL = 20
ECON_K0 = 2          # economic: huong tu lag 2 (tin hieu t, vao close t+1)
OOF_KEEP = 0.5       # |rho_oof| >= 50% |rho_fit|, cung dau
MIN_PAIRS = 10       # nguong "ho con ngo"

OUT = dmod.ROOT / "trading_1min" / "results" / "leadlag_scan"


def within_day_returns(m1c):
    """Return 1-phut trong-phien: diff log-close, bo return dau phien."""
    r = m1c.diff()
    day = np.array([d for d in m1c.index.date])
    new_day = np.r_[True, day[1:] != day[:-1]]
    r.values[new_day, :] = np.nan
    return r, day


def day_blocks(day):
    """Danh sach (start, end) tung phien theo vi tri hang."""
    idx = np.flatnonzero(np.r_[True, day[1:] != day[:-1]])
    return list(zip(idx, np.r_[idx[1:], len(day)]))


def residualize(r, beta):
    mkt = np.nanmean(r, axis=1)
    return r - np.outer(mkt, beta)


def fit_beta(r):
    """OLS beta tung ma so voi market (mean dong trong so), tren cua so fit."""
    mkt = np.nanmean(r, axis=1)
    ok_m = np.isfinite(mkt)
    betas = np.empty(r.shape[1])
    for j in range(r.shape[1]):
        ok = ok_m & np.isfinite(r[:, j])
        x, y = mkt[ok], r[ok, j]
        betas[j] = (x @ y) / (x @ x)
    return betas


def cross_corr_by_lag(resid, blocks, max_lag):
    """rho_k[k-1] = ma tran 100x100 corr(resid_i(t), resid_j(t+k)), gom trong-phien.

    Chuan hoa toan cua so (mean~0, std=1) roi gom tich cheo tung phien.
    Tra ve (rho list, n list).
    """
    x = resid.copy()
    mu = np.nanmean(x, axis=0)
    sd = np.nanstd(x, axis=0)
    x = (x - mu) / sd
    x = np.nan_to_num(x, nan=0.0)          # NaN (dau phien) -> 0: khong dong gop
    ncol = x.shape[1]
    rhos, ns = [], []
    for k in range(1, max_lag + 1):
        acc = np.zeros((ncol, ncol))
        n = 0
        for s, e in blocks:
            if e - s <= k:
                continue
            a = x[s:e - k]
            b = x[s + k:e]
            acc += a.T @ b
            n += e - s - k
        rhos.append(acc / n)
        ns.append(n)
    return rhos, ns


def bh_fdr(pvals, q):
    """Benjamini-Hochberg: tra ve nguong p va mask dau."""
    p = np.sort(pvals.ravel())
    m = len(p)
    thresh = q * np.arange(1, m + 1) / m
    ok = p <= thresh
    p_cut = p[ok].max() if ok.any() else -1.0
    return p_cut


def pvals_from_rho(rhos, ns):
    from scipy.stats import norm
    out = []
    for rho, n in zip(rhos, ns):
        z = np.abs(rho) * np.sqrt(n)
        out.append(2 * norm.sf(z))
    return out


def day_shuffle(resid, blocks, rng):
    """Null: hoan vi khoi-ngay DOC LAP tung ma (giu noi-ma, pha alignment cap)."""
    ncol = resid.shape[1]
    out = np.empty_like(resid)
    nb = len(blocks)
    lens = [e - s for s, e in blocks]
    # cac phien co do dai khac nhau -> hoan vi trong nhom cung do dai
    from collections import defaultdict
    groups = defaultdict(list)
    for i, L in enumerate(lens):
        groups[L].append(i)
    for j in range(ncol):
        perm = np.arange(nb)
        for L, idxs in groups.items():
            src = np.array(idxs)
            perm[src] = rng.permutation(src)
        for i, (s, e) in enumerate(blocks):
            ps, pe = blocks[perm[i]]
            out[s:e, j] = resid[ps:pe, j]
    return out


def scan_window(resid, blocks):
    rhos, ns = cross_corr_by_lag(resid, blocks, MAX_LAG)
    return rhos, ns


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
    say(f"===== LEAD-LAG SCAN ({tag}) — spec pre-commit leadlag_spec.md =====")

    univ, half = dmod.load_universe(100)
    m1c = dmod.load_log_prices(univ, "2024-07-01", "2024-12-31", ["close"])["close"]
    m1c = m1c.ffill()                      # ffill trong+xuyen phien; return dau phien bi bo rieng
    univ = list(m1c.columns)
    r_all, day = within_day_returns(m1c)
    days = sorted(set(day))
    say(f"universe {len(univ)} | {len(days)} phien | {len(r_all):,} bar")

    fit_end = pd.Timestamp("2024-09-30").date()
    if args.smoke:
        fit_days = [d for d in days if d <= fit_end][:10]
        oof_days = [d for d in days if d > fit_end][:10]
        n_null = 3
    else:
        fit_days = [d for d in days if d <= fit_end]
        oof_days = [d for d in days if d > fit_end]
        n_null = N_NULL

    m_fit = np.isin(day, fit_days)
    m_oof = np.isin(day, oof_days)
    r_fit, d_fit = r_all.values[m_fit], day[m_fit]
    r_oof, d_oof = r_all.values[m_oof], day[m_oof]
    say(f"fit {len(fit_days)} phien ({fit_days[0]}->{fit_days[-1]}) | "
        f"oof {len(oof_days)} phien ({oof_days[0]}->{oof_days[-1]})")

    # --- residual hoa (beta tu FIT, dung cho ca hai cua so) ---
    beta = fit_beta(r_fit)
    res_fit = residualize(r_fit, beta)
    res_oof = residualize(r_oof, beta)
    blocks_fit = day_blocks(d_fit)
    blocks_oof = day_blocks(d_oof)

    # sigma_B 1-phut (OOF, bp) cho economic stage
    sig_oof_bp = np.nanstd(res_oof, axis=0) * 1e4

    # --- detection (FIT) ---
    rhos_fit, ns_fit = scan_window(res_fit, blocks_fit)
    pv = pvals_from_rho(rhos_fit, ns_fit)
    # loai duong cheo (autocorrelation — khong phai lead-lag)
    for k in range(MAX_LAG):
        np.fill_diagonal(pv[k], 1.0)
        np.fill_diagonal(rhos_fit[k], 0.0)
    all_p = np.stack(pv)                                    # (30, 100, 100)
    p_cut = bh_fdr(all_p, FDR_Q)
    surv = all_p <= p_cut if p_cut > 0 else np.zeros_like(all_p, bool)
    say(f"[detection] n_fit/lag ~{ns_fit[0]:,} | p_cut BH = {p_cut:.2e} | "
        f"survivor (cap,lag): {int(surv.sum()):,} / {surv.size:,}")

    # --- null calibration ---
    rng = np.random.default_rng(42)
    null_counts = []
    for i in range(n_null):
        res_null = day_shuffle(res_fit, blocks_fit, rng)
        rhos_n, ns_n = scan_window(res_null, blocks_fit)
        pv_n = pvals_from_rho(rhos_n, ns_n)
        for k in range(MAX_LAG):
            np.fill_diagonal(pv_n[k], 1.0)
        all_pn = np.stack(pv_n)
        pc = bh_fdr(all_pn, FDR_Q)
        cnt = int((all_pn <= pc).sum()) if pc > 0 else 0
        null_counts.append(cnt)
        say(f"[null {i+1}/{n_null}] survivor gia: {cnt}")
    say(f"[null] survivor gia: median {int(np.median(null_counts))}, "
        f"max {max(null_counts)}")

    # --- confirmation (OOF) ---
    rhos_oof, ns_oof = scan_window(res_oof, blocks_oof)
    ks, ii, jj = np.where(surv)
    confirmed_pairs = {}
    n_conf = 0
    for k, i, j in zip(ks, ii, jj):
        rf = rhos_fit[k][i, j]
        ro = rhos_oof[k][i, j]
        if np.sign(ro) == np.sign(rf) and abs(ro) >= OOF_KEEP * abs(rf):
            n_conf += 1
            confirmed_pairs.setdefault((i, j), []).append((k + 1, rf, ro))
    say(f"[confirmation] (cap,lag) xac nhan OOF: {n_conf:,} | "
        f"cap co >=1 lag xac nhan: {len(confirmed_pairs):,}")

    # --- economic (OOF) ---
    rows = []
    cum_oof = np.zeros((len(univ), len(univ)))
    for k in range(ECON_K0 - 1, MAX_LAG):                   # k=2..30 (index 1..29)
        cum_oof += rhos_oof[k]
    for (i, j), lags in confirmed_pairs.items():
        edge = abs(cum_oof[i, j]) * sig_oof_bp[j]
        floor = 2 * half.get(univ[j], np.nan)
        rows.append(dict(leader=univ[i], follower=univ[j],
                         n_lags_conf=len(lags),
                         best_lag=int(min(l for l, _, _ in lags)),
                         rho_fit_best=max((abs(rf), rf) for _, rf, _ in lags)[1],
                         cum_rho_oof=cum_oof[i, j],
                         sigma_b_bp=sig_oof_bp[j],
                         edge_bp=edge, cost_floor_bp=floor,
                         passes=bool(edge > floor)))
    eco = pd.DataFrame(rows).sort_values("edge_bp", ascending=False) if rows else pd.DataFrame()
    n_pass = int(eco["passes"].sum()) if len(eco) else 0
    if len(eco):
        eco.to_csv(OUT / f"economic_{tag}.csv", index=False)
        say("[economic] top 10 theo EDGE:")
        for _, r in eco.head(10).iterrows():
            say(f"  {r.leader:>5} -> {r.follower:<5} lag{r.best_lag:>2} "
                f"cum_rho_oof {r.cum_rho_oof:+.4f} sigma {r.sigma_b_bp:.1f}bp "
                f"EDGE {r.edge_bp:.2f}bp vs san phi {r.cost_floor_bp:.2f}bp "
                f"{'PASS' if r.passes else 'fail'}")
    say(f"[economic] cap vuot san phi: {n_pass} (can >= {MIN_PAIRS})")

    # --- phan quyet (chi ap cho run full) ---
    say("")
    if args.smoke:
        say("KHOI-TEST xong — chua ap luat phan quyet.")
    else:
        alive = n_pass >= MIN_PAIRS
        say("*" * 70)
        if alive:
            say(f"HO 2 CON NGO: {n_pass} cap EDGE > san phi (nguong {MIN_PAIRS}).")
            say("Buoc ke (theo spec): kiem demean phut-trong-ngay + xac nhan 2022-23.")
        else:
            say(f"PHAN QUYET: DONG HO 2 VINH VIEN o cau truc phi hien tai "
                f"({n_pass} cap vuot san, can {MIN_PAIRS}).")
        say("*" * 70)

    np.save(OUT / f"rho_fit_{tag}.npy", np.stack(rhos_fit))
    np.save(OUT / f"rho_oof_{tag}.npy", np.stack(rhos_oof))
    say(f"tong: {time.time() - t0:.0f}s")
    (OUT / f"report_{tag}.txt").write_text("\n".join(rep), encoding="utf-8")


if __name__ == "__main__":
    main()
