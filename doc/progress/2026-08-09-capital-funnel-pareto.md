# Capital funnel re-measured; grant package re-ranked

STATUS:    measurement + plan re-scope; read-only; Phase-3 step 8.

WHAT:      doc/research/2026-08-09-capital-funnel-pareto.md — the current
           window's blocker Pareto (3 selection events, 0 broker
           receipts / 41 sessions; rank floor
           2,390; BULL_CALM admission 1,155; qp threshold 12.6pp Kelly),
           the staleness of the July diagnosis, the #942 root-cause link,
           and the visible re-scoping of step 9 behind #942.

WHY/DIR:   The operator's Phase-3 asked for the deployable-cash
           simulation; the accounting pass found the binding constraint
           moved since July — and bottomed out in the zero-admissible
           served model (#942). Simulating switch relaxations before #942
           would be theater.

EVIDENCE:  artifact:      committed under doc/research/data/ [VERIFIED —
                          each re-run by the committed verifier, exit 0]:
                          2026-08-09-funnel-summary.json (both paretos,
                          run structure, receipt chain),
                          …-funnel-candidates.csv (all 5,040+ block-event
                          rows with run_id/run_type/commit_sha/
                          training_cutoff/model_content_sha256/
                          is_canonical), …-funnel-selections.csv (the 3
                          selection events with has_trade_row/
                          has_broker_receipt = 3/3/0),
                          …-funnel-sessions.csv, …-funnel-cash.csv (mean
                          cash 79.1%), via …-funnel-derivation.py and
                          …-funnel-verify.py. The zero-admissible claim
                          reads the SERVED artifact
                          RenQuant/backtesting/renquant_104/artifacts/
                          prod/panel-ltr.alpha158_fund.json
                          (wf_gate_metadata.trade_monotonicity.regimes)
                          [VERIFIED — read this session; recorded in
                          orch#942].
           prod or exp:   read-only measurement
           existing data: supersedes-in-part the July capital diagnosis
                          (task #14 / pipeline#223 / pipeline#224 /
                          orch#608: wash-sale mass block, integer-share
                          flooring) — real then, not the binding
                          constraint on THIS window; and corrects the G-E
                          "$4,820/yr" drag quote (priced at the
                          unattainable replay rate) to ~$680/yr at 8%
                          ASSUMED
           best-known?:   yes — §5 states what is NOT shown (per-gate
                          relaxation P&L needs a post-#942 backtest)
           scope:         GRANT PACKAGE, re-ranked (operator's single
                          decision list):
                          1. #942 fork: (a) repair retrain/promote until
                             a monotonicity-passing model serves, or
                             (b) review the monotonicity bar; EITHER plus
                             the one-line promotion refusal for
                             zero-admissible stamps.
                          2. #941: stamp binding cutoffs into promote
                             receipts (review-sized fix).
                          3. (demoted) fractional/one-share switches,
                             wash-sale floor confirmation, alerts.py sync,
                             L2 shadow job, sigma* — all still wanted,
                             none capital-critical this window.

TESTS:     none — measurement; every number re-runnable read-only.

NEXT:      operator picks the #942 fork (the only decision that unblocks
           the book); per-gate relaxation backtest follows a serving,
           buy-admissible model.
