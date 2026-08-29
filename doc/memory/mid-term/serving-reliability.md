# SERVING RELIABILITY — the path from "merged model" to "model actually deciding"

> Tier: **MID.** Agent proposes, operator confirms. Opened 2026-07-28 and
> **CONFIRMED by the operator** (2026-07-28/29, in-session "go" in direct
> response to an explicit recommendation to open this workstream). This file
> is the post-decision record, not a pending proposal.
> Sibling workstreams: `model-edge.md` (does a model have edge)
> · `agent-control.md` (how work lands). This one owns: **when a model is
> supposed to be deciding, is it actually deciding — and if not, does the
> system say so out loud?**

## Why this workstream exists

2026-07-28 produced four independent defects that all belong to ONE class:
**the serving path fails silently and reports the failure as a normal
verdict.** None of them were caught by tests, CI, or the daily gates —
each surfaced only when a human looked at a specific number and asked why.

| # | defect | silent symptom | true cause | status |
|---|---|---|---|---|
| 1 | freshness gate holds `rawlabel` to a raw 28d SLA | weekly PatchTST retrain "refused — NOT FRESH", old pin kept, rc=0 | the panel it derives from is dropna'd on fwd labels, so its frontier is structurally ~91d behind; the SLA is unsatisfiable by construction | RenQuant#541 |
| 2 | inference-frame cache key embeds the whole `panel_scoring` block (incl. `artifact_path`) | every model swap rebuilds 145 tickers — cold rebuilds observed at ~795s and ~1201s, and a third run hit a hard 1800s timeout and ABORTED `[VERIFIED — /tmp/ptserve_e2e.log (795s), /tmp/ptprod_e2e2.log (1201s), /tmp/ptprod_e2e.log (1800.07s TimeoutError)]` | key over-specified: fields that cannot change frame content invalidate the cache | orch#589 (design, MERGED 2026-07-29) |
| 3 | `rank_score` compared against a probability floor while still in the RAW domain | "no trade" — indistinguishable from the model declining | unit error: scoring writes raw, calibration overwrites with probability; when calibration does not run the raw value survives | pipeline#219 + RenQuant#542 |
| 4 | umbrella kernel fork lags the pinned pipeline | `panel_scorer_invalid_kind` (blend), `adaptive_quantile` unsupported | two copies of the same kernel; only one gets the fix | RenQuant#540 (blend), #542 (mirror); **fork retirement still open** |

Common shape: **a gate or default that is correct in isolation, wrong
against the current data/config reality, and whose failure mode is
indistinguishable from a legitimate "nothing to do".** The existing
sentinels watch whether jobs RAN; nothing watched whether a model's opinion
actually reached the funnel.

## Acceptance criteria (proposed)

- **AC1 — no unsatisfiable gate.** Every freshness/staleness threshold is
  checked against the structural floor of its own recipe (label horizon,
  embargo). A gate that cannot pass by construction is a defect, not a
  strict setting. (#541 fixes one; orch#588 memo covers the health-record
  twin; the fundamentals `worst=6q>1` rule is the next candidate.)
- **AC2 — unit-typed decision inputs.** Any threshold comparison names its
  domain; a cross-domain compare fails loud, never silently empties the
  funnel (#219 pattern generalised).
- **AC3 — one kernel.** Retire the umbrella-local kernel fork so a fix
  cannot land on one copy only (F-2, long-standing).
- **AC4 — warm serving path (OPEN — design landed, implementation not
  started).** Frame preparation would be pre-built by schedule and keyed
  only on what determines frame content, so a model swap never costs a
  session. orch#589's cache-key design memo is now **MERGED**
  `[VERIFIED — gh pr view 589, mergedAt 2026-07-29T07:14:15Z]`, so AC4 is no
  longer blocked on that design; the implementation itself (allowlist cache
  key + scheduled warm step) has not landed, so AC4 is not satisfied and
  must not be read as such until that implementation lands.
- **AC5 — silent-refusal telemetry.** Every weekly promote refusal and every
  fail-closed funnel exit is counted and surfaced; a refusal repeated N weeks
  running is an alarm, not a log line. (#541 was invisible for months
  precisely because the job exited rc=0 each Saturday.)

## Evidence anchor (2026-07-28)

The PatchTST swap exercised the whole chain end to end and produced the
decisive read for `model-edge.md`: with the calibrator attached, the fresh
serving artifact (effective cutoff 2026-04-27) scored 82/82, of which 75
were evaluated against the buy floor and 10 cleared it, VLO was selected
slot 1 at calibrated 0.5245 — and `SizeAndEmitTask: VLO Kelly=0 — skip`,
0 orders. Diagnostic: `CALIBRATOR-SATURATED: rank_score IQR=0.011` (warn
floor 0.050), held names spanning 0.4959–0.5090 (every figure this
paragraph `[VERIFIED — /tmp/ptserve_e2e.log, readonly preflight, no
orders, no state]`). **A model whose calibrated conviction sits at
coin-flip correctly sizes to zero.** That is the funnel working; the
earlier all-vetoed run was defect #3 impersonating the same answer
`[VERIFIED — pipeline#219 / RenQuant#542]`.


## Addendum 2026-08-29 — defect #5: the serving chain had no liveness (orch#1085)

- 2026-08-28: host booted 10:38 local; launchd dropped the 06:15 batch-score
  export and 06:25 scheduler `StartCalendarInterval` slots (never backfilled
  across a boot); no bundle, shadow serving `SKIP upstream` on line 1, no
  serving rows — and `rq105_liveness_check.py` printed OK because it watched
  only the three tick collectors `[VERIFIED — progress doc
  2026-08-29-rq105-liveness-serving-chain.md, incident table]`. Same class as
  rows 1–4: a normal-looking verdict over a chain that did nothing.
- Fix (PR for #1085): the check compares `meta.session_date == today` on the
  bundle (`export_missing`), the serving log + `session_date` rows
  (`serving_noop`), and the scheduler when armed (`scheduler_dark`) — a
  DISARMED scheduler is named in the OK line, never silent. `RunAtLoad` +
  `rq105_catchup_guard.sh` catch a boot-missed slot up to 13:00 local; the
  drift scan compares declared `run_at_load`/`keep_alive` intents against the
  installed plists. **Landing (bootout/bootstrap of the two plists + `-run`
  sync) is an operator action — until then the running check is the old one.**
