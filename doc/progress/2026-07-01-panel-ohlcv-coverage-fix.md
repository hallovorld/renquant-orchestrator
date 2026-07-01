# panel OHLCV coverage fix — full 292-ticker refresh + partial-freeze guard

STATUS:   code + tests (this PR). Mocks/fixtures only — no real OHLCV fetch, no production data write, no retrain executed.
BRANCH:   fix/panel-ohlcv-coverage → main (`hallovorld/renquant-orchestrator`).

ROOT CAUSE (the load-bearing model-staleness root):
          The panel training universe is tier_A + tier_B (~292 tickers), read from
          `data/transformer_universe_inventory.json` by
          `renquant_base_data.alpha158_qlib_panel.LoadUniverseJob`. Only the ~142-ticker
          live watchlist gets fresh daily `data/ohlcv/<ticker>/1d.parquet` bars as a
          live-path side effect. The ~150 extra research tickers had NO refresh cadence
          (`scripts/fetch_russell2000_ohlcv.py` SKIPS existing files), so they sat at
          ~2026-05-12; after the (correct) fwd_60d label clip that surfaced as a
          ~2026-02-13 panel freeze for ~148 tickers. The umbrella freshness scan
          (`ScanDailyTrainingDataTask`) only scans the watchlist, so the freeze passed
          SILENTLY → the served model trained on a half-frozen panel.

WHAT:     Two new tasks in `retrain_alpha158_fund.RetrainJob`, inserted BEFORE the panel build:
          1. `RefreshFullUniverseOhlcvTask` — iterates the FULL panel universe (tier_A + tier_B,
             NOT just the watchlist) and calls the incremental (cache-first, delta-only,
             append-merge, timeout-protected) fetch for each ticker. Resilient: one ticker's
             failure/delisting NEVER aborts the retrain. Records n_refreshed / n_stale /
             n_delisted / n_failed.
          2. `PanelUniverseFreshnessGuardTask` — after refresh, computes each panel ticker's
             OHLCV bar max date; if > `freshness_max_stale_fraction` (default 10%) of the
             universe lags the universe frontier by > `freshness_stale_after_days` (default 10
             trading days), emits a LOUD ntfy alert and — per `freshness_fail_on_stale` — either
             FAILS the retrain (default, fail-closed, mirroring the umbrella data-scan strict
             default) or proceeds with the warning. This would have caught the May freeze.

FWD-60D:  The guard reads RAW OHLCV bars, whose frontier is ~today−1 — NOT the built panel,
          which legitimately ends ~today−60 trading days after the (correct) fwd_60d label clip.
          So the expected fwd_60d frontier is distinguished from genuine input staleness (bars
          themselves old); an on-frontier universe never trips the guard.

NON-DESTRUCTIVE: uses only the incremental append-merge primitive; never overwrites/deletes
          `data/ohlcv/`. The fwd_60d label clip is UNCHANGED (correct for training).

RUNTIME WIRING (important):
          `fetch_ohlcv_incremental` is a base-data primitive
          (`renquant_base_data.loaders.data.fetch_ohlcv_incremental`), not natively importable
          from the orchestrator package boundary. It is DEPENDENCY-INJECTED via
          `RetrainContext.fetch_fn`; when None it resolves lazily through `_default_fetch_fn()`,
          which imports the primitive at call time via the subrepo PYTHONPATH the retrain already
          sets up (`_subrepo_pythonpath` includes `renquant-base-data/src`). Tests inject a fake
          fetch so no network/import happens. At runtime, the scheduled retrain leaves `fetch_fn`
          None and the real primitive is used; no additional wiring is required beyond the
          existing PYTHONPATH. The guard's on-disk reader is likewise injectable
          (`ohlcv_max_date_fn`, default reads the parquet) and also consumes the refresh-captured
          per-ticker max-date map.

CONFIG:   new CLI flags on `retrain_alpha158_fund`: `--refresh-ohlcv/--no-refresh-ohlcv`,
          `--ohlcv-timeout-sec`, `--panel-universe-file` (list or inventory; default
          `<data-dir>/transformer_universe_inventory.json`), `--freshness-stale-after-days`,
          `--freshness-max-stale-fraction`, `--freshness-fail-on-stale/--no-...`, `--ntfy-topic`.

