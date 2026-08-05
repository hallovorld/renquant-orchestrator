# Triage: the 14 undispositioned failing jobs

STATUS: diagnosis complete, evidence-only. **No code, no ack, no live surface.** Each
row below is now dispositionable — that is the deliverable.

WHAT: a per-job diagnosis of all 14 undispositioned failing launchd jobs, each
read from the log THAT JOB ACTUALLY WRITES, plus the category split that is the
actual finding. Evidence only — no code, no ack, no live surface.

WHY/DIR: operator report 2026-08-05, *"the issue has been repeatedly showing up for
months"*. 16 `com.renquant.*` jobs hold a nonzero last exit; 5 acks exist and only 2
cover a currently-failing job, so **14 are undispositioned**
[VERIFIED — `launchctl list` ∩ `ops/renquant104/sentinel_acks.json` on origin/main].

Every diagnosis below was read from the log **that job actually writes**, found by
reading its wrapper for the redirect target — not from the launchd stream files, which
are stale by design wherever the script does `exec >> "$LOG"`. That mistake, and its
retraction, is recorded in `2026-08-05-log-mtimes-cannot-tell-you-when-a-job-last-RAN.md`.

## The categories matter more than the list

Sorting the 14 by *why* they exit nonzero splits them three ways, and the split is the
finding:

| category | n | what "failing" means |
|---|---|---|
| **A. the monitor works and found something real** | 7 | the job is healthy; its FINDING needs action |
| **B. genuinely broken / chronic** | 4 | the job itself cannot complete |
| **C. dead or already fixed** | 3 | nothing to debug |

**Seven of the fourteen are monitors correctly reporting.** A monitor that exits
nonzero on a finding is indistinguishable, in `launchctl list`, from one that crashed.
`sentinel_receipt.py` already draws exactly this distinction for one job
(`EXIT_ALARMS=1` vs `EXIT_INTERNAL=3`, added so a crashed sentinel would stop looking
like an alarming one) — it is simply not applied fleet-wide. That is the structural
reason this list looks hopeless and stays that way.

## A — the monitor works, the finding is real

| job | exit | finding | evidence |
|---|---|---|---|
| **rq104-risk-budget** | 1 | `per_name_concentration` **CRITICAL, consumption 193.4%** — TSLA at 23.2% of book vs the BULL_CALM cap of 12%, a budget declared `kind: hard`. `book_beta` CRITICAL 170% (measured 1.02 vs planning limit 0.6, `kind: planning`, PROVISIONAL). Drawdown OK (48.7% consumed), sleeve OK. | `risk_budget_live_2026-08-01T223001Z.json`, as_of 2026-07-31 |
| **rq104-scorer-identity** | 1 | CRITICAL: `shadow_models[0..2]` fingerprints changed between 2026-07-31 and 2026-08-04 with **no recorded promote/rollback event** in the boundary window | `scorer_identity_2026-08-04.log` |
| **rq104-model-freshness** | 3 | `shadow-panel` effective_selection_cutoff **2026-02-10, age 176d**, receipt has no `promoted_pin` (fail-closed escalate); tournament 141/142 at 43d | `launchd_model-freshness.out`, 2026-08-05 |
| **rq104-silent-refusal** | 1 | `retrain-panel104` has **11 non-acting runs** (2026-08-02, 07-26, 07-19, 07-12, 07-05, 06-28 …; 2 CRASHED, 9 self-reported FAIL) | `launchd_silent_refusal.out`, 2026-08-04 |
| **rq105-liveness** | 1 | `paired_is.jsonl` last complete row 2026-08-03 while today is 2026-08-04 (stale); post-close completion bound exceeded | `launchd_liveness.out` |
| **run-surface-drift** | 1 | PYTHONPATH **fallback is firing for exactly 5 jobs**, all `rq105-*` (batch-scores-export, postclose, quote-logger, session-scheduler, shadow-serving): their wrappers use the `[ -d X-run/src ] \|\| X/src` idiom and `renquant-common-run/src` does not exist, so they resolve to the dev checkout. **21 other jobs declare a deterministic root and are clean.** | `launchd_run_surface_drift.out`, 2026-08-05T07:00 |
| **agent-pr-loop** | 1 | `merge audit failed`. **Not a blockage and not a stale checkout** — see the addendum: the audit is the loop's LAST step, so every review/fix/merge already ran, and orch#830's fix is present in the checkout the loop uses. The gate is red **on merit**: 264/358 in-window merges carry no pre-merge `Merged by` comment. It clears when merges start carrying the marker, not when a pin advances. |
| **ops-audit** | 1 | 4 NEW findings (launchd-liveness, ack-ledger, gate-stamp-parity, booster-identity). Also reports its ledger at `renquant-orchestrator-run/ops/ops_audit_acks.json` with **0 acks** while the dev checkout has 1 — merged-but-not-deployed | `launchd_ops-audit.out`, 2026-08-05T05:50 |

