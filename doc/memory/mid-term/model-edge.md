# Workstream: model edge (the binding problem)

STATUS:   active — this is the one thing between us and live buys.
GOAL:     a PatchTST model with **positive real cross-sectional IC** that passes the WF gate.
NEXT:     pruning NOT closed (prereg ≥2-seeds/arm NOT fully run — Exp A single-seed). Defensible:
          Exp B recipe shows no stable edge across 2 seeds; no promotable model. Before closing or
          switching architecture → run a PROPERLY-POWERED signal-existence diagnostic (≥5 seeds,
          dense corpus, audit placebo matched to gate's 120d shift) + diagnose BULL_CALM
          monotonicity (real vs low-n artifact). Promotion needs operator sign-off; never bypass.
EVIDENCE: partial (final doc 2026-06-21): all completed runs FAIL. Exp B aligned_real_ic sign-
          unstable across seeds (+0.0079 / −0.0085); all ICs in noise band (<0.01) so the gate's
          floored placebo threshold is ill-conditioned here; corpus was sparse (4-cutoff, speed);
          audit placebo (shift-60-rows) mismatched the gate's 120d shift; BULL_CALM monotonicity
          undiagnosed. `[VERIFIED — /tmp/exp_{A,B,B45}_gate.log + self-audit, ephemeral]`
CONSTRAINT: PatchTST is the chosen model (LONG #4); XGB is vetoed as a pitch (LONG #3).
