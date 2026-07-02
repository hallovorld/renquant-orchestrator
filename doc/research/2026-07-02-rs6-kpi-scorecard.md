# RS-6: weekly KPI scorecard — exact, runnable definitions for the #231 §0 state vector

STATUS: research deliverable (RS-6 of the unified 107 master plan). One command, read-only,
committed with its first measurement. Definitions here are the STANDING weekly instrument;
the master plan's §4 monthly re-baseline consumes this series.
DATE: 2026-07-02

## 0. The one command

```bash
/Users/renhao/git/github/RenQuant/.venv/bin/python scripts/kpi_scorecard.py
# optional: KPI_AS_OF=YYYY-MM-DD  RQ_ROOT=/path/to/RenQuant
```

Writes `doc/research/evidence/kpi_scorecards/kpi_<YYYY-MM-DD>.json` (every metric with
`value` + `source` + `method` + `measured_at` + `status`) and prints a compact table.
All inputs read-only; the sqlite DB is opened `mode=ro` (falls back to
`mode=ro&immutable=1` for sandboxed readers that cannot create the WAL `-shm` file — the
mode used is recorded in the JSON). Every metric degrades to
`{"status": "unavailable", "blocker": ...}` instead of crashing, so a broken input becomes
a reported fact on the scorecard rather than a missing scorecard.

## 1. Per-metric definitions

