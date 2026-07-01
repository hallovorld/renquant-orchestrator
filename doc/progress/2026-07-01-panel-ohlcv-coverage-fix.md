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
