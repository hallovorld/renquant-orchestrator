# PR #333 Codex review fixes (v2)

DATE: 2026-07-04
PR: #335 (feat/104-105-code-completion-v2, supersedes #333)

## What

Addressed two substantive Codex review findings on PR #333:

### 1. §9.4 economic-authorization gate (safety)

The session runner had a live-execution path reachable whenever the quintuple
gate armed and a port_factory was present. The docs claimed "shadow-only until
§9.4" but the code did not enforce this.

FIX: Added an explicit `_check_section_9_4()` method that requires a
`section_9_4_economic_authorization.json` file with `authorized: true` and a
`prereg_id` field. Without this file, the runner ALWAYS falls back to shadow
even when the quintuple gate arms. This is a SEPARATE gate from the §9.3a
arming gate. Updated the module docstring to accurately describe the two-gate
safety model.

4 new tests covering: armed-without-§9.4 → shadow, authorized=false → reject,
missing prereg_id → reject, valid file → pass.

### 2. S10 memo evidence downgrade (methodology)

Codex correctly identified that the S10 IS memo carried conclusions too strong
for the data quality:
- 30/67 trades unmatched (weekend run_dates)
- Post-hoc outlier exclusion (HON |IS| > 1000bps)
- Heuristic deduplication

FIX: Downgraded all claims from definitive to EXPLORATORY. Added a mandatory
"Data quality caveats" section listing the three instability points. Updated
the 105 as-built doc to reference "EXPLORATORY" instead of "NOT CONFIRMED".

### 3. outcome_backfiller provenance (documentation)

Added a prominent "RECONSTRUCTED SUBSTRATE" warning to the module docstring
clarifying that gate verdicts are inferred from blocked_by annotations, not
recorded from live ledger events.

## Round 2: S10 sensitivity analysis ported from a parallel fix attempt

The original §2 fix above (downgrading claims to EXPLORATORY) hedged the
language but did not actually address the methodology instabilities Codex
named. A separate, parallel fix attempt on the closed PR #333 (branch
`feat/104-105-code-completion`, commit `f2e69427`) went further: it added
real `--weekend-remap` and `--exclude-outlier-bps` CLI parameters to
`scripts/s10_open_auction_is.py` and ran an actual 4-way sensitivity sweep
against `runs.alpaca.db`, rather than just hedging the existing single-cut
(n=36) numbers.

That work has been ported into this branch, since it represents completed
analysis rather than qualified language around the same analysis:

- `scripts/s10_open_auction_is.py`: added `remap_weekend_run_dates()` and
  `apply_outlier_exclusion()`, wired to new `--weekend-remap` /
  `--exclude-outlier-bps` CLI flags. File confirmed byte-identical to the
  parallel attempt's version after the port.
- `tests/test_s10_open_auction_is.py` (new): 9 tests for the two new
  functions, ported directly.
- `doc/research/2026-07-04-open-auction-is-measurement.md`: replaced with
  the sensitivity-sweep version — reports all 4 configurations (raw,
  exclusion-only, remap-only, both), confirms the round-1 memo's numbers
  are reproduced exactly at one config point, and surfaces a SECOND
  HON-like split-artifact trade (`HON@2026-05-15`) that the original
  weekend-unmatched bucket was silently dropping.
- `doc/design/renquant-105-as-built.md`: Purpose and Current Status
  sections updated to cite the sensitivity-checked finding instead of the
  single-cut EXPLORATORY framing. PR references corrected from the closed
  #333 to #335.

Re-ran the ported CLI against the real `runs.alpaca.db` backup
(`~/.renquant-state-backup/data/runs.alpaca.db`) with both flags and
reproduced the parallel attempt's exact reported numbers for the fullest
configuration (n=65): vs-open -7.8bps [-50.8,+37.8], vs-VWAP -32.6bps
[-74.3,+7.3], dollar-weighted -74.9bps — confirming the port is correct
and the original analysis is reproducible.

The §9.4 gate (`section_9_4_economic_authorization.json`) and
`outcome_backfiller` provenance fixes above are unchanged by this port.

## Tests

2211/2213 relevant tests pass (2 pre-existing, unrelated failures in
`test_bundle_consistency_ci_gate.py` reproduce identically on clean
`origin/main`).
