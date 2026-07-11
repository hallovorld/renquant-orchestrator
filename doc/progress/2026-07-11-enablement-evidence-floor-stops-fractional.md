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
