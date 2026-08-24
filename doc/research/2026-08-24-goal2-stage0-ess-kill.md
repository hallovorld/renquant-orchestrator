# GOAL-2 Stage 0: the ESS measurement — and the kill it triggers

STATUS: Stage 0 of the approved orch#1027 design, delivered. **The frozen kill
condition fires: Stage 1 is NOT run.** That is the deliverable the design
specified for this outcome — "record the kill as the finding".

## The measurement

ESS = greedy maximal set of observation dates spaced ≥ h trading days apart
(non-overlapping label windows), computed over dates that have BOTH a
multi-leg score cross-section AND a realized forward label.

| panel | h=5 | h=10 | h=20 | **h=60 (the estimand)** |
|---|---:|---:|---:|---:|
| **meta-panel** (3-leg core ∩ labeled) | 2 | 1 | 0 | **0** |
| reference ceiling: single-scorer LIVE history | 15 | 8 | 4 | **1** |

Kill bar (frozen in the design, not a knob): **n_eff ≥ 12 at h=60**.

- The 3-leg core (`blend ∩ blend_mom ∩ blend_rb_mom`) shares **14 dates**,
  2026-08-04..2026-08-21 — **zero** of which have a realized `fwd_60d`. The
  first multi-leg row earns its 60d label ~**2026-10-27**.
- The reference row is the CEILING for the re-score-history option, and it is
  computed on **live, strategy-named runs only** `[REVISED 2026-08-24, codex
  review]`. The first revision counted every `candidate_scores` row with a
  panel score, which pulled in **560 SIM dates** alongside the 90 live ones and
  reported the result as a 104 re-score history — it was not one. Provenance
  now recorded in the artifact: **74 dates selected, 560 excluded**, predicate
  `run_type='live' AND strategy NOT NULL/''`, with the selected `(run_date,
  run_id)` rows digested so the number is reproducible against a DB that grows
  later.

  The corrected ceiling is **1**, not 11: only **24** live dates carry a
  realized `fwd_60d` at all, and they compress to a single non-overlapping
  60d observation. The direction was always conservative — filtering can only
  remove rows, so the audited ceiling could only fall — but the magnitude
  matters for how the result reads: "11 vs 12" invites "one more month fixes
  it", and that was never true.

## Why this is the finding, not a failure

At h=60 with non-overlapping windows, a panel accrues **~4 independent
observations per year**. That single number is the whole story:

| unlock path | what it yields | when |
|---|---|---|
| (a) wait — shadow fleet keeps accruing | n_eff=12 at h=60 | **~2029** — not a plan |
| (b) re-score live history per leg | ceiling **1** < 12 | dead on arrival at h=60 — and by an order of magnitude, not by one |
| (c) extend the corpus backward (pre-2024) then re-score | ~4/yr × extra years | real, but it inherits the survivor-triage problem already catalogued in the universe-extension feasibility note |
| (d) re-design at a shorter horizon | h=20 live reference n_eff=**4** (was reported 34 pre-filter) | **NOT the easy exit it looked like.** Still a NEW estimand needing its own design and review — and on audited data it is now also below the bar, so it does not rescue anything by itself |

The honest ordering: (d) is the only path that makes a conditional-weighting
test feasible on data that exists, and it must go back through design review
because the 60d horizon was a deliberate, operator-visible choice (the model's
own label horizon). Nothing here licenses quietly re-running the same test at
h=20 until it passes — that is the multiple-comparisons failure the kill bar
exists to prevent.

## What Stage 0 did NOT do, on purpose

No conditional-skill table, no per-leg IC by state tercile, no model of any
kind. The design's order is ESS first precisely so that no screen result
exists to tempt a rule into being frozen around it. With n_eff=0, any such
table would be noise wearing a table's clothes.

## Files

`data/2026-08-24-goal2-stage0/`: `stage0_ess.py` (fail-closed on missing core
lanes; kill bar and lane list are constants in the script, mirroring the
frozen design), `stage0_ess.json` (full lane coverage + per-horizon ESS +
verdict), `run.out`.
