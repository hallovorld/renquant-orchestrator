# S5 Path B: forward-outcome observer

STATUS: PR opened.
WHAT: `outcome_observer.py` — scheduled job that populates `decision_outcomes`
      from forward-return data after the 60d horizon elapses.
WHY: S5 Path B (the spec's live-data path). Path A (bootstrap from
     candidate_scores) exists but is reconstructed/approximate. Path B writes
     authoritative outcomes from the actual forward returns table.
HOW: Queries the ledger for decisions with no outcome row, joins entry prices
     and forward returns from runs.alpaca.db, writes atomically (all 3 horizons
     in one row per INSERT OR IGNORE). Idempotent, resumable.
TESTS: 21 tests covering pending detection, filtering, write semantics,
       dry-run, idempotency, partial returns, multi-gate, multi-date.
CLI: `rq observe-outcomes [--runs-db PATH] [--dry-run] [--max-as-of DATE]`
