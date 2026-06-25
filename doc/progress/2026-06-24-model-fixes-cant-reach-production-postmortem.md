# Postmortem — model fixes can't reach production (systemic)

STATUS:   doc PR (postmortem + RFC). No code change in this PR. Raised by the operator as a
          SYSTEM problem: "mu 做好了但是不能进 daily full."
WHAT:     `doc/design/2026-06-24-model-fixes-cant-reach-production-postmortem.md` — names the
          pattern (correct, deployed fixes ship default-OFF and never turn on → zero live
          effect; mu demean #145 dark since 06-23, momentum #187 gated on impossible
          validation), the root causes, and the structural fix.
ROOT:     (1) no shadow/WARN execution wired into daily-full; (2) no accumulating
          decision-ledger (live trace didn't even record mu); (3) enable is a manual,
          faith-based config flip gated on a validation that can never run.
FIX:      daily-full SHADOW-runs the candidate gates + persists a per-name append-only ledger
          → fix exercised live daily, evidence auto-accumulates, enable becomes data-backed.
          One mechanism subsumes mu validation + momentum validation + the missing ledger.
HONESTY:  includes the author's own process failures as evidence — treated "merged/deployed"
          as progress, ran an unfaithful proxy validation, wrote a test that didn't exercise
          the edit. Symptoms of motion-over-impact.
NEXT:     Phase 1 (mu in the LIVE top-level decision-trace builder) implemented on pipeline
          `feat/decision-trace-mu`; ledger sink + shadow-gate + validation report are the next
          focused build. RULE: no more default-OFF model guards until this loop exists.
