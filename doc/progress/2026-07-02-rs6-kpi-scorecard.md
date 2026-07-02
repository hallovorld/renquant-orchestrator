# RS-6 weekly KPI scorecard — research PR

STATUS:   research deliverable (RS-6 of the unified 107 master plan #231): script + first
          committed measurement + standing definitions. Read-only against all production
          inputs; no code/config/broker/risk/sizing change.
REVISION: r1.
WHAT:     `scripts/kpi_scorecard.py` — one read-only command emitting a dated JSON scorecard
          for every #231 §0 state-vector metric (each with value + source + method +
          measured_at; every metric degrades to {"status":"unavailable","blocker":...}
          instead of crashing) to `doc/research/evidence/kpi_scorecards/kpi_<date>.json` +
          a compact printed table. `doc/research/2026-07-02-rs6-kpi-scorecard.md` — the
          per-metric definition table (metric | source | exact query/method | cadence |
          owner), the first scorecard's values, and 7 stated limitations. First measurement
          committed: `doc/research/evidence/kpi_scorecards/kpi_2026-07-02.json`.
WHY/DIR:  #231 §0's state vector and §4's standing measurement plan name the metrics but had
          no runnable instrument — "gate-verdict age" and "ledger coverage" were prose facts,
          not queries. RS-6 freezes exact, reproducible definitions BEFORE the tasks they
          read out (S4 verdict, S5 ledger, M4 recentering, N1/N2 collectors) land, so their
          ACs are judged by a pre-existing instrument rather than post-hoc measurement.
          Definition constants are pinned in the script; changing one requires a PR touching
          the research doc, not a silent edit.
EVIDENCE: first scorecard (2026-07-02, all 8 metrics ok, none unavailable):
          deployed_fraction 0.214 (trailing-5 0.223; target ≥95% incl. sleeve) ·
          floor_gap_vs_spy +3.48pp of book foregone (46 sessions 04-24→07-01, avg cash
          weight 72.1%, SPY span +4.5%; descriptive, not annualized per RS-1 §1) ·
          gate_verdict_age "mute since 2026-05-18 (45 days)" (freshest serving-artifact
          stamp is diagnostic_only=true/passed=false, run_at 06-22; gate_verdicts table
          0 rows) · ledger_coverage 86.2% fwd_20d over 5,199 aged rows (S5 AC ≥95%) ·
          pit_accrual_days 1 (2026-07-02) · collector_liveness live (pilot ticks 0.01h,
          rq105 quote log 0.42h but zero-byte-flagged) · calibrator_sign_laundered 44
          (2026-07-01 run — counter found in pipeline_runs.counters_json, NOT pending-S5)
          · buy_side_decision_tc 0.288 mean (SE 0.167, n=4 measured of 10 canonical runs;
          post-retrain runs unmeasurable, ≤2 admission survivors).

          Canonical evidence-block subfields (`doc/AGENT-RETROSPECTIVE.md` §4(b)):
          ```
          artifact:      doc/research/evidence/kpi_scorecards/kpi_2026-07-02.json
                         (+ scripts/kpi_scorecard.py, the generating instrument)
          prod or exp:   experiment / research readout — reads prod stores (runs.alpaca.db
                         mode=ro, serving artifact JSON, log mtimes, snapshot dirs) but
                         changes nothing live
          existing data: no prior committed KPI scorecard exists; the #231 §0 table cited
                         one-off measurements (25% deployed 07-01, "gate mute since 05-18",
                         44/90 laundered) — this PR's values are consistent with all of
                         them under pinned definitions
          best-known?:   yes for the definitions (first standing instrument); the TC number
                         is explicitly EXPLORATORY (POC-S-TC round-3 caveats apply
                         verbatim, imported not re-implemented)
          scope:         weekly standing readout of the state vector, vs no existing
                         instrument; floor_gap_vs_spy deviates from RS-1 §1's snapshot
                         (72.1%/3.48pp vs 75.5%/2.88pp — RS-1 didn't pin canonical-row
                         selection; this script does, and the delta is stated in the
                         research doc §3.2 rather than reconciled away)
          ```
          [VERIFIED — ran `scripts/kpi_scorecard.py` once in this session against the live
          read-only stores; every number above is from the committed JSON, re-printed from
          the file (not from memory); the wf_gate_metadata stamp fields were read directly
          from the serving artifact; sqlite opened mode=ro.]
