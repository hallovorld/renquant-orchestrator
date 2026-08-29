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
| Bar store identity = the store the census audited | `build_rows` sha256 of every consumed file at run time vs the GATE audit's `bar_store_sha256` (fail closed: `SystemExit` on a mismatch OR on a file the audit never saw) |
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
| `--dev-run` built ONLY from frozen constants; smoke hook private | `dev_run_config(auth)` (its only parameter is the gate authorization), `_smoke_config` (the only override path), `RunConfig` defaults |
| `--dev-run` fails closed without the Stage I-0 GATE_RUN bundle (r2) | `ACCEPTED_GATE_BUNDLE`, `load_gate_authorization`, `_bind_dev_run`; see "Gate binding + provenance (r2)" below |

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

Reads: the bar store (sha256 of every consumed file must equal the GATE audit's, else it refuses), `doc/research/data/2026-08-29-g2v3-i0-gate-run/g2v3_stage_i0_audit.json.gz` (the gate bundle's audit — the ONLY census audit the dev run may consume; the 2026-08-27 DEVELOPMENT_ONLY audit is no longer read), `/Users/renhao/git/github/RenQuant/data/ohlcv/SPY/1d.parquet`, and `sector_map` / `sector_etf_map` from the pinned `renquant-strategy-104/configs/strategy_config.json`. Writes: `doc/research/data/2026-08-29-g2v3-i1/report.json` + `g2v3_stage_i1_audit.json.gz` only. Sector ETFs present in the audited store: SPY, GLD, XLE, XLF, XLI, XLK, XLU, XLY `[VERIFIED — gate audit bar_store_sha256 keys, re-read 2026-08-29 for r3; the r2 text wrongly listed GLD as absent]`; XLV/TLT/XLRE/XLC are absent (`EXPECTED_ABSENT_FROM_AUDIT`), so healthcare / bond / defensive_bonds / real_estate / telecom get sec13 = NaN by the spec's NaN rule (commodity gets sec13 from GLD); recorded in `report.inputs.sec13_etf_available_by_sector`. With r3 the dev run writes `doc/research/data/2026-08-29-g2v3-i1/<run_id>/` (`report.json` + `g2v3_stage_i1_audit.json.gz`), one directory per run.

## Gate binding + provenance (r2, 2026-08-29 — PR #1084 review r1 by codex)