TESTS:    `tests/test_retrain_ohlcv_coverage.py` (18 tests, mocks/fixtures) — full universe
          refreshed (not just watchlist), universe sourced from inventory tier_A+tier_B, delisted
          + failed tickers do not abort, guard fires past threshold (fail-closed raises + loud
          ntfy) and proceeds-with-warning when configured, guard stays QUIET at the expected
          fwd_60d frontier and below threshold, injected reader + runtime default-fetch seam,
          end-to-end refresh→guard catches the partial freeze. `test_retrain_alpha158_fund.py`
          shape test updated for the two new tasks; all 14 existing retrain tests still green.
          Run: `.venv/bin/python -m pytest tests/test_retrain_ohlcv_coverage.py -q` → 18 passed.

SCOPE:    orchestrator code + tests only. Does NOT run the retrain, does NOT touch the live
          umbrella tree, does NOT write production data. Follow-up (out of scope): retire the
          skip-existing `fetch_russell2000_ohlcv.py` behavior in favor of this incremental path,
          and widen the umbrella `ScanDailyTrainingDataTask` to the panel universe (or delete it
          in favor of this guard).

── REVISION (2026-07-01, Codex CHANGES_REQUESTED on PR #217): the guard FAILED OPEN ──
WHY:      Codex found the load-bearing guard could pass while proving nothing. Every soft path
          was a silent success. Fixes below make it fail CLOSED.

1. UNESTABLISHABLE UNIVERSE → FAIL CLOSED. `_resolve_panel_universe` no longer returns `[]`
   (which made refresh+guard an `n_universe=0` "success") on a missing / unreadable / corrupt /
   non-inventory / empty file, or an empty explicit universe. It raises `InventoryUnavailableError`
   and returns a FINGERPRINTED provenance (`sha256:` over the sorted active universe + generated_utc
   + kind) for a NON-EMPTY inventory. The fingerprint is persisted into the refresh summary and
   freshness report so every run is tied to a specific inventory content.

2. UNPROVABLE FRESHNESS → FAIL CLOSED. No resolvable OHLCV max dates now raises
   `FreshnessUnprovableError` instead of the old "soft skip" success — that state is exactly when a
   silent freeze slips through. An underivable expected session also raises.

3. INDEPENDENT REFERENCE SESSION (the uniform-freeze hole). Freshness is now measured against an
   INDEPENDENTLY-derived expected latest completed market session (`_resolve_expected_session`;
   injectable / persisted in the report), NOT `max(known dates)`. A globally-uniform freeze — the
   whole universe stuck on one old date — used to look 100% fresh; it now reads 100% stale and
   BLOCKS. Per-name lag is measured vs that expected session.

4. SHARED EXCHANGE CALENDAR. Replaced the plain Mon-Fri `np.busday_count` helper with the shared
   NYSE `pandas_market_calendars` calendar (`_default_session_gap` / `_expected_last_completed_session`,
   mirroring base-data's `_last_completed_nyse_session`). Holidays are skipped (e.g. Juneteenth 6/19,
   observed Independence Day 7/3) and half-days count as sessions with an early-close cutoff for the
   "is today complete" decision. Injectable so unit tests need no calendar; the real calendar is
   covered by importorskip tests, and `pandas-market-calendars` is added to CI install.

5. THRESHOLD + DELISTINGS + PROMOTION SEPARATION.
   • STRICT-DEFAULT: `DEFAULT_FRESHNESS_MAX_STALE_FRACTION` 0.10 → 0.0. The old 10% was unjustified
     (no coverage-loss-vs-rank/IC/turnover sensitivity was ever run) and could hide ~29/292 frozen
     names — enough to move cross-sectional ranks. Rather than ship an unjustified escape hatch, the
     guard now blocks on ANY genuinely-stale name. A non-zero tolerance remains available only as a
     deliberate, documented per-run override.
   • DELISTINGS via VERSIONED UNIVERSE, not tolerated failures: the inventory may declare
     `delisted_tickers` / `inactive_tickers` / `retired_tickers`; those names are pruned from the
     active universe (audited as `n_delisted_excluded`). Missing/absent bars for names that are NOT
     declared delisted count as stale (fail-closed), never absorbed by the tolerance slack.
   • REFRESH ≠ PROMOTION: `RefreshFullUniverseOhlcvTask` always completes to populate the audit
     summary; the fail-closed `PanelUniverseFreshnessGuardTask` is the authoritative gate, and this
     module still writes only to caller-provided (staging) artifact paths — it never promotes. Also
     `n_future` bucket added: bars dated after the expected session are integrity anomalies, counted
     stale.

TESTS (revised): `tests/test_retrain_ohlcv_coverage.py` now covers globally-uniform-stale → BLOCK,
          missing/corrupt/empty inventory → fail-closed, no-readable-parquet → fail-closed,
          no-resolvable-dates → fail-closed, underivable-expected-session → fail-closed, future-dated
          bars, versioned delisted exclusion + fingerprint, strict default, and the real
          NYSE-calendar holiday + half-day (early-close cutoff) semantics (importorskip).
          `tests/test_retrain_alpha158_fund.py` full-pipeline tests pin a fresh single-name universe
          (the guard is now fail-closed). Run:
          `.venv/bin/python -m pytest tests/test_retrain_ohlcv_coverage.py tests/test_retrain_*.py -q`
          → all green; full `make test` → 599 passed / 3 skipped.
NOTE:     stays compatible with PR #218 (σ-head `_rawlabel` refresh) which stacks on this branch —
          no shared symbol/task touched.

── REVISION 2 (2026-07-01, 2nd Codex CHANGES_REQUESTED on PR #217): per-name tolerance + replay ──
WHY:      Codex confirmed the fail-open defects are fixed but found one policy blocker plus a
          reproducibility gap. The tolerated stale FRACTION cannot see a PER-NAME lag, so the old
          `freshness_stale_after_days=10` let EVERY active ticker sit up to ten sessions (~two
          calendar weeks) behind and still read `n_bad=0` even at `max_stale_fraction=0.0`. And the
          reference-session injection existed on the context but `main()` did not expose it, so
          historical replay depended on the wall clock unless invoked programmatically.

1. PER-NAME LAG TIGHTENED 10 → 1 SESSION. `DEFAULT_FRESHNESS_STALE_AFTER_DAYS` is now 1 — a
   narrowly-justified single-session OPERATIONAL lag (the option Codex explicitly allowed in lieu of
   the 0/1/5/10-session sensitivity experiment, which needs data this code-only PR does not run).
   Why one and not zero: the refresh can legitimately finish before a vendor publishes a name's T+0
   bar, and a one-session input lag has zero label impact (the panel's fwd_60d clip puts the training
   frontier ~60 sessions back), so exactly one session is a deliberate, minimal allowance that still
   catches the ~two-month partial freeze and any multi-session drift. A wider tolerance is a
   documented per-run override, never a silent default.

2. RUN-BUNDLE PERSISTENCE of overrides + affected names. `freshness_report` now carries the FULL
   affected-name lists (`stale_names` with per-name lag, `missing_names`, `future_names`) — not just
   the worst 10 — plus an `overrides` block recording every knob deviating from the fail-closed
   defaults (`stale_after_days` / `max_stale_fraction` / `fail_on_stale`) and whether the expected
   session was pinned. The report is set BEFORE any fail-closed raise, so a blocked run still records
   the exact names to chase and any loosening an operator applied.

3. CLI/REPLAY INJECTION exposed on `main()`. New `--expected-session YYYY-MM-DD` pins the reference
   session directly (fully deterministic, no clock/calendar) and `--as-of {date|ISO-datetime}` pins
   the wall clock and lets the shared exchange calendar derive the session (a bare date = that day's
   end-of-session). `--expected-session` wins when both are given. Both flow into `RetrainContext`
   (`expected_session` / `now_fn`), so freshness never depends on when the job happens to run.

TESTS (revision 2): `tests/test_retrain_ohlcv_coverage.py` adds the 1-session default guard, a
          uniform multi-session-lag block, the exactly-one-session tolerance boundary, affected-name
          + override persistence (incl. on a fail-closed raise), CLI parsing of
          `--expected-session` / `--as-of` (bare date and timestamp) + bad-input rejection, `main()`
          injection into the context, the expected-session-over-as-of priority, and an as-of →
          real-NYSE-calendar session resolution (importorskip). Run:
          `.venv/bin/python -m pytest tests/test_retrain_ohlcv_coverage.py tests/test_retrain_*.py -q`
          → 121 passed. Still compatible with PR #218 (no shared symbol/task touched).
