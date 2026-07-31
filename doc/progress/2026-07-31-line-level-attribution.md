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
