# A test that goes red when production improves

STATUS: complete. Test-only. No probe, job, log or live surface is touched.

WHAT: `test_the_LIVE_2026_08_04_session_refutes_the_stdout_reading` stops asserting
that two rq105 jobs are still in their degraded states, and asserts instead that every
job gets a state the probe actually declares.

WHY/DIR: the test went **red on `main`** on 2026-08-05, and it went red because the
system got **better**.

Its last two lines were:

```python
assert rows["rq105-session-scheduler"]["state"] == P.STATE_LOG_EMPTY
assert rows["rq105-postclose-pairing"]["state"] == P.STATE_STALE_PRODUCT
```

Probed today against the same 2026-08-04 session:

| job | asserted | today |
|---|---|---|
| rq105-session-scheduler | `LOG_EMPTY` | `LOG_EMPTY` |
| rq105-postclose-pairing | `PRODUCT_STALE` | **`WROTE_OUTPUT`** |

[VERIFIED — `P.probe("2026-08-04")` on the live tree, read-only, 2026-08-05]

**The pairing product caught up.** The assertion had pinned a transient degraded
reading as though it were fixed evidence, so the only way for the suite to stay green
was for the loop to stay broken. A test whose green depends on production remaining
unhealthy is measuring the wrong thing, and it is worse than a flaky test: it applies
pressure in the wrong direction and it teaches the reader to ignore a red that this
time meant good news.

## What the test is for, kept intact

The purpose is to refute orch#621's headline that these jobs had been silent ~28 days.
That rests on `len(wrote) >= 4` and on three named jobs reading `WROTE_OUTPUT` —
unchanged, and evidence that only ever gets stronger.

The narrowing the review asked for (*"it does NOT claim the loop is healthy"*) is
carried by the docstring and by **not asserting health** — which is a different thing
from **asserting ill health**. The former stays true as the system changes; the latter
expires the moment anything is fixed.

## The invariant that holds either way

Every job must come back with a state the probe declares. Silence dressed up as an
unrecognised value is the one failure a liveness probe cannot have.

The known set is **derived from the module** (`STATE_*` in `vars(P)`), not hand-listed:
an enumeration silently rejects every state added later and silently accepts nothing
new, which would make this a rename detector rather than a contract check. It also
asserts the derived set is non-empty, so a renamed prefix fails loudly instead of
making the loop vacuous.

## A note on this file's own subject

This test file exists because orch#621 read a 0-byte `StandardOutPath` and reported
four rq105 jobs "silent 28 days" — the wrappers redirect to dated logs, so that file
stays empty whether or not the job runs.

**I repeated that exact mistake today** in orch#838, on five different jobs, and
retracted it in orch#840 before it merged. The correction was already committed here,
in this repo, and I did not find it until afterwards. Noting it so the next reader
meets both records together.

EVIDENCE:

| claim | value | provenance |
|---|---|---|
| the assertion fails on unmodified `src` | yes | [VERIFIED — re-run on a docs-only branch off main] |
| the cause is an improvement | `PRODUCT_STALE` → `WROTE_OUTPUT` | [VERIFIED — live `P.probe("2026-08-04")`] |
| the refutation assertions still pass | 4 wrote, 3 named jobs `WROTE_OUTPUT` | [VERIFIED — same probe] |
| probe suite | **15 passed** | [VERIFIED — `pytest -q tests/test_rq105_job_liveness_probe.py`] |
