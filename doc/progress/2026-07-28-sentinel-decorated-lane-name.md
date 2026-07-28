# Sentinel: accept decorated config-lane names in the health-record sink

Date: 2026-07-28
PR: ops/sentinel-decorated-lane-name

## What

`rq104_shadow_scorer_sentinel` matched health records by exact
`shadow_name == "hf_patchtst"`. The 2026-07 clf promotion renamed the
config lane to `hf_patchtst_pt07_strict_seed44_previous_primary`, so the
primary sink claimed zero records and the sentinel silently demoted itself
to the DB fallback (observed in the 2026-07-28 kickstart demo: health JSONL
present, verdict sourced `shadow_runs_db_fallback`).

Fix: `_matches_shadow_lane()` — exact key or `SHADOW_NAME_<suffix>`
decorated form; a differently-keyed lane (`topdecile_clf_blend_leg`) never
matches. Sink filter now uses it.

## Why it matters

The fallback cannot read `actionable`/`status`, so a by-design non-load or
an expected-skip day would page (or worse, a fault day could pass on
derived thresholds). GOAL-1 AC3's designed signal path is the structured
record; the rename had quietly disconnected it.

## Evidence

- New tests: decorated-name records silence a feed-dark DB (primary sink
  claims them); foreign-lane records do not; prefix requires the `_`
  separator. `tests/test_rq104_shadow_scorer_sentinel.py` 50/50 pass.

## Follow-up (queued, not in this PR)

- Multi-lane sentinel: the config now carries two shadow lanes
  (`topdecile_clf_blend_leg` + demoted patchtst); today only the patchtst
  key is patrolled. Per-lane verdicts need a design pass (the DB fallback
  is meaningless for the clf lane, which logs to MLflow, not the shadow
  runs DB).
