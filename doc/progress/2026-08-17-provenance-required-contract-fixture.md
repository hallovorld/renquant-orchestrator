# Provenance-required cutover — declare lineage in two orchestrator fixtures

STATUS:    delivered. NOT blocked: `renquant-model#226`, which this work depended
           on, merged 2026-08-17 14:26 PDT — before this PR's current head
           `1716270c` (2026-08-17 14:39 PDT). CI is green on that head. Two
           fixtures, no live path touched, nothing deployed.

WHAT:      Two changes, both adding a lineage declaration that the 2026-08-15
           cutover made mandatory.

           1. `src/renquant_orchestrator/contract_fixture.py` — the trainer's
              returned artifact gains `"provenance": {"kind": "none"}`.
              Note this is `src/`, not `tests/`: the fixture is a shipped
              module. Its `promotion_status` was ALREADY `"candidate"`, so
              unlike the sister repos there is no false `"prod"` claim to drop
              here; the manifest was simply silent about lineage, and silence
              stopped counting as an answer.

           2. `tests/test_daily_run_pipeline.py` — the `_trainer` stub gains the
              same declaration. This one was MISSED in the first pass (see
              "the miss" below).

           `kind="none"` is the accurate determination for stubs that train
           nothing real, and it is admissible precisely because neither claims
           `promotion_status="prod"`.

WHY/DIR:   `renquant-artifacts` sets `PROVENANCE_REQUIRED_AFTER = date(2026,8,15)`;
           `provenance_required()` returns True unconditionally on/after that
           date (one-way, no env override).

THE TWO-REPO DEPENDENCY (resolved, recorded because it shaped the work):
           Adding the key to fixture 1 alone did NOT fix it — still 20 failed.
           The manifest reaching the validator is REBUILT one layer down by
           `renquant_model_gbdt.pipelines.BuildArtifactManifestTask` from the
           enumerated `_RUNTIME_ARTIFACT_FIELDS` allow-list, which did not carry
           `provenance`, so the declaration was stripped between here and the
           guard. That was the real defect; fixed in renquant-model#226, MERGED.

THE MISS (recorded because the failure mode is reusable):
           After #226 landed, CI still showed 4 failures in
           `tests/test_daily_run_pipeline.py` as `AssertionError: Regex pattern
           did not match`. I had classified those 4 as "pre-existing, unrelated
           to provenance" from their assertion type without opening one. They
           were the SAME cause: the tests assert a specific error via a `match=`
           regex, and the provenance `ValueError` had DISPLACED the expected
           error. #226 makes assembly CARRY a trainer's determination; it does
           not invent one, so a stub declaring nothing is still rejected — the
           "necessary but not sufficient" property #226 states about itself,
           landing in this repo. A failing `match=` is evidence that something
           else was raised; it is never on its own evidence of an unrelated
           cause.

EVIDENCE:
  artifact:       src/renquant_orchestrator/contract_fixture.py (one key),
                  tests/test_daily_run_pipeline.py (one key)
  prod or exp:    neither. `contract_fixture` is a deterministic smoke fixture,
                  dispatchable via the job runner but NOT scheduled — it appears
                  in no launchd plist and is absent from
                  `ops/launchd_manifest.json` (verified). No live path touched.
  existing data:  main's last CI run before the cutover is 2026-08-14, so its
                  "green" predates the rule and is not evidence of health.
                  Measured locally on a clean origin/main sibling worktree
                  instead.
  best-known?:    yes. Validator behaviour measured directly, not inferred:
                    kind=none      + prod       -> REJECT
                    kind=none      + candidate  -> PASS
                    kind=canonical + prod       -> REJECT (missing
                                                   publication_record_digest,
                                                   registry bindings)
                    kind=canonical + candidate  -> PASS
  scope:          this repo's two fixtures. The same cutover independently broke
                  renquant-pipeline (#288, 28 tests — MERGED),
                  renquant-backtesting (#113, 2 tests — MERGED) and
                  renquant-model (#226, src defect + 5 fixtures — MERGED).
                  renquant-artifacts is green (345 passed): it owns the guard
                  and its tests were written against it.

VERIFICATION:
  Run from a SIBLING worktree — `[tool.pytest.ini_options] pythonpath` uses
  `../renquant-*/src`, so a worktree outside `git/github/` fails with unrelated
  ModuleNotFoundErrors that have nothing to do with the change under test.

  Local `renquant-model` verified at `origin/main` (0 commits behind), i.e.
  carrying #226, so the reproduction is faithful to CI.

  fixture 1 only, before #226:          20 failed   <- the strip, proven
  fixture 1, with #226:                 tests/test_contract_fixture.py 26 passed
  fixture 2, with #226:                 tests/test_daily_run_pipeline.py
                                          4 failed -> 6 passed, 1 skipped
  full suite (fixed siblings):          9 failed, 6288 passed, 2 skipped
                                          (down from 29 failed, 6268 passed)

  Of the 9: 2 are an artifact of the local verification itself
  (`test_goal3_public_export_resolution.py` detects that `pythonpath` was
  repointed at a substituted worktree — 11 passed with default siblings), and
  the remaining 3 (`test_goal7_arm_a_producer.py`,
  `test_goal7_arm_b_accrual_probe.py`, `test_position_cap_conformance.py`) are
  local-only live-state conformance tests with ZERO provenance hits — they
  compare records against this machine's live book/ledger/checkout and pass in
  CI, confirmed by the CI run reporting only the daily_run_pipeline 4.

NEXT:      none in this repo for the cutover. The open item is upstream and
           carried in renquant-model#226: no trainer declares any provenance
           (measured: zero occurrences in `renquant-model/src` before #226), so
           the first real retrain that reaches manifest assembly is still
           rejected. Choosing what a real model declares is a governance call
           for the promotion-guard owner. It is latent today — the live chain
           fails earlier at the orch#799 blend-vs-xgb reference rule.
