# D-group: hardcoded path cleanup (OR-9 + related)

DATE: 2026-07-04

## What

Replace hardcoded `Path.home() / "git/github/RenQuant/..."` paths with
`default_data_root()` from `runtime_paths.py` in 4 modules:
- `entry_timing_shadow.py` (OR-9 audit finding)
- `intraday_pairing_logger.py` (same pattern)
- `risk_budget/budget.py` (removed `DEFAULT_UMBRELLA`)
- `risk_budget/report.py` + `attribution/report.py` (forbidden-prefix guards)

All paths now resolve via `RENQUANT_DATA_ROOT` env or the default path resolver,
consistent with the rest of the 105 family. Behavior-invariant: the resolved
default path is the same on the operator's machine.
