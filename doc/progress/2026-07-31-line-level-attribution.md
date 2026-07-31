# Attribution, measured at the LINE — with the matching rule stated

**Bottom line `[本次实测 2026-08-01]`.** Codex was right that the earlier CSV proved
nothing about attribution: it recorded filenames and mtimes and never looked at a line.
Rather than narrow the claim, this measures the thing.

**The matching rule.** A line **self-attributes** iff it begins with an ISO date, an ISO
datetime, or `HH:MM:SS`, optionally preceded by `[` or `"`:

```
^\s*(?:\[|")?(?:\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}|\d{2}:\d{2}:\d{2}|\d{4}-\d{2}-\d{2})
```

A timestamp **elsewhere** in the line does not count — it cannot order two lines from
different runs.

| layer | lines | self-timestamped | |
|---|---:|---:|---:|
| launchd stdout, all 14 failing jobs | **8 079** | **0** | **0.000** |
| dated wrapper logs, 14 most recent of 908 | 3 682 | 1 018 | 0.276 |

## What this establishes, and what it replaces

**Not one line** in the launchd stdout layer carries its own timestamp — across
**8 079** lines and every failing job. So for that layer, *"an append-only file can
still contain attributable per-run records"* is measured and **false**.

The dated-wrapper layer is **partly** attributable and the spread is the point:
per-file fractions run **0.0000 … 0.9969**, with **6 of 14 at exactly zero**. So a
**dated filename does not imply attributable lines** — codex's exact objection,
now a measurement rather than a rebuttal.

**This replaces the retracted "7 of 14 attributable" headline.** That number came from
a wrapper-source classifier and was wrong in both directions (orch#679, folded in here).
These numbers are read off the bytes, under a rule anyone can re-run.

## Two of my own errors in this round, both caught before publishing

1. I asserted `max(frac) == 1.0` — the value I had read off a **2-decimal printout**.
   The measured value is **0.9969** (324/325). Asserting a display value is the
   assert-instead-of-measure shape, at the smallest possible scale.
2. I asserted `"self-attributes" in prose` where the prose writes `SELF-ATTRIBUTES`.
   A case-sensitive check against my own text.

Both were test-side, both failed immediately, and both are recorded rather than
silently amended.

Tests: 5. Suite **4792 passed / 2 skipped**.

---

# Made re-runnable, and the claim narrowed — after codex on #676

## The claim, restated to what was measured

Withdrawn: *"per-run attribution is impossible on this surface."* What was measured is
narrower and is all that is claimed now:

> **Under a stated rule — a line self-attributes iff it BEGINS with an ISO date, an ISO
> datetime, or `HH:MM:SS`, optionally preceded by `[` or `"` — not one of the 8,112
> non-blank lines across the 14 failing jobs' `launchd` stdout begins with a
> timestamp.**

A leading timestamp is not a run identifier, and its absence does not prove attribution
is impossible: a **non-leading** timestamp, an explicit **start/end marker**, or an
external index could each attribute a record. None of those was searched for, so nothing
is claimed about them.

## `ops/evidence_census.py` — the census is now reproducible

`[本次实测 2026-07-31]` The original CSVs carried a **basename** (`launchd_stdout.log`)
and no digest, so the figure could not be re-derived and a reader could not tell whether
the file in front of them was the file that was counted. The census now resolves every
source from the **installed plist's `StandardOutPath`** and records, per label: the
absolute path, a **sha256 of the exact bytes counted**, size, mtime, the line counts, and
the **plist's own sha256** — the plist decides *which* file a job writes, so pinning the
log without it cannot tell a changed log from a redirected one.

```
python3 ops/evidence_census.py --out doc/research/evidence/2026-07-31-failing-surface-evidence
```

## What re-running it showed

| | committed | re-census |
|---|---:|---:|
| 14 failing jobs, non-blank lines | 8,079 | **8,112** |
| …self-timestamped | **0** | **0** |

**The load-bearing figure reproduces exactly. The denominator moved by 33 lines**, and
the reason is the argument for digests: `agent-pr-loop` (+26) and `run-surface-drift`
(+7) are **live logs still being appended to**. A line count of a moving target is only
meaningful pinned to a digest and an mtime — which is what the census now emits.

## Positive control — the rule is not simply failing to match

A count of zero is worthless if the regex never matches anything. Across all 39
countable labels the rule fires **794** times in **135,851** lines, including:

| label | self-timestamped | fraction |
|---|---:|---:|
| `weekly-fundamental-refresh` | 39 / 39 | **1.00** |
| `monthly-meta-label-retrain` | 3 / 4 | 0.75 |
| `daily-news-sentiment` | 686 / 81,004 | 0.0085 |

At **1.00** on one file, the rule demonstrably matches real log lines. The zeros are
real zeros.

## A defect in the census itself, found by running it

The first version used `plistlib` only, which is `expat`-strict and **rejects `--`
inside an XML comment**. Two heavily-annotated plists contain exactly that, so the
census recorded them as **absent** — reporting a parser limitation as a fact about the
run surface. Both are loaded and running (`launchctl list` shows
`weekly-retrain-patchtst` and `weekly-tournament-retrain` at status 0).

`ops/run_surface_drift_check.py:_plist_load` **already** handled this with a `plutil`
fallback, and its comment names the same cause. Checking that before filing anything is
what kept this from becoming a bogus "two malformed plists" finding. The census now uses
the same fallback: coverage went **37 → 39 of 40**, and one of the two recovered labels
turns out to contribute **62** self-timestamped lines to the positive control.

The single remaining absent label, `rq104-risk-budget`, is a real observation: its
plist declares a `StandardOutPath` that **does not exist**.
