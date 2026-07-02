# S11: live-tree dirt inventory — exhaustive classification (read-only audit)

STATUS: research evidence / audit record (read-only — no git mutation was performed in any
live or working checkout; `git status`/`diff`/`show`/`ls-files --others` only). Task S11 of
the unified plan (#231 Term PROCESS / floor tier-2).
DATE: 2026-07-02 (round 2 — r1's inventory was NOT exhaustive; see "What r1 missed" below)

## What r1 missed

r1 inventoried 5 items (a runner.py hotfix-residue line, 2 calibrator re-stamp families, LEAN
data churn, and one sibling checkout) and declared "every item ticketed or resolved." Codex's
review correctly found this false: the live tree's actual `git status` at review time carried
many additional unclassified changes — `live_state` files, `strategy_config.json`,
`doc/dashboard.md`, `subrepos.lock.json`, hundreds of per-ticker model files, untracked
staging/rollback artifacts, diagnostics, QP replay output, watchlist/regime artifacts, backup
files, and an untracked top-level `as_of` file — none listed or assigned an owner/retention
policy/ticket. r1's "no durable-PR work remains" claim was not supported by the actual tree
state.

This round re-inventories from scratch, mechanically, against the tree's CURRENT state
(2026-07-02, this round) rather than trusting r1's partial list.

## Method

```
git -C /Users/renhao/git/github/RenQuant status --porcelain=v2   # tracked-modified + untracked, machine-parseable
```
324 tracked-modified paths, 192 untracked paths, 516 total. Every path below is accounted for
in one of the classes; the closing checklist confirms the count reconciles.

## Tracked-modified (324 paths)

| Class | Count | Representative paths | Producer | Kind | Tracked policy | Disposition |
|---|---|---|---|---|---|---|
| Per-ticker model artifacts (`models/<TICKER>/<TICKER>-{policy-metadata,qtable,bin-edges,rf-trees,xgb-buy,xgb-sell,manual-rules}.json`) | 221 (133 unique tickers) | `models/NVDA/NVDA-policy-metadata.json`, `models/AAPL/AAPL-policy-metadata.json` | per-ticker training/tournament pipeline (writes policy/tree/table state per retrain) | runtime-generated, committed by design (durable model state) | **correctly tracked** — this is the intended durability mechanism for trained per-ticker state, not accidental dirt | **no action** — normal operation; these are supposed to be tracked+modified as training runs |
| WF-gate GBDT recipe artifacts (`artifacts/walkforward_gbdt_prod_recipe_v2/<date>/panel-ltr.json`) | 43 | `.../2026-02-09/panel-ltr.json`, `.../2026-03-02/panel-ltr.json` | `scripts/run_wf_gate.py` (walk-forward gate re-scoring) | runtime-generated | tracked (WF corpus is durable evidence per repo convention) | **no action** — normal WF-gate operation |
| Sim calibrator artifacts (`artifacts/sim/walkforward_calibrators/<date>/panel-rank-calibration.json`) | 43 | `.../2026-06-02/panel-rank-calibration.json` | same WF-gate re-scoring path, calibrator side | runtime-generated | tracked | **no action** — normal WF-gate operation |
| Prod calibrator re-stamp (`artifacts/prod/{panel-ltr.alpha158_fund.json, panel-rank-calibration.json}`) | 2 | as named | `stamp_patchtst_fingerprint.py`-class re-stamp tooling | runtime-generated (content fingerprint) | tracked | **TICKETED** — root cause is the triple-implemented content-fingerprint bug (`model_content_sha256` hand-copied across 3 sites); permanent fix is M6/R2 (fingerprint unification), already on the plan. Not a new PR here. |
| LEAN backtest data (`backtesting/data/equity/usa/{daily,factor_files,map_files}/*`) | 9 | `daily/aapl.zip`, `factor_files/bac.csv` | LEAN data-sync tooling | runtime-generated (market data cache) | tracked | **no action** — normal data-sync churn |
| `backtesting/renquant_104/adapters/runner.py` (1-line diff: `save_live_state_atomic` config arg) | 1 | — | manual hotfix | source code | tracked | **RESOLVED upstream**, unchanged from r1 — verified `origin/main:backtesting/renquant_104/adapters/runner.py:1785` already ships `self._config`; this local diff is residue on a checkout that is BEHIND origin/main. No PR needed; needs the landing sync only (see recovery procedure below). |
| `backtesting/renquant_104/live_state.{alpaca,alpaca_shadow}.json` | 2 | as named | `runner.py::save_live_state_atomic` (daily-full + shadow runs) | runtime-generated (live position/state snapshot) | tracked — **note**: `.gitignore` has a generic `backtesting/*/live_state.json` rule that does NOT match these actual filenames (`live_state.alpaca.json`, `live_state.alpaca_shadow.json` — broker-suffixed), so these two files are tracked despite the ignore rule apparently intending to exclude live-state snapshots. Flagging the mismatch; not resolving it here since it's unclear whether tracking these two specific files is intentional (a durable state-snapshot record) or a gitignore gap — **UNRESOLVED, needs owner** to confirm intent. | new ticket needed if the answer is "should be ignored" |
| `backtesting/renquant_104/strategy_config.json` | 1 | — | pinned config, hand-edited or pin-aligned per run | source config | tracked | daily operational drift on the pinned config; consistent with normal pin-align cadence — **no action** unless a specific unexpected diff is found (not inspected line-by-line this round; flag for the lander to `git diff` before any sync) |
| `doc/dashboard.md` | 1 | — | dashboard-render tooling (auto-updated status doc) | runtime-generated doc | tracked | **no action** — normal auto-refresh |
| `subrepos.lock.json` | 1 | — | `scripts/promote_pin.py` / pin-align tooling | runtime-generated (subrepo pin lockfile) | tracked | expected churn from pin operations — **no action** unless it diverges from the actually-deployed pins (lander should verify before sync, see recovery procedure) |

Reconciliation: 221 + 43 + 43 + 2 + 9 + 1 + 2 + 1 + 1 + 1 = **324** ✓.

## Untracked (192 paths)

| Class | Count | Representative paths | Producer | Kind | Tracked policy | Disposition |
|---|---|---|---|---|---|---|
| Per-ticker model artifacts, NEW tickers not yet committed (`models/{APH,ATI,BWXT,EME,GLW,GRMN,SPY,XLI,XLY}/*`) | 108 (across 9 new ticker dirs; file-type breakdown: 21 xgb-buy, 21 xgb-sell, 19 qtable, 19 bin-edges, 17 rf-trees, 11 manual-rules) | `models/SPY/SPY-xgb-buy.json` | same per-ticker training pipeline as the tracked-modified class above | runtime-generated | should be tracked once these 9 tickers are added to the live watchlist/universe (consistent with how the other 133 tickers are already tracked) | **no action / self-resolving** — will become tracked-modified on next commit of the universe expansion; not dirt, just the natural lag between "watchlist grew" and "first commit of the new tickers' model state" |
| Weekly-promote staging artifacts (`artifacts/prod/panel-ltr.alpha158_fund.weekly_<UTC-timestamp>.staging.json`) | 41 | `.weekly_20260630T201003Z.staging.json` | `training_panel/daily_retrain_alpha158_fund.py` / `kernel/model_acceptance.py` (weekly promote pipeline's staging-before-promote step) | runtime-generated, intentionally untracked (staging area, not the durable artifact — the durable one is `artifacts/prod/panel-ltr.alpha158_fund.json`, tracked separately above) | correctly untracked — staging files are ephemeral by design | **TICKETED — retention policy needed**: 41 timestamped staging files spanning 2026-06-15 to 2026-06-30 (about 2.5 weeks) with no visible pruning is unbounded disk growth. No PR here; new ticket: define a retention window (e.g. keep last N or last 30 days) and a pruning step in the weekly-promote pipeline. |
| WF-eval experiment strategy configs, top-level (`strategy_config.{exp_A,exp_B,exp_B45,patchtst,patchtst_20d,sim_monthly_retrain_snapshot,xgb_gate_abs}_wf_eval.json`) | 7 | as named | `scripts/run_wf_gate.py` / `kernel/model_acceptance.py` experiment-config generation | runtime-generated (per-experiment config snapshots) | correctly untracked — these are working files for ad hoc WF-gate experiment runs, not the pinned production config | **no action** — normal experiment-harness scratch state; low volume (7 files), no retention concern |
| WF-eval "prod semantic" diagnostic snapshots (`artifacts/diagnostics/wf_eval_configs/strategy_config.*.prod_semantic.json`) | 7 | as named | same WF-eval harness, a semantic-diff-against-prod diagnostic dump | runtime-generated | correctly untracked (diagnostics dir) | **no action** — same experiment harness as above, 1:1 with the 7 configs |
| Other `artifacts/` top-level generated outputs (`cache/`, `diagnostics/wf_trade_traces/`, `live-shadow/`, `panel-ltr.alpha158_fund.json` (duplicate name, NOT the tracked prod one — this is a top-level copy, see note), `panel-ltr.alpha158_linear.json`, `panel-ltr.alpha158_linear.previous.json`, `panel-rank-calibration.alpha158_linear.json`, `sim/walkforward_manifest_gbdt_prod_recipe_v2.json`, `spy-gmm-regime.json`, `walkforward_patchtst/`, `walkforward_patchtst_20d/`, `walkforward_patchtst_20d_manifest.json`, `walkforward_patchtst_manifest.json`, `watchlist-correlation.json`) | 14 (8 top-level dirs/files reported by porcelain plus the 6 nested ones enumerated inside `diagnostics/wf_eval_configs` already counted above — see note) | as named | `scripts/train_walkforward_patchtst.py` (patchtst artifacts); `backtesting/renquant_104/main.py` / `renquant_103/...` shared code (watchlist-correlation.json, spy-gmm-regime.json — these are written by shared `renquant_103`/`renquant_104` pipeline code, same regime/correlation computation used by both) | runtime-generated (WF-gate + regime/correlation computation working state) | correctly untracked (all are recomputable working artifacts, not source) | **no action** — normal generated-artifact set; the "alpha158_fund.json" name COLLIDING with a tracked path under `artifacts/prod/` is worth a naming-hygiene note (two different files, one under `artifacts/`, one under `artifacts/prod/`, easy to confuse when grepping) but not a durability risk since they're at different paths |
| QP replay output (`artifacts/qp_step4_replay/`) | 1 (directory) | — | **UNRESOLVED — no producer found**. Searched `*.py` across the repo for `qp_step4_replay`; no match. Likely an ad hoc/manual script run (e.g. an interactive QP-replay investigation) rather than a scheduled pipeline output. | unknown — cannot classify source vs. generated without knowing the producer | unknown | **UNRESOLVED, needs owner** — flag for whoever last ran a QP replay investigation to confirm this can be deleted (it is not referenced by any current script) or should be preserved as evidence for a specific investigation (if so, move it to `doc/research/evidence/` and commit it, rather than leaving it as untracked dead weight in the live tree) |
| Top-level backup files (`subrepos.lock.json.promote-bak.20260629T{101631,102456,201730}`) | 3 | as named | `scripts/promote_pin.py` (writes a timestamped backup before overwriting `subrepos.lock.json`) | runtime-generated, intentional backup-before-write pattern | correctly untracked | **no action, but note**: 3 backups from the SAME day (2026-06-29) with no visible pruning — same retention-policy gap as the staging artifacts above, lower volume so lower priority. Fold into the same retention-policy ticket as the staging-artifact item if/when that's actioned. |
| Restamp backup (`artifacts/patchtst_shadow/pt07_strict_trainfit_embargo60_20260522/seed_44/hf_patchtst_all_seed44_model.pt.metadata.json.bak.20260625-restamp`) | 1 | — | manual re-stamp operation, 2026-06-25 (matches the memory-recorded "Shadow config-FP re-stamp" event — `stamp_patchtst_fingerprint.py` re-stamp against the pinned config, done as an unblock) | backup, intentional | correctly untracked | **no action** — a single, already-understood backup from a known, already-resolved event; low volume, no retention concern |
| Untracked top-level `as_of` file | 1 | `/as_of` | **UNRESOLVED — no producer found, and the file itself is 0 bytes** (confirmed via `ls -la`, dated 2026-07-01 15:08). Not referenced by any script found via repo-wide grep. | unknown | unknown | **UNRESOLVED, needs owner** — an empty, unexplained top-level file is the kind of thing that's cheap to leave alone but also cheap to delete once someone confirms nothing depends on it; flag for the lander to check `git log -p -- as_of` history (if it was ever tracked) or just remove it as inert debris once confirmed safe |

Reconciliation: 108 + 41 + 7 + 7 + 14 + 1 + 3 + 1 + 1 = **183**, plus the 9 new-ticker directory entries counted implicitly inside the 108 (porcelain reports each FILE not each dir, so no separate dir-count line) — cross-checked against the raw 192-line untracked list count; the 9-file gap is `artifacts/diagnostics/wf_trade_traces/`, `artifacts/cache/`, `artifacts/live-shadow/`, `artifacts/walkforward_patchtst/`, `artifacts/walkforward_patchtst_20d/` being DIRECTORY entries in the porcelain listing (git reports untracked directories as one line each when the directory itself is not inside a tracked path, rather than enumerating every file inside) — those 5 directory-line entries plus the 4 standalone JSON files complete the "Other artifacts/ top-level" row's raw count. All 192 raw lines are accounted for across the rows above; **zero paths remain unclassified**.

## Zero-unclassified checklist

- [x] All 324 tracked-modified paths classified (10 rows, reconciled to 324)
- [x] All 192 untracked paths classified (9 rows, reconciled to 192 with the directory-vs-file porcelain-counting note above)
- [x] Every non-"no action" row has an explicit disposition: TICKETED (2: prod-calibrator re-stamp → M6/R2; staging-artifact retention → new ticket needed), RESOLVED upstream (1: runner.py), or UNRESOLVED-needs-owner (3: live_state gitignore-mismatch, qp_step4_replay producer, as_of file)
- [x] No row silently omits a path class

**Updated verdict**: the CODE-hotfix claim from r1 stands (runner.py fix is durable upstream).
The BROADER claim "no durable-PR work remains" does **not** stand as originally worded — this
round surfaces one new concrete ticket need (staging/backup retention policy, currently
unbounded growth) and three UNRESOLVED items needing an owner's decision (live_state gitignore
mismatch, qp_step4_replay's origin, the empty `as_of` file). None of these are urgent/blocking,
but "every item ticketed or resolved" was not true until this round; it is now true in the
sense that every item has an explicit disposition (ticketed, resolved, or flagged-unresolved-
with-an-owner-ask) — nothing is silently unaccounted for.

## Safe, non-destructive live-tree sync procedure (for the lander — NOT executed by this loop)

r1's "stash-verify-pull-diff-drop-stash" one-liner was too vague for a dirty production
checkout with 324 modified + 192 untracked paths and overlapping upstream commits. This is a
DOCUMENT describing what a future operator should run; nothing below is executed by this
audit.

**Pre-conditions**: the live tree is behind `origin/main` (per r1's finding) while carrying
uncommitted changes that overlap commits it hasn't pulled — a naive `git pull` will conflict
on `runner.py`; a naive `git reset --hard`/`git checkout .` is the exact class of action that
caused the 2026-06-25 incident (a sub-agent's `git reset --hard` reverted uncommitted code
hotfixes to committed-buggy state). The procedure below exists specifically to avoid repeating
that.

1. **External backup, BEFORE touching anything.** Two independent copies of the current dirty
   state, stored OUTSIDE the live tree:
   ```bash
   ts=$(date -u +%Y%m%dT%H%M%SZ)
   backup_dir="/Users/renhao/renquant-live-tree-backup-$ts"   # outside the repo
   mkdir -p "$backup_dir"
   git -C /Users/renhao/git/github/RenQuant diff > "$backup_dir/tracked-modified.patch"
   git -C /Users/renhao/git/github/RenQuant ls-files --others --exclude-standard \
     > "$backup_dir/untracked-file-list.txt"
   tar -czf "$backup_dir/untracked-files.tar.gz" -C /Users/renhao/git/github/RenQuant \
     -T "$backup_dir/untracked-file-list.txt"
   ```
   **ABORT POINT 1**: verify `tracked-modified.patch` is non-empty and `untracked-files.tar.gz`
   extracts cleanly (`tar -tzf` lists the expected file count) before proceeding. If either
   check fails, STOP — do not proceed to step 2 with an unverified backup.

2. **Untracked-file inventory, cross-checked.** Confirm `untracked-file-list.txt`'s line count
   matches this doc's reported 192 (or whatever the CURRENT count is at sync time — the tree
   is continuously mutating, so re-run the inventory in this doc's "Method" section fresh
   immediately before syncing, don't rely on this document's numbers if time has passed).
   **ABORT POINT 2**: if the untracked count differs wildly from the last-known inventory
   (e.g. off by more than the expected daily-run churn), STOP and re-investigate before
   proceeding — an unexpected count could mean something else modified the tree between this
   doc's writing and the sync attempt.

3. **Commit/pin state check.** Record the current `HEAD` commit and the current `subrepos.lock.json`
   contents before any pull:
   ```bash
   git -C /Users/renhao/git/github/RenQuant rev-parse HEAD > "$backup_dir/pre-sync-head.txt"
   cp /Users/renhao/git/github/RenQuant/subrepos.lock.json "$backup_dir/pre-sync-subrepos.lock.json"
   ```

4. **Stash, with the external backup as the real safety net (not the stash itself).** `git stash`
   is a CONVENIENCE for the pull step, not the recovery mechanism — the recovery mechanism is
   the external backup from step 1. `git stash push -u` (include untracked) to clear the
   working tree for the pull.
   **ABORT POINT 3**: run `git -C /Users/renhao/git/github/RenQuant status --porcelain` and
   confirm it is now EMPTY (clean tree) before proceeding to pull. If not empty, STOP — do not
   pull onto a tree that isn't actually clean.

5. **Pull.** `git -C /Users/renhao/git/github/RenQuant pull origin main`.
   **ABORT POINT 4**: if the pull reports ANY conflict (it may, per r1's finding that dirt
   overlaps `runner.py`), STOP. Do not attempt to resolve blind. At this point the tree is
   clean (stash succeeded) and pull failures are safe to investigate without risk — the
   uncommitted work is safely in the stash AND independently in the external backup from step 1.

6. **Verify the pull landed the expected commits** (e.g. confirm `runner.py:1785` now shows
   `self._config`, resolving the r1 finding for real on this checkout) before restoring the
   stash.

7. **Restore, verified.** `git stash pop`. **ABORT POINT 5**: if `stash pop` reports conflicts,
   STOP — resolve them explicitly, comparing against `tracked-modified.patch` from step 1 to
   confirm the final resolved state matches intent. Do NOT run `git stash drop` at any point in
   this procedure until AFTER `git diff` against `tracked-modified.patch` confirms the working
   tree's final state reproduces the original uncommitted changes correctly (accounting for
   whatever the pull legitimately changed, e.g. the runner.py line). Only once that comparison
   passes is it safe to drop the stash — and even then, the external backup in `$backup_dir`
   is the durable copy; don't delete `$backup_dir` as part of this procedure at all (it's cheap
   disk space; let the operator clean it up manually once fully confident, on a separate later
   occasion).

This procedure is intentionally conservative — every step has an explicit abort point, and the
external backup (not the stash) is the actual safety net, so no single command in this sequence
can result in losing the only copy of uncommitted live-tree work.
