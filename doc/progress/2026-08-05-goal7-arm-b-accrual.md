# 2026-08-05 — GOAL-7: Arm B is ~2027, and nothing was checking it was coming

## The gap

The frozen registration says Arm B — **the only arm that may certify** — becomes
eligible when BULL_CALM has ≥30 evaluation dates with matured labels, "not
before ~2027".

A date that far out is exactly the promise nothing verifies. If the weekly
training job stops, the ledger simply never grows, Arm B never arrives, and
**no alarm distinguishes that from waiting**. This project has met that shape
repeatedly: deployed-but-dark, merged-not-deployed, a sentinel watching the
wrong object.

## Measured `[VERIFIED — this session]`

```
ledger rows ................. 1
distinct cutoffs ............ 1
newest cutoff ............... 2026-08-02 (3d ago, 0 missed 7d firings)
matured BULL_CALM dates ..... 0 of 30 needed

2026-08-02  regime=BULL_CALM  matures 2026-10-23

STATE: GENESIS_ONLY_NO_CADENCE_YET
projection: REFUSED — 1 cutoff, fewer than 3
```

`com.renquant.momentum-train-weekly` is installed, last exit 0, next fire
Saturday. So the lane is alive and has produced exactly its genesis row.

## Why the projection is refused, and what refusing protects

One point is not a rate. Projecting from the registration's *assumed* weekly
cadence would report an **assumption as a measurement** — the tidy answer is
available and it is the wrong one. The probe refuses until it has three cutoffs
to observe a cadence from, and names the refusal.

What can be said today, as arithmetic behind the registration's estimate rather
than a new claim: BULL_CALM is **1684 of 2380** production-regime dates =
**70.8 %** `[VERIFIED — orch#825's Arm A run]`. At one scoring per week that is
~42 weeks to reach 30 BULL_CALM cutoffs, plus the last one's 60-business-day
maturity. Consistent with "~2027" — now with the arithmetic attached, so the
date stops being folklore.

## What the probe keeps apart

| state | means |
|---|---|
| `LEDGER_ABSENT` / `LEDGER_UNREADABLE` | could not read the evidence — **not** "nothing accrued" |
| `GENESIS_ONLY_NO_CADENCE_YET` | started, too few rows to observe a rate |
| `ACCRUING` | growing on cadence |
| `STOPPED_ACCRUING` | **≥2 missed firings** — the failure this exists for |
| `ARM_B_ELIGIBLE` | the §6 sample floor is met |

**Two** missed firings, not one: an operator rebooting a machine is not an
incident, and crying one teaches the reader to ignore the next.

**An unknown regime is not the primary one.** If the production regime chain
cannot run, every per-date regime is `None`, the matured-BULL_CALM count stays
**0**, and the render says *"UNKNOWN, not zero"* — assuming the primary would
inflate the single number that decides eligibility.

**Maturity ignores market holidays**, so every `matures` date is the **earliest
possible**. Stated because an optimistic maturity makes Arm B look closer than
it is.

## Three correctness gaps the review found, all real `[codex on orch#836]`

**1. Two declared states could never be observed.** `LEDGER_ABSENT` and
`LEDGER_UNREADABLE` were in the state table, but `probe()` *raised* instead of
returning them and `--json` emitted nothing at all. **A declared state a caller
cannot observe is not a state** — and a daily report that gets an exception
where it expected a row cannot tell *unavailable evidence* from *not eligible
yet*, which is the one distinction this probe exists for. `probe_result()` now
returns a structured row for both (counts `None`, **not zero**), the CLI exits
**2** on them, and the exception stays available for callers that want it.

**2. A broken producer could read as an empty ledger.** A row with no
`cutoff_date` was silently skipped; a malformed one raised a raw `ValueError`.
Every field the accrual needs is now validated per row and surfaces as
`LEDGER_UNREADABLE`. A row the accrual cannot count is a **broken producer**,
not "nothing accrued yet".

**3. An eligible arm was still being forecast.** Once
`n_primary_matured ≥ 30`, `need` went ≤ 0 and the arithmetic produced a
"projected eligibility" date **in the past**. A reached threshold is not a
forecast; the projection is now explicitly refused with *"already eligible"*.

## Not claimed

Nothing about whether the momentum member works. Arm A already established that
all four §6 conditions hold on the reconstruction **and certify nothing**. This
is about whether the evidence that *could* certify is still being produced.

Suites: 18 tests — the three unreadable/absent/stopped distinctions, one late
firing NOT reading as stopped, the refusal-to-project, projection from an
observed rate once there are three cutoffs, business-day maturity, unknown
regimes counting as unknown, and the live ledger pinned — plus the three above: unavailable
evidence as an observable state with `None` counts and CLI exit 2, a row with a
missing/malformed/non-object `cutoff_date` reading as `LEDGER_UNREADABLE`, and
an already-eligible arm projecting nothing. Regimes come from an injected stub
so the tests never depend on the umbrella being present.

## Next

Unscheduled and read-only for now. Wiring it into the daily fleet report is the
obvious follow-up and a separate reviewable step — a probe nobody runs has the
same failure mode as the thing it watches.

## Review round 3: unavailable evidence had a second door

`is_file()` succeeding does not make the bytes readable. `path.read_text()` can still
raise `OSError` (permission, mid-read I/O) or `UnicodeDecodeError` — **after** the
existence check — so those escaped the state machine entirely and `--json` emitted no
`LEDGER_UNREADABLE` row at all. The states exist to keep "I could not see the
evidence" apart from "nothing accrued"; a path that bypasses them defeats the whole
construction, and it is the least visible way to do it.

The read/decode step is now inside `LedgerUnreadable`, carrying the exception type so
the reason is legible rather than just "unreadable".

Two regressions: a monkeypatched `PermissionError` on that exact path (asserting the
structured result, `n_rows is None`, and `--json` exit 2 with the state), and a file
of genuine non-UTF-8 bytes. Both fail against the pre-change module [VERIFIED — `git
stash push ops/…`, re-run: 2 failed]. Suite: 20 passed.
