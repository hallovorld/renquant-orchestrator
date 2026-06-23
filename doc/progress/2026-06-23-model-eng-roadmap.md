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
NEW:      idiosyncratic-residual neutralization (the cheapest first model move — in-repo
          data, no acquisition; predict the sector+beta-neutralized label); trend-scanning
          + meta-labeling labels (drift-free); analyst-revision/fundamental-momentum factor
          (CONDITIONAL — an external-data acquisition project, not a cheap local experiment);
          diverse-SIGNAL ensemble (only behind the scorer-lineup reopen trigger). Eng:
          self-consistent model bundle + atomic reversible deploy (kills the whack-a-mole).
EVIDENCE: existing-plan survey (Explore agent over RenQuant/orchestrator/model docs) + web
          research on the new directions. The idiosyncratic-residual audit has now been RUN
          on the in-repo panel (recent ~3y, purged 3-fold): XGB on RAW fwd_60d_excess OOS
          IC +0.0321 vs XGB on sector+beta-RESIDUALIZED label +0.0342 (ratio 1.07; worst
          fold −0.009→+0.009) → idiosyncratic alpha SURVIVES neutralization, so a local
          neutralization retrain is the cheap win (still needs the full WF gate to confirm
          BULL_CALM placebo-clean). `[VERIFIED — survey + sources cited in doc + audit run]`
NEXT:     cheapest-first MODEL move = idiosyncratic-residual audit (DONE, positive) →
          neutralized retrain with a drift/momentum control through the full WF gate;
          cheapest-first ENG move = self-consistent bundle build. Analyst-revision stays
          gated on a committed data source; ensemble stays behind the reopen trigger.
