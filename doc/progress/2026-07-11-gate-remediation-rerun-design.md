# Gate remediation + rerun — design RFC

STATUS:    in-review, r4 posted (design-only PR; do not merge without Codex
           approval) — r4 fixed a P0 architecture-ownership gap (the umbrella
           cannot be the permanent execution/lifecycle authority) plus an
           internal Class-TBD verdict contradiction and a P1 experiment-
           accounting gap, see Correction (r4) below
WHAT:      Full three-plane gate inventory (renquant-pipeline kernel gates +
           data_availability.v1/funnel_integrity.v1, umbrella daily_104 path
           + preflight P-* consumption + retrain/re-stamp tooling,
           orchestrator monitors/ledger/run-bundle identity) classified by
           (transience T1-T4, remediation existence, remediation risk class
           R0-R3) into a verdict policy STOP / REMEDIATE+RERUN / RERUN /
           DEGRADE+ALARM / ALARM_ONLY, plus the mechanics of a bounded
           remediation controller: pipeline gates EMIT declarative
           remediation hints (r2: a SEPARATE versioned `remediation_hints.v1`
           block, not an additive field inside the existing v1 blocks — see
           Correction below), the orchestrator owns a reviewed action
           registry + policy/budget/audit (`remediation.v1`), action bodies
           stay in the owning repos' existing scripts. Chain depth 1,
           per-action attempt/cooldown budgets, poisoned-session rule (any
           identity failure disables ALL remediation), decision-ledger
           supersession as a hard prerequisite for reruns, a formal
           execution-safety state machine (r2), a mandatory per-action data/
           model fidelity contract (r2), a falsifiable per-action evaluation
           protocol (r2), and shadow-first rollout in 5 stages with
           per-risk-class enablement.
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

## Correction (r2 — Codex review response, 2026-07-11)

Codex's CHANGES_REQUESTED found four categories of gap; all four are now
first-class sections in the design doc, not narrative asides:

1. **P0 execution safety** — the prior draft treated decision-ledger
   supersession as the whole safety story for reruns. It only solves an
   analytical duplicate-row problem; it says nothing about duplicate broker
   orders, duplicate notifications, duplicate artifact publication, or a
   rerun observing a later external state. New §5.3 replaces the narrative
   treatment with a formal run-lifecycle state machine: an explicit
   PRE_SIDE_EFFECT / SIDE_EFFECT_BEGUN / TERMINAL phase model with a
   mechanical pre-side-effect cutoff (`lifecycle_events == []`), an
   idempotency key + single-writer lease (§5.3.2) so concurrent controller
   invocations cannot double-fire the same episode, and the buy-only
   `n_buy_orders == 0` precondition generalized to cover exits explicitly
   (§5.3.4) — a run that has executed ANY order, buy or sell, has left the
   phase where remediation is offered, full stop.
2. **P1 data/model fidelity** — the anti-07-06 consistency precondition and
   the calibrator fingerprint checks were correct WORKED EXAMPLES but only
   narrated per-action. New §5.6 makes the underlying contract
   (`fidelity_contract`: immutable input snapshot, as-of cutoff, source/
   output fingerprints, mechanical no-leakage proof) a MANDATORY field on
   every action registry entry — an action with none is not eligible past
   Stage 0. Auto-retrain's cutoff is now explicit: the ORIGINAL eligible
   training cutoff, never "now", with its output still just a candidate
   through the normal promotion gates (restating P3, not weakening it).
3. **P1 falsifiable evaluation** — the #474 registry's 36/56 number was
   being read too strongly. New §7bis makes explicit that it is incident
   MOTIVATION only, and requires a per-action pre-registered protocol
   (eligibility, expected result, forbidden side effects, counterfactual
   comparator, false-positive target, rollback rule) PLUS both a historical
   incident replay set and prospective shadow coverage with action-specific
   minimum event counts and a holdout period — a blanket "≥10 sessions" is
   explicitly called out as necessary but not sufficient.
4. **P1 contract compatibility** — the additive-optional-field-in-v1 design
   assumed forward-compatibility across every current producer/consumer/
   validator without auditing them. Reversed (open decision D6): the hint
   now publishes as a separate, additively-versioned `remediation_hints.v1`
   block, with a cross-repo compatibility test as an explicit Stage-0
   precondition rather than an assumed property.

No section was deleted; the two worked examples (§6.1/§6.2) are preserved
and now cross-reference the formalized mechanisms (§5.3, §5.6) instead of
standing alone. New open decisions D9 (lease store implementation) and D10
(historical replay set scope) added to §8.

## Correction (r3 — Codex review response, 2026-07-11, P0)

Codex's second-pass CHANGES_REQUESTED found one P0 contradiction and three
smaller corrections. The P0 required real architecture research (two
separate read-only traces of renquant-pipeline and the umbrella's live
runner, no code changes), not just a doc rewrite:

