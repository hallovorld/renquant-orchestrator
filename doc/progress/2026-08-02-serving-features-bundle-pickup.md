# Serving feature persistence — rollout step 3: the daily bundle consumes the record

STATUS: delivered — additive tri-state `serving_features` block in the daily
`run_bundle.json` + 9 new tests + full-suite regression; PR open under
review.
WHAT: implements rollout step 3 of the MERGED pipeline#250 design (step 2 =
pipeline#252, merged 2026-08-02). `PersistDailyRunBundleTask`
(`src/renquant_orchestrator/daily.py`) now emits
`"serving_features": serving_features_block(ctx.inference_context,
output_dir=ctx.output_dir)` — a new module
`src/renquant_orchestrator/serving_features_provenance.py` that (1)
completes any deferred parquet write into THIS run's output dir via the
pipeline's exported `write_staged_serving_features` (the identical
finalization the pipeline's own payload writers perform — the real #252
data flow), then (2) forwards the digest sidecar verbatim via
`serving_features_bundle_block`. Tri-state and additive per the
`serving_bundle` / `g4_session` / `wf_gate_provenance` idiom: explicit
`not_staged` marker when the producer never fired (sequence/history scorers
— today's live hf_patchtst primary — and pre-step-2 contexts), explicit
`pipeline_support_unavailable` marker on version skew (guarded import, the
`_record_bundle_contract` ImportError tri-state precedent), forwarded
`written` / `write_failed` from the producer otherwise, `recorder_error`
catch-all. NEVER raises (the `wf_gate_provenance` recorder rule).
WHY/DIR: closes the measured gap this chain exists for — the daily bundle
carried 0 feature keys against ~290 decision rows (orch#678) and the served
matrix was unrecoverable in principle (orch#703). Rollout: 1 design
(pipeline#250, MERGED) → 2 pipeline writer+sidecar (pipeline#252, MERGED)
→ **3 this PR** → 4 pin batch (operator). Nothing reaches the live run
until step 4.
EVIDENCE:
  artifact:      tests/test_serving_features_bundle_block.py (9 tests);
                 src/renquant_orchestrator/serving_features_provenance.py;
                 the one wired key in src/renquant_orchestrator/daily.py
  prod or exp:   exp — additive bundle key; live daily unchanged until the
                 pin batch. On the current live primary (hf_patchtst,
                 score_with_history) the producer stages nothing and the
                 block is the explicit `not_staged` marker — pinned by test.
  existing data: pipeline#250 design (governs; names this step),
                 pipeline#252 (the producer + exports this consumes),
                 orch#678/#703 (the measured gap), orch#647 (the Stage-3
                 producer this unblocks)
  best-known?:   yes — the pickup follows the bundle's own established
                 additive-block idiom and imports the pipeline's producer
                 contract instead of re-implementing any of it; the only
                 alternative (a always-absent key or a raising import)
                 recreates defect shapes this repo has already catalogued
  scope:         "this is tests/test_serving_features_bundle_block.py (9
                 tests) + tests/test_daily_bundle_contract.py + full
                 orchestrator suite, exp path (block inert-absent on the
                 live primary), vs baseline = origin/main 2f014b8c"

  Measured counts. Full suite on this head, default `make test` (stale
  sibling checkouts — the honest local reality): **5419 passed, 14
  skipped, 0 failed** `[VERIFIED — make test in the PR worktree,
  2026-08-02]`. Baseline at `origin/main` 2f014b8c in a sibling-located
  worktree, same invocation: **5416 passed, 8 skipped, 0 failed**
  `[VERIFIED — make test at 2f014b8c, 2026-08-02]`. Delta +3 passed / +6
  skipped = exactly the 9 new tests under the local skew (see below)
  `[DERIVED]`. Against CURRENT siblings (pipeline main 398cda9 with #252,
  common main ef7726d with the AC6 binding), via pytest `-o pythonpath=`
  overriding the hardcoded ini paths: **9/9 new tests pass**; with current
  pipeline + stale common: 7 passed / 2 skipped (the pre-existing
  common#40 `needs_binding` skew, orch#747 item 6)
  `[VERIFIED — pytest -o runs, 2026-08-02]`.
  tests/test_daily_bundle_contract.py: **6 passed, 6 skipped** under the
  default invocation (all 6 skips = the pre-existing common#40
  `needs_binding` skew — untouched by this PR), and **12/12 pass** under
  the current-siblings `-o pythonpath=` run `[VERIFIED — both pytest runs,
  2026-08-02; an earlier draft of this doc ASSERTED "10 passed, 2 skipped"
  without measuring — corrected from the actual runs]`.

  Two pre-existing tests were UPDATED, both designed to move with this
  change:
  * `tests/test_feature_snapshot_dependency.py::
    test_the_daily_bundle_does_not_carry_feature_vectors` — the test whose
    OWN docstring said "if this starts failing, step 1 of the plan has
    landed". It landed (pipeline#252 + this PR); flipped to its successor
    `test_the_daily_bundle_now_carries_the_serving_features_block`, which
    pins the NEW premise.
  * `data/strategy_snapshot.json` — regenerated via the failure message's
    own remedy (`scripts/generate_strategy_snapshot.py --update`); the
    single diff line is the new `serving_features_provenance` module in
    `source_modules` `[VERIFIED — git diff, 2026-08-02]`.

  Measurement trap, recorded in the skipif reason itself: the Makefile's
  `PIPELINE_SRC` override does NOT reach pytest — pyproject's
  `[tool.pytest.ini_options] pythonpath` hardcodes `../renquant-pipeline/src`
  ahead of the environment (measured with a probe test: the same import
  succeeds under `python -c` and fails under pytest). The new tests
  therefore loud-skip on the stale sibling (the `needs_binding` precedent)
  and CI, which checks out all siblings at main, runs them for real.

NEXT: (4) pin batch (operator). After the first live run persists a matrix
and the bundle carries its digest, the Stage-3 T-1 producer design
(orch#647) can be written against real bytes — the successor test now pins
that the missing input has a standing home. AC6 gate-design rule: N/A — no
capital-admission gate added, tightened, or loosened; a provenance recorder
on the bundle, and the AC6 R4 contract validation
(`require_gate_provenance`) is pinned undisturbed in both the staged and
absent states.
