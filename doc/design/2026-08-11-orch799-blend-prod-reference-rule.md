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
The served scorer's genuine placebo-controlled IC is positive only in BEAR; in the
current BULL_CALM regime its IC is placebo/negative. Refreshing the xgb leg does
NOT create bull alpha that the data says does not exist, and the fallback model is
9 days fresh (≤28d SLA). Unsticking this gate is **pipeline hygiene** (restores the
ability to promote a refreshed leg + stops the weekly not-acting alarm), not an
alpha lever. It should not displace [[goal-b-bear-exit-line]] (making the genuine
BEAR edge tradeable), which is the higher-value line.

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
  refreshed xgb leg — so the measured delta attributes cleanly to the retrain,
  which is precisely the promotion question ("does refreshing the panel-ltr leg
  improve the served blend?").
- Promotion, on PASS, swaps only the xgb leg into the served blend
  (momentum_residual leg unchanged); the blend recipe/weights are unchanged.

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
   leg + z-blend weights verbatim (no re-fit).
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
- On a synthetic PASS, only the xgb leg artifact is swapped; momentum_residual +
  weights byte-identical.
- The weekly not-acting alarm clears (the gate now decides instead of refusing).
