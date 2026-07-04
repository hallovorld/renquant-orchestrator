# D-group hardcoded paths round 2

STATUS: ready
WHAT: replace remaining hardcoded `Path.home() / "git/github/RenQuant"` paths with
`default_data_root()` in transfer_coefficient.py, decision_pnl_attribution.py, and
attribution/ledger.py. These were missed in the first D-group PR #307.
WHY/DIR: campaign D hygiene (compliance audit #296 OR-9) — CI portability + no
hard-coded paths to the operator's machine layout.
EVIDENCE: `make test` 1902 passed, 2 skipped.
NEXT: merge after CI green.
