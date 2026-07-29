# Progress: survivorship — probed what current subscriptions can buy

STATUS:   findings delivered, no spend made, decision requested.

WHAT:     Adds `doc/research/2026-07-29-survivorship-data-availability.md`: what the
          existing FMP and Alpaca subscriptions can and cannot provide for a
          delisting-inclusive universe, four costed options, and a recommendation.

WHY/DIR:  GOAL-6 Stage 1's panel failed its survivorship criterion, and every Stage-2
          result on it inherits the bias. Before spending or scoping down, measure
          what we already own.

EVIDENCE: live read-only probes `[VERIFIED — 2026-07-29]`. FMP
          `stable/historical-price-eod/full` returns real history for a delisted
          symbol (TWTR: 459 bars ending 2022-10-27). FMP `stable/delisted-companies`
          serves page 0 only (100 rows, 2026-07-02..07-27); page 1 returns HTTP 402 on
          Starter. Alpaca `/v2/assets?status=inactive` returns 19,209 US equities but
          is OTC-dominated (16,355 OTC vs 1,310 NASDAQ / 845 NYSE / 97 AMEX) and hits
          only 2 of 9 probed known-delisted majors (CERN, XLNX; misses TWTR, ATVI,
          VMW, SIVB, FRC, PXD, SPLK). No IC/return claim is made.

NEXT:     Operator decision between an index-constituent-by-date product (recommended
          - it defines the universe the strategy competes against and sidesteps the
          registry entirely), an FMP tier upgrade (verify the registry's DEPTH before
          paying - page 1 is gated so depth is unmeasured), or running Stage 2 with
          the bias stated in the results rather than a footnote. The cheap next probe:
          whether Alpaca's inactive list is adequate once filtered to names that ever
          appeared in our panel.
