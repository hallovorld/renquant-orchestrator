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
