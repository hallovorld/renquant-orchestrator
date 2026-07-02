# S11: live-tree dirt inventory — exhaustive, machine-verified classification (read-only audit)

STATUS: **INCOMPLETE** — research evidence / audit record (read-only — no git mutation was
performed in any live or working checkout; `git status`/`diff`/`show`/`ls-files --others` and
read-only `Path.rglob` only). Task S11 of the unified plan (#231 Term PROCESS / floor tier-2).
Incomplete because 4 paths across 3 items are UNRESOLVED pending an owner decision (see below);
S11 does not close until those decisions land or the items are otherwise resolved.

DATE: 2026-07-02 (round 3 — r1's inventory was not exhaustive; r2's was directionally better
but still relied on prose counting that did not mechanically reconcile, per Codex's second
review round. This round replaces prose counting with a machine-generated, programmatically
reconciled manifest.)

## What r1 and r2 got wrong

r1 inventoried 5 items and declared "every item ticketed or resolved" — false, the live tree
carried 516 total changed/untracked paths, most unclassified.

r2 re-inventoried by hand into a 19-class prose table claiming "516 paths exhaustively
classified" with a reconciliation note explaining a 9-path gap as "already counted" elsewhere.
Codex correctly rejected this: a human-written table whose row sums don't cleanly add up to the
raw `git status` count, "reconciled" via prose explaining away the gap, is not actually a
verified bijection — it's an assertion that happens to be closer to true than r1's.

## Method (round 3): a script, not a table

`scripts/s11_live_tree_inventory.py` — reads `git status --porcelain=v2` against the live tree
(read-only), classifies every single raw path into exactly one of 19 classes via ordered regex
rules, and **asserts programmatically** (not narrates) that:
- every raw path appears in the classification (no omissions) — an unmatched path raises
  `AssertionError` and the script exits non-zero; this is not a soft warning,
- no path is classified more than once (no duplicates),
- `raw_path_count == classified_row_count` exactly.

Untracked DIRECTORY entries (git reports a wholly-untracked directory as one line rather than
recursing into it) are classified as a single raw path each; a **supplementary**, clearly
separate `nested_file_count_supplementary` field records how many actual files are inside, for
readability — this count is explicitly NOT part of the reconciliation arithmetic, which is the
exact class of conflation (mixing directory-line counts with nested-file counts in one sum) that
broke r2's reconciliation.

Running the script against the tree's actual current state (this round) initially **failed** —
it caught 38 rollback/staging-variant paths (`panel-ltr.alpha158_fund.weekly_rollback_*.json`,
`panel-rank-calibration.weekly_*.staging.json`, `panel-rank-calibration.*_rollback_*.json`) and
7 WF-eval config paths that r2's prose table had silently missed entirely. The classification
rules were broadened until the reconciliation assertion passed — proof that the exhaustiveness
claim is now backed by a mechanism that actually fails loudly on gaps, not just a claim that
happened not to be tested against a failing case until this round.

**Current reconciliation: PASS.** `raw_path_count = 516` (324 tracked-modified + 192 untracked)
`== classified_row_count = 516`, zero duplicates, zero omissions. Full manifest committed at
`doc/research/evidence/2026-07-02-s11-live-tree-inventory/manifest.json` (per-path: path, XY
status, class, producer, artifact kind, tracked policy, disposition, ticket — 516 rows).
Reproduce: `python3 scripts/s11_live_tree_inventory.py --out <path>`.

## Class summary (19 classes; full per-path detail in the manifest, not here)

| Disposition | Path count | Classes |
|---|---|---|
| `no_action` | 456 | per-ticker model artifacts (tracked, 329), WF-gate GBDT recipe (43), sim calibrators (43), LEAN data (9), strategy_config.json (1), dashboard.md (1), subrepos.lock.json (1), WF-eval experiment configs (7), WF-eval prod-semantic diagnostics (7), other generated artifacts (14), known restamp backup (1) |
| `self_resolving_no_action` | 9 | new-ticker model-artifact directories (9 tickers) — see ticket below, this is genuinely low-priority but now has an explicit tracked item rather than a bare "self-resolving" claim |
| `resolved_upstream` | 1 | `runner.py` hotfix residue — `origin/main:runner.py:1785` already ships the fix; this checkout is behind origin |
| `ticketed` | 46 | prod calibrator re-stamp (2, existing M6/R2 fingerprint-unification item), weekly-promote staging (20, both `panel-ltr` and `panel-rank-calibration` families), weekly/monthly promote rollback snapshots (21 — **a class r2 missed entirely**), `subrepos.lock.json.promote-bak.*` backups (3) — all four staging/rollback/backup classes now point at one real backlog item, `s11-staging-backup-retention-policy` |
| `unresolved_needs_owner` | 4 | `live_state.{alpaca,alpaca_shadow}.json` tracked-vs-gitignore mismatch (2 paths, 1 ticket), `artifacts/qp_step4_replay/` unknown producer (1 path, 1 ticket), untracked 0-byte `as_of` (1 path, 1 ticket) |

## Real dispositions, not prose placeholders

r2 used "new ticket needed" and "unresolved needs owner" as bare prose labels with nothing to
follow. This round adds 5 real items to `doc/roadmap-backlog.json` (this repo's actual backlog
mechanism — verified there was no existing item covering any of these before adding them):

- `s11-staging-backup-retention-policy` — retention/pruning for the 46 ticketed staging/
  rollback/backup paths above.
- `s11-live-state-gitignore-mismatch` — confirm intent on the 2 `live_state.*.json` files.
- `s11-qp-replay-origin` — identify or remove `artifacts/qp_step4_replay/`.
- `s11-as-of-file-origin` — identify or remove the empty top-level `as_of` file.
- `s11-universe-expansion-model-commit` — the 9 new-ticker directories' commit cadence
  (low priority; genuinely self-resolving on the next universe-expansion commit, but now has a
  tracked item rather than an untracked assertion that it's fine).

All 5 are `consequential: false` (no GPU/deploy/strategy/live action implied) and `pending`.

## Verdict

The runner.py CODE-hotfix claim stands: origin/main already ships the fix. "Every item ticketed
or resolved" — r1's original claim — is now genuinely true in the sense that every one of 516
raw paths has an explicit, mechanically-verified disposition, and every non-`no_action`
disposition points at a real backlog item. It is **not** true that S11 is *closed*: 4 paths (3
distinct decisions) remain `unresolved_needs_owner` and require an actual owner decision, not
just a ticket existing. STATUS stays INCOMPLETE until those 3 decisions land.

## Safe, non-destructive live-tree sync procedure (for the lander — NOT executed by this loop)

Unchanged from round 2 (already addressed a separate Codex finding about recovery-procedure
safety; retained in full below for continuity — a companion runbook doc for the actual sync
drill is `renquant-orchestrator#242`, a separate PR aligned with this same procedure).

r1's "stash-verify-pull-diff-drop-stash" one-liner was too vague for a dirty production
checkout with 324 modified + 192 untracked paths and overlapping upstream commits. This is a
DOCUMENT describing what a future operator should run; nothing below is executed by this audit.

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
   matches the CURRENT count at sync time — the tree is continuously mutating, so re-run
   `python3 scripts/s11_live_tree_inventory.py` fresh immediately before syncing, don't rely on
   this document's numbers if time has passed.
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

7. **Restore, verified.** `git stash apply <exact-stash-OID-recorded-in-step-4>` — NOT
   `git stash pop`, which drops the stash immediately on a successful apply with no separate
   verification step. **ABORT POINT 5**: if `stash apply` reports conflicts, STOP — resolve
   them explicitly, comparing against `tracked-modified.patch` from step 1 to confirm the final
   resolved state matches intent. Do NOT run `git stash drop` at any point in this procedure
   until AFTER `git diff` against `tracked-modified.patch` confirms the working tree's final
   state reproduces the original uncommitted changes correctly (accounting for whatever the
   pull legitimately changed, e.g. the runner.py line). Only once that comparison passes is it
   safe to drop the stash — and even then, the external backup in `$backup_dir` is the durable
   copy; don't delete `$backup_dir` as part of this procedure at all (it's cheap disk space;
   let the operator clean it up manually once fully confident, on a separate later occasion).

This procedure is intentionally conservative — every step has an explicit abort point, and the
external backup (not the stash) is the actual safety net, so no single command in this sequence
can result in losing the only copy of uncommitted live-tree work.
