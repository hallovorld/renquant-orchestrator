# Design: unfreeze the WF promote gate for a blend production (orch#799)

STATUS: **design for review (docs only — NO code / config / behavior change).**
DATE: 2026-08-14. Operator-directed ("全干", after choosing 2026-08-13 to keep the blend prod).
Per the standing rule: approve this design BEFORE implementing.

## 1. Bottom line

The weekly WF promote gate has been fail-closed since the 2026-08-04 "整本切换" made prod a
`kind=blend` scorer. It refuses at `_find_gbdt_config` (`exit 2`) because it requires a **pinned
config whose top-level `ranking.panel_scoring.kind ∈ {xgb, panel_ltr_xgboost}`** as a same-kind
production reference, and prod is now `kind=blend`. This cascades to `retrain-panel104`,
`rq104-silent-refusal`, and `conditional-retrain104` (all refuse), and is the root of the
`wf-promote-chronic-reject` alarm cluster.

**The direction floated earlier — "gate a blend candidate against the blend prod" (Option B) — is
INFEASIBLE with current infra** (three independently-verified blockers, §4). The realistic,
minimal, keep-the-blend fix is **Option A: give the gate an xgb-shaped reference derived from the
blend's `components[0]`** — which IS the production xgb panel scorer. This restores the
pre-blend-switch xgb-component refresh path (recipe-validated promote + RFC#210 freshness
governance) and clears the alarm cluster, WITHOUT reverting the operator's blend decision (the blend
structure is unchanged; only its xgb leg can be refreshed).

**Honest scope (§6):** Option A validates the xgb component's *recipe* and a reference walk-forward —
NOT the served blend's z-sum output, and NOT the new booster's learned quality (the gate is
booster-blind by design, §5). It restores a known-weak path; it does not make it strong, and it does
NOT by itself make 104 buy (that is the separate no-bull-edge finding). Real blend-level gating is
named as deferred future work (§8).

## 2. The blend prod, measured `[VERIFIED — pinned strategy_config.json]`

`RenQuant/.subrepo_runtime/repos/renquant-strategy-104/configs/strategy_config.json`,
`ranking.panel_scoring`:
- `kind = "blend"`; top-level `artifact_path = artifacts/prod/panel-ltr.alpha158_fund.json`.
- `components[0]` = **the production panel scorer (rank:pairwise xgb)** —
  `artifact_path: artifacts/prod/panel-ltr.alpha158_fund.json`, `expected_content_sha256:
  sha256:6461b827ab23…`, `expected_config_fingerprint: sha256:f8fb2259b2bf1537`. `_role` verbatim:
  "component 0 = PRODUCTION panel scorer (rank:pairwise xgb)".
- `components[1]` = slow momentum residual v0 (12-1, weekly ledger-served), `kind:
  momentum_residual`.
- Served composition = **unweighted cross-sectional z-sum** `z(component[0]) + z(component[1])`
  (`blend_scorer.py`; weighting is deferred to the MoE stage, see the served-blend note). The weekly
  retrain produces a new **xgb** panel artifact — i.e. a candidate to refresh `components[0]`.

## 3. Root cause `[VERIFIED — file:line]`

- **Shell freeze point:** `RenQuant/scripts/weekly_wf_promote.sh:148-161` — `_find_gbdt_config`
  (L105-146) scans PINNED configs for top-level `panel_scoring.kind ∈ {xgb, panel_ltr_xgboost}`;
  prod is `blend` → no match → `exit 2` with the "no PINNED strategy config declares kind=xgb"
  message. The message itself names the fork: "either derive the xgb reference from the blend's
  component[0] semantics, or gate blend prods on a blend-kind candidate."
- **Runner parity guard (why you cannot simply point the env var at the blend config):**
  `renquant-backtesting/src/renquant_backtesting/wf_gate/wf_config_builder.py:183-193` —
  `select_prod_reference_for_candidate` normalizes the reference config's
  `ranking.panel_scoring.kind` and, `if ref_kind != kind: raise ValueError(... "Fail closed.")`.
  A `blend` reference against an `xgb` candidate fail-closes. The reference must be **xgb-shaped**
  (top-level `panel_scoring.kind == xgb`); `build_wf_config_from_prod` and the parity guard assume a
  single top-level `panel_scoring` block and do **not** descend into `components[]`.

## 4. Feasibility finding — Option B (blend-vs-blend) is INFEASIBLE `[VERIFIED ×3]`

Gating a blend candidate against the blend prod would require the gate to construct, train, and score
a blend. Every one of those is blocked today:
1. **blend cannot be trained as a candidate.** `renquant-pipeline/.../panel_pipeline/model_registry.py:280`
   — `@registry.register("blend")`'s `train_cmd` raises "blend is an inference-only composition; train
   each component". The weekly retrain cannot emit a blend candidate artifact at all.
2. **blend is not a registered `renquant_common.scorers` entry point** (empty grep of the pinned
   renquant-common package metadata) — the gate's sanity path `load_scorer(kind="blend")` would raise
   `ScorerKindNotRegistered`.
3. **no blend WF manifest + no blend sanity branch.** The `artifacts/sim/walkforward_manifest*.json`
   are all xgb-recipe; `run_sanity_battery` (`runner.py`) dispatches only `panel_ltr_xgboost` and the
   PatchTST kinds, else `passed=False, "sanity not implemented for this kind"`.

So Option B is not a config tweak — it is a multi-artifact build (blend train handler + blend WF
manifest + blend sanity dispatch + a common-scorer entry point). Out of scope for unfreezing;
named as future work (§8).

## 5. The gate is BOOSTER-BLIND — context the design must be honest about `[VERIFIED — test + code]`

