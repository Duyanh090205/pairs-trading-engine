# BAN VA DO LUONG — ky H1/2024: KY MOI TINH (chua ai nhin, day la lan cham dau tien).
# May sim chuan v0, lag1_close. Quet moc chia tuan bang CLI: --offset 0..4.
# ⚠ FLAG (quyet dinh user 2026-07-15): data start 2023-12-20 la runway formation —
# cac tuan trade dau thang 1/2024 hoc Johansen + mean/std tren vai phien cuoi 12/2023.
# Chi formation dung 2023; KHONG co lenh nao duoc do tren 2023.
CONFIG = dict(
    name="patch_h1_2024",
    n_univ=100,
    data=dict(start="2023-12-20", end="2024-06-30", columns=["close"]),
    weeks=dict(trade_days=5, anchor_mode="trade_start", trade_start="2024-01-02",
               offset_days=0),
    variants=[["390", 390], ["780", 780]],
    modes=[["lag1_close", "close", 1]],
    sim=dict(convention="v0", z_entry=2.0),
    control=dict(n=150, seed=42, beta_bars=780),
    min_formation_obs=100,
    k_ar=12,
)
