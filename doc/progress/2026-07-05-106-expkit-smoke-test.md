# 106 expkit smoke test

Date: 2026-07-05

## What changed

Added `scripts/expkit_smoke_test.py` — exercises the full 106 experiment
framework flow with synthetic data: FrozenSpec → write/load → per_date_ic →
block_bootstrap → multi_seed_unanimity → evidence manifest → verify.

All paths pass. Framework confirmed ready for real WF-gate corpus.

## N2 PIT collector status

Already deployed: `com.renquant.pit-estimate-snapshot` running, 102 snapshots
collected (latest 2026-07-03), weekdays 14:30. No action needed.
