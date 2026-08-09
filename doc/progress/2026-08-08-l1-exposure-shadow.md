# L1 exposure shadow logger — the controller starts watching (operator grant "开")

STATUS:    code delivered for review. Operator granted the shadow phase
           2026-08-08 ("开"). No orders, no config, one JSONL row per date in
           its own log dir. Job installation follows MERGE under the same
           grant, with the launchd manifest updated in the same batch and a
           tracked issue carrying the revert steps (containment discipline).

WHAT:      src/renquant_orchestrator/l1_exposure_shadow.py + 6 tests.
           Computes target_exposure = clip((0.15/EWMA-vol)·g(regime), 0.3, 1)
           daily from the live surfaces (OHLCV universe vol; regime label +
           confidence from live_state_snapshots) and logs COMPONENTS —
           sigma_hat, g, regime source, target, achieved, gap — so any later
           σ* choice recomputes from the log alone: the shadow period is
           σ*-agnostic and the operator's drawdown-appetite decision does not
           reset the clock.

WHY/DIR:   orch#919 measured the controller at +17.1%/yr, Sharpe 1.38,
           maxDD −17.4% (frozen single parameter set) vs the accidental
           ~22%-invested book at ~+5.6%/yr. The shadow phase is the zero-risk
           first step the operator approved: watch the controller against the
           live book daily before any order-path proposal.

EVIDENCE:  artifact:      dry-run against the real surfaces this session
                          (read-only DB, log to session scratch):
                          sigma_hat 0.180, BULL_CALM conf 0.5921 -> g=1.0,
                          target 0.8333 vs achieved 0.2348, gap +0.5986
                          [VERIFIED — module stdout, 2026-08-08]
           prod or exp:   experiment tooling; the production write (its log
                          dir under the umbrella) happens only when the
                          GRANTED job runs, not by hand
           existing data: no daily record of designed-vs-achieved exposure
                          has ever existed
           best-known?:   yes — first live reading of the deployment gap:
                          59.9 points
           scope:         orchestrator module + tests. LIVE ADAPTATION stated
                          in the module docstring: the evaluation used the
                          regime-artifact posterior vector; the live surface
                          emits (label, confidence); g uses the same frozen
                          form fed by what production actually publishes, and
                          every row records the source for auditability.

           Contracts (each tested): append-only one row per date (rewrite
           refused); REFUSED-STALE-SNAPSHOT unless --allow-stale-snapshot
           (the row records snapshot_run_date either way); thin-universe
           refusal (< 30 names with OHLCV) — never an invented vol; garbage
           confidence degrades to g=1, never negative; TEMPORAL INTEGRITY
           (review r3) — the vol input is truncated to sessions STRICTLY
           BEFORE the snapshot's run date, the cutoff + last session used
           are persisted in every row (vol_input_cutoff /
           vol_input_last_date), and an end-to-end guard proves a same-day
           partial bar or later OHLCV refresh cannot change the row for a
           fixed snapshot date.

TESTS:     tests/test_l1_exposure_shadow.py — 8 passed (pure math, append-
           only, both CLI refusals, both temporal-integrity guards; tmp
           dirs only).

NEXT:      after merge, under the SAME operator grant: install the daily
           launchd job (manifest updated in the same batch, tracked issue
           with literal revert steps), first scheduled row next trading day;
           then a weekly gap digest line in the ops report.
