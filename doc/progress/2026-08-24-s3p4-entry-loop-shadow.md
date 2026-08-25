# S3-P4, observe-only half: the guarded entry loop decides and records — no order path exists

STATUS: implementation PR (design `2026-08-23-rq105-stage3-live-entries.md`
§4/§4b/§5). With S3-a (producer) and S3-b (pinned serving) live as of today,
this adds the ladder's decision surface — as a recorded counterfactual. The
live emission stage is deliberately NOT here: it ships WITH the S3-c operator
authorization, because a dark order stage waiting behind a flag is inert
scaffolding.

## What

- `src/renquant_orchestrator/rq105_entry_loop_shadow.py` — one tick:
  * batch side = the T-1 live run via the EXISTING leak-guarded loader
    (`intraday_session_inputs.load_frozen_daily_signal`, §4b(ii) reuse
    contract — selection is not re-implemented); loader refusals are recorded
    verbatim as `session_block` with the reason (§4b rejection contract);
  * intraday side = the S3-b rows for this (session, as_of);
  * `decide_entries` (#1038 core, its own suite + mutants) with v1 guardrails
    — `max_concurrent_positions` READ FROM THE PINNED CONFIG, refusing on
    absent/malformed (closes orch#1050: the dataclass default is never what
    a live surface relies on);
  * occupancy = positions ∪ pending ∪ reservations from the session
    scheduler's own shadow tick ≤ as_of, staleness-bounded — no evidence ⇒
    named refusal, never "0 slots used";
  * `entries_today`/`notional_today` recomputed from this log's own records;
  * every record asserts broker vocabulary is ABSENT before persisting.
- `ops/renquant105/run_shadow_serving.sh` — the entry-loop tick runs after
  each serving tick (same cadence, same pinned config, same log).
- 16 tests: config-cap provenance + refusal, occupancy union/staleness/
  missing-log refusals, batch-refusal recording, budget exhaustion across
  ticks, cap-full vs config-cap, stale-quote per-name censoring, and the
  broker-vocabulary poison test.

## Evidence (§4b)

- Suite: **16 passed** (py3.10) [VERIFIED 2026-08-24].
- **Real read-only end-to-end smoke** [VERIFIED — scratch outputs, deleted
  after]: served 90 rows at `as_of=15:30:05 ET` from today's real snapshot,
  then the loop against the REAL runs DB and REAL scheduler tick log:
  batch side resolved `2026-08-21-live-933658ce` (leak-guarded), occupancy
  7 (real tick 15:25:29, 4.6 min fresh), **1 intent (TMO, limit 630.36,
  $750 budget)**, every rejection named (82 intraday_quote_censored /
  6 not_batch_admitted / 1 intraday_veto).

## Not here

No orders, no broker imports, no live mode. S3-c remains an explicit
operator ask; the emission stage will be its own PR under that
authorization, reusing `live.runner`'s broker path per the design's
execution-interface contract.

## r2 (codex round 1): two P1s — serving-failure gate, tick idempotency

Both accepted.

1. **Serving failure gates the decision.** The wrapper now captures the
   serving step's exit code PER TICK and passes it as `--serving-rc`; nonzero
   ⇒ the loop persists a NAMED refusal (`serving_failed rc=N`) without
   reading rows — a failed serving can leave a partial row set for exactly
   this as_of, and a plan from a subset reads as complete evidence. The
   refusal is recorded, not silent (the evidence lane must show the gap).
2. **One (session, as_of) decides exactly once.** Idempotency gate before
   any work (a retry returns the existing record flagged `duplicate_tick`),
   re-checked under an exclusive `flock` around the read+append critical
   section so two concurrent retries serialize and the loser sees the
   winner's record. `session_totals` additionally dedups by tick identity
   (defense in depth for pre-fix logs).

Tests: +4 (persisted refusal on serving_rc≠0; retry appends nothing and
totals stay 1×; duplicate records in a pre-fix log count once; a
two-thread race with a barrier past the pre-gate lands exactly one record
and one `duplicate_tick`). The two pre-existing tests that reused one
as_of across ticks began failing — the gate firing correctly — and now use
distinct as_ofs with occupancy ticks that track them, matching the real
four-checkpoint cadence. **20 passed.**

## r4 (codex round 3): the plan binds its evidence by content, not by path

Accepted. Every persisted record now carries an `evidence` block:
`pinned_config_sha256` (the exact bytes read), `shadow_rows_sha256`
(canonical `hash_jsonable` over the exact selected row set, ticker-sorted),
`occupancy_tick_sha256` (the exact scheduler record used — the occupancy
reader now returns it), and `batch_signal_version` (run_id + score sha, as
before). A record WITH intents refuses to persist if any binding is
missing/unhashable — an unprovable plan is not an evidence base. The
canonical primitive is `renquant_artifacts.hash_jsonable`, and the wrapper
resolves the artifacts checkout through the same `--verify-subrepo`
loader-code-identity gate as pipeline (#1053) before it joins PYTHONPATH.
Tests: bindings present on plans; each input change flips exactly its
binding; unhashable provenance refuses with nothing persisted. **24
passed**; real no-rows smoke shows config/occupancy/batch bound with
`shadow_rows_sha256: null` on the refusal record (a refusal binds what it
actually read).
