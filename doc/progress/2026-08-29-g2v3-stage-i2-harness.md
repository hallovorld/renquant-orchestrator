# Progress: GOAL-2v3 Stage I-2 harness implemented as preregistered (#1089) — synthetic smoke only; NOT RUN on development data

STATUS:    delivered (harness + tests + this record). `--dev-run` has NOT been executed;
           no development-window number exists for Stage I-2. No production path is
           read or written; the harness reads the audited bar store, the I-0 gate
           audit, SPY daily closes and the pinned strategy config, and would write only
           `doc/research/data/2026-08-29-g2v3-i2/<run_id>/`.

WHAT:      `scripts/experiments/g2v3_stage_i2_stack.py` implements
           `doc/design/2026-08-29-goal2v3-stage-i2-prereg.md` (#1089) §1–§5 literally,
           on top of the IMPORTED Stage I-1 harness (`g2v3_stage_i1_bases.py`, reused
           for the feature builder, folds/purge/row cap, base fitting, session-block /
           episode / AR(1)-ESS / block-t machinery, store-manifest and gate guards,
           provenance helpers — nothing re-implemented). Frozen constants at module top,
           each traceable to a prereg section (file:line below). Two entry points as in
           I-1: default synthetic smoke; `--dev-run` fail-closed (exit 2) on the I-0 gate,
           the I-1 bundle binding, a dirty tree, an existing bundle, an incomplete store,
           a consumed-bar aggregate that is not the I-1 bundle's, and the §1.1 determinism
           guard — which runs BEFORE any meta fit. 82 tests in
           `tests/test_g2v3_stage_i2_harness.py` + `tests/test_g2v3_stage_i2_binding.py`.

WHY/DIR:   GOAL-2v3 intraday-granularity line: prereg #1076 → I-0 gate #1083 → I-1
           harness #1084 → I-1 dev run #1088 (trigger fired by 0.087) → I-2 prereg #1089
           (merged before any fit) → this harness → ONE `--dev-run` from a clean main
           worktree (its own PR). The prereg's execution plan (§7.2) requires the harness
           PR to land with tests for every guard and for the pass-bar arithmetic before
           the run; the harness-level readings of prereg text that was still open are
           declared here and in the report's interpretations list BEFORE the run, so the
           run cannot be tuned after the fact.

EVIDENCE:  §4(b) block — this PR makes no model/data claim; the only numbers are a
           synthetic smoke's and the frozen constants copied from #1088 / #1089.
           artifact:      none committed (the smoke writes to a temp dir). Harness
                          `scripts/experiments/g2v3_stage_i2_stack.py` (1,186 lines).
           prod or exp:   experiment code only; `--dev-run` not executed.
           existing data: the I-1 bundle `i1-dev-20260829T113813Z-666484a7` (#1088) is the
                          binding target; its report/audit sha256 and consumed-bar aggregate
                          are re-hashed from disk by `test_bound_constants_are_the_committed_i1_bundle_field_for_field`
                          `[VERIFIED — pytest, 2026-08-29]`.
           best-known?:   n/a (no result).
           scope:         "Stage I-2 harness, synthetic smoke only; 146 passed
                          (82 I-2 + 64 I-1) in 61 s `[VERIFIED — pytest, 2026-08-29]`;
                          default CLI smoke 7 s `[VERIFIED — run 2026-08-29]`; vs existing
                          best: none (no dev run)".

NEXT:      (1) codex review of this PR; (2) ONE `--dev-run` from a clean main worktree
           containing this harness, `G2V3_BAR_STORE` pointed at the audited store
           (`wt-gate/scripts/experiments/g2v3_bars`, the store #1088 consumed);
           (3) record PR with the bundle + descriptive research doc quoting the §4.4
           outcome row and stating the P1/P2/P3 margins as numbers. Nothing else is
           unblocked; the sealed window stays untouched.

## Frozen constants → prereg section (`scripts/experiments/g2v3_stage_i2_stack.py`)

| constant (line) | prereg | value |
|---|---|---|
| `ACCEPTED_I1_BUNDLE` (89) | §1 binding | dir `doc/research/data/2026-08-29-g2v3-i1/i1-dev-20260829T113813Z-666484a7`, run_id, source commit `666484a7ab37dc9f88dd5692f8d9e90f3aab9332`, run_status `DEV_RUN`, report sha256 `666d9c6a…`, audit gz sha256 `d124d8f2…`, consumed-bar aggregate `4addcbe2…` over 1,508 files, gate run_id `i0-gate-20260829-f3d5bf7b`, trigger fired, n_observations 10,487,004 / n_oof 7,097,590, s₀ 4.1861 / 622 blocks — every value read from the bundle's report.json on main `[VERIFIED — test_bound_constants_are_the_committed_i1_bundle_field_for_field]` |
| `I1_HARNESS_SHA256` (111) | §1.1 "re-fit … exactly as preregistered in I-1" | `13c31d12…` = sha256 of `g2v3_stage_i1_bases.py` at 666484a7 AND on disk (the module I-2 imports) `[VERIFIED — git show 666484a7:… \| shasum; test_bound_constants…]` |
| `EXPECTED_I1_BLOCK_T` / `EXPECTED_I1_N_BLOCKS` / `DETERMINISM_DECIMALS` (114–116) | §1.1 + interpretation 5 | B0 3.5042/622, B1 3.1837/511, B2 3.5915/622, B3 3.2394/619; equal to 4 dp and equal n_blocks, else REFUSED |
| `SURVIVING_BASES` (118) | interpretation 1 | all four |
| `META_FOLDS` / `META_OOF_PERIOD` (137–138) | §2 table | derived from I-1 `FOLDS`: M1 2022H1→2022H2, M2 2022H1–2022H2→2023H1, M3 …→2023H2, M4 2022H1–2023H2→2024H1; meta-OOF 2022-07-01..2024-06-30; 2022H1 never meta-scored |
| `META_PURGE_BARS` | §2 | 13 (I-1 `apply_purge`, inert on the A1 grid) |
| `META_SEED_BASE`, `META_XGB_PARAMS`, `META_ROW_CAP` (141–145) | §3 | 20260829 + 1000·meta_fold; reg:squarederror, depth 2, 200 trees, lr 0.05, subsample 0.8, colsample 1.0, min_child_weight 50, hist, random_state 20260829, n_jobs 8; 4,000,000 without replacement |
| `META_FEATURES` (146) | §3 | p_B0..p_B3 (NaN on abstain), n_abstain, regime one-hot ×4, b3_slow_sign, slot — 11; s₀ is NOT a feature; no sector one-hot |
| `SECONDARY_HORIZONS` (150) | interpretation 6 | h=1, h=3 for M_xgb, diagnostic only |
| `P1_LIFE_BAR_T`, `P1_BEAR_MIN_N_EFF_ADJ`, `SERIES` (153–155) | §4 | 1.0; 30; M_xgb, M0, B0..B3, s₀ all on the common sample |
| `OUTCOME_REGISTER` (158) | §4.4 | PASS / FAIL-A / FAIL-B / REFUSED rows verbatim; the report's `outcome` quotes the row it lands on |
| `PREREG_INTERPRETATIONS` (177) | §5 | the six, verbatim (`test_outcome_register_and_interpretations_are_verbatim_from_the_prereg` finds each numbered line in the markdown) |
| `HARNESS_INTERPRETATIONS` (193) | — | the eight harness-level readings below, appended as interpretations 7–14 |

## Harness-level interpretations declared BEFORE the dev run (prereg text still open; numbered 7–14, in every report)

7. `meta_fold` in the seed formula is the M-number (M1 → 1 … M4 → 4): seeds 20261829, 20262829, 20263829, 20264829; `random_state` stays 20260829 for every meta-fit (the seed formula governs the row-cap subsample, as in I-1).
8. The determinism guard additionally requires: the s₀ reference to reproduce the I-1 bundle (4.1861 / 622 — no fit is involved, so a mismatch is a row-set defect, still REFUSED); the bars consumed by the re-fit to aggregate to the I-1 bundle's manifest (checked after the store is read, before any fit); the imported I-1 harness to be byte-identical to the blob at the bundle's commit.
9. Regime one-hot: an undefined prior-close regime (I-1 code −1; impossible inside the dev window) → all four indicators 0; `b3_slow_sign` NaN (fewer than 61 daily closes before D) is passed as missing. Both counts are reported.
10. Meta-training rows = every base-OOF row of the training halves (the label always exists by the A1 rule; features may be NaN); no row dropped for abstains; purge via I-1 `apply_purge`.
11. M0: per base, z over that base's FINITE predictions among the rows present at the session×slot; a base with < 2 finite values or zero spread contributes nothing; M0 = the plain sum of the available z's; the MIN_NAMES_PER_IC floor counts rows present; a row with no available z has no M0.
12. P1 (life bar AND BEAR n_eff_adj ≥ 30) is evaluated on the common sample — the same row set as P2/P3; M_xgb on its full meta-OOF rows is reported beside it, never gating. An unestablished block-t fails the corresponding P; a BEAR n_eff_adj of "unestablished" fails P1.
13. The §1.2 sector code is carried in the audit as the per-fold post-fold B2 OOF state list from the re-fit; it enters the stack only through p_B2 (§3).
14. The excluded fraction is reported over the meta-OOF rows where M_xgb has a prediction (all of them — XGBoost scores NaN natively), attributed per base by abstain count; the M0-only extra exclusion is reported separately.

## `--dev-run` order of refusal (all `DevRunRefused`, CLI exit 2, nothing written)

1. `I1.load_gate_authorization(REPO)` — the I-0 GATE_RUN bundle (unchanged from I-1).
2. `load_i1_binding(REPO)` — file checks (report/audit sha256 on disk; run_status DEV_RUN; run_id, source commit, clean tree, gate run_id, trigger fired, all four `passes_life_bar`, block-t/n_blocks == the constants, s₀, I-1 frozen folds/params; consumed aggregate rebuilt from the audit; the I-1 harness on disk hashes to `I1_HARNESS_SHA256`) THEN git (commit resolvable; the harness blob at that commit hashes to the constant).
3. `_bind_dev_run` — I-1's gate/audit/config re-check + the I-1 bundle re-hashed + the determinism targets == the constants.
4. `dev_run_identity` — clean tree outside the bar store / output root; `i2-dev-<UTC>-<shortsha>`; `<out_root>/<run_id>/` must not exist.
5. `I1.check_store_manifest(strict=True)` before any bar is read.
6. Consumed-bar aggregate == the I-1 bundle's (after `build_rows`, before `run_bases`).
7. `determinism_guard` after the base re-fit, BEFORE `fit_meta`.

## Evidence (synthetic smoke only)

- `PYTHONPATH=src …/.venv/bin/python -m pytest -q tests/test_g2v3_stage_i2*.py tests/test_g2v3_stage_i1*.py`: **146 passed in 61 s** (82 I-2: 28 harness + 54 binding; 64 I-1 unchanged) `[VERIFIED — pytest, 2026-08-29]`.
- I-2 cases: constants vs the prereg markdown (hashes, run_id, commit, block-t/n_blocks, xgb params, row cap, seed formula, 11 features, meta-fold table rows, outcome-register rows, six interpretations numbered); I-1 import not copy; `dev_run_config(auth, i1)` only; meta folds forward-chaining with the first half never scored; literal purge; capped rows seeded without replacement; NaN meta-features + n_abstain + one-hot + slow sign; M0 floor + z arithmetic; common-sample exclusion arithmetic; P1/P2/P3 + every register row on 10 synthetic cases incl. equality-is-not-> and unestablished; margins as numbers; determinism guard exact/5th-dp/4th-dp/n_blocks/None/s₀. Binding: committed bundle bound; faithful copy passes file checks; missing dir/report/audit; tampered report/audit by hash; SMOKE / DEVELOPMENT_ONLY / GATE_RUN / None status; wrong run_id; wrong commit; dirty I-1 tree; foreign gate; trigger not fired; B3 not surviving; block-t / n_blocks / s₀ drift; consumed manifest (report and audit); I-1 frozen block drift; harness changed / missing; copy in a fresh `git init` (commit not resolvable); blob at the commit hashing differently. Run flow: off-by-1e-4 block-t and off-by-1 n_blocks → `DeterminismRefused` with `fit_meta` forbidden and nothing written; exact targets → guard PASS, deterministic run-to-run; foreign consumed aggregate → refused before `run_bases`. Preflight on a real tmp git repo: no I1Binding / foreign targets / no gate; dirty tree; existing bundle; clean+fresh proceeds to the store check; CLI exit 2 without the gate, without the I-1 bundle, on a dirty tree. Provenance: complete block validates clean with the real gate + I-1 binding attached; 25 single-claim falsifications; DEV_RUN relabel surfaces the frozen-folds / guard / consumed / strict / audit-path / bundle-dir requirements.
- Default CLI smoke (`python scripts/experiments/g2v3_stage_i2_stack.py`, 30 names × 40 sessions, 3 base folds → M1, M2): 15,600 observations, 15 base fits, 2 meta fits; base re-fit block-t B0/B1/B2 12.746, B3 13.14; meta-OOF 6,240 rows, common sample 6,240 (excluded 0.0); series on the common sample M_xgb 8.5172, M0 8.8284, B0/B1/B2 8.6138, B3 9.0034, s₀ 9.1906; P1 false (BEAR n_eff_adj unestablished — the synthetic SPY has no BEAR episode), P2 false, P3 false → `FAIL-B`, `binding: false`; 7 s; provenance validates `[VERIFIED — run 2026-08-29]`. A planted-reversal synthetic panel is not evidence about the stack; the smoke shows the machinery runs and the arithmetic is exercised end to end.

## The exact development command (do not run before this PR's review lands)

```bash
G2V3_BAR_STORE=/path/to/the/audited/g2v3_bars \
  ../RenQuant/.venv/bin/python scripts/experiments/g2v3_stage_i2_stack.py --dev-run
```

Writes `doc/research/data/2026-08-29-g2v3-i2/i2-dev-<UTC>-<shortsha>/report.json` + `g2v3_stage_i2_audit.json.gz`. The report's `outcome.verdict` is one of PASS / FAIL-A / FAIL-B with the §4.4 row quoted; REFUSED never produces a report.
