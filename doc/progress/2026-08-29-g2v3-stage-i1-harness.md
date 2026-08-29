# Progress: GOAL-2v3 Stage I-1 harness built as preregistered — NOT RUN on development data

2026-08-29. Bottom line: `scripts/experiments/g2v3_stage_i1_bases.py` implements the
Stage I-1 preregistration (doc/design/2026-08-27-goal2v3-intraday-granularity.md,
"Stage I-1" section + Amendment A1) item by item, with every frozen number in a
module-level constant that `tests/test_g2v3_stage_i1_harness.py` compares with the
spec text. It has been executed ONLY on a synthetic bar store (30 names x 40 sessions
x 39 slots). **No `--dev-run` has happened**: the real Stage I-1 run is gated on codex's
review of the Stage I-0 gate-run PR (#1083); running before that verdict would spend a
development attempt against an unreviewed gate. No production path is touched; the
harness reads the bar store, the census audit, SPY daily closes and the pinned
strategy config, and writes only `doc/research/data/2026-08-29-g2v3-i1/`.

## Implemented-as-preregistered checklist (spec item -> code)

| spec item | implementation (`scripts/experiments/g2v3_stage_i1_bases.py`) |
|---|---|
| Canonical 39-slot RTH grid, position = time, NaN = missing (A1) | `load_panel` (census slot convention `((h*60+m)-570)//10`) |
| Observation exists only when close[t-13], close[t], close[t+13] present; t = 13..25 | `build_rows` (`exists` mask over `SCREEN_SLOTS`) |
| Eligibility after BOTH drift layers, from the census artifact (not recomputed) | `load_census_audit`, `session_list`, `eligibility_matrix` |
| Bar store identity = the store the census audited | `build_rows` sha256 check vs `bar_store_sha256` (fail closed: `SystemExit`) |
| F: r1, r3, r13 (log), rv13, rng13, vz (60-session same-slot mean), gap, slot, m13, sec13, rel13; NaN on missing, no imputation | `name_features`, `trailing_log_return`; sec13 per `sector_etf_map` ETF from the bar store, NaN when the ETF is absent (`sec13_available` in the report) |
| Label: forward 13-bar within-session log return, dropped when truncated | `name_features` (`y13`); rows for t > 25 never exist |
| B0 pooled | `run_bases` (`state_cols["B0"]`) |
| B1 per K5 approx-regime, census regime formula on daily SPY, upsampled | `k5_regime_daily` (verbatim census formula), `regime_per_session` |
| B2 per config `sector_map` sector, <50,000 training rows per fold -> OTHER | `b2_state_map` (`MIN_SECTOR_ROWS`) |
| B3 2x2 macro state: slow = sign(close[D-1]/close[D-61]-1) over 60 completed sessions; fast = sign(close[t]/close[t-39]-1) with the prior-session slot required present; zero => +1; missing => abstain | `b3_slow_state`, `b3_fast_state`; missing state code -1 -> unscored in `run_bases` |
| Model class verbatim; xgboost version recorded | `XGB_PARAMS`, `fit_predict`; `report.versions.xgboost` |
| Row cap 4,000,000 without replacement, `default_rng(20260828 + 1000*fold + 100*base_code + state_index)`, global per fit; state_index = position in the base's SORTED state list | `cap_rows`, `fit_seed`, `run_bases` (`states = sorted(...)`); every seed persisted in the audit `fits` list |
| Folds: 5 forward-chaining 6-month OOF folds, expanding train, 13-bar purge | `FOLDS`, `fold_masks`, `apply_purge` (`PURGE_BARS`) |
| Screen: per session, Spearman at t=13..25 across eligible names (>=100), block = mean of 13, all 13 required | `session_blocks` (`MIN_NAMES_PER_IC`) |
| Regime episodes as in the census; rho1 raw + floored at 0; n_eff_adj = n(1-rho)/(1+rho); fail closed <8 pairs; block-t on adjusted units | `episodes_of`, `ess_stats` (`MIN_PAIRS`) |
| Life bar block-t >= 1.0 OVERALL; per regime reported, never gating | `screen_base` (`passes_life_bar` from `overall` only; `per_regime` informational) |
| Secondary horizons {1,3,39} diagnostic only | `screen_base` (`secondary_horizons_DIAGNOSTIC_ONLY`; h=39 "not computed") |
| s0 = -r13 carried as the naive reference, not a base | `build_rows` (`rows["s0"]`), `run_stage_i1` (`s0_reference`) |
| Each base's block-t vs B0 + Stage I-2 trigger (a conditioned base passes AND beats B0) | `run_stage_i1` (`base_vs_b0`, `stage_i2_trigger`) |
| Report + compact audit (per-base per-session block series, per-fold row counts, seeds) | `run_stage_i1` -> `report.json`, `g2v3_stage_i1_audit.json.gz` |
| `--dev-run` built ONLY from frozen constants; smoke hook private | `dev_run_config` (no parameters), `_smoke_config` (the only override path), `RunConfig` defaults |

## Interpretations (spec text that needed a concrete reading; conservative choice; all listed in `INTERPRETATIONS` and copied into every report)

1. Returns r1/r3/r13/m13/sec13 and the label are LOG returns (rel13 = r13 - sec13 needs one unit); gap, vz, rng13 follow the spec's literal arithmetic formulas.
2. rv13 = sqrt(sum of the 13 squared 1-bar log returns t-12..t) — requires closes t-13..t.
3. rng13 window is the 13 bars t-12..t; NaN when max high == min low.
4. vz denominator = mean of the PRESENT same-slot volumes over the 60 sessions strictly before D, NaN below 48 present (80% — the frozen eligibility coverage fraction, not a new number). A literal "all 60 present" rule would void vz on the thin IEX feed.
5. gap = open[slot 0] / prior session's last present RTH close - 1 (the census's IEX session-close convention).
6. B1 state for session D = the K5 regime as of the PRIOR session's close (`regime.shift(1)` — the pure upsample of the post-close 104 regime series; no same-day close information, matching B3's explicit "as-of prior close" rule). Screen EPISODES use the census's unshifted same-day mapping so the block structure equals the I-0 artifact's. `B1_STATE_LAG_SESSIONS` is the single constant a reviewer can veto.
7. B2: names absent from `sector_map` (most of the 1,256-name eligible panel; the map covers 159 watchlist names) go to OTHER rather than being dropped; OTHER is never re-folded.
8. A conditioned state with zero training rows in a fold fits nothing; its OOF rows are unscored (abstain), never re-routed.
9. The 13-bar purge is implemented literally on continuous bar numbers and is inert on the A1 grid (within-session labels; first OOF row at slot 13) — `test_purge_is_literal_and_inert_on_the_a1_grid`.
10. Secondary horizons: h=1/h=3 rank the h=13-trained prediction against the 1-/3-bar within-session label; h=39 is not computable within a session.
11. A bar-time IC with undefined Spearman (constant predictions) is missing, so that session forms no block.

