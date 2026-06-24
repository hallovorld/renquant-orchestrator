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
EVIDENCE: per-regime placebo-clean momentum IC (independently reproduced 2026-06-24):
          BULL_CALM −0.006 (~ZERO; real +0.037 is entirely leakage, placebo +0.043), BEAR
          +0.026 (n=77d, noisy), BULL_VOL −0.062 — momentum has NO clean ranking power. The
          decile table is the real (and only) justification: BULL_CALM median fwd_60d_excess
          rises monotonically from −0.107 (bottom mom decile) to +0.021 (top), reproduced to
          the digit. `[VERIFIED — reproduced; an earlier draft's IC +0.0166/BEAR −0.32 did
          NOT reproduce and is corrected.]`
CAVEATS:  ranking IC is ~zero (NOT a ranking signal — the guard is a tail VETO only); the
          decile MEAN spread is outlier-driven (robust signal = bottom-decile median
          underperformance, not a smooth gradient). Prior: fundmom REJECTED (#177); price
          trend-scan caveated-promising (#176).
ANTI-CF:  percentile set by where forward returns turn negative in the decile table (bottom
          decile), universe-relative + name-agnostic — NOT reverse-engineered to exclude NFLX/ZM.
NEXT:     operator reviews this design. If approved → implement the default-OFF veto in
          renquant-pipeline + the admitted-set placebo-clean validation (≥5 seeds) BEFORE any
          strategy-104 enable. Ships dark; WARN-mode shadow first.
