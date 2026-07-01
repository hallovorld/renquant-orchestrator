# σ-head `_rawlabel` refresh — keep the QuantileHead label in lockstep with the panel

STATUS:   code + tests (this PR, #218). Mocks/fixtures only — no real `build_raw_fwd60d_label.py`
          run, no production `_rawlabel` parquet write, no retrain executed. Rebased
          2026-07-01 onto #217's resolved tip (`f99fe3c2`, post-#217-fail-closed-revision +
          post-main-merge) after #217 landed its own conflict fix (`ff089467`); one
          conflict resolved (two independently-added functions adjacent in the same
          file — kept both, no logic change).
BRANCH:   feat/sigma-head-rawlabel-refresh → **base `fix/panel-ohlcv-coverage` (#217)**
          (`hallovorld/renquant-orchestrator`). STACKS on #217; retargets to main when #217 merges.

CONSUMER-SIDE ENFORCEMENT (Codex CHANGES_REQUESTED, r2): the first revision of this PR
          defined `assert_rawlabel_admissible` / wrote an invalidation receipt but nothing
          called it — Codex correctly flagged that as fail-open at the system boundary
          (a helper nobody calls enforces nothing). Fixed by a COORDINATED companion PR:
          **`hallovorld/RenQuant` PR #427** wires the equivalent check directly into
          `scripts/train_ngboost_proper.py` — confirmed by investigation to be the REAL,
          currently-live σ-head training entrypoint (its default `--panel-path` is this
          exact `_rawlabel` corpus; its output schema/`train_run_id` convention matches
          `backtesting/renquant_104/artifacts/prod/ngboost-head.alpha158_fund.json`,
          `trained_date=2026-05-17`, currently wired `enabled=true` in
          `strategy_config.json`). RenQuant does not import this package, so #427
          reimplements the receipt/provenance JSON schema by file-contract, plus an extra
          check this repo's helper does not: the provenance `source_panel_sha256` must
          match the CURRENT source panel's digest (catches drift even with no receipt).
          #427 ships its own integration test invoking the real training `main()` end to
          end (INVALID/missing/mismatched → refuses before any read; matching → trains
          and writes a real artifact). **Until #427 merges, this repo's receipt/provenance
          are recorded correctly but NOT YET enforced at the training boundary** — do not
          claim end-to-end admission control before it lands (docstrings in
          `retrain_alpha158_fund.py` were corrected to say this explicitly, not just
          "a follow-up").

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

ISOLATED BUT NOT FAIL-OPEN: the σ-head is a SEPARATE downstream model, so ANY failure here logs +
          emits a LOUD ntfy alert but NEVER aborts the main XGB-ranker / calibrator retrain — the
          task records the outcome in `ctx.rawlabel_refresh_summary` and returns True. But an
          ntfy alert alone is not a data-integrity guarantee, so every non-certified outcome (build
          failure, empty/rejected output, OR a missing upstream panel) also writes a durable
          `<corpus>.INVALID.json` invalidation receipt beside the corpus (missing-panel stays a
          soft skip — no alert, since the ranker path surfaces that itself — but still records the
          receipt). A successful, VALIDATED swap clears the receipt and stamps
          `<corpus>.provenance.json` (horizon, source-panel sha256 digest + frontier, row/ticker
          counts, finite fraction). `_default_rawlabel_validate_fn` runs pre-swap and refuses
          (staging discarded, prior corpus untouched) unless schema/non-empty/unique-keys/exact
          source-panel coverage/finite-fraction-floor all hold. See "CONSUMER-SIDE ENFORCEMENT"
          above for where the receipt/provenance are actually enforced.

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

TESTS:    `tests/test_retrain_sigma_head_rawlabel.py` (grew from 13 → real-parquet-backed tests
          across both revisions) — task wired immediately after the fund-panel merge; build →
          staging → validate → atomic swap; stale staging cleared first; failure isolated (returns
          True, alerts, prior artifact preserved, INVALID receipt written) and silent under
          `quiet`; empty build output treated as failure; missing panel soft-skips without a false
          alert but still writes a receipt; disabled + dry-run skip without building; CLI flag
          defaults + main wiring; end-to-end pipeline proves a σ-head failure does NOT abort the
          ranker retrain; the default builder's raw-excess math is asserted bit-for-bit parity
          against a frozen fixture transcribed from the canonical
          `scripts/build_raw_fwd60d_label.py` loop; each pre-swap validation rejection mode
          (schema/empty/duplicate-keys/coverage-mismatch/finite-floor) covered on real parquet.
          `test_retrain_alpha158_fund.py` shape test updated for the new task; all existing retrain
          tests still green. Run: `.venv/bin/python -m pytest tests/test_retrain_*.py -q` → 102
          passed (post-rebase onto #217's resolved tip).

SCOPE:    orchestrator code + tests only. Does NOT run the retrain, does NOT touch the live umbrella
          tree, does NOT write production data. Minimal + additive so it merges cleanly on top of #217.
          Consumer-side enforcement of the receipt/provenance contract this PR writes lives in a
          SEPARATE, coordinated repo (`hallovorld/RenQuant` PR #427) — see "CONSUMER-SIDE
          ENFORCEMENT" above; that PR states its receipt producer is this PR (#218).
