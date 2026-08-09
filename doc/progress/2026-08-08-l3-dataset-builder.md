# Paired-trade audit — provenance and pairing ambiguity made explicit

STATUS:    code delivered for review. Read-only over the runs DB; writes one
           CSV + manifest sidecar wherever pointed. No production surface.

WHAT:      src/renquant_orchestrator/l3_dataset_builder.py + 7 tests. One row
           per BUY with entry-time features (regime, confidence, panel_score,
           mu, sigma, expected_return, sector, active_scorer, rank_score,
           kelly_target_pct — from the buy row itself, nothing recomputed)
           and the realized outcome of the round trip it opened (win/pnl_pct/
           hold_days/exit_reason from the paired sell).

WHY/DIR:   A descriptive audit supporting the L3 research track. It makes
           provenance and the lack of lot identity visible, but it is NOT an
           L3 classifier dataset: 99.7% of its FIFO-paired outcomes are
           ambiguous. The CLI fails closed unless the caller explicitly
           acknowledges that it is requesting surrogate labels for audit.

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
                          rate 0.7606, pairing_ambiguous on 5,928/5,947 rows
                          (99.7% — FIFO labels are surrogates for nearly the
                          whole set; the flag is why that is now visible)
                          [VERIFIED — builder stdout]
           prod or exp:   experiment — read-only
           existing data: the 76% figure matches the standing memory
                          ("win rate is backtest not live") EXACTLY — the
                          builder reproduces known ground truth, which is the
                          cross-check that it pairs correctly
           best-known?:   yes — first entry-labeled dataset; the honest
                          eval set remains trade_evaluations (64 rows,
                          forward-labeled)
           scope:         orchestrator module + tests. Pairing = FIFO by
                          (date, rowid), deterministic in both queries.
                          AMBIGUITY IS A COLUMN (review r2): pairing_ambiguous=1 iff
                          the lot's interval overlaps any other lot of the
                          same ticker (paired or still open) — symmetric,
                          because with no lot identity on the sells, WHICH
                          exit belongs to WHICH entry is unobservable. The
                          manifest counts them; a downstream experiment must
                          CHOOSE to include them.

TESTS:     7 builder tests passed — pairing + provenance + counts; the
           NULL-date run_id fallback (the production path); no backwards
           pairing; CSV+manifest write and empty-refusal; concurrent lots
           flagged ambiguous on BOTH sides with deterministic FIFO; an open
           buy overlapping a paired lot flags it. 2 doc-alignment tests also
           passed (9 focused tests total).

NEXT:      Build a separate L3 training dataset from candidate_scores JOIN
           ticker_forward_returns at a declared point-in-time forward horizon.
           That change must define its population, availability cutoff,
           horizon, and out-of-sample evaluation before any classifier trains.
