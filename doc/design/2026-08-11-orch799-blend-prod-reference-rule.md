# orch#799 — the blend-prod reference rule for the WF promote gate — RECOMMENDATION (design, not yet authorized)

STATUS: **RECOMMENDATION for a design decision — NOT an authorized code change.**
Proposes how the weekly WF promote gate should form a "kind-matched production
reference" when the served primary is a `kind=blend` but the retrain candidate is
`kind=xgb`. Changes NO code in this PR; the umbrella `scripts/weekly_wf_promote.sh`
+ `scripts/subrepo_ops_contract.py` edit that would implement it is a separate,
operator-gated live-tree change.

## The stuck condition (verified 2026-08-11)

`weekly-wf-promote` and `retrain-panel104` refuse every cycle. Root cause
(`scripts/weekly_wf_promote.sh:149-159`, `scripts/subrepo_ops_contract.py:218-241`):
the served production primary is a **z-blend** (`kind=blend` =
panel-ltr xgb leg + momentum_residual leg, since the 2026-08-04 blend cutover),
but the retrain pipeline emits a **`kind=xgb`** candidate (a fresh panel-ltr).
The gate searches the PINNED strategy configs for one declaring `kind=xgb` to use
as the same-kind GBDT production reference, finds none (prod is a blend), and
**refuses rather than simulate a phantom config** — a correct fail-closed choice
(comparing an xgb candidate against a cross-kind or a known-diverged working-copy
reference would be non-comparable WF evidence). So the gate **can never pass**:
the model-refresh pipeline is structurally stuck, and the served scorer stays on
the RFC#210 freshness fallback indefinitely.

## Priority note (honest)

This is **low current value** and is filed as a recommendation, not an urgent fix.
The argument is structural, and deliberately carries no empirical claim:

**A change to which object the gate compares against cannot create edge.** It
changes whether a verdict is reachable, not what the verdict will be. So unsticking
this gate is **pipeline hygiene** — it restores the ability to promote a refreshed
leg and stops the weekly not-acting alarm — and it is not an alpha lever under any
outcome. That holds by construction; it needs no measurement, and it is why this
should not displace higher-value lines.

An earlier draft ranked this work using regime-conditional IC and model-freshness
assertions. Those are **removed, not demoted**: this document has no reproducible
source for them (no run ID, no measurement command, no named object whose freshness
was measured), and `ranking.blend_updated = 2026-05-06` — the only freshness field
this doc actually measured — does not substantiate any such statement. If a
regime/freshness argument is load-bearing for prioritization, it belongs in the
document that establishes it, cited from there with its artifacts. Borrowing a
conclusion across documents without its evidence is how an unverified number
acquires the authority of a citation, even when — as here — it was being used to
argue for LOWER priority rather than higher.

## The recommended reference rule: blend-substitution (option B)

**When the served primary is `kind=blend` and the candidate is a fresh xgb leg,
the production reference is the SERVED BLEND, and the candidate is evaluated as the
served blend with its xgb leg replaced by the candidate leg. The gate compares
blend-vs-blend on the frozen WF metric.**

- Both sides of the comparison are `kind=blend` → the same-kind requirement is
  satisfied at the SYSTEM (served-object) level, which is the level the WF metric
  (return-space + sanity battery) actually measures. No phantom config, no
  cross-kind comparison.
- The candidate blend differs from the reference blend in exactly one factor — the
  refreshed xgb leg — so the measured delta attributes to the retrain **on folds
  where both legs scored non-degenerately**. That qualifier is load-bearing and is
  not a formality; see "Preregistered evaluation" below.
- Promotion, on PASS, swaps only the xgb leg into the served blend
  (momentum_residual leg unchanged). **There is no weight vector to hold fixed:**
  the blend is an unweighted sum of per-component cross-sectional z-scores, with
  per-component weights deliberately not introduced (weighting is the MoE stage's
  own preregistered change, AC5). `ranking.blend_weights` is absent from the served
  config; its only occurrence in the pinned strategy repo is in `config_drift.py`'s
  `DEFAULT_IGNORES`. The invariant to pin is the **pipeline commit** supplying the
  combine rule, not a config key.

## Preregistered evaluation — what makes the delta attributable

The estimand is: *does replacing the served blend's xgb leg with the candidate leg
improve the frozen WF metric?* Three conditions, fixed before any run:

1. **Degenerate-leg exclusion (the one that would silently break it).** The pinned
   `BlendPanelScorer` gives a degenerate leg — `std == 0`, or fewer than 2 finitely
   scored names — a contribution of **0**, recording
   `component{i}[…]_n_lt_2` / `_std_zero` in `metadata["degraded_reason"]`. It fails
   SOFT inside the composite. So on any fold where the momentum_residual leg
   degrades, `blend == z(xgb)` alone, and a blend-vs-blend comparison there measures
   the xgb swap **unblended** — a different estimand. Folds carrying a
   `degraded_reason` token for either leg are **excluded**, and the excluded count is
   reported; a run excluding more than a preregistered fraction is a FAIL of the
   comparison, not a smaller sample.
