# Expert naming standard + registry v1

STATUS:    delivered. Design-layer doc only; no artifact renamed (a rename
           would re-stamp every fingerprint for zero benefit).

WHAT:      doc/design/2026-08-08-expert-naming-registry.md — the
           <family>_<method>_<clock> standard, three registration rules, and
           registry v1: four existing experts named (xgb_rank_60d,
           xgb_clf_60d, mom_resid_252, mom_resid_63), three proposed
           (val_yield_252, rev_21, lowvol_63), patchtst retired-for-lineage.

WHY/DIR:   Operator directive: naming must be standardized. The routing table
           (regime x sector -> model) needs stable IDs to reference; the
           312-cell cube and all future shadow lanes use these IDs only.

EVIDENCE:  artifact:      the four live artifacts' own fields (label_col,
                          params_version) read this session
           prod or exp:   experiment — documentation layer
           existing data: no naming convention existed; four artifacts carried
                          four unrelated naming styles
           best-known?:   yes — first canonical registry
           scope:         one design doc; zero production surface.

TESTS:     none — a registry. Its contract is rule 2: no unregistered ID may
           enter the routing table.

NEXT:      Run the 312-cell cube (sector x regime x expert, return-space
           metrics + n + adj t per cell, description only) using canonical
           IDs; then update routing-table v0 candidates from the heatmap for
           operator policy picks.
