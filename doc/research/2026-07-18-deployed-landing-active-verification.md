# Active verification of the 2026-07-18 landed/deployed changes

**Date:** 2026-07-18
**Author:** hallovorld (Claude)
**Reviewer:** haorensjtu-dev (Codex)
**Type:** verification memo (read-only / sandbox; ZERO live orders; DBs `mode=ro&immutable=1`; all writes to TEMP)
**Do NOT merge** — this records evidence only.

## Bottom line

All four active verifications **VERIFIED**. The landing/deploy is healthy end-to-end.
No FAILED result. Two operator-facing observations (neither a landing defect):

- The deployed orchestrator pin advanced **`8c0acd5f` → `ade07dd`** *during* this
  verification (a concurrent live deploy; reflog + `subrepos.lock.json` confirm
  `ade07dd` is now authoritative). `renquant-pipeline` (`d32f7017`) and
  `renquant-strategy-104` (`082dccd2`) are unchanged and match the task exactly.
  #2 was run against the authoritative deployed pin set.
- The deployed sentinel's launchd-exit check shows one **un-acked LOUD** row —
  `com.renquant.run-surface-drift (last exit 1)` — consistent with the in-progress
  deploy/pin reconciliation window I witnessed. Operator should glance; it is the
  designed drift reminder, not a sentinel malfunction.

Runtime used throughout: `/Users/renhao/git/github/RenQuant` + `.subrepo_runtime`
pinned repos + `RenQuant/.venv/bin/python`. No git mutation of the live tree; no
writes to production DBs/artifacts.

---

## 1. Meta-label monthly job — step-0 consumer gate — **VERIFIED**

Ran the DEPLOYED `RenQuant/scripts/monthly_meta_label_retrain.sh` with
`RQ_META_LABEL_REPO_DIR` pointed at a TEMP repo dir (symlinked `.venv`, copied
`subrepo_env.sh`) and `RENQUANT_SUBREPO_ROOT` at the pinned runtime, so the real
snapshot sim can never run and every write lands in TEMP.

Evidence:
- Consumer-gate input (pinned strategy config `ranking.meta_label.enabled`) = **`False`**.
- **Exit 0** in **0.031 s** (< 5 s).
- Exact log line emitted (stdout + TEMP log):
  `meta-label consumer dark — retrain skipped by design (see doc/design/2026-07-18-metalabel-monthly-retrain-redesign.md)`
- Writes: only `…/scratchpad/v1_metalabel_repo/logs/monthly_meta_label/2026-07-18.log`
  (TEMP). Live-tree `logs/monthly_meta_label/` has **no** file dated today; **no**
  `data/*monthly_meta_label*` and **no** `meta-label-exit.candidate-*` artifacts written.
- **No ntfy** — the exit-0-by-design path (script lines 96–99) never calls `notify()`;
  no network egress.

Conclusion: the chronic monthly alarm is fixed on deployed code — the job short-circuits
at the consumer gate with zero training compute, zero artifact churn, and no page.

## 2. Landed pins health — full daily-contract sim — **VERIFIED**

Ran `python -m renquant_orchestrator daily-contract` (the deterministic
train→infer→execute→backtest contract fixture; `--broker-type paper`, dry-run) against
the authoritative deployed pins, PYTHONPATH resolved to `.subrepo_runtime/repos/*/src`,
`--strategy-config` = pinned strat-104 config, `--output-dir` = TEMP.

Pins in use: orch **`ade07dd`**, pipeline **`d32f701`**, strat-104 **`082dccd`**.

Evidence:
- **Exit 0**, `ok: true`, `dry_run: true`, `broker_name: paper-smoke`.
- Training funnel executed: `['load','train','validate']`.
- **BUY intent present (no zero-buy regression):** `order_intents = [{ticker: AAPL,
  action: buy, quantity: 1}]`; submitted order `{action: BUY, status: dry_run,
  order_id: dry-1}` — dry-run only, no real fill.
- **Full run_bundle produced** at the TEMP path with 18 keys:
  `account_snapshot, artifact_manifest, backtest_report, data_manifest,
  decision_trace, dry_run, execution_audit, market_snapshot, order_intents,
  output_files, run_id, run_type, schema_version, serving_bundle, stage_trace,
  strategy_config_hash, strategy_manifest, submitted_orders`.
- **Small-n guard INERT in prod:** pinned config has **no** `ranking.panel_scoring.buy_floor_min_n`
  key (value absent → `None`); the pipeline#207/#208 guard requires a valid int in
  `[2,30]` to act, so the deployed status quo is bit-identical (guard is shadow-only,
  strat-104#61). Config-parity intact (validator `accepted: true`; `strategy_config_hash`
  present in the bundle).

Conclusion: today's landing is healthy end-to-end on the deployed pins.

## 3. G4 canonical shadow job (#551) — smoke against a recorded snapshot — **VERIFIED**

