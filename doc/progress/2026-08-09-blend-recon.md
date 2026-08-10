# Blend-composite reconstruction — serving stack end-to-end reproducible

STATUS:    measurement; read-only; task #26 serving-fidelity cell 3.

WHAT:      doc/research/2026-08-09-blend-recon.md — the blend composite
           rebuilt offline from its two legs (prod panel artifact via
           the production transform + the ledger-served momentum_residual
           v0 artifact in force; z+z, ddof=0, NaN propagates) matches
           live's recorded composite on all four blend-served days:
           Spearman 0.9948-0.9979 (median 0.9972), top-5 overlap 5/5
           every day.

WHY/DIR:   Closes the #26 serving-fidelity question together with
           orch#949: the traded system's scoring stack is faithfully
           reproducible offline. The validated-vs-traded gap therefore
           lives in model family + candidate screen + admission gates —
           not serving mechanics. Also re-confirmed the running config
           is the PINNED strategy-104 golden (kind=blend, pins verified);
           the umbrella strategy_config.json still reads hf_patchtst —
           stale surface, separate hygiene item.

EVIDENCE:  artifact:      data/2026-08-09-blend-recon-score.py (CLI
                          args) + …-blend-recon_daily.csv +
                          …-blend-recon_summary.json — the script's
                          VERBATIM outputs [VERIFIED — run 2026-08-09,
                          exit 0, committed files are the outputs]
           prod or exp:   read-only measurement
           existing data: orch#948 extension corpus + fund merge;
                          orch#949 cells 1-2; momentum ledger row 0
                          (cutoff 08-02, sha a824c480…, n_scored 144);
                          golden config pins (6461b827…, momentum-v0)
           best-known?:   yes — pre-07-27 step attribution remains open
                          (orch#949 §5), unchanged by this cell
           scope:         research note + script + 2 evidence files

TESTS:     make test not run — docs+research-data only; scoring run
           exit 0.

NEXT:      (a) pre-07-27 step attribution (older OHLCV snapshot or
           live-tree deploy log); (b) #26 pivots to the model-family
           comparison: replay-validated WF xgb vs served blend on the
           now-shared dates.
