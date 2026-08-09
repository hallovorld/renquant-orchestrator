# Real-frame sector table — the live blend's own selection, measured

STATUS:    descriptive measurement; read-only; Phase-2 step 7.

WHAT:      doc/research/2026-08-09-realframe-sector-table.md — the sector
           question re-asked with the REAL system's scores
           (ticker_daily_state × OHLCV fwd-5d, 38-43 usable dates).

WHY/DIR:   The replay-frame table (#936) does not describe the traded
           system (#937: 0/15 picks overlap). The operator's question
           deserves an answer in the frame that owns the money.

EVIDENCE:  artifact:      the table [VERIFIED — tds × OHLCV joins, this
                          session]: pooled selection edge +25.1 bp/5d;
                          consumer +150.8 / industrial +53.4 / software
                          +34.5 / finance +6.4 / datacenter −12.4 /
                          ai_chip −84.7 bp per 5d.
           prod or exp:   experiment; mode=ro DB + OHLCV reads
           existing data: entirely — no new collection
           best-known?:   yes — 5d horizon and 38-day caveats stated up
                          front; no routing decision proposed
           scope:         seed table for the converged comparison after
                          orch#939; no production change.

TESTS:     none — a measurement note; every number re-runnable read-only.

NEXT:      after orch#939 (corpus extension) the converged table replaces
           this; xgb_mom_60d verdict publishes separately (run in flight).
