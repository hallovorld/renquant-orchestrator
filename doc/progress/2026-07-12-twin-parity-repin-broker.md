# fix: re-pin twin parity manifest for execution broker changes

**Date**: 2026-07-12
**PR**: fix/twin-parity-repin-broker

## Change

Re-pin `data/twin_parity_manifest.json` for `broker.py` and
`alpaca_broker.py` in renquant-execution. The execution side diverged
from the pinned hash after recent broker changes were merged upstream.

Generated via `python scripts/check_twin_parity.py --write-manifest`.
All 23 twin-parity checks pass after re-pin.
