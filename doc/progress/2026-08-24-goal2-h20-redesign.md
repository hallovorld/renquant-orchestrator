# GOAL-2 h=20 redesign: the new estimand, through the front door

STATUS:   design PR only. Supersedes the killed h=60 line per its own kill
          text ("a shorter horizon is a NEW estimand requiring review").
WHAT:     doc/design/2026-08-24-goal2-h20-redesign.md, v2 after review.
          Horizon grounded in realized holds measured first (live median 10d;
          sim 25d). Stage 0b REDESIGNED PIT-SAFE after codex caught score
          leakage in v1 (today's artifacts would place evaluation dates inside
          their own training windows; placebo/gap-blocking cannot detect
          upstream leakage — Stage 1 would have measured memorization):
          study-only leg REPLICAS trained once at a frozen 2023-12-29 cutoff,
          per-row artifact identity + cutoffs recorded, availability check
          (0b-α) with its own kill BEFORE any compute, ESS kill on the
          assembled OOS panel. The bar of 12 is re-derived as a
          horizon-independent block-t validity floor, with the h=20 minimum
          detectable effect (~0.52σ at n≈30) stated so an underpowered null
          cannot masquerade as evidence of no effect. The replicas' scope
          limitation is stated: Stage-1 survival re-fits on the live legs'
          own shadow panel before anything ships.
V3 AFTER ROUND-2 REVIEW: recipe SELECTION is itself leakage — the
          legs' recipes were chosen on 2024-2026 outcomes, so a pre-2024
          training cutoff alone just relocates the leak. v3 quarantines
          2024-2026 entirely: train replicas 2016-2019, evaluate EXCLUSIVELY
          2020-2023 (the one window untouched by both weight fitting and
          recipe selection; ceiling ~16 blocks >= bar 12), recipe provenance
          (selection window + the runs that chose it) recorded per leg in
          0b-α with its own kill. The sensitivity rule is EX-ANTE: α, power,
          the MDE formula, and the minimum effect of interest frozen in the
          prereg before outcomes are inspected; every outcome reports
          estimate + interval; nonsurvival is NOT-DEMONSTRATED (or
          UNDERPOWERED-NULL when the preregistered MDE exceeds the minimum
          effect of interest). NO-EFFECT is not an available label — absence
          claims would need a preregistered SESOI + equivalence test, which
          this design deliberately omits (r4, codex). No post-hoc power/MDE
          is computed at all.

WHY/DIR:  operator delegated GOAL-2 design decisions; the h=60 kill left
          exactly one honest continuation and this is it, with the
          multiple-comparisons question answered first and in the open.
EVIDENCE:
  artifact:      the design doc.
  prod or exp:   neither — documentation only.
  existing data: hold_days measurement [VERIFIED — runs DB]; the h=60 kill
                 record and its ceiling numbers cited from #1031, not
                 re-derived.
  best-known?:   yes — accrual alone reaches the bar mid-2027; re-scoring is
                 the only real unlock and was priced in the kill record.
  scope:        design only.
REVIEW:    codex (haorensjtu-dev).
