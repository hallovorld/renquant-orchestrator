# S11 live-tree inventory — audit PR

STATUS:   research/audit record (read-only; no git mutation in any live/working checkout).
          **INCOMPLETE** — 4 paths (3 decisions) remain unresolved-needs-owner; see ROUND 3.
REVISION: r3.
WHAT:     `doc/research/2026-07-02-s11-live-tree-inventory.md` + `scripts/s11_live_tree_
          inventory.py` — the S11 deliverable: every live-tree dirt item (516 raw paths)
          classified via a machine-verifiable script with a programmatic reconciliation
          assertion, not a hand-written table. Headline: the adapter-save NameError fix is
          ALREADY durable (verified umbrella origin/main:runner.py:1785 ships self._config) —
          the stale memory claim ("origin/main still ships the NameError") is corrected; the
          local diff is residue on a checkout that is BEHIND origin/main. Re-stamp artifact
          dirt → ticketed to M6/R2 (fingerprint unification). Data churn → normal. 46 staging/
          rollback/backup paths + 108 new-ticker model files + 3 unresolved items → 5 real
          `doc/roadmap-backlog.json` entries (was prose "new ticket needed" placeholders).
WHY/DIR:  #231 Term PROCESS / floor tier-2: the undisciplined floor is unbounded until
          live-tree dirt is inventoried; S11's AC ("diff empty or fully ticketed") is NOT yet
          fully met — every path has a disposition, but 4 paths (3 decisions) are genuinely
          unresolved pending an owner, so S11 stays open until those land. The other standing
          risk is documented for the lander: the checkout is behind origin/main WITH
          overlapping dirt — naive pull conflicts, naive reset/checkout is the 06-25 incident;
          the safe-landing drill doc is `renquant-orchestrator#242` (separate PR, R7).
EVIDENCE: `python3 scripts/s11_live_tree_inventory.py` against the live tree (read-only) →
          `reconciliation: PASS`, 516/516 paths classified, 0 unclassified; manifest committed
          at `doc/research/evidence/2026-07-02-s11-live-tree-inventory/manifest.json`;
          14/14 tests pass (`tests/test_s11_live_tree_inventory.py`). `[VERIFIED — script run
          against /Users/renhao/git/github/RenQuant live tree, 2026-07-02 this session]`
NEXT:     Codex review; operator decision on the 3 unresolved items (live_state gitignore
          intent, qp_step4_replay origin, as_of origin) closes S11; lander executes the sync
          per #242's runbook once #242 lands.

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

## ROUND 3 (Codex CHANGES_REQUESTED — "516 paths exhaustively classified" not substantiated; prose dispositions not real tickets)

**Finding.** r2's prose table claimed exhaustive classification but the untracked-path row
sums (183) didn't cleanly reconcile to the raw 192-path count — the "9-path gap" was explained
via prose noting some entries were "already counted," which is not a reproducible bijection
from raw `git status` output to classified rows. Also: "new ticket needed" and "unresolved
needs owner" were prose labels with no actual issue/ticket behind them, and the 108 untracked
new-ticker model files were waved away as "self-resolving/no action" without linking real
universe-expansion tracking work.

**Fix.**
- New `scripts/s11_live_tree_inventory.py`: reads `git status --porcelain=v2` against the live
  tree (read-only), classifies every raw path via ordered regex rules into one of 19 classes,
  and **programmatically asserts** `set(raw_paths) == set(classified_paths)` with no duplicates
  — an unmatched path raises `AssertionError` and the script exits non-zero, rather than a
  human explaining away a gap in prose. Running it against the tree's actual current state
  initially FAILED, catching 38 rollback/staging-variant paths and 7 WF-eval config paths r2's
  table had missed entirely; classification rules were broadened until the assertion passed.
  Untracked directory entries get a separate, clearly-labeled `nested_file_count_supplementary`
  field, kept explicitly OUT of the reconciliation arithmetic (the exact conflation that broke
  r2's counting).
- Committed the script's output as a real machine-generated manifest:
  `doc/research/evidence/2026-07-02-s11-live-tree-inventory/manifest.json` (516 per-path rows:
  path, XY status, class, producer, artifact kind, tracked policy, disposition, ticket).
  `reconciliation: "PASS"` is now a field asserted by code, not a claim in the doc.
- New `tests/test_s11_live_tree_inventory.py` (14 tests): reconciliation-assertion behavior
  (passes on a fully-classified synthetic repo, raises on an unclassified path), classification
  rules for the key contested classes (ticker model dirs, live_state, qp_replay, as_of, staging
  vs. rollback distinction, runner.py), the directory-vs-nested-file-count separation, and a
  consistency check on the actually-committed manifest file itself.
- Added 5 real items to `doc/roadmap-backlog.json` (verified no existing item covered any of
  these before adding): `s11-staging-backup-retention-policy` (now covers BOTH the staging
  files AND the newly-found rollback-snapshot class — 46 paths total, not r2's 41), `s11-live-
  state-gitignore-mismatch`, `s11-qp-replay-origin`, `s11-as-of-file-origin`, `s11-universe-
  expansion-model-commit` (the 108 new-ticker files now point at a tracked item instead of a
  bare "self-resolving" claim). All `consequential: false`, `status: pending`.
- STATUS changed to explicitly **INCOMPLETE**: 4 unresolved paths (3 distinct decisions —
  live_state intent, qp_step4_replay origin, as_of origin) require an actual owner decision,
  which having a ticket does not substitute for. S11 does not close until those land.

**New finding from the corrected reconciliation:** the previous "41 staging files" undercounted
— the mechanical pass found 20 staging files (both `panel-ltr` and `panel-rank-calibration`
families, r2 only classified the `panel-ltr` one) PLUS 21 weekly/monthly rollback snapshots
(a distinct, entirely separate class r2 missed) PLUS 3 backup files — 46 total paths under one
retention-policy ticket, not r2's 41 under a narrower one.

Commit: see PR history. Files: `scripts/s11_live_tree_inventory.py` (new),
`tests/test_s11_live_tree_inventory.py` (new),
`doc/research/evidence/2026-07-02-s11-live-tree-inventory/manifest.json` (new),
`doc/roadmap-backlog.json` (5 new items), `doc/research/2026-07-02-s11-live-tree-inventory.md`,
this progress doc.

## Follow-up (post-merge, via #242 r5)

`scripts/s11_live_tree_inventory.py`'s `git status` parsing was NUL-unsafe (line/space-split
text-mode porcelain, and flatly rejected any type-'2' rename/copy record) — the same defect
class `#242`'s sync-drill runbook was independently found to have in its own step 2b. Both are
now fixed together via a new shared `scripts/git_status_porcelain.py` parser (NUL-aware,
correctly handles ordinary/untracked/rename-copy records), landed in `#242`'s r5 round since
that PR already needed the exact same fix and reuse was the whole point of the review finding.
This classifier's own reconciliation guarantee (raw path set == classified path set) is
unaffected — the live tree has had zero renames in every run to date, so this was a latent
correctness gap, not something that changed any PAST manifest's actual output.
