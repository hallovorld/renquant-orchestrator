# 2026-07-25 — VERDICTS row: objective-blend confirmatory CONFIRMED (cross-repo)

STATUS:    ledger row only
WHAT:      One row in `doc/research/VERDICTS.md` registering the renquant-model#68/#70
           confirmatory verdict, per the ledger contract ("every new verdict memo adds
           its row"; the memo lives cross-repo per the model-training boundary).
WHY/DIR:   `VERDICTS.md`'s own header states the contract this row fulfills: "Owned by
           the S-REL program ... Every new verdict memo adds its row in the same PR."
           Per the model-training repo boundary the underlying study lives in
           renquant-model (#68/#70), not here, but the ledger is this orchestrator's
           single cross-repo index of every standing verdict regardless of which repo
           owns the study — without this row the confirmatory result would be
           discoverable only by reading renquant-model#68/#70 directly. This is a
           ledger-contract row, not a workstream open/close/redirect, so no MID-tier
           edit is needed beyond it (SOP-M only triggers on workstream state changes).
EVIDENCE:
  artifact:      renquant-model `doc/research/evidence/2026-07-25-objective-blend/`
                 (screen-six-arm-result.json + confirmatory-result.json), results memo
                 `doc/research/2026-07-25-objective-blend-confirmatory-results.md`
  prod or exp:   EXPERIMENT (read-only research harness); no production surface touched
  existing data: prereg frozen pre-run (model#68); run-integrity timeline disclosed in
                 the results memo (first run killed unread after review's executor catch).
                 DISCLOSED GAP (added during this fix cycle): the committed
                 confirmatory-result.json predates model#68's replayable-bundle fix and
                 is aggregate-only, not independently replayable — see model#70's
                 progress doc. Still PROVISIONAL for exactly that reason; this row does
                 not upgrade the verification status.
  best-known?:   first objective-function change confirmed on this book
  scope:         survivorship panel paired diff; CI lower bound +0.0018 (thin);
                 consequence = SHADOW design only, no production change
NEXT:      GATED — shadow deployment design PR (pipeline shadow-scorer line) does not
           open until a replayable rerun against model#68's bundle-capable executor
           exists (mirrors model#70's own gated NEXT field, fixed in the same fix
           cycle); S-REL verification queue may separately pick the row up per R1.

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
