# GOAL-2 design: conditional blend weights

STATUS:   design PR only — no code, no config, no deploy.
WHAT:     doc/design/2026-08-23-goal2-conditional-blend-weights.md. Meta-learner
          = per-leg weights w(state) on the existing z-blend; 60d horizon;
          Stage 0 is ESS-first with a hard kill (n_eff<12 at h=60 ⇒ stop);
          Stage 1 = simplest conditional model under prereg + placebo; capacity
          models only on survival.

          REVISED 2026-08-24 (codex review) — two changes, both narrowing:
          * §4a separates the FEASIBILITY floor (n_eff>=12: can any statistic
            mean anything) from the MODEL-EVALUATION floor (can a conditional
            learner be fitted AND evaluated out of sample). The latter is a
            PRODUCT, not a threshold: (state buckets x folds x min indep obs
            per cell). The design's own tercile shape needs n_eff>=30 at the
            most permissive fold count, and EVERY tabulated configuration
            exceeds 12 — so there is a real band (12 <= n_eff < 20) where
            Stage 0 is measurable and Stage 1 is still not runnable. Clearing
            the feasibility floor no longer authorizes Stage 1.
          * §5a: this design authorizes STAGE 0 ONLY. §5 left the model a
            disjunction ("ridge OR depth-2 xgb") and left folds, the
            regularisation grid, w_max and the numerical meaning of "beats
            uniform" to be settled later — i.e. after Stage 0 had shown the
            data. A label-bearing Stage-1 run now requires a SECOND prereg PR
            that freezes one model, its hyperparameters as literals, the
            buckets/folds/clamp, a numerical criterion with dependence-aware
            inference, and the realized n_eff against the §4a floor.
            The binding constraint: Stage 0's results may NOT be used to choose
            any of those — same corpus, so a rule fitted to its table is a rule
            fitted to the data it will be tested on. If they cannot be
            justified without seeing the table, the corpus is BURNED for
            Stage 1 and the second PR must say so (the orch#993 rule).
WHY/DIR:  operator goal 2026-08-23. The design channels it into the one routing
          hypothesis the frozen gates left alive (slow-state, orch#966) and
          explicitly rejects the 10-minute-data prerequisite: slow conditioning
          variables + 60d label gain nothing from intraday granularity.
EVIDENCE:
  artifact:      the design doc.
  prod or exp:   neither — documentation only.
  existing data: the three fast-routing KILLs (sector 27.8%<33.3%, Spearman
                 −0.185; dispersion contrast negative; GOAL-8 all-arm) and the
                 live ESS measurement (n_eff=2 at h=60, 2026-08-23) are cited
                 from their frozen records, not re-derived.
  best-known?:   yes — fills the reserved blend-weighting slot (MoE AC5) with
                 bounded failure (clamp+renormalise ⇒ uniform ⇒ production).
  scope:        design only, and now explicitly STAGE 0 ONLY — approving this
                PR does not authorize a Stage-1 run (§5a). No code, no config,
                no deploy, no corpus consumed.
NEXT:      Stage 0 only — assemble the meta-panel and MEASURE n_eff at h=60 on
           the backtest corpus (committed script, read-only inputs, descriptive
           output). Then one of three, decided by the measurement and not by
           preference:
           (a) n_eff < 12 → line closed, written up, no Stage 1;
           (b) 12 <= n_eff < the §4a model-evaluation floor for the intended
               shape → Stage 0's table is the deliverable and Stage 1 is NOT
               runnable on this corpus; say so and propose a fresh corpus;
           (c) n_eff >= that floor → open the SECOND prereg PR per §5a, whose
               items 1–4 must be justified WITHOUT reference to Stage 0's
               table, or the corpus is declared burned for Stage 1.
           No Stage-1 run is authorized by this PR under any branch.

REVIEW:    codex (haorensjtu-dev).
