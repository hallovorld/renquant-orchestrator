# renquant105 Stage-1 paired intraday-vs-batch IS logging harness

STATUS: Built + tested; PR open, not merged/approved. Stage-1 **OPERATIONS-ONLY**
data collector — it COLLECTS real pilot data and makes **no** execution-quality
claim, places **no** orders, and gates/promotes/pins nothing. First buildable
piece of the merged RFC `doc/design/2026-06-30-renquant105-intraday-decisioning-architecture.md`
(§9, converged r11/r12).

WHAT: New module `src/renquant_orchestrator/intraday_pairing_logger.py` — an
OBSERVE-ONLY / post-hoc logger. For each daily-admitted name on a session it
emits a **paired** implementation-shortfall (IS) record joining:
- (a) the ACTUAL next-day-open **batch** entry (real historical fill, from
  `trades` in the read-only runs DB, joined on `run_id`), and
- (b) the HYPOTHETICAL **intraday** entry at the daily decision's intraday tick
  (from a structured tick-quote JSONL source — nothing is placed intraday),

both measured as a signed deviation vs a common **decision-time reference mid**
(§9.1 arrival-price convention). Record shape:
`{date, ticker, side, signal_version, reference_mid, batch_entry_ref{price,time},
intraday_entry_ref{price,time}, implementation_shortfall_batch,
implementation_shortfall_intraday, admitted, filled, censored_reason}`. Rows
accumulate as JSONL (default under the operator data root, decoupled from the
umbrella git tree). `--dry-run` / `--json` summary mode; append is idempotent on
the design pair key `(signal_session, symbol, signal_version)`.

WHY: The merged RFC's Stage-1 is operations-only (r11/r12 converged): the whole
execution-quality A/B — sample size, block length, and whether a 10-bps effect is
even identifiable at this ~$10.5k book — is DEFERRED to a future SEPARATE
simplified experiment-prereg PR that must be finalized against REAL pilot
variance (§9.4). That future PR needs a clean corpus of real paired-session
execution data to consume. This harness is exactly that accumulation buffer plus
the pairing structure — the first thing that can be built now without touching
the (deferred) statistics or placing any real intraday order.

EVIDENCE:
- `tests/test_intraday_pairing_logger.py` — 18 deterministic tests (all injected
  timestamps, in-memory + tmp fixtures, never touches live state): shortfall
  sign/magnitude (buy + sell), complete pairing, censored handling
  (no-fill / no-tick / both), pair-join + date-keyed fallback, counts-only
  summary, idempotent append, read-only loaders (`selected=1` + `run_type` filter,
  `run_id` fill join, buy-only), JSONL tick loader, end-to-end `collect`.
  `RenQuant/.venv/bin/python -m pytest tests/test_intraday_pairing_logger.py -q`
  → **18 passed**.
- CLI smoke (tmp DB): `--dry-run --json` and `--out` append both produce the
  expected paired JSONL (NVDA complete: IS_batch=+2.0, IS_intraday=+0.5; MU
  censored `no_intraday_tick+no_batch_fill`).

SCOPE (explicit boundaries):
- **Stage-1 operations-only.** DELIBERATELY renders no PASS/FAIL, no
  non-inferiority verdict, and no ±10-bps claim — the summary is counts only, and
  no between-arm IS comparison is computed. All of that is deferred to §9.4.
- **OBSERVE-ONLY.** Emits no orders, no pins, no gates, no promotion. All DB
  access is read-only (`mode=ro` URI). The intraday arm is flagged
  `intraday_entry_hypothetical` — no real intraday order exists in Stage-1.
- **Censored, not imputed** (§9.2d): no-fill / no-intraday-tick pairs are recorded
  by cause; missing shortfalls stay `null`.
- Boundary compliance (CLAUDE.md): the orchestrator only schedules /
  provenances / accumulates data; it implements no broker adapter (execution) or
  sizing/decision internals (pipeline). The intraday full-decisioning tick feed
  is upstream (execution/pipeline, §8) — until it lands the tick source is absent
  and every pair is censored `no_intraday_tick`, the correct, honest Stage-1
  state (scaffold ready, waiting for the feed).

NEXT: Wire the structured intraday decision-tick quote feed once the
execution/pipeline Stage-1 PRs (§8) land, so real paired rows accumulate under
the frozen canary envelope (§9.3). After a preset minimum of real independent
sessions is collected, the SEPARATE simplified experiment-prereg PR (§9.4)
consumes this JSONL to decide sample size / block length / identifiability — this
harness makes none of those calls.
