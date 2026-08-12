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
EVIDENCE:
  artifact:      `doc/design/2026-08-11-orch799-blend-prod-reference-rule.md`
                 (recommendation + the prereg protocol its estimand needs) and
                 this record. No code.
  prod or exp:   neither yet — this is a RECOMMENDATION for a future
                 production-gate rule. Nothing here changes the gate, and the
                 rule is operator-gated. But the doc makes empirical claims
                 that a promotion decision would rest on, so they are measured
                 below rather than asserted.
  existing data: yes — read READ-ONLY from the PINNED runtime
                 `.subrepo_runtime/repos/renquant-strategy-104/configs/strategy_config.json`
                 (strategy-104 `e00d935`, config sha256 `43cbb9b2…`) and the
                 pinned `renquant-pipeline` blend implementation. Nothing
                 generated, no run performed.

                 | measured | value |
                 |---|---|
                 | `ranking.panel_scoring.kind` | `blend` |
                 | component[0] | `artifacts/prod/panel-ltr.alpha158_fund.json`, cfg_fp `sha256:f8fb2259b2bf1537`, content `sha256:6461b827ab2339a8`, **no `kind` key** (its `_role` prose says "rank:pairwise xgb") |
                 | component[1] | `artifacts/momentum/momentum_artifact_ledger.jsonl`, `kind=momentum_residual`, cfg_fp `momentum-v0-fd65161a20b2`, no content sha **by design** (append-only ledger, pipeline#261) |
                 | `ranking.blend_updated` | `2026-05-06` |
                 | `ranking.blend_n_symbols` | `103` |
                 | `ranking.blend_weights` | **ABSENT** — see below |

  best-known?:   the recommendation is best-known among the four options only
                 CONDITIONAL on the protocol in the design doc's new
                 "Preregistered evaluation" section. Without the degenerate-leg
                 condition recorded there, the central attribution claim is
                 false on a subset of folds, so the comparison would not be
                 best-known — it would be undefined.
  scope:         "this is the orch#799 blend-vs-prod reference rule (design
                 recommendation, not implemented), vs existing best = today's
                 structural refusal, which returns no verdict at all. The
                 recommendation's estimand is 'does refreshing the panel-ltr
                 leg improve the SERVED BLEND', measured blend-vs-blend on the
                 frozen WF metric, restricted to folds where BOTH legs scored
                 non-degenerately. It makes no alpha claim and authorizes no
                 promotion."

WEIGHTS — resolved, and it removes a gap rather than opening one. I went to pin
"the blend weights" and `ranking.blend_weights` does not exist in the served
config; its only appearance in the pinned strategy repo is inside
`config_drift.py`'s `DEFAULT_IGNORES`, a drift-IGNORE list, not a value source.
Reading the pinned `renquant-pipeline` implementation resolves why: the blend is
an UNWEIGHTED sum of per-component cross-sectional z-scores, and per-component
weights are deliberately not introduced ("weighting is the MoE stage's own
preregistered change (AC5)"). So there is no weight vector to hold fixed. The
invariant to pin is therefore the PIPELINE COMMIT supplying the combine rule,
not a config key — the doc has been corrected accordingly.
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
