# BULL_CALM momentum admission guard (#51) — design for review

STATUS:   design PR (research doc only — NO pipeline/production change). For operator review
          before any implementation, same discipline as the mu-floor plan.
WHAT:     `doc/research/2026-06-24-bull-calm-momentum-admission-guard.md`. Proposes a
          regime-gated, default-OFF + WARN-first admission veto: in BULL_CALM, veto candidates
          below the 10th momentum percentile (mom60 = -ROC60), evaluated alongside (not
          replacing) the existing ConvictionGateTask / mu_floor / #145 demean.
WHY-DIR:  the vol-tilt model parks low-momentum NFLX/ZM-type names in BULL_CALM; data shows
          those names reliably underperform there → a cost-aware admission veto (the entry-filter
          lever #186 endorses), not new alpha.
EVIDENCE: per-regime placebo-clean momentum IC: BULL_CALM +0.0166 (weak, below the ~0.036
          floor), BEAR −0.32, BULL_VOL −0.047 — momentum only helps in BULL_CALM. The decile
          table is the real justification: BULL_CALM median fwd_60d_excess rises monotonically
          from −0.107 (bottom mom decile) to +0.021 (top). `[VERIFIED — /tmp/ren51_momentum.py]`
CAVEATS:  IC is below the leakage floor (weak ranking power); the decile MEAN spread is
          outlier-driven (robust signal = bottom-decile median underperformance, not a smooth
          gradient). Prior: fundmom REJECTED (#177); price trend-scan caveated-promising (#176).
ANTI-CF:  percentile set by where forward returns turn negative in the decile table (bottom
          decile), universe-relative + name-agnostic — NOT reverse-engineered to exclude NFLX/ZM.
NEXT:     operator reviews this design. If approved → implement the default-OFF veto in
          renquant-pipeline + the admitted-set placebo-clean validation (≥5 seeds) BEFORE any
          strategy-104 enable. Ships dark; WARN-mode shadow first.
