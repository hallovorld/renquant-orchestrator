# Workstream: model edge (the binding problem)

STATUS:   active — this is the one thing between us and live buys.
GOAL:     a PatchTST model with **positive real cross-sectional IC** that passes the WF gate.
NEXT:     PRUNING LINE CLOSED (2-seed set falsifies a stable edge). Escalate to the next lever —
          feature engineering / architecture / regime handling — AND separately diagnose the
          BULL_CALM monotonicity wall (a 2nd independent blocker). Pending operator priority
          (parallel-work discussion PR #160). Promotion needs operator sign-off; never bypass.
EVIDENCE: 2-seed set complete (final doc 2026-06-21): all runs FAIL the gate. Exp B aligned_real_ic
          FLIPS SIGN between seeds — seed44 +0.0079, seed45 −0.0085 — so the seed44 near-miss
          (placebo +0.0059) was seed noise, not a stable edge. BULL_CALM monotonicity fails in ALL
          runs independent of placebo. `[VERIFIED — /tmp/exp_{A,B,B45}_gate.log, ephemeral]`
CONSTRAINT: PatchTST is the chosen model (LONG #4); XGB is vetoed as a pitch (LONG #3).
