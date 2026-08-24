# S3-P4a: the intraday entry DECISION core — pure, guarded, inert

STATUS:   delivered. Third implementation PR of the Stage-3 ladder. Decides,
          never executes: no broker import, no order path, no scheduler
          wiring, nothing reads it yet. The execution leg is S3-P4b; the live
          flip is S3-c and remains an explicit operator ask.
WHAT:     `intraday_entry_decision.py` — v1 admission = batch ∩ intraday
          (intraday can VETO a batch admission, never create one; a censored
          quote is a veto, fail closed), plus every approved-design guardrail
          as data (frozen Guardrails: 2 entries/day, $1,500/day, 15-min
          session edges, SHARED max_concurrent_positions, halt env), applied
          unconditionally in fixed order. Budgets hold BY CONSTRUCTION — the
          plan cannot exceed them for an executor to catch. Every non-entered
          name carries exactly one named reason (the #598/#599/#600 lesson at
          the source).
WHY/DIR:  shipping the decision core alone keeps the capital-adjacent surface
          reviewable in isolation, and the S3-b shadow window can exercise the
          exact production decision path with zero order risk.
EVIDENCE:
  artifact:      the module + 21 hermetic tests.
  prod or exp:   exp — pure functions; the orchestrator suite covers tests/
                 wholesale.
  existing data: 8 targeted mutants (halt, window, both entry budgets,
                 notional, shared cap, batch gate, censor gate), each
                 compile-checked first so a syntax-broken mutant cannot count
                 as "killed" — ALL KILLED [VERIFIED]. Three successive fixture
                 revisions of one test each tripped a DIFFERENT real guardrail
                 (notional, then shared cap) before passing — recorded in the
                 test as evidence the limits compose.
  best-known?:   yes — guardrails as frozen data mean a caller cannot omit
                 one; the plan records which Guardrails produced it.
  scope:        one pure module + tests. NOT wired anywhere.
REVIEW:    codex (haorensjtu-dev).

## Review round 2 (codex, 2026-08-24) — the input contract

Four findings, all real for a capital-adjacent core, all fixed.

**The design decision under them:** two kinds of bad input arrive here and they
get OPPOSITE treatment.

* **market data** — a NaN intraday score, an unusable mid — is expected to be
  bad sometimes. It rejects the NAME, with its own reason, and the loop
  continues. That is ordinary operation on a live tape.
* **plumbing** — a NaN per-entry notional, a negative counter, incoherent
  guardrails, a naive timestamp — is the caller breaking the contract, and
  raises `InvalidDecisionInput`. There is no correct plan to return: a NaN
  notional does not reject one name, it makes EVERY budget comparison False, so
  the plan would look guarded and not be. For this module that is the worst
  outcome available.

1. **Non-finite values passed every comparison.** `x <= 0.0` is False for NaN,
   so a NaN score was admitted and sorted on, a NaN mid became the order's
   `limit_price`, and a NaN `per_entry_notional` defeated the daily budget
   (`0.0 + nan > 1_500.0` is False). Non-finite market data now rejects the name
   under its own reason — `intraday_score_not_finite`,
   `intraday_mid_not_finite`, `batch_expected_return_not_finite` — and
   non-finite/non-positive sizing, negative counters and incoherent guardrails
   raise.

   Guardrail validation also refuses edges that consume the whole session: a
   limit that blocks every tick is indistinguishable from a broken one.

2. **Duplicate and blank identities.** `rejections` is keyed by ticker and each
   intent names one, so "exactly one outcome per name" was only true if names
   were unique. Two rows for one ticker produced two intents — double-consuming
   the daily budget for a single position — or silently overwrote one row's
   rejection. EVERY occurrence of a duplicated name is now rejected rather than
   deduplicated to a winner: picking a winner invents a rule the design does not
   state, inside a capital-adjacent path, and a caller passing two rows for one
   ticker has an upstream bug that should surface.

3. **`now_et` was ET by name only.** An aware UTC value was compared by wall
   clock with no conversion — 13:00 UTC read as 13:00 ET, comfortably inside the
   entry window, when in ET it is 09:00 and the market has not opened. Naive
   values were accepted with their zone unknowable. Aware timestamps are now
   normalised to `America/New_York`; naive ones raise.

4. **The committed strategy snapshot** was regenerated. The diff is one line —
   `+ "intraday_entry_decision"` — read rather than taken on trust from
   `--update`.

VERIFICATION (round 2):
  60 passed. Each guard mutation-verified INDIVIDUALLY, because a single
  all-or-nothing revert only proves the tests import new symbols:
    drop the ET normalisation      ->  5 failed
    drop state validation          -> 13 failed
    drop guardrail validation      ->  7 failed
    drop the duplicate check       ->  3 failed
    drop the finite market-data checks -> 7 failed
    restored                       -> 60 passed
  [VERIFIED 2026-08-24]

  `test_snapshot_not_stale` passes. `tests/test_shadow_ab_daily_script.py` shows
  13 failures both WITH and WITHOUT this change on the pristine branch tip, and
  does not read `data/strategy_snapshot.json` — pre-existing, not this diff.
