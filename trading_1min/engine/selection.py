"""
selection.py — chon cap moi ky (Johansen cua so ngan) + control boc tham + lich tuan.

Quy uoc ke thua tu script cu — KHONG doi khi tai lap:
- Johansen: det_order=0, k_ar_diff=12; giu cap trace > cv95 va 0 < beta <= 5
  (beta = -v[1]/v[0] tu eigenvector dau); yeu cau coverage >= 80% cua so
- control: boc 150 cap ngau nhien MOI TUAN (dung 1 lan goi rng.choice / tuan,
  theo thu tu tuan — de tai lap chuoi ngau nhien cua script cu, seed 42);
  beta control = |he so hoi quy| tren diff 780 bar cuoi (quirk lat dau giu nguyen)
"""
import numpy as np
import pandas as pd

_M = None
_C = None


def _init(path):
    global _M, _C
    df = pd.read_parquet(path)
    _C = {c: i for i, c in enumerate(df.columns)}
    _M = df.to_numpy()


def _jo_chunk(args):
    from statsmodels.tsa.vector_ar.vecm import coint_johansen
    pairs, i0, i1, k_ar = args
    out = []
    for ta, tb in pairs:
        a = _M[i0:i1, _C[ta]]
        b = _M[i0:i1, _C[tb]]
        m = np.isfinite(a) & np.isfinite(b)
        if m.sum() < 0.8 * (i1 - i0):
            continue
        try:
            r = coint_johansen(np.column_stack([a[m], b[m]]), det_order=0, k_ar_diff=k_ar)
            if r.lr1[0] > r.cvt[0, 1]:
                v = r.evec[:, 0]
                if abs(v[0]) > 1e-12:
                    beta = -v[1] / v[0]
                    if 0 < beta <= 5:
                        out.append((ta, tb, float(beta)))
        except Exception:
            pass
    return out


def johansen_select(ex, all_pairs, i0, i1, k_ar=12, chunk=400):
    """Quet Johansen toan bo cap tren cua so [i0, i1) bang pool co san."""
    chunks = [(all_pairs[i:i + chunk], i0, i1, k_ar) for i in range(0, len(all_pairs), chunk)]
    sel = []
    for r in ex.map(_jo_chunk, chunks, chunksize=2):
        sel.extend(r)
    return sel


def draw_control(rng, m1, all_pairs, first, n_control=150, beta_bars=780, min_obs=100):
    """Control boc tham cho 1 tuan. PHAI goi dung 1 lan/tuan theo thu tu tuan."""
    fwin = m1.iloc[max(0, first - beta_bars):first]
    ctl_idx = rng.choice(len(all_pairs), n_control, replace=False)
    ctl = []
    for j in ctl_idx:
        ta, tb = all_pairs[j]
        va, vb = fwin[ta].diff().values, fwin[tb].diff().values
        mm = np.isfinite(va) & np.isfinite(vb)
        if mm.sum() < min_obs:
            continue
        b_ = np.polyfit(vb[mm], va[mm], 1)[0]
        if 0 < abs(b_) <= 5:
            ctl.append((ta, tb, float(abs(b_))))
    return ctl


def schedule_weeks(days, wcfg):
    """Danh sach chi so ngay bat dau tung tuan trade.

    anchor_mode:
      - "index":       bat dau tai days[anchor_index]           (kieu run #10)
      - "trade_start": ngay dau tien >= trade_start + offset_days (kieu run #11;
                       offset_days la nut van cua bai quet moc chia tuan)
    Chi lay tuan du trade_days ngay (tuan cut duoi bi bo — giu quy uoc cu).
    """
    td = wcfg["trade_days"]
    mode = wcfg["anchor_mode"]
    if mode == "index":
        i0 = wcfg["anchor_index"]
    elif mode == "trade_start":
        d0 = pd.Timestamp(wcfg["trade_start"]).date()
        cands = [d for d in days if d >= d0]
        i0 = days.index(cands[0]) + wcfg.get("offset_days", 0)
    else:
        raise ValueError(f"anchor_mode la? {mode}")
    return list(range(i0, len(days) - td + 1, td))
