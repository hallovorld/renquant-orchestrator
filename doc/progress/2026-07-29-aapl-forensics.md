# Progress: AAPL forensics — the floor logged it, conviction decided it

STATUS:   delivered (forensics doc). Read-only investigation; nothing changed.

WHAT:     `doc/research/2026-07-29-aapl-never-bought-forensics.md`. Traces AAPL
          through the live funnel over 15 sessions to the function and line that
          blocked it each time, plus the deeper cause that would have blocked it
          anyway.

WHY/DIR:  Operator question: AAPL has had a strong run, why did the model never
          buy it. They asked for function level, not a hand-wave.

EVIDENCE: artifact: `RenQuant/data/runs.alpaca.db` (4,774 rows, opened
                    `mode=ro`), `RenQuant/logs/daily_104/2026-07-*.log`,
                    `renquant-pipeline/.../job_panel_scoring.py`,
                    `live/runner.py`. All READ-ONLY.
  prod or exp:      PROD observation. No order placed, no config or artifact
                    changed.
  existing data:    Yes, measured this session. AAPL blocked at
                    `job_panel_scoring.py:2115` in every scored session
                    `[VERIFIED]`; rank 16/72 at best (07-24) `[VERIFIED]`;
                    above the model's own median on 12 of 13 scored sessions
                    `[VERIFIED]`; `mu = +0.0068` vs required `+0.03`
                    `[VERIFIED]`, a 4.4x shortfall `[DERIVED]`; only 2 of 78
                    candidates cleared `mu>=0.03` on 07-28 and 0 of 76 on 07-24
                    `[VERIFIED]`. The adaptive floor was recomputed from the DB
                    and matched the logged value to 3 decimals 15/15
                    `[VERIFIED]` — reproduced, not inferred.
  best-known?:      Yes for the admission plumbing. NOT established: WHY the
                    model's view decoupled from price. That needs feature
                    attribution on the pinned artifact and the per-day feature
                    matrices are not retained.
  scope:            Two docs. No pin advanced, no config edited, no live
                    surface touched.

THREE THINGS THIS RULES OUT:
          * Not "the model disliked AAPL" — it was above the model's own median
            on 12 of 13 sessions; the floor takes only the top ~18%.
          * Not the stale per-ticker model — `bypass_ticker_gate: true` and the
            active scorer is `panel_ltr_xgboost`; the 3.49 Sharpe is a frozen
            legacy tournament.
          * Not the whole-share price bias — AAPL died two tasks earlier every
            session. That bias IS biting (SPG at $236.69 on 07-28 was the only
            name to clear both model gates and was killed by `if shares < 1`),
            but it is not AAPL's cause.

A LEAD I CHASED AND CLOSED:
          `raw_panel` repeats byte-identically on some consecutive pairs, which
          would be a stale feature axis if real. My first measurement said 38.5%
          and was WRONG — polluted by same-date reruns. Deduplicated to one row
          per (ticker, date): 245/2,837 = 8.6% `[VERIFIED]`, clustered on
          weekend/holiday boundaries and hitting many tickers at once. That is
          feature-frame reuse across non-trading days, not staleness. Closed.

THE HONEST NEGATIVE:
          AAPL's `raw_panel` fell from +0.104 (06-26) to -0.199 (07-29), moving
          AGAINST the rally `[VERIFIED]`. A signal story, not a plumbing defect,
          and I cannot attribute it without feature-level work the retained data
          does not support.

NEXT:     The surviving design criticism is in orchestrator#610: a floor at
          mean+1sigma on a Platt-compressed calibrator throttles breadth to ~16%
          regardless of edge, and an absolute mu_floor sits above the
          calibrator's own p90. Whether mu_floor=0.03 is an ECONOMIC or a
          STATISTICAL threshold is the open question.
