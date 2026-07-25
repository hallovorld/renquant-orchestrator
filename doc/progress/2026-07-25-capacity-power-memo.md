# Relocate capacity + power reconciliation memo to renquant-model

STATUS:    delivered
WHAT:      Removes `doc/research/2026-07-24-capacity-and-power-reconciliation.md`
           and `doc/research/evidence/2026-07-24-capacity-memo/` (5 analysis
           scripts + 6 result JSONs) from this repo. The memo now lives
           byte-identical (plus two fixes made in transit — see below) in
           `hallovorld/renquant-model#69`. This PR is reduced to this
           progress doc documenting the relocation.
WHY/DIR:   Two consecutive review rounds on this PR (both BLOCKER) found the
           memo and its evidence bundle are model/strategy research, not
           orchestration: `depth_probe.py` and `horizon_matched.py` import
           `renquant_model_gbdt.panel_data`/`panel_trainer` and train XGB
           cells directly, the exact hard-boundary violation the
           factorial-HFR study was relocated for in this same branch's
           history (`bd943860`, -> `renquant-model#67`). Per the umbrella
           multi-repo code-placement rule (model research -> `renquant-
           model`, never the orchestrator), this PR completes the same
           move. Two review findings that were fixable in-place also
           travelled with the relocation rather than being fixed twice:
           the hardcoded agent-session scratch paths in 4 of the 5 scripts
           (now env-overridable, repo-local default), and the memo's §3/§4
           "zero statistical risk" claim on the TC 0.4→0.7 lever (now a
           conditional scenario pending a precommitted execution/P&L
           validation, per review finding 3 on this PR's first round).
EVIDENCE:  n/a
NEXT:      This PR now carries no model/data claim of its own — the
           relocated claims and their §4(b) evidence blocks are in
           `renquant-model#69`'s progress doc
           (`doc/progress/2026-07-24-capacity-power-memo.md` in that repo).
           Review continues there; nothing further pending in this repo for
           this memo.
