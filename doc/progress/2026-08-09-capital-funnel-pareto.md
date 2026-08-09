# Capital funnel re-measured; grant package re-ranked

STATUS:    measurement + plan re-scope; read-only; Phase-3 step 8.

WHAT:      doc/research/2026-08-09-capital-funnel-pareto.md — the current
           window's blocker Pareto (3 selection events, 0 broker
           receipts / 41 sessions; rank floor
           2,390; BULL_CALM admission 1,155; qp threshold 12.6pp Kelly),
           a provisional current-window triage (the July frictions do
           not appear in this window's top blockers; they were real and
           their fixes remain right), the served-artifact condition
           behind the biggest blocker (#942), and the provisional
           re-scoping of step 9 behind #942.

WHY/DIR:   The operator's Phase-3 asked for the deployable-cash
           simulation; the accounting pass delivers its prerequisite: a
           triage of the pipeline's WILLINGNESS to deploy on this window
           (zero broker order receipts, so no realized-deployment or
           P&L claim). On this window the funnel chokes at the score
           floors and the regime admission gate; the largest blocker
           traces to the currently served zero-admissible artifact — a
           condition requiring a governed decision (the #942 fork), not
           a demonstrated unique/binding system root cause. Per-gate
           relaxation execution is interpretable only once a
           buy-admissible model serves (note §5); its timing-safe
           read-only design can be drafted now.

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
           existing data: the July capital diagnosis (task #14 /
                          pipeline#223 / pipeline#224 / orch#608:
                          wash-sale mass block, integer-share flooring)
                          — real then, fixes remain right; those
                          frictions do not appear among THIS window's
                          top blockers (provisional triage observation,
                          note §2); and corrects the G-E
                          "$4,820/yr" drag quote (priced at the
                          unattainable replay rate) to ~$680/yr at 8%
                          ASSUMED
           best-known?:   yes — §5 states what is NOT shown (per-gate
                          relaxation P&L needs a post-#942 backtest)
           scope:         GRANT PACKAGE, re-ranked for THIS WINDOW —
                          a provisional triage ordering, not a standing
                          law (operator's single decision list):
                          1. #942 fork: (a) repair retrain/promote until
                             a monotonicity-passing model serves, or
                             (b) review the monotonicity bar; EITHER plus
                             the one-line promotion refusal for
                             zero-admissible stamps.
                          2. #941: stamp binding cutoffs into promote
                             receipts (review-sized fix).
                          3. (re-queued) fractional/one-share switches,
                             wash-sale floor confirmation, alerts.py sync,
                             L2 shadow job, sigma* — all still wanted;
                             not among this window's top blockers.

TESTS:     none — measurement; every number re-runnable read-only.

NEXT:      operator decides the #942 fork — a governed decision on the
           served-artifact condition, first in this window's triage
           ordering. The per-gate counterfactual is timing-safe,
           read-only work: its design can be drafted now, its execution
           is interpretable only once a buy-admissible model serves
           (note §5), and either way it informs remediation — it does
           not establish realized deployment or P&L, and it must not
           feed promotion.
