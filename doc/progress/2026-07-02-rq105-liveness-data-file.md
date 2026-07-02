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

## Round 3 (Codex review — future-timestamp fail-open + weaker missing-timestamp fallback)

**Finding.** Two consistency gaps in round 2's fix: (1) `age = now - ts_val` treated a
timestamp materially in the FUTURE (clock skew, corrupted/garbage `ts` field) as very
fresh — a negative age is always `< _TIGHT_AGE_BOUND`, so it passed; (2) a row with a
valid `date`+`ticker` but no parseable `ts`/`source_ts`/`tick_time` fell back to the OLD
"date matches today" check without the tight bound, silently permitting anywhere-in-today
staleness for that one case — weakening the exact contract round 2 established, even
though all three collectors are confirmed (by reading their write code directly) to emit
one of the three timestamp fields unconditionally.

**Fix.**
- New `_CLOCK_SKEW_TOLERANCE = 5 seconds`. A row's timestamp more than this far in the
  future is now rejected with an explicit "in the FUTURE... treated as corrupt/clock
  issue, not freshness" reason — distinct from the "exceeds bound" staleness message.
- `_last_complete_jsonl_row`'s definition of a "complete" row now REQUIRES a parseable
  timestamp (`_row_timestamp(row) is not None`) in addition to `date`+`ticker` — a row
  missing all three timestamp fields is treated exactly like a schema-invalid row (skipped
  by the backward scan, contributes to `tail_was_corrupt` if it's the physical last line),
  never silently accepted on a date-only match. `_data_output_fresh` now `assert`s
  `ts_val is not None` rather than branching around a `None` case that can no longer occur
  — a future refactor that weakens the invariant fails loudly instead of quietly
  reintroducing the date-only fallback.
- Module docstring updated to state the current contract precisely (timestamp required for
  row-completeness, future-timestamp rejection) rather than the round-2 wording.
- Updated the PR body, which still described the round-1 "existence + mtime ≤6h" contract.

**Evidence:** 6 new/updated tests: a row with `ts` 1 hour in the future is rejected
("FUTURE" in the reason); a row 2 seconds ahead still passes (tolerance isn't zero); a
row with `date`+`ticker` but no timestamp field is rejected ("timestamp" in the reason,
not silently accepted); `_last_complete_jsonl_row` directly tested to skip a
no-timestamp row and fall back to an earlier valid+timestamped one; the two round-2 tests
that previously wrote timestamp-free rows (`..._true_when_last_row_dated_today`,
`..._false_when_last_row_is_stale`) updated to include a `ts` field, since a bare
date-only row is no longer "complete" under the tightened contract.

`/Users/renhao/git/github/RenQuant/.venv/bin/python -m pytest
tests/test_rq105_collector_scheduling.py tests/test_pit_snapshotter_scheduling.py -q` →
54 passed (Python 3.10.20), zero regressions.

[VERIFIED — ran the exact commands above in this session; syntax-checked the modified
module directly; re-read all three collectors' write code to confirm the
ts/source_ts/tick_time-unconditional claim before relying on it, rather than assuming it.]

## Round 4 (Codex review): the round-3 "unconditional" claim was itself wrong — per-collector schema mismatch

**Finding.** Round 3's verification claim ("re-read all three collectors' write code") was
incomplete — it apparently checked field NAMES existed somewhere in each module without
tracing which are actually TOP-LEVEL on the emitted record. Codex traced the real record
constructors and found: `intraday_pairing_logger.build_paired_record()` writes NO top-level
timestamp field at all (timing lives nested in `batch_arm`/`intraday_arm` —
`ArmObservation.eligible_ts`, `QuoteRef.source_ts`); `entry_timing_shadow.build_record()`
writes top-level `entry_tick_time` (not `tick_time`), legitimately `None` on a
censored/no-entry-eligible row. Round 3's mandatory-top-level-field rule would have
REJECTED every real pairing row and every real censored entry-timing row as "corrupt" — a
production-breaking false-liveness-failure regression the round-2/3 synthetic tests (quote-
like rows only) could not catch, since they never exercised the actual pairing/entry-timing
record shapes.

**Fix.**
- `_data_outputs()` now returns `(name, path, timestamp_extractor, allow_file_completion)` —
  a per-collector extractor instead of one shared rule: `_row_timestamp_quote` (unchanged
  top-level fallback), `_row_timestamp_pairing` (reads nested arm fields, intraday arm
  preferred over batch), `_row_timestamp_entry_timing` (reads `entry_tick_time`).
- `entry_timing_shadow` is a genuine POST-CLOSE ONE-SHOT batch writer (not continuously
  appended) — a censored row's freshness now falls back to the file's own mtime
  (`allow_file_completion=True`), the legitimate collector-completion signal for a
  once-daily write. This differs in kind from the original round-2 mtime-alone bug: that
  bug applied mtime-only trust to a CONTINUOUSLY-appended feed (where mtime cannot prove
  recent CONTENT); here mtime genuinely IS "when this one-shot job ran."
- `intraday_pairing_logger` stays `allow_file_completion=False` — it's continuously
  appended, so a row with no extractable timestamp anywhere is still treated as incomplete,
  same as a corrupt row (never a silent file-mtime fallback for this collector).
- Fixed a secondary `tail_was_corrupt` diagnostic bug found while restructuring the scan:
  an oversized true-last-line that needed a bigger read but ultimately parsed successfully
  was being reported as `tail_was_corrupt=True` even though the returned row genuinely WAS
  the file's actual last line (just needed more bytes) — corrected to reflect whether we
  actually fell back to an EARLIER row, not a transient first-pass failure that resolved.
- Module docstring, PR body corrected to remove the round-3 overclaim and describe the real
  per-collector contract.

**Evidence:** 6 new tests build rows via the REAL `build_paired_record()`/`build_record()`
constructors (not synthetic quote-like dicts): a normal pairing row, a normal entry-timing
row (`entry_tick_time` present), a censored entry-timing row (file-mtime fallback, both
fresh-passes and stale-file-fails cases), and a pairing row with no extractable timestamp
(correctly fails, no file-mtime escape hatch for this collector). Plus a direct test proving
the oversized-true-last-line diagnostic fix.
`/Users/renhao/git/github/RenQuant/.venv/bin/python -m pytest
tests/test_rq105_collector_scheduling.py tests/test_pit_snapshotter_scheduling.py -q` →
60 passed (Python 3.10.20), zero regressions.

[VERIFIED — read `build_paired_record()`, `ArmObservation`/`QuoteRef` dataclasses, and
`build_record()` directly in this round (not the round-3 approach of trusting a prior claim)
before writing the extractors; every new test constructs its fixture via the actual
production functions, not a hand-written dict guessing at field names.]

## Round 5 (Codex review — event-time vs. completion-time: round-4's fields were right, the
## freshness MEANING was still wrong for both post-close collectors)

**Finding.** Round 4 correctly identified WHICH field each collector's timestamp lives in,
but kept applying the quote feed's tight ≤10-minute *event-time* bound to all three.
`intraday_pairing_logger` and `entry_timing_shadow` are POST-CLOSE ONE-SHOT batch jobs
(`run_postclose_loggers.sh` fires once at 13:15 PT; `rq105_liveness_check` runs at 14:00 PT,
~45min later, per the plists/README) whose row timestamps are MARKET-EVENT instants, often
near session open — not proof the collector itself ran recently. A perfectly healthy
post-close job that ran on schedule and correctly wrote today's real data would still fail
round 4's check, since the events it reports happened hours before the post-close run.
Round 4's `allow_file_completion=True` was also inconsistent — it only used file mtime on
the branch where the row's own timestamp was ABSENT (the censored entry-timing case), so a
NORMAL entry-timing row (with a real `entry_tick_time`) and every pairing row still used
event-time with the 10-minute bound — meaning one collector's liveness MEANING silently
changed based on policy outcome (censored vs. not).

**Fix.**
- Replaced the boolean `allow_file_completion` with an explicit `freshness_basis` of either
  `_ROW_EVENT_TIME` (`intraday_quote_logger` — unchanged, correct: a continuous sampler's
  last row is always recent) or `_FILE_MTIME` (`intraday_pairing_logger`,
  `entry_timing_shadow` — the file's own mtime, applied UNCONDITIONALLY to every row from
  these two collectors, not only timestamp-missing/censored ones).
- New `_POSTCLOSE_COMPLETION_AGE_BOUND = 90min` for the `_FILE_MTIME` basis — covers the
  45min postclose→liveness gap plus launchd scheduling jitter and normal runtime, while
  remaining far tighter than "anywhere in today's ~6.5hr session." `_TIGHT_AGE_BOUND`
  (10min) is now scoped explicitly to the quote feed only.
- `_last_complete_jsonl_row`'s completeness rule updated to match: under `_FILE_MTIME`
  basis, a schema-valid row is complete regardless of whether its own timestamp extracts
  (the row's timestamp is diagnostic only, never gates completeness or freshness for these
  two collectors) — reversing round 4's `intraday_pairing_logger` behavior specifically
  (round 4 kept it event-time/incomplete-without-timestamp; that was itself wrong once the
  postclose/batch nature of this collector was correctly understood).
- Added `check_collector_data_outputs(data_root, as_of) -> dict[name, {status, path,
  reason}]` — a STABLE PUBLIC interface encapsulating the per-collector extractor/basis
  dispatch behind one call, so external consumers never need the internal tuple shape.
  `renquant-orchestrator#247`'s KPI scorecard currently imports `_data_outputs`/
  `_data_output_fresh` directly and will break against this round's internal signature
  change (4-tuple → new basis semantics) — flagged as a required follow-up in #247, not
  fixed here (out of scope for this file's own worktree; #247 needs its own PR to switch to
  the new public function).

**Evidence:** rewrote/added tests using the REAL `build_paired_record()`/`build_record()`
constructors for every scenario, including the two codex named explicitly: a healthy
post-close run whose row event-timestamps are from this morning (hours old) but whose FILE
was freshly written — reports fresh; an old file (mtime 3h stale) containing today's morning
event-timestamped rows — still reports stale, proving the check genuinely reads file mtime
as the completion signal rather than being fooled by plausible-looking row content. Also
added the paired positive/negative mtime-staleness tests for the pairing collector's
no-timestamp case (round 4 only tested entry-timing's censored case).
`/Users/renhao/git/github/RenQuant/.venv/bin/python -m pytest
tests/test_rq105_collector_scheduling.py -q` → 42 passed (Python 3.10.20), zero regressions.

[VERIFIED — read `ops/renquant105/README.md` and `com.renquant.rq105-postclose.plist`
directly to confirm the actual 13:15 PT postclose-fire / 14:00 PT liveness-check schedule
(the 45min gap) before choosing the 90-minute bound, rather than picking an arbitrary
number; every new test's fixture timestamp was checked against `_TIGHT_AGE_BOUND` to
confirm it genuinely WOULD fail the old event-time check, proving the test exercises the
real fix rather than passing coincidentally.]
