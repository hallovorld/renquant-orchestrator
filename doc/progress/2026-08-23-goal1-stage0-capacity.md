# GOAL-1 AC1 v2: the capacity grid, now with production parity

STATUS:   delivered (AC1 of orch#1025), rewritten after codex review of v1.
WHAT:     doc/research/2026-08-23-goal1-stage0-capacity.md + script/grid/log.
          Headline: cap 8→10 doubles deployment (17.3%→32.6% median);
          saturation by ~15; integer tilt 1.28×→1.50× vs fractional 1.00–1.13×.
WHY/DIR:  codex's three findings on v1 were all valid and all fixed by
          MEASUREMENT: (1) production-seam preamble + an era-gated parity block
          proving input parity to 2.3e-5 and zero share mismatches, with every
          set difference annotated by production's own blocked_by; (2) session
          provenance = the provably-unique candidate-bearing live run per date,
          19 violating dates excluded and recorded; (3) required CLI args +
          recorded fingerprints, no workstation paths.
EVIDENCE:
  artifact:      doc/research/data/2026-08-23-goal1-stage0/ (script, grid JSON
                 with embedded provenance + parity, run log).
  prod or exp:   exp — read-only against the runs DB.
  existing data: the config-era discovery (ratio exactly 0.4000 pre-08-04
                 orders, exactly 1.0000 from 08-10) is measured from recorded
                 decision_inputs_json, and dates the max_position_pct 0.12→0.3
                 change to the 08-04 z-blend switch window [VERIFIED].
  best-known?:   yes for a mechanical screen with measured approximation error.
  scope:        research artifact only.
REVIEW:    codex (haorensjtu-dev).
