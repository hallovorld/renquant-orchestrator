# 2026-07-25 — VERDICTS: add the two 2026-07-25 rows (conditions now met)

STATUS:    ledger rows only
WHAT:      Adds BOTH 2026-07-25 rows to `doc/research/VERDICTS.md` — objective-blend
           CONFIRMED and factorial NULL×7. The merged #576 deliberately recorded the
           withdrawal/hold instead of rows, with explicit re-add conditions.
WHY/DIR:   Both conditions are now met: model#73 (blend results, replayable bundle)
           MERGED; model#72 (factorial results) MERGED.
EVIDENCE:
  artifact:      renquant-model evidence dirs 2026-07-25-objective-blend/ (bundle) and
                 2026-07-25-factorial-hfr/ (analyzer bundle); both landed via accepted PRs
  prod or exp:   EXPERIMENT records; no production surface touched
  existing data: #576 merged progress doc records the exact re-add conditions
  best-known?:   row text mirrors the accepted memos verbatim in all numbers
  scope:         both rows PROVISIONAL (R1); blend consequence remains shadow-design-only
NEXT:      shadow deployment design PR (unblocked); S-REL queue may pick both rows up.
