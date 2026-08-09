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
                          regenerates the CSV byte-identically from the
                          committed regime snapshot + three sibling-resolved,
                          env-overridable external inputs (review r3
                          correction): renquant-model/src (code),
                          renquant-strategy-104 strategy config (universe),
                          umbrella OHLCV tree (the one machine-local,
                          non-clonable input)
           prod or exp:   experiment — read-only research
           existing data: no exposure controller was ever evaluated; exposure
                          has never been a designed quantity in this system
           best-known?:   yes — first controller evaluation; supersedes
                          nothing
           scope:         research only. Headline: ann +17.1% / Sharpe 1.38 /
                          maxDD −17.4% vs full-invest +25.5% / 1.21 / −34.6%;
                          bear-signal days (CORRECTED to the controller's own
                          lagged signal after codex caught a future-aligned
                          mask): segment DD capped −25.2% → −7.8%, at an
                          upside cost (+222.1% → +47.8% pace) in this
                          rebound-heavy history — the dial is PROTECTION,
                          priced into the headline numbers, not a return
                          enhancer [VERIFIED — corrected derivation output].
                          Mean exposure 76%, turnover 4.6x/yr.

TESTS:     the committed verifier reproduces every headline number from the
           CSV alone (run this session). The derivation is single-frozen-set
           by design — no sensitivity surface exists to cherry-pick from.

NEXT:      operator inputs: drawdown appetite (calibrates σ* once, before any
           live proposal) and go/no-go on the SHADOW phase (daily target-
           exposure logging beside the live run — no order impact). Then the
           panel-book fidelity replay, and L2's paper-bandit spec.
