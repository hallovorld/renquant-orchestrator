# Pre-deploy model bundle consistency checker

STATUS: ready
WHAT: commit the untracked `scripts/check_model_bundle_consistency.py` + tests.
Runs all four consistency contracts offline before deploy: config fingerprint,
watchlist parity, calibrator/scorer fingerprint binding, WF-gate metadata.
WHY/DIR: the 2026-06-23 XGB deploy hit all four contracts one-by-one IN PRODUCTION,
each hand-patched. This script catches them all before the deploy happens.
Fixes the hardcoded DEFAULT_REPO path to use `default_data_root()`.
EVIDENCE: 7 unit tests (all four failure modes + consistent happy path).
NEXT: merge; wire into pre-deploy CI or promote workflow.
