# rq105: batch score vector from the blend composite (operator directive)

## STATUS
delivered (repo-side; deploy = coordinator syncs the pinned run checkout)

## WHAT
`export_batch_scores.py` gains a score source switch (`RQ105_SCORE_SOURCE`,
`prod` default / `blend`): `blend` sources the frozen class-A vector from
`runs.alpaca_shadow_blend.db` — the isolated read-only lane daily_104.sh
Step 5 populates by running the FULL funnel with the pinned
`strategy_config.shadow_blend.json` profile (pipeline#218 `kind="blend"`,
z(prod panel-ltr) + z(clf top-decile), both component pins fail-closed in
the pipeline). The launchd wrapper now defaults the switch to `blend`
(ONE-LINE REVERT: flip that line back to `prod`, or set
`RQ105_SCORE_SOURCE=prod` in the env). Blend mode adds two fail-closed
guards on top of every existing selection/health/fingerprint gate: the
source run's `broker_mode` must be `alpaca_shadow_blend` (a mispointed DB
is the new failure class) and its `artifact_hashes` must carry BOTH
resolved blend component hashes. Every export (both modes) now stamps a
`scorer_identity` block into the meta (score_source, broker_mode,
config_hash, panel + blend-component artifact sha256s,
model_content_sha256, training_cutoff) so each shadow-realtime record is
attributable to the exact model that produced its frozen vector.
`rq105_status.py` resolves the same env so the dashboard reports the DB
the exporter actually reads, and surfaces `score_source` from the meta.

## WHY/DIR
2026-07-28 operator directive: "105 直接换成 blend 模型, go go go".
Sourcing from the Step-5 lane DB — instead of re-scoring here — keeps the
blend identity pins single-sourced in the pinned strategy profile and this
repo free of scorer internals (repo boundary: orchestrator reads committed
run state, never scores).

## SAFETY MAP (STEP 0)
No rq105 surface that consumes the exported vector places or routes
orders. The vector's ONLY consumer is `run_shadow_serving.sh` →
`shadow_realtime_serving` (pure score collector, appends
`shadow_realtime_serving.jsonl`; no broker submit path). The session
scheduler's class-A input reads `runs.alpaca.db` directly via
`intraday_session_inputs` (NOT the exported JSON) and is untouched, as are
quote-logger/postclose/liveness. The producing lane is a
`ReadOnlyBrokerWrapper` shadow (writes swallowed). Capital paths: zero
contact.

## EVIDENCE
Unit: tests/test_rq105_batch_scores_export.py 51 passed (8 new: lane
selection + identity stamp, env switch, wrong-lane refusal, missing
component-pin refusal, prod-default regression, unknown-source refusal,
per-source DB paths, replay-side verify); rq105 status/wrapper suites
green. Rehearsal (worktree, DB copies, read-only sources): (R1) prod
regression exports 80/80 from 2026-07-27-live-e548dd21 with identity
stamped; (R2) blend vs the real lane DB today refuses loudly (lane has no
07-27 run — correct fail-closed); (R3) the real 07-28 lane smoke run
(buy_blocked) is refused on health evidence; (R4) real lane bundle shape
with full-funnel flags exports 87/87, meta carries both component pins
(04d7a381…, 1e644354…), replay-side `verify_bundle` = ok. Literal pin
load: `load_blend_scorer` (pinned pipeline checkout) loads BOTH
components: content 04d7a381cd6df847… / fp f8fb2259b2bf1537 and content
1e644354e0981f47… / fp sha256:1d8f167f…e41b — matching the directive.

## NEXT
First real blend export = the morning after the first full-funnel Step-5
lane run lands in the lane DB (expected tonight 13:55 PT). Until then the
exporter fails loudly at 06:15 PT and serving skips the day — the designed
alarm, not a regression. Deploy: coordinator syncs the pinned run
checkout; no launchd change needed (wrapper carries the switch).
