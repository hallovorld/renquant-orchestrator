# 2026-08-05 — GOAL-3: the twin guard exists in one repo, and its subject is nearly empty in the others

## The question I started with, and the better one underneath it

`renquant-pipeline` has a twin-implementation guard (`tools/twin_pairs.py` +
`twin_pairs.json` + a one-sided-repin exception file). **No other repo has one**
`[VERIFIED — 2026-08-05, file presence across all seven]`. The obvious next step
is "install it everywhere". The prior question is: **would it see anything?**

The guard's SUBJECT is `__all__`. Measured `[VERIFIED — this session,
`scripts/goal3_twin_surface_audit.py`]`:

| repo | `__all__` | module-level public defs | subject coverage | duplicate names | visible to an `__all__` guard |
|---|---|---|---|---|---|
| renquant-pipeline | 56 | 836 | 6.7% | 24 | **20** |
| renquant-orchestrator | **3** | 949 | **0.3%** | **42** | **0** |
| renquant-backtesting | 2 | 348 | 0.6% | 34 | 0 |
| renquant-base-data | 7 | 261 | 2.7% | 30 | 0 |
| renquant-execution | 125 | 132 | 94.7% | 1 | 0 |
| renquant-common | 53 | 152 | 34.9% | 0 | 0 |
| renquant-strategy-104 | 2 | 13 | 15.4% | 0 | 0 |

**Installing the pipeline guard in the orchestrator today would report clean
forever** — not because the repo is clean, but because its subject covers 3 of
949 definitions. That is the registry's own defect class (a check whose subject
is not the object you assume), one level up from the sites it records.

## What is actually there

The orchestrator's 42 duplicate-definition names are **not** `main()` noise.
Verified examples `[VERIFIED — body digests read this session]`:

- `BuildAlpha158PanelTask` — `retrain_alpha158_fund.py` (13 L) vs
  `retrain_alpha158_linear.py` (15 L), **different bodies**
- `RefitCalibratorTask` — `retrain_alpha158_fund.py` (18 L) vs
  `retrain_patchtst.py` (23 L), **different bodies**
- `RetrainJob` — **four** files
- `EmitJob` — `build_patchtst_wf_manifest.py` vs `build_wf_manifest.py`,
  **identical digest** `21f0b25f6e90` (a copy, i.e. a divergence risk rather
  than a which-one-runs risk)

Tasks and Jobs in retrain and manifest chains — exactly the class of object the
twin problem is about.

## What this does NOT claim

**A duplicate is a candidate, not a verdict.** Same-name-in-two-files is where
you start reading, not a finding: confirming a twin means reading both bodies
and deciding which one the callers reach. This produces the work list and says
so in its own output. No count here should be quoted as "42 twins".

## The near-miss worth recording

My first version of this measurement parsed `__all__` with `ast.literal_eval`
and reported **zero duplicates in every repo, including pipeline**. It looked
like a clean bill of health. The positive control caught it: pipeline is *known*
to have ~19, so a method that finds none there is broken — `__all__` is built
dynamically in that package, `literal_eval` failed, and the `if not names:
continue` skipped the repo silently. **A silent skip is a vacuous pass.** The
tool now imports the package and reads `__all__` off the module, the way the
pipeline guard does, and the live-corpus test fails if this repo's numbers move.

## NEXT

1. Decide per repo whether the answer is "widen `__all__`" or "scope the guard
   to something other than `__all__`" — they are different fixes and this
   measurement does not choose between them.
2. Read the orchestrator's top candidates (the retrain Tasks first — they sit on
   the model-production path) and record which ones are real twins.

Suites: 10 new tests · 5634 passed, 2 skipped repo-wide.