On the production path (`walkforward.enabled=True`) admission does **not** score the candidate's
booster. `inspect_artifact_usage` returns `candidate_artifact_used=False` unconditionally (a current
artifact can't be replayed into old sim windows without look-ahead), so
`validation_scope_ok = candidate_artifact_used or recipe_validated = recipe_validated`, and
`recipe_validated` is a **sha256 recipe-fingerprint match** (`_recipe_projection`: `kind`,
`feature_cols`, `feature_norm_kind`, feature-source contract keys, `label_col`, `lookahead_days`,
learner *params* — **no learned weights**) between the candidate and the manifest's pre-trained
per-cut artifacts. The WF backtest + IC sanity then score the **manifest's** per-cut scorers, not the
candidate. This is a documented, tested property:
`renquant-backtesting/tests/test_wf_gate_recipe_admission_is_booster_blind.py`.

**Implication:** unfreezing (Option A) restores the ability to *promote a same-recipe xgb artifact*
(and to run RFC#210 freshness governance) — but "promote" means "the recipe is unchanged and the
kind-matched reference manifest passes WF", NOT "the new booster is proven better than the current
one". orch#799 does NOT change this; fixing booster-blindness is a separate goal (§8).

## 6. Recommended design — Option A, derive the xgb reference from `components[0]`

**Recommended shape: A2 (single source of truth).** When the pinned prod is `kind=blend`, teach the
reference resolution to derive the xgb reference from `components[0]` (its `artifact_path` +
`expected_config_fingerprint`), presenting it to the gate as a top-level xgb-shaped reference. The
xgb candidate then gates against the blend's *own current xgb leg* — exactly the pre-blend-switch
comparison, self-maintaining as `components[0]` advances.

Touch points (implementation, after approval):
- `weekly_wf_promote.sh:_find_gbdt_config` — when a pinned config is `kind=blend` with a
  `components[0]` whose resolved kind is xgb, materialize/emit an xgb-shaped reference (a derived
  temp config, or return the component's artifact+fingerprint) instead of failing at L148.
- `wf_config_builder.py:select_prod_reference_for_candidate` / `build_wf_config_from_prod` / parity
  (`runner.py:3633-3644`) — accept the derived xgb reference; the parity guard must compare against
  the derived (xgb) kind, not the blend wrapper. **Must NOT** weaken the `ref_kind != kind`
  fail-close for the non-blend case (that guard stays; we only add a blend→component[0] derivation
  path).

**Rejected alternative A1 (a pinned sidecar `strategy_config.gbdt_prod_reference.json`).** Simpler
(no runner change — `_find_gbdt_config` just finds the sidecar), but it is a **second source of truth**
that must be hand-kept in sync with `components[0]`; if `components[0]`'s pin advances and the sidecar
does not, the gate silently validates against a stale reference — precisely the
"guards that validate the wrong object" / "digests verify identity not validity" failure class this
codebase keeps hitting. A2's derive-from-the-live-component avoids the drift.

## 7. What unfreezing does / does NOT do (honesty ledger)

- **Does:** restore the weekly xgb-component refresh path (recipe-validated promote + the RFC#210
  freshness fallback the `exit 2` currently blocks); clear the `wf-promote / retrain-panel104 /
  silent-refusal / conditional-retrain` alarm cluster; keep the blend prod exactly as-is.
- **Does NOT:** make 104 buy — the book sits in cash because of the measured no-bull-edge state
  (P-WF-GATE admits but negative bull ER), an independent problem. Prove the refreshed booster is
  better — the gate is booster-blind (§5). Validate the *served blend* — it validates the xgb leg's
  recipe + a reference WF, not the z-sum with the momentum leg (§8).

## 8. Deferred future work (named, not silently dropped)

1. **Real blend-level gating** — build a blend WF manifest + a blend sanity dispatch + a
   common-scorer entry point so the served z-sum can be gated blend-vs-blend (the honest version of
   Option B). Large; a separate goal.
2. **Booster-blindness** — the recipe-hash admission never scores the candidate booster
   (`wf-gate-admits-on-recipe-hash-only`). Also a separate goal.

## 9. Prereg / rollback framing

- **Change class:** reference *resolution*, not a threshold or metric change. All frozen constants
  (`SHUF_IC_MAX`, the 0.40/0.25/0.5 literals, `GATE_VERSION=2`, the Sharpe/placebo/regime rules,
  `runner.py:102,209-267,1529-1539`) are **untouched**. The pass rule and its constants stay frozen;
  we only make the gate *reachable* for a blend prod by supplying the xgb-shaped reference it already
  requires.
- **Behaviour-invariance obligation (implementation gate, before merge):** for a `kind=xgb` pinned
  prod (the non-blend case), reference resolution + the parity guard must be **byte-for-byte
  unchanged** (a regression test asserting the old path is untouched). The blend→component[0]
  derivation is an *added* branch, never a relaxation of the existing fail-close.
- **Rollback:** a config/env toggle restoring the current `exit 2` behavior for blend prods
  (fail-closed = safe); the `RQ_WF_GATE_RUNNER=umbrella` explicit-rollback seam already exists for the
  runner.
- **Adversarial check the implementation PR must survive:** does the derived xgb reference's
  `expected_config_fingerprint` actually equal `components[0]`'s, so the parity guard compares the
  live xgb leg and not a phantom? Prove with the resolved reference vs the pinned `components[0]`.

## 10. Plan

This design PR → codex approve → implementation (touch points §6, with the §9 behaviour-invariance +
adversarial gates) → operator-gated live-tree deploy (the weekly job runs from the run checkout).
Flag-gated + rollback. Behaviour-invariant for the non-blend case.
