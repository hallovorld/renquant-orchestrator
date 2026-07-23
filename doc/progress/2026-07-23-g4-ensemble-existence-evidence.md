# 2026-07-23 — GOAL-4 existence screen: both experts placebo-clean null (PR #569)

STATUS:    delivered
WHAT:      Runs the merged generic `tiered_screen` primitive (#568) as a
           preregistered Tier-0/Tier-1 existence screen for the GOAL-4
           two-expert (XGB + PatchTST) ensemble pitch. Tier-0 positive
           control passes on real data (injected rho=0.8 -> real_ic 0.717).
           Tier-1 (leakage-correct single split @ 2023-01-01, placebo =
           shifted label at 2x horizon) finds both experts placebo-clean
           null at every horizon in {5,20,60}d, with confirmed (powered)
           nulls at 5d (K=163) and 20d (K=39). Verdict: KILL GOAL-4 — two
           individually-null experts cannot ensemble into signal.
WHY/DIR:   GOAL-4's flagship premise (ensembling XGB + PatchTST) requires
           at least one expert to clear its own placebo floor. This closes
           the 2026-07-16 Phase-0 "evidence-blocked" status with a real,
           powered measurement instead of leaving it open indefinitely.
           Built on #568's generic primitive rather than duplicating
           statistics; no production path touched.
EVIDENCE:
  artifact:      doc/research/evidence/2026-07-23-g4-ensemble/{panel_provenance.json,
                 xgb_existence_results.json, patchtst_existence_results.json}
  prod or exp:   experiment (research existence screen; no model promoted or
                 deployed, no production path written)
  existing data: consistent with the standing "XGB null at 60d" finding (3
                 prior independent lines) and the 2026-07-16 Phase-0
                 "evidence-blocked" audit; this is the first leakage-clean,
                 powered measurement at 5d/20d for both experts.
  best-known?:   n/a — this is a KILL (non-existence) verdict, not a
                 beats-prior-best claim. Both experts' clean IC (0.002-0.004,
                 one negative at 20d PatchTST) sit inside the leakage/noise
                 floor, below every Bonferroni lower bound.
  scope:         "single-split, single-seed, gross rank-IC existence screen
                 (research artifact, not prod), powered at 5d/20d,
                 underpowered at 60d. Kills the GOAL-4 two-expert ensemble
                 pitch specifically. Does NOT satisfy the >=5-seed
                 diagnostic doc/memory/mid-term/model-edge.md NEXT requires
                 before closing/switching the primary-strategy architecture
                 — see doc §10 for the explicit reconciliation."
  `[VERIFIED — doc/research/evidence/2026-07-23-g4-ensemble/*.json, reproducible
  via the two committed runner scripts against the content-hashed panel]`
NEXT:      Reopening GOAL-4 needs a NEW registration with a materially
           different expert family, feature set, or objective — not a
           re-run of these two on this panel. `model-edge.md`'s own
           >=5-seed NEXT item is untouched by this PR and stays open for
           that separate workstream.

## Review round fixes (this push)
- Added `doc/research/2026-07-23-g4-ensemble-existence.md` §9 — an explicit
  §4(b) evidence block for the KILL G4 conclusion (Codex HIGH finding).
- Added §10 — reconciliation with `doc/memory/mid-term/model-edge.md`: this
  screen answers a narrower question (does either expert individually clear
  its placebo floor, for the ensemble pitch) than model-edge.md's >=5-seed
  ask (close/switch the primary-strategy architecture); the latter stays
  open and binding.
- Fixed a stale "(pending)" note in §7 — PatchTST results finished after the
  first commit, both results files are complete.
- Added this progress doc (was missing — Codex BLOCKER).
- Rebuilt the branch as a single clean commit under the PR-owner identity
  (`hallovorld`) with no `Co-Authored-By` trailer and no `claude` bot
  attribution (Codex BLOCKER — mixed branch attribution).

## Review
Not self-merged; Codex review is the merge gate.
