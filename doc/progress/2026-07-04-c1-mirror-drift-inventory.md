# C1 mirror-drift inventory + CI freeze-line

Date: 2026-07-04
Campaign: Group C (mirror-drift governance)
Status: DELIVERED

## What

Built the baseline inventory comparing the pipeline kernel (189 files, the
authority) against the umbrella kernel (217 files, the compatibility mirror):

- 63 identical, 32 trivial drift (import-path only), 73 material drift
- 49 umbrella-only (42 LIFT, 7 RETIRE), 21 pipeline-only (native)

Delivered:
1. `scripts/mirror_drift_inventory.py` — generates the inventory (table or JSON)
2. `scripts/check_mirror_drift.py` — CI freeze-line check (report-only now, `--strict` ready)
3. `data/c1_drift_baseline.json` — committed baseline snapshot
4. `doc/design/2026-07-04-c1-mirror-drift-inventory.md` — full file-by-file disposition table
5. 16 tests covering both scripts

## Relation to campaign

This is the foundation for Group C. The freeze-line prevents new drift while
the 73 material-drift files are reconciled in batches. The campaign decision
("pipeline = single authority") is codified in the tooling.

## Round 2 (codex review)

Two real issues, both fixed — counts unchanged (still 73/168 material/shared):

1. **Strict-mode over-broad new-file check**: `check_mirror_drift.py`'s
   `new_files` computation previously flagged ANY file new relative to the
   baseline, including legitimate `pipeline_only` additions — since pipeline
   is the sole kernel/ authority, new pipeline-only files are normal
   evolution, not mirror drift, and must never trip the freeze-line.
   Narrowed the check to only the mirror-eligible categories (files shared
   between both trees, and `umbrella_only` files — the umbrella mirror is
   meant to be frozen, so a brand-new umbrella-only file is itself
   suspicious and correctly still fails strict mode). Verified with a
   synthetic test: a new pipeline-only file → exit 0; a new umbrella-only
   file, and a genuine drift on an existing shared file → exit 1.
   `tests/test_mirror_drift_inventory.py::test_new_file_detected` was
   locking in the exact buggy behavior (asserting a new pipeline-only file
   should fail strict mode) — replaced with
   `test_new_pipeline_only_file_is_not_drift` /
   `test_new_umbrella_only_file_is_flagged` covering both corrected cases.
2. **Hard-coded machine-specific absolute paths**: `PIPELINE_DEFAULT` /
   `UMBRELLA_DEFAULT` in `mirror_drift_inventory.py` were hard-coded to one
   operator's home directory. Replaced with a derivation from `__file__`
   assuming the established sibling-repo layout (per `RENQUANT_REPOS.md`:
   every subrepo checked out as a sibling of this repo under a common
   parent directory) — verified the derivation resolves correctly against
   the actual canonical checkout locations. `check_mirror_drift.py`'s own
   `BASELINE_DEFAULT` was already `__file__`-derived and needed no change.

1908/1908 tests pass (17 in this module, +1 net from the split test).
