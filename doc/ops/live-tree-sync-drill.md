# Live-tree sync drill — the safe way to bring the umbrella checkout up to origin/main

STATUS: ops runbook (R7's remaining slice; #231 Term PROCESS / floor tier-2). Executed by the
OPERATOR/LANDER only — agents and automation never run git mutations in the live tree (hard
rule; a sub-agent `reset --hard` near-miss and the 2026-06-25 clobber are the case law).
DATE: 2026-07-02 (r3: this runbook depends on #241's manifest as its classification oracle;
#241 is not yet merged and was itself under changes-requested review when r2 landed, so r3
adds a runtime guard — step 2 below — that verifies the manifest's existence, reconciliation
status, and freshness at EXECUTION time rather than trusting it as unconditionally
authoritative. r3 also fixes unvalidated stash creation and non-NUL-safe archiving — see
"r2 → r3" below. r2: corrected the stash-safety and snapshot-independence gaps a Codex review
found in r1; aligned with #241's revised recovery procedure so this repo publishes ONE
recovery protocol, not two).
CONTEXT: the live umbrella checkout is routinely BEHIND origin/main while carrying dirt that
can OVERLAP unpulled commits (S11 inventory, 2026-07-02: runner.py residue whose fix is
already upstream). A naive `git pull` conflicts; a naive `reset`/`checkout` reverts live
hotfixes — that exact sequence caused 18 intraday FAILs on 2026-06-26.

## r2 → r3: what Codex found and why this procedure changed again

r2 fixed the stash-pop/snapshot/blanket-conflict defects, but two operational blockers
remained: (1) this runbook treated `#241`'s inventory as unconditionally authoritative while
`#241` was itself unmerged and under changes-requested review at the time — an executable
production runbook must not trust a disputed document as a silent dependency; (2) stash
creation was never validated — if `git stash push` reports "No local changes to save" or fails
partially, blindly resolving `stash@{0}` can capture a PRE-EXISTING, unrelated stash rather
than the one this procedure just tried to create. r3 fixes both: step 2 now VERIFIES the
manifest (existence, `reconciliation: PASS`, freshness) at execution time and refuses to
proceed on any dirt-classification step if that check fails, regardless of #241's merge
status; step 3 now records a stash-list baseline, requires proof a NEW stash entry was
created, and only then captures its OID — never re-resolving `stash@{0}` blind. The backup
archive (step 1) also switched to NUL-delimited path handling, since a line-delimited
`ls-files`/`tar -T` pipeline silently mishandles any untracked filename containing a newline.

## r1 → r2: what Codex found and why this procedure changed

r1's "stash-verify-pull-diff-drop-stash" one-liner had three real defects: (1) it told the
operator to retain the stash for ≥1 week but instructed `git stash pop`, which drops the
stash automatically the instant the apply succeeds — the retention guarantee was already
broken by the very next command; (2) its "snapshot" was `git status`/`git diff` output written
to `/tmp` — `/tmp` is not durable (cleared on reboot on many systems), `git diff` alone omits
every untracked file's content (a filename list can't restore what it names), so this was
never actually an independent recovery copy; (3) "drop local hunk / take upstream" / "take
stash" as conflict-resolution instructions are too coarse for a checkout with hundreds of
overlapping paths — a blanket rule can silently take the wrong side on a specific path.

