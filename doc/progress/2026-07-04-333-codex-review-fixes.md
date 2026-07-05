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

## Tests

2205 passed, 2 skipped.
