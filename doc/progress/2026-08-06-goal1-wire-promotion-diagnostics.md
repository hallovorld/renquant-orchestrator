# GOAL-1: one promotion degraded three diagnostics and nothing alarmed — wiring two of the three into the daily audit

**Date:** 2026-08-06
**Lane:** GOAL-1 (shadow reliability gates)

## Why

On 2026-08-04 the operator moved the z-blend into prod (`z-blend进prod` /
`整本切换`). That single change:

| | consequence | found |
|---|---|---|
| orch#863 | `shadow_blend_momentum` became **byte-identical to prod** in all 21 score-affecting keys — the lane stopped being a control | by hand, 5 rounds later |
| orch#864 | `momentum_residual_v0_shadow` now serves the **same artifact** as prod's `component[1]` — its reported ρ=+0.75 is a self-comparison | by hand, 6 rounds later |
| orch#870 | GOAL-7's preregistered Arm B turned from a deployment **gate** into a post-hoc **monitor** | by hand, 7 rounds later |

**All three were found by reading correlations, days after the fact.** Nothing in
the daily surface could have raised any of them: every existing detector watches
run-surface drift, artifact identity, or job liveness, and *a promotion that
orphans its own controls changes none of those*.

Two probes were built for #863 and #864 — and then sat unwired, which is the
"deployed-but-dark" failure this repo has recorded before. A probe nothing runs
is worth nothing.

## Delivered

Both are now `ops_audit.py` MEMBERS, so they run under
`com.renquant.ops-audit` daily:

```
ops-audit: 13 detector(s) — ok=2 findings=10 info=1 unusable=0 crash=0 timeout=0 missing=0
  [findings] shadow-lane-control      exit=1 NEW  is each lane still distinguishable from prod?
  [findings] shadow-leg-independence  exit=1 NEW  is each leg a different model from the primary?
```

Both follow the aggregator's existing exit convention exactly: **1 = finding,
2 = refusal**, and `2` is deliberately **not** declared as a finding exit for
either — so a refusal (prod config missing or unparseable) lands on HARNESS
rather than being read as *"the fleet is clean"*.

`ops_audit` treats a missing member as `STATUS_MISSING`, so this wiring is safe
regardless of the order these land in.

## The test that failed, and why that was correct

`test_the_cited_contract_is_the_one_in_force` went red on the first run. It is a
**provenance pin** — it asserts the exact `{member: finding_exits}` mapping so
that widening any member's contract must appear as a diff. Adding two detectors
is exactly the change it exists to surface. Updated with the citation for both,
rather than by loosening the assertion.

## Scope and dependencies

This PR **stacks on orch#863 and orch#864** — it merges both, because the
detectors it registers are the probes those PRs add. Reviewing this one implies
reviewing those.

Suite on the stacked branch: **5925 passed, 1 failed** — the failure is orch#855,
pre-existing on main and fixed in orch#849, which is not stacked here.

## What this does NOT do

- **It does not catch the third case (orch#870).** A prereg whose purpose has
  inverted is a governance state, not a config property; no probe here detects it,
  and I am not claiming coverage I did not build.
- **It does not prevent the promotion.** These are detectors — they fire the day
  after, not before. Making the promotion path itself check whether it orphans a
  control would be the actual fix, and it belongs upstream.
- **It does not say the two live controls are good** — only that they are not
  prod. That distinction is stated in both probes' output.
