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
