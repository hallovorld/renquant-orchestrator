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

FOLLOW-UP (look-ahead fix, Codex blocking review on PR #211):
- `read_recent_rows` only enforced the lower bound (`row_dt >= cutoff`); it never
  enforced the upper bound against the injected/real `now`. An operator replay with
  `--as-of <past date>` would therefore consume EVERY later audit row in the file
  (look-ahead into the future relative to the requested as-of).
  - FIX: bound the window on both sides — `cutoff <= row_dt <= current`. Rows strictly
    after the effective `now` are excluded. Live behavior is unchanged: with `--as-of`
    unset, `current` is the real now and no future rows exist anyway.
- `test_pipeline_alerts_on_persistent_drawdown` previously built fixture dates relative
  to the real current date (via a `_recent_date` helper) while injecting `now=2026-06-01`,
  so the rows were in the FUTURE relative to the as-of and only "passed" because the
  upper bound was missing. Replaced with FIXED in-window dates 2026-05-21..2026-05-25
  (all <= now=2026-06-01, all inside the default 30d window, cutoff 2026-05-01). Removed
  the now-obsolete `_recent_date` helper and its unused `timedelta` import.
- Added regression coverage that a post-as-of row is excluded:
  `test_read_recent_rows_excludes_future_rows` (unit: future row not returned) and
  `test_main_as_of_excludes_future_rows` (e2e via `main --as-of`: `n_rows` counts only
  the <= now rows). Both FAIL against the old `row_dt >= cutoff` code and PASS with the
  two-sided bound, confirming they catch the look-ahead.

WHY:
- `read_recent_rows` filters audit rows to a `window_days`-relative window around
  `datetime.now()`. The three tests wrote fixed May-2026 fixture dates but never
  injected a fixed "now", so as real wall-clock time advanced past ~60 days from
  those fixtures the boundary rows fell outside the window (`n_rows` 2 -> 1,
  drawdown streak collapses -> empty -> no action -> exit 0). The tests rot with
  the calendar rather than testing behavior. Injecting `now` makes them deterministic.
- `--as-of` also gives operators a replay/testing knob for the monitor.

EVIDENCE:
- `tests/test_weekly_apy_monitor.py`: 9 passed (7 original + 2 new look-ahead regressions).
- Broader `tests/` (excluding 3 modules that need sibling repos `renquant_pipeline`/
  `renquant_execution` not installed in this env): 535 passed, 2 skipped; the only
  failures are pre-existing sibling-import ModuleNotFoundErrors, unrelated to this change.

SCOPE:
- One src file + its test. No behavior change when `--as-of` is unset (`now=None`
  -> real `datetime.now()`, identical to before). No live-tree changes.

NEXT:
- None required. If other monitors share the same `datetime.now()` pattern, apply the
  same `now`/`--as-of` injection so their tests don't rot either.
