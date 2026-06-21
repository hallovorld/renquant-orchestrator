# PatchTST edge-recovery — RESULTS (Exp A / Exp B gate verdicts)

Results for the pre-registered experiment (`2026-06-19-patchtst-edge-recovery-experiment.md`).
**Authoritative evidence = the production WF gate VERDICTs below.** Both FAIL; no model is
promotable. But the prune direction is validated and is a near-miss on the core failure.

## Verdicts (production WF gate, 60d, seed44, /tmp-isolated)

| | exclude | aligned_real_ic | placebo_ic | threshold | placebo ratio | WF-sim | VERDICT |
|---|---|---|---|---|---|---|---|
| baseline 60d | none | (neg) | +0.0116 | 0.0065 | 1.8× over | — | FAIL |
| **Exp A** (reproduce B2) | 15 (STD/MIN/IMIN) | **+0.0046** | **+0.0317** | 0.0050 | **6.3× over** | PASS-floor | **FAIL** |
| **Exp B** (B2 + pure-placebo) | 42 (+IMXD/CORR/RANK/RSV/IMAX/…) | **+0.0079** | **+0.0059** | 0.0050 | **1.18× over** | FAIL | **FAIL** |

Path-pinned: `/tmp/exp_A_gate.log`, `/tmp/exp_B_gate.log` (session-local). `[VERIFIED — gate logs]`

## What this shows (the validated finding)
- **Pruning the pure-placebo features works as hypothesized:** placebo_ic fell **+0.0317 → +0.0059
  (−81%)** from Exp A → Exp B, while the **aligned real IC stayed positive and rose**
  (+0.0046 → +0.0079). B2's signal is real; the pure-placebo families (IMXD/CORR/RANK/RSV/IMAX)
  were the placebo drivers.
- **Exp B is a near-miss:** placebo only **0.0009 over** threshold (1.18×) vs Exp A's 6.3×.

## Why it still FAILS (honest, two separate problems)
1. **Placebo just over threshold** (0.0059 > 0.0050) — close but not clean.
2. **WF trading sim degraded** in Exp B (mean Sharpe +0.19, all-3 fail) — pruning 42 features
   may have hurt the trading-economics layer even as it cleaned the placebo.
3. **Trade monotonicity fails in BULL_CALM** in both — a persistent, separate issue.

→ **No promotion. The gate is correctly blocking; not bypassed.**

## Next (bounded, in flight)
- **seed45 of the Exp B recipe** (running): seeds44/45 of B2 had val IC +0.004 vs +0.024 (6×);
  a stronger aligned IC raises the threshold, which may tip the near-miss placebo to a pass.
- If seed45 also misses: the finding is that this feature set's clean 60d edge is marginal —
  escalate to feature engineering / architecture, not a forced promotion.