2. **Fold-local fitting.** The candidate xgb leg is retrained per fold on
   training-only data, with fold-local normalization/calibration. The
   momentum_residual leg and the combine rule (pipeline commit) are held fixed
   across both arms and all folds. Identical universe, costs, and constraints.
3. **A paired held-out decision metric with the PASS/FAIL rule fixed in advance**,
   evaluated on the same dates for both arms.

### What this document fixes, and what it explicitly does not

Splitting these is the point: a fact I can read from the system belongs here, and a
judgment I would be inventing does not.

**Fixed here (facts, read from the pinned system):**

| | |
|---|---|
| combine rule | `renquant_pipeline/kernel/panel_pipeline/blend_scorer.py::BlendPanelScorer.score` — unweighted Σ of per-component cross-sectional z, `ddof=0` over each component's finite-scored universe |
| the pinned object | the **pipeline commit** supplying that module, recorded in the prereg at run time. I am deliberately not pasting today's runtime commit: `.subrepo_runtime` currently reads `e13cd3eb` while the lock has already advanced past it, so any commit quoted here would be stale before the run |
| missing scores | already defined by the implementation, not a free choice: a name a healthy leg cannot score finitely becomes NaN and is dropped downstream as unscored |
| degenerate leg | `std == 0` or `< 2` finitely scored names → contributes 0, token in `metadata["degraded_reason"]`, SOFT inside the composite |
| exclusion rule | folds carrying a `degraded_reason` token for either leg are excluded, and the excluded count is reported |

**NOT fixed here — and this document does not have the standing to fix them.** The
maximum exclusion fraction, the fold/date construction, the held-out metric and its
horizon, the PASS/FAIL threshold or comparison statistic: each of these determines
whether the comparison can manufacture an apparent benefit, and I would be choosing
them from nothing rather than from evidence. Picking numbers here to make the
document look complete is the failure this repo has been bitten by before — a
threshold asserted in prose reads as preregistered when it was improvised.

**Therefore this recommendation is explicitly CONDITIONAL** on a separate,
committed, versioned prereg artifact that fixes those quantities, is approved before
any umbrella gate change, and is frozen before any run is executed. Until that
artifact exists and is approved, this document recommends the reference **rule** and
licenses **no** promotion decision made under it — including a decision that would
merely "try it and see".

### Rejected alternatives

- **(A) bare-leg reference** (compare candidate xgb leg vs current xgb leg in
  isolation): same-kind but evaluates an object that is NOT served — a leg's
  standalone WF metric need not track its contribution inside the blend. Rejected:
  measures the wrong object.
- **(C) retrain the whole blend** (emit a blend candidate so kinds match trivially):
  larger pipeline change; also re-fits the momentum_residual leg, so the delta no
  longer isolates the panel-ltr refresh. Rejected as heavier + less attributable.
- **(D) retire the xgb-only weekly promote**: throws away the ability to refresh
  the leg. Rejected — the leg SHOULD be refreshable; the gate just needs the right
  reference.

## What implementing (B) requires (out of scope for this doc; operator-gated)

1. The gate constructs the candidate blend = served blend recipe with the xgb leg
   artifact swapped to the candidate; re-uses the served blend's momentum_residual
   leg verbatim (no re-fit) and leaves the combine rule untouched. **There are no
   weights to reuse** — the combine rule is the unweighted z-sum implemented in
   `renquant_pipeline/kernel/panel_pipeline/blend_scorer.py::BlendPanelScorer.score`,
   so the object to hold fixed is that MODULE at a pinned pipeline commit, not a
   config value.
2. The same-kind reference check (`subrepo_ops_contract.py`) accepts a `kind=blend`
   pinned prod reference when the candidate is a leg of that blend, instead of
   requiring a top-level `kind=xgb` config.
3. The WF metric + sanity battery run on the two blends; PASS/FAIL as today.
4. On PASS, promotion swaps only the leg. The served blend's fingerprint changes;
   RFC#210 governance + the scorer/calibrator binding gate apply unchanged.
5. This is a change to umbrella `scripts/weekly_wf_promote.sh` +
   `scripts/subrepo_ops_contract.py` — a LIVE-TREE / run-surface change, so it is
   gated on: operator authorization, a full dry-run of the gate against the current
   served blend (asserting it forms the candidate blend + reaches a verdict without
   touching production), and the standard landing discipline. It also wants codex
   review of the reference-rule change before any live edit.

## Acceptance (when/if implemented)

- A dry-run weekly-wf-promote against the current served blend reaches a real
  PASS/FAIL verdict (no orch#799 refusal), production unchanged.
- The candidate blend differs from the served blend only in the xgb leg artifact
  (verified by fingerprint diff of the two blend recipes).
- On a synthetic PASS, only the xgb leg artifact is swapped; the
  momentum_residual leg is byte-identical and the pipeline commit supplying the
  unweighted z-sum is unchanged (there is no weight object to compare).
- The comparison reports its degenerate-leg exclusion count, and that count is
  within the preregistered bound.
- The weekly not-acting alarm clears (the gate now decides instead of refusing).
