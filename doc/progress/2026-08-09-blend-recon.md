# Blend-composite reconstruction — 0.9948-0.9979 on the four blend days (conditional)

STATUS:    measurement; read-only; task #26 serving-fidelity cell 3.

WHAT:      doc/research/2026-08-09-blend-recon.md — the blend composite
           rebuilt offline from its two legs (prod panel artifact via
           the production transform + the ledger-served momentum_residual
           v0 artifact in force; z+z, ddof=0, NaN propagates) matches
           live's recorded composite on all four blend-served days:
           Spearman 0.9948-0.9979 (median 0.9972), top-5 overlap 5/5
           every day.

WHY/DIR:   With orch#949, the measured surfaces (pure-panel days +
           these four blend days) reconstruct at 0.97+ under recorded
           identities (fail-closed bindings: golden pin, ledger row,
           source rev, parquet sha; coverage: n_live_only=0 asserted,
           offline surface = the 144-name ACTIVE universe on
           these days — CORRECTED from "fund-merge narrowing":
           the merge log shows zero row loss; 292 is the
           whole-window unique-ticker count incl. delisted).
           NOT claimed closed: candidate screen (untested),
           transform-version drift, pre-07-27 step. The cells support
           redirecting the NEXT increment to model family + candidate
           screen + admission gates. Running config re-confirmed =
           pinned strategy-104 golden; umbrella strategy_config.json
           panel_scoring.kind=hf_patchtst is a stale surface — separate
           hygiene item.

EVIDENCE:  artifact:      data/2026-08-09-blend-recon-score.py (CLI
                          args; fail-closed identity bindings +
                          coverage assertion) + …-blend-recon_daily.csv
                          + …-blend-recon_coverage.csv +
                          …-blend-recon_summary.json — the script's
                          VERBATIM outputs [VERIFIED — rerun 2026-08-09
                          after hardening, exit 0, committed files are
                          the outputs; numbers unchanged]
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
