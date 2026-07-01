# σ-head `_rawlabel` refresh — keep the QuantileHead label in lockstep with the panel

STATUS:   code + tests (this PR). Mocks/fixtures only — no real `build_raw_fwd60d_label.py`
          run, no production `_rawlabel` parquet write, no retrain executed.
BRANCH:   feat/sigma-head-rawlabel-refresh → **base `fix/panel-ohlcv-coverage` (#217)**
          (`hallovorld/renquant-orchestrator`). STACKS on #217; retargets to main when #217 merges.

ROOT CAUSE (fix #1 from the training-data investigation):
          `data/alpha158_291_fundamental_dataset_rawlabel.parquet` (the σ-head / QuantileHead
          RAW-label panel) sat at 2026-02-11 only because `scripts/build_raw_fwd60d_label.py`
          had NO retrain cadence — its source, `alpha158_291_fundamental_dataset.parquet`, was
          already fresh (to 2026-04-02) once the panel build ran. So the ranker panel moved
          forward while the σ-head label silently drifted ~2 months behind. #217 fixed the
          OHLCV coverage feeding the ranker panel; this fix keeps the derived σ-head label
          moving with it.

WHAT:     One new task in `retrain_alpha158_fund.RetrainJob`, inserted AFTER `MergeFundFeaturesTask`
          (the fresh panel's producer) and before `TrainGbdtScorerTask`:
          `RefreshSigmaHeadRawLabelTask` — regenerates the RAW `_rawlabel` panel from the freshly
          merged `alpha158_291_fundamental_dataset.parquet` so the QuantileHead label stays in
          lockstep with the ranker panel.

NON-DESTRUCTIVE: builds to a `<name>.staging` sibling then `os.replace`-swaps atomically into
          place; a pre-existing `_rawlabel` survives a failed build (a half-written staging is
          never swapped, and a stale staging is cleared before the next build).

ISOLATED: the σ-head is a SEPARATE downstream model, so ANY failure here logs + emits a LOUD
          ntfy alert but NEVER aborts the main XGB-ranker / calibrator retrain — the task records
          the outcome in `ctx.rawlabel_refresh_summary` and returns True. A missing upstream panel
          is a soft skip (`skipped-no-panel`, no alert) because the ranker path surfaces that
          failure itself; only a genuine build failure alerts.

RUNTIME WIRING:
          The RAW-label logic lives only as the umbrella script `scripts/build_raw_fwd60d_label.py`
          (hard-coded umbrella `data/` paths → not safe to shell out to from the orchestrator with
          a custom data dir). So the build callable is DEPENDENCY-INJECTED via
          `RetrainContext.rawlabel_build_fn`; when None it resolves to `_default_rawlabel_build_fn()`,
          a path-parametrized port of the script — `build(panel_in, panel_out, ohlcv_dir, horizon)`
          computing the UN-normalized `fwd_60d_excess_raw` = (ticker fwd_60d return − SPY fwd_60d
          return) on the return scale. Tests inject a fake builder so no real build runs / no
          production parquet is written; the task always points `panel_out` at the staging path.

CONFIG:   new CLI flag on `retrain_alpha158_fund`: `--refresh-rawlabel/--no-refresh-rawlabel`
          (default on).

TESTS:    `tests/test_retrain_sigma_head_rawlabel.py` (13 tests, mocks/fixtures) — task wired
          immediately after the fund-panel merge; build → staging → atomic swap; stale staging
          cleared first; failure isolated (returns True, alerts, prior artifact preserved) and
          silent under `quiet`; empty build output treated as failure; missing panel soft-skips
          without a false alert; disabled + dry-run skip without building; CLI flag defaults + main
          wiring; end-to-end pipeline proves a σ-head failure does NOT abort the ranker retrain;
          one test exercises the default builder's raw-excess math on TINY tmp parquet fixtures.
          `test_retrain_alpha158_fund.py` shape test updated for the new task; all existing retrain
          tests still green. Run: `.venv/bin/python -m pytest tests/test_retrain_*.py -q` → 64 passed.

SCOPE:    orchestrator code + tests only. Does NOT run the retrain, does NOT touch the live umbrella
          tree, does NOT write production data. Minimal + additive so it merges cleanly on top of #217.
