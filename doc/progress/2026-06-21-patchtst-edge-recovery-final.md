# PatchTST edge-recovery — PARTIAL verdict (Exp B 2-seed only)

STATUS:   in-progress (PARTIAL verdict — Exp B 2-seed only; prereg NOT complete; pruning line
          NOT closed; no promotable model)
WHAT:     records the gate verdicts for the runs completed so far (Exp A seed44; Exp B seed44 +
          seed45). Does NOT complete the prereg (which needs >=2 seeds PER ARM — Exp A is single
          seed). Supersedes the interim seed44 doc; updates the MID model-edge workstream.
WHY/DIR:  narrow defensible result — the Exp B prune recipe shows NO stable edge across its 2
          seeds (aligned_real_ic +0.0079 / -0.0085, sign-unstable, indistinguishable from zero);
          no promotable model on completed runs. The broader pruning line is NOT closed.
EVIDENCE: all completed runs FAIL the gate. Caveats (self-audit): all ICs in the noise band
          (<0.01) so the gate's floored placebo threshold is ill-conditioned here; sparse 4-cutoff
          corpus (speed); audit placebo (shift-60-rows) mismatched the gate's 120d shift; BULL_CALM
          monotonicity fails in all but is UNDIAGNOSED (possible low-n artifact, not a confirmed
          wall). `[VERIFIED — /tmp/exp_{A,B,B45}_gate.log + self-audit, ephemeral]`
NEXT:     before closing any line or switching architecture — a properly-powered signal-existence
          diagnostic (>=5 seeds, dense corpus, audit placebo matched to the gate's 120d shift) +
          a BULL_CALM monotonicity diagnosis (real vs low-n). No promotion; gate correctly blocking.
