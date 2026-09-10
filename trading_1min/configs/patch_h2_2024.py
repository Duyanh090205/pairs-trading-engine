# BAN VA DO LUONG — ky H2/2024 (ky da dung o run #10/#11).
# May sim chuan v0, lag1_close. Quet moc chia tuan bang CLI: --offset 0..4.
# Data start 2024-06-14 chi la runway formation (~10 phien truoc tuan trade dau);
# cell offset=0 / 780 bar PHAI tai lap dung run #11 (+5.98+-1.72, N=64,837) — sanity check.
CONFIG = dict(
    name="patch_h2_2024",
    n_univ=100,
    data=dict(start="2024-06-14", end="2024-12-31", columns=["close"]),
    weeks=dict(trade_days=5, anchor_mode="trade_start", trade_start="2024-07-01",
               offset_days=0),
    variants=[["390", 390], ["780", 780]],
    modes=[["lag1_close", "close", 1]],
    sim=dict(convention="v0", z_entry=2.0),
    control=dict(n=150, seed=42, beta_bars=780),
    min_formation_obs=100,
    k_ar=12,
)