## What is NOT run yet and why

- `--dev-run` on the real bar store: NOT executed. Gate: codex's review of the Stage I-0 gate-run PR (#1083). The harness must not consume a development attempt before the gate that authorizes Stage I-1 is reviewed.
- Consequently there is no Stage I-1 evidence, no base verdict, no xgboost-version statement for the record beyond the smoke's (`2.1.4` in the umbrella venv, `[VERIFIED — python -c "import xgboost"]`), and no I-2 trigger evaluation.

## Evidence (synthetic smoke only; no development-window number exists)

- `make test` (worktree, sibling src pointed at the real checkouts): **6802 passed, 17 failed, 11 skipped** `[VERIFIED — make test, 2026-08-29]`. The 17 failures are all pre-existing checkout-relative tests (13 `git -C <worktree>` subprocess errors, sibling-path FileNotFound, pinned-pipeline HEAD assertions) that measure the sibling layout of the checkout — none touch the files in this PR; the same family as memory note "Tests that measure the operator's disk".
- `tests/test_g2v3_stage_i1_harness.py`: **9 passed** `[VERIFIED — pytest]`: frozen constants == spec; `--dev-run` config takes no overrides; B3 zero/missing rules; purge literal + inert; row cap seeded, without replacement; ESS fails closed <8 pairs; planted-signal smoke B0 block-t = 10.12 > 1.0 with schema/audit/seed checks; null-store |block-t| <= 0.74 for all bases; eligibility from the audit honoured (28/29/30 names on the dropped sessions) and a hash-changed store refused.
- Default CLI smoke (`python scripts/experiments/g2v3_stage_i1_bases.py`): 15,600 synthetic observations, 10 fits, B0/B1/B2 block-t 10.12, B3 9.91, s0 10.83, trigger false (as designed on a single-state synthetic panel) `[VERIFIED — run 2026-08-29]`.

## The exact development command (do not run before the #1083 review lands)

```bash
G2V3_BAR_STORE=/path/to/the/audited/g2v3_bars \
  ../RenQuant/.venv/bin/python scripts/experiments/g2v3_stage_i1_bases.py --dev-run
```

Reads: the bar store (sha256 of every consumed file must equal the census audit's, else it refuses), `doc/research/data/2026-08-27-g2v3-i0/g2v3_stage_i0_audit.json.gz`, `/Users/renhao/git/github/RenQuant/data/ohlcv/SPY/1d.parquet`, and `sector_map` / `sector_etf_map` from the pinned `renquant-strategy-104/configs/strategy_config.json`. Writes: `doc/research/data/2026-08-29-g2v3-i1/report.json` + `g2v3_stage_i1_audit.json.gz` only. Sector ETFs present in the audited store: SPY, XLE, XLF, XLI, XLK, XLU, XLY `[VERIFIED — audit bar_store_sha256 keys]`; XLV/GLD/TLT/XLRE/XLC are absent, so healthcare / commodity / bond / defensive_bonds / real_estate / telecom get sec13 = NaN by the spec's NaN rule (recorded in `report.inputs.sec13_etf_available_by_sector`).
