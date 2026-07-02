# S11 live-tree inventory — audit PR

STATUS:   research/audit record (read-only; no git mutation in any live/working checkout).
REVISION: r2.
WHAT:     `doc/research/2026-07-02-s11-live-tree-inventory.md` — the S11 deliverable: every
          live-tree dirt item classified and ticketed or resolved. Headline: the adapter-save
          NameError fix is ALREADY durable (verified umbrella origin/main:runner.py:1785
          ships self._config) — the stale memory claim ("origin/main still ships the
          NameError") is corrected; the local diff is residue on a checkout that is BEHIND
          origin/main. Re-stamp artifact dirt → ticketed to M6/R2 (fingerprint unification).
          Data churn → normal. Backtesting working-copy residue → content already merged
          upstream (#54 etc.); cleanup is a landing action outside this loop's lane.
WHY/DIR:  #231 Term PROCESS / floor tier-2: the undisciplined floor is unbounded until
          live-tree dirt is inventoried; S11's AC ("diff empty or fully ticketed") is met by
          this audit. The one standing risk is documented for the lander: the checkout is
          behind origin/main WITH overlapping dirt — naive pull conflicts, naive
          reset/checkout is the 06-25 incident; the safe-landing drill doc remains R7's open
          deliverable.
EVIDENCE: read-only git status/diff/show outputs quoted in the memo (2026-07-02).
NEXT:     Codex review; lander executes the sync per the standing-risk note; R7's drill doc
          is the remaining open slice.

## ROUND 2 (Codex CHANGES_REQUESTED — r1 inventory was not exhaustive, recovery procedure too vague)

**Finding.** r1's 5-item inventory ("every item ticketed or resolved") did not match the
actual live-tree `git status` — 324 tracked-modified + 192 untracked paths existed, r1 covered
a fraction. Codex named specific missing classes: `live_state` files, `strategy_config.json`,
`doc/dashboard.md`, `subrepos.lock.json`, hundreds of model files, untracked
production/staging/rollback artifacts, diagnostics, QP replay output, watchlist/correlation/
regime artifacts, backup files, an untracked top-level `as_of` file. The recovery procedure
("stash-verify-pull-diff-drop-stash") was also too vague for a dirty production checkout with
overlapping untracked files, and implied dropping the only recovery copy.

**Fix.** Re-ran the inventory from scratch, mechanically, against the tree's current state
(`git status --porcelain=v2`, 324 + 192 = 516 total paths). Every path is now in one of 19
classes (10 tracked-modified, 9 untracked), each with count, representative paths, producer
(traced via repo-wide grep, not assumed), classification (source/runtime-generated/backup),
tracked-vs-untracked policy assessment, and an explicit disposition. Reconciliation counts
confirm 0 unclassified paths.

**New findings from the exhaustive pass** (none present in r1):
- 133 tracked + 77 untracked unique tickers have model-artifact state — the untracked ones are
  9 new tickers not yet in a committed universe snapshot (self-resolving, not dirt).
- 41 untracked weekly-promote staging artifacts spanning ~2.5 weeks with no visible pruning —
  **new ticket needed**: retention policy for the staging pipeline (unbounded growth).
- 3 items are genuinely **UNRESOLVED, needs an owner's decision**, not silently omitted:
  (1) `live_state.{alpaca,alpaca_shadow}.json` are tracked despite a `.gitignore` rule that
  appears intended to exclude them but doesn't match the actual (broker-suffixed) filenames —
  unclear if tracking is intentional; (2) `artifacts/qp_step4_replay/` has no identifiable
  producer anywhere in the current codebase (repo-wide grep found nothing) — likely a manual
  investigation's leftover; (3) a 0-byte untracked top-level `as_of` file with no producer
  found either.

**Corrected recovery procedure.** Replaced the one-line "stash-verify-pull-diff-drop-stash"
with a 7-step procedure whose actual safety net is an EXTERNAL patch+tarball backup taken
BEFORE any git operation (not the stash, which is treated as a convenience for the pull step
only) — with 5 explicit abort points and an explicit rule that `git stash drop` never runs
until the post-pull working tree is verified against the pre-sync backup.

**Updated verdict.** The runner.py CODE-hotfix claim stands. "No durable-PR work remains" does
NOT stand as r1 worded it — one new ticket is needed (staging retention) and 3 items need an
owner's decision. Nothing is silently unaccounted for now; "every item ticketed or resolved"
is corrected to "every item classified, with an explicit disposition — ticketed, resolved, or
flagged-unresolved-with-an-owner-ask."
