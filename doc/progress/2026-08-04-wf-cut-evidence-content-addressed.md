# 2026-08-04 — wf-cut evidence verification: content-address the subject, not the slot

## What broke

`make test` on fresh main went red on
`test_wf_cut_independence.py::test_the_manifest_VERIFIES_against_the_sources_when_they_are_present`:

```
AssertionError: 04d7a381cd6d... != 7a232110d2cb...
```

The 2026-07-31 evidence bundle (`doc/research/evidence/2026-07-31-wf-cut-independence/evidence.json`)
records its artifact subject as `panel-ltr.alpha158_fund.previous.json` — a **moving slot**
that every pair-swap rewrites. Today's RFC #210 promotion (11:31 PT, designed behavior)
replaced the slot's contents, so the test turned a legitimate promotion into a suite red.
This is the "tests that measure the operator's disk" class: the assertion's subject was a
name on the live tree, not the measured bytes.

## Measured facts [2026-08-04]

- Slot `prod/panel-ltr.alpha158_fund.previous.json` now holds sha `04d7a381cd6d…`
  (the pre-promotion ACTIVE, displaced by today's swap).
- The evidence-recorded bytes still exist on the machine:
  `prod/panel-ltr.alpha158_fund.weekly_rollback_2026-07-06.json` hashes to the full
  recorded `7a232110d2cb…` (read back from `shasum` stdout).
- The sim manifest digest still matches its recorded sha (stable committed corpus).

## Fix

The test now identifies the artifact subject by **content**: it tries the recorded slot
name first as a hint, then scans `prod/panel-ltr.alpha158_fund*.json` siblings for a file
whose sha256 equals the recorded `artifact_sha256`. Any hit satisfies the verification.
If the bytes are nowhere on the machine (rollback copies eventually get pruned), the test
skips **loudly**, naming both digests — same principle as the existing tree-absent skip: a
verification that cannot run must not read as one that passed. The manifest half is
unchanged and still hard-asserts (that file is a stable corpus, not a slot).

The 07-31 evidence bundle itself is untouched — it is a frozen historical measurement and
stays correct about the bytes it measured.

## Verification

- `pytest tests/test_wf_cut_independence.py` — 33 passed (was 1 failed / 32 passed).
- Full suite before fix: 1 failed, 5509 passed; the failure is exactly this test.

## Lesson (existing register)

Evidence bundles must name their subject by content hash only; any live-tree *name* is a
hint for locating bytes, never an identity. `.previous` / rollback slots are rewritten by
routine promotions — RFC #210 made that weekly, so slot-pinned assertions are now
guaranteed to rot on schedule.
