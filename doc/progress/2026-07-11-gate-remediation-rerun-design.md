# Gate remediation + rerun — design RFC

STATUS:    in-review (design-only PR; do not merge without Codex approval)
WHAT:      Full three-plane gate inventory (renquant-pipeline kernel gates +
           data_availability.v1/funnel_integrity.v1, umbrella daily_104 path
           + preflight P-* consumption + retrain/re-stamp tooling,
           orchestrator monitors/ledger/run-bundle identity) classified by
           (transience T1-T4, remediation existence, remediation risk class
           R0-R3) into a verdict policy STOP / REMEDIATE+RERUN / RERUN /
           DEGRADE+ALARM / ALARM_ONLY, plus the mechanics of a bounded
           remediation controller: pipeline gates EMIT declarative
           remediation hints (additive-optional field inside the existing
           v1 blocks), the orchestrator owns a reviewed action registry +
           policy/budget/audit (`remediation.v1`), action bodies stay in the
           owning repos' existing scripts. Chain depth 1, per-action
           attempt/cooldown budgets, poisoned-session rule (any identity
           failure disables ALL remediation), decision-ledger supersession
           as a hard prerequisite for reruns, shadow-first rollout in 5
           stages with per-risk-class enablement.
WHY/DIR:   Operator mandate 2026-07-11: some fail-closed gate failures
           should trigger a remediation + rerun instead of stopping the
           pipeline. Grounded in #474's registry: 36/56 sessions fully
           blocked by engineering causes; at least 4 block classes had
           known machine-runnable fixes executed manually days late
           (07-09 recovery retrain, fundamentals feed rebuild, calibrator
           re-stamp x3, wash-sale broker-truth correction x2).
EVIDENCE:  Design doc §4 cites file:line for every gate (read-only sweep of
           the three repos, 2026-07-11); worked examples §6 replay the
           07-08/09 outage and the calibrator re-stamp history end-to-end
           through the proposed flow, including the counterfactual failure
           branches and the anti-07-06 consistency precondition.
NEXT:      Codex review of the RFC; operator decisions D1-D8 (design doc
           §8); then per-stage implementation PRs (Stage 0 shadow first:
           pipeline hint-emission PR + orchestrator shadow-controller PR),
           each with its own progress doc.

Deliverable: `doc/design/2026-07-11-gate-remediation-rerun-design.md`.

Key structural findings from the inventory (durable, independent of the RFC's
fate):

- Nothing reruns today anywhere: no pipeline rerun hook, umbrella's only
  automatic re-invocation is the sell-only fallback, orchestrator posture is
  diagnose-and-notify (autonomous-ops-loops §4.2) — the RFC supersedes that
  default only for the classed lane and records the LONG-ledger amendment as
  open decision D7.
- The house already has the closed-loop template (`promote_pin.py` bump →
  verify → auto-rollback) and the event-trigger precedent
  (`conditional_retrain_104.sh` anomaly → retrain chain).
- Decision-ledger sharp edge: verdicts are (run_id, scope, gate)-scoped but
  the autopsy query and decision_outcomes are as_of-scoped — a same-day rerun
  currently doubles verdict rows with no supersession marker. Must be fixed
  with/before the S5 wiring PR regardless of this RFC.
- UNIVERSE-OUTAGE paging (umbrella #463) was closed-unmerged in favor of the
  orchestrator outage monitor (#480, merged, dark) — the controller consumes
  the same two v1 blocks and extends the same title-tag vocabulary
  (new tag SELF-HEALED).
- The 07-06 vs 07-08 pair fixes the hardest classification question: an
  admission-universe collapse whose rejection causes are staleness-dominated
  is remediable by retrain (07-08), but a no_artifact-dominated collapse is a
  corruption signature and must STOP (07-06) — the same detector, opposite
  verdicts, distinguished by a machine-checkable models-dir consistency scan.
