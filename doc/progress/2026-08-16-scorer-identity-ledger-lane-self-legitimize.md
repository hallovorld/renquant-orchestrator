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

REVIEW FIX (codex #983, 2026-08-16): the shortcut also blessed a lineup MEMBERSHIP
           change (a lane `added`/`retired`) as an in-place refit — a lane joining the
           lineup with a valid in-window ledger returned `explained=True` and downgraded
           to `warn`, silencing exactly the CRITICAL event the monitor exists for. Fixed:
           `_ledger_append_explains` now returns early `(False, None)` unless
           `change.lifecycle is None` (an in-place same-lane file-sha swap). Only an
           existing lane's scheduled refit self-legitimizes; added/retired stay CRITICAL.
           Regression coverage added (2 tests): an evaluate-level ledger-backed `added`
           lane stays CRITICAL, and `_ledger_append_explains` refuses both `added` and
           `retired` even with a valid in-window ledger (the lifecycle gate, not a missing
           file, is what blocks it — both fail with the gate removed).

REVIEW FIX 2 (codex #983 round-2, 2026-08-16): `_ledger_append_explains` legitimized from
           the LIVE on-disk ledger without proving it was the bytes the `curr` run actually
           stamped. If the ledger ADVANCED after the run (a later append), a genuine
           unexplained change could be downgraded because that later in-window append still
           looked link-intact. Fixed: read the ledger bytes once, hash them, and require the
           on-disk file sha to equal `change.curr.artifact_sha` (via the prefix-tolerant
           `_digest_matches`) before reading any legitimizing append -- else fail closed
           `(False, None)`. Regression coverage added (1 test):
           `test_ledger_advanced_after_run_fails_closed` -- curr stamps a sha that no longer
           matches the advanced on-disk ledger, so it stays CRITICAL (fails with the bind
           removed).

REVIEW FIX 3 (codex #983 round-3, 2026-08-16): binding only the CURR side still let a
           full-file REPLACEMENT at the same path masquerade as a scheduled append — set
           `curr.artifact_sha` to the (replaced) on-disk bytes and `prev.artifact_sha` to any
           unrelated digest and the change downgraded to `warn`, even though the current
           ledger need not EXTEND the previously stamped revision. Fixed: bind the PREV side
           too. New helper `_ledger_extends_prev(raw, prev_sha)` requires the sha the prev run
           stamped to be a byte-PREFIX of the current append-only file — provable because the
           writer only ever opens the ledger in append mode and never rewrites existing bytes
           (`renquant_model_momentum.ledger.append_chained_row`), so a prior revision is an
           exact byte-prefix of a later one. No prefix matches ⇒ ancestry unproven ⇒ fail
           closed `(False, None)`. Regression coverage added (2 tests):
           `test_ledger_full_file_replacement_at_same_path_still_fires` (the reviewer's exact
           repro — curr-bound + link-intact + in-window but prev is no prefix → stays CRITICAL)
           and `test_ledger_extends_prev_distinguishes_append_from_replacement` (the helper
           accepts a genuine prefix, refuses unrelated/None/absent/full-file digests).

EVIDENCE:
  artifact:      `scorer_identity_monitor.py` (2 helpers + explain_boundary step) +
                 `tests/test_scorer_identity_monitor.py` (9 new tests) + this doc.
  prod or exp:   neither — monitor logic + unit tests; no live/production write. The
                 monitor is observe-only (opens the DB read-only).
  existing data: [VERIFIED] the run bundle stamps the momentum lane path ABSOLUTE
                 (`/Users/renhao/git/github/RenQuant/backtesting/renquant_104/artifacts/
                 momentum/momentum_artifact_ledger.jsonl`) → no path-resolution ambiguity;
                 the ledger is link-chained (`prev_row_sha`/`row_sha`) with
                 `appended_at_utc`; the 08-08 12:00 UTC append (Sat weekly job) is what
                 flipped the file sha 9aa2d8c9→65d09112 inside the 08-07→08-10 boundary.
  best-known?:   yes — GUARD PRESERVED and tested: a file SWAP breaks linkage → still
                 CRITICAL; a change with no in-window append → still CRITICAL; a ledger that
                 ADVANCED past the stamped `curr` sha → still CRITICAL (fails closed, review
                 fix 2); a full-file REPLACEMENT at the same path (prev is no byte-prefix of
                 curr) → still CRITICAL (fails closed, review fix 3); the genuine-same-lane-
                 substitution guard test still passes; only `_ledger.jsonl` lanes are eligible
                 (prod/calibrator/clf untouched). 47 pre-existing tests pass unchanged.
                 Binding is now at BOTH ends of the transition: curr = the stamped on-disk
                 bytes, and prev = a byte-prefix of that same append-only file. Because the
                 writer only ever appends (never rewrites existing bytes), a prefix match IS a
                 cryptographic proof that the current ledger EXTENDS the previously stamped
                 revision — the B-extends-A ancestry the round-3 review asked for, provable
                 from the file sha the prev run already stamps (no upstream tail-row change
                 required). A tail `row_sha` stamp upstream would remain a redundant belt-and-
                 suspenders, no longer load-bearing.
  scope:         "legitimizes a scheduled append-only-ledger refit on a shadow (never-
                 submit) lane so it stops false-alarming, WITHOUT weakening the silent-
                 swap guard for any lane. Touches no production, no order path, no
                 threshold. Source-repo; operator-gated deploy to -run brings it live."

TESTS:     `pytest tests/test_scorer_identity_monitor.py` → 56 passed [VERIFIED — pytest,
           this session] (47 pre-existing + 9 new: refit legitimized, broken-linkage still
           fires, out-of-window still fires, non-ledger lane ineligible, ledger-backed
           `added` stays CRITICAL, `_ledger_append_explains` refuses `added`/`retired`
           lineup changes, ledger-advanced-after-run fails closed → CRITICAL, same-path
           full-file replacement fails closed → CRITICAL, ancestry helper accepts a prefix /
           refuses unrelated·None·absent·full-file digests).

NEXT:      codex review → merge → -run sync (operator-gated) → the Saturday false CRITICAL
           stops while a genuine swap (added/retired lane, broken linkage, out-of-window,
           advanced-past-stamp, or same-path replacement) still fires. Ancestry is now proven
           from the prev run's already-stamped file sha; the upstream tail-row stamp is
           optional redundancy, not a prerequisite.
