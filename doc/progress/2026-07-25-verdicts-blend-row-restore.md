# 2026-07-25 — VERDICTS: factorial row added; objective-blend row STAYS WITHDRAWN

STATUS:    ledger row — factorial only. Objective-blend row NOT re-added (round-5
           codex review, HIGH, on head `04821bd4`; this commit reverts that row).
WHAT:      Adds the 2026-07-25 factorial NULL×7 row to `doc/research/VERDICTS.md`
           (model#72 MERGED; numbers verified verbatim against the merged PR body).
           Does NOT re-add the objective-blend row: the prior commit on this branch
           added it as **CONFIRMED** with stale numbers from the closed model#70 run
           (+0.0552 / [+0.0018,+0.1085] / 10/10 / +0.0095) and claimed the shadow
           deployment design PR was unblocked. Both claims are wrong against the
           actual accepted evidence.
WHY/DIR:   model#73 (results v2, MERGED `2173a157`) is the accepted, replayable-bundle
           PR that satisfies the #576 progress doc's literal re-add condition
           ("an accepted results PR carrying a replayable bundle"). Its *numbers* are
           different from what the reverted commit claimed: diff **+0.0602/60d**, CI90
           **[+0.0116,+0.1155]**, seeds **9/10**, w50 guard **+0.0125** — not the
           stale +0.0552/[+0.0018,+0.1085]/10/10/+0.0095 figures. But the numbers are
           not the blocking problem: model#73's own PR body explicitly states
           **"PR standing: EXPLORATORY / PROVISIONAL (downgraded per review round 2,
           BLOCKER 2)"** because the frozen #68 prereg's screen provenance only covers
           the *component* arms (`rank_pairwise`, `top_decile_clf`, `big_run_clf`,
           `rank_on_20d`) individually — the exact `blend` construction under test was
           never screened before being frozen — and it states **"Consequence:
           WITHDRAWN. No shadow-design PR and no orchestrator ledger VERDICTS row
           re-add are authorized by this PR."** verbatim. A merged, evidence-carrying
           PR that explicitly disclaims authorizing the very re-add this row would
           perform cannot be cited as authorizing it — restating the row with
           corrected numbers would still contradict model#73's own consequence
           clause. Per the round-5 finding's two offered paths ("keep the row
           withdrawn, or restate ... to match the accepted renquant-model#73 scope
           ... exactly"), matching #73's scope exactly means NOT adding a ledger row.
EVIDENCE:
  artifact:      renquant-model evidence dir `2026-07-25-factorial-hfr/` (analyzer
                 bundle, model#72 MERGED); objective-blend evidence dir
                 `2026-07-25-objective-blend/` exists (model#73 MERGED) but its
                 owning PR does not authorize a ledger row
  prod or exp:   EXPERIMENT records; no production surface touched
  existing data: `gh pr view 73 --repo hallovorld/renquant-model` body, verbatim
                 "Consequence: WITHDRAWN..." clause; `gh pr view 72` body matches
                 this row's numbers exactly (anchor +0.0489 vs +0.0488, I1 p=0.83,
                 I2 p=0.97, I3 p=0.53, nontechnical_14 −0.0125)
  best-known?:   factorial row text mirrors the accepted model#72 memo verbatim
  scope:         factorial row PROVISIONAL (R1); blend row remains un-added, not
                 merely re-worded — no shadow-design consequence follows from it
NEXT:      Objective-blend re-add stays gated on a NEW condition set by model#73
           itself: a pre-registered screen of the exact `blend` construction
           (committed evidence), then a re-frozen confirmatory prereg citing that
           screen — only then does the shadow-design PR / ledger re-add come into
           scope. S-REL queue may pick up the factorial row per R1.

## Round 5 review finding addressed

HIGH (codex, head `04821bd4`) — the objective-blend row this branch had added is not
supported by the merged source-of-truth evidence: model#73 downgrades PR standing to
EXPLORATORY/PROVISIONAL, withdraws ledger-row authorization, and corrects the
replayable-bundle numbers to +0.0602/[+0.0116,+0.1155]/9 of 10/+0.0125; this branch's
`VERDICTS.md` restored the row as CONFIRMED with the superseded stale numbers
(+0.0552/[+0.0018,+0.1085]/10 of 10/+0.0095) and its progress doc claimed the row
mirrors the accepted memo verbatim and unblocks the shadow-design PR — both false.
Fixed by removing the objective-blend row from `VERDICTS.md` entirely (verified via
`gh pr view 73` that its own consequence clause withdraws re-add authorization,
independent of which numbers would be quoted) and rewriting this progress doc to
record the actual model#73 standing and the real re-add condition. The factorial row
is unaffected — verified independently against `gh pr view 72` and left as-is.
