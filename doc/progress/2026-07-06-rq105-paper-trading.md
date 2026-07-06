# 2026-07-06 rq105 paper trading mode — REVERTED (architecture-boundary violation)

STATUS: reverted
WHAT: this PR originally added `MODE_PAPER` to the intraday session scheduler,
a `--mode paper` CLI override, `_build_paper_submitter()` (a direct
`alpaca.trading.client.TradingClient` + `client.submit_order()` integration),
and hardwired `ops/renquant105/run_session_scheduler.sh` to `--mode paper` by
default. It also added an `if mode == MODE_PAPER: return` bypass to
`assert_shadow_never_submits()` — the scheduler's RUNTIME never-submit
assertion, previously a hard invariant stronger than a docstring contract. Per
the doc's own original "Verified results" section (now removed), this code
path was actually exercised: 3 BUY orders were submitted and filled on the
Alpaca paper account (FTNT, BLK, GRMN).

WHY-DIR: `AGENTS.md`'s Hard Boundaries section states "Do not implement
broker adapters here" — `renquant-orchestrator` orchestrates pinned subrepos;
broker execution belongs in `renquant-execution` (see the `AlpacaBrokerPort`
and `PaperBrokerPort` adapters already built there). Adding a submit path
directly inside the scheduler, and bypassing the module's own "Nothing here
can place an order" contract to do it, is a genuine control-plane bypass —
not a small extension of the Stage-1 shadow slice, a role change for this
repo. Separately, the branch had also silently regressed two already-merged
fixes from #399 (the fingerprint-gap required-key set back to the buggy
3-key form, and the `max_cycles` cadence-derivation test helper back to a
hardcoded `max_cycles=60`), deleting the tests that proved both — restored by
merging `origin/main` before making any of the changes below.

EVIDENCE: removed entirely from this PR — `MODE_PAPER`, `_build_paper_submitter`,
the `--mode` CLI argument and its config-override handling, the
`assert_shadow_never_submits` bypass, the `AlpacaLiveStateSource` paper-credential
branching (`ALPACA_SHORTS_*`), and `run_session_scheduler.sh`'s `--mode paper`
default. `grep`-confirmed zero remaining references to `MODE_PAPER`,
`_build_paper_submitter`, `TradingClient`, or `submit_order` in this module.
`assert_shadow_never_submits` is restored to its original form: any mode other
than `"shadow"`, or any broker-submission evidence in a tick payload, raises
`ShadowModeViolation` before the record is persisted — no exceptions.

The frozen-score pipeline (`_FrozenScoreScoringJob`, replacing the per-tick
feature-rebuild with pre-computed daily scores) is KEPT, but re-labeled
diagnostic-only in its docstring: `_StubFeatureMatrixTask` injects an empty
feature matrix and a hardcoded `default_quantity=1` purely to unblock the
pipeline's feature-availability gate, with no proof this preserves the
pipeline's semantics, no real sizing control, and no exit/sell path. It is
confined to the shadow-only scheduler (no submit path exists in this module
anymore), so it can only ever produce shadow-logged intents.

NEXT: paper-execution wiring is deferred to a future PR in `renquant-execution`,
with its own ownership boundary, authorization path (analogous to the §9.4
economic-authorization gate already built for the live path), order envelopes,
exit/sell lifecycle, and success/rollback criteria defined BEFORE any submit
path is wired — not as a side effect of an orchestrator PR. The frozen-score
pipeline's semantic validity (does bypassing the feature contract produce
meaningful, non-degenerate intents?) also remains unproven and should be
established with a dedicated test before it's relied on for anything beyond
shadow diagnostics.

## Round 2 (codex review)

STATUS: fixed
WHAT: codex confirmed the broker-adapter removal above is correct, then
found a SECOND architecture-boundary violation: `bind_pipeline_tick_runner()`
imported `renquant_pipeline.panel_scoring` tasks and
`renquant_pipeline.selection.SelectionJob` directly, then assembled a
custom `_FrozenScoreScoringJob`/`_frozen_score_stages()` pipeline here —
`AGENTS.md` says not to implement signal internals in this repo, and the
scheduler's own docstring says it consumes slice 2 "strictly through their
contracts; implements neither." Composing a custom stage graph from raw
pipeline tasks is not consuming a contract; it is reaching into pipeline
internals and redefining stage composition in the wrong repo.
WHY-DIR: the same class of boundary violation as round 1 (broker
internals), this time on the pipeline/signal side. `run_intraday_decision_tick`'s
`stages=` parameter is a legitimate internal composition seam for
renquant-pipeline's own callers/tests, but it is not meant to let an
external repo hand it a stage list built from that repo's private tasks.
EVIDENCE: moved the entire frozen-score composition into renquant-pipeline
(companion PR `feat/frozen-score-slice2-contract`, see that repo's progress
doc for the full change): `FrozenScoreScoringJob` now lives next to
`PanelScoringJob` in `panel_scoring.py` (inheriting its `run()`/`should_skip()`
choke-point unchanged — a first attempt at a standalone class duplicated the
`buy_blocked` writer and broke `TestCensusPin::test_single_designated_writer`;
fixed via inheritance instead of a from-scratch reimplementation), and a new
`run_frozen_score_diagnostic_tick()` entry point in `intraday_decisioning.py`
wraps `run_intraday_decision_tick(..., stages=frozen_score_diagnostic_stages())`
internally. `bind_pipeline_tick_runner()` here now imports ONLY
`renquant_pipeline.intraday_decisioning` and calls
`contract.run_frozen_score_diagnostic_tick(...)` — `grep`-confirmed zero
remaining references to `panel_scoring`, `SelectionJob`, or any of the
individual task classes in this module. Full orchestrator suite (run against
the modified pipeline checkout): 3140 passed, 3 skipped, 0 failures.
Pipeline-side: 1336 passed, 7 skipped, 0 failures, including 5 new tests
proving the frozen-score diagnostic contract's actual semantics — notably
`test_frozen_score_diagnostic_tick_has_no_real_sizing_control`, which found
that the "quantity is always 1" claim is true only because this repo's
`session_start_provider` never populates `order_quantity_by_ticker`; the
diagnostic job itself would honor real per-ticker quantities if a future
caller supplied them. Docstrings in both repos now say this precisely
instead of overclaiming an intrinsic property that isn't actually true of
the code.
NEXT: land the companion `renquant-pipeline` PR first (this branch's tests
were run against that unmerged branch locally); once merged, confirm CI
here is green against the real pinned `renquant-pipeline` version.
