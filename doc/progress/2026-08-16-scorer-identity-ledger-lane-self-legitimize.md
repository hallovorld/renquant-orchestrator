# scorer-identity: ledger-backed shadow lanes self-legitimize a scheduled refit

STATUS:    fix — stops the standing false CRITICAL the rq104-scorer-identity monitor
           fires every Saturday on the momentum shadow lanes. Source-repo,
           shadow-lane-only, guard-preserving. Operator-directed ("解决所有问题").

WHAT:      `src/renquant_orchestrator/scorer_identity_monitor.py`: new helper
           `_ledger_append_explains(change, boundary)` + a step in `explain_boundary`.
           For a shadow lane whose `artifact_path` ends `_ledger.jsonl`, a detected
           identity change is legitimized iff the on-disk ledger is LINK-INTACT (each
           row's `prev_row_sha` chains from the prior `row_sha`) AND a row was appended
           within the boundary window (`appended_at_utc` between the two runs'
           `created_at`). The ledger IS the promote record for these never-submit lanes.

WHY/DIR:   The momentum/momentum_fast shadow lanes are append-only ledgers; their stamped
           identity is the ledger FILE sha, which flips on EVERY scheduled weekly refit
           append (Sat `momentum-train-weekly`) even though nothing was silently swapped.
           They carry no promotion receipt (scheduled, not promoted), and even a receipt
           couldn't match (it records the model content-sha, the monitor diffs the
           file-sha). Result: a false CRITICAL every Saturday (fired 08-15; would recur
           08-22…). The PRODUCTION scorer never changed (forensic: panel 6461b827,
           calibrator bce257d19a3d, trained 2026-08-02 byte-identical 08-07/10/14).

EVIDENCE:
  artifact:      `scorer_identity_monitor.py` (helper + explain_boundary step) +
                 `tests/test_scorer_identity_monitor.py` (4 new tests) + this doc.
  prod or exp:   neither — monitor logic + unit tests; no live/production write. The
                 monitor is observe-only (opens the DB read-only).
  existing data: [VERIFIED] the run bundle stamps the momentum lane path ABSOLUTE
                 (`/Users/renhao/git/github/RenQuant/backtesting/renquant_104/artifacts/
                 momentum/momentum_artifact_ledger.jsonl`) → no path-resolution ambiguity;
                 the ledger is link-chained (`prev_row_sha`/`row_sha`) with
                 `appended_at_utc`; the 08-08 12:00 UTC append (Sat weekly job) is what
                 flipped the file sha 9aa2d8c9→65d09112 inside the 08-07→08-10 boundary.
  best-known?:   yes — GUARD PRESERVED and tested: a file SWAP breaks linkage → still
                 CRITICAL; a change with no in-window append → still CRITICAL; the
                 genuine-same-lane-substitution guard test still passes; only
                 `_ledger.jsonl` lanes are eligible (prod/calibrator/clf untouched). 47
                 pre-existing tests pass unchanged. Honest limitation (in the docstring):
                 this proves "a valid scheduled append happened in-window", not a
                 cryptographic B-extends-A binding — the prev run stamps only the file
                 sha, not the tail `row_sha`; sufficient for never-submit shadow lanes, a
                 stronger binding would stamp the tail row_sha upstream.
  scope:         "legitimizes a scheduled append-only-ledger refit on a shadow (never-
                 submit) lane so it stops false-alarming, WITHOUT weakening the silent-
                 swap guard for any lane. Touches no production, no order path, no
                 threshold. Source-repo; operator-gated deploy to -run brings it live."

TESTS:     `pytest tests/test_scorer_identity_monitor.py` → 51 passed (47 pre-existing +
           4 new: refit legitimized, broken-linkage still fires, out-of-window still
           fires, non-ledger lane ineligible).

NEXT:      codex review → merge → -run sync (operator-gated) → the Saturday false CRITICAL
           stops while a genuine swap still fires. Deferred (optional hardening): stamp the
           ledger tail row_sha in the run bundle for a cryptographic B-extends-A binding.