**rq104-silent-refusal is the instrument this fleet already has** for "did the job
act?", derived per job from that job's own dated logs. It is currently exit=1,
undispositioned, and reporting correctly — its alarm is being lost with the rest.

## B — genuinely broken / chronic

| job | exit | diagnosis |
|---|---|---|
| **weekly-wf-promote** | 1 | the chronic WF-gate root. Latest run 2026-08-04 ends `WF gate REJECTED staged model — production unchanged. Reject disposition: prod FRESH (trained 2026-08-02, 2d ≤ 28d SLA) — governance nominal, calm notify, exit 0`. So the *newest* outcome is a clean refusal; the retained exit=1 is from an earlier, failing run. |
| **retrain-panel104** | 1 | a faithful **mirror**: it delegates to weekly-wf-promote and reports whatever that returns — `=== retrain_panel delegated weekly_wf_promote FAIL at Sun Aug 2 10:22:11 ===`. It has no independent failure. Fixing weekly-wf-promote clears both. |
| **monthly-calibrator-refresh** | 1 | `SCORER/CALIBRATOR BINDING GATE FAILED: calibrator/scorer BINDING MISMATCH — this calibrator was fit against a different scorer than the live runtime will load`. **Staged calibrator quarantined; production calibrator never modified.** This is a fail-closed gate protecting production, firing monthly. |
| **rq105-shadow-serving** | 4 | `SKIP not-wired: no producer exists for data/rq105/feature_snapshot_<date>.json (Stage-3, #221)`. Exit 4 is the wrapper's own not-wired code — the job cannot succeed until #221 ships a producer. |

## C — dead or already fixed

| job | exit | state |
|---|---|---|
| **crypto-session** | 2 | G2 crypto KILLED 2026-07-18; removed from the reviewed manifest in orch#832. Awaiting one operator grant: `launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.renquant.crypto-session.plist && rm …` |
| **weekly-apy104** | 2 | APY below the alert floor — the alarm doing its job. Its unreadable *text* is fixed in orch#837. |

## What this deliberately does NOT do

No acks are written. An ack suppresses an alarm, and CLAUDE.md's containment protocol
requires each to name an owner, an exit code, and an expiry or restore condition; seven
of these fourteen should not be acked at all, because the job is fine and the *finding*
is what needs an owner. Writing fourteen acks to make a list go green would be the
purest form of the failure being reported.

No live surface is touched. The concentration reading in particular is a **measurement,
not an instruction**: TSLA at 23.2% is consistent with an entry-time cap plus
appreciation rather than a control failure, the book is 4 names at $10.7k with current
drawdown 3.7% and 48.7% of the DD budget consumed, and any position change is an
operator decision.

EVIDENCE:

