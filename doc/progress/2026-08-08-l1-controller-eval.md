# L1 controller evaluation — frozen parameters, 2412 days, verifier committed

STATUS:    delivered as a research record. No config, pin, or production
           surface touched. Single frozen parameter set, no sweep.

WHAT:      doc/research/2026-08-08-l1-controller-eval.md + committed daily
           CSV + CSV-only verifier + provenance derivation. Controller
           exposure = clip((0.15/EWMA-vol)·g(regime posterior), 0.3, 1.0),
           one-day lag, 10bps/unit turnover cost.

WHY/DIR:   orch#918's L1 is the machine's first layer and the operator's
           dissatisfaction demanded a measured generative deliverable, not
           another gate. This is it: the accidental-exposure book (~22%
           invested) leaves ~$1,275/yr on the table vs the controller ON THE
           SAME RISK STORY (maxDD designed to −17.4% vs full-invest −34.6%).

EVIDENCE:  artifact:      committed CSV (2412 rows) + verifier; derivation
                          provenance-only (machine-local OHLCV + production
                          regime posteriors)
           prod or exp:   experiment — read-only research
           existing data: no exposure controller was ever evaluated; exposure
                          has never been a designed quantity in this system
           best-known?:   yes — first controller evaluation; supersedes
                          nothing
           scope:         research only. Headline: ann +17.1% / Sharpe 1.38 /
                          maxDD −17.4% vs full-invest +25.5% / 1.21 / −34.6%;
                          high-bear days cut from −37.3% pace & −29.9% DD to
                          −14.1% & −10.2% [VERIFIED — verifier + derivation
                          outputs]. Mean exposure 76%, turnover 4.6x/yr.

TESTS:     the committed verifier reproduces every headline number from the
           CSV alone (run this session). The derivation is single-frozen-set
           by design — no sensitivity surface exists to cherry-pick from.

NEXT:      operator inputs: drawdown appetite (calibrates σ* once, before any
           live proposal) and go/no-go on the SHADOW phase (daily target-
           exposure logging beside the live run — no order impact). Then the
           panel-book fidelity replay, and L2's paper-bandit spec.
