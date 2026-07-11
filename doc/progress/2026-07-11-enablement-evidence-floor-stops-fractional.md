# Enablement evidence packet: floor / stops / fractional (s104 #55/#56)

STATUS:    complete (evidence packet; no code, no config, no production writes)
WHAT:      Assembles the evidence Codex demanded before approving strategy-104 #55
           (one-share floor + software_stops enable) and #56 (fractional enable):
           an offline prod-ledger floor ON-vs-OFF replay, the software-stop
           registry-freshness operational test (12/12 vs the pinned runtime code),
           a stage-3/RS-2 gap scorecard, and the exact operator-action shortlist.
WHY/DIR:   Codex CHANGES_REQUESTED both PRs; the approved cash-drag sequence is
           design/evidence first. D7 (#444) + RS-2 define the gates; this packet
           measures what already passes them and names what cannot pass yet.
EVIDENCE:  doc/research/2026-07-11-enablement-evidence-floor-stops-fractional.md
           (+ doc/research/evidence/2026-07-11-enablement/ scripts + result JSONs
           + renquant-artifacts `enablement-floor-replay-20260711` sealed bundle).
           Key numbers (r2, corrected): floor replay 6/11 unambiguous canonical
           sessions rescued, Δ$392–$1,356/session, mean $911 (07-02 replay
           $1,356.18 cross-validates the recorded $1,355); ASML correctly
           cap-refused; shadow floor observations since arming: 0; two-arm A/B
           valid sessions: 0 (pinned s104 runtime dirty — logs/, now fixed by
           orchestrator#470); stops operational test 12/12 PASS, pager scheduled:
           NO; fractional enable today would fail-close ALL buys (live broker
           adapter lacks the capability-gate methods).
NEXT:      Codex re-review of the r2 packet; operator executes the remaining
           shortlist (§6 of the research doc) — floor gate decision, pager
           arming + SLA demo, machine-death signature, broker wiring PR
           (in flight), read-only broker verification, pin bump past s104 #54.
           #55/#56 stay un-merged until then.

## Notes

- READ-ONLY discipline: ledger queried from a scratchpad copy of the runs DBs;
  registry tests ran against a scratchpad registry importing the pinned runtime
  module; the only prod-path CLI invocation was the liveness checker in its
  read-only "no registry" branch. No git commands in the umbrella or primary
  checkouts; this PR was produced from a scratchpad clone.
- The replay is the packet's central instrument because the armed shadow cannot
  express the RS-2 §A-3 estimand as written (ops shadow + both two-arm configs run
  hf_patchtst; prod runs xgb; both two-arm configs already carry floor=ON).

## r2 addendum (2026-07-11, this revision)

Codex review found r1's floor-replay evidence non-reproducible (hardcoded
`/private/tmp` scratch + `/Users/renhao/.../RenQuant` absolute paths in the
committed scripts/JSON) and outcome-selected (per-date representative run
picked by `max(deployment_delta_usd)` among up to 36 same-day
`pipeline_runs` rows — mostly zero-candidate renquant105 intraday
decisioning ticks — with a denominator counting all 28 calendar dates
rather than the same population as the numerator).

Fixed:
- **Sealed evidence**: `renquant-artifacts#15` adds the fingerprinted,
  content-addressed bundle (`enablement-floor-replay-20260711`) — every
  `candidate_scores`/`pipeline_runs` row and OHLCV close this replay
  touches, inline. No DB/OHLCV access needed to verify.
- **Selection bias**: `floor_replay.py` now predeclares exactly one
  canonical run_id per date via a structural, outcome-blind rule (the
  unique `pipeline_runs` row with `n_candidates>0` that date) and fails
  closed (EXCLUDED) on 0 or 2+ such rows rather than picking by outcome.
  3 dates (06-09, 06-23, 06-29) are now excluded as genuinely ambiguous
  (each had 2 same-day candidate-scoring runs); 14 dates had no daily-full
  candidate-scoring session at all.
- **Reproducibility**: `floor_replay.py` gained `--extract` (parameterized
  `--db-path`/`--ohlcv-dir`, no hardcoded paths, writes the sealed bundle)
  and a default pure-compute mode (`--bundle <path>`, no DB/OHLCV/umbrella
  access at all). `stops_operational_test.py` now takes required
  `--umbrella-root`/`--scratch-dir` CLI args instead of hardcoded paths;
  reran cleanly, same 12/12 pass outcome.

Corrected result: 6/11 unambiguous canonical dates rescued (r1's
uncorrected framing: 7/28). Per-date dollar math is otherwise unchanged
for every date that survives the corrected filter — mean $911.13 (r1:
$916.71, entirely the loss of 06-29's $950.17, which is now correctly
excluded as ambiguous rather than picked by outcome).

## r3 (2026-07-11): run_type filter, sealed config provenance, n_buys check

Codex re-review of r2's sealed bundle found two more validity gaps:

1. The canonical query never constrained `run_type='live'` — a shadow or
   other candidate-scoring run could in principle become the claimed
   production representative solely because `n_candidates>0`. Fixed:
   both the date-population and canonical-candidate queries in
   `build_canonical_manifest` now explicitly filter `run_type='live'`,
   sealed per canonical row. No-op on this dataset (all 915 in-window
   `pipeline_runs` rows are already `'live'`), but now a real, checked
   constraint rather than an unstated assumption.
2. `REGIME_CAP`/`RESERVE` were a hardcoded table with no fingerprinted
   proof they were the operative pinned strategy-104 config — and this
   genuinely mattered in principle: `BULL_CALM.max_position_pct` was
   **0.15 at the window's start (2026-06-01) and dropped to 0.12 on
   2026-06-09** (commit `5ce58af`). A naive "use current config"
   assumption would have been silently wrong for part of the window.
   Fixed: new `resolve_regime_sizing_config()` resolves, per canonical
   run, the EXACT `renquant-strategy-104` git commit active at that
   run's `created_at` (via `git log --before=<ts>`), extracts
   `regime_params[regime].{max_position_pct,cash_reserve_pct}` from that
   commit's `configs/strategy_config.json`, and seals both the commit
   sha and the file's content sha256 alongside the extracted values.
   `compute_replay` now reads `cap_pct`/`res_pct` from each run's sealed
   `regime_sizing_config`, never a hardcoded table. All 11 canonical
   dates happen to postdate the 06-09 change, so the resolved value is
   0.12/0.0 throughout and the corrected numbers are unchanged — but
   this is now a proven per-run fact, not an assumed constant.
3. Added an explicit `n_buys==0` check the "zero admission distortion"
   claim structurally depends on but r1/r2 never verified. A canonical
   run with `n_buys != 0` is now excluded (`excluded_nonzero_n_buys`),
   not silently assumed non-displacing — this replay does not
   reconstruct normal-buy cash state for that case. All 17
   candidate-scoring runs in the window (not just the 11 canonical ones)
   already have `n_buys=0`, so nothing is newly excluded.

`renquant-artifacts#15`'s `RUN-LOCK.json` was re-sealed with the corrected
bundle (`run_type`, `regime_sizing_config` per run, `strategy_config_repo`
input, `excluded_nonzero_n_buys` in results); fingerprint updated to
`sha256:db81fa1...` and `STORE-MANIFEST.json`/the registry entry updated
to match — verified via `renquant-artifacts`' own
`test_store_manifest.py`/`test_no_large_artifacts.py` (hash-consistency
checks pass against the recomputed fingerprint).

Both PRs' framing corrected per Codex's explicit wording: this is
**retrospective exploratory replay evidence**, not an RS-2 preregistration
substitute — it can inform a recorded deviation decision but cannot
itself satisfy the preregistered gate.

Numbers unchanged from r2 (6/11 unambiguous canonical dates, $392.13–
$1,356.18/session, mean $911.13) — now independently verifiable from
sealed, fingerprinted inputs rather than an unverified table + an
unstated filter.

Tests: orchestrator suite unaffected (`floor_replay.py` has no dedicated
test file; verified via direct re-extraction + diff against r2's
`floor_replay_result.json` — same 11/6/6 counts and identical per-date
dollar deltas; the JSON structure itself gained the new sealed fields
(`regime_sizing_config`, `excluded_nonzero_n_buys`), so it is not a
byte-identical file, but the underlying replay result is numerically
unchanged). `renquant-artifacts` `pytest tests/` — 22 passed.
