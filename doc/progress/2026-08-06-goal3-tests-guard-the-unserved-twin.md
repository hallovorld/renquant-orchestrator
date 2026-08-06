# GOAL-3: the test suite's centre of gravity is the twin production does not run

STATUS:   delivered (docs-only finding; resolves orch#861's open question, corrected twice on
          re-measurement).
WHAT:     shows `kernel/panel_pipeline/job_panel_scoring.py` (4350 lines, 0 production import
          sites even through the module's PEP 562 lazy `__getattr__` map) is exercised by 28 test
          files, while the twin that production actually imports (`panel_scoring.py`, 1005 lines,
          imported at `pp_inference.py:334`) is exercised by only 5.
WHY/DIR:  GOAL-3 (architecture compliance audit) — names the mechanism behind a past incident
          (`tests/test_panel_scoring_twin_domain_lockstep.py`, 2026-07-29: a #219 safety guard
          landed only in the unserved twin) as structural, not a one-off: fixes naturally land in
          the module the tests import, which is not the module production runs.
EVIDENCE: re-measured via the lazy `__getattr__` map (not a raw grep, which orch#861 used and
          which cannot find a counterexample): 0 production importers confirmed for
          `job_panel_scoring.py`; test-file count corrected from an initial 37 (string match,
          including 9 comment-only mentions) to 28 (verified imports/patches).
          `[VERIFIED — this session, re-scanned this session]`
NEXT:     pipeline owners (repo boundary) must decide which twin is canonical — if
          `job_panel_scoring` is canonical, `pp_inference.py:334` is wired to the wrong module; if
          `panel_scoring.py` is canonical, the 4350 lines + 28 tests guard something that never
          runs and the lockstep test is the only thing keeping the two aligned.

**Date:** 2026-08-06
**Lane:** GOAL-3 (architecture compliance audit)

## Bottom line

orch#861 left one question open: *`kernel/panel_pipeline/job_panel_scoring.py` is
4350 lines, nothing imports it by name, and it was maintained on 08-03 — dead
code, or a canonical implementation the runtime silently stopped using?*

Answer: **neither, and the real state is worse than both** `[VERIFIED — this session]`.

| | kernel twin `job_panel_scoring.py` | served twin `panel_scoring.py` |
|---|---:|---:|
| lines | **4350** | 1005 |
| last commit (pinned repo) | **2026-08-03** | 2026-08-01 |
| **production import sites** | **0** | ≥1 (`kernel/pipeline/pp_inference.py:334`) |
| **test files that import/patch it** | **28** | 5 |

**28 test files exercise a module with zero production importers.** The suite's
investment is concentrated on the copy the runtime does not execute, while the
copy that decides live trades is imported by 5.

## Correcting my own method twice

**1. #861's probe looked for the wrong token.** I grepped for the string
`job_panel_scoring` and concluded "every hit is a docstring". But
`panel_pipeline/__init__.py` implements a **PEP 562 lazy `__getattr__` map**:

```python
"PanelScoringJob":        (".job_panel_scoring", "PanelScoringJob"),
"LoadScorerTask":         (".job_panel_scoring", "LoadScorerTask"),
"BuildFeatureMatrixTask": (".job_panel_scoring", "BuildFeatureMatrixTask"),
"ApplyScoresTask":        (".job_panel_scoring", "ApplyScoresTask"),
"VetoWeakBuysTask":       (".job_panel_scoring", "VetoWeakBuysTask"),
```

So an importer reaches that module **without the string ever appearing in their
source**. Re-measured through the lazy map: still **0 production importers** — the
conclusion survived, but it had been resting on a probe that could not have found
a counterexample.

**2. My first test count was 37; the verified number is 28.** The 37 counted any
file containing the string. Nine only mention it in a comment. This is the same
error as (1), one round later, in the direction that flattered the finding.

## Why this is the mechanism behind a past incident, not just an oddity

`tests/test_panel_scoring_twin_domain_lockstep.py` exists, written 2026-07-29, and
its docstring records exactly what this arrangement produces:

> the unit guard added by #219 landed in the kernel implementation only. The
> top-level public export resolved to the OTHER one … **So the documented public
> symbol was the one WITHOUT the safety guard.**

That is this finding's consequence, already realised once. **When a fix is
written, the natural place to put it is the module the tests import — and that is
not the module production runs.**

The lockstep test is real and valuable, but its scope is narrow: it pins the
`RANK_SCORE_DOMAIN_*` constants and asserts `_rank_score_domain` appears in both
`VetoWeakBuysTask` sources. It does **not** guarantee the 4350-line and
1005-line implementations agree behaviourally, and nothing extends it to the
other four lazily-mapped symbols.

## What this does NOT establish

- **Not that the served twin is under-tested in absolute terms** — 5 files may be
  adequate for 1005 lines. The finding is the **asymmetry** and its direction.
- **Not that the two implementations currently disagree** anywhere beyond the
  #219 guard already recorded. I compared import counts, not behaviour.
- **Not that `job_panel_scoring` should be deleted.** It may be the intended
  canonical implementation with the runtime wired wrongly — which would invert
  the fix entirely. That decision is `renquant-pipeline`'s (repo boundary).

## Next

The discriminating question for the pipeline owners: **which twin is meant to be
canonical?** Every remedy follows from it, and they are opposite:

- if `job_panel_scoring` is canonical → the runtime is wired to the wrong module
  and `pp_inference.py:334` is the bug;
- if `panel_scoring.py` is canonical → 4350 lines and 28 test files are guarding
  something that never runs, and the lockstep test is the only thing standing
  between the two.
