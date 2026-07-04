# Progress: execution/common/model design-compliance audit (findings memo)

DATE: 2026-07-04 (audit executed 2026-07-03). DOCS ONLY — no code change.

## Deliverable

`doc/arch/2026-07-04-execution-common-model-compliance-audit.md` — one
severity-ranked findings memo covering `renquant-execution`, `renquant-common`,
`renquant-model` (broker / primitives / factory boundaries) plus the cross-repo
dimensions (version caps, import directions, hand-copied impls). Placed in
orchestrator `doc/arch/` because the findings span repos.

## Method

Fresh clones at `origin/main` in an isolated scratchpad (no git operation in any
primary checkout or the live tree; HEAD SHAs recorded in the memo §0). Baseline:
umbrella `subrepo-operating-model.md` (roles + Universal Rules 1-6), each repo's
`CLAUDE.md`/`renquant_repo.yml`, the M6 stage-1/stage-2 fingerprint designs
(post-step-0 state), and the session rules (single-impl, flags OFF, fail-loud
fingerprints). Four parallel audit lanes (execution / common / model factory /
cross-repo); every finding verified at the cited file:line; both P0s and the two
load-bearing P1s independently re-verified.

## Result

**30 findings: 2 P0 · 13 P1 · 15 P2**, each with repo+file:line, rule violated,
one-line fix, and fix owner. Headliners:

- **P0 F1**: a full discretionary IGV short-options strategy (entry signals,
  TP/SL, launchd monitor, live-order capability) lives inside renquant-execution
  — hard breach of the broker-execution-only role (currently disarmed:
  dry-run/paper/`IGV_LIVE_ARMED=0`).
- **P0 F2**: the fail-closed WF-loader fingerprint verifier now exists as THREE
  divergent copies (pipeline = M6-migrated; backtesting fork = 266-line drift
  with 12-char prefix acceptance; umbrella copy = the live `run_wf_gate.py`
  path) — the triple-impl incident class M6 exists to kill, re-created around
  M6's own fix.
- Factory-lane P1 cluster (F8-F11): umbrella is still the live production
  trainer with capability drift (#426 provenance stamping umbrella-only),
  factory artifacts ship with no content fingerprint (Rule 5), and the
  renquant-artifacts registry is bypassed by the entire active path.
- Common P1s (F5-F7): v1 fingerprint classification is top-level-only with one
  global table (stage-1 §2a deviation — gates M6 stage-4), a byte-identical
  `calibrator_quality` hand-copy lives in both common and model, and the API
  snapshot does not pin the `model_fingerprint` submodule surface.

No fixes are made in this PR; every finding names its fix owner, and the memo
§9 gives a suggested remediation order (F2 folds into the M6 stage-2 landing).
