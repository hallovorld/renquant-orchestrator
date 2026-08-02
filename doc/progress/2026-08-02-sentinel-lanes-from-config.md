# The shadow-scorer sentinel derives its patrol list from the strategy config (orch#758)

STATUS: complete. `watched_lanes()` no longer restates the lane set; it reads
`ranking.panel_scoring.shadow_models` from the pinned strategy config. Batch
prerequisite for `renquant-strategy-104#77` — no live surface is touched by this
PR itself.

WHAT: `lane_names_from_config()` returns `(names, finding)` from the pinned
config; `watched_lanes()` builds a `WatchedLane` per declared name. Where each
lane's evidence LIVES stays in `_lane_evidence()` — the config declares which
lanes exist, never where their health records are written. A declared lane the
table has not been taught is still patrolled, with **no** fallback source.
An unreadable or lane-less config keeps the last-known set **and** returns a
finding.

WHY/DIR: orch#758, found during review of strategy-104#77. The hand-maintained
pair drifted in **both directions at once**:

| direction | lane | before |
|---|---|---|
| retire | `hf_patchtst` | still patrolled after strategy-104#75 removed it → a daily FEED_DARK on a lane retired on purpose |
| add | `momentum_residual_v0_shadow` | declared by strategy-104#77, patrolled by nobody → a data-collection lane free to die unnoticed |

One list, two opposite drifts, because the list was a copy of something that
changes elsewhere. Deriving it closes both — and closes the next one nobody has
thought of yet, which is the part a two-lane patch would not have.

EVIDENCE:

| claim | value | provenance |
|---|---|---|
| module tests | 83 passed (8 new) | [VERIFIED — `pytest -q tests/test_rq104_shadow_scorer_sentinel.py`] |
| the 8 derivation tests are load-bearing | all 8 fail against the pre-fix sentinel | [VERIFIED — `git show HEAD:…` over the fix, re-run] |
| the real pinned config drives it | derives `['hf_patchtst_pt07_strict_seed44_previous_primary', 'topdecile_clf_blend_leg']`, finding `None` | [VERIFIED — `lane_names_from_config()` against the pinned checkout] |

That last row is the behaviour that matters: the pinned config still carries the
decorated patchtst lane because the pin has not advanced past strategy-104#75.
When it does, the lane leaves the patrol **by itself** — no follow-up edit, which
is the failure mode this replaces.

## Two defects I introduced and the tests caught

1. **Early binding.** My first version made the evidence table a module-level
   dict, freezing `SHADOW_DB` / `MLRUNS_DIR` at import — the exact defect
   `watched_lanes`'s own docstring warns about ("resolved at call time, so tests
   and operators can retarget paths"). Seven existing tests went red immediately.
   It is a function now.
2. **The decorated-name lookup.** Config lanes decorate the served key
   (`hf_patchtst_pt07_…`); the evidence table is keyed by the undecorated name.
   Without prefix resolution the served lane silently loses its DB fallback —
   pinned by `test_a_DECORATED_config_name_still_finds_its_evidence`.

## The fail-closed choice, stated because it is the load-bearing one

An unreadable config could reasonably yield an empty patrol. It must not: an
empty patrol is **indistinguishable from a healthy quiet run**, which is the
silent death this sentinel exists to prevent. So it falls back to the last-known
set and reports a finding — loud and still watching, never quiet and blind.

NEXT: this unblocks one of the three gates orch#759's review names
(`renquant-pipeline#254` and `RenQuant#550` remain open issues with no PR).
The slice-5 pin advance still waits on all three plus the operator's grant.
