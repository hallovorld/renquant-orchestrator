# Shadow staleness gate vs label horizon — design memo (operator decision)

Date: 2026-07-28
Status: DECISION NEEDED (two options, recommendation included)
Owner: claude · Reviewer: codex

## The problem: a freshness gate no fwd60 model can ever pass

The shadow health record (renquant-pipeline#211) and the shadow-scorer
sentinel judge actionability by `staleness_days` — CALENDAR days, computed
as `(run_date - cutoff).days` (`shadow_health.py:324`) — measured from
`effective_train_cutoff_date`, threshold 28 calendar days
(`DEFAULT_SHADOW_HEALTH_MAX_STALENESS_DAYS`). But a model labeled with a
60-TRADING-day forward return (`fwd_60d_excess`; horizon inferred by
`infer_label_lookahead_days`, `renquant_model_gbdt/panel_data.py:57-60`;
the label itself is a `.groupby("ticker").shift(-60)` over one row per
trading day — `renquant_model_patchtst/hf_trainer.py:392-395`) CANNOT have
a training cutoff closer than that horizon (converted trading->calendar)
behind today — the label for the last training row must have fully
resolved before it can be included.

Live evidence (both flags today are this artifact of the metric, not a
process failure):

| model | trained | effective cutoff | staleness flag | freshest possible |
|---|---|---|---|---|
| topdecile_clf (fwd60) | 2026-07-27 | 2026-04-28 | `stale_91d_limit_28d` | ~82–91d by construction |
| fresh PatchTST fold 2026-03-02 (fwd60) | 2026-07-28 | 2025-12-05 | (would flag) | same bound |

A model retrained THIS MORNING flags stale on arrival. The gate conflates
two different axes:

- **training recency** (`trained_date` age) — what the freshness
  governance policy (RFC #210, "no model >28 days") actually governs;
  fully controllable by retrain cadence.
- **data-cutoff lag** (`effective_train_cutoff_date` age, CALENDAR days) —
  bounded below by the label horizon ALONE, converted trading->calendar
  (NOT `horizon + embargo` as a separate additive term — see the
  correction in Option A below); for fwd60 (60 trading days) that floor is
  ~82–91 calendar days (`pd.offsets.BDay(60)` from a given date, ±
  real-world holiday variance — matches the two observed rows in the
  table above); NOT controllable; only its EXCESS over that bound signals
  a problem (stopped retraining, broken panel refresh).

## Option A (recommended): two-axis check, horizon-aware bound

Health record + sentinel gate on BOTH:
1. `trained_age = today − trained_date` ≤ 28 calendar days (aligns with
   RFC #210 / `DEFAULT_SHADOW_HEALTH_MAX_STALENESS_DAYS`).
2. `cutoff_lag = today − effective_train_cutoff_date` (calendar days) ≤
   `label_horizon_calendar + slack`, where:
   - `label_horizon_calendar` = the artifact's own stamped `lookahead_days`
     (TRADING days — `infer_label_lookahead_days`,
     `renquant_model_gbdt/panel_data.py:57-60`; read per-artifact, never
     hardcoded — the precedent already shipped in
     `doc/progress/2026-07-02-per-recipe-freshness-horizon.md`: fail
     closed to `TIER_UNKNOWN` if the stamped value is missing/invalid,
     don't guess a default), converted trading->calendar via
     `pd.offsets.BDay(N)` (same convention as
     `kernel/walk_forward_splits.py:95`).
   - **Correction from the first draft**: there is no separate "embargo"
     term to add on top of the horizon. This codebase's own splitter sets
     its embargo window EQUAL to the label horizon, not additive
     (`kernel/walk_forward_splits.py:71,76`: default `embargo_days=60`,
     "matching fwd_60d_excess label horizon"). Summing horizon + embargo
     in the first draft double-counted the same quantity under two names.
   - `slack` = an explicit operator-chosen buffer (NOT sourced from any
     existing constant) to absorb calendar/holiday variance and give the
     retrain cadence margin. A candidate default is the same 28 calendar
     days used for axis 1, but that is a proposal here, not a citation.
   - Worked example (ILLUSTRATIVE ONLY, not an executable gate value):
     fwd60 -> 60 trading days ≈ 84 calendar days via `pd.offsets.BDay(60)`
     (± holiday variance — the ~82–91d actually observed in the table
     above) + 28d slack ≈ 112d. This number is not authoritative until an
     implementation PR pins (a) the per-artifact stamped field it reads,
     (b) the trading->calendar conversion call site, and (c) the slack
     value as a reviewed config default — this memo fixes the SHAPE of
     the check, not the constant.

Record carries both raw numbers (`trained_age`, `cutoff_lag`) plus the
per-artifact `label_horizon` used to derive the bound; `actionable=false`
only when either axis breaches. The 622-calendar-day legacy lane still
flags under any plausible slack (622 ≫ ~112) — true positives preserved
regardless of the exact slack chosen. Requires: producer change in
renquant-pipeline (read `lookahead_days` off the artifact per the
`doc/progress/2026-07-02-...` precedent — fail closed, do not hardcode
60), sentinel threshold via the existing env, one slack config field per
shadow lane. Recipe keys already carry `effective_train_cutoff_date`, so
no schema change — only the verdict rule.

## Option B (minimal): switch the existing single check to trained_date

Keep one axis: `trained_date` age ≤ 28d. One-line producer change, no new
config. Loses the cutoff-lag tripwire — a broken panel refresh that
freezes `effective_train_cutoff_date` while retrains keep succeeding
would go undetected (this is the fund-freshness bug class we have
actually had). Cheaper but blinder.

## Recommendation

Option A. The two axes fail for different root causes we have BOTH
experienced (stale model = per-ticker tournament frozen since April;
frozen cutoff = fund-freshness serving-axis clip). One number cannot
watch both. Cost is one reviewed pipeline PR + a sentinel env default.

Until decided, the `stale_91d` flag on the clf lane stays — correctly
reported, known benign, documented here.
