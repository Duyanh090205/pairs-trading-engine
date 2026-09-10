"""
stats.py — thuoc do. MAC DINH cua engine la t-stat GOM THEO TUAN
(moi tuan 1 quan sat = mean bps cua tuan) — bai hoc qua min moc chia tuan:
lenh cung tuan chiu chung cu soc thi truong, t per-trade bi thoi phong.

Van in bang pooled per-trade (mean, se, t, t_diff, NET) de doi chieu voi
report cu — nhung dien giai chinh thuc phai dua vao weekly t.
"""
import numpy as np


def pooled(bps):
    """Bang kieu legacy: N, mean, se (ddof=0 nhu script cu), t."""
    g = np.asarray(bps, dtype=float)
    n = len(g)
    if n == 0:
        return 0, np.nan, np.nan, np.nan
    m = g.mean()
    se = g.std() / np.sqrt(n)
    return n, m, se, m / se if se > 0 else np.nan


def t_diff_pooled(m_sel, se_sel, m_ctl, se_ctl):
    return (m_sel - m_ctl) / np.sqrt(se_sel ** 2 + se_ctl ** 2)


def weekly_means(df):
    """df co cot week, bps -> Series mean bps theo tuan (moi tuan 1 quan sat)."""
    return df.groupby("week")["bps"].mean()


def weekly_t(means):
    """t gom theo tuan: mean cua cac weekly-mean / se (ddof=1). Tra (m, se, t, n_tuan)."""
    x = np.asarray(means, dtype=float)
    n = len(x)
    if n < 2:
        return np.nan, np.nan, np.nan, n
    m = x.mean()
    se = x.std(ddof=1) / np.sqrt(n)
    return m, se, m / se if se > 0 else np.nan, n


def weekly_diff_t(sel_df, ctl_df):
    """t gom theo tuan cua HIEU sel - control (chi tuan co ca hai nhom)."""
    ws = weekly_means(sel_df)
    wc = weekly_means(ctl_df)
    common = ws.index.intersection(wc.index)
    return weekly_t((ws.loc[common] - wc.loc[common]).values)


def check_target(m, se, n, target, tol=0.0051):
    """Nghiem thu: N khop tuyet doi, mean & se khop toi +-0.01 (do chinh xac report cu)."""
    tm, tse, tn = target
    ok = (n == tn) and (abs(m - tm) <= tol) and (abs(se - tse) <= tol)
    return ok