| Metric | Source | Exact query / method | Cadence | Owner |
|---|---|---|---|---|
| **deployed_fraction** | `runs.alpaca.db pipeline_runs` (`run_type='live'`) JOIN `candidate_scores` | `1 − cash/portfolio_value` on the latest CANONICAL FULL run (last `pipeline_runs` row per `run_date` among rows whose `candidate_scores` count is ≥`MIN_FULL_RUN_CANDIDATES`, NOT the raw latest row by `created_at` — an intraday monitor pass can be more recent than the day's full run and must never silently supersede it); context: trailing-5-session mean over the same canonical daily series. Counts long stock only — no sleeve exists yet (RS-1/S7 not implemented), so idle cash is genuinely idle. Target (#231 §0): ≥95% incl. sleeve. | weekly (also the S6/S7 AC metric, 15-session windows) | orchestrator (this script) |
| **floor_gap_vs_spy** | `pipeline_runs` canonical daily live FULL rows + `data/ohlcv/SPY/1d.parquet` close | For each canonical FULL-run session t (SPY trading days only, window anchored at 2026-04-24 per RS-1 §1): `foregone += cash_weight(t) × SPY_close-to-close(t→t+1)`; cumulative simple sum in pp of book. DESCRIPTIVE realized attribution — never annualized (RS-1 §1's own correction). | weekly | orchestrator |
| **gate_verdict_age** | `metadata.wf_gate_metadata` stamped by `RenQuant/scripts/run_wf_gate.py` into the serving artifact `backtesting/renquant_104/artifacts/panel-ltr.alpha158_fund.json`; cross-check `runs.alpaca.db gate_verdicts` | Authoritative verdict := stamp with `diagnostic_only != true` AND non-null `passed`; report its age in days. Otherwise report **"mute since 2026-05-18"** (operator-established date, #231 §0) with the freshest diagnostic stamp attached (run_at / passed / reasons). Unmuting = S1–S4. | weekly (S4's AC is one recorded verdict; then this becomes days-since-verdict) | backtesting repo owns the gate; orchestrator owns the readout |
| **ledger_coverage** | `candidate_scores` JOIN `pipeline_runs` (run_date) LEFT JOIN `ticker_forward_returns` (as_of_date, ticker) | Aged := `run_date ≤ as_of − 35 calendar days` (20 trading days for `fwd_20d` to resolve + buffer). Coverage = % of aged live decision rows whose (run_date, ticker) joins a non-null `fwd_20d`. S5 AC: ≥95%. | weekly | pipeline/orchestrator (S5 wiring) |
| **pit_accrual_days** | `RenQuant/data/estimate_snapshots/<YYYY-MM-DD>/` dir listing, each validated via `ops/pit/pit_liveness_check.check_snapshot()` | Count of directories named `YYYY-MM-DD` that PASS the N2 collector's own 4-endpoint publication contract (all manifests present, `status=="ok"`, `as_of` matching, referenced parquet present and non-empty) — imported unchanged, single-impl rule. A directory that merely EXISTS but fails the contract (partial/crashed publish) is listed under `rejected_days` with its specific problem, never counted. `accrual_stale` flags the latest VALID dir >3 calendar days old (N2's missed-day alert). D3 needs ≥120 accrued (valid) days; time-irreversible, cannot be backfilled. | weekly (accrual itself is daily) | N2 snapshotter |
| **collector_liveness** | `ops/renquant105/rq105_liveness_check.py`'s own `_data_outputs()` path resolvers + `_data_output_fresh()` content validator | Imported unchanged, single-impl rule — never a directory-mtime scan (r1's scan reported "live" from an empty wrapper log and a censored intermediate ticks file, without checking any collector's actual data content). Each of the 3 covered collectors (`intraday_quote_logger`, `intraday_pairing_logger`, `entry_timing_shadow`) is checked via its OWN path resolver, and is fresh iff its last JSONL row's own `date` field equals `as_of` (mtime is only a documented fallback when the last row is unparseable). Reported per-collector INDEPENDENTLY; the aggregate is `live` only if every one passes. Non-session-day `as_of` reports `not_a_session_day`, never conflated with live/stale. | weekly (N1's AC is 3 complete sessions + lapse-alert test-fire) | N1 collectors |
| **calibrator_sign_laundered** | `pipeline_runs.counters_json` of the latest canonical daily FULL run (≥80 `candidate_scores` rows, last `created_at` per `run_date`) | `counters_json["calibrator_sign_laundered"]` (int). The full counter dict is attached for context. M4 (BL-1 recentering) AC: single digits. | weekly | pipeline (M4) |
| **buy_side_decision_tc** | `candidate_scores` + `trades` via `scripts/poc_transfer_coefficient.py` | **Imported unchanged** from `poc_transfer_coefficient.buy_side_decision_tc` (round-3 `blocked_by` stage taxonomy) — single-implementation rule; the scorecard never re-implements it. Eligible = candidates with `mu ≥ 0.03`; admission survivors per the taxonomy; Pearson corr(kelly_target_pct, emitted buy target_pct) only over runs with real dispersion (`measured` category); undefined cases categorized, never averaged in as 0. Mean ± SE over measured runs. EXPLORATORY DIAGNOSTIC, not measured-tier TC — every caveat in `doc/progress/2026-07-02-s-tc-measurement.md` applies verbatim. | weekly | orchestrator (S-TC); graduates to per-run ledger series with S5 |

Constants are pinned at the top of `scripts/kpi_scorecard.py` (`GATE_MUTE_SINCE`,
`FLOOR_GAP_ANCHOR`, `MIN_FULL_RUN_CANDIDATES=80`, `LEDGER_AGED_CUTOFF_DAYS=35`). Changing
any of them is a definition change and needs a PR touching this doc, not a silent edit.
"Full run" status (used by `deployed_fraction`, `floor_gap_vs_spy`, `calibrator_sign_
laundered`, `buy_side_decision_tc`) is always determined by joining `candidate_scores` and
counting — never `pipeline_runs.n_candidates`, which is 0 on every real production row
despite its name (verified directly against `runs.alpaca.db`: 1441/1441 live rows).

## 2. First measurement (2026-07-02, committed as `doc/research/evidence/kpi_scorecards/kpi_2026-07-02.json`; r2 corrected)

r1's values below are superseded — its `_canonical_daily_live` docstring claimed a
full-run-only selection but the implementation didn't actually filter on run size at all
(silently mixing in intraday partial rows), and `pit_accrual_days`/`collector_liveness`
were unvalidated directory scans (see Round 2 in the progress doc for the full finding).
These are the r2 re-measured, methodology-corrected values:

| Metric | Value | Reading |
|---|---|---|
| deployed_fraction | **0.2468** (trailing-5 mean 0.2051) | vs ≥95% target — the FLOOR term gap. Differs from r1's 0.214/0.223 because the full-run filter now genuinely excludes intraday partial rows, not because of a data change |
| floor_gap_vs_spy | **-1.11 pp of book** (10 sessions, avg cash weight 76.1%) | descriptive. Differs substantially from r1's 46-session/+3.48pp figure — r1 was NOT actually restricted to full runs despite its stated method; 10 sessions is the genuinely full-run-only canonical series |
| gate_verdict_age | **mute since 2026-05-18 (45 days)** | freshest stamp on the serving artifact is `diagnostic_only=true, passed=false` (run_at 2026-06-22, sanity FAIL: BULL_CALM,CHOPPY); `gate_verdicts` table has 0 rows |
| ledger_coverage | **86.2%** (fwd_20d over 5,199 aged rows) | below the S5 ≥95% AC — the ledger is not yet wired (#133), this measures the passive-collection substrate |
| pit_accrual_days | **1** (2026-07-02, contract-validated, not stale) | most visible dated dirs are pre-collector test artifacts that correctly fail the 4-manifest check; genuine accrual is thin, D3 needs ≥120 valid days |
| collector_liveness | **stale** (per-collector breakdown in the JSON `detail`) | r1 had reported `live` from directory activity on files unrelated to any collector's actual data output; the corrected per-collector check finds the covered pilot/shadow collectors' data outputs are not fresh as of this as_of |
| calibrator_sign_laundered | **44** (run 2026-07-01) | unchanged (this metric was already full-run-correct, joining `candidate_scores` directly) |
| buy_side_decision_tc | **0.288 mean (SE 0.167, n=4 measured of 10 canonical runs)** | unchanged — imported unchanged from `poc_transfer_coefficient`, which already used the join-based full-run selection this fix brought the other metrics up to |

## 3. Limitations (stated, not discovered later)

1. **This is a state readout, not a validated gate.** Several metrics readout the AC of a
   task that has not landed (S5 ledger, S4 verdict, M4 recentering); the scorecard makes the
   gap visible weekly, it does not certify anything.
2. **floor_gap_vs_spy does not reproduce RS-1 §1's snapshot numbers, and now diverges more
   than r1 reported.** RS-1 reported avg cash 75.5% / 2.88pp over 46 sessions; this script's
   corrected (r2) canonical-row definition — genuinely FULL-run-only, unlike r1's — yields
   avg cash 76.1% / -1.11pp over only 10 sessions. RS-1's memo did not pin its canonical-row
   selection to full runs; this script does (last live `pipeline_runs` row per `run_date`
   among FULL runs only — joined against `candidate_scores` count, since `pipeline_runs.
   n_candidates` is unpopulated — trading days only, next-session close-to-close
   attribution). The much smaller session count (10 vs. r1's 46) reflects how few of the
   window's live runs are genuinely full runs once correctly filtered; this makes the
   metric noisier (fewer independent sessions) but removes intraday-partial-row
   contamination. The standing weekly series is THIS definition; RS-1's and r1's figures
   remain their own respective descriptive snapshots, not reconciled.
3. **buy_side_decision_tc is exploratory by construction** (POC-S-TC round 3): n=4 measured
   runs, non-stationary across the 06-27 retrain boundary (0.57/0.57/0.0/0.0), and the two
   most recent full runs cannot be measured at all (≤2 admission survivors). It is reported
   with category counts and SE precisely so it cannot be quoted as a settled TC.
4. **ledger_coverage measures joinability, not ledger wiring.** `ticker_forward_returns` is
   a collect-only table today; 86.2% says the forward-outcome substrate exists for most aged
   decisions, not that decisions are provenance-complete (S5's actual deliverable).
5. **collector_liveness is an mtime heartbeat**, not a content check — a collector writing
   garbage on schedule reads "live". Content/completeness checks are N1's own AC ("3 sessions
   of complete output"), out of scope here.
6. **immutable=1 fallback** can read a torn snapshot if a writer is mid-transaction at the
   exact read moment; the open mode is recorded in the JSON (`inputs.db_open_mode`) so any
   anomalous scorecard can be checked against it. The normal `mode=ro` path has no such
   caveat.
7. **Weekend/holiday runs** degrade two metrics benignly (collector staleness, missing next
   SPY close). Run the scorecard on a trading day; the master plan's §4 cadence is weekly.

## 4. Relation to the master plan

- #231 §0's state-vector table rows "Deployment", "FLOOR", "PROCESS" (gate-verdict age,
  ledger coverage) now have a standing weekly instrument instead of ad-hoc measurement.
- §4's monthly re-baseline = read the last 4-5 committed scorecards; the JSON files are the
  dated addenda substrate.
- Metrics that graduate (S4 first verdict, S5 ledger, M4 recentering) keep the SAME
  definition here; only their readings change — that is the point of freezing definitions
  before the tasks land.