1. **P0 — P6 vs §5.3/§6.1 contradiction.** P6 claimed reruns happen "only
   after the failed run's exit pass completed," while §5.3.1/5.3.4 required
   `lifecycle_events == []` (no order submitted, buy OR sell) before the
   controller may act. A normal completed daily-full run cannot satisfy
   both. Traced the real order-submission path
   (`RenQuant/live/runner.py` → `RunnerAdapter.commit()`,
   `.../adapters/runner.py` sells ~1177 / buys ~1509): submission is
   SYNCHRONOUS and same-run — there is no code-level gap between decision
   and broker submission for either side. Since the remediation controller
   is deliberately scheduled AFTER the daily run (§5.1, unchanged), it can
   only ever observe a completed run in phase (b) or later for any gate
   that fires at or after `enforce_buy_block`'s position (verified: strictly
   after `TickerSellJob` and its exit-refinement chain, §5.3.4) — which is
   most of the gate table, including the flagship §6.1 example.
   **Resolution:** split remediation into Class A (gate aborts BEFORE the
   sell pass — `commit()` never reached — a genuine same-day chained rerun
   is safe) and Class B (gate sets a soft block, run completes normally
   through `commit()` — remediation repairs the input same-day, but only
   the NEXT regularly-scheduled session resumes trading; no rerun, no new
   `run_id`, no resubmitted order). §2 (P6), every row in §4's gate table,
   §5.2's action registry schema, §5.3.4/5.3.5/5.3.7/5.4, and §6.1's entire
   worked-example walkthrough are corrected to this model. §6.2 was already
   Class A in substance (both its detection planes precede `commit()`) and
   now says so explicitly. §4.3's preflight rows (20-28) are left as
   Class TBD with an honest caveat — their interaction with `daily_104.sh`'s
   sell-only fallback needs the same rigor as a follow-up trace, not a
   guess; they default to Class B (no same-day rerun) until traced.
   Also closed Codex's specific sub-point: `orders_submitted` must be
   stamped by the EXECUTION owner (`RunnerAdapter.commit()` itself, at its
   `broker.place_order` call sites) — never inferred by the controller from
   a separate log or count — and a missing/unavailable stamp fails closed
   to phase (b), never defaults to phase (a).
2. **D4 reversed.** "Pipeline emits, umbrella forwards" would have added new
   forwarding code to a repo being actively deprecated. Reversed: pipeline
   emits `preflight_verdicts.v1` directly into the shared run bundle the
   orchestrator already reads; orchestrator consumes it directly; no new
   umbrella code.
3. **Neutral runtime root.** `~/renquant-data/remediation_log.jsonl` was a
   separate, undocumented state authority. Standardized under the R-PIN
   neutral root: `~/.renquant/remediation/remediation_log.jsonl`, sibling to
   `~/.renquant/deploy/` and orchestrator#481's `~/.renquant/ops/`.
4. **R0 vendor-refetch eligibility.** Added an explicit constraint to §5.6:
   a refetch action is only eligible for the same-session remediation lane
   when its vendor source can supply a versioned/as-of-queryable snapshot;
   a mutable "latest"-only source has no after-the-fact no-leakage proof
   and must be treated as next-session preparation only, never a
   same-session remediation+rerun, regardless of its Class A/B tag.

No section was deleted. This correction personally authored (not delegated
to a fork) per the design-review-fixes-personal convention; two research
passes (order-submission timing, sell-pass/buy-gate ordering) were run to
ground the fix in the real codebase rather than in the RFC's own prior
narrative.

## Correction (r4 — Codex's third review pass on this doc, 2026-07-11)

Codex's review of the r3 (Class A/B) fix called it "a real improvement" but
found two P0s and one P1 remaining:

1. **P0 — architecture ownership.** The r3 fix's "ownership of the stamp"
   paragraph traced `orders_submitted` to the umbrella's
   `RunnerAdapter.commit()` as ground truth — accurate, but Codex correctly
   held that a forensic trace of legacy code cannot define the DURABLE
   owner. New §5.1bis states the target-state ownership split
   (renquant-execution owns lifecycle events + broker-submit idempotency;
   renquant-pipeline owns `preflight_verdicts.v1` + immutable input
   snapshots; renquant-orchestrator owns the controller + neutral state;
   the schedule invokes a multi-repo entrypoint, never `daily_104.sh`
   directly) and a concrete, machine-checkable CUTOVER PREDICATE (a census,
   analogous to the existing `engineering_census` AST-scan pattern,
   confirming zero umbrella-path references in the active schedule and
   that `orders_submitted` is stamped exclusively from renquant-execution)
   that must hold before any Class A rerun-capable action is enabled past
   Stage 0 shadow. §5.3.1 and §7's stage table are corrected to reference
   it explicitly.
2. **P0 — internal contradiction.** §4.3's rows 20-23 said "default to
   Class B until traced" but still carried a live `RERUN`/`REMEDIATE`
   verdict — directly contradicting Class B's own no-rerun definition.
   Corrected to an explicit `SHADOW-ONLY` verdict (no action enabled at any
   stage) until BOTH the sell-only-fallback trace and (for whichever rows
   resolve to Class A) the new cutover predicate hold. §7's Stage 1/3 rows
   are corrected to gate `ohlcv_refetch`, `session_rerun`, and
   `calibrator_binding_restamp` (the Class A actions) on the cutover
   predicate specifically, while leaving Class B actions
   (`broker_snapshot_repoll`, the R1/R2/R3 Class B actions) ungated by it.
3. **P1 — experiment accounting.** New §7bis "Class B estimand" paragraph:
   a Class B `SELF_HEALED` episode repairs tomorrow's input but cannot
   recover the triggering session's lost trading. The evaluation plan must
   report it separately as prevention of a repeated failure (next-session
   comparator + explicit missed-session opportunity/cost), and no
   acceptance decision may count a Class B outcome as recovered trading
   performance for the triggering session.

No section was deleted; §5.1bis is net-new, everything else is a targeted
correction in place. Personally authored per the design-review-fixes-
personal convention — no new research pass was needed this round (the
architecture-ownership and accounting points follow from principles
already established elsewhere in this session, e.g. the R-PIN/umbrella-
deprecation trajectory and `artifacts#22`'s independent reaffirmation of
the same non-authority principle for the umbrella).
