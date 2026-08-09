# L2-S backtest executed as frozen — RECORD-ONLY, with the sector table

STATUS:    completed outcome. One execution, zero deviations from the
           merged design (orch#934 + #935).

WHAT:      doc/research/2026-08-09-l2s-backtest.md + committed artifacts
           under doc/research/data/ (derivation, daily CSV with all book
           series and weight paths, full holdings CSV, placebo deltas,
           summary JSON, verifier).

WHY/DIR:   The §4 frozen rule requires all four legs; two failed. Sharpe
           floor and maxDD pass decisively (composite 1.52/−27.6% vs
           global 0.91/−30.1%) but the sector-tilt leg fails (max ending
           non-champion local weight 0.276 < 0.40) and the placebo leg
           fails (real delta +0.605 < permuted p95 +0.818): the
           composite's edge is the BOOK STRUCTURE, not the sector labels.
           The global L2 stands; the per-sector×arm table publishes.

EVIDENCE:  artifact:      2026-08-09-l2s-summary.json [VERIFIED — verifier
                          re-ran every recursion, re-derived every cost
                          from the committed holdings, recomputed legs and
                          verdict; exit 0]. Calendar 541 days
                          2024-01-03..2026-05-14 == #926; substantive
                          invariance gate: rebuilt global gross series
                          reproduce #927's committed CSV day-by-day.
                          Table highlights [VERIFIED — daily CSV]:
                          ai_chip panel 1.96 > slow 1.48 > fast 1.11;
                          datacenter_hw panel 2.49; software/industrial/
                          finance won by slow (1.31/1.52/0.90); consumer
                          supports no arm (≤0.28).
           prod or exp:   experiment — read-only inputs, committed
                          artifacts; no production surface touched
           existing data: #926 replay arms + #927 committed CSV (the
                          invariance ground truth) + pinned sector map
           best-known?:   yes — the record states the two harness defects
                          its own gates caught pre-run (calendar state
                          carry; floored local path + missing lag in
                          controls) and why raw OHLCV digests drift
                          legitimately (appended bars)
           scope:         allocation-level sector question priced; any
                          new sector mechanism = NEW dated design. The
                          global L2 shadow-grant request is unchanged.

TESTS:     data/2026-08-09-l2s-verify.py — exit 0 [VERIFIED — run this
           session]; P0 sweep done pre-publication (no open P0 touches
           this line).

NEXT:      operator reads §3's table (his original MoE question, answered
           at the measurable granularity: the panel already IS the chip
           expert; slow momentum is the broad-sector expert; consumer
           supports nothing). Standing asks unchanged: σ*, L2 shadow-job
           grant, alerts.py sync, #902 disposition.
