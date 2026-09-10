# Tai lap run #10 (Week 6/research_1min/confirmation_test.py)
# Data H2-only, tuan anchor tai index 10 cua danh sach ngay H2, may sim legacy10.
# Script cu chay them variant 0.5d (195 bar) — bo o day vi khong la so dich;
# khong anh huong: control boc 1 lan/tuan truoc vong variant, cac variant doc lap.
CONFIG = dict(
    name="repro_run10",
    n_univ=100,
    data=dict(start="2024-07-01", end="2024-12-31", columns=["close", "open"]),
    weeks=dict(trade_days=5, anchor_mode="index", anchor_index=10),
    variants=[["1d", 390], ["2d", 780]],
    modes=[["lag1_close", "close", 1], ["lag2_close", "close", 2],
           ["lag3_close", "close", 3], ["lag1_open", "open", 1]],
    sim=dict(convention="legacy10", z_entry=2.0, max_shift=3),
    control=dict(n=150, seed=42, beta_bars=780),
    min_formation_obs=100,
    k_ar=12,
)

# So dich tu results/confirmation_h2_2024/report.txt — (mean, se, N)
ACCEPT = {
    ("2d", "lag1_close"): (10.80, 1.38, 59455),
    ("1d", "lag1_close"): (7.99, 1.05, 95799),
}
BONUS = {
    ("2d", "lag2_close"): (10.19, 1.39, 59455),
    ("2d", "lag3_close"): (9.44, 1.38, 59455),
    ("2d", "lag1_open"): (10.26, 1.39, 59455),
    ("1d", "lag2_close"): (6.65, 1.05, 95799),
    ("1d", "lag3_close"): (5.87, 1.06, 95799),
    ("1d", "lag1_open"): (7.92, 1.06, 95799),
}