NEXT:     Codex review. Then: run weekly on a trading day (candidate for the existing
          weekly-monitor launchd pattern — scheduling is a separate ops PR, not this one);
          §4 monthly re-baseline reads the accumulated JSONs; when S4/S5/M4 land their ACs
          are read from THIS instrument; the zero-byte rq105 quote log wants a look at the
          next close; buy_side_decision_tc graduates to a per-run ledger series with S5.

## Round 2 (Codex review: false-confidence metrics)

**Finding.** `collector_liveness` scanned only two directories for the newest-mtime file —
the committed r1 evidence called the system live from an empty quote-wrapper log and a
censored intermediate ticks file, not each collector's actual canonical data output.
`pit_accrual_days` counted dated directory NAMES without validating the 4-manifest
publication contract, so a partial/crashed directory would have inflated an irreversible
accrual count. The scorecard itself overwrote a same-date JSON non-atomically with no
input/run/content hashes — not independently reproducible.

**Fix.**
- `collector_liveness` now imports `rq105_liveness_check`'s own `_data_outputs()` (exact
  per-collector path resolvers, never hardcoded/guessed) and `_data_output_fresh()`
  (validates the last JSONL row's own `date` field, not directory mtime) — single-impl
  rule, same pattern as `buy_side_decision_tc`'s reuse of `poc_transfer_coefficient`. Every
  collector is reported INDEPENDENTLY; the aggregate is `live` only if every one passes. A
  non-session `as_of` is reported as its own state (`not_a_session_day`), never conflated
  with live/stale.
- `pit_accrual_days` now runs `pit_liveness_check.check_snapshot()` (imported unchanged)
  against EVERY dated directory and only counts days that pass the full 4-endpoint
  publication contract. Rejected (partial/invalid) days are listed by name with their
  specific problems, not silently dropped.
- `_canonical_daily_live` gained a full-run filter. **Round-2a correction**: my first pass
  filtered on `pipeline_runs.n_candidates >= 80`, which looked right against the column
  name but is WRONG — verified against `runs.alpaca.db` directly, `n_candidates` is 0 on
  every one of 1441 real live rows, not a populated proxy for run size in this schema.
  Fixed to join `candidate_scores` and count, the same way
  `poc_transfer_coefficient._canonical_daily_runs()` already does (that script never used
  `n_candidates` either — should have checked first). Caught by actually re-running the
  script against real read-only production stores after the first pass, which surfaced
  `deployed_fraction`/`floor_gap_vs_spy` going UNAVAILABLE ("no rows with n_candidates >=
  80") even though real full runs obviously exist.
- `metric_deployed_fraction`'s headline `value` now reads the latest CANONICAL FULL run
  (via the corrected `_canonical_daily_live`), not the raw latest `pipeline_runs` row by
  `created_at` — an intraday monitor pass can be more recent than the day's full run and
  must never silently supersede it.
- Reproducibility: `_generator_sha256()` (content hash of the script itself — a
  self-referential `generator_commit` is a chicken-and-egg bug already hit once this
  session, #430), `_canonical_content_hash()` (sorted-key, fixed-float-precision hash of
  the metrics payload alone, excluding wall-clock `measured_at` — two runs against
  identical underlying state now provably produce the identical hash), `_atomic_write_json`
  (temp file + fsync + rename, same pattern as #236's batch-scores bundle fix), and
  `inputs.db_snapshot`/`spy_parquet_sha256`/`serving_artifact_sha256` recording exactly
  which source-artifact state fed this specific scorecard.
- New `tests/test_kpi_scorecard.py` (8 tests): the 4 cases Codex named explicitly
  (unrelated-newest-file false green, partial-PIT-dir exclusion, same-day-rerun content-hash
  idempotency, full-run-supersedes-later-intraday-partial run-selection semantics) plus
  atomicity and hash-stability checks.

**Re-measured (2026-07-02, real read-only production stores, corrected methodology):**
`deployed_fraction` 0.2468 (trailing-5 mean 0.2051 — differs from r1's 0.214/0.223 because
the full-run filter now genuinely excludes intraday partial rows from the canonical series,
not because of a data change) · `floor_gap_vs_spy` -1.11pp over 10 sessions (down from r1's
46-session/+3.48pp figure — r1's `_canonical_daily_live` was NOT actually filtering to full
runs at all despite its docstring's claim, so it was averaging in many intraday partial-run
sessions; 10 sessions is the genuinely full-run-only canonical series) · `pit_accrual_days`
1, contract-validated (down from r1's raw directory count — full production history for
this metric is still thin, most of the visible dated dirs are pre-collector test artifacts
that correctly fail the 4-manifest check) · `collector_liveness` now correctly reports
`stale` (r1's directory-mtime scan had reported `live` from the unrelated files codex
identified). All other metrics unchanged. 64/64 tests pass across this file plus the
touched sibling test files (`test_rq105_collector_scheduling.py`,
`test_pit_snapshotter_scheduling.py`, `test_poc_transfer_coefficient.py`).

Evidence JSON regenerated in place: `doc/research/evidence/kpi_scorecards/kpi_2026-07-02.json`.

## Round 3 (Codex review: DB provenance + stale review surface)

**Finding.** `runs.alpaca.db` is a mutable, continuously-written SQLite file; the round-2
fix stamped only its size+mtime, which cannot prove which rows a metric actually read
(two DB states can share size+mtime while differing in content) and doesn't bind the exact
canonical run set used. `output_content_sha256` (over the metrics payload) proves
run-to-run OUTPUT reproducibility but was being relied on as if it also proved source
provenance, which it doesn't. `pit_accrual_days`/`collector_liveness` recorded that a check
passed but not a content anchor for what was checked. The module docstring and PR body
still described the pre-round-2 directory-mtime/plain-count logic and pre-round-2 values.

**Fix.**
- New `_extract_hash()` — canonical sorted-key/fixed-float hash of a pandas DataFrame or row
  list, same family as `_canonical_content_hash`. Wired into every DB-derived metric:
  `deployed_fraction`/`floor_gap_vs_spy` hash the canonical FULL-run extract and record the
  full list of canonical run_ids used (not just the one picked); `ledger_coverage` hashes
  its full ~5,199-row aged extract; `calibrator_sign_laundered` hashes the raw
  `counters_json` string directly; `buy_side_decision_tc` hashes its `per_run` breakdown
  plus records `canonical_run_ids`.
- `pit_accrual_days` now hashes the actual byte content of each valid day's 4 validated
  manifests (`valid_day_manifest_sha256` per day, `accrual_extract_sha256` overall) — proves
  which manifest bytes were read as "valid," not just that `check_snapshot()` said so.
- `collector_liveness` now reads and hashes the same 8KB tail each collector's freshness
  check consumed (`tail_read_sha256`), correctly `null` only when the file is genuinely
  missing/empty (nothing to hash) — verified against real production data: 2 of 3 covered
  collectors show `null` (missing files), 1 shows a real hash.
- `db_snapshot`'s size+mtime fields are kept (a cheap sanity signal) but now carry an
  explicit `note` stating they do NOT prove row-level provenance — that's the per-metric
  `*_extract_sha256`/`*_sha256` fields' job now.
- Module docstring rewritten (was still describing the pre-round-2 mtime-scan/directory-count
  logic); added a top-level "Provenance" paragraph explaining the source-vs-output hash
  distinction.
- PR body corrected to the round-2 regenerated values (`deployed_fraction` 0.2468,
  `floor_gap_vs_spy` -1.11pp/10 sessions, `collector_liveness` stale) — was still showing
  pre-fix numbers and "all 8 metrics ok / collectors live."

**New tests (10 total, up from 8):**
`test_extract_hash_distinguishes_same_size_same_mtime_different_content` — the exact case
Codex named: two SQLite files forced to identical size (zero-padded) and identical mtime
(`os.utime`) but different `cash` values in their one `pipeline_runs` row; asserts
`_extract_hash` on the canonical extract produces different hashes for the two, proving the
provenance mechanism is genuinely content-based, not a disguised size/mtime proxy.
`test_pit_accrual_manifest_hash_changes_with_manifest_content` — same principle for the PIT
manifest hash: two otherwise-identical valid days with one differing manifest field produce
different `accrual_extract_sha256` values.

**Re-verified end to end** against real read-only production stores
(`RQ_ROOT=/Users/renhao/git/github/RenQuant`): all 8 metrics still `ok`, values unchanged
from round 2 (0.2468 / -1.11pp / 86.2% / 1 / stale / 44 / 0.288), new hash fields genuinely
populated in the regenerated `kpi_2026-07-02.json` (confirmed by direct inspection, not
assumed). 10/10 new-file tests pass; 66/66 across this file plus the touched sibling test
files.
