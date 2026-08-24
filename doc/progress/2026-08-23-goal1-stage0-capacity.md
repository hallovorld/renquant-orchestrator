# GOAL-1 AC1: the Stage-0 capacity grid, committed and reproducible

STATUS:   delivered (AC1 of orch#1025). Research artifact only — no config, no
          production path, no deploy.
WHAT:     doc/research/2026-08-23-goal1-stage0-capacity.md + the script/grid/
          log/manifest bundle. Headline: cap 8→10 nearly doubles deployment
          (37.0%→61.7% median); the cap stops binding above ~12; integer-share
          tilt worsens with the cap (1.05×→1.24×) while fractional pins ~1.0×.
WHY/DIR:  the model finds 20–27 buyable names per session against 0–4 free
          slots; capacity is the only lever that changes how much model output
          reaches capital. AC3: no cap change ships from Stage 0 — mechanical
          admission only, no return claim.
EVIDENCE:
  artifact:      the bundle under doc/research/data/2026-08-23-goal1-stage0/.
  prod or exp:   exp — read-only against runs.alpaca.db; writes only its own
                 output file.
  existing data: production sizer called directly (no twin implementation);
                 served regime params READ not assumed (first draft assumed
                 0.15/0.10; served BULL_CALM is 0.3/0.0 — recorded in the doc);
                 re-run reproduces the JSON byte-identically [VERIFIED].
  best-known?:   yes for a mechanical screen; the return question is Stage 1,
                 gated on AC2 ESS.
  scope:        research doc + data bundle. Nothing else.
REVIEW:    codex (haorensjtu-dev).
