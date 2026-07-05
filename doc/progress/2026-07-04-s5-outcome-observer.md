# S5 Path B: forward-outcome observer

STATUS: fixed and pushed (round 2, addresses Codex review).
WHAT: `outcome_observer.py` — scheduled job that populates `decision_outcomes`
      from forward-return data after the 60d horizon elapses.
WHY: S5 Path B (the spec's live-data path). Path A (bootstrap from
     candidate_scores) exists but is reconstructed/approximate. Path B reads
     the precomputed `ticker_forward_returns` derived table — a useful
     substrate, but NOT a first-hand realized-close-price fetch (see round 2).
HOW: Queries the ledger for decisions with no outcome row, joins entry prices
     from `candidate_scores` and forward returns from `ticker_forward_returns`
     in runs.alpaca.db, writes atomically (all 3 horizons in one row per
     INSERT OR IGNORE, only once all three are available). Idempotent,
     resumable.
TESTS: 22 tests covering pending detection, filtering, write semantics,
       dry-run, idempotency, atomic-write gating, backfill-on-full-data,
       multi-gate, multi-date.
CLI: `rq observe-outcomes [--runs-db PATH] [--dry-run] [--max-as-of DATE]`

ROUND 2 (Codex review — two bugs):
1. Partial-write poisoning: `observe_outcomes()` wrote a row whenever ANY of
   5d/20d/60d was present, not requiring all three. Since `write_outcomes()`
   is INSERT OR IGNORE on a fixed primary key (no update path) and
   `pending_decisions()` treats "row exists" as "done", a partial write
   permanently suppressed backfill of the missing horizons. Fixed: the
   observer now writes a row ONLY when all three horizons are available
   (`or` instead of `and` in the skip condition) — matching the module's
   own documented atomic-write contract. `test_partial_fwd_returns_accepted`
   (which blessed the buggy behavior) replaced with
   `test_partial_fwd_returns_not_written` +
   `test_becomes_pending_again_once_all_horizons_available`.
2. Data-source overclaim: `_load_forward_prices()` computed `target_date`
   but never queried by it — it reads `ticker_forward_returns` keyed by
   `run_date = as_of`, not a first-hand realized-close-price fetch at the
   target date. Corrected the module docstring, the function's docstring,
   and this doc's WHY/HOW to describe it accurately as reading a
   precomputed derived table, not "the actual forward returns"/authoritative
   realized prices.