r2 fixes all three by adopting the same structure `renquant-orchestrator#241` landed for its
own (broader) live-tree recovery procedure: an external, verified, out-of-repo backup is the
REAL safety net (not the stash), every stage has an explicit abort point, and conflicts are
resolved path-by-path against that backup plus the S11 inventory — never a blanket rule. This
runbook's procedure below is the same protocol, scoped to the specific ff-only-merge/sync
operation this doc covers (#241's version additionally covers general dirty-tree recovery from
first principles; this doc assumes the #241 inventory already exists and is fresh).

## 0. When to run

- **After** the daily 13:55 PT run completes and **outside** market hours (intraday ticks run
  every 12 min during the session). Safe windows: ≥15:30 PT, or pre-market ≤05:30 PT.
- Never while `logs/daily_104/<today>.log` is still growing, and never with a run-lock held.

## 1. External backup, BEFORE touching anything (the REAL safety net)

Two independent copies of the current dirty state, stored OUTSIDE the repo — not `/tmp`, which
is not durable across reboots:

```bash
cd /Users/renhao/git/github/RenQuant
ts=$(date -u +%Y%m%dT%H%M%SZ)
backup_dir="/Users/renhao/renquant-live-tree-backup-$ts"   # outside the repo, durable
mkdir -p "$backup_dir"

git diff --binary                        > "$backup_dir/tracked-modified.patch"   # --binary: text+binary
git status --porcelain=v2                > "$backup_dir/status.txt"
git rev-parse HEAD                       > "$backup_dir/pre-sync-head.txt"
git for-each-ref                         > "$backup_dir/pre-sync-refs.txt"
cp subrepos.lock.json                      "$backup_dir/pre-sync-subrepos.lock.json"

# untracked files: CONTENTS, not just a filename list — a name alone can't restore content.
# NUL-delimited throughout: a line-delimited `ls-files`/`tar -T` pipeline silently mishandles
# any untracked filename containing a newline (rare, but a production tree with varied
# generated artifacts is exactly the kind of tree where "rare" isn't "never" — r3 fix).
git ls-files -z --others --exclude-standard > "$backup_dir/untracked-file-list.nul"
tar --null -T "$backup_dir/untracked-file-list.nul" -czf "$backup_dir/untracked-files.tar.gz"
# human-readable companion listing (NOT used for restore/verify — untracked-file-list.nul is
# the authoritative, NUL-safe source of truth):
tr '\0' '\n' < "$backup_dir/untracked-file-list.nul" > "$backup_dir/untracked-file-list.txt"

git fetch origin main                    # updates refs only; touches no files
git log --oneline main..origin/main | head -20 > "$backup_dir/incoming-commits.txt"
```

**ABORT POINT 1 — verify the backup before trusting it.** Confirm `tracked-modified.patch`
either matches an empty tree cleanly or is non-empty and parses (`git apply --check
"$backup_dir/tracked-modified.patch"` against a scratch clone, or at minimum `patch
--dry-run`); confirm `untracked-files.tar.gz` extracts cleanly and its member count matches the
NUL-delimited entry count (`tar -tzf "$backup_dir/untracked-files.tar.gz" | wc -l` must equal
`tr -cd '\0' < "$backup_dir/untracked-file-list.nul" | wc -c` — count NUL bytes, not lines; the
`.txt` companion is for human inspection only and under-counts if any filename contains a
literal newline). If either check fails, STOP. Do not proceed to step 2 with an unverified
backup — an unverified backup is not a backup.

## 2. Cross-check against the S11 inventory (the classification, not a fresh re-derivation)

**2a. Verify the manifest before trusting it as an oracle (r3 fix).** This step depends on
`#241`'s machine-generated manifest as its classification source of truth. `#241` may not be
merged, and its content is independently reviewed/changed on its own schedule — this runbook
must not treat it as unconditionally authoritative just because it exists on disk. Verify it at
EXECUTION time, every run, regardless of #241's merge status:

```bash
manifest="/Users/renhao/git/github/renquant-orchestrator/doc/research/evidence/2026-07-02-s11-live-tree-inventory/manifest.json"
orch_repo="/Users/renhao/git/github/renquant-orchestrator"

if [ ! -f "$manifest" ]; then
  echo "ABORT: S11 manifest not found at $manifest — cannot classify live-tree dirt. STOP." >&2
  exit 1
fi

reconciliation=$(python3 -c "import json; print(json.load(open('$manifest'))['reconciliation'])")
case "$reconciliation" in
  PASS*) : ;;
  *) echo "ABORT: manifest reconciliation is '$reconciliation', not PASS — the manifest does
not vouch for its own completeness. STOP, do not use it for classification." >&2; exit 1 ;;
esac

# Freshness: the manifest has no embedded generation timestamp (a real gap — flagged, not
# silently worked around), so use the committing commit's date as a proxy. This is weaker than
# an embedded timestamp (a manifest could in principle be regenerated with identical content
# and no new commit) but still catches the common failure mode of a genuinely stale, un-rerun
# manifest.
manifest_date=$(git -C "$orch_repo" log -1 --format=%cI -- doc/research/evidence/2026-07-02-s11-live-tree-inventory/manifest.json)
manifest_epoch=$(date -j -f "%Y-%m-%dT%H:%M:%S" "${manifest_date%%+*}" +%s 2>/dev/null || date -d "$manifest_date" +%s)
now_epoch=$(date +%s)
age_days=$(( (now_epoch - manifest_epoch) / 86400 ))
if [ "$age_days" -gt 7 ]; then
  echo "ABORT: S11 manifest is $age_days days old ($manifest_date) — the live tree mutates
continuously; re-run scripts/s11_live_tree_inventory.py (in the orchestrator repo, read-only
against the live tree) to regenerate before trusting this classification. STOP." >&2
  exit 1
fi

echo "Manifest OK: reconciliation=$reconciliation, age=${age_days}d"
```

**ABORT POINT 2a — do not proceed past this check on any failure.** A missing, non-PASS, or
stale (>7 days) manifest means step 2's classification table below cannot be trusted — treat
every path as "not in the inventory" (the STOP row) until a fresh, verified manifest exists.

**2b. Cross-check the live tree's current paths against the verified manifest.** Re-run `git
status --porcelain=v2` / `git ls-files --others --exclude-standard` fresh (the tree is
continuously mutating) and diff the current path set against the verified manifest's
`class_summary`/`paths` (human-readable summary: `doc/research/2026-07-02-s11-live-tree-
inventory.md`). Every path must fall into one of that manifest's classes:

| Class | Examples | Resolution during sync |
|---|---|---|
| CODE residue whose content is already upstream | `adapters/runner.py` (verify: `git show origin/main:<file> \| grep <signature>`) | drop local hunk after verifying upstream has it |
| CODE hotfix NOT yet upstream | (none as of 2026-07-02, per #241) | STOP — commit it to a branch + PR FIRST, sync after it merges |
| Live-stamped artifacts | `artifacts/prod/*.json` re-stamps | KEEP the working-tree version (the live stamp is the truth; upstream is not) |
| Data churn | LEAN zips, factor/map files | keep working tree; never checkout over them |
| Anything NOT in #241's inventory | — | STOP — this is new dirt the inventory hasn't classified; re-run #241's audit before syncing, do not guess |

**If any dirty file falls in class 2 (or the "not in the inventory" row), the drill halts**
until its PR lands or the inventory is refreshed. That is the whole lesson of 06-25: dirt that
exists nowhere else must become durable BEFORE any tree movement, and dirt that hasn't been
classified must not be moved through blind.

**ABORT POINT 2b — clean-tree precondition.** This step is classification only, no mutation yet;
if anything is unclassifiable per the table above, STOP here, before step 3.

## 3. Stash — a convenience for the pull, NOT the recovery mechanism

The recovery mechanism is the external backup from step 1. The stash only exists to give
`git merge --ff-only` a clean working tree to operate on.

```bash
# Validate creation before trusting stash@{0} (r3 fix): if `stash push` reports "No local
# changes to save" or fails partially, blindly resolving stash@{0} next could capture a
# PRE-EXISTING, unrelated stash rather than the one this run just tried to create.
stash_count_before=$(git stash list | wc -l)

stash_out=$(git stash push --include-untracked -m "pre-sync-$ts")
echo "$stash_out"

stash_count_after=$(git stash list | wc -l)
if [ "$stash_count_after" -le "$stash_count_before" ]; then
  echo "ABORT: 'git stash push' did not create a new entry (before=$stash_count_before,
after=$stash_count_after; output: $stash_out). Resolving stash@{0} now would risk capturing a
pre-existing, unrelated stash. STOP — investigate why nothing was stashed before proceeding
(e.g. the tree may already be clean, or the push may have failed partially)." >&2
  exit 1
fi

# Only capture the OID immediately after a VERIFIED-successful push, before anything else
# (another process, a later step) could push a stash and shift the index.
stash_oid=$(git rev-parse stash@{0})
echo "$stash_oid" | tee "$backup_dir/stash-oid.txt"
echo "pre-sync-$ts" > "$backup_dir/stash-message.txt"
```

**ABORT POINT 3a — a stash was actually created.** If the count check above fails, STOP before
capturing any OID — see the abort message in the script.

Record `$stash_oid` explicitly (a captured OID, not a `stash@{N}` index — the index shifts if
anything else pushes a stash before this procedure finishes). Never re-resolve `stash@{0}`
later in this procedure; always use the captured `$stash_oid`. The stash is a convenience
buffer; it is explicitly NOT dropped automatically anywhere in this procedure — see step 6.

**ABORT POINT 3b — confirm the tree is actually clean before merging.** Run `git status
--porcelain`. It must be EMPTY. If not, STOP — do not attempt `--ff-only` against a tree that
isn't actually clean; investigate why the stash didn't fully clear it before proceeding.

## 4. The merge — ff-only, never a plain pull/merge, never reset/checkout/clean

```bash
git merge --ff-only origin/main
```

`--ff-only` refuses to create a merge commit or silently resolve anything — it either
fast-forwards cleanly or fails loudly. If it fails, the working tree is still clean (the stash
already holds the uncommitted work, independently backed up in step 1) — investigate the
failure without time pressure; nothing is at risk yet.

**ABORT POINT 4 — verify the expected commits actually landed** before restoring the stash:
```bash
git log --oneline -5                                                             # sanity
grep -n "self._config" backtesting/renquant_104/adapters/runner.py | head -2     # the 06-25 canary
```
If the merge failed, or the expected canary line isn't present, STOP. Do not proceed to step 5.
The uncommitted work is safe in both the stash and the external backup; there is no urgency.

## 5. Restore — apply by exact OID, verify, retain explicitly (never `stash pop`)

```bash
git stash apply "$stash_oid"
```

Use `apply`, not `pop`. `pop` drops the stash the instant the apply succeeds, which directly
contradicts any "keep the stash for N days" retention guarantee — r1's exact defect. `apply`
leaves the stash entry intact regardless of outcome, so the external backup AND the stash both
remain available until an operator explicitly confirms it's safe to discard either.

**On conflicts:** resolve PATH BY PATH — for every conflicting path, look it up in the #241
inventory (step 2's table) AND compare the two candidate contents against
`"$backup_dir/tracked-modified.patch"` / the untracked archive before deciding. Never apply a
single blanket "take stash" or "take upstream" rule across all conflicts; different classes in
the same conflict set legitimately resolve in different directions (class 1 → take upstream,
class 3/4 → take the stashed version).

**ABORT POINT 5 — verify the restored tree before touching the stash at all.** Compare the
restored working tree against `"$backup_dir/tracked-modified.patch"` (accounting for whatever
the merge legitimately changed, e.g. the runner.py canary line) and confirm the untracked files
from `untracked-files.tar.gz` are all present with matching content. Only once this comparison
passes does step 6 apply. If it does not pass, STOP — do not drop the stash, do not delete
`$backup_dir`; investigate using the still-intact stash and backup.

## 6. Retain, don't auto-drop

Do not run `git stash drop` as part of this procedure. Leave the stash entry (`$stash_oid`) and
`$backup_dir` in place for at least one week (per r1's original retention intent — now actually
achievable, since `apply` never auto-dropped it). `git stash list` must continue to show it.
Cleanup, if ever done, is a separate, later, explicitly-confirmed operator action — not a step
in this runbook.

## 7. Verify before the next scheduled run

```bash
make doctor                                                                     # repo smoke
launchctl list | grep renquant | head            # jobs still loaded, none mid-run
```

**ABORT POINT 6 — `make doctor` must be clean.** If it isn't, STOP and investigate before the
next scheduled job fires; do not let a broken sync silently reach a live trading job.

Then watch the NEXT intraday tick's log for a clean pass before walking away.

**ABORT POINT 7 — the first scheduled tick after sync must complete cleanly.** If it doesn't,
this is the highest-priority signal in the whole procedure — the 06-26 failure mode was
discovered 18 ticks late specifically because no one was watching the first tick. Do not treat
a clean `make doctor` as sufficient; watch the actual first live tick.

## 8. Never list (case law attached)

- `git reset --hard` / `git checkout -- <path>` / `git clean -fd` in the live tree
  (2026-06-25 incident; agent near-miss 2026-06-25 #412).
- `git stash pop` in this procedure (r1's defect — always `git stash apply "$stash_oid"`
  followed by explicit, later, separately-confirmed retention/cleanup).
- A "snapshot" that isn't a verified, out-of-repo, content-complete archive (r1's defect — a
  `/tmp` status/diff dump is not a recovery copy).
- A blanket ours/theirs conflict resolution across multiple conflicting paths (r1's defect —
  always resolve path-by-path against the #241 inventory and the external backup).
- Trusting the #241 manifest without verifying it at execution time (r3's defect — a missing,
  non-PASS, or stale manifest must halt step 2, never be assumed authoritative because it
  exists on disk).
- Resolving `stash@{0}` without first proving `git stash push` created a NEW entry (r3's
  defect — a "no local changes" or partially-failed push can leave `stash@{0}` pointing at a
  pre-existing, unrelated stash).
- Line-delimited (`ls-files` / `tar -T`) handling of untracked filenames (r3's defect — use
  NUL-delimited (`-z`, `--null`) throughout; a filename containing a newline silently corrupts
  a line-delimited pipeline).
- Overwriting canonical prod inputs (`data/rawlabel.parquet`, 2026-06-17 incident).
- Touching `runtime/.subrepo_runtime` (pinned runtime; pin moves go through promote_pin).
- Running the drill during market hours or a scheduled-job window.
- Any of the above BY AN AGENT: this runbook is operator-only by design.
