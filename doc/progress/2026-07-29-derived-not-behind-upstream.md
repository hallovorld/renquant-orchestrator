# Progress: a derived artifact may not lag the artifact it is built from

STATUS:   delivered (invariant + 5 tests). Stacked on orch#609 (APPROVED, not
          pushed to — pushing would invalidate its approval). Found a REAL
          production fault on its first run.

WHAT:     `check_derived_not_behind_upstream()` in
          `ops/data_frontier_check.py`, wired into `main()` as a `[CHAIN]`
          finding. For declared `(derived, upstream)` pairs it asserts the
          derived frontier is not older than its input's. `main()` now exits
          non-zero on a chain fault even when every artifact is HEALTHY.

WHY/DIR:  Found while verifying the 9-ticker panel rebuild. Rebuilding the
          transformer corpus from the CURRENT fund panel gave all 142
          incumbents +3 rows, which I first mis-read as a side effect of adding
          tickers. It was not:

            PROD alpha158-fund-panel (the input)  max_date 2026-05-01, 2597 dates
            PROD transformer-panel  (its output)  max_date 2026-04-28, 2594 dates

          The corpus is 3 sessions BEHIND the panel it derives from, and the
          per-artifact age check reports it HEALTHY (92d against a 112d
          structural bound) because 92d is genuinely fine for a 60-day-label
          panel. Age asks "is this new enough"; nothing asked "did the chain
          run in order".

EVIDENCE: artifact: `ops/data_frontier_check.py`,
                    `tests/test_data_frontier_check.py`; live
                    `RenQuant/data/{alpha158_291_fundamental_dataset,transformer_v4_wl200_clean}.parquet`,
                    READ-ONLY.
  prod or exp:      PROD ops tooling, READ-ONLY. Reads parquet date columns;
                    writes nothing, installs nothing.
  existing data:    Yes, measured this session:
                    fund panel max_date 2026-05-01, 2597 dates `[VERIFIED]`
                    corpus     max_date 2026-04-28, 2594 dates `[VERIFIED]`
                    lag = 3 sessions `[DERIVED]`
                    Live run after the change: 3/3 artifacts HEALTHY AND one
                    `[CHAIN]` finding `[VERIFIED]` — the exact combination the
                    age check could not produce.
                    Rebuilding the corpus from the current panel recovered
                    exactly those 3 dates for all 142 incumbents `[VERIFIED]`.
  best-known?:      Yes for the invariant and the fault. NOT claimed: that the
                    3-session lag caused any trading harm — the live scorer
                    computes features from real-time bars, not from this
                    corpus, so the lag affects TRAINING inputs.
  scope:            `renquant-orchestrator` ops + tests. No pin advanced, no
                    config edited, no live surface touched, no job installed.

DESIGN NOTES, both deliberate:
          * Only BEHIND is a fault. A derived artifact AHEAD of one upstream is
            legitimate — it may have other inputs.
          * A pair with an unreadable side is SKIPPED. The age check already
            reports an unreadable artifact; a second finding for the same fault
            would double-count one problem as two.

VERIFICATION:
          27 tests (5 added), including the measured production case as a
          regression and `test_main_exits_nonzero_on_a_chain_fault_alone`,
          which asserts a chain fault fails the run while every artifact
          reports HEALTHY — the combination that made this invisible.

NEXT:     The corpus refresh job is behind its input in production. Re-running
          it is a machine landing and needs an operator grant; the alarm is now
          the durable reminder rather than a thing nobody could see.
