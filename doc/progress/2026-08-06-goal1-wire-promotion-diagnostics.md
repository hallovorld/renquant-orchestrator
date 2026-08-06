# GOAL-1: one promotion degraded three diagnostics and nothing alarmed — wiring two of the three into the daily audit

STATUS:   delivered — both probes registered and running daily; covers 2 of the
          3 diagnostics degraded by the 2026-08-04 promotion (the third,
          orch#870, is a governance-state change no config probe can detect).
WHAT:     registers `shadow_lane_control_probe.py` and
          `shadow_leg_independence_probe.py` as `ops_audit.py` MEMBERS
          (`shadow-lane-control`, `shadow-leg-independence`), running under
          `com.renquant.ops-audit` daily with the aggregator's existing exit
          convention (1=finding, 2=refusal), and updates the provenance-pin
          test to the widened `{member: finding_exits}` contract.
WHY/DIR:  on 2026-08-04 the operator moved the z-blend into prod
          (`z-blend进prod` / `整本切换`). That single change degraded three
          diagnostics and nothing alarmed on any of them — they were found by
          hand, days later, by reading correlations. Two probes were already
          built for two of the three (orch#863, orch#864) and then sat
          unwired, the "deployed-but-dark" failure this repo has recorded
          before; a probe nothing runs is worth nothing.

## The promotion's blast radius

| | consequence | found |
|---|---|---|
| orch#863 | `shadow_blend_momentum` became **byte-identical to prod** in all 21 score-affecting keys — the lane stopped being a control | by hand, 5 rounds later |
| orch#864 | `momentum_residual_v0_shadow` now serves the **same artifact** as prod's `component[1]` — its reported ρ=+0.75 is a self-comparison | by hand, 6 rounds later |
| orch#870 | GOAL-7's preregistered Arm B turned from a deployment **gate** into a post-hoc **monitor** | by hand, 7 rounds later |

Nothing in the daily surface could have raised any of them: every existing
detector watches run-surface drift, artifact identity, or job liveness, and a
promotion that orphans its own controls changes none of those.

## Delivered

```
ops-audit: 13 detector(s) — ok=2 findings=10 info=1 unusable=0 crash=0 timeout=0 missing=0
  [findings] shadow-lane-control      exit=1 NEW  is each lane still distinguishable from prod?
  [findings] shadow-leg-independence  exit=1 NEW  is each leg a different model from the primary?
```

Both follow the aggregator's existing exit convention exactly: **1 = finding,
2 = refusal**, and `2` is deliberately **not** declared as a finding exit for
either — so a refusal (prod config missing, unparseable, or non-UTF-8) lands
on HARNESS rather than being read as *"the fleet is clean"*. `ops_audit`
treats a missing member as `STATUS_MISSING`, so this wiring is safe regardless
of the order these land in.

## The test that failed, and why that was correct

`test_the_cited_contract_is_the_one_in_force` went red on the first run. It is
a **provenance pin** — it asserts the exact `{member: finding_exits}` mapping
so that widening any member's contract must appear as a diff. Adding two
detectors is exactly the change it exists to surface. Updated with the
citation for both, rather than by loosening the assertion.

## Review round 2 — the refusal path had a hole

Codex review flagged that `Path.read_text(encoding="utf-8")` on the PRIMARY
config in both probes can raise `UnicodeDecodeError`, which neither probe
caught — an uncaught exception exits 1 (Python's default), and because
`ops_audit` declares 1 as a finding exit for both members, a corrupted prod
config would misclassify as FINDINGS instead of HARNESS/refusal. Fixed by
catching `UnicodeDecodeError` alongside `OSError`/`JSONDecodeError` on both
primary reads, with CLI-level tests pinning exit 2 for a non-UTF-8 primary
config in both probes. `[codex]`

## What this does NOT do

- **Does not catch the third case (orch#870).** A prereg whose purpose has
  inverted is a governance state, not a config property; no probe here
  detects it, and this claims no coverage it did not build.
- **Does not prevent the promotion.** These are detectors — they fire the day
  after, not before. Making the promotion path itself check whether it
  orphans a control would be the actual fix, and it belongs upstream.
- **Does not say the two live controls are good** — only that they are not
  prod. That distinction is stated in both probes' output.

EVIDENCE:
artifact:      `ops/ops_audit.py` (MEMBERS registration),
               `ops/renquant104/shadow_lane_control_probe.py`,
               `ops/renquant104/shadow_leg_independence_probe.py`.
prod or exp:   prod — `com.renquant.ops-audit` runs both detectors daily as of
               this PR; read-only probes, no config/artifact/schedule mutated.
existing data: `pytest -q tests/test_ops_audit.py tests/test_shadow_lane_control.py
               tests/test_shadow_leg_independence.py` → 69 passed (incl. the
               2 new non-UTF-8-primary-config exit-2 regression tests added in
               review round 2). Live `ops-audit` run:
               `shadow-lane-control exit=1 NEW`, `shadow-leg-independence exit=1 NEW`.
best-known?:   yes — the only two of the three degraded diagnostics with a
               built probe are now wired; orch#870 has no probe (see "does
               NOT do" above).
scope:         this repo's daily ops-audit surface only; no scorer, training,
               backtest, execution, or strategy-config behavior changes.

## Stacking note

This branch stacks on orch#863 and orch#864 (still open, unmerged) — it
registers the probes those PRs add, so reviewing this implies reviewing
those. Their own progress docs live in their own PRs; this doc is the single
PR-scoped record for the wiring change delivered here.

NEXT:     merge orch#863 and orch#864 first (or land this after a rebase once
          they merge); no probe exists yet for orch#870 — that governance-state
          detector is unbuilt and unassigned.
