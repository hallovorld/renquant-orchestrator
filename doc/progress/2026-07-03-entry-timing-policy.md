# Progress — entry-timing policy module, shadow-evaluated (sprint D2 item 1)

Date: 2026-07-03
Scope: renquant105, orchestrator-owned shadow surface. Design note:
`doc/design/2026-07-03-entry-timing-policy.md`. Parent: RFC #208 §5.3/§11b/§12.
Evidence basis: S10 open-auction IS memo (fills ARE the open auction; the entry leak is
the planning-grade ~40bps/entry figure, absolute magnitude still INCONCLUSIVE at 10 days)
+ the Phase −1 pivot to the execution-timing residual (not directional alpha).

## What shipped

- `src/renquant_orchestrator/entry_timing_policy.py` — (1) a PURE policy-decision
  function over a pre-declared family: `baseline_open_delay` (the control = current
  behavior), `delay_fixed` (T configurable), `gap_reversion_trigger` (submit on a
  `retrace_frac` retrace of a gap-up open; gap-down/no-gap ⇒ submit now), `vwap_chase`
  declared OUT OF SCOPE (order slicing, Stage 2+). Every policy carries a HARD deadline
  (default = the §11b entry cutoff) degrading to submit-now with the degradation logged —
  participation is never sacrificed silently. (2) `ShadowEntryTimingEvaluator` — the
  default and ONLY wired mode: consumes the shadow scheduler's tick records and logs what
  each policy WOULD have done + the counterfactual cost vs baseline (same feed,
  mid-as-fill) to schema-versioned
  `logs/renquant105_pilot/entry_timing_policy_shadow.jsonl` (idempotent; censored cells
  recorded by cause). (3) `report` CLI — per-policy saved-bps distributions /
  participation / degradations, the parameter-tuning surface; `replay` CLI backfills from
  persisted shadow logs.
- `src/renquant_orchestrator/intraday_session_scheduler.py` — minimal additive seam:
  optional `tick_observer` (invoked post-assert, post-append; exceptions counted in the
  manifest and swallowed — a diagnostic may never halt the loop), per-tick `windows`
  stamp, and CLI wiring of the evaluator (flush in `finally`). No decision-path change.
- Config: `intraday_decisioning.entry_timing.{policy, delay_minutes, retrace_frac,
  min_gap_bps, deadline_minutes_before_cutoff, prior_close_refs_path, shadow_log}` —
  absent ⇒ baseline; any malformed value fails safe to baseline with errors collected.
- Pre-registered selection protocol (design note §6): ≥20 disjoint sessions, ≥30 priced
  rows/policy, per-session median saved-bps with date-clustered bootstrap CI lower bound
  > 0, participation 100%, degradation ≤30%, Holm–Bonferroni over the two candidates;
  selection yields a PROPOSAL — live wiring stays a separate Stage-2 §9.3a decision.

## Explicitly NOT in this PR

No live wiring (no submit path exists in the module); no change to gates/sizing/exits
(non-buy intents are never delayed); no absolute IS claim (S10/§9.4 own that).

## Verification

- `tests/test_entry_timing_policy.py` (29 tests): decision matrix on synthetic fixtures
  (gap-up reverting / gap-up running / gap-down / no-gap), deadline degradation boundary
  (`now + tick >= deadline`), hand-computed counterfactual ((105−102.5)/105×1e4 =
  238.095 bps), schema round-trip + idempotent re-append, flag-absent ⇒ baseline +
  malformed-config fail-safe, report/replay CLIs, and the scheduler seam end-to-end
  (evaluator inside a full fake session; exploding observer leaves the session
  `completed` with `tick_observer_errors` counted).
- Full suite green: 1500 passed, 3 skipped.
- CLI exercised end-to-end on a synthetic session (replay → report; reversion +107.8 bps
  vs baseline on the fixture path).
