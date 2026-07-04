# Entry-timing policy module — shadow-evaluated, harvests the open-gap leak (sprint D2)

STATUS: design note for the shipped shadow module (`src/renquant_orchestrator/entry_timing_policy.py`).
DATE: 2026-07-03
PARENT: RFC #208 `doc/design/2026-06-30-renquant105-intraday-decisioning-architecture.md`
§5.3 (entry-timing policy), §11b (entry windows), §12 Stage 2, §9.3a (live authorization bar).
EVIDENCE BASIS: `doc/research/2026-07-02-s10-open-auction-is.md` (fills ARE the open auction;
fill-vs-day-VWAP true cohort +80bps point estimate, CI [−14.8, +165.2] — suggestive,
INCONCLUSIVE at 10 days; ~40bps/entry is the planning figure, not a validated one) and the
Phase −1 pivot (`doc/research/2026-06-27-renquant105-phase-minus-1-results.md`): the
controllable win is the **execution-timing residual**, explicitly NOT intraday directional
alpha.

## 1. What this is (and is not)

The 104 batch queues buys for the next open; the measured entry cost concentrates in the
opening print (S10). This module is the **code half** of harvesting that leak: a small,
pre-declared family of entry-timing policies, evaluated **in shadow only**, against the
same tick feed the Stage-1 shadow scheduler already runs on. It produces the evidence
corpus; it changes **no** live behavior.

- **NOT an alpha model.** Policies act on a frozen daily intent (class A, §6); they decide
  only WHEN within the §11b entry window, never WHETHER or HOW MUCH.
- **NO live wiring exists.** The only wired mode is shadow evaluation inside the
  shadow-only session scheduler (which itself has a runtime never-submit assertion). The
  live consumer is a separate Stage-2 decision under RFC #208 §9.3a.
- **Exits are never delayed.** Non-buy intents short-circuit to submit-now
  (exits-always-allowed, §10); the evaluator does not even track them.

## 2. The pre-declared policy family and frozen defaults

| Policy | Rule | Params (frozen defaults) |
|---|---|---|
| `baseline_open_delay` | submit at the first eligible tick after the intent arrives (open + entry_open_delay) — **the current behavior, the control** | — |
| `delay_fixed` | submit at `open + delay_minutes` | `delay_minutes = 30` |
| `gap_reversion_trigger` | gap-UP open: submit when mid retraces `retrace_frac` of the opening gap (`trigger = open_print − retrace_frac × (open_print − prior_close)`); gap-DOWN or \|gap\| < `min_gap_bps`: submit now (the leak is the inflated gap-up open); missing gap reference: submit now, flagged degraded | `retrace_frac = 0.5`, `min_gap_bps = 10` |
| `vwap_chase` | **explicitly OUT OF SCOPE** — needs order slicing (Stage 2+); selecting it in config is a config error that falls back to baseline | — |

**Hard deadline (every policy):** default = the §11b entry cutoff (`close −
entry_close_cutoff`, scaled to the calendar session). A still-waiting policy **degrades to
submit-now** on the last tick that can still act (`now + tick_seconds >= deadline`) —
participation is never sacrificed silently; the degradation is recorded on the row
(`degraded: true`, reason `hard_deadline_degraded_submit_now`).

## 3. Config — `intraday_decisioning.entry_timing.{...}` (pinned strategy config)

| Key | Default | Meaning |
|---|---|---|
| `policy` | `baseline_open_delay` | the SELECTED policy (informational in shadow; what a future Stage-2 consumer would read) |
| `delay_minutes` | `30` | `delay_fixed`'s T |
| `retrace_frac` | `0.5` | fraction of the opening gap to retrace |
| `min_gap_bps` | `10` | \|gap\| below this ⇒ no-gap ⇒ submit now |
| `deadline_minutes_before_cutoff` | `0` | hard deadline = entry cutoff − this |
| `prior_close_refs_path` | absent | JSON `{ticker: prior_close}` — the gap reference; absent ⇒ reversion rows record degraded submit-now (honest, never guessed) |
| `shadow_log` | `logs/renquant105_pilot/entry_timing_policy_shadow.jsonl` | output override |

Absent section ⇒ all defaults (baseline). **Any malformed value forces `policy` back to
baseline** (errors collected in `config_errors`, logged) — a typo can never select a
non-control policy.

## 4. Shadow evaluation architecture

