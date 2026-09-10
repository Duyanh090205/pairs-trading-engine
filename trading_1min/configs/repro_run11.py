# Tai lap run #11 (Week 6/research_1min/window_opt_stage1.py)
# Data co runway tu 2024-01-02, tuan anchor tu ngay trade dau >= 2024-07-01,
# may sim legacy11 (= chuan v0 tai lag=1). Script cu chay 6 variant
# (390/585/780/1170/1560/adaptive) — chi tai lap 2 variant la so dich;
# khong anh huong: control boc 1 lan/tuan truoc vong variant.
CONFIG = dict(
    name="repro_run11",
    n_univ=100,
    data=dict(start="2024-01-02", end="2024-12-31", columns=["close"]),
    weeks=dict(trade_days=5, anchor_mode="trade_start", trade_start="2024-07-01",
               offset_days=0),
    variants=[["390", 390], ["780", 780]],
    modes=[["lag1_close", "close", 1]],
    sim=dict(convention="legacy11", z_entry=2.0),
    control=dict(n=150, seed=42, beta_bars=780),
    min_formation_obs=100,
    k_ar=12,
)

# So dich tu results/window_opt_stage1/report.txt — (mean, se, N)
ACCEPT = {
    ("780", "lag1_close"): (5.98, 1.72, 64837),
    ("390", "lag1_close"): (6.40, 1.07, 103305),
}
