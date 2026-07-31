# Progress: AAPL forensics — the floor logged it, conviction decided it

STATUS:   delivered (forensics doc). Read-only investigation; nothing changed.

          CORRECTED 2026-07-29: two counts below were re-derived and did not
          hold (`12 of 13` -> `11 of 13`, `15/15` -> `13/13`). Corrected in
          place. See `doc/progress/2026-07-29-aapl-forensics-count-corrections.md`
          and research doc §0a.

WHAT:     `doc/research/2026-07-29-aapl-never-bought-forensics.md`. Traces AAPL
          through the live funnel to the function and line that blocked it each
          time, plus the deeper cause that would have blocked it anyway. Window:
          all 18 logged sessions 2026-07-06..2026-07-29 plus 2026-06-26; AAPL was
          scored in 13 of them.

WHY/DIR:  Operator question: AAPL has had a strong run, why did the model never
          buy it. They asked for function level, not a hand-wave.

EVIDENCE: artifact: `RenQuant/data/runs.alpaca.db` (241,675 `candidate_scores`
                    rows over 39,728 `pipeline_runs`, opened `immutable=1`)
                    `[VERIFIED-now]`, `RenQuant/logs/daily_104/2026-07-*.log`,
                    `RenQuant/logs/daily_104/2026-06-26.log`,
                    `renquant-pipeline/.../job_panel_scoring.py`,
                    `live/runner.py`. All READ-ONLY.
  reproducer:       `scripts/aapl_admission_forensics.py` re-derives every number
                    below from the DB + the daily logs, never from
                    `strategy_config.json`.
  prod or exp:      PROD observation. No order placed, no config or artifact
                    changed.
  existing data:    Yes, measured this session. AAPL blocked at
                    `job_panel_scoring.py:2115` in every scored session
                    `[VERIFIED-now]`; rank 16/72 at best (07-24)
                    `[VERIFIED-now]`; above the model's own median on
                    **11 of 13** scored sessions `[VERIFIED-now — script]`;
                    `mu = +0.0068` vs required `+0.03`
                    `[VERIFIED-now — required mu_floor re-sourced from each
                    historical run's own ConvictionGateTask log line
                    (mu_floor=0.03 on 13/13 scored sessions, and on all 20 gate
                    lines across all 169 retained logs), NOT today's
                    strategy_config.json — see research doc §0b]`,
                    a 4.4x shortfall `[DERIVED — 0.03 / 0.006836]`; only 2 of 78
                    candidates cleared `mu>=0.03` on 07-28 and 0 of 72 on 07-24
                    `[VERIFIED-now]`. The adaptive floor was recomputed from the
                    DB and matched the logged value to 3 decimals **13/13**
                    `[VERIFIED-now]` — reproduced, not inferred.
  best-known?:      Yes for the admission plumbing. NOT established: WHY the
                    model's view decoupled from price. That needs feature
                    attribution on the pinned artifact and the per-day feature
                    matrices are not retained.
  scope:            Two docs. No pin advanced, no config edited, no live
                    surface touched.

THREE THINGS THIS RULES OUT:
          * Not "the model disliked AAPL" — it was above the model's own median
            on 11 of 13 sessions `[VERIFIED-now]`; the floor took a mean 18.3%
            of the cross-section (range 15.2-22.2%) `[VERIFIED-now]`. The two
            exceptions are 07-06 (43rd pct) and 07-07 (42nd pct).
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
          and was WRONG — polluted by same-date reruns. Deduplicated (last live
          run per (ticker, date), role='candidate'): 254/2,768 = 9.2%
          `[VERIFIED-now]`; first-run tie-break gives 213/2,768 = 7.7%
          `[VERIFIED-now]`. Every variant is 7-10%, nowhere near 38.5%. Repeats
          cluster on weekend/holiday boundaries and hit many tickers at once —
          feature-frame reuse across non-trading days, not staleness. Closed.

THE HONEST NEGATIVE:
          AAPL's `raw_panel` fell from +0.1040 (06-26) to -0.1988 (07-29), moving
          AGAINST the rally `[VERIFIED-now]`. A signal story, not a plumbing
          defect, and I cannot attribute it without feature-level work the
          retained data does not support.

NEXT:     The open design question, stated as what was actually measured
          rather than as a mechanism: over the 13 scored sessions the mean+1sigma
          floor admitted a mean 18.3% of the cross-section (range 15.2-22.2%)
          and, combined with the absolute mu_floor (orchestrator#610, which sits
          above the calibrator's own p90), a mean 6.1% survived both (range
          0.0-17.7%) `[VERIFIED-now - scripts/aapl_admission_forensics.py]`.
          Both aggregates need the full 13-session window: over only the 11
          sessions the first revision tabulated, the floor-and-mu share is 4.8%
          `[VERIFIED-now]`.
          An earlier revision of this line said the floor throttles breadth
          "regardless of edge" and cited a code comment for it; WITHDRAWN -
          that comment is in the `adaptive_quantile` branch as the motivation
          for replacing mean+ksigma, not a property of `adaptive_mean_std`
          which is the mode running here, and 13 sessions at one edge level
          cannot establish invariance anyway. Whether mu_floor=0.03 is an
          ECONOMIC or a STATISTICAL threshold remains the open question.
