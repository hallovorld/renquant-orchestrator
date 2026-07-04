# Python 3.9 Pydantic + runtime type-alias compatibility fix

DATE: 2026-07-04

## What changed

Two files used Python 3.10+ union syntax (`float | None`,
`Callable[[str], float | None]`) that fails at runtime on the system
Python 3.9.6:

1. `live_state_v2.py`: Pydantic v2 model fields — Pydantic evaluates
   type hints at runtime regardless of `from __future__ import
   annotations`. Switched to `Optional[float]`.
2. `anomaly_triggers.py`: module-level `Callable` alias with `|`
   syntax evaluated at import time. Switched to `Optional` form.

## Impact

Eliminates 37 test collection errors. Test suite: 1881 passed with 0
collection errors (remaining 51 failures are pre-existing, unrelated).

## Files

- `src/renquant_orchestrator/live_state_v2.py`
- `src/renquant_orchestrator/anomaly_triggers.py`
