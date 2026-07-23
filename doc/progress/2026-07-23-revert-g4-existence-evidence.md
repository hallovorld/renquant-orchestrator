# Progress - revert misplaced G4 existence-screen artifacts

## STATUS:
Delivered for review.

## WHAT:
Reverts PR #569 in full: the model-specific XGB/PatchTST runners, checkpoints,
result artifacts, G4 existence-screen document, and its progress record are
removed from `renquant-orchestrator`.

## WHY/DIR:
This repository owns pinned-subrepo daily orchestration and shared generic
orchestration primitives. Model research, training artifacts, score evidence,
and experiment decisions belong in `renquant-model`. PR #569 also recorded a
G4 KILL decision without a precommitted protocol, producer-time score
provenance, or a direct paired-ensemble test. This revert restores the
repository boundary without changing the generic `tiered_screen` primitive
merged separately in PR #568.

## EVIDENCE:
- The revert removes only the 12 files introduced by PR #569 plus its prior
  progress document; it leaves the generic tiered-screen implementation intact.
- `make doctor` passes on the corrective branch.
- CI for the original revert PR passed its test and progress-document checks.

## NEXT:
Any future G4 experiment must be proposed in `renquant-model`, using a frozen
protocol, producer-time score admission facts, and the experiment scope needed
for the decision it claims to support.
