# Progress: GOAL-2v3 intraday-granularity design

Date: 2026-08-27. PR-carried progress doc for
`doc/design/2026-08-27-goal2v3-intraday-granularity.md`.

- Operator directed the granularity fork (verbatim 「go」, 2026-08-27),
  consistent with the original GOAL-2 spec's explicit 10-minute clause.
- Measured substrate: Alpaca IEX 10-min bars from 2020-07-27 (free, probed);
  rq105 tick plane live since 2026-07-02 (serving parity).
- Windows declared: dev 2020-08..2024-06 (contains the 2022 bear); eval
  2024-07..2026-06 sealed. The daily-panel line is formally closed by this
  (its 2020-23 eval can no longer run uncontaminated) — both daily routes
  were already dead on their own evidence; the trade is on the record.
- Stage I-0 is the front-loaded kill point: coverage census + IEX drift
  validation + ESS table; KILL if BEAR n_eff < 30 blocks at h=13.
- No transformer before a base passes; no serving/live-flip content here.