Bottom line: `--dev-run` now FAILS CLOSED (exit code 2) unless it can load the immutable Stage I-0 GATE_RUN bundle
(`doc/research/data/2026-08-29-g2v3-i0-gate-run/`, PR #1083 r2 = e41f04df, merged into this branch so #1084 stacks on
#1083; the diff collapses once #1083 merges) and verify it against a frozen constant block; every I-1 report carries a
`provenance` block that a validator rebuilds from disk. No `--dev-run` was executed. The 12-entry `INTERPRETATIONS`
list is byte-identical to r1 (the doc's 11 numbered readings above plus the s0-reference reading; nothing edited).

**Gate binding** (`scripts/experiments/g2v3_stage_i1_bases.py`):

- `ACCEPTED_GATE_BUNDLE` (module constant): dir, run_id `i0-gate-20260829-f3d5bf7b`, frozen commit
  `f3d5bf7bd75ffa9c0fb59f8c3bfa98fa509e8779`, run_status `GATE_RUN`, gate_verdict `PASS`, h=13, window
  2020-08-01..2024-06-30, seed list path/sha256/count (2144), census script sha256, design doc sha256, input-manifest
  aggregate sha256 + count (2124), report sha256 `da41a706..`, audit sha256 `dd5127d7..` — every value copied from the
  bundle's `provenance.json` `[VERIFIED — test_bound_constants_are_the_reviewed_gate_bundle compares field by field]`.
- `load_gate_authorization(repo_root)` -> `GateAuthorization`, else raises `GateNotAuthorized` with the specific reason.
  Order of checks: bundle dir / report / audit / provenance present; report `run_status == GATE_RUN` (a DEVELOPMENT_ONLY
  report is refused by name) and `gate_verdict == PASS` and `h == 13`; every provenance field above == the constant
  (run_id, frozen commit, seed/script/design hashes + commits, manifest aggregate + count, output paths + hashes,
  clean_tree is true); THEN the files on disk: report and audit sha256 == the constants, seed list sha256 + count, the
  manifest aggregate recomputed from the audit's `bar_store_sha256` (the gate's own aggregate method, `manifest_aggregate`)
  == the constant; THEN git: the frozen commit must be resolvable in `repo_root` and the census script + design doc blobs
  AT that commit must hash to the constants (a faithful bundle copy outside the reviewed repository is not authorization).
- `--dev-run` calls `load_gate_authorization(REPO)` FIRST (before reading `G2V3_BAR_STORE`); `dev_run_config(auth)` takes
  the authorization as its only parameter and sets `census_audit = GATE_AUDIT`; `run_stage_i1` re-checks via `_bind_dev_run`
  (DEV_RUN with no authorization, or with a census audit that is not the gate bundle's audit, or whose audit hash changed,
  raises). The old `CENSUS_AUDIT` constant pointing at `2026-08-27-g2v3-i0/` is deleted; the only remaining reference to
  that directory is the seed list, which is an input of the gate itself.
- Bar store: `build_rows` hashes every file it reads (names + SPY + sector ETFs) at run time; a hash differing from the
  gate audit's, or a file the audit never saw, is a fail-closed `SystemExit`. The consumed hashes are the audit's
  `consumed_sha256` and the report's aggregate manifest.

**Provenance** (`report.provenance`, built in `run_stage_i1`; validated by `validate_i1_provenance`): `run_id`
`i1-dev-<UTCdate>-<shortsha>` (`i1-smoke-…` for the smoke); `source` = `git rev-parse HEAD` + `clean_tree` from
`git status --porcelain --untracked-files=all` ignoring the bar store and the output dir (ignored paths listed);
`invocation` = argv, cwd, python, `G2V3_BAR_STORE`; `timestamps_utc` start/end from this process's own clock; `gate_bundle`
= run_id, frozen commit, verdict, report/audit/provenance sha256, manifest aggregate + count; `inputs` = sha256 of the
census audit, the strategy config file, the `sector_map` / `sector_etf_map` dicts (canonical JSON), the SPY daily parquet;
`frozen_parameters` = the full frozen block + the interpretations; `consumed_bar_manifest` = count + aggregate (gate
method). The validator rebuilds every hash from disk, requires DEV_RUN reports to carry the gate bundle / pinned config /
frozen folds, and checks the interpretations byte-identical.

**Evidence** `[VERIFIED — pytest, 2026-08-29]`: `tests/test_g2v3_stage_i1_harness.py` + `tests/test_g2v3_stage_i1_provenance.py`
+ `tests/test_g2v3_stage_i1_gate_binding.py` + `tests/test_g2v3_gate_run_bundle_provenance.py`: **58 passed**. Gate binding
cases: missing bundle / missing report / audit / provenance; DEVELOPMENT_ONLY report; the 2026-08-27 dev bundle dropped
into the gate dir; gate_verdict FAIL; wrong source commit; wrong run_id; wrong census-script / design-doc / seed /
manifest-aggregate / manifest-count / audit hash / h in provenance; clean_tree false; tampered report file (status +
verdict intact, only the hash catches it); tampered audit file; tampered seed list; faithful copy in a fresh `git init`
repo (commit not resolvable); CLI `--dev-run` with no bundle -> exit 2 before anything else; `run_stage_i1` refusing
DEV_RUN without authorization or with a non-gate audit; and the exact committed PASS bundle -> authorized
(run_id, commit, hashes, BEAR n_eff_adj 191.0). Provenance cases: complete block; validates clean; on-disk report ==
in-memory; consumed-manifest tamper; strategy-config / sector-map / SPY / census-audit tamper; gate-hash tamper;
frozen-block and interpretation tamper; identity / clock / argv checks; DEV_RUN claims held to the gate + frozen folds.
Default CLI smoke re-run: B0/B1/B2 block-t 10.117, B3 9.909, s0 10.830, unchanged from r1; `run_id
i1-smoke-20260829-62145271`, 33 consumed files, provenance validates `[VERIFIED — run 2026-08-29]`.

## Complete-store manifest + DEV_RUN identity (r3, 2026-08-29 — PR #1084 review r2 by codex)

Bottom line: a DEV_RUN now refuses BEFORE any bar is read unless the store carries, hash-matching, every file the gate
audit has for the eligible names + sector ETFs + SPY; the only tolerated absence is the frozen set of sector ETFs the
gate census never fetched (`EXPECTED_ABSENT_FROM_AUDIT = {TLT, XLC, XLRE, XLV}`), and the computed absent set must equal
it exactly. A DEV_RUN also refuses a source tree that is not clean outside the declared bar store and output root, mints
`i1-dev-<UTC YYYYMMDDTHHMMSSZ>-<shortsha>` and writes its own `<out_root>/<run_id>/`, refusing if that directory already
exists. Smoke keeps its fixed directory, overwrite and dirty-tree tolerance and records `run_status = SMOKE`. No
`--dev-run` was executed; the 12-entry `INTERPRETATIONS` list is byte-identical to r1/r2 `[VERIFIED — git show
674511c9 block == working copy]`.

**Ask 1 — store manifest before any load** (`scripts/experiments/g2v3_stage_i1_bases.py`):

- `check_store_manifest(store, audit, sessions, sector_etf_map, strict, expected_absent)` runs in `run_stage_i1` right after
  the session list and before `build_rows`; it opens no parquet (existence + whole-file sha256 only). `needed` = eligible
  names over the window + `sector_etf_map` values + SPY; `required` = needed ∩ the audit's `bar_store_sha256` keys.
  Strict (DEV_RUN): an eligible name or SPY outside the audit's file set → refused; audit-absent set ≠
  `EXPECTED_ABSENT_FROM_AUDIT` → refused ("a re-binding, not a run"); any `required` file missing from the store → refused
  naming the first 10; then every present file is hashed and a mismatch or an unaudited file → refused. Non-strict (SMOKE)
  keeps the old ergonomics (missing recorded, SPY missing refused, mismatch/unaudited refused). All refusals are
  `StoreNotAudited` (a `DevRunRefused`; CLI exit 2).
- `build_rows` takes the manifest and opens only the files it hashed; under DEV_RUN it re-checks that nothing is missing
  (`incomplete store manifest`, unreachable by design). The `missing.append; continue` path is gone: an ETF not in the
  manifest is either in the bound absent set (DEV_RUN) or a recorded smoke omission; an eligible name not in the manifest
  can only occur in SMOKE.
- The bound absent set was computed, not asserted: the gate audit's 2124 files vs the pinned config's 17-entry
  `sector_etf_map` → present GLD/SPY/XLE/XLF/XLI/XLK/XLU/XLY, absent TLT/XLC/XLRE/XLV; all 1,508 in-window eligible names
  are in the audit `[VERIFIED — python over the gate audit + pinned strategy_config.json, 2026-08-29]`.
  `test_bound_absent_set_is_exactly_the_gate_audits_missing_sector_etfs` recomputes it from the committed audit.
- Provenance gains `store_manifest_check` (strict, n_needed, n_required_in_audit, n_hashed, missing_files,
  absent_from_audit, expected_absent_from_audit, rule); `validate_i1_provenance` requires a DEV_RUN report to show
  strict=True, no missing files and absent_from_audit == the constant.

**Ask 2 — clean tree, unique identity, own bundle** (`dev_run_identity`, `run_stage_i1`):

- `source_state(REPO, ignore=[bar_store, out_root])` is computed right after `_bind_dev_run`; for DEV_RUN
  `dev_run_identity` refuses (`DevRunRefused`) when `clean_tree` is not True (git `status --porcelain --untracked-files=all`
  minus entries under the two declared paths, listing the first 10) or when no commit resolves; run_id =
  `i1-dev-<UTC YYYYMMDDTHHMMSSZ>-<shortsha>` from the process's own clock; bundle = `<out_root>/<run_id>/`, refused if it
  exists; the directory is created with `exist_ok=False` at write time (a race to the same id fails there). Smoke:
  `i1-smoke-<same stamp>-<shortsha|nogit>`, bundle = the fixed out dir, `exist_ok=True`.
- Provenance gains `outputs` (root, bundle_dir, file names, policy); the validator requires a DEV_RUN's `bundle_dir` to be
  `<root>/<run_id>/`, its `source.clean_tree` True, its run_id to carry a real sha, and the run_id's instant to equal
  `timestamps_utc.start` (the r2 date-only run_id form is rejected).
- CLI: `--dev-run` catches `DevRunRefused` (gate / tree / bundle / store) → `REFUSED --dev-run (fail closed): …`, exit 2.

**Evidence** `[VERIFIED — pytest, 2026-08-29]`: the four r2 files + new `tests/test_g2v3_stage_i1_dev_run_preflight.py`:
**75 passed** (58 r2 + 17 new). New cases — ask 1: bound set == the committed audit's real absent ETFs; complete synthetic
store passes strict and hashes every required file; missing eligible name → refused (and recorded, not refused, in
SMOKE); missing audited sector ETF → refused; missing SPY → refused; hash-mismatched file → refused; absent set ≠ bound
constant → refused (both an empty binding and the real constant against the synthetic store); eligible name / SPY absent
from the audit's file set → refused; an unaudited present file refused in both modes; `build_rows` refuses an incomplete
manifest under DEV_RUN. Every one runs with `pd.read_parquet` monkeypatched to raise, proving nothing is read before the
check. Ask 2, on a real tmp git repository with a DEV_RUN configuration that passes `_bind_dev_run` (real gate
authorization, the gate audit) and is refused at the store manifest, never past it: an untracked file → refused (tree
not clean, entry named), a staged file → refused; untracked files under the output root and the declared bar store are
not dirt while the same tree without the exclusions is dirty; a pre-existing `<root>/<run_id>/` → refused, its contents
untouched; clean + fresh → `dev_run_identity` returns the expected id/path and the run proceeds to the store check with
nothing written; no commit → refused; CLI `--dev-run` on a dirty tree → exit 2 with the reason; smoke runs twice into the
same fixed dir, `run_status = SMOKE`, strict=False, absent {XLV}, provenance validates. Default CLI smoke: B0/B1/B2
block-t 10.117, B3 9.909, s0 10.830 — unchanged from r1/r2; `run_id i1-smoke-20260829T111827Z-674511c9`
`[VERIFIED — run 2026-08-29]`.
