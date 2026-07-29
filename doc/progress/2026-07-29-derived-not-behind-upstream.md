# Progress: a derived artifact may not lag the artifact it is built from

STATUS:   delivered (invariant + 5 tests `[VERIFIED — git diff origin/main...HEAD -- tests/test_data_frontier_check.py, 5 new test_ defs]`).
          Stacked on orch#609 (APPROVED, not
          pushed to — pushing would invalidate its approval). Found a REAL
          production fault on its first run.

WHAT:     `check_derived_not_behind_upstream()` in
          `ops/data_frontier_check.py`, wired into `main()` as a `[CHAIN]`
          finding. For declared `(derived, upstream)` pairs it asserts the
          derived frontier is not older than its input's. `main()` now exits
          non-zero on a chain fault even when every artifact is HEALTHY.

WHY/DIR:  Found while verifying the 9-ticker panel rebuild. Rebuilding the
          transformer corpus from the CURRENT fund panel gave all 142
          incumbents `[VERIFIED — this session, rebuild diff against
          RenQuant/data/transformer_v4_wl200_clean.parquet]` +3 rows
          `[DERIVED — 2597 - 2594]`, which I first mis-read as a side effect
          of adding tickers. It was not:

            PROD alpha158-fund-panel (the input)  max_date 2026-05-01, 2597 dates `[VERIFIED — this session, parquet date column, RenQuant/data/alpha158_291_fundamental_dataset.parquet]`
            PROD transformer-panel  (its output)  max_date 2026-04-28, 2594 dates `[VERIFIED — this session, parquet date column, RenQuant/data/transformer_v4_wl200_clean.parquet]`

          The corpus is 3 sessions BEHIND `[DERIVED — 2597 - 2594 = 3]` the panel it derives from, and the
          per-artifact age check reports it HEALTHY (92d against a 112d
          structural bound) `[VERIFIED — python ops/data_frontier_check.py
          live run against the same two files, this session]` because 92d is
          genuinely fine for a 60-day-label
          panel. Age asks "is this new enough"; nothing asked "did the chain
          run in order".

EVIDENCE: artifact: `ops/data_frontier_check.py`,
                    `tests/test_data_frontier_check.py`; live
                    `RenQuant/data/{alpha158_291_fundamental_dataset,transformer_v4_wl200_clean}.parquet`,
                    READ-ONLY.
  prod or exp:      PROD ops tooling, READ-ONLY. Reads parquet date columns;
                    writes nothing, installs nothing.
  existing data:    Yes, measured this session:
                    fund panel max_date 2026-05-01, 2597 dates `[VERIFIED —
                    this session, parquet date column,
                    RenQuant/data/alpha158_291_fundamental_dataset.parquet]`
                    corpus     max_date 2026-04-28, 2594 dates `[VERIFIED —
                    this session, parquet date column,
                    RenQuant/data/transformer_v4_wl200_clean.parquet]`
                    lag = 3 sessions `[DERIVED — 2597 - 2594 = 3]`
                    Live run after the change: 3/3 artifacts HEALTHY AND one
                    `[CHAIN]` finding `[VERIFIED — python ops/data_frontier_check.py
                    live run against production RenQuant/data/*.parquet, this
                    session]` — the exact combination the
                    age check could not produce.
                    Rebuilding the corpus from the current panel recovered
                    exactly those 3 dates for all 142 incumbents `[VERIFIED —
                    this session, rebuild diff]`.
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
          27 tests (5 added) `[VERIFIED — pytest -q tests/test_data_frontier_check.py
          on head 2326663c, re-run this session, "27 passed"]`, including the
          measured production case as a
          regression and `test_main_exits_nonzero_on_a_chain_fault_alone`,
          which asserts a chain fault fails the run while every artifact
          reports HEALTHY — the combination that made this invisible.
          (24 `test_` defs; 27 collected items because one pre-existing
          parametrized test — `tdays,cal` at line 43 — expands to 4 cases.
          19 defs / 22 collected on `origin/main` before this PR
          `[VERIFIED — git show origin/main:tests/test_data_frontier_check.py |
          grep -c '^def test_']`; +5 defs matches the PR diff exactly.)

NEXT:     The corpus refresh job is behind its input in production. Re-running
          it is a machine landing and needs an operator grant; the alarm is now
          the durable reminder rather than a thing nobody could see.
