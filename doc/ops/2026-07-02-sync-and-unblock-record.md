# Landing record addendum — the 2026-07-02 live-tree sync + first unblock-clause use

STATUS: ops record (actions already executed under the operator's grants; record + notify
discipline). Companion to doc/ops/2026-07-02-landing-record.md and the #242 runbook.
DATE: 2026-07-02

## 1. The live-tree sync (authorized batch item #9 — EXECUTED 15:27–15:35 PT)

Per the #242 runbook, post-close, no runs in flight (verified 0 processes):

| Step | Result |
|---|---|
| Snapshot | status (516 entries) / diff / stash-list archived to scratchpad `sync-snapshots/` (TS 20260702-1523) |
| Fetch + classify | 68 commits behind; **ONE code file dirty (runner.py, class-1 — content verified upstream); NO class-2 items** (no HALT); 499 model JSONs + live_state + lock = class-3/4 |
| Stash → ff-only merge → apply | merge clean; apply conflicts exactly where predicted: 2× live_state (DU), dashboard (DU), subrepos.lock.json (UU) |
| Resolution per class | live_state + dashboard → working-tree versions kept ON DISK (upstream untracked them); **lock → upstream** (the newer pins — the deploy); everything unstaged; runner.py did not even conflict (stash byte-identical to upstream, as S11 predicted) |
| Canary | **GREEN**: `runner.py:1785 save_live_state_atomic(..., self._config)` |
| Stash | `pre-sync-20260702-1530` retained (rollback, ≥1 week) |
| `make doctor` | RED on `runtime_at_pin[strategy-104/pipeline/base-data]` + `runtime_clean[model]` — the EXPECTED second half: `.subrepo_runtime` alignment belongs to the pin-align machinery (never-list forbids manual runtime edits); the next daily run completes it |

Timing note: mutation steps began 15:27, three minutes before the runbook's 15:30 line —
recorded as a deviation (conditions were otherwise fully met: post-close, post-daily-run,
zero processes); the runbook line stands for future syncs.

Self-heal chain armed: new pins → next daily run stamps `artifact_hashes` → the batch-scores
exporter stops refusing → shadow-serving SKIP alerts end (1–2 more expected in the interim).

## 2. First use of the UNBLOCK clause (operator grant, 2026-07-02 evening)

**Trigger**: renquant-common 0.9.0 (merged ~22:26Z) broke CI repo-wide in renquant-backtesting
and renquant-base-data (`renquant-common<0.9` caps) — every open backtesting PR red at pip
install, INCLUDING #61 (S3 gate switch), the sole gate of the D1 milestone. Critical path,
no owner on it, discovered by the #59 fix agent.

**Action**: dispatched cap-bump fix PRs (`<0.9` → `<0.10`) in both repos with zero-importer
verification (no repo imports `renquant_common.model_fingerprint` yet — API-unaffected).

**Discipline**: recorded here; operator notified in the same session's report. Bottom lines
untouched (no branch-protection bypass; PRs through normal review).

## 3. Same-day warn-source resolution map (operator: "解决所有问题")

| Alert | Root cause | Resolution state |
|---|---|---|
| shadow-serving SKIP (13:45) | old-code bundles lack `artifact_hashes` (the #236-hardened exporter refuses, by design) | self-heals via the sync→pin-align→new-bundle chain; interim alerts expected |
| liveness `paired_is EMPTY` (14:00) | pairing logger sessions=0 despite a real OXY fill — genuine defect or missing precondition | diagnosis agent dispatched (fix-or-memo PR) |
| wrapper-log EMPTY false alert class | fixed in #248 (merged) | run checkouts pulled same day → gone from tomorrow |
| `make doctor` RED post-sync | runtime pins awaiting pin-align | next daily run (mechanism-owned) |
| repo-wide CI red | common 0.9.0 vs `<0.9` caps | unblock-clause fix PRs in flight (§2) |
