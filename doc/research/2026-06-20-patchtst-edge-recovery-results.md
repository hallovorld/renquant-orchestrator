# PatchTST edge-recovery — INTERIM execution update (seed44; seed45 pending)

> **SUPERSEDED by `2026-06-21-patchtst-edge-recovery-final.md`** (2-seed set complete).
> seed45 flipped the aligned IC sign (+0.0079 → −0.0085), so the seed44 near-miss recorded
> below was seed noise, not a stable edge. Kept for history; read the final doc.

> **This is an INTERIM update, NOT a final results verdict.** The pre-registration
> (`2026-06-19-...-experiment.md`) commits to **≥2 seeds per arm**; this records the
> **seed44** runs only — **seed45 (the prereg's 2nd seed) is still running.** The final
> verdict PR lands when the full seed set is in. Treat everything below as single-seed,
> bounded-observational evidence, not an established conclusion.

Interim record for the pre-registered experiment (`2026-06-19-patchtst-edge-recovery-experiment.md`).
**Authoritative evidence = the production WF gate VERDICTs below (seed44).** Both seed44 arms
FAIL; no model is promotable. Exp B is a near-miss on the placebo — a direction to be confirmed
or falsified once seed45 (and any further seeds) complete.

## Verdicts (production WF gate, 60d, seed44, /tmp-isolated)

| | exclude | aligned_real_ic | placebo_ic | threshold | placebo ratio | WF-sim | VERDICT |
|---|---|---|---|---|---|---|---|
| baseline 60d | none | (neg) | +0.0116 | 0.0065 | 1.8× over | — | FAIL |
| **Exp A** (reproduce B2) | 15 (STD/MIN/IMIN) | **+0.0046** | **+0.0317** | 0.0050 | **6.3× over** | PASS-floor | **FAIL** |
| **Exp B** (B2 + pure-placebo) | 42 (+IMXD/CORR/RANK/RSV/IMAX/…) | **+0.0079** | **+0.0059** | 0.0050 | **1.18× over** | FAIL | **FAIL** |

Path-pinned: `/tmp/exp_A_gate.log`, `/tmp/exp_B_gate.log` (session-local). `[VERIFIED — gate logs]`

## What this shows (bounded observation — NOT established causation)
- **On these two single-seed (seed44) runs:** adding the pure-placebo families to the prune was
  *associated with* a large drop in placebo_ic (**+0.0317 → +0.0059, −81%**, Exp A → Exp B),
  while aligned_real_ic stayed positive (+0.0046 → +0.0079).
- **This does NOT yet establish** that those families are *the* placebo drivers in a stable
  sense, nor that B2's signal is "real" in a decision-grade sense — because **both runs still
  FAIL the gate, the result is single-seed, the WF trading-sim degraded in Exp B, and the
  BULL_CALM monotonicity failure persists.** The causal attribution is **provisional**, pending
  more seeds and a gate PASS.
- **Exp B is a near-miss on placebo:** only **0.0009 over** threshold (1.18×) vs Exp A's 6.3×.

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
