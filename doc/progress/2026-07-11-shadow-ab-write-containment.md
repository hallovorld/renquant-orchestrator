# 2026-07-11 — shadow-ab write containment (self-poisoning fix)

## Incident

The first VALID §2a pair (02:15 PT) itself poisoned the next session: the
kernel's `AdmissionShadowLoggerTask` defaults its JSONL to
`config["_strategy_dir"]/logs/` — on the arm path that is the
MANIFEST-PINNED strategy checkout. The 04:5x sanity kickstart (run
deliberately after amending the manifest's base-data pin) precheck-aborted:

```
run manifest verification failed: renquant-strategy-104: working tree DIRTY (1 path(s), e.g. '?? logs/')
```

Session N's arms dirty the tree AFTER session N's own verification passed →
session N+1 fails closed. Stray `logs/admission_shadow.jsonl` (58k, 02:00
timestamp) archived to the experiment root
(`archive/strayed-arm-logs-*/`) as evidence; tree restored clean for today's
14:35 PT counted session (arms only dirty post-verify, so today is safe
even without this PR deployed).

## Fix

1. **Containment**: the runner threads `--log-containment-dir <arm_dir>`
   into each arm's inference step; hydration redirects every known
   strategy-dir-relative kernel writer in-memory (`admission_shadow.path`,
   `sleeve.log_path` when present) to the arm's own directory. Same
   identity-safety argument as the #464 artifact rewrite: config sha is
   frozen from raw file bytes; these keys are not in the P-CONFIG-FP
   projection. Arm configs untouched (no VOID).
2. **Self-healing backstop**: post-arms, the runner re-scans every manifest
   repo; an untracked `logs/` (the known byproduct pattern) is QUARANTINED
   into the session dir with a bundle warning (evidence preserved, next
   session unblocked); anything else dirty is reported and left in place —
   the next precheck fails closed on it, by design.

## Evidence

- 2 new tests (arm commands carry the containment dir pointing at the arm
  dir; quarantine moves logs/ + preserves evidence + leaves unrelated dirt
  in place with a warning). Affected suites green except the 6 pre-existing
  sandbox-baseline failures (verified identical on origin/main earlier
  tonight).

## 2026-07-11 r1 addendum: retry-safety + hydration-level proof

Codex r1 review: the backstop wasn't retry-safe — `quarantine_stray_arm_
byproducts` always renamed to a FIXED `quarantine_root/{name}-logs`
destination; a retried or repeated same-session quarantine after an
earlier successful move found that destination already present, `rename`
raised, the caller's blanket `except OSError` swallowed it into a single
error note (discarding any other repos' already-recorded notes too), and
`logs/` was left behind in the pinned checkout — poisoning the next
precheck again, the exact failure this PR exists to prevent.

Fixed:

- `_reserve_unique_quarantine_dest`: atomically claims a fresh
  `{name}-logs-{NNNN}` directory via `Path.mkdir(exist_ok=False)` — two
  attempts (or a retry) can never collide on the same destination. The
  reserved directory is held (not released) from claim to population, so
  there is no TOCTOU window; the source `logs/`'s CONTENTS are moved into
  it (not the directory itself renamed onto it) and the empty source is
  then removed.
- Each repo's quarantine attempt is now isolated in its own try/except
  inside `quarantine_stray_arm_byproducts` — one repo's unexpected failure
  no longer discards other repos' already-recorded success notes.
- New append-only bundle record (`quarantine_root/index.jsonl`, one JSON
  line per attempt: repo, status, dest/error, files, timestamp) so N
  repeated attempts in one session are fully auditable, not silently
  overwritten.
- Hydration-level test: extracted the inline containment-rewrite block out
  of `hydrate_pipeline_context` into its own `rewrite_config_log_
  containment` function (mirroring the existing `rewrite_config_artifact_
  refs` pattern for the same identity-safety argument), then added a real
  end-to-end test (`test_hydrate_pipeline_context_threads_log_containment_
  into_admission_shadow_and_sleeve`) that runs the ACTUAL pinned pipeline
  twice — once with containment, once without — on the same payload, and
  asserts every decision/output-relevant field (prices, holdings, cash,
  portfolio_value, today, ohlcv universe) is identical between the two,
  while only the two writer-path keys (`admission_shadow.path`,
  `sleeve.log_path`) differ.

Tests: 3 new/changed (retry-safety, unit-level rewrite-function proof,
hydration-level end-to-end proof) + 1 existing test's fixed-path assertion
updated for the new unique-destination naming. The retry-safety and
extracted-function tests fail against the pre-fix code (ImportError /
OSError respectively) — confirmed meaningful via stash-revert. The
hydration-level test passes against both pre- and post-fix code (the
containment rewrite itself was already correct pre-fix; this test adds the
coverage Codex asked for, it does not catch a regression). Full guardrail
suite: 76 passed / 2 pre-existing Python-3.9-vs-3.10-syntax failures in
`renquant_pipeline/inference.py` (unrelated repo/file, reproduced
identically on the pre-fix commit). Full orchestrator suite: 3486 passed /
8 pre-existing environment failures (missing cvxpy/xgboost in this
worktree, hardcoded sibling paths — reproduced identically on the pre-fix
commit).
