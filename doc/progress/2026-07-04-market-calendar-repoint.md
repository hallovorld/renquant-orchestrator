# Re-point to the canonical NYSE market calendar (campaign B5)

Date: 2026-07-04
PR: fix(calendar): re-point to the common canonical
Campaign: B5 (PR #297 / audit #296 §4.1, XC-2, XC-3) — six independent
"previous / last-completed NYSE session" implementations, one canonical in
renquant-common, all re-pointed.

## What changed here (4 of the 6 sites + the de-facto canonical live in this repo)

- `intraday_quote_logger.py` (§4.1 row 1, the de-facto canonical):
  `SessionBounds` / `SessionCalendar` / `NyseSessionCalendar` /
  `default_session_calendar` lifted VERBATIM to
  `renquant_common.market_calendar` and re-exported here SAME-OBJECT, so
  every in-repo consumer (scheduler, session inputs, entry-timing, both ops
  liveness checkers) and their tests are untouched.
- `retrain_alpha158_fund.py` (row 2): `_expected_last_completed_session`
  (the docstring-admitted hand-mirror of base-data, already diverged 16d vs
  14d) and `_default_session_gap` now delegate to the canonical
  (`last_completed_session` / `sessions_between`); kept as named seams for
  the test monkeypatches and the FreshnessUnprovableError mapping. The
  freshness gate's "independently-derived" contract is clock-vs-data, not
  library-vs-library — CI comment updated accordingly.
- `scripts/kpi_scorecard.py` (row 5): `_ledger_session_keys` (the
  docstring-admitted copy of backtesting's session_resolution semantics)
  delegates to canonical `sessions_between` + `session_keys`; the weekday
  fallback stays as this call-site's EXPLICIT lenient wrap (also covers a
  stale-deployed renquant_common).
- `ops/renquant105/batch_scores_bundle.py` (row 6):
  `expected_previous_session` delegates to canonical `previous_session`
  (same fail-closed ValueError contract); added a bare-script bootstrap so
  the launchd wrapper (which passes no PYTHONPATH) resolves a sibling
  renquant-common when the venv install predates market_calendar.
- `intraday_session_inputs.py` (row 7): `previous_session` day-walk
  delegates to canonical `previous_session_from_calendar`
  (injected-calendar generic); FrozenSignalError contract preserved.
- Ops wrappers (`run_quote_logger.sh`, `run_session_scheduler.sh`,
  `run_postclose_loggers.sh`, `run_shadow_serving.sh`) put a sibling
  renquant-common on PYTHONPATH (pinned `-run` checkout preferred);
  shadow-serving exports it BEFORE the bundle-verify step. Both liveness
  checkers' lazy bootstraps extended the same way.
- Ratchet: `tests/test_market_calendar_repoint.py` asserts ZERO
  `import pandas_market_calendars` remain in src/scripts/ops (the XNYS
  `exchange_calendars` research scripts are a different package, note-only
  per audit rows 8-9) + same-object and golden-vector lockstep tests.

## Divergence disposition (the audit's classes)

- 16d vs 14d lookback: canonical default 30d dominates both; proven
  immaterial on the 10-year fixture (NYSE's longest modern closure ~6
  calendar days). Not reachable on any live path.
- Fail-closed vs swallow: canonical raises; each lenient call-site wraps
  explicitly (kpi weekday fallback; base-data None). No silent lenient
  default remains.
- kpi's `clip(min=0)` on dates preceding the sessions window: canonical
  raises instead — degenerate-only (the 14-day pad makes idx<0 impossible),
  documented as the one behavior-affecting edge; not reachable on a live
  path.

## Evidence

- 10-year equivalence fixture (2016-01-01..2026-12-31, every calendar date;
  4 intraday probes for last-completed-session incl. half-day closes and
  the exact-close boundary): all six impls + umbrella script variants
  byte-identical to the canonical (0 mismatches).
- Suites: orchestrator 1870 passed / 3 skipped on the branch vs 1861 / 3 on
  pristine main (delta = the 9 new lockstep tests); common 271 passed;
  base-data 240; backtesting 317; umbrella targeted 30.

## Merge order

renquant-common `feat(calendar)` FIRST (consumers' CI checks out
common@main and stays red until then) → orchestrator / base-data /
backtesting in any order → umbrella scripts LAST. Deploy: advance the
renquant-common pin (0.10.0); the ops-wrapper PYTHONPATH fallback covers
the venv's stale 0.8.1 install; a pinned `renquant-common-run` checkout is
the recommended landing step (operator action).
