# GOAL-4: the fleet is a designed factorial, and one whole factor level has never produced a datum

STATUS:   delivered (docs-only finding).
WHAT:     shows the shadow fleet is a 2-factor (clf leg x momentum leg) design in which both cells
          at the `fast` momentum level (`shadow_blend_momentum_fast`, `shadow_blend_rb_fast`) have
          never emitted a score, and a third cell (`shadow_blend_momentum`) duplicates PROD.
WHY/DIR:  GOAL-4 asks whether ensembling is worth pursuing; of six nominal cells, only two are live,
          non-duplicate controls and zero have measured forward skill — reframes orch#845 from
          "two lanes broken" to "the fast-momentum factor has no data".
EVIDENCE: reading every lane's `panel_scoring.components` shows both fast-momentum cells point at
          `artifacts/momentum_fast/`, which does not exist, and carry no `expected_config_fingerprint`
          while every populated component does; orch#856 confirms `RAN_AND_SCORED_NOTHING` on 2/2
          dates each; orch#863 confirms `shadow_blend_momentum` is byte-identical to PROD in all 21
          score-affecting keys. `[VERIFIED — this session, panel_scoring.components + orch#856 +
          orch#863 read this session]`
          artifact:      every shadow lane's `panel_scoring.components` config, read live this session
          prod or exp:   prod — these are the live shadow fleet's own configs
          existing data: orch#856 (serving-side RAN_AND_SCORED_NOTHING) + orch#863 (byte-identical config diff)
          best-known?:   n/a — this is a fleet-design audit, not a model-variant skill comparison
          scope:         "this is the shadow fleet's own config/serving state, prod, vs. its own designed factorial — no forward-skill claim is made"
NEXT:     orch#845 is the highest-leverage GOAL-4 item under this reframing; retire or re-point
          `shadow_blend_momentum` (orch#863); skill stays unmeasurable until forward returns mature.

**Date:** 2026-08-06
**Lane:** GOAL-4 (multi-model ensemble)

## Bottom line

Reading every lane's `panel_scoring.components` shows the fleet is not an
accumulation of lanes — it is a **factorial over two factors** `[VERIFIED — this session]`:

- **clf leg** — `artifacts/shadow/panel-clf.top-decile.fwd60.json` — present / absent
- **momentum leg** — `momentum/` (slow) / `momentum_fast/` (fast) / absent

| lane | clf leg | momentum leg | cell |
|---|:--:|---|---|
| **PROD** | — | slow | baseline |
| `shadow_blend` | ✓ | — | clf only |
| `shadow_blend_momentum` | — | slow | **duplicate of PROD** |
| `shadow_blend_momentum_fast` | — | **fast** | **no data — ever** |
| `shadow_blend_rb_mom` | ✓ | slow | clf + slow |
| `shadow_blend_rb_fast` | ✓ | **fast** | **no data — ever** |

## The finding

**Both cells at the `fast` level of the momentum factor are empty.** Neither
`shadow_blend_momentum_fast` nor `shadow_blend_rb_fast` has ever emitted a score
(orch#845, confirmed from the serving side in orch#856: `RAN_AND_SCORED_NOTHING`
on 2 of 2 dates each). Both point at `artifacts/momentum_fast/`, which does not
exist — and consistently, both carry **no `expected_config_fingerprint`** on that
component, while every populated component carries one.

So the fleet cannot answer **fast vs slow momentum** — an entire experimental
factor — because that factor level has never been populated. This is a sharper
statement than orch#856's "2 of 5 lanes carry separating information": those two
dead lanes are not two lanes short, they are **one whole comparison short**.

And a third cell is a duplicate: `shadow_blend_momentum` is byte-identical to
PROD in all 21 score-affecting keys (orch#863), because the z-blend it was built
to shadow was promoted into prod on 2026-08-04.

**Of six nominal cells: one is the baseline, one duplicates it, two have never
produced data, and two are live controls** (`shadow_blend`, `rb_mom`).

## What this does NOT establish

- **Not that the design is wrong.** A clf × momentum factorial is a reasonable
  way to ask which leg carries the edge. The finding is that it is **not
  currently running as designed**.
- **Not that the two live controls are skilled.** They differ from prod
  (ρ≈0.929 and ≈0.923), which is necessary for a component and not sufficient.
  No forward-return skill has been measured for any lane, and with a 60-day
  horizon and 7 dates of data it cannot be yet.
- **Not that the missing producer is hard to build.** I have not looked at what
  producing `momentum_fast/` would require; orch#845 tracks that and remains
  open.

## Why this matters for the ensemble premise

The GOAL-4 anchor asks whether ensembling is worth pursuing. The measured state
of the evidence base is now specific:

| | |
|---|---|
| lanes that duplicate prod | 1 |
| lanes with no producer | 2 |
| live controls | 2 |
| lanes with **measured forward skill** | **0** |
| admission path that can rank two candidates | **none** (orch#862, orch#868) |

An ensemble needs components that are different **and** individually skilled. The
fleet currently measures only the first, for two of six cells, against a baseline
whose own artifacts carry no content identity.

## Next

1. **orch#845** is the highest-leverage GOAL-4 item, and this reframes it: it is
   not "two lanes are broken", it is "the fast-momentum factor has no data".
2. Retire or re-point `shadow_blend_momentum` (orch#863) so the duplicate cell
   stops consuming a scheduled slot while reporting healthy.
3. Skill remains unmeasurable until forward returns mature. Nothing in this round
   moves that, and no probe will.
