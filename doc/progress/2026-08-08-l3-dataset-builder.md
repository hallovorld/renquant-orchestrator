# L3 meta-label dataset builder — entry-labeled trades with provenance as a column

STATUS:    code delivered for review. Read-only over the runs DB; writes one
           CSV + manifest sidecar wherever pointed. No production surface.

WHAT:      src/renquant_orchestrator/l3_dataset_builder.py + 4 tests. One row
           per BUY with entry-time features (regime, confidence, panel_score,
           mu, sigma, expected_return, sector, active_scorer, rank_score,
           kelly_target_pct — from the buy row itself, nothing recomputed)
           and the realized outcome of the round trip it opened (win/pnl_pct/
           hold_days/exit_reason from the paired sell).

WHY/DIR:   Step 1 of the L3 meta-label entry filter — the allocation-machine
           track's honest win-rate lever (L1 exposure shadow and L2 paper
           bandit already merged). The classifier can only be as honest as
           its dataset, so the dataset ships first, with provenance as an
           explicit column the trainer must choose over — never an implicit
           default.

TWO MEASURED FACTS THE FIRST DRAFT GOT WRONG (fixed before PR, with tests):
  1. trade_date is NULL on 12,391/12,493 real rows (sim rows never stamp it);
     the run_id prefix is a valid date on ALL rows. Dates use
     COALESCE(trade_date, substr(run_id,1,10)) — the choice is recorded in
     the docstring and covered by a dedicated NULL-date test, because that IS
     the production path.
  2. ALL 5,989 pnl-carrying sells lack a broker_order_id — outcome labels are
     effectively sim-only today. provenance became entry_live/exit_live flags
     plus provenance='live' iff BOTH legs are brokered; nothing about the
     imbalance is hidden.

EVIDENCE:  artifact:      real-DB build this session (read-only, scratch out):
                          5,947 paired rows, 458 unclosed buys EXCLUDED AND
                          COUNTED, provenance {live: 0, sim: 5947}, sim win
                          rate 0.7606 [VERIFIED — builder stdout]
           prod or exp:   experiment — read-only
           existing data: the 76% figure matches the standing memory
                          ("win rate is backtest not live") EXACTLY — the
                          builder reproduces known ground truth, which is the
                          cross-check that it pairs correctly
           best-known?:   yes — first entry-labeled dataset; the honest
                          eval set remains trade_evaluations (64 rows,
                          forward-labeled)
           scope:         orchestrator module + tests. Pairing rule v1
                          (first-buy-to-first-later-sell per ticker) stated
                          in the docstring with ambiguity counts reported.

TESTS:     4 passed — pairing + provenance + counts; the NULL-date run_id
           fallback (the production path); no backwards pairing; CSV+manifest
           write and empty-refusal.

NEXT:      the L3 classifier itself (small, shallow, shadow-first) trains on
           this CSV with provenance as an EXPLICIT choice — the honest
           framing per the design: sim-trained, live-evaluated on the 64
           trade_evaluations rows until live labels accrue.
