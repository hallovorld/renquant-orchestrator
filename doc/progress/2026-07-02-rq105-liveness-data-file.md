# rq105 liveness: key on the tick DATA file — fix PR

STATUS:   ops fix (one logic change + comment).
WHAT:     rq105_liveness_check.py judged the quote loop by the wrapper LOG being non-empty;
          the first KPI scorecard (PR #247) caught the log at zero bytes while tick data
          flowed normally (module writes ticks directly; redirect stays empty) — a false
          alert waiting for 14:00 PT. Health now keys on logs/renquant105_pilot/
          intraday_ticks.jsonl existence + mtime (≤6h during a session day).
WHY:      liveness must watch the OUTPUT that matters (#212 rule) — the data, not the
          plumbing's chatter.
NEXT:     landing loop re-copies the script to the run checkout on merge (or the next
          ff-only pull picks it up before tomorrow's 14:00 check).

## Round 2 (Codex review — fail-open corrupt-row fallback)

**Finding.** The data-file freshness check (`_data_output_fresh`/`_last_jsonl_row`) parsed
only the file's LAST JSONL line; if that line was truncated, corrupt, or lacked the
required `"date"` field, the check fell back to trusting the file's raw `mtime` alone
("mtime says today, so it's probably fine"). A process appending a corrupt trailing row —
a crash mid-write, a bug — would still report healthy as long as the OS-level mtime looked
fresh, exactly the class of silent failure this data-file switch (round 1) was meant to
close.

**Fix.**
- `_last_jsonl_row` replaced with `_last_complete_jsonl_row`: scans the tail BACKWARD for
  the most recent row that is both valid JSON and carries the required `date`+`ticker`
  fields (all three collectors' actual write schema, confirmed by reading
  `intraday_quote_logger.py`/`intraday_pairing_logger.py`/`entry_timing_shadow.py`
  directly). The read starts at a fixed 8KB tail chunk and DOUBLES (capped at 128KB) if no
  complete row is found — so a legitimately oversized final row does not chop an earlier,
  perfectly valid row out of the search window.
- A row that fails validation is NEVER papered over with an mtime fallback. If no valid
  row is found at all, liveness FAILS.
- Added a fine-grained freshness bound: if the found row carries a `ts`/`source_ts`/
  `tick_time` field (the exact fallback chain `entry_timing_shadow.py` itself already uses
  to read its own rows back), its age is checked against a TIGHT 10-minute bound (all three
  collectors default to a 60s sample cadence — `intraday_quote_logger.DEFAULT_CADENCE_SEC`
  — so 10 minutes is several missed cycles of slack, far tighter than "anywhere today").
  A stale timestamp fails liveness even when the coarse `date` field still matches today.
- The "last physical line was corrupt, but an earlier complete row is fresh" case (a
  writer legitimately mid-write at the instant of the check) is handled without failing:
  the prior complete row is used, its freshness is verified via the tight bound above, and
  the corrupt tail is reported as a non-fatal `stderr` warning — never silently discarded,
  never fatal on its own.

**Evidence:** 8 new tests in `tests/test_rq105_collector_scheduling.py` covering: missing
required field (no more mtime fallback), corrupt-tail-only with fresh mtime and no
recoverable row, empty `date` value, mid-write recovery via a prior fresh complete row,
stale-valid-row-plus-fresh-corrupt-row (must report the real stale date, not fake
freshness off the corrupt row's mtime), a row correctly dated today but timestamp-stale
beyond the tight bound, and a final row larger than the fixed tail chunk (proves the
expanding-read backward scan still finds the earlier valid row). Two pre-existing tests
that referenced the removed `_last_jsonl_row` function were ported to the new
`_last_complete_jsonl_row`; one test that asserted the OLD fail-open mtime-fallback
behavior was rewritten to assert the corrected fail-closed behavior instead.

`python3 -m pytest tests/test_rq105_collector_scheduling.py -q` → 29 passed (system
`python3` is 3.9; this repo's PEP 604 syntax elsewhere needs 3.10+, a pre-existing
environment fact — re-verified clean via `uv venv --python 3.10` +
`uv pip install pytest pandas_market_calendars pandas`: 57 passed across both rq105 test
files with zero regressions).
