# Live-tree sync drill runbook — ops doc PR

STATUS:   ops runbook (docs only; operator-executed by design — agents never run git
          mutations in the live tree).
REVISION: r2.
WHAT:     `doc/ops/live-tree-sync-drill.md` — R7's remaining slice (S11 named it the open
          deliverable): the safe sequence for bringing the behind-with-overlapping-dirt live
          umbrella checkout up to origin/main. External verified backup (out-of-repo, content-
          complete) → classify dirt against #241's inventory → stash (convenience buffer, not
          the safety net) → ff-only-merge → `stash apply` by exact OID (never `pop`) with
          path-by-path conflict resolution → explicit retain (no auto-drop) → verify (runner.py
          canary, make doctor, watch the next intraday tick) → never-list with case law (06-25
          clobber, 06-26 18-FAIL discovery lag, 06-17 rawlabel overwrite, #412 agent near-miss).
WHY/DIR:  #231 Term PROCESS / floor tier-2: the undisciplined floor's only remaining
          documented hole was the absence of a written safe-landing sequence — the 06-25
          incident happened precisely because the recovery was improvised. Timing windows
          (post-daily-run, outside market hours), ff-only semantics, and the class-2 HALT
          rule encode the lessons as procedure.
EVIDENCE: S11 inventory (2026-07-02, PR #241, r2: 324 tracked-modified + 192 untracked, zero
          unclassified) for the current dirt classes; #241's own r2 recovery-procedure
          structure (external backup, abort points) reused verbatim rather than re-derived;
          incident case law from the memory records (dates in-doc). [VERIFIED — pure-doc
          change, `python3 scripts/require_progress_doc.py` passes against this diff,
          2026-07-02]
NEXT:     Codex review; the lander uses this runbook for the pending sync (which also clears
          the "pins NOT deployed" WARN); the runbook is referenced from the M9 generated-
          snapshot follow-up so doc and procedure stay linked.

## Round 2 (Codex CHANGES_REQUESTED — three real defects in r1's recovery mechanics)

**Finding.** (1) r1 said the stash must survive ≥1 week but used `git stash pop`, which drops
the stash automatically the instant apply succeeds — the retention guarantee was broken by the
very next command in the runbook. (2) r1's "snapshot" was `git status`/`git diff` output
written to `/tmp` — not durable across reboots, and `git diff` alone omits untracked file
content, so it was never an independent recovery copy. (3) "drop local hunk / take upstream" /
"take stash" is too coarse for a checkout with hundreds of overlapping paths (per #241's
exhaustive inventory, 324 tracked-modified + 192 untracked) — a blanket rule can silently
resolve the wrong side on a specific path. Codex also flagged that this runbook and #241's
independently-derived recovery procedure risked becoming two conflicting protocols for the same
kind of operation.

**Fix.** Rewrote `doc/ops/live-tree-sync-drill.md` around the same structure #241 landed for
its own recovery procedure: an external, out-of-repo, VERIFIED backup (`git diff --binary` +
full `tar` archive of untracked file CONTENTS + status/HEAD/refs/subrepos.lock/stash-OID) is
the real safety net, not the stash; `git stash apply "$exact_oid"` replaces `git stash pop`
(apply never auto-drops); the stash and external backup are both explicitly retained (never
auto-dropped) with a dedicated "retain, don't auto-drop" step; conflict resolution is required
to go path-by-path against the #241 inventory and the external backup, never a blanket
ours/theirs rule; and 7 explicit abort points now cover every stage (backup verification,
classification, clean-tree precondition, ff-only merge landing, restore verification, `make
doctor`, and the first live tick post-sync — the 06-26 lesson that failures were discovered 18
ticks late is now an explicit abort point, not just a "watch for it" note). The runbook now
states plainly that this is the SAME protocol as #241's, scoped to this specific ff-only-sync
operation, rather than an independently-derived one — avoiding the two-conflicting-protocols
problem Codex flagged.

Pure-doc change, no code/tests; verified this repo's progress-doc-schema CI gate passes.

## Round 3 (Codex review — two operational blockers remained, 2026-07-02)

**Finding.** r2 fixed the recovery-mechanism defects, but two operational blockers remained:
(1) this runbook depended on `#241`'s inventory as an unconditionally-trusted classification
oracle, while #241 was itself unmerged and under changes-requested review — an executable
production runbook must not silently trust a disputed document; (2) stash creation was
unvalidated — if `git stash push` reports "No local changes to save" or fails partially,
resolving `stash@{0}` next can capture a PRE-EXISTING, unrelated stash rather than the one the
procedure just tried to create; (3) the backup archive used line-delimited `ls-files`/`tar -T`,
which silently mishandles any untracked filename containing a newline.

**Fix.**
- Added step **2a**: a runtime guard that verifies the #241 manifest (`doc/research/evidence/
  2026-07-02-s11-live-tree-inventory/manifest.json`) actually exists, shows `reconciliation:
  PASS`, and is fresh (age computed from the manifest file's own git commit date — the manifest
  has no embedded generation timestamp, a real gap flagged explicitly rather than silently
  worked around; >7 days old aborts). On any failure, every path is treated as "not in the
  inventory" (the existing STOP row) rather than trusting a stale/missing/unmerged manifest.
  This makes the #241 dependency explicit and verified at execution time, independent of
  #241's actual merge status at any given moment.
- Fixed stash creation (step 3): records a `git stash list` count BASELINE before `stash push`,
  verifies the count actually increased after the push (aborting with a clear message if not —
  covers both "no local changes" and partial-failure cases), and only THEN captures
  `stash@{0}`'s OID — never resolving `stash@{0}` blind or later in the procedure.
- Fixed the backup archive (step 1): `git ls-files -z` + `tar --null -T` throughout
  (NUL-delimited), with a human-readable `.txt` companion listing explicitly marked as
  NOT authoritative for restore/verify; ABORT POINT 1's member-count check now counts NUL
  bytes, not lines, so it doesn't itself inherit the newline-filename bug it's meant to guard
  against.
- Renumbered abort points for clarity: 2a (manifest verification, new), 2b (was 2, clean-tree
  precondition), 3a (stash-creation validation, new), 3b (was 3, tree-clean-before-merge).
  Added 4 new "Never list" entries (§8) for the 3 new failure modes plus their case-law framing.

Pure-doc change, no code/tests; re-verified progress-doc-schema CI gate passes.

## Round 4 (Codex review r4): execution-time regeneration, not a stale-snapshot proxy

**Finding.** `#241` merged to `main` in between rounds — `scripts/s11_live_tree_inventory.py`
became a real dependency instead of a forward reference to an unmerged PR. But round 3's own
freshness check was still wrong on its own terms: checking whether a COMMITTED manifest file's
git commit date is under 7 days old does not prove the manifest matches the live tree's CURRENT
state — the tree mutates continuously (the entire premise of this runbook), so "recently
committed" is not "generated right now." Step 2b also only described "diff current paths against
it" in prose, with no enforceable command.

**Fix.**
- Merged this branch onto current `main` so `scripts/s11_live_tree_inventory.py` is genuinely
  present in this branch's history (not just referenced by name).
- Step 2a (rewritten): stops reading any committed manifest snapshot entirely. Runs the
  classifier FRESH, every execution, via
  `python3 scripts/s11_live_tree_inventory.py --live-tree /Users/renhao/git/github/RenQuant
  --out "$backup_dir/s11-manifest-live.json"` — writing output into THIS run's external backup
  directory (established in step 1), never back into the orchestrator repo. Checks the script's
  own exit code (it raises `AssertionError` and exits non-zero on any unclassifiable path —
  verified this behavior directly against a throwaway test repo, confirming a non-zero exit
  correctly triggers the abort path) and the `reconciliation` field for `PASS`. This makes
  manifest freshness a non-issue by construction: the manifest used for classification is
  generated from the live tree's actual state at the moment this step runs.
- Step 2b (new): adds a concrete, literal Python script (embedded in the runbook, not prose)
  that re-runs `git status --porcelain=v2` immediately after step 2a and asserts the raw path
  set is IDENTICAL to the manifest's `paths[].path` set — catching the case where something
  mutates the live tree in the brief window between manifest generation and use. Verified both
  branches against a throwaway test repo (`/tmp`, never the real live tree): the happy path
  (tree unchanged since manifest generation) reports "Set-equality OK"; the failure path
  (a file added to the tree after manifest generation) correctly aborts with exit 1 and lists
  the specific mismatched path.
- Renumbered/added abort points: 2a (classifier regeneration + reconciliation, rewritten),
  2b(i) (set-equality, new), 2b(ii) (was 2b, clean-tree precondition). Updated the "Never list"
  (§8) to reflect the corrected failure modes (committed-snapshot trust, missing set-equality
  re-check) instead of the now-superseded age-based-freshness entry.
- Updated the PR title/body's DATE/STATUS header and added an "r3 → r4" narrative section
  explaining the change, consistent with the doc's existing r1→r2/r2→r3 sections.
- Updated the PR description (was still r1-era, advertising `stash push`+`pop` even though the
  runbook has used `stash apply` since round 2) to accurately describe the current r4 state.

**Evidence:** embedded Python block in step 2b verified to `compile()` cleanly; set-equality
logic tested end-to-end against a throwaway git repo at a session-scratchpad path (never the
real live tree) — confirmed both the pass case (3/3 paths match) and the fail case (mutation
after manifest generation correctly detected and aborted, exit 1). The classifier's fail-closed
exit-on-unclassifiable-path behavior was also independently confirmed against that same
throwaway repo (generic filenames don't match RenQuant's real classification rules, so the
script correctly raised `AssertionError` and exited non-zero — proving the abort path in step 2a
actually triggers on classifier failure, not just in theory).

Pure-doc change (plus a merge commit pulling in `#241`'s already-merged content), no new
code/tests; progress-doc-schema CI gate re-verified.

## r5 (Codex review): NUL-delimited path parsing, consistently

**Finding.** r4 fixed the stale-manifest problem but introduced a NEW inconsistency: the
backup-archive step (step 1, since r3) is genuinely NUL-safe (`git ls-files -z` +
`tar --null`), but step 2b's set-equality check parsed `git status --porcelain=v2` (no `-z`)
as TEXT — line-split, then last-space-field extraction. That breaks on any path containing a
space, tab, backslash, or literal newline (rare in practice, but a live production tree with
varied generated artifacts is exactly the kind of tree where "rare" isn't "never" — the same
reasoning that motivated the archive step's own NUL-safety in r3). `#241`'s classifier
(`scripts/s11_live_tree_inventory.py`, this step's actual manifest producer) had the identical
defect — same non-`-z` porcelain parsing, plus it flatly REJECTED (raised) on any type-'2'
rename/copy record rather than parsing it. And the archive verification in Abort Point 1
counted `tar -tzf | wc -l` LINES against NUL-BYTE counts — itself line-based, contradicting the
newline-safety it was supposed to confirm.

**Fix.**
- New `scripts/git_status_porcelain.py`: ONE shared, NUL-aware `git status --porcelain=v2 -z`
  parser, reused by both the classifier and this runbook (not duplicated). Correctly handles
  ordinary (`1`), untracked (`?`), and rename/copy (`2`) records — the `-z` format encodes a
  type-'2' record as TWO consecutive NUL-terminated tokens for one logical entry (fields+newPath,
  then a separate origPath token); consuming only one token per record — the bug in every prior
  ad hoc parser here, including the one this fix replaces — silently misparses every rename
  encountered as if its origPath token were the START of the NEXT record.
- `scripts/s11_live_tree_inventory.py` (`#241`, already merged) updated to use the shared
  parser instead of its own line-based one; genuinely classifies rename/copy entries (by their
  new path) instead of raising. 3 new tests: a filename-with-spaces fixture (proves the full
  path survives — a text-mode parser would truncate it), a real `git mv`-staged rename fixture
  (proves the type-'2' two-token record is parsed correctly, not rejected or misparsed), and a
  mixed ordinary+untracked fixture. 17/17 tests pass (was 14).
- New `scripts/s11_verify_set_equality.py`: replaces step 2b's inline ad hoc Python with a real,
  reusable script built on the shared parser. The runbook now calls this script instead of
  embedding its own parsing logic.
- Abort Point 1's archive verification: replaced the line-based `tar -tzf | wc -l` vs NUL-byte
  count comparison with genuine round-trip verification — extract to a scratch directory
  (never the live tree), then compare the actually-extracted file set against the recorded
  NUL-delimited list via Python (`os.walk` + byte-level set comparison — NOT `find | sed`,
  which was drafted first and then caught by direct testing: `sed` operates on newline-delimited
  records, so piping NUL-delimited `find -print0` output through it only strips a per-record
  prefix from the FIRST record, silently leaving every subsequent record's prefix untouched —
  confirmed with `xxd` against a throwaway two-file fixture before discarding that approach).

**Evidence:** all 3 new pieces (`git_status_porcelain.py`, `s11_verify_set_equality.py`, the
archive-verification block) tested end-to-end against throwaway git repos/directories at
session-scratchpad paths — never the real live tree. Confirmed: (a) a filename with a space
survives the classifier's reconciliation intact; (b) a `git mv`-staged rename is parsed as
`rename_copy` with the correct new/orig path pair, not rejected; (c) the set-equality script
passes on a matching manifest and correctly aborts (exit 1, naming the specific mutated path)
when the tree changes after manifest generation; (d) the corrected archive-verification script
passes on a genuine tar round-trip of files with spaces in their names, including a nested
file. 38/38 tests pass across `test_s11_live_tree_inventory.py` + `test_pit_snapshotter_scheduling.py`.

**Follow-up note added to `doc/progress/2026-07-02-s11-live-tree-inventory.md`** (the `#241`
progress doc, now merged) documenting that its classifier's parsing was corrected by this PR,
since the fix touches content that PR introduced.
