# PatchTST edge-recovery — FINAL verdict (2-seed set)

STATUS:   in-progress (final verdict PR; pruning line CLOSED; no promotable model)
WHAT:     completes the prereg ≥2-seed set; records all gate verdicts; supersedes the interim
          seed44 doc; updates the MID model-edge workstream (pruning CLOSED → escalate).
WHY/DIR:  decisive negative result — Exp B aligned_real_ic flips sign across seeds (seed44
          +0.0079 / seed45 −0.0085), so the seed44 placebo near-miss was seed noise, not a
          stable edge. Pruning does not yield a gate-passing 60d model on this feature set.
EVIDENCE: all 3 runs FAIL the production WF gate; aligned IC sign-unstable; BULL_CALM
          monotonicity fails in all (independent 2nd blocker).
          `[VERIFIED — /tmp/exp_A_gate.log, /tmp/exp_B_gate.log, /tmp/exp_B45_gate.log, ephemeral]`
NEXT:     operator priority on escalation (feature/architecture) + BULL_CALM monotonicity
          diagnostic — see discussion PR #160. No promotion; gate correctly blocking.