| claim | value | provenance |
|---|---|---|
| failing / acked / undispositioned | 16 / 5 (2 covering) / **14** | [VERIFIED — `launchctl list` ∩ ledger on origin/main] |
| category split | A=7, B=4, C=3 | [VERIFIED — each row's own log, cited above] |
| TSLA concentration | weight 0.2321, cap 0.12, consumption 1.9339, status CRITICAL, `kind: hard` | [VERIFIED — `breaches.per_name_concentration` + `readings.concentration` in the 2026-08-01 statement] |
| book beta | measured 1.0195, limit 0.6, consumption 1.6992, `kind: planning` PROVISIONAL | [VERIFIED — `breaches.book_beta`] |
| retrain-panel104 is a mirror, not an independent failure | delegates to weekly_wf_promote and reports its result | [VERIFIED — `logs/retrain_panel/2026-08-02.log`] |

Ordering, by what the evidence supports:
1. **weekly-wf-promote** — clears two rows (B), and its newest run already exits 0.
2. **the 5 rq105 fallbacks** — `renquant-common-run/src` absent means the run
   checkout is not what review approved; that undermines every other deployment claim.
3. **rq104-scorer-identity** — unexplained shadow-model fingerprint changes are the
   kind of thing that is cheap now and expensive later.
4. Fleet-wide `EXIT_ALARMS` vs `EXIT_INTERNAL`, so category A stops reading as breakage.

## Addendum: the fallback's real scope, and how the daily run resolves

Bounding the `run-surface-drift` row took three corrections, all of the same shape —
reading a **superset as the alarm set** — and they are recorded because the shape
recurs:

1. Grepping `pythonpath com.renquant` returned **27** jobs and I read them as flagged.
   That pattern also matches the checker's own `declares a deterministic root` INFO
   line. Flagged: **5**. Clean: **21**.
2. All five are `rq105-*`. The idiom the checker looks for is specifically
   `VAR="<...>-run/src"; [ -d "$VAR" ] || VAR="<...>/src"`, which only the rq105
   wrappers use. `daily104` and `intraday104` were never flagged.
3. I then ran the daily run's own resolver in a stripped environment and got
   `/Users/renhao/git/github` — the dev checkouts. Wrong: I had omitted
   `renquant_load_subrepo_env` (`daily_104.sh:109`), which sources
   `RenQuant/.subrepo_assembly/current.env`. **Stripping the environment removed the
   very thing that decides the answer.** With that line included the resolver returns
   `RenQuant/.subrepo_runtime/repos`, matching what the last real run logged:
   `strategy_config resolved: …/.subrepo_runtime/repos/renquant-strategy-104/configs/strategy_config.json`.

So: **the daily/intraday lane resolves to the pinned assembly, deterministically.** The
fallback is real but confined to the five rq105 jobs, and today it is benign — the
`renquant-common` dev checkout sits at exactly `origin/main` (detached, 0 ahead, 0
behind). What the checker objects to stands: *which* copy executes is decided by
whether a directory exists, not by review.

[VERIFIED — `grep "by FALLBACK"` vs `grep "declares a deterministic root"` on the
2026-08-05T07:00 scan; the resolver re-run with `renquant_load_subrepo_env` included;
`git -C … rev-parse`/`rev-list --count` on the five sibling checkouts, read-only]

Also verified while checking the dev checkouts, since it bears on the same question:
`renquant-pipeline` is on `feat/persist-served-matrix` and `renquant-strategy-104` on
`fix/f1-f3-clf-component-kind`, but **both are 0 commits ahead of `origin/main`** —
they carry no code main does not — and pipeline's one "dirty" entry is an *untracked*
`persistence_backup_check.py` at the repo root, not on any `src` path. Benign today;
unreviewed as a mechanism.

## Addendum 2: agent-pr-loop was mis-filed, and the correction matters

I put `agent-pr-loop` in category C ("already fixed; clears when the run checkout
advances its pin"). **Both halves were wrong**, and the row now sits in category A.

Measured on the live job:

| | |
|---|---|
| stdout lines | 9,152, of which **only the first three** are not `cleared stale lock and resumed` |
| stderr, last 300 | **299 × `merge audit failed`** + 1 × `agent identity preflight failed` |
| `status.json` | `"ok": false` |

That reads like a loop doing nothing, and my first reading was exactly that: the review
queue had seven unreviewed PRs, the loop looked livelocked on its own lock file, and the
inference — *the merge-audit gate is aborting the loop before it works* — fit perfectly.

It is wrong. `scripts/agent_pr_loop.py:417` runs the audit as the **last** step:

```python
merge_audit = _orch(["repos", "merge-audit", "--repo", "all", "--strict"])
status["steps"].append({"name": "merge-audit", "result": merge_audit})
if merge_audit["rc"] != 0:
    raise RuntimeError("merge audit failed")
```

Everything above it — review, fix, merge — has already run. A red audit costs the exit
code and `status.ok`, not the work. The quiet stdout is a loop with nothing to do, not a
loop that cannot start.

And the checkout is current: `renquant-orchestrator` (the dev clone the loop uses via
`RENQUANT_ORCHESTRATOR_ROOT`) has `GATE_WINDOW_DAYS` and the `exhausted = len(rows)`
coverage rule from orch#830 **in its working tree already**
[VERIFIED — `grep` on the live path, 2026-08-05]. So no pin advance is pending; the gate
is simply red **on merit** — 264/358 in-window merges lack a pre-merge `Merged by`
comment, which is a behaviour, not a bug.

**What this changes:** `agent-pr-loop` is the fleet's single loudest failing job (it fires
every 5 minutes) and it is a **category-A monitor reporting a real, clearable finding**.
Nothing about it needs debugging. It clears when the agent that merges starts posting the
marker before merging — orch#830 is what made that possible, and the marker cannot be
added afterwards.

**The reasoning error, since it is the third of this shape today:** every observation was
real and the story built from them was wrong, because I inferred the *ordering* of the
loop's steps from the shape of its output instead of reading the file. The same shape
produced "27 jobs use the fallback" (it was 5) and "the daily run executes dev checkouts"
(it does not). Reading the source costs one command; the inference cost three
retractions.

artifact: none. Nothing is produced or modified; every figure is read from logs, plists
  and ledgers the fleet had already written.
prod or exp: neither. Read-only diagnosis. No job is touched, no ack written, no
  schedule or config changed — deliberately, since seven of the fourteen should never
  be acked at all.
existing data: yes, entirely — each job's own dated logs, `launchctl list`,
  `ops/renquant104/sentinel_acks.json` on origin/main, the installed plists, and the
  2026-08-01 risk-budget statement. Nothing was re-run to produce any number here.
best-known?: yes for the diagnosis. Reading each job's real log is the primary record,
  and it is what corrected the earlier mtime-based attempt (orch#838/#840). It is NOT a
  best-known remedy for any individual finding — those are named per row and owed to
  whoever owns each surface.
scope: documentation only. One progress doc plus two addenda correcting its own earlier
  claims; no source file, test, config or ack is touched.

NEXT: weekly-wf-promote (clears two rows at once,
and orch#843 shows its refusals are correct); the five rq105 PYTHONPATH fallbacks;
rq104-scorer-identity (in review as orch#847); and the fleet-wide EXIT_ALARMS vs
EXIT_INTERNAL split, so category-A monitors stop reading as breakage.
