# PatchTST edge-recovery — RESULTS (Exp A/B gate verdicts)

STATUS:   in-progress (results record; both experiments FAIL; seed45 follow-up running)
WHAT:     records the production WF gate VERDICTs for Exp A (reproduce B2) and Exp B (B2 +
          pure-placebo prune). Both FAIL; no promotable model. Documents the validated finding
          (pruning pure-placebo cut placebo_ic -81% while aligned IC stayed positive) and the
          two remaining failure modes (placebo 0.0009 over threshold; WF-sim degraded in B).
WHY/DIR:  north star = a gate-passing 60d model so daily-full can trade. This is the closest
          approach so far and validates the prune direction; next bounded try = seed45.
EVIDENCE: (authoritative = the gate verdicts)
  Exp A: aligned_real_ic +0.0046, placebo_ic +0.0317 (thr 0.0050) → VERDICT FAIL
    artifact: /tmp/exp_A/2026-03-09/hf_patchtst_all_seed44_model.pt | exp | scope: full WF gate
    [VERIFIED — /tmp/exp_A_gate.log, ephemeral]
  Exp B: aligned_real_ic +0.0079, placebo_ic +0.0059 (thr 0.0050) → VERDICT FAIL (near-miss)
    artifact: /tmp/exp_B/2026-03-09/hf_patchtst_all_seed44_model.pt | exp | scope: full WF gate
    [VERIFIED — /tmp/exp_B_gate.log, ephemeral]
NEXT:     seed45 of the Exp B recipe (running, isolated /tmp) → gate → append verdict.
          Promotion only on a clean gate PASS + operator sign-off; never bypass the gate.

UPDATE: per SOP-PR (every PR updates the touched memory tier), refreshed the MID workstream
        doc/memory/mid-term/model-edge.md with the Exp A/B verdicts (bounded-observational) and
        the new NEXT (seed45 running; else escalate). The prior NEXT ("evaluate B2 through the
        gate") is now done, so the stale tier is corrected.
