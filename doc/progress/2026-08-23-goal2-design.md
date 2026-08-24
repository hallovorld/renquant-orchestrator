# GOAL-2 design: conditional blend weights

STATUS:   design PR only — no code, no config, no deploy.
WHAT:     doc/design/2026-08-23-goal2-conditional-blend-weights.md. Meta-learner
          = per-leg weights w(state) on the existing z-blend; 60d horizon;
          Stage 0 is ESS-first with a hard kill (n_eff<12 at h=60 ⇒ stop);
          Stage 1 = simplest conditional model under prereg + placebo; capacity
          models only on survival.
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
  scope:        design only.
REVIEW:    codex (haorensjtu-dev).
