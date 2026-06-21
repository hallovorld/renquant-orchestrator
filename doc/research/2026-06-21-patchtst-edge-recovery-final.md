# PatchTST edge-recovery — FINAL verdict (2-seed set complete)

Completes the pre-registered experiment (`2026-06-19-...-experiment.md`, ≥2 seeds/arm).
Supersedes the interim seed44 write-up (`2026-06-20-...-results.md`).
**Authoritative evidence = the production WF gate VERDICTs.** **All runs FAIL; no promotable
model. The prune direction does not produce a stable edge — falsified by the 2-seed set.**

## Verdicts (production WF gate, 60d)

| arm | seed | aligned_real_ic | placebo_ic | threshold | monotonicity | VERDICT |
|---|---|---|---|---|---|---|
| Exp A (prune STD/MIN/IMIN) | 44 | +0.0046 | +0.0317 | 0.0050 | FAIL BULL_CALM | FAIL |
| Exp B (+ pure-placebo) | 44 | **+0.0079** | +0.0059 | 0.0050 | FAIL BULL_CALM | FAIL |
| Exp B (+ pure-placebo) | **45** | **−0.0085** | −0.0100 | 0.0050 | FAIL BULL_CALM | FAIL |

`[VERIFIED — /tmp/exp_A_gate.log, /tmp/exp_B_gate.log, /tmp/exp_B45_gate.log, ephemeral]`

## The decisive finding (bounded)
- **The aligned real IC is NOT seed-stable: it flips sign between seeds** for the same Exp B
  recipe — seed44 **+0.0079**, seed45 **−0.0085**. The seed44 "near-miss" on placebo was
  therefore **within seed noise, not evidence of a stable edge.** This is exactly the failure
  the prereg's ≥2-seed requirement existed to catch.
- **On this evidence, pruning (Exp A/B recipe) does not yield a gate-passing 60d model.** The
  earlier single-seed "−81% placebo / positive aligned IC" observation does **not** generalize
  across seeds.

## A second, independent blocker
- **`BULL_CALM` trade-monotonicity fails in ALL runs** (incl. seed45) — independent of placebo.
  Even a placebo-clean model would still be blocked here. (Tracked separately — see the
  parallel-work proposal / its follow-up.)

## Decision
- **Pruning line: CLOSED.** Not "tune a bit more" — the 2-seed set falsifies a stable edge from
  this feature set + prune. No promotion; the gate is correctly blocking (not bypassed).
- **Escalate** to the next lever (feature engineering / architecture / regime handling), and
  separately diagnose the BULL_CALM monotonicity wall. Both are now the model-edge workstream's
  direction — pending operator priority (parallel-work discussion PR).
