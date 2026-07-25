# 2026-07-25 — VERDICTS row: objective-blend confirmatory CONFIRMED (cross-repo)

STATUS:    WITHDRAWN — row deferred pending durable evidence (round-4 finding below);
           `VERDICTS.md` is now byte-identical to `main` (no row added). This PR is
           kept open as the record of the attempt and the blocking reason, not as a
           pending ledger change.
WHAT:      Was: one row in `doc/research/VERDICTS.md` registering the
           renquant-model#68/#70 confirmatory verdict, per the ledger contract ("every
           new verdict memo adds its row"; the memo lives cross-repo per the
           model-training boundary). Now: the row has been REMOVED from this PR's diff
           (round-4 fix below) — its evidence source, renquant-model#70, closed
           unmerged during this fix cycle, so the row's cited evidence is not durable
           and the ledger contract ("a row changes ONLY via a PR that carries the
           evidence for the change") is not satisfiable from a closed branch.
WHY/DIR:   `VERDICTS.md`'s own header states the contract this row fulfills: "Owned by
           the S-REL program ... Every new verdict memo adds its row in the same PR."
           Per the model-training repo boundary the underlying study lives in
           renquant-model (#68/#70), not here, but the ledger is this orchestrator's
           single cross-repo index of every standing verdict regardless of which repo
           owns the study — without this row the confirmatory result would be
           discoverable only by reading renquant-model#68/#70 directly. This is a
           ledger-contract row, not a workstream open/close/redirect, so no MID-tier
           edit is needed beyond it (SOP-M only triggers on workstream state changes).
EVIDENCE:  historical — describes the withdrawn row, not a live claim.
  artifact:      renquant-model `doc/research/evidence/2026-07-25-objective-blend/`
                 (screen-six-arm-result.json + confirmatory-result.json), results memo
                 `doc/research/2026-07-25-objective-blend-confirmatory-results.md` —
                 both lived only on the now-closed renquant-model#70 branch; NEITHER
                 is present on renquant-model's `main` (verified: `git ls-tree -r
                 origin/main` finds no `2026-07-25-objective-blend-confirmatory-
                 results.md` and no `confirmatory-result.json` under
                 `doc/research/evidence/2026-07-25-objective-blend/`, only the
                 model#68 prereg + `screen-six-arm-result.json`)
  prod or exp:   EXPERIMENT (read-only research harness); no production surface touched
  existing data: prereg frozen pre-run (model#68, MERGED to renquant-model main);
                 results (model#70) CLOSED unmerged 2026-07-25T08:43:43Z, ~2s after
                 #68 merged — the aggregate-only, non-replayable confirmatory-result.json
                 this row would cite never landed on any accepted branch
  best-known?:   n/a — withdrawn pending durable evidence
  scope:         n/a — withdrawn pending durable evidence
NEXT:      Re-add this row only once the objective-blend confirmatory result is
           committed through an ACCEPTED (merged) renquant-model results PR —
           either model#70 reopened and restacked on the merged #68, or a fresh
           results PR — carrying a replayable bundle against #68's bundle-capable
           executor (`ceac403`+), per the round-4 review's explicit instruction. The
           row must be added in the same evidence-carrying PR or one that includes
           that immutable evidence reference — not by re-citing a closed branch.

## Round 3 review finding addressed

MED — the ledger row's bolded `**CONFIRMED**` verdict, read together with "Consequence
per frozen prereg: SHADOW design PR only," promoted a conclusion beyond what the
committed (aggregate-only, non-replayable) evidence in model#70 supports — even
though this doc's own EVIDENCE block already disclosed the gap. Mirrored model#70's
own round-3 fix in the same cycle: reworded the `VERDICTS.md` row's Verdict cell to
`CONFIRMED per the frozen numeric rule (PROVISIONAL AS A DECISION — non-replayable
evidence)`, gated the shadow-design-PR consequence on a replayable rerun in both the
Verdict and Reopening-condition cells, and added the non-replayable-bundle fact to
the Evidence-boundary cell. The frozen numeric result itself is unchanged.

## Round 4 review finding addressed

BLOCKER — the revised (round-3) wording no longer authorized shadow deployment, but
the review held the row still cannot merge: the ledger contract requires a
row-change PR to carry durable evidence for the change, and this row's cited
source, renquant-model#70, is CLOSED and unmerged — its aggregate confirmatory-result
artifact is not present in the model default branch or in this PR, so referencing a
closed branch is not a durable evidence record. Verified independently: `git fetch`
+ `git ls-tree -r origin/main` on renquant-model confirms neither
`2026-07-25-objective-blend-confirmatory-results.md` nor
`confirmatory-result.json` exists on that repo's `main` — only #68's prereg content
(merged) is present. This is not a wording problem the three prior rounds' softening
could fix; it is an evidence-availability gap that requires either reopening/
restacking #70 with a replayable bundle or a fresh results PR, neither of which is a
"smallest correct fix" achievable in this fix cycle (re-running the 10-seed
confirmatory panel is multi-hour compute, and this workflow does not merge/reopen
PRs). Took the review's only remaining instruction: removed the row entirely from
`VERDICTS.md` (now byte-identical to `main`, verified via `git diff origin/main --
doc/research/VERDICTS.md`) rather than further rewording a row whose underlying
evidence does not durably exist. Rewrote STATUS/WHAT/EVIDENCE/NEXT above to record
the withdrawal and the exact re-add condition instead of describing a live ledger
change.

Tests: none — this PR touches only `doc/research/VERDICTS.md` (now a no-op diff
against `main`) and this progress doc.

## Amendment (same day): second row — factorial H×F×R NULL ×7

Same-day addition to this ledger PR: the factorial (model#67 frozen law,
model#72 results) returned NULL on all seven registered tests; the frozen
consequence rehabilitates the earlier OFAT conclusions. Evidence and
run-integrity disclosures (run-1 quarantine, model#71) live in
renquant-model; this row keeps the ledger single-source.