`g4_shadow_job.py` / `g4_admission.py` are merged to orch `main` (#551) but NOT yet in
the deployed orch pin (`ade07dd`), and their runtime contract
`renquant_pipeline.decision_schedule` (pipeline#209, `a871166`) is merged to pipeline
`main` but NOT yet in the deployed pipeline pin (`d32f7017`, one commit behind) —
**expected**: G4 is SHADOW-ONLY / NOT scheduled; activation is a later governed step
(Phase 0 stays BLOCKED). Smoked from `origin/main` worktrees against a **real recorded
decision snapshot** (run `2026-07-17-live-41b03289`, 5 candidates BWXT/EME/ATI/XLI/XLY,
read-only from the runs DB) into a TEMP evidence store, using the **real NYSE calendar**.

Evidence:
- Session window (real NYSE) for T=2026-07-17: `close=2026-07-17T16:00-04:00`,
  `next_open=2026-07-20T09:30-04:00`.
- **Immutable write-once v4 §2 records** for both arms:
  `l1-cf1e6c895c1c-c9c696bc20cd.json` and `champion-10cf7d762556-96cb18cddcf5.json`,
  each `mode=0o444`, `execution_mode=shadow`, `orders_scheduled_for=2026-07-20`
  (open T+1). Recomputed `job_id` and `decision_digest` both **match** the persisted
  values (l1 digest `sha256:c9c696bc20cd…`, champion `sha256:96cb18cddcf5…`).
- **Admission ledger** for the unregistered session: `registration_bound=False` →
  **`series_eligible=False`** (correct — no pilot registration exists; the frozen
  registration identifiers only appear at the v4 §4 pilot-registration commit, out of
  step-2 scope). `admissible=true`, `reason_codes=[]`.
- **Byte-identical re-run is a no-op:** durable evidence (records + content-addressed
  inputs + admission) byte-unchanged; store retry outcomes `['identical']`; decision
  digests run1==run2. Only the append-only `attempts.jsonl` audit trail grows by one
  `outcome:"identical"` entry — by design.

Conclusion: the G4 step-2 plumbing works before any prospective accrual.

## 4. Sentinel live-fire check — **VERIFIED (healthy)**

Ran the deployed `ops/renquant104/rq104_degradation_sentinel.py` from the deployed
orchestrator-run checkout, read-only against the prod runs DB (`mode=ro&immutable=1`),
with `alert()` patched to CAPTURE so no page is ever sent.

Evidence:
- Module loads; **all rules present**, including the two current deliverables:
  `check_smalln_all_veto` (rule e, RFC pipeline#204 §2.3) and
  `check_smalln_guard_suppressed` (rule f, pipeline#207 §2). `n0_sentinel(pinned)=12`
  (built-in floor, since `buy_floor_min_n` absent). Ack ledger carries 10 entries.
- `--as-of 2026-07-18` (Saturday): correctly **skips** (not an NYSE session day), rc=0.
- `--as-of 2026-07-17` (last session): **rc=1 DEGRADED — 2 issues**:
  1. **small-n all-veto funnel freeze** — latest live scan `2026-07-17-live-41b03289`
     had the rank floor veto **ALL 5/5** scored candidates at `n_finite=5 < N0=12`.
     This is the sentinel firing **correctly by design** on the known 07-16/17
     override-session pattern; this alarm is deliberately un-ackable (never routes
     through the launchd ack ledger). The sentinel's own launchd row is acked with
     "exit 1 IS the alarm-delivered signal (by design)".
  2. **`com.renquant.run-surface-drift (last exit 1)`** — un-acked LOUD launchd
     nonzero exit (see observation above; consistent with the concurrent pin deploy).
  8 launchd jobs are acked → reported as **INFO** (conditional-retrain104, daily104,
  monthly-meta-label-retrain, retrain-panel104, rq105-batch-scores-export,
  shadow-ab-daily, weekly-retrain-patchtst, weekly-wf-promote).
- **Positive controls (synthetic TEMP DBs):** small-n(5) all-veto → **fires**;
  normal-n(20) all-veto → silent; small-n(5) with one admitted → silent. The deployed
  sentinel would correctly fire on a small-n all-veto and does not over-fire.

Conclusion: the deployed sentinel is healthy and correctly fires on a small-n all-veto —
proven on both real 07-17 data and synthetic controls.

---

## Reproduction (all read-only / TEMP)

- #1 `RQ_META_LABEL_REPO_DIR=<temp> RENQUANT_SUBREPO_ROOT=RenQuant/.subrepo_runtime/repos bash RenQuant/scripts/monthly_meta_label_retrain.sh`
- #2 `PYTHONPATH=<pinned */src> RenQuant/.venv/bin/python -m renquant_orchestrator daily-contract --strategy-config <pinned> --output-dir <temp> --broker-type paper`
- #3 driver `scratchpad/v3_g4_smoke.py` (orch `origin/main` + pipeline `origin/main` worktrees; recorded snapshot from `data/runs.alpaca.db` read-only)
- #4 driver `scratchpad/v4_sentinel_check.py` (deployed orchestrator-run sentinel; `alert()` patched to capture; prod DB `mode=ro&immutable=1`)
