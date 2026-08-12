# orch#799 blend-vs-prod WF reference rule — design recommendation (doc only)

STATUS:    delivered (doc only) — the design itself is a RECOMMENDATION, not an
           authorized code change.
WHAT:      Commit the authored design recommendation
           `doc/design/2026-08-11-orch799-blend-prod-reference-rule.md`. It
           proposes how the weekly WF promote gate should form a kind-matched
           production reference when the served primary is a `kind=blend` but the
           retrain candidate is a `kind=xgb` leg (blend-substitution / option B).
           This PR changes NO code.
WHY/DIR:   The weekly-wf-promote / retrain-panel104 gate is structurally stuck
           (orch#799): prod is a z-blend, the retrain emits a bare xgb leg, and
           the same-kind reference check finds no `kind=xgb` prod config, so the
           gate fail-closes every cycle and the served scorer stays on the RFC#210
           freshness fallback. The doc records the recommended reference rule and
           the rejected alternatives so the operator can decide. Low current
           value (pipeline hygiene, not an alpha lever — see the doc's priority
           note); must not displace the BEAR exit line.
EVIDENCE:  n/a — documentation only; no code, no model/data claim in this PR. The
           design doc's own analysis carries its verified/quoted provenance
           inline (file:line references to the umbrella scripts it discusses).
NEXT:      Operator decision on the reference rule, THEN a separate,
           operator-gated umbrella/live-tree change to
           `scripts/weekly_wf_promote.sh` + `scripts/subrepo_ops_contract.py`
           implementing it (full dry-run against the served blend, standard
           landing discipline, codex review of the rule). NOT implemented here.

## Pointer

Design recommendation: `doc/design/2026-08-11-orch799-blend-prod-reference-rule.md`
(committed verbatim as authored). This progress doc is the required per-PR
record; it deliberately adds no code and authorizes no gate change — the gate
change is the operator-gated umbrella work described in the design doc's
"What implementing (B) requires" and "Acceptance" sections.
