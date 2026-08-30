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
  `rq105_catchup_guard.sh` catch a boot-missed slot on an NYSE session day up
  to that session's ACTUAL local close (r2, codex: `rq105_catchup_cutoff.py`
  — 10:00 PT on an early-close day, refused on a weekday holiday; the r1
  fixed 13:00 would have exported after an early close); the
  drift scan compares declared `run_at_load`/`keep_alive` intents against the
  installed plists. **Landing (bootout/bootstrap of the two plists + `-run`
  sync) is an operator action — until then the running check is the old one.**

## Addendum 2026-08-30 — defect #6: three run-surface CHECKERS were not telling the truth

- Drift scan's import-resolution check: called `verify()` without the daily's
  package roots → three false "unresolvable" alarms every morning; the roots
  the CLI did establish were APPENDED behind the venv's editable `.pth`
  siblings, so four of eight packages were pinned against the mutable sibling
  checkouts while the pin read OK `[VERIFIED — progress doc
  2026-08-30-run-surface-checkers-truth.md §Evidence]`. Fix: `verify()`
  establishes the resolution itself at the PYTHONPATH position and asserts
  every `renquant_*` symbol lies under the chosen root
  (`resolved_from_unpinned_path` otherwise); the INFO line names the tree.
- Dawn preflight: "pins not aligned" for 7 sessions (08-19..08-27) over ONE
  dirty auto-generated README, while the order path (`_is_pinned` alone)
  ran; then the 08-28 slot was dropped by the boot. Fix: `PIN_MISMATCH`
  (abort) vs `TREE_DIRTY` (docs/README/generated allow-list → WARN + continue)
  vs `TREE_DIRTY_BLOCKING` (src/configs/code → abort); aborts now notify.
- Boot catch-up generalised: `ops/catchup_guard.sh` + `ops/catchup_cutoff.py`
  (moved from `ops/renquant105/`), `session` or literal-`HHMM` cutoff; wired
  into the dawn preflight (0605 session) and a new drift-scan wrapper (0700,
  2400 — calendar-day job unchanged). `RunAtLoad` intents + the drift job's
  new `program_args` are in the manifest; **landing = operator
  bootout/bootstrap of the two `deploy/` plists + `-run` sync**, then delete
  the four `PENDING_INTENT_INSTALL` / one `PENDING_PROGRAM_ARGS_INSTALL`
  entries in `tests/test_run_surface_drift_check.py`.
- Lesson (recurring): a checker that measures the wrong object passes
  forever; ask "which tree / which predicate does the PRODUCTION path use?"
  and bind the checker to that, then make its verdict name the object.

## Addendum 2026-08-30 — defect #7 (AC1 class): the retrain freshness gate vetoed on a delisting

- 2026-08-29/30: the weekly promote failed `PANEL-FREEZE 1/293 stale` — the
  one name is AVB (Equity Residential merger closed 2026-08-17, last bar
  2026-08-24), still in `tier_A_tickers` and NOT in the served watchlist
  `[VERIFIED — progress doc 2026-08-30-retrain-universe-exclusion-registry.md]`.
  The strict 0.0 stale fraction assumed delistings reach the versioned
  inventory, but the inventory ships NO `delisted_tickers` channel (generated
  2026-05-05, no regeneration since), so the gate could not pass by
  construction — same shape as IAC in July (hand-coded
  `RETRAIN_EXCLUDE_TICKERS=IAC` in the umbrella promote).
- Fix (orch#1096 r2): exclusions are EXPLICIT and REVIEWED —
  `config/retrain_universe_exclusions.json` in the orchestrator (reason enum,
  effective date, evidence URL, adding PR; loaded fail-closed). Its names leave
  the universe before the refresh and the guard, AND the guard hands base-data's
  panel build a filtered copy of the inventory (`--inventory`), so an excluded
  name leaves the actual training universe. A heuristic skip ("stale AND not
  served ⇒ presumed delisted", r1) was REJECTED in review: an outage, a symbol
  transition or an ingestion gap satisfy it, and pruning only the freshness
  accounting leaves stale rows in the panel. Every remaining stale name still
  vetoes; the veto names ticker / lag / last bar and says to add a reviewed
  registry entry or fix ingestion; an informational `STALE-NON-WATCHLIST` ntfy
  names the registry path. **Deploy = orchestrator pin / `-run` sync (operator
  action); until then the live promote still vetoes on AVB** — interim bridge
  is umbrella PR #625 (`RETRAIN_EXCLUDE_TICKERS` default `IAC,AVB`, freshness
  accounting only). The versioned fix stays base-data's: regenerate the
  inventory with a `delisted_tickers` channel.
