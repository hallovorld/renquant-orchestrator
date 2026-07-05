# Lazy-import runtime_paths in bundle consistency checker

Date: 2026-07-05
Task: fix test failure in scripts/check_model_bundle_consistency.py

## What shipped

- `scripts/check_model_bundle_consistency.py`: moved the module-level import
  of `renquant_orchestrator.runtime_paths` into a lazy `_default_repo()`
  helper called only from `main()`. `check_bundle()` never needed it; the
  CLI test shim runs the script as a subprocess without the package on
  `sys.path`, so the eager import raised `ModuleNotFoundError` before any
  test logic ran.
- `--repo` now defaults to `None` and resolves via `_default_repo()` inside
  `main()` only when the flag is omitted.

## Round 2 (codex review)

STATUS: fixed
WHAT: two gates were red — the required progress-doc check (this file was
missing) and the branch was behind main.
WHY-DIR: codex correctly declined to merge on a green unit diff alone while
policy-required gates were unsatisfied.
EVIDENCE: merged `origin/main` cleanly (no conflicts); added this progress
doc. Full suite passes locally after the merge (see commit history for the
underlying fix's own verification).
NEXT: none.
