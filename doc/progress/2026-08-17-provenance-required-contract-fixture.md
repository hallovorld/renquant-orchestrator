# Provenance-required cutover — declare lineage in the contract fixture

STATUS:    delivered, BLOCKED ON renquant-model#226 for CI-green (see NEXT).
           One key added to a smoke fixture. No live path touched, nothing
           deployed. `daily_contract_fixture` is a job-runner-dispatchable smoke
           fixture, NOT a scheduled job — verified: it appears in no launchd
           plist and is absent from `ops/launchd_manifest.json`.

WHAT:      `src/renquant_orchestrator/contract_fixture.py`, the trainer's
           returned artifact: `+ "provenance": {"kind": "none"}`.

           Note this is `src/`, not `tests/` — the fixture is a shipped module.
           Its `promotion_status` was ALREADY `"candidate"`, so unlike the sister
           repos there is no false `"prod"` claim to drop here; the manifest was
           simply silent about lineage, and silence stopped counting as an
           answer on 2026-08-15.

WHY/DIR:   `renquant-artifacts` sets `PROVENANCE_REQUIRED_AFTER = date(2026,8,15)`;
           `provenance_required()` returns True unconditionally on/after that
           date (one-way, no env override). This smoke fixture trains nothing
           real, so `kind="none"` is the accurate determination for it, and it is
           admissible precisely because the manifest does not claim
           `promotion_status="prod"`.

EVIDENCE:
  artifact:       src/renquant_orchestrator/contract_fixture.py (one key)
  prod or exp:    neither — deterministic smoke fixture; not scheduled, not live
  existing data:  main's last CI run is 2026-08-14, before the cutover date.
                  Measured locally on a clean origin/main sibling worktree:
                  tests/test_contract_fixture.py 20 failed, all one cause.
  best-known?:    yes, and the first attempt was WRONG in an instructive way.
                  Adding the key to the fixture alone did NOT fix it — still
                  20 failed. The manifest that reaches the validator is REBUILT
                  one layer down by
                  `renquant_model_gbdt.pipelines.BuildArtifactManifestTask` from
                  the enumerated `_RUNTIME_ARTIFACT_FIELDS` allow-list, which did
                  not carry `provenance`, so the fixture's declaration was
                  stripped between here and the guard. That is the real defect
                  and it is fixed in renquant-model#226; this repo's change is
                  only the other half.
  scope:          this repo's fixture. The same cutover independently breaks
                  renquant-pipeline (#288, 28 tests), renquant-backtesting
                  (#113, 2 tests) and renquant-model (#226, src defect + 5
                  fixtures). renquant-artifacts is green (345 passed) — it owns
                  the guard and its own tests were written against it.

VERIFICATION:
  Run from a SIBLING worktree — `[tool.pytest.ini_options] pythonpath` uses
  `../renquant-*/src`, so a worktree outside `git/github/` fails with unrelated
  ModuleNotFoundErrors that have nothing to do with the change under test.

  Because the fix spans two repos, local verification overrides the sibling
  paths to point at the fixed worktrees:
  `-o pythonpath=$'src\n../renquant-model-wt-prov/src\n...'` (newline-separated;
  pytest parses this ini key as a linelist, so a comma-separated value is taken
  as ONE path and every import collapses).

  pre-fix  (clean origin/main):        tests/test_contract_fixture.py  20 failed
  fixture key added, model unfixed:    20 failed   <- the strip, proven
  fixture key + renquant-model#226:    26 passed

NEXT:      renquant-model#226 must merge FIRST. This repo's CI checks out
           `hallovorld/renquant-model` with no `ref:` (floating to main), so once
           #226 lands this PR goes green with no further change here. Merging in
           the other order leaves this red for a reason that is not in its diff.
