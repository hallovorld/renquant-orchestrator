# RS-2: lane-A timing — PREPARE + SHADOW A-1/A-3 separately, DEFER A-2 behind its own
marginal-rank evidence (delegated decision)

STATUS: research recommendation (delegated per the 2026-07-02 grant; operator NOTIFIED).
DATE: 2026-07-02
QUESTION (#231 §6): run the cash-drag de-throttle experiments before or after D1's first
WF-gate verdict, given the model has no standing validation?

## Round 2 correction (Codex CHANGES_REQUESTED)

r1 over-authorized A-1/A-3 for near-term live enablement on evidence that turns out to be
either retracted or insufficiently rigorous. Corrected below:

- **The "buy-side TC 0.09" citation is REMOVED.** #234's corrected revision (same review
  round) retracted that number: its admission/sizing split had misclassified `blocked_by`
  values (`broker_pending_submitted` is terminal outcome telemetry for names that WERE
  bought, not an admission blocker), which mechanically forced a spurious result. #234 now
  reports zero validated sizing-TC days, everything labeled exploratory. A-1/A-3 do **not**
  "repair a measured TC deficit" — there is currently no measured TC deficit to repair.
- **A-3 is not zero-risk.** A one-share floor makes a previously-unaffordable/unselected
  high-price name newly investable — this changes WHICH names get selected, not just their
  relative order, which changes concentration, cash use, and realized exposure. In some
  portfolio states it can ADD net exposure rather than merely swap which admitted name fills
  a slot. Reclassified as a genuine model-selection-adjacent change with real (if likely
  small) risk.
- **A-1 is not zero incremental model risk.** Changing λ changes the QP's optimized weights
  and deployed notional among forecasts that are themselves unvalidated. Existing per-name/
  sector/correlation caps bound the maximum possible loss from any single name; they do not
  prove the overall risk/expectancy profile is unchanged from λ=0.
- **The "thin-margin" evidence is relabeled.** The SQL below leaves `<full runs>`
  unspecified, does not select one canonical completed run per calendar day, and carries no
  confidence interval or cross-regime stability check. It is a **descriptive score-density
  observation**, not a statistically validated claim that picks 4–6 are indistinguishable
  from pick 3 or "OXY-like." Treated as such throughout this doc.
- **"D1 OR M3" is not sufficient authorization for A-2.** A passing AGGREGATE model verdict
  (D1) or a general uncertainty haircut (M3) does not establish the INCREMENTAL net value of
  admitting a 4th–6th name specifically. A-2 now requires its own dedicated frozen
  marginal-rank test (§ below).
- **A-1 and A-3 recommendation downgraded** from "ENABLE NOW" to "PREPARE and SHADOW
  separately now, each per its own preregistered protocol (§ below) — NO LIVE ENABLE until
  each experiment's preregistered operational/risk gate clears," per #228 §1.2's
  one-change-at-a-time experiment requirement.

## The descriptive measurement (reproducible one-liner, runs.alpaca.db — NOT a statistical
claim; see caveat above)

Thin-margin share of the floor-clearing pool (mu ∈ [0.030, 0.0375) = within 25% of the
floor — the OXY class):

| run | names ≥ floor | thin-margin | share | avg admitted mu |
|---|---|---|---|---|
| 07-01 | 17 | 15 | **88%** | 0.0351 |
| 06-30 | 20 | 16 | **80%** | 0.0353 |
| 06-26 | 22 | 17 | 77% | 0.0360 |
| 06-25 / 06-23 / 06-22 | 6 / 8 / 9 | 6 / 4 / 6 | 100 / 50 / 67% | 0.031–0.041 |

```sql
-- CAVEAT: <full runs> is an unspecified run-id list (not one canonical completed run per
-- calendar day — a later run superseding an earlier same-day run, or a partial/failed run,
-- could double-count or contaminate a day). No confidence interval or regime breakdown is
-- computed. This is score-density over whatever runs were passed in, not a validated
-- indistinguishability test between pick 3 and picks 4-6. A proper confirmatory version
-- would select through pipeline_runs completion state (one canonical run/day, matching
-- strategy/data/model/config fingerprints — the same discipline #430/#234's corrected
-- revisions apply this session) and report a CI + per-regime breakdown before any
-- statistical claim is made from it.
select run_id, sum(mu>=0.03), sum(mu>=0.03 and mu<0.0375), round(avg(case when mu>=0.03 then mu end),4)
from candidate_scores where role='candidate' and run_id in (<full runs>) group by run_id;
```

**Observation only:** the admitted pool in these sampled runs looks ~80–88% thin-margin
post-retrain — suggestive that the conviction floor is doing little separation among
admitted names, with no uncertainty penalty (M3 not yet built) and no model verdict (D1 not
yet rendered). This motivates caution on A-2 (see below) but is not itself evidence that
A-1/A-3 are safe or that A-2's 4th–6th picks are statistically equivalent to the 3rd.

## Recommendation — split lane A by what each knob actually admits

