# Live-tree sync drill — the safe way to bring the umbrella checkout up to origin/main

STATUS: ops runbook (R7's remaining slice; #231 Term PROCESS / floor tier-2). Executed by the
OPERATOR/LANDER only — agents and automation never run git mutations in the live tree (hard
rule; a sub-agent `reset --hard` near-miss and the 2026-06-25 clobber are the case law).
DATE: 2026-07-02
CONTEXT: the live umbrella checkout is routinely BEHIND origin/main while carrying dirt that
can OVERLAP unpulled commits (S11 inventory, 2026-07-02: runner.py residue whose fix is
already upstream). A naive `git pull` conflicts; a naive `reset`/`checkout` reverts live
hotfixes — that exact sequence caused 18 intraday FAILs on 2026-06-26.

## 0. When to run

- **After** the daily 13:55 PT run completes and **outside** market hours (intraday ticks run
  every 12 min during the session). Safe windows: ≥15:30 PT, or pre-market ≤05:30 PT.
- Never while `logs/daily_104/<today>.log` is still growing, and never with a run-lock held.

## 1. Snapshot first (all read-only)

```bash
cd /Users/renhao/git/github/RenQuant
TS=$(date +%Y%m%d-%H%M)
git status --porcelain           | tee /tmp/livetree_status_$TS.txt
git diff                          > /tmp/livetree_diff_$TS.patch
git stash list                   | tee /tmp/livetree_stashes_$TS.txt
git fetch origin main            # updates refs only; touches no files
git log --oneline main..origin/main | head -20
```

## 2. Classify every dirty file (the S11 classes)

| Class | Examples | Resolution during sync |
|---|---|---|
| CODE residue whose content is already upstream | `adapters/runner.py` (verify: `git show origin/main:<file> \| grep <signature>`) | drop local hunk after verifying upstream has it |
| CODE hotfix NOT yet upstream | (none as of 2026-07-02) | STOP — commit it to a branch + PR FIRST, sync after it merges |
| Live-stamped artifacts | `artifacts/prod/*.json` re-stamps | KEEP the working-tree version (the live stamp is the truth; upstream is not) |
| Data churn | LEAN zips, factor/map files | keep working tree; never checkout over them |

**If any dirty file falls in class 2, the drill halts until its PR lands.** That is the whole
lesson of 06-25: dirt that exists nowhere else must become durable BEFORE any tree movement.

## 3. The sync (no reset, no checkout, no clean — ever)

```bash
git stash push --include-untracked -m "pre-sync-$TS"   # recoverable, unlike reset
git merge --ff-only origin/main                         # ff-only: refuses surprises
git stash pop                                           # conflicts? the stash SURVIVES
```

On conflicts: resolve per the class table (class-1 → take upstream; class-3/4 → take stash).
The stash is the rollback — do not drop it for ≥1 week (`git stash list` must show it).

## 4. Verify before the next scheduled run

```bash
grep -n "self._config" backtesting/renquant_104/adapters/runner.py | head -2   # the 06-25 canary
make doctor                                                                     # repo smoke
launchctl list | grep renquant | head            # jobs still loaded, none mid-run
```

Then watch the NEXT intraday tick's log for a clean pass before walking away — the 06-26
failure mode was discovered 18 ticks late.

## 5. Never list (case law attached)

- `git reset --hard` / `git checkout -- <path>` / `git clean -fd` in the live tree
  (2026-06-25 incident; agent near-miss 2026-06-25 #412).
- Overwriting canonical prod inputs (`data/rawlabel.parquet`, 2026-06-17 incident).
- Touching `runtime/.subrepo_runtime` (pinned runtime; pin moves go through promote_pin).
- Running the drill during market hours or a scheduled-job window.
- Any of the above BY AN AGENT: this runbook is operator-only by design.
