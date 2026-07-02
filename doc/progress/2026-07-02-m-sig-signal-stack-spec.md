# M-SIG signal-stack spec — design PR

STATUS:   design / pre-registration scaffold (docs only; each candidate's build lands as its
          own PR citing this table's frozen threshold).
REVISION: r1.
WHAT:     `doc/design/2026-07-02-m-sig-signal-stack-spec.md` — the MID-term IC core (#231
          Term IC): four candidates with estimand, substrate, prior-evidence tier, FROZEN
          individual threshold, earliest test date, and kill condition. C1 estimate-revision
          drift (needs ≥6mo N2 accrual → 2027-Q1); C2 quality composite (re-test justified
          ONLY by the FMP coverage delta ≥20%, else the measured NULL stands); C3
          regime-conditioned RESIDUAL momentum (only the untested residual×regime cell —
          raw momentum NULL not re-litigated); C4 trend-scanning label (#176's
          promote-to-proper-gate result, unlocked by the S1–S3 gate repair). Design rules:
          S5/S8 substrate only, placebo-clean differences only, per-regime cuts mandatory,
          orthogonality measured per pair (extends POC-D), one candidate PR at a time,
          misses recorded-and-dropped.
WHY/DIR:  G106 (≥2 signals ≥0.015, combined ≥0.02) is the plan's central coin flip; freezing
          the thresholds BEFORE any measurement is the prereg discipline (#230 §1), and the
          sequencing note protects against a premature kill: the branch cannot fire before
          C1's accrual window (the strongest, truly-orthogonal leg) has run — killing the
          stack before its best leg is measurable would be a sequencing artifact.
EVIDENCE: #176 trendscan evidence doc (3/3 seeds +0.0149 BULL_CALM placebo-clean, absolute
          ICs embargo-floored); fundamentals_scan + regimemom measured NULLs (scope of what
          is NOT re-tested); POC-D ρ=0.217 stacking math; revision-drift literature (cited
          tier, pre-halved per McLean–Pontiff).
NEXT:     Codex review; C3/C4 build PRs may start Q3 (C4 waits on the S3 placebo-difference
          margin being frozen in the gate-repair PR); C2 waits on the N3 coverage verdict;
          C1 waits on N2 accrual — one more reason the collector/snapshotter installs are the
          binding step.
