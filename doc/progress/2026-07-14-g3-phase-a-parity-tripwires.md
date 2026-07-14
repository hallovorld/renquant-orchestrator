# 2026-07-14 — G3 Phase A: cross-repo parity tripwires

STATUS: ready for review
WHAT: Read-only parity tests that detect constant/contract drift across
      sibling repos, per the G3 refactoring plan Phase A.
WHY: Every Phase B single-source consolidation needs a tripwire that
     fires when the duplicated code drifts. These tests are that tripwire.

## Changes

### A2: duplicated constants parity (4 tests)

| Contract | Pipeline source | Execution source | Status |
|----------|----------------|-----------------|--------|
| `MIN_FRACTIONAL_NOTIONAL_USD` | `kernel.sizing:187` | `broker:73` | EQUAL (1.0) |
| `compute_parent_intent_id` | `intraday_decisioning:103` | `order_state_machine:179` | EQUAL (3 golden vectors) |

Tests verify value equality and signature parity. The functions differ
only in docstrings — logic is byte-identical.

### A3: calendar implementation inventory (2 tests)

Found 7 raw `pandas_market_calendars` imports in pipeline kernel that
should use `renquant_common.market_calendar`:

| File | Line |
|------|------|
| `__init__.py` | 9 |
| `data.py` | 64 |
| `execution/t2_settlement.py` | 28 |
| `exits.py` | 70, 126 |
| `pipeline/task_data_freshness.py` | 225 |
| `typed_past/typed_data_freshness.py` | 95 |

Test reports these via warning and sets an upper-bound baseline of 7.
New non-canonical imports will fail the test. Phase B calendar
consolidation (B2) should migrate these to the common canonical import.

## Risk assessment

ZERO risk — all tests are read-only assertions with no code changes.
Tests skip gracefully if sibling repos are not importable.

## Test results

- 6 new tests, all passing
- 3910 total passing (8 pre-existing failures in `test_native_context_hydration.py`,
  unrelated to this change — present on main)

## Files

- `tests/test_cross_repo_parity.py` (new)
- `doc/progress/2026-07-14-g3-phase-a-parity-tripwires.md` (this file)
