# Dynamic-β Smoke Test — Key Findings (honest narrative)

This is the human-readable companion to the auto-generated [report.md](report.md). Same numbers, but with context, caveats, and the methodology bug we caught.

## TL;DR

- **A1 (short-window OLS β refit)** → fails both pre-registered criteria. Static β estimation horizon is fine; shortening to 60d doesn't help.
- **B1 (Kalman within-window β, HL=10d, properly accounted)** → technically passes pre-registered P1 (median lift +1.99) and P2 (4/6 folds won). **But the secondary diagnostics fail**: 95% bootstrap CI [-1.22, +3.51] includes 0, sign test p=0.34 — with only 6 folds we cannot rule out that the lift is noise.
- **The decision per pre-registered rule**: proceed to full 39-fold test. **But interpret as "promising, not decisive"** — the wide CI and one strongly-hurting fold (28) say this could go either way at full scale.

## The methodology bug we caught (and fixed) before reporting

**First run, B1 showed Sharpe lift of +11.5 on 6/6 folds.** This was too good. Root cause: B1's P&L spread used time-varying Kalman β. Mathematically, when β changes from β[t-1] to β[t], the spread changes by `Δβ · b[t]` on top of the legitimate `Δa - β·Δb`. That extra term is **phantom P&L** — it books a profit/loss from re-labeling the hedge ratio, not from actual price movements on a held portfolio.

This is the canonical accounting bug in naive Kalman pairs trading implementations. The literature (Wang 2022, Palomar §15.6) is explicit: signal-β and portfolio-β must be separated.

**Fix**: in [arms.py](../../scripts/research/dynamic_beta/arms.py), B1 now uses:
- **Signal spread** `a[t] - α_prior[t] - β_prior[t]·b[t]` for Z-score and entry/exit decisions (Kalman captures regime info)
- **P&L spread** `a[t] - α_lock - β_lock·b[t]` with `(α_lock, β_lock)` frozen at entry of each trade (portfolio doesn't actually change β until rebalance/exit)

After the fix: B1 lift collapsed from +11.5 to +1.99 — believable. The 9.5-point gap was the phantom term.

**Defensibility lesson logged**: every smoke result that looks "too good" gets a P&L-accounting audit before publishing. Pre-registered S1 (bootstrap CI) was the right diagnostic — even the post-fix result has CI that crosses 0, so the test correctly says "this is fragile."

## Per-fold breakdown — where B1 wins, where it loses

| Fold | Month | A0 Sharpe | B1 Sharpe | Diff | A0 return | B1 return | A0 trades | B1 trades |
|---|---|---|---|---|---|---|---|---|
| 4 | 2023-04 | +5.96 | +6.37 | +0.41 | +2.26% | +0.59% | 70 | 35 |
| 5 | 2023-05 | -9.20 | -9.25 | -0.05 | -22.1% | -16.1% | 107 | 105 |
| 18 | 2024-06 | -2.76 | +3.86 | **+6.62** | -1.34% | +0.45% | 113 | 61 |
| 22 | 2024-10 | -5.37 | -1.80 | **+3.57** | -3.22% | -0.65% | 152 | 91 |
| 28 | 2025-04 | +4.52 | +1.20 | **-3.33** | +3.41% | +0.36% | 87 | 56 |
| 32 | 2025-08 | -2.81 | +1.86 | **+4.67** | -5.38% | +0.74% | 144 | 99 |

Pattern: **B1 trades less aggressively** (always fewer trades than A0) and **rescues bad folds** (18, 22, 32 — where A0 lost) **but hurts good folds** (28 — where A0 won big, B1 underperforms). On fold 5 it's a wash for both.

Interpretation: Kalman's updated β changes the *timing* of entries (fewer entries because signal-β shifts the Z-threshold-crossing points). In bad regimes this avoids whipsaw losses; in good regimes this misses winning entries.

This is consistent with the literature: **dynamic β acts as a noise filter**, beneficial when the static β is wrong but harmful when it's right.

## Why the bootstrap CI includes 0

With only 6 folds and high per-fold variance (+6.62 to -3.33 range), the standard error of the mean lift is large. Block bootstrap resamples folds with replacement → some bootstrap samples are dominated by fold 28 (where B1 hurts) and produce negative diffs.

**This is not a flaw in the test — it's the test correctly telling us that 6 folds is too few to call this.** Per the pre-registered design, P1+P2 → proceed to full test. Full 39-fold test with bootstrap CI is the decisive evaluation.

## β diagnostics

- A0 β: mean 1.18, range [0.00, 4.99] (V4 capped at 5)
- A1 β (60-day OLS): mean 0.73, range [0.00, 4.99]. Substantially LOWER than V4. Could reflect short-window OLS noise or genuine short-term β decline.
- B1 β posterior: range [-0.03, +5.12]. **Slightly breaches V4's β-cap (+5.12)** — but within smoke tolerance (I3 allows ±20). For full test, posterior clamp to [0.3·β_form, 3·β_form] is required (matches Wang 2022 robust KF practice).
- B1 within-window drift: max |Δβ| = 0.313 (median 0.017). So most pairs barely move β within 19-bar trading window. The performance lift comes from **a handful of pairs where β moves materially**, not uniform across pairs.

## What this tells us for the V5 pipeline / HMM design

1. **Static β estimation horizon (A1 result)**: short-window doesn't help. Keep V4's 12-month formation Johansen. Don't change discovery.

2. **Within-window dynamic β (B1 result)**: suggestive lift but not decisive. **For HMM design**: don't assume dynamic β is in. Design HMM as a regime gate (trade/no-trade) first; revisit regime-conditional β only if full B1 test passes.

3. **Trade count drops 30-50% under B1**: dynamic β filters trades. If you add HMM regime gate on top, trade count will drop further. Watch for capacity/diversification issues.

4. **Fold 28 hurt by -3.3 Sharpe**: this fold is 2025-04, a calm winning month for V4. Dynamic β can't help when static is already right — it can only add noise. If HMM identifies this as "static-good regime," β should stay static there.

## Next steps (if pursuing this further)

| Step | What | When |
|---|---|---|
| 1 | Run B1 (fixed) on all 39 folds | After HMM lands or in parallel |
| 2 | Add posterior β-clamp + innovation outlier gate (Wang 2022 style) | Before full test |
| 3 | β half-life sweep (HL ∈ {10, 20, 30, 60} days) | If full test confirms B1 lift |
| 4 | Combine with HMM regime gate — only run Kalman in "regime-shifting" state | After 1-3 |

## Reproducibility

- Run timestamp: `20260525_150838`
- Inputs locked: `per_pair.parquet`, `per_fold.parquet`, `daily_pnl.parquet`, `metadata.json`
- Git SHA logged in `run.log`
- All 3 arms ran on identical pair list per fold (I1 invariant verified)
