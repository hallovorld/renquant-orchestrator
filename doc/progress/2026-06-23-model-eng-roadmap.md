# Model + engineering roadmap — restructure (research)

STATUS:   research/strategy doc for discussion (roadmap re-prioritization; not execution).
WHAT:     restructured short/mid/long-term route for the two main-line goals — upgrade
          model capability + raise engineering quality — grounded in existing plans but
          adding research-backed NEW directions.
WHY/DIR:  two findings: (1) the *current* alpha158+fund × 60d-label *stack* has not produced
          a placebo-clean BULL_CALM edge despite extensive work on it (feature pruning,
          σ-wire, macro overlay, asset embeddings, multi-horizon, PatchTST 70/81-trial DOE,
          4 architectures) — evidence *that stack* is tapped, NOT a verdict that all
          incremental work is dead; (2) the 2026-06-23 deploy hit 4 consistency guards by
          hand — engineering fragility taxes every model iteration.
NEW:      drift-free labels (trend-scanning + meta-labeling); analyst-revision/fundamental-
          momentum factor (CONDITIONAL — an external-data acquisition project, not a cheap
          local experiment); diverse-SIGNAL ensemble (only behind the scorer-lineup reopen
          trigger). Eng: self-consistent model bundle + atomic reversible deploy (kills the
          whack-a-mole). NOTE: idiosyncratic-residual neutralization was the proposed cheap
          first move but has now been TESTED AND REJECTED (see EVIDENCE).
EVIDENCE: existing-plan survey (Explore agent over RenQuant/orchestrator/model docs) + web
          research on the new directions. The idiosyncratic-residual neutralization idea was
          run end-to-end and **rejected by the per-regime WF gate**: a cheap aggregate audit
          looked positive, but the decisive per-regime + placebo test showed the momentum/
          drift-neutralized label DESTROYS the BULL_CALM signal (placebo-clean BULL_CALM IC
          raw +0.0240 vs neutralized −0.0291). Full spec/data/folds/outputs + the reversal
          are in the path-pinned record `doc/research/2026-06-23-residual-neutralization-
          evidence.md` (scripts under `scripts/experiments/2026-06-23-*`).
          `[VERIFIED — survey + sources + experiment record]`
NEXT:     cheapest-first MODEL move (residual neutralization) is SPENT — tested, rejected.
          Remaining model frontier: drift-free labels (in-repo) and, conditional on a
          committed data source, the analyst-revision factor; ensemble stays behind the
          reopen trigger. cheapest-first ENG move = self-consistent bundle build (unaffected).
