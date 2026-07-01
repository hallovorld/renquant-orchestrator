# renquant105 Stage-1 paired intraday-vs-batch arrival-observation harness

STATUS: Built + tested; PR open, not merged/approved. Stage-1 **OPERATIONS-ONLY**
data collector — it COLLECTS real pilot data and makes **no** execution-quality
claim, places **no** orders, and gates/promotes/pins nothing. First buildable
piece of the merged RFC `doc/design/2026-06-30-renquant105-intraday-decisioning-architecture.md`
(§9, converged r11/r12). Rev 2 (2026-07-01): reworked from a single-mid paired
shortfall to RAW per-arm arrival observations + a timing/execution decomposition,
per the Codex CHANGES_REQUESTED review (see FIX below).

WHAT: New module `src/renquant_orchestrator/intraday_pairing_logger.py` — an
OBSERVE-ONLY / post-hoc logger. For each daily-admitted name on a session it
records **raw per-arm arrival observations** for the two entry paths:
- (a) the ACTUAL next-day-open **batch** entry (real historical fill, from
  `trades` in the read-only runs DB, joined on `run_id`) plus the batch arm's own
  **arrival/reference quote** at the instant it became executable (session-T open
  reference, §9.2c), and
- (b) the HYPOTHETICAL **intraday** entry — the intraday arm's arrival quote at
  the **first eligible tick after conviction** (§11b), selected by the frozen rule
  below. Nothing is placed intraday; the intraday arm has no real fill in Stage-1.

Record shape (schema v2):
`{schema_version, stage, record_kind, intraday_entry_hypothetical, prereg,
date, ticker, side, signal_version,
batch_arm{arm, eligible_ts, arrival_quote{bid,ask,mid,source_ts,source}, fill{price,time}, fill_model},
intraday_arm{...same shape, fill=null},
decomposition{timing_component, execution_shortfall_batch, execution_shortfall_intraday,
              total_difference, is_execution_quality(=false), fill_model, note},
admitted, filled, censored_reason}`.
Rows accumulate as JSONL (default under the operator data root, decoupled from the
umbrella git tree). `--dry-run` / `--json` summary mode; append is idempotent on
the design pair key `(signal_session, symbol, signal_version)`.

FIX (Codex CHANGES_REQUESTED, 2026-07-01 — blocking estimand issue):
The v1 record measured BOTH arms against ONE common intraday-tick midpoint while
the batch arm's entry was an actual next-open fill. So
`implementation_shortfall_batch` silently absorbed the overnight/timing move
(fill − intraday-mid), while `implementation_shortfall_intraday` collapsed to ~0
because the intraday entry defaulted to that same midpoint. That paired difference
was mechanically favored toward the hypothetical arm and did not isolate execution
quality — calling a midpoint a "hypothetical entry" without a spread/impact model
is invalid. Rev 2:
1. **Stopped emitting the biased paired shortfall.** Each arm now records its OWN
   arrival/reference quote (bid/ask/source-ts/`source`) at the instant that arm
   becomes executable, plus its eligibility ts and `fill_model = "none/raw"`. No
   arm's entry is defaulted to a midpoint.
