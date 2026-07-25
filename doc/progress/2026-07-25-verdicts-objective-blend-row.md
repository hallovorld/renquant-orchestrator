# 2026-07-25 — VERDICTS row: objective-blend confirmatory CONFIRMED (cross-repo)

STATUS:    ledger row only
WHAT:      One row in `doc/research/VERDICTS.md` registering the renquant-model#68/#70
           confirmatory verdict, per the ledger contract ("every new verdict memo adds
           its row"; the memo lives cross-repo per the model-training boundary).
EVIDENCE:
  artifact:      renquant-model `doc/research/evidence/2026-07-25-objective-blend/`
                 (screen-six-arm-result.json + confirmatory-result.json), results memo
                 `doc/research/2026-07-25-objective-blend-confirmatory-results.md`
  prod or exp:   EXPERIMENT (read-only research harness); no production surface touched
  existing data: prereg frozen pre-run (model#68); run-integrity timeline disclosed in
                 the results memo (first run killed unread after review's executor catch)
  best-known?:   first objective-function change confirmed on this book
  scope:         survivorship panel paired diff; CI lower bound +0.0018 (thin);
                 consequence = SHADOW design only, no production change
NEXT:      shadow deployment design PR (pipeline shadow-scorer line); S-REL
           verification queue may pick the row up per R1.