| Knob | What it changes | Verdict | Basis |
|---|---|---|---|
| **A-1 `qp_cash_drag_lambda` 0 → 0.05** | allocation among names the QP already admitted — no new-name admission | **PREPARE + SHADOW separately, own preregistered protocol (§ below) — NO LIVE ENABLE until its gate clears** | exposure delta bounded by existing per-name/sector/correlation caps, but caps bound loss, they do not prove unchanged risk/expectancy; solver default is 0.05 — we would be un-disabling a shipped control, not introducing a new one |
| **A-3 one-share floor for high-price names** | removes the selection-by-share-price artifact (BLK vs OXY) — changes WHICH admitted name gets a slot; can also change concentration/cash-use/exposure, not merely reorder | **PREPARE + SHADOW separately, own preregistered protocol (§ below) — NO LIVE ENABLE until its gate clears** | artifact removal, measured descriptively in the OXY forensics; NOT a "zero-risk ordering fidelity" change — a genuine model-selection-adjacent change with real (likely small, unquantified) risk |
| **A-2 `panel_buy_top_n` 3 → 5–6** | admits MORE names per session from a pool that descriptively looks thin-margin-heavy in the samples above | **DEFER — behind its OWN dedicated frozen marginal-rank test** (forward net return, turnover/cost, concentration, and regime stability specifically for the 4-vs-6 comparison), not merely "D1 OR M3 passing" | a passing aggregate D1/M3 verdict does not establish the incremental value of the 4th–6th pick specifically; at top_n=6 the worst case adds ~3 thin-margin entries/day ≈ +9pp/day of unvalidated-model exposure — the risk is first-order even though A-2's own dedicated benefit evidence does not yet exist |

**Deployment AC unaffected**: POC-B put lane A's shrinkage-realistic ceiling at ~40–43%
regardless; lane B (the sleeve) carries the ≥60% deployment AC in the interim, which is
exactly the #231 S6/S7 division of labor.

## A-1 and A-3 preregistered shadow protocols (per #228 §1.2's one-change-at-a-time rule)

Both experiments follow #228 §1.2's structure: ONE parameter changed at a time (all other
lane-A knobs held at current values), against a FIXED admission universe held constant
across the variants being compared, so any measured effect is attributable to that specific
change. Both carry the universal #228 non-degradation gate (turnover/cost, concentration,
drawdown) IN ADDITION to their item-specific criterion below — deployed-fraction rising is
necessary but never sufficient.

### A-1 (`qp_cash_drag_lambda` 0 → 0.05)

- **Baseline:** current production value (λ=0), same session set, same admission universe.
- **Immutable sessions:** the shadow-replay session list must be frozen (recorded, dated,
  and committed) BEFORE the sweep runs — not selected after seeing which sessions favor the
  new value. Minimum 10 sessions per #228's existing framing; explicitly note (per Codex's
  finding) that 10 sessions can validate PLUMBING/CONSTRAINT-BINDING behavior only, NOT a
  60-day economic outcome — do not present the 10-session result as an economic verdict.
- **Estimand:** deployed-fraction change among ALREADY-admitted names at λ=0.05 vs λ=0,
  holding A-2/A-3/A-4 fixed; the QP must not force any entry past the existing
  conviction/veto gate stack.
- **Non-inferiority / risk thresholds (to be frozen at protocol sign-off, before shadow
  data is inspected):** turnover/round-trip count within [tolerance TBD] of baseline;
  realized-cost proxy within [tolerance TBD]; sector/single-name concentration caps still
  bind identically; drawdown no worse than the baseline window. Numeric tolerances are not
  yet frozen in this doc — they must be set and committed in the actual shadow-sweep PR
  before that PR's data is examined, not derived post hoc from the sweep's own results.
- **Stop rule:** abort the shadow sweep immediately if any non-degradation gate is breached
  mid-run (do not run to session-count completion to "see if it recovers").
- **Rollback:** λ reverts to 0 (current production value) — a single config-value revert,
  no state migration required.

### A-3 (one-share investability floor)

- **Baseline:** current production behavior (high-price names dropped when
  `share_price > target_notional`), same session set, same admission universe.
- **Immutable sessions:** same discipline as A-1 — frozen session list before the sweep
  runs, minimum 10 sessions, explicitly NOT an economic-outcome validation at that sample
  size.
- **Estimand:** rate of selection-by-share-price artifact occurrence (BLK-class names
  admitted at comparable rates to cheap names) vs baseline, holding A-1/A-2/A-4 fixed; AND,
  because this changes the selected-name set (not just ordering), the resulting change in
  concentration, cash use, and realized exposure must be measured and reported, not assumed
  zero.
- **Non-inferiority / risk thresholds:** same universal gate as A-1 (turnover/cost,
  concentration, drawdown non-degradation) — tolerances to be frozen at protocol sign-off,
  before shadow data is inspected.
- **Stop rule:** same as A-1 — abort immediately on any mid-run gate breach.
- **Rollback:** revert to the prior share-price drop behavior — a single config/logic
  revert, no state migration required.

## A-2's required dedicated evidence (replaces "D1 OR M3" as the gate)

A-2 stays deferred until a dedicated marginal-rank test exists, measuring — specifically for
the 4-vs-6 name-count comparison, not the aggregate model verdict — forward net return,
turnover/cost, concentration, and regime stability. This test does not exist yet; it is not
scoped further in this round of the doc (out of scope for RS-2's timing question) beyond
naming it as A-2's actual gate.

## Why this is the right risk order (theory, corrected)

TC repair (A-1/A-3) targets HOW admitted conviction is expressed, not WHICH names get money
in aggregate — but each individually still carries real (if likely smaller than A-2's)
incremental risk, which is why both now require their own preregistered shadow gate rather
than "enable now." Pool widening (A-2) raises exposure to the unvalidated μ-ordering itself;
the descriptive thin-margin observation above is a reason for caution on A-2, not a
statistical proof that the 4th–6th picks are indistinguishable from the 3rd. Prepare and
shadow the two lower-risk knobs first, under real preregistered protocols; leave the
higher-risk knob deferred behind its own dedicated evidence.