2. **Decomposition, strictly separated** (§9.1's two readouts):
   `timing_component` = signed(batch_arrival_mid − intraday_arrival_mid) = the
   overnight/latency market move between the two arrival instants (opportunity
   cost, **NOT** execution quality); `execution_shortfall_{batch,intraday}` =
   signed(fill − that arm's OWN arrival mid) = within-path execution, flagged
   **NOT** an execution-quality verdict (`is_execution_quality=false`,
   `fill_model="none/raw"`) until a pre-registered spread/impact fill model
   exists; `total_difference` = signed(batch_fill − intraday_fill), **null** unless
   BOTH arms have a real fill. Algebraic identity (tested):
   `total = timing + exec_batch − exec_intraday`. In Stage-1 the intraday arm has
   no real fill, so `execution_shortfall_intraday` and `total_difference` are
   `null` by construction — the honest state, never a fabricated zero.
3. **Tick-selection rule made explicit + tested + frozen** (below), so no future
   analysis can pick a favorable tick post hoc.

PRE-REGISTRATION (frozen BEFORE evidence — mirrored in code as `FROZEN_PREREG`,
stamped on every row as `prereg`; changing any of these is a recorded decision,
not an ad-hoc edit):
- **Tick selection** = `first_eligible_tick_after_conviction`: the FIRST intraday
  tick whose quote `source_ts` is at/after the name's conviction/eligibility
  instant (**as-of enforced**) — never a later, more favorable tick. Ties resolve
  to feed order (stable), never "best price at that instant". Without a declared
  eligibility instant, NO tick is selected (closes the post-hoc loophole).
- **Session / calendar** = eligibility window `open+5min .. close−30min` (§11b);
  ticks before eligibility or after the no-entry cutoff are ineligible. The loader
  returns the RAW tick list; selection is deferred to the frozen rule at join time.
- **Censoring** = `recorded_not_imputed` (§9.2d): no-fill / no-tick /
  no-arrival-quote observations are recorded by cause in `censored_reason` and the
  affected decomposition terms stay `null`. The intraday arm having no real fill is
  the normal Stage-1 state (`intraday_entry_hypothetical=true`), NOT a censoring
  anomaly — only missing OBSERVED inputs are flagged.
- **Analysis unit** = `session_date` (dates, not rows) — the summary reports
  `n_sessions` alongside row counts; the future experiment (§9.4) blocks on dates.

WHY: The merged RFC's Stage-1 is operations-only (r11/r12 converged): the whole
execution-quality A/B — sample size, block length, and whether a 10-bps effect is
even identifiable at this ~$10.5k book — is DEFERRED to a future SEPARATE
simplified experiment-prereg PR that must be finalized against REAL pilot
variance (§9.4). That future PR needs a clean corpus of real paired-session
execution data to consume. This harness is exactly that accumulation buffer plus
the pairing structure + the frozen data-collection contract — the first thing that
can be built now without touching the (deferred) statistics or placing any real
intraday order.

EVIDENCE:
- `tests/test_intraday_pairing_logger.py` — 31 deterministic tests (all injected
  timestamps, in-memory + tmp fixtures, never touches live state): within-path
  execution sign/magnitude (buy + sell) + missing-input null; timing-component as
  arrival-to-arrival move (not execution) + null; decomposition identity
  (`total = timing + exec_b − exec_i`), Stage-1 no-intraday-fill leaves execution
  + total null (NOT zero), no-batch-arrival censors timing + exec_batch; raw
  per-arm arrival quotes on the record; censoring (no-fill / no-tick /
  no-intraday-fill-is-not-an-anomaly); **first-eligible-tick selection** (earliest
  at/after eligibility, later favorable tick NOT selected, pre-eligibility ticks
  ignored, no-entry cutoff respected, no-eligibility-instant selects nothing,
  out-of-order feed sorted); pair-join with selection + tick-stamped-eligibility
  fallback + date-keyed fill fallback; counts-only summary with `analysis_unit`;
  idempotent append; read-only loaders (`selected=1` + `run_type` filter, `run_id`
  fill join buy-only, raw tick list not collapsed, batch-arrival first-wins),
  end-to-end `collect`.
  `RenQuant/.venv/bin/python -m pytest tests/test_intraday_pairing_logger.py -q`
  → **31 passed**.
- CLI smoke (tmp DB): `--out` append produces the expected JSONL. Worked example
  (NVDA, batch arrival mid 101, intraday first-eligible-tick mid 100, batch fill
  102): `timing_component=+1.0` (overnight move), `execution_shortfall_batch=+1.0`
  (within-path), `execution_shortfall_intraday=null` (NOT imputed to 0),
  `total_difference=null`. The old biased v1 would have reported
  `IS_batch=+2.0 / IS_intraday=0.0` — the +2.0 is now correctly split into
  1.0 timing + 1.0 within-path execution, and no fake intraday zero is emitted.

SCOPE (explicit boundaries):
- **Stage-1 operations-only.** DELIBERATELY renders no PASS/FAIL, no
  non-inferiority verdict, no ±10-bps claim, and no between-arm execution-quality
  comparison — the summary is counts only. `decomposition.is_execution_quality` is
  always `false`. All of that is deferred to §9.4.
- **OBSERVE-ONLY.** Emits no orders, no pins, no gates, no promotion. All DB
  access is read-only (`mode=ro` URI). The intraday arm is flagged
  `intraday_entry_hypothetical` — no real intraday order exists in Stage-1.
- **Censored, not imputed** (§9.2d): missing observations recorded by cause;
  affected decomposition terms stay `null`.
- Boundary compliance (CLAUDE.md): the orchestrator only schedules /
  provenances / accumulates data; it implements no broker adapter (execution) or
  sizing/decision internals (pipeline). The intraday full-decisioning tick feed
  and the batch open-auction arrival-quote feed are upstream (execution/pipeline,
  §8) — until they land those sources are absent and every pair is censored, the
  correct, honest Stage-1 state (scaffold ready, waiting for the feeds).

NEXT: Wire the structured intraday decision-tick quote feed and the batch
open-auction arrival-quote feed once the execution/pipeline Stage-1 PRs (§8) land,
so real paired rows accumulate under the frozen canary envelope (§9.3). After a
preset minimum of real independent sessions is collected, the SEPARATE simplified
experiment-prereg PR (§9.4) consumes this JSONL to decide sample size / block
length / identifiability, and to introduce a pre-registered fill model that would
promote the within-path `execution_shortfall_*` terms from raw deltas to an actual
execution-quality read — this harness makes none of those calls.
