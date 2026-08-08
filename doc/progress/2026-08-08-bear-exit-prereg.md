# BEAR exit-side prereg — candidate config and evaluation plan frozen

STATUS:    design only. Nothing runs, nothing deployed. The prereg freezes
           candidate values + evaluation plan + authorization boundary BEFORE
           the backtest exists to steer them.

WHAT:      doc/design/2026-08-08-bear-exit-prereg.md — one frozen candidate
           amendment (BEAR-keyed min_holding_days 10 / pct floor 0.35 / mu
           ceiling +0.01, with default-preserving fallback semantics), one
           frozen evaluation plan (episode-level, return-space, per-arm
           placebo x200, three regime-series shifts, episode block bootstrap),
           and the grant boundary (live config change = operator, always).

WHY/DIR:   G-B decision routes BEAR to the exit side. The 2026-08-08
           reachability verdict (task #21) showed the active exit is enabled
           yet geometrically unreachable (holdings sit at median 0.84 of
           their own cross-section; 60d holding exemption covers the thesis
           horizon). The lever is regime-keyed config the schema already
           half-supports. Freezing now is the only window — after the
           backtest exists, any value choice is post-hoc.

EVIDENCE:  artifact:      task_panel_conviction_xs.py gates (read); pinned
                          strategy_config risk.panel_exit (read); 48-day/448
                          row reachability measurement (task #21)
           prod or exp:   experiment — design doc only
           existing data: no BEAR-conditioned exit config exists; BEAR
                          inherits default:60 and fires never
           best-known?:   yes — first exit-side prereg; the honest power
                          statement (BEAR n_eff ~4, policy-grade decision)
                          is in the doc, not discovered later
           scope:         design doc. The pipeline _by_regime key change and
                          any live config change are explicitly out of scope
                          and separately gated.

TESTS:     none — a prose contract. Its contract: the evaluation can be
           judged entirely from §2/§3 with zero live choices, and §2 forbids
           value sweeps ("no other values may be tried").

NEXT:      after this merges: implement the pipeline `_by_regime` key support
           (default-preserving, behaviour-invariance regression first), then
           run the §3 evaluation exactly as frozen and PR the results with
           derivation artifacts.
