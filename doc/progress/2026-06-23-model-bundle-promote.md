# Self-consistent bundle build + atomic reversible verified promote

STATUS:   merge-pending (PR #175). Additive; promote is dry-run by default — NO real promote was run.
WHAT:     model_bundle.py (stamp / verify / atomic_set_pin / rollback / promote) + scripts/model_promote.py
          CLI + tests. stamp makes a bundle pass the #172 check by construction (refuses to fake WF
          metadata); promote refuses unless deploy_ready then atomically swaps one pin (reversible).
WHY-DIR:  the 2026-06-23 deploy was a 6-step manual pin/restamp dance that hit 4 contracts by hand.
          This is the deploy half of #172: contracts hold by construction; pin swap atomic + reversible.
EVIDENCE: 8 new + 7 #172 tests pass (stamp->deploy_ready; refuses w/o WF; pin swap+rollback; promote
          refuses inconsistent / dry-run no-op / real reversible). No broker mutation. `[VERIFIED — pytest]`
NEXT:     wire promote into the deploy runbook + a readonly daily-full buy-assert before the swap (operator-gated).
