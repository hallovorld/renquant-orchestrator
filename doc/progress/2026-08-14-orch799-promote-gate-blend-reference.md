# orch#799 promote-gate blend-reference — design (doc only)

STATUS:    design/feasibility finding for review. Docs only — NO code / config / behavior
           change. Per operator: approve BEFORE implementing.

WHAT:      `doc/design/2026-08-14-orch799-promote-gate-blend-reference.md`: root-causes the
           weekly WF promote gate freeze (prod is `kind=blend`; the gate requires an
           xgb-shaped same-kind reference and fail-closes at `_find_gbdt_config` exit 2);
           establishes as a FEASIBILITY FINDING that "blend-vs-blend" gating is infeasible
           with current infra (3 verified blockers); recommends Option A (derive the xgb
           reference from the blend's `components[0]`, single-source-of-truth shape A2); and
           carries an explicit honesty ledger of what unfreezing does / does NOT do.

WHY/DIR:   Operator "全干" 2026-08-14, after choosing 2026-08-13 to keep the blend prod. The
           freeze is the root of the wf-promote / retrain-panel104 / silent-refusal /
           conditional-retrain alarm cluster (`wf-promote-chronic-reject-config-tangle`,
           08-12 root = orch#799). This design picks the reachable fix that keeps the blend.
           It also CORRECTS an earlier verbal direction ("gate blend-vs-blend") that the
           mechanics prove infeasible.

EVIDENCE:
  artifact:      `doc/design/2026-08-14-orch799-promote-gate-blend-reference.md` + this
                 progress doc. No code, no config, no production/live path.
  prod or exp:   neither — design/theory only; no computation run, no live change.
  existing data: [VERIFIED] pinned `strategy_config.json` (`kind=blend`; `components[0]` =
                 the prod xgb scorer `panel-ltr.alpha158_fund.json`, content 6461b827, fp
                 f8fb2259; `components[1]` = momentum_residual). [VERIFIED file:line]
                 `weekly_wf_promote.sh:148-161` (`_find_gbdt_config` exit 2);
                 `wf_config_builder.py:183-193` (`ref_kind != kind` → ValueError, fail
                 closed); `model_registry.py:280` (blend `train_cmd` raises "inference-only
                 composition"); blend absent from renquant-common scorer entry points;
                 `run_sanity_battery` dispatches only xgb + PatchTST;
                 `tests/test_wf_gate_recipe_admission_is_booster_blind.py` (booster-blind
                 admission is a documented, tested property). All three Option-B blockers +
                 the parity fail-close were independently re-verified (double-audit), not
                 taken from the mechanics map alone.
  best-known?:   yes — Option A is the minimal keep-the-blend fix that is actually feasible;
                 the rejected A1 (sidecar config) and B (blend-vs-blend) are documented with
                 the specific failure mode / infeasibility. The design freezes NO new
                 numbers and touches NO gate threshold — it only makes the existing frozen
                 gate reachable for a blend prod by supplying the xgb reference it already
                 requires, with a behaviour-invariance obligation for the non-blend case.
  scope:         "a design + feasibility finding to unfreeze the WF promote gate for a blend
                 production by deriving the xgb reference from the blend's component[0].
                 Authorizes NO code, NO config, NO live change. Does NOT alter any gate
                 threshold/metric, does NOT fix booster-blindness, does NOT build blend-level
                 gating (named deferred), and does NOT claim to restore 104 buying (the
                 no-bull-edge state is a separate problem). Implementation lands later in
                 weekly_wf_promote.sh (umbrella) + wf_gate/wf_config_builder.py
                 (renquant-backtesting), flag-gated + behaviour-invariant, then
                 operator-gated deploy."

TESTS:     none — doc-only PR.

NEXT:      codex review → (on approval) implementation with the §9 behaviour-invariance +
           adversarial gates → operator-gated live-tree deploy. Separately: the scorer-identity
           monitor keying fix (distinct PR) and the two deferred goals (real blend gating;
           booster-blindness).
