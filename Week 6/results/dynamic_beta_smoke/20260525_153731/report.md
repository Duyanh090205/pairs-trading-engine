# Dynamic-β Smoke Test — Decision Report

**Run dir**: `20260525_153731`

Decision rules and design pre-registered in [`README.md`](../../scripts/research/dynamic_beta/README.md). This report applies them to the actual smoke output.

## Sanity invariants

✅ All I1-I5 sanity invariants pass — comparison is apples-to-apples.

## Per-fold per-arm Sharpe

|                 |   A0_static_v4 |   A1_short_ols60 |   B1_kalman_hl10 |   B1c_clamp_gate |   B1g_all_guards |
|:----------------|---------------:|-----------------:|-----------------:|-----------------:|-----------------:|
| (4, '2023-04')  |          5.959 |            3.381 |            6.37  |            6.592 |            6.592 |
| (5, '2023-05')  |         -9.196 |           -8.892 |           -9.247 |           -9.235 |           -9.26  |
| (18, '2024-06') |         -2.761 |           -2.841 |            3.86  |            3.86  |            3.86  |
| (22, '2024-10') |         -5.366 |           -4.599 |           -1.797 |           -1.797 |           -1.805 |
| (28, '2025-04') |          4.525 |            3.055 |            1.198 |            1.237 |            1.237 |
| (32, '2025-08') |         -2.807 |           -2.277 |            1.865 |            1.865 |            1.83  |

### Per-fold per-arm return (%)

|                 |   A0_static_v4 |   A1_short_ols60 |   B1_kalman_hl10 |   B1c_clamp_gate |   B1g_all_guards |
|:----------------|---------------:|-----------------:|-----------------:|-----------------:|-----------------:|
| (4, '2023-04')  |           2.26 |             1.68 |             0.59 |             0.57 |             0.57 |
| (5, '2023-05')  |         -22.1  |           -14.79 |           -16.13 |           -15.99 |           -15.69 |
| (18, '2024-06') |          -1.34 |            -1.07 |             0.45 |             0.45 |             0.45 |
| (22, '2024-10') |          -3.22 |            -2.6  |            -0.65 |            -0.65 |            -0.65 |
| (28, '2025-04') |           3.41 |             2.17 |             0.36 |             0.4  |             0.4  |
| (32, '2025-08') |          -5.38 |            -2.81 |             0.74 |             0.74 |             0.73 |

### Per-fold per-arm n_trades

|                 |   A0_static_v4 |   A1_short_ols60 |   B1_kalman_hl10 |   B1c_clamp_gate |   B1g_all_guards |
|:----------------|---------------:|-----------------:|-----------------:|-----------------:|-----------------:|
| (4, '2023-04')  |             70 |               78 |               35 |               35 |               35 |
| (5, '2023-05')  |            107 |              108 |              105 |              106 |              106 |
| (18, '2024-06') |            113 |              139 |               61 |               61 |               61 |
| (22, '2024-10') |            152 |              164 |               91 |               91 |               91 |
| (28, '2025-04') |             87 |              101 |               56 |               58 |               58 |
| (32, '2025-08') |            144 |              166 |               99 |               99 |               99 |

## Pre-registered decisions

### A1_short_ols60 vs A0_static_v4

Per-fold Sharpe diff: fold (4, '2023-04'): -2.578, fold (5, '2023-05'): +0.304, fold (18, '2024-06'): -0.080, fold (22, '2024-10'): +0.767, fold (28, '2025-04'): -1.469, fold (32, '2025-08'): +0.529

| Criterion | Value | Threshold | Pass |
|---|---|---|---|
| **P1** Median lift | +0.112 | ≥ +0.2 | ❌ |
| **P2** Wins | 3/6 | ≥ 4/6 | ❌ |
| **S1** Bootstrap CI (95%) | [-0.756, +0.390] | excludes 0 | — |
| **S2** Sign test p | 0.656 | ≤ 0.2 | — |

**Verdict: no smoke-win** — pre-registered primary criteria not both satisfied.

### B1_kalman_hl10 vs A0_static_v4

Per-fold Sharpe diff: fold (4, '2023-04'): +0.411, fold (5, '2023-05'): -0.051, fold (18, '2024-06'): +6.621, fold (22, '2024-10'): +3.569, fold (28, '2025-04'): -3.327, fold (32, '2025-08'): +4.672

| Criterion | Value | Threshold | Pass |
|---|---|---|---|
| **P1** Median lift | +1.990 | ≥ +0.2 | ✅ |
| **P2** Wins | 4/6 | ≥ 4/6 | ✅ |
| **S1** Bootstrap CI (95%) | [-1.222, +3.507] | excludes 0 | — |
| **S2** Sign test p | 0.344 | ≤ 0.2 | — |

**Verdict: SMOKE-WIN** — both P1 and P2 pass. Proceed to full 39-fold test with guardrails (clamp + innovation gate).

### B1c_clamp_gate vs A0_static_v4

Per-fold Sharpe diff: fold (4, '2023-04'): +0.633, fold (5, '2023-05'): -0.039, fold (18, '2024-06'): +6.621, fold (22, '2024-10'): +3.569, fold (28, '2025-04'): -3.287, fold (32, '2025-08'): +4.672

| Criterion | Value | Threshold | Pass |
|---|---|---|---|
| **P1** Median lift | +2.101 | ≥ +0.2 | ✅ |
| **P2** Wins | 4/6 | ≥ 4/6 | ✅ |
| **S1** Bootstrap CI (95%) | [-1.200, +3.501] | excludes 0 | — |
| **S2** Sign test p | 0.344 | ≤ 0.2 | — |

**Verdict: SMOKE-WIN** — both P1 and P2 pass. Proceed to full 39-fold test with guardrails (clamp + innovation gate).

### B1g_all_guards vs A0_static_v4

Per-fold Sharpe diff: fold (4, '2023-04'): +0.633, fold (5, '2023-05'): -0.064, fold (18, '2024-06'): +6.621, fold (22, '2024-10'): +3.561, fold (28, '2025-04'): -3.287, fold (32, '2025-08'): +4.637

| Criterion | Value | Threshold | Pass |
|---|---|---|---|
| **P1** Median lift | +2.097 | ≥ +0.2 | ✅ |
| **P2** Wins | 4/6 | ≥ 4/6 | ✅ |
| **S1** Bootstrap CI (95%) | [-1.192, +3.483] | excludes 0 | — |
| **S2** Sign test p | 0.344 | ≤ 0.2 | — |

**Verdict: SMOKE-WIN** — both P1 and P2 pass. Proceed to full 39-fold test with guardrails (clamp + innovation gate).

## Final verdict

**Smoke-win**: B1_kalman_hl10, B1c_clamp_gate, B1g_all_guards. Proceed to full test.
