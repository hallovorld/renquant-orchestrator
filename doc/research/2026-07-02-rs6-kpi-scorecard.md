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
| **deployed_fraction** | `runs.alpaca.db pipeline_runs` (`run_type='live'`) | `1 − cash/portfolio_value` on the latest live row by `created_at`; context: trailing-5-session mean over the canonical daily series (last row per `run_date`). Counts long stock only — no sleeve exists yet (RS-1/S7 not implemented), so idle cash is genuinely idle. Target (#231 §0): ≥95% incl. sleeve. | weekly (also the S6/S7 AC metric, 15-session windows) | orchestrator (this script) |
| **floor_gap_vs_spy** | `pipeline_runs` canonical daily live rows + `data/ohlcv/SPY/1d.parquet` close | For each canonical session t (last live row per `run_date`, SPY trading days only, window anchored at 2026-04-24 per RS-1 §1): `foregone += cash_weight(t) × SPY_close-to-close(t→t+1)`; cumulative simple sum in pp of book. DESCRIPTIVE realized attribution — never annualized (RS-1 §1's own correction). | weekly | orchestrator |
| **gate_verdict_age** | `metadata.wf_gate_metadata` stamped by `RenQuant/scripts/run_wf_gate.py` into the serving artifact `backtesting/renquant_104/artifacts/panel-ltr.alpha158_fund.json`; cross-check `runs.alpaca.db gate_verdicts` | Authoritative verdict := stamp with `diagnostic_only != true` AND non-null `passed`; report its age in days. Otherwise report **"mute since 2026-05-18"** (operator-established date, #231 §0) with the freshest diagnostic stamp attached (run_at / passed / reasons). Unmuting = S1–S4. | weekly (S4's AC is one recorded verdict; then this becomes days-since-verdict) | backtesting repo owns the gate; orchestrator owns the readout |
| **ledger_coverage** | `candidate_scores` JOIN `pipeline_runs` (run_date) LEFT JOIN `ticker_forward_returns` (as_of_date, ticker) | Aged := `run_date ≤ as_of − 35 calendar days` (20 trading days for `fwd_20d` to resolve + buffer). Coverage = % of aged live decision rows whose (run_date, ticker) joins a non-null `fwd_20d`. S5 AC: ≥95%. | weekly | pipeline/orchestrator (S5 wiring) |
| **pit_accrual_days** | `RenQuant/data/estimate_snapshots/<YYYY-MM-DD>/` dir listing | Count of directories named `YYYY-MM-DD`; `accrual_stale` flags latest dir >3 calendar days old (N2's missed-day alert). D3 needs ≥120 accrued days; time-irreversible, cannot be backfilled. | weekly (accrual itself is daily) | N2 snapshotter |
| **collector_liveness** | file mtimes under `RenQuant/logs/rq105` and `RenQuant/logs/renquant105_pilot` | Newest-file mtime per collector dir; **live** iff every collector wrote within 30h (covers overnight gap; catches a dead launchd job by the next scorecard). Zero-byte newest files flagged (`zero_byte_warning`) but don't fail liveness (a fresh log is legitimately empty at open). Weekend runs read "stale" benignly — run on a trading day. | weekly (N1's AC is 3 complete sessions + lapse-alert test-fire) | N1 collectors |
| **calibrator_sign_laundered** | `pipeline_runs.counters_json` of the latest canonical daily FULL run (≥80 `candidate_scores` rows, last `created_at` per `run_date`) | `counters_json["calibrator_sign_laundered"]` (int). The full counter dict is attached for context. M4 (BL-1 recentering) AC: single digits. | weekly | pipeline (M4) |
| **buy_side_decision_tc** | `candidate_scores` + `trades` via `scripts/poc_transfer_coefficient.py` | **Imported unchanged** from `poc_transfer_coefficient.buy_side_decision_tc` (round-3 `blocked_by` stage taxonomy) — single-implementation rule; the scorecard never re-implements it. Eligible = candidates with `mu ≥ 0.03`; admission survivors per the taxonomy; Pearson corr(kelly_target_pct, emitted buy target_pct) only over runs with real dispersion (`measured` category); undefined cases categorized, never averaged in as 0. Mean ± SE over measured runs. EXPLORATORY DIAGNOSTIC, not measured-tier TC — every caveat in `doc/progress/2026-07-02-s-tc-measurement.md` applies verbatim. | weekly | orchestrator (S-TC); graduates to per-run ledger series with S5 |

Constants are pinned at the top of `scripts/kpi_scorecard.py` (`GATE_MUTE_SINCE`,
`FLOOR_GAP_ANCHOR`, `MIN_FULL_RUN_CANDIDATES=80`, `LEDGER_AGED_CUTOFF_DAYS=35`,
`COLLECTOR_LIVE_MAX_AGE_HOURS=30`). Changing any of them is a definition change and needs a
PR touching this doc, not a silent edit.

## 2. First measurement (2026-07-02, committed as `doc/research/evidence/kpi_scorecards/kpi_2026-07-02.json`)

| Metric | Value | Reading |
|---|---|---|
| deployed_fraction | **0.214** (trailing-5 mean 0.223) | vs ≥95% target — the FLOOR term gap, unchanged from the 07-01 state (#231 §0 said 25%) |
| floor_gap_vs_spy | **+3.48 pp of book foregone** (46 sessions 04-24→07-01, avg cash weight 72.1%, SPY span +4.5%) | descriptive; the mechanical core of flat-book-vs-rally |
| gate_verdict_age | **mute since 2026-05-18 (45 days)** | freshest stamp on the serving artifact is `diagnostic_only=true, passed=false` (run_at 2026-06-22, sanity FAIL: BULL_CALM,CHOPPY); `gate_verdicts` table has 0 rows |
| ledger_coverage | **86.2%** (fwd_20d over 5,199 aged rows; any-join 88.5%) | below the S5 ≥95% AC — the ledger is not yet wired (#133), this measures the passive-collection substrate |
| pit_accrual_days | **1** (2026-07-02, not stale) | accrual started today; D3 needs ≥120 |
| collector_liveness | **live** (pilot ticks 0.01h old; rq105 quote logger 0.42h old, zero-byte flagged) | N1 partially live; the zero-byte quote log wants watching at close |
| calibrator_sign_laundered | **44** (run 2026-07-01, 89 candidate_scores rows) | unchanged from M4's motivating measurement (44/90); AC = single digits |
| buy_side_decision_tc | **0.288 mean (SE 0.167, n=4 measured of 10 canonical runs; 2 insufficient-sizing-population)** | EXPLORATORY: two ~0.57 runs (06-09/06-10) and two 0.0 runs (06-22/06-23, pre-retrain); post-retrain runs (06-30/07-01) had ≤2 admission survivors — too few to correlate |

## 3. Limitations (stated, not discovered later)

1. **This is a state readout, not a validated gate.** Several metrics readout the AC of a
   task that has not landed (S5 ledger, S4 verdict, M4 recentering); the scorecard makes the
   gap visible weekly, it does not certify anything.
2. **floor_gap_vs_spy does not exactly reproduce RS-1 §1's snapshot numbers.** Same window,
   same session count (46), same method family, but RS-1 reported avg cash 75.5% / 2.88pp
   while this canonical-row definition yields 72.1% / 3.48pp. RS-1's memo did not pin its
   canonical-row selection; this script does (last live `pipeline_runs` row per `run_date`,
   trading days only, next-session close-to-close attribution). The standing weekly series
   is THIS definition; RS-1's figures remain that memo's own descriptive snapshot.
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
