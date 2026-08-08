# The allocation machine — generative redesign, three layers

STATUS:    design. Supersedes the offline routing-table FRAME as the target
           architecture (the gate machinery is retained, demoted to
           promotion-guard duty). Nothing deployed.

WHAT:      doc/design/2026-08-08-allocation-machine.md — three layers:
           L1 deployment controller (exposure = f(vol, regime posterior);
           ships first; solves the measured ≈$4,820/yr cash drag BY DESIGN and
           moves G-B to the size dial), L2 online expert allocation
           (Hedge/EG over the registry experts' paper books, champion floor
           w_panel >= 0.5, regret bounds replace unreachable offline power;
           the weight state IS the routing table, alive), L3 meta-label
           entry filter (the repo memory's own "honest win-rate lever",
           foundation already merged).

WHY/DIR:   Operator rejected the defensive frame: two days of kill-machinery
           and an all-panel table. The critique is accepted in the doc's §0:
           a frame that demands offline per-cell proof from a history that
           cannot supply it (regime n_eff 2-4) only ever outputs "no". The
           redesign uses the standard advanced moves that need LESS data:
           condition on what is predictable (vol/regime persistence),
           allocate adaptively under regret guarantees, filter with
           trade-outcome labels.

EVIDENCE:  artifact:      committed records, exact paths. AGAINST the old
                          frame:
                          doc/research/2026-08-08-pocket-layer-return-space.md
                          §2 r3 — mean cash 78.0% (median 80.2%), ≈$994
                          missed on the 62-day window ⇒ ≈$4,820/yr on the
                          $10,961.59 book [VERIFIED — prior work,
                          script-measured from live_state_snapshots];
                          doc/design/2026-08-08-routing-table-v0.md — 120
                          cells, 0 with |t| ≥ 2, strongest t = +0.76
                          [VERIFIED — prior work];
                          doc/research/2026-08-08-moe-s10-confirmatory-kill.md
                          — the 75/25 blend sign-reverses out of sample
                          [VERIFIED — prior work]. FOR the layers:
                          the survey inlined in the design doc §0 (arXiv:2207.07578, arXiv:2603.13252, MarketRegimeNet) —
                          AlphaMix two-stage MoE = L2's shape, Two-Level
                          Uncertainty 2025 = L1's shape; and
                          doc/memory/mid-term/win-rate-payoff.md — names a
                          meta-label entry filter as the next lever
           prod or exp:   experiment — design only
           existing data: no exposure controller exists (exposure is an
                          accident); shadow lanes already produce the paper
                          P&L L2 consumes; meta-label exit foundation merged
           best-known?:   yes — first generative architecture doc; knowledge
                          anchors tagged as such (Moreira-Muir 2017,
                          Barroso-Santa-Clara 2015, Hedge/EG, AFML
                          meta-labeling), distinct from in-repo VERIFIED tags
           scope:         design doc + this record. orch#917 (BEAR exit
                          prereg) demoted to complementary line, stays open.

TESTS:     none — architecture. Each layer carries a constructive floor
           (E_min/E_max clip; champion floor; shadow-first) rather than a
           significance claim.

NEXT:      L1 spec + 1910-day evaluation (frozen parameters, return-space
           report, #913 reproducibility standard) — the measured dollar
           value of designed exposure, then the proposal to the operator.
