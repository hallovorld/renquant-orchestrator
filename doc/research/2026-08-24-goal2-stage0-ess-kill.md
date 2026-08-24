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
| reference ceiling: single-scorer history | 132 | 67 | 34 | **11** |

Kill bar (frozen in the design, not a knob): **n_eff ≥ 12 at h=60**.

- The 3-leg core (`blend ∩ blend_mom ∩ blend_rb_mom`) shares **14 dates**,
  2026-08-04..2026-08-21 — **zero** of which have a realized `fwd_60d`. The
  first multi-leg row earns its 60d label ~**2026-10-27**.
- The reference row is the CEILING for the re-score-history option: the full
  2024-01..2026-05 labeled corpus (584 dates), if every leg were re-scored
  over all of it, still compresses to **11** non-overlapping 60d observations
  — below the bar before spending a dollar of compute.

## Why this is the finding, not a failure

At h=60 with non-overlapping windows, a panel accrues **~4 independent
observations per year**. That single number is the whole story:

| unlock path | what it yields | when |
|---|---|---|
| (a) wait — shadow fleet keeps accruing | n_eff=12 at h=60 | **~2029** — not a plan |
| (b) re-score 2024+ history per leg | ceiling 11 < 12 | dead on arrival at h=60 |
| (c) extend the corpus backward (pre-2024) then re-score | ~4/yr × extra years | real, but it inherits the survivor-triage problem already catalogued in the universe-extension feasibility note |
| (d) re-design at a shorter horizon | h=20 reference n_eff=34 | **viable — but it is a NEW estimand**, not this design; it needs its own design decision and review |

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
