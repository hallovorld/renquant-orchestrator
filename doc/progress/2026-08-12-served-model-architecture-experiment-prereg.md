# served-model architecture experiment — frozen preregistration (orch#799 decider, doc only)

STATUS:    frozen experiment preregistration (design) — commit + codex-approve
           BEFORE any execution. No computation run. This PR changes NO code.

WHAT:      Commit the authored, frozen prereg
           `doc/design/2026-08-12-served-model-architecture-experiment-prereg.md`
           VERBATIM (byte-identical to the authored source — sha256
           `d36033570b6e4a1fe7190394981761a39b959492fca428bb1b3d7408a4ace7a2`).
           It preregisters the empirical decider for orch#799: is the served
           model better as **solo-xgb** (A0 — revert, unblocks the weekly promote
           + the 25-missing-model coverage, no new subsystem) or the **z-blend**
           (A1 current / A2 weight-reoptimised — justifies funding the blend-WF
           subsystem). Primary metric = BEAR-regime paired IC difference vs A0;
           decision rule FROZEN (retain z-blend iff Δ_BEAR ≥ +0.03 & placebo-clean
           & no bull harm; else revert to A0; underpowered → default A0).

WHY/DIR:   The 08-04 z-blend cutover made prod `kind=blend`, which structurally
           broke the weekly xgb promote (orch#799 — the WF gate can only score a
           solo GBDT, not the blend) and left 25/145 watchlist names un-modelled.
           The blend was never validated as OUTPERFORMING solo-xgb OOS. This
           prereg settles that head-to-head by a DATA verdict, not deferral,
           resolving the 8× alarm. It is the sibling decider to the option-B
           reference-rule recommendation (`doc/design/2026-08-11-orch799-blend-prod-reference-rule.md`):
           if A0 wins, that subsystem is moot; if A1/A2 wins, it is justified.

EVIDENCE:
  artifact:      `doc/design/2026-08-12-served-model-architecture-experiment-prereg.md`
                 (the frozen prereg, committed verbatim as authored) + this
                 progress record. No code. [VERIFIED — diff vs authored source
                 EMPTY; sha256 identical both sides.]
  prod or exp:   neither — design only; no confirmatory computation. No
                 live-config / production write. The prereg's own §8.2 gate
                 (feasibility: momentum_residual PIT-computability + actual
                 n_folds + BEAR n_eff) is a SEPARATE read-only investigation
                 that must clear before execution.
  existing data: none read/written for this doc-only PR; the prereg cites the
                 served config's blend structure and the xgb WF manifest as the
                 fold set, to be confirmed by the feasibility gate.
  best-known?:   yes among the framings — 3 arms (A0/A1/A2) keep FWER manageable
                 at policy-grade n; the decision rule and window are frozen here,
                 pre-result, so the verdict cannot be outcome-shopped.
  scope:         "this is the served-model-architecture prereg (frozen design,
                 NOT executed and NOT implemented), vs existing best = orch#799's
                 structural stalemate, which returns no verdict. The estimand is
                 'does the z-blend add genuine, placebo-clean BEAR-regime OOS
                 skill over solo-xgb'. It authorizes no run, no promotion, and no
                 live-config change; execution is gated on this feasibility
                 confirm + codex approval + operator authorization."

TESTS:     none — doc-only PR; no code touched.

NEXT:      (1) feasibility confirm (prereg §8.2, read-only) — momentum_residual
           PIT-computability over the manifest's fold cutoffs + report the actual
           n_folds and BEAR n_eff (if BEAR n_eff ~0, the design is honestly
           under-powered and defaults to A0); (2) codex approval of this frozen
           prereg; (3) execution (isolated, no-spend local compute) of the 3 arms
           + placebos, double-audited; (4) verdict → operator-authorized live
           config change (revert-to-solo-xgb, or keep-blend + fund option A).
