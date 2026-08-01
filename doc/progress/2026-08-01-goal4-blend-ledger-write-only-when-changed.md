# GOAL-4 — reading the blend evidence rewrote it, and a crash would have destroyed it

**Date:** 2026-08-01 · `renquant-orchestrator` · GOAL-4 (blend 陪跑台账)

## The blend ledger, as it stands

Five sessions accumulated, none matured `[本次实测 2026-08-01]`:

| run_date | prod∩blend top-10 | candidates | clf scored | aged | realized |
|---|--:|--:|--:|---|---|
| 2026-07-27 | **6/10** | 84 | 80 | False | False |
| 2026-07-28 | **6/10** | 85 | 77 | False | False |
| 2026-07-29 | **6/10** | 84 | 78 | False | False |
| 2026-07-30 | **7/10** | 83 | 77 | False | False |
| 2026-07-31 | **6/10** | 83 | 79 | False | False |

The blend and prod disagree on **3–4 of 10 picks every session**, so the arms are
genuinely distinguishable at the *picks* level without waiting for maturity. No row is
`aged`: `MATURITY_TDAYS = 61`, so 2026-07-27 realizes around **late October 2026**. There
is nothing to conclude about performance yet and this document concludes nothing.

## The defect

`mature_fill`'s comment has said *"Write whenever anything changed — including
telemetry-only updates"* since it was written. The line under it was:

```python
ledger.write_text("".join(json.dumps(r) + "\n" for r in rows))
```

**Unconditional.** No comparison, no `if`. Measured by running the readout on a
non-session day with `filled == 0` — **the live ledger's mtime moved anyway.**

Two consequences, neither cosmetic:

- **Reading the evidence mutated it.** Every diagnostic invocation rewrote an
  *append-only* ledger. That is how an analysis pass becomes a write to a live data
  surface — precisely what the append-only design exists to prevent.
- **A crash truncated it.** `write_text` truncates and *then* writes; an interrupt between
  those leaves an empty or partial file, and **no other copy of these sessions exists.**

## The fix

Compare rendered bytes against what is on disk, and write through a temp file +
`os.replace` (atomic on POSIX). This preserves the original intent exactly — a
telemetry-only update still differs, so it still writes — while a no-op pass touches
nothing and an interrupted pass leaves the previous ledger byte-identical.

`current = None` on `OSError` means **write**, not "assume it already matches": the
fail-open reading would silently skip persisting a real update.

## I caused this write, and that is the honest part

I ran `rq104_blend_readout.py` to read the ledger. `mature_fill` runs *before* the
"no new session" message, so **my diagnostic invocation rewrote a file under
`RenQuant/data/`** — a live data surface I am not to write. The content was a round-trip
of the same rows by the same serializer and `filled == 0`, so no value changed; the write
still happened and should not have. The fix removes the class of accident, but the rule
that would have prevented it is mine to keep, not the code's.

## And a number I nearly published

My first read of the ledger reported **overlap 0/10 on all five sessions** — because I
guessed the keys `prod_top10` / `blend_top10`, which do not exist; the real ones are
`picks_prod` / `picks_blend`. The 6–7/10 above is the corrected measurement. That is the
fifth instance this session of a claim built on a guessed field name, and the only reason
it did not ship is that 0/10 contradicted a number already on the record.

## Tests

6. A no-op pass leaves mtime **and** bytes untouched; a telemetry-only change still
writes; a simulated interrupt after the temp write leaves the previous ledger byte-identical
and non-empty; no `.tmp` survives success; an absent ledger creates nothing.

The first fixture used a `date` column where the real schema is `as_of_date`, so the query
threw, `mature_fill` returned 0 before the write, and two tests failed for a reason
unrelated to the fix. Recorded because "the test failed" and "the code is wrong" are
different findings.

Suite: **5157 passed, 2 skipped**, run before the push.
