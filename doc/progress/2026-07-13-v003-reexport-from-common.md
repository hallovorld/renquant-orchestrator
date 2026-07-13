# fix(V-003): re-export decision_ledger from common

**Date**: 2026-07-13
**PR**: orchestrator fix/v003-reexport-from-common

## Change

Rewrite `decision_ledger.py` to import persistence primitives (`connect`,
`write_verdicts`, `DDL`, `DEFAULT_DB`, `_VALID_VERDICTS`) from
`renquant_common.decision_ledger` and re-export them for backward
compatibility. Query helper `verdicts_for` stays orchestrator-local.

All 3896 tests pass — zero test changes needed thanks to the re-export.

## Companion PRs

- **common#30**: persistence functions moved to common
- **pipeline#195**: update import to use common
