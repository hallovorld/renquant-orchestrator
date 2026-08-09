# Real-frame sector table — the live blend's own selection, measured

STATUS:    descriptive measurement; read-only; Phase-2 step 7.

WHAT:      doc/research/2026-08-09-realframe-sector-table.md — the sector
           question re-asked with the REAL system's scores
           (ticker_daily_state × OHLCV fwd-5d), derived by the committed
           frozen contract doc/research/data/
           2026-08-09-realframe-sector-derivation.py with per-name and
           per-sector-day rows committed beside it.

WHY/DIR:   The replay-frame table (#936) does not describe the traded
           system (#937: 0/15 picks overlap). The operator's question
           deserves an answer in the frame that owns the money — stated
           at descriptive strength only.

EVIDENCE:  artifact:      doc/research/data/2026-08-09-realframe-sector-
                          {derivation.py, rows.csv, days.csv}
                          [VERIFIED — derivation rerun clean this session]:
                          pooled selection edge +28.3 bp/5d over 195
                          sector-days / 37 usable dates; consumer +166.0 /
                          industrial +52.8 / software +45.2 / finance
                          +11.7 / datacenter_hw −22.6 / ai_chip −93.6 bp
                          per 5d. Short-window descriptive ranking —
                          overlapping fwd-5d windows, six correlated
                          contrasts, no prespecified test; sign/ordering
                          not confirmed. r1 corrections: the first push's
                          scratch-derived numbers were irreproducible and
                          are withdrawn in a visible corrections section.
           prod or exp:   experiment; mode=ro DB + OHLCV reads
           existing data: entirely — no new collection
           best-known?:   yes — 5d horizon, 37-day and overlap caveats
                          stated up front; no routing decision proposed
           scope:         seed table for the converged comparison after
                          orch#939; no production change.

TESTS:     the derivation script IS the test — it re-derives from the
           read-only DB + OHLCV and asserts frame-equality against both
           committed CSVs (rerun clean this session); it REFUSES on drift.

NEXT:      after orch#939 (corpus extension) the converged table replaces
           this; xgb_mom_60d verdict publishes separately (run in flight).
