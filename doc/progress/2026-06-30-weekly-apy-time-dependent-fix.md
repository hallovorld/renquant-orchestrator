# Weekly-APY monitor: make "now" injectable (fix time-dependent tests)

STATUS: done — branch `fix/weekly-apy-monitor-time-dependent`, PR against `main`.

WHAT:
- `weekly_apy_monitor.py`: thread an injectable `now` through the monitor.
  - Added `now: datetime | None = None` to `WeeklyApyContext`.
  - `LoadAuditRowsTask.run` now passes `now=ctx.now` into `read_recent_rows(...)`
    (the function already accepted a `now` kwarg; the src path just never wired it).
  - Added a `--as-of` CLI flag; `main` parses it via the existing
    `_parse_utc_datetime` and sets `ctx.now`.
- `tests/test_weekly_apy_monitor.py`: the 3 wall-clock-flaky tests now pin a fixed
  `now` (`2026-06-01`) instead of relying on the real clock — `WeeklyApyContext(now=...)`
  for the two pipeline tests, `--as-of 2026-06-01T00:00:00+00:00` for the CLI test.

WHY:
- `read_recent_rows` filters audit rows to a `window_days`-relative window around
  `datetime.now()`. The three tests wrote fixed May-2026 fixture dates but never
  injected a fixed "now", so as real wall-clock time advanced past ~60 days from
  those fixtures the boundary rows fell outside the window (`n_rows` 2 -> 1,
  drawdown streak collapses -> empty -> no action -> exit 0). The tests rot with
  the calendar rather than testing behavior. Injecting `now` makes them deterministic.
- `--as-of` also gives operators a replay/testing knob for the monitor.

EVIDENCE:
- `tests/test_weekly_apy_monitor.py`: 7 passed.
- Broader `tests/` (excluding 3 modules that need sibling repos `renquant_pipeline`/
  `renquant_execution` not installed in this env): 535 passed, 2 skipped; the only
  failures are pre-existing sibling-import ModuleNotFoundErrors, unrelated to this change.

SCOPE:
- One src file + its test. No behavior change when `--as-of` is unset (`now=None`
  -> real `datetime.now()`, identical to before). No live-tree changes.

NEXT:
- None required. If other monitors share the same `datetime.now()` pattern, apply the
  same `now`/`--as-of` injection so their tests don't rot either.
