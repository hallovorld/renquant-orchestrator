# GOAL-4: the lane built to shadow the z-blend became prod, and nothing said so

STATUS:   delivered.
WHAT:     ships `ops/renquant104/shadow_lane_control_probe.py` + 13 tests, which compares each
          shadow lane's score-affecting config against prod; live run finds
          `alpaca_shadow_blend_mom` differs from prod in 0 of 21 score-affecting keys (a byte-level
          duplicate), exit 1.
WHY/DIR:  GOAL-4 (multi-model ensemble) — `_mom` existed to shadow the momentum z-blend; on
          2026-08-04 the z-blend was promoted to prod (operator override, 'z-blend进prod') and
          nothing retired or re-pointed its shadow, so a lane that agrees with prod by construction
          has been scoring and reporting healthy daily. Of 5 fleet lanes, only 2 carry separating
          information.
EVIDENCE: component-by-component diff of `strategy_config.shadow_blend_momentum.json` vs
          `strategy_config.json` shows identical `artifact_path`, `expected_content_sha256`, and
          `expected_config_fingerprint` on both components; the probe's live run reports exactly 1
          copy-of-prod lane, matching this manual diff. `[VERIFIED — this session, config diff +
          probe run this session]`
          artifact:      `strategy_config.shadow_blend_momentum.json` vs `strategy_config.json`, both read this session
          prod or exp:   prod — both configs are live-serving (one primary, one shadow)
          existing data: orch#856's ρ=0.9998 fleet-divergence measurement, now explained by this config diff
          best-known?:   n/a — this is a config-identity check, not a model-variant skill comparison
          scope:         "this is a live shadow lane's own config, prod, vs. the live primary scorer — no model is ranked, the lane is shown to be a duplicate"
NEXT:     `_mom` needs a decision — retire or re-point at a non-prod candidate (a
          `renquant-strategy-104` config change, repo boundary, not actioned here); wire this probe
          into the daily surface so the next promotion that orphans its own shadow is caught same-day.

**Date:** 2026-08-05
**Lane:** GOAL-4 (multi-model ensemble)

## Bottom line

`alpaca_shadow_blend_mom` scored ρ=0.9998 against prod with 10/10 top-k overlap
(orch#856). I left "inspect `_mom`'s inputs" as the follow-up. Done, and the
answer is complete `[VERIFIED — this session]`:

> **`strategy_config.shadow_blend_momentum.json` differs from prod in ZERO of 21
> score-affecting keys.**

Component by component, against `strategy_config.json`:

| | prod | `_mom` | |
|---|---|---|---|
| comp0 `artifact_path` | `artifacts/prod/panel-ltr.alpha158_fund.json` | same | ✔ |
| comp0 `expected_content_sha256` | `sha256:6461b827ab2339a8` | same | ✔ |
| comp0 `expected_config_fingerprint` | `sha256:f8fb2259b2bf1537` | same | ✔ |
| comp1 `kind` | `momentum_residual` | same | ✔ |
| comp1 `artifact_path` | `momentum_artifact_ledger.jsonl` | same | ✔ |
| comp1 `expected_config_fingerprint` | `momentum-v0-fd65161a20b29314` | same | ✔ |

`conviction_gate` and `global_calibration` are identical once `_`-prefixed
commentary is excluded. The **only** differences are `shadow_experiment` and
`shadow_models` — the shadow legs a lane *reports* alongside its decision, which
do not enter its own score.

## This is a promotion, not a bug

Prod's own config records the cause, in the operator's words:

> `_buy_floor_reason`: "OPERATOR OVERRIDE 2026-08-04 (verbatim: 'z-blend进prod' /
> choice '整本切换')"

`_mom` existed to shadow the momentum z-blend. **On 2026-08-04 the z-blend became
prod.** The shadow did not fail — it was made redundant by the thing it was
shadowing being promoted, and no step in that promotion retired or re-pointed it.

So a lane that agrees with prod **by construction** has been running daily,
scoring, and reporting healthy. It cannot inform an ensemble and cannot falsify
prod. Only a rank correlation reveals it, and only if someone thinks to look.

## Fleet standing, corrected

| lane | status |
|---|---|
| `alpaca_shadow_blend` | control (ρ≈0.929) |
| `alpaca_shadow_blend_rb_mom` | control (ρ≈0.923) |
| **`alpaca_shadow_blend_mom`** | **COPY OF PROD — 0/21 keys differ** |
| `alpaca_shadow_blend_mom_fast` | config differs, but **never emitted a score** (orch#845) |
| `alpaca_shadow_blend_rb_fast` | config differs, but **never emitted a score** (orch#845) |

**Of five fleet lanes, two carry separating information.** One is a duplicate of
prod; two have never produced evidence. That is the concrete state of the
"multi-model ensemble" premise.

## What this does NOT establish

**Not that the two surviving lanes are good.** Differing config is *necessary*
for a lane to carry information, not *sufficient* — a lane can differ from prod
and still be worthless. This measures only that a lane is not prod. The probe
carries that refusal as a field and a test pins it.

It also does **not** say the promotion was wrong. The z-blend going to prod may
be entirely correct; what is missing is the step that should have retired or
re-pointed its shadow.

## Delivered

`ops/renquant104/shadow_lane_control_probe.py` + 13 tests. Compares the
score-affecting subset of `ranking.panel_scoring` per lane against prod.

Two details worth a reviewer's eye:

- `_`-prefixed commentary is stripped **recursively**. An earlier draft stripped
  only the top level, so two blocks differing solely in a nested `_reason` string
  would have been reported as a genuine control — **a lane declared informative
  on the strength of a comment.** Both that case and its anti-vacuity twin (a
  real nested change must still be caught) are pinned by test.
- Missing/unparseable prod **refuses** rather than reporting every lane as a
  control, and an unreadable lane is its own state, never a control.

Live: **1 copy of prod**, exit 1.

## Next

1. `_mom` needs a decision: retire it, or re-point it at a candidate that is not
   prod. Either is a config change in `renquant-strategy-104` (repo boundary) —
   not actioned here.
2. Wire this probe into the daily surface so the **next** promotion that orphans
   its own shadow is caught the same day rather than five rounds later by a rank
   correlation.
