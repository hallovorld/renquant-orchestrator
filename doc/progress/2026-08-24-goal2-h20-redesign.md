# GOAL-2 h=20 redesign: the new estimand, through the front door

STATUS:   design PR only. Supersedes the killed h=60 line per its own kill
          text ("a shorter horizon is a NEW estimand requiring review").
WHAT:     doc/design/2026-08-24-goal2-h20-redesign.md. Horizon grounded in
          realized holding periods measured BEFORE any conditional result
          exists (live median 10d n=35; sim median 25d n=5,989) — the 60d
          label was the model's training horizon, not the portfolio's. Adds
          Stage 0b (re-score the 584-date corpus per leg, local compute) with
          its own ESS kill at the same bar of 12, applied to the ASSEMBLED
          panel, not the ceiling.
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
