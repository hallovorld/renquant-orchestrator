# 2026-08-04 — the stranded 2026-07-23 G4 report, archived as an UNREPRODUCED historical claim

STATUS:    archival commit; the inner document is added byte-untouched,
           and THIS record is the authoritative label for what it now is:
           **an unreproduced historical claim with partial surviving
           evidence** — NOT a currently-verifiable verdict.
WHAT:      doc/research/2026-07-23-g4-ensemble-AUTHORITATIVE.md + the
           three files that survive beside it (h2_ensemble_FIXED_results
           .json, patchtst_existence_FIXED_results.json,
           runner_h2_ensemble.py, 16K total), found 2026-08-04 during
           worktree hygiene sitting UNTRACKED and byte-identical in two
           dead worktrees (wt-cutindep, wt-lanepre) — written 07-23,
           never committed.
WHY UNREPRODUCED (the honest inventory, codex #778 round 1):
           - The report cites evidence that is NOT in this payload and no
             longer exists anywhere on the machine: a full-disk search
             for xgb_existence_results.json and panel_provenance.json
             found nothing (the July scratchpad they lived in was
             deleted); the referenced score frames are likewise gone.
           - The surviving runner hard-codes that deleted /private/tmp
             scratchpad and machine-specific absolute paths — it is a
             provenance exhibit, not a runnable replay.
           - The inner document's own "3-way cross-audited /
             AUTHORITATIVE" framing therefore CANNOT be re-verified from
             this payload. The title word "AUTHORITATIVE" is part of the
             preserved historical bytes, not this archive's claim.
STANDING:  Its disposition ("KILL G4, bounded reopening path", the
           XGB+PatchTST two-expert screen) is a 07-23 claim to be read
           against the later record: #569 KILL independently re-derived
           as WEAKENED (checkpoint mis-attribution) and reverted by
           #570; the 08-01 double-audited premise re-assessment reached
           the compatible "zero components clear verified-edge +
           served-fresh"; PatchTST RETIRED 08-02; GOAL-8 (08-03)
           supersedes the premise with a DIFFERENT second expert (slow
           momentum, ρ=+0.23 vs prod). Nothing downstream cites this
           document as binding; it does not bind the GOAL-8 ladder.
WHY KEEP IT AT ALL: it is the only record of what the 07-23 audit arc
           concluded and how; deleting it would erase the trail the
           WEAKENED/revert history refers to. Preservation ≠ endorsement.
EVIDENCE:  both stranded copies byte-identical (diff -rq clean); absent
           from origin/main; full-disk search for the two missing
           evidence files returned nothing (2026-08-04).
NEXT:      none — archival. The two source worktrees are removed after
           this PR merges.
