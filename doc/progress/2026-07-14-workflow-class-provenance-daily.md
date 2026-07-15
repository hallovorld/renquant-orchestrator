# Daily GBDT Training Declares workflow_class=canonical (F-7 Coordination)

STATUS: blocked-on-upstream — do not merge until renquant-model#55 merges
AND the `renquant-model` pin is bumped past it, in that order.

WHAT: `daily.py::TrainGbdtArtifactTask.run()` — the real daily production
GBDT training entrypoint — now constructs `renquant_model_gbdt.TrainingContext`
with an explicit `workflow_class=WORKFLOW_CLASS_CANONICAL` kwarg. The same
kwarg was added to the 5 test fixtures in `tests/test_daily.py` that build a
`TrainingContext` directly to seed `ctx.training_context` for downstream task
tests (`RunRuntimeInferenceTask`, `RunBacktestCheckTask`,
`PersistDailyRunBundleTask`). One new test,
`TestTrainGbdtArtifactTask.test_declares_canonical_workflow_class`, stubs
`TrainingContext` to assert the exact kwarg `TrainGbdtArtifactTask` passes,
independent of whichever `TrainingContext` signature happens to be pinned.

WHY/DIR: renquant-model PR #55 (branch `fix/f7-provenance-none`, open, not yet
merged) makes `workflow_class` a required constructor argument with no default
on both `TrainingContext` and `PatchTstTrainingContext` (F-7 round 4 —
Codex review: a producer self-classifying an experiment artifact as `none`
is precisely the bypass the provenance gate must prevent). That branch's own
`renquant_model_common/workflow_provenance.py` docstring explicitly names
this repo's `daily.py::TrainGbdtArtifactTask` as the one known external call
site not yet updated, and states it "will raise `TypeError` ... until that
repo is updated in a coordinated follow-up PR" — this PR is that follow-up.
Confirmed directly against the `#55` branch (cloned, not guessed):
`WORKFLOW_CLASS_CANONICAL = "canonical"` /
`WORKFLOW_CLASS_EXPERIMENT = "experiment"`, re-exported from both
`renquant_model_gbdt` and `renquant_model_patchtst` for caller convenience.
`daily.py`'s call IS the canonical daily production path, so it must declare
`WORKFLOW_CLASS_CANONICAL`, never `"experiment"`. Repo-wide grep found no
other direct constructor of either dataclass in `renquant-orchestrator`:
`train_gbdt.py` uses an unrelated `GbdtTrainingContext` (no `workflow_class`
field), and the two orchestrator entrypoints that touch PatchTST
(`retrain_patchtst.py`, `build_patchtst_wf_manifest.py`) subprocess into
`renquant_model_patchtst.hf_trainer` / `fit_calibrator` rather than
constructing `PatchTstTrainingContext` directly — that call site lives inside
`renquant-model` itself and is #55's own responsibility to fix, not
orchestrator's.

Sequencing: the currently pinned `renquant-model` (main, and the local
sibling checkout used by `make test`) does NOT export `WORKFLOW_CLASS_CANONICAL`
from `renquant_model_gbdt` yet, so this PR's added import
(`from renquant_model_gbdt import WORKFLOW_CLASS_CANONICAL, ...`) raises
`ImportError` against the current pin — before the `workflow_class` kwarg
itself is ever evaluated. This is expected, not a regression to silently
absorb. Confirmed exact blast radius via full-suite diff (current pin, fix
applied vs. `origin/main` baseline, all other suite noise held identical):
exactly 5 new failures, all one root cause — `tests/test_daily.py` (collection
error), `tests/test_daily_run_pipeline.py` (collection error),
`tests/test_contract_fixture.py` (collection error, imports `daily`
transitively), `tests/test_cli.py::test_daily_contract_cli_writes_run_bundle`,
`tests/test_cli.py::test_daily_contract_cli_execute_uses_paper_fill`. No other
test in the suite regresses. CI's "Full multirepo test" job checks out
`renquant-model` at its default branch (main) with no pin override, so this
PR's own CI is expected to go red on exactly these 5 items until
renquant-model#55 merges and this repo's pin is bumped — do not merge before
then, and do not chase this specific CI red as a bug in this PR.

EVIDENCE: cloned `hallovorld/renquant-model@fix/f7-provenance-none` directly
(not guessed) to read the real signatures and constant names. Ran the full
`renquant-orchestrator` suite against the currently pinned `renquant-model`
sibling checkout both before and after this change (`pytest -q
--continue-on-collection-errors`) and diffed the FAILED/ERROR line sets —
delta is exactly the 5 items above, nothing else moved. Separately, ran
`daily.py`'s real `TrainGbdtArtifactTask.run()` end-to-end against the real,
cloned `#55` branch content (not a stub) with `TrainingContext` construction
unmocked: confirmed the real dataclass raises
`TypeError: __init__() missing 1 required positional argument: 'workflow_class'`
without the kwarg, and that with this fix applied the constructed
`TrainingContext.workflow_class` reads back as `"canonical"` end-to-end. Also
confirmed the full `tests/test_daily.py` + `tests/test_daily_run_pipeline.py`
+ `tests/test_contract_fixture.py` + `tests/test_cli.py` suites (124 tests)
pass cleanly when pointed at the `#55` branch content in place of the current
pin, i.e. this fix is correct and the suite is green once the pin bump lands.

NEXT: after renquant-model#55 merges, bump this repo's `renquant-model` pin
past it (separate PR, out of scope here), then land this PR (or rebase/merge
it) in the same coordinated wave. Re-run `make test` post-pin-bump to confirm
the 5 items above go green and nothing else regresses. No pin-bump attempted
in this PR by design.