The scheduler (`intraday_session_scheduler`) gained a minimal additive seam: an optional
`tick_observer` invoked with each persisted shadow tick record (AFTER the never-submit
assertion and AFTER the record is appended), plus a per-tick `windows` stamp (the §11b
windows, so consumers do window/deadline math without re-deriving the calendar). Observer
exceptions are counted in the session manifest (`tick_observer_errors`) and swallowed —
a diagnostic surface may never halt the shadow decision loop.

`ShadowEntryTimingEvaluator` consumes that seam: BUY entry intents from
`decisions.intents` define the frozen daily intents (arrival tick = the earliest any
policy may act); per-tick mids come from `inputs.live_state.prices` (the class-D quotes
the loop itself decided on). One row per `(session, ticker, policy)`, idempotent append,
schema-versioned (`rq105-entry-timing-policy-v1`); unresolved cells are written censored
by cause at flush, never imputed. A `replay` CLI re-runs the SAME evaluator code path over
a persisted shadow decision log (backfills already-collected sessions; a session manifest
supplies windows for logs predating the stamp).

**Counterfactual method (pre-declared):** all policies are priced on the SAME mid series,
mid-as-fill, zero modeled slippage — consistent with the `entry_timing_shadow` collector's
frozen `arrival_mid_reference__zero_modeled_shortfall` fill model. `saved_vs_baseline_bps
= (baseline_mid − policy_mid) / baseline_mid × 1e4` (buys; positive = cheaper than the
control). This measures the **between-policy timing differential on one feed**; it does
not re-measure the absolute leak vs broker fills (that is S10 / the paired-IS harness) and
carries the IEX-vs-SIP quote-quality caveat of RFC #208 §11 like every other class-D
consumer.

Relation to the existing `entry_timing_shadow` collector: the collector replays candidate
policies offline over the #216 tick feed (vwap-cross / opening-range / pullback family);
this module is the **in-loop decision surface** — the policy family is re-anchored on the
S10-measured gap-up leak, adds the hard-deadline participation guarantee, and logs
baseline-anchored counterfactual costs, which the collector deliberately does not compute.

## 5. The comparison report — the parameter-tuning surface

`python -m renquant_orchestrator.entry_timing_policy report [--log …] [--json]` aggregates
the shadow log per policy: participation rate, degradation count, and the
`saved_vs_baseline_bps` distribution (mean/median/p25/p75/min/max). It renders **no
verdict**; picking the policy + params later = reading this report against §6.

## 6. Pre-registered selection protocol (what shadow evidence picks the winner)

Frozen BEFORE the corpus exists. Rows self-identify their exact parameterization via
`config_fingerprint`; changing any parameter restarts the corpus for that policy.

- **Corpus floor:** ≥ **20 disjoint pilot sessions** (matches the collector's
  `min_pilot_sessions`) AND ≥ **30 priced rows per candidate policy**.
- **Primary endpoint:** per-session **median** `saved_vs_baseline_bps` (median, not mean —
  S10 measured strong right-skew), analysis unit = session.
- **Winner rule** (a candidate may be proposed to replace baseline iff ALL hold):
  1. date-clustered bootstrap 95% CI lower bound of the session-median saved bps **> 0**;
  2. participation = **100%** of resolved intents (degradation is acceptable and counted;
     silent non-participation is disqualifying);
  3. degradation rate ≤ **30%** (a policy that mostly degrades is baseline in disguise —
     its apparent edge would come from an unrepresentative minority path);
  4. evaluated on the frozen params of §2 — **no post-hoc parameter tuning against the
     same corpus**; a re-parameterized policy starts a new corpus.
- **Multiplicity:** two non-control candidates ⇒ Holm–Bonferroni across the family
  (consistent with the collector's frozen design).
- **Selection ≠ enablement.** A winning policy yields a **proposal**, not a config flip:
  live wiring is a Stage-2 decision under RFC #208 §9.3a — separate PR, Codex adversarial
  review, rollback = single config revert to `baseline_open_delay`, operator notified
  (2026-07-02 delegation standard for capital-risk changes).

## 7. Non-goals / out of scope

- `vwap_chase` (order slicing) — Stage 2+.
- Any change to gate admission, sizing, or the exit path.
- Any absolute execution-quality (implementation-shortfall) claim — deferred to §9.4's
  experiment on the paired-IS corpus.
- Live wiring of ANY policy, including baseline behind a flag — there is nothing to wire;
  the module has no submit path.
