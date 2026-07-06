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
