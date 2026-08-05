# 2026-08-05 — GOAL-4: three of five shadow lanes produced no separating evidence

## The premise question, asked as a measurement

GOAL-4 is "multi-model ensemble". The fleet exists to accumulate evidence that
separates candidate scorers from the deployed one. **That only works if the
candidates rank names differently.** A lane whose top-K is prod's top-K would
have bought the same names that day — it produced no separating evidence at all,
and is an expensive way to re-run prod.

**Nothing in the fleet measured this.** Every lane reports its own decision;
agreement with prod is invisible because no one compares them.

## Measured `[VERIFIED — this session]`

2026-08-04, against prod run `2026-08-04-live-a199b993` (83 scored):

| lane | n | spearman | top10 | resid/sd | prod_sd | state |
|---|---:|---:|---:|---:|---:|---|
| blend | 81 | 0.6058 | 5/10 | 91.9 % | 1.3448 | DIVERGED |
| **blend_mom** | 82 | **0.9997** | **10/10** | **1.1 %** | 1.3394 | **SAME_TOP_K_AS_PROD** |
| blend_rb_mom | 82 | 0.9272 | 8/10 | 49.4 % | 1.3394 | DIVERGED |
| blend_mom_fast | — | — | — | — | — | **RAN_AND_SCORED_NOTHING** |
| blend_rb_fast | — | — | — | — | — | **RAN_AND_SCORED_NOTHING** |

`blend_mom` picked prod's **entire top 10**, and its score is — to ~1 % of the
score's own cross-sectional dispersion — an **affine rescaling of prod's**.
Two more lanes recorded a run and scored nothing (matching their
`panel_scoring_fail_closed` log lines).

So of five shadow lanes on that date: **one produced no separating evidence
because it agreed, two because they did not score.**

## The caveat is bigger than the finding

**`blend_mom` has exactly one date.** All four of its runs are 2026-08-04
re-runs `[VERIFIED]`. One date cannot support a conclusion about a lane in
either direction, and this does not draw one. It is a claim about what evidence
the fleet **has**, not about whether any lane's model is good — `blend_mom`'s
momentum member is not judged here at all. That is exactly why the number wants
counting over time instead of asserting once, which is what the probe is for.

The one lane with a history behaves differently: **`blend` over six dates
never once matched prod's top 10** `[VERIFIED — this session]`, and that claim
now has its own committed record
(`doc/progress/data/2026-08-05-fleet-divergence-blend-range.json`) rather than a
test that re-derives it from mutable sqlite:

| date | prod run | top10 |
|---|---|---:|
| 2026-07-28 | `2026-07-28-live-5b859fff` | 7/10 |
| 2026-07-29 | `2026-07-29-live-34603e64` | 7/10 |
| 2026-07-30 | `2026-07-30-live-7521e521` | 7/10 |
| 2026-07-31 | `2026-07-31-live-381747dd` | 6/10 |
| 2026-08-03 | `2026-08-03-live-ff1f674a` | 6/10 |
| 2026-08-04 | `2026-08-04-live-a199b993` | 5/10 |

## A denominator that moved 8×

`resid/sd` is normalised by prod's own cross-sectional score sd, and that
**went 0.17 → 1.35 on 2026-08-04** when prod itself became a two-component
z-blend `[VERIFIED]`. So the ratio is **not comparable across that boundary**,
and the probe prints `prod_score_sd` on every row: a ratio whose denominator is
invisible is a number nobody can check.

## No invented threshold

The verdicts are facts, not cutoffs:

- `NO_RUN` vs `RAN_AND_SCORED_NOTHING` — no evidence, for two different reasons
  that must not collapse into one (a lane failing closed every day looks
  identical to a lane not scheduled, if you merge them);
- `SAME_TOP_K_AS_PROD` — the lane's top-K set **equals** prod's. Definitional;
- `DIVERGED` — otherwise, with its counts.

The residual ratio is a **magnitude, never a verdict**. Picking a cutoff for it
after seeing these numbers is the forking path this file exists to expose, not
to commit. A test pins that: a lane with a real non-zero residual **below** the
cut still reads `SAME_TOP_K` — the state answers "would it have bought the same
names", not "is it identical".

## Two review blockers, both real `[codex on orch#826]`

**1. The reference was not validated.** If prod had no run on the date — or a
run that scored nothing — `probe()` kept going: every lane compared against an
**empty** prod score set, landed in `TOO_FEW_COMMON_NAMES`, and the summary
line reported the whole fleet as producing "no separating evidence".
**A missing control would have been published as a finding about the fleet.**
The reference is now the first thing checked, and its absence (or too few names
to define the requested top-K) **refuses the entire run** with exit 3 rather
than colouring it.

That is the same shape as the thing this probe was built to catch, arriving
from the other direction: a number that looks like a measurement of the fleet
but is actually a measurement of the harness.

**1b. A range claim needs a record of the range** `[codex on orch#826]`. The
six-date statement was asserted from a test that re-queried mutable sqlite and
skipped when absent, while the committed bundle held **one** date. `--range`
now persists all six as one bundle — each with its prod run id, the lane run id,
and both score-set hashes — and a date whose baseline is unavailable is
**RECORDED as such, never dropped**, because a range that quietly shrinks is a
different range.

`--top-k` also refuses zero and negatives: an empty top-K set makes **every**
lane read `SAME_TOP_K_AS_PROD` — the strongest verdict this file can emit, from
a parameter that asked for nothing.

**2. The record was not auditable.** The probe reads **mutable** sqlite, and a
result naming only a run id cannot prove the rows behind that id are the rows
compared. Every row now carries `score_set_sha256` of the set actually read,
`--out` persists the bundle, and the committed bundle
(`doc/progress/data/2026-08-05-fleet-divergence-2026-08-04.json`) is what this
document cites. The record-bound tests read **the bundle**, not the DB; a
separate live test asserts the DB still reproduces it and **fails** — does not
skip, does not silently re-derive — if it does not. A record that quietly
recomputes itself is not a record.

## The baseline guard caught something the same day it landed

Running the probe for **2026-08-05** refuses:

> `prod run 2026-08-05-live-622373ac scored 0 name(s) on 2026-08-05`

`[VERIFIED — this session]`. Under the pre-review code that would have been
reported as *"5 of 5 shadow lanes produced no separating evidence"* — a fleet
conclusion drawn from a prod run that scored nothing. That is not investigated
here; it is noted as an observation the guard surfaced, and it belongs to
GOAL-5, not to this measurement.

## Next

The honest next step is **not** a conclusion about `blend_mom` — it is more
dates. The probe is read-only and unscheduled; wiring it into the daily fleet
report is a separate, reviewable step.

Suites: 24 tests — all three no-evidence states kept distinct, the
absent/empty/too-few prod-baseline refusals, the CLI exiting 3 instead of
printing a fleet conclusion, the score-set hash being order-independent but
value-sensitive, the ratio-with-its-denominator rule, the no-cutoff case, the
bundle-bound record, and the live-still-reproduces-the-bundle check ·
full suite green.
