# 2026-07-23 — GOAL-4 existence screen: both experts placebo-clean null (PR #569)

STATUS:    delivered
WHAT:      Runs the merged generic `tiered_screen` primitive (#568) as an
           existence screen (hypotheses fixed a priori, but committed in
           the same commit as the results — not a verifiably preregistered
           study, see doc §1) for the GOAL-4 two-expert (XGB + PatchTST)
           ensemble pitch. Tier-0 positive control passes on real data
           (injected rho=0.8 -> real_ic 0.717). Tier-1 (leakage-correct
           single split @ 2023-01-01, placebo = shifted label at 2x horizon)
           finds both experts placebo-clean null at every horizon in
           {5,20,60}d, with confirmed (powered) nulls at 5d (K=163, both
           experts) and 20d (K=39, XGB only — PatchTST's own 20d MDE=0.097
           is not powered by the same bar). Verdict: KILL GOAL-4 — treats
           two individually-null experts as insufficient evidence to fund
           an ensemble; H2 (the paired-ensemble increment) was never
           directly tested (see doc §8).
WHY/DIR:   GOAL-4's flagship premise (ensembling XGB + PatchTST) requires
           at least one expert to clear its own placebo floor. This closes
           the 2026-07-16 Phase-0 "evidence-blocked" status with a real,
           powered measurement instead of leaving it open indefinitely.
           Built on #568's generic primitive rather than duplicating
           statistics; no production path touched.
EVIDENCE:
  artifact:      doc/research/evidence/2026-07-23-g4-ensemble/{panel_provenance.json,
                 xgb_existence_results.json, patchtst_existence_results.json,
                 checkpoints/pt_{5d,20d,60d}/*.pt[.metadata.json]}
  prod or exp:   experiment (research existence screen; no model promoted or
                 deployed, no production path written)
  existing data: consistent with the standing "XGB null at 60d" finding (3
                 prior independent lines) and the 2026-07-16 Phase-0
                 "evidence-blocked" audit; this is the first leakage-clean,
                 powered measurement at 5d for both experts and at 20d for
                 XGB (PatchTST's own 20d MDE=0.097 is not powered by the
                 same bar).
  best-known?:   n/a — this is a KILL (non-existence) verdict, not a
                 beats-prior-best claim. Both experts' clean IC (0.002-0.004,
                 one negative at 20d PatchTST) sit inside the leakage/noise
                 floor, below every Bonferroni lower bound.
  scope:         "single-split, single-seed, gross rank-IC existence screen
                 (research artifact, not prod), powered at 5d for both
                 experts and at 20d for XGB only, underpowered at 60d and
                 at 20d for PatchTST. Tests H1 (individual existence) only
                 — H2 (paired-ensemble increment) was never directly
                 computed; treating two individually-null experts as
                 insufficient to fund an ensemble is an inference, not a
                 test, of H2 (doc §8). Kills the GOAL-4 two-expert ensemble
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

## Review round fixes (round 2, fixed by claude)
- HIGH (reproducibility) — `runner_patchtst_existence.py` read pretrained `.pt`
  checkpoints from an ephemeral `/private/tmp/...` scratchpad not covered by
  this PR's diff or the provenance manifest, so a future reviewer could not
  reconstruct the PatchTST side of the KILL verdict from repo artifacts alone.
  Fixed: committed the 3 checkpoints (`checkpoints/pt_{5d,20d,60d}/`, 984 KB
  total) alongside the runner script, and repointed the script at the
  committed path (no more scratchpad dependency). Verified by re-loading all
  3 checkpoints from the new path — `val_ic` matches the doc's tables exactly
  (0.0465 / 0.1454 / 0.1994).
- MED (overstated power claim) — "powered measurement at 5d/20d for both
  experts" overstated PatchTST's 20d result: its own MDE there is 0.097 (vs
  XGB's 0.047), well above the bar that made 20d "powered" for XGB. Narrowed
  every instance (research doc status line, §8, §9, §10; this progress doc's
  WHAT/EVIDENCE) to "5d for both experts; 20d for XGB only."
- HIGH (KILL inference overreach, H1 vs H2) — the doc treated "both experts
  individually null" as proof the paired ensemble has no edge; that does not
  follow logically (correlated-noise cancellation could in principle reveal a
  combined signal neither expert clears alone), and H2 was never directly
  computed (per-date scores were not persisted by either runner). Fixed:
  research doc §8/§9/§10 now say explicitly that H2 was never tested and that
  the KILL rests on an inference (uncorrelated near-zero individual signals
  are unlikely to combine into a robust one), not a proof — and name the
  cheap precommitted paired-ensemble test as the way to close the gap if
  contested. Did not run that test in this pass (would need a new
  precommitted protocol, which is exactly what finding #2 below flags —
  bolting it on post-hoc here would repeat the same defect).
- Preregistration-claim overreach — the doc called itself "preregistered"
  but protocol and results were committed together in one commit, so a
  reader cannot verify the protocol preceded the observation. Fixed: removed
  "preregistered" from the status line, §8 title, and progress-doc WHAT;
  added an explicit caveat in doc §1 naming this an "existence screen with
  hypotheses stated a priori," not a verifiable preregistration.
- Repo-placement finding (not applied) — a review argued this model-specific
  research belongs in `renquant-model`, not `renquant-orchestrator`. Declined:
  `doc/research/` + `doc/research/evidence/` in this repo already hosts
  dozens of prior XGB/PatchTST-specific research docs and evidence dirs
  (e.g. `2026-06-19-patchtst-edge-recovery-experiment.md`,
  `2026-06-21-xgb-gate-relax-decision.md`, `evidence/2026-06-10-ic-to-pnl-*`)
  merged to `main` under this exact pattern — moving this one PR's artifacts
  would be inconsistent with established, already-merged practice in this
  repo, not a correction of a new mistake. Flagged in the PR comment for the
  reviewer to confirm or override.
- Provenance-manifest-insufficiency finding (not applied) — already argued
  and conceded-in-part in doc §0 (required for a GO, not for a KILL); left
  as the standing disagreement rather than re-litigated here.

## Review
Not self-merged; Codex review is the merge gate.
