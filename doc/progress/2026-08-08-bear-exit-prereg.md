# BEAR exit-side prereg — candidate config and evaluation plan frozen

STATUS:    design only. Nothing runs, nothing deployed. The prereg freezes
           candidate values + evaluation plan + deterministic PASS rule +
           authorization boundary BEFORE the backtest exists to steer them.

WHAT:      doc/design/2026-08-08-bear-exit-prereg.md — one frozen candidate
           amendment (BEAR-keyed min_holding_days 10 / pct floor 0.35 / mu
           ceiling +0.01 [ASSUMED — frozen policy choice], with
           default-preserving fallback semantics), one frozen evaluation
           plan (episode-level, return-space, per-arm placebo x200, three
           regime-series shifts +5/+10/+20, episode block bootstrap — all
           [ASSUMED — frozen policy choice]), a frozen five-leg PASS rule
           (§3.1 decision table: effect sign, placebo p95, drawdown
           non-inferiority +1.0pt, all-shifts, bootstrap support ≥0.75 —
           conflicts FAIL by construction), and the grant boundary (live
           config change = operator, always). Plus the committed
           reachability measurement backing §1:
           doc/research/data/2026-08-08-bear-exit-reachability-{derivation.py,rows.csv}.

WHY/DIR:   G-B decision routes BEAR to the exit side. The 2026-08-08
           reachability measurement (re-measured this session, committed
           CSV) showed the active exit is enabled yet geometrically
           unreachable: 43 days x 200 holding-day rows [VERIFIED — committed
           rows CSV], holdings sit at median 0.89 of their own cross-section
           (min 0.20), the AND-rule's two legs never coincide (7 rows at or
           below the bottom-20% threshold, all with mu > 0; 1 row with
           mu <= 0, not in the bottom quintile), the strong-mu bypass never
           fires, and the 60d holding exemption covers the thesis horizon
           [VERIFIED — pinned config]. The lever is regime-keyed config the
           schema already half-supports. Freezing now is the only window —
           after the backtest exists, any value choice is post-hoc.

CORRECTIONS: r1 review — the initially quoted 48-day/448-row/median-0.84
           figures came from a non-persisted session join; superseded by the
           committed re-measurement above (LONG #10). Verdict unchanged:
           zero fires on either trigger leg. Visible correction note in the
           design doc's "Corrections" section.

EVIDENCE:  artifact:      doc/research/data/2026-08-08-bear-exit-reachability-rows.csv
                          + -derivation.py (default mode re-verifies every
                          §1 number from the committed CSV alone: 43 days /
                          200 rows / pct median 0.8907 min 0.20 / mu median
                          +0.0351 / AND fires 0 / strong fires 0);
                          gate read: renquant-pipeline/src/renquant_pipeline/
                          kernel/pipeline/task_panel_conviction_xs.py
                          (CrossSectionalPanelExitTask.run trigger
                          arithmetic, replayed by the derivation script);
                          pinned config: renquant-strategy-104/configs/
                          strategy_config.json::risk.panel_exit;
                          BEAR gate stat: RenQuant/backtesting/renquant_104/
                          artifacts/prod/panel-ltr.alpha158_fund.json::
                          metadata.wf_gate_metadata.sanity_regime_ic
                          .per_regime.BEAR (mean_ic +0.2767, hit 0.9636,
                          n_dates 55)
           prod or exp:   experiment — design doc only; measurement reads
                          prod DB/artifacts, writes nothing to them
           existing data: no BEAR-conditioned exit config exists; BEAR
                          inherits default:60 and fires never (zero
                          panel_conviction exits among the window's 42 live
                          sells [VERIFIED — runs.alpaca.db trades join])
           best-known?:   yes — first exit-side prereg; the honest power
                          statement (BEAR n_eff ~4 [DERIVED — ~77 days /
                          ~20d episodes], policy-grade decision) is in the
                          doc, not discovered later
           scope:         design doc. The pipeline _by_regime key change and
                          any live config change are explicitly out of scope
                          and separately gated.

TESTS:     python3 doc/research/data/2026-08-08-bear-exit-reachability-derivation.py
           → VERDICT: REPRODUCED (all 9 frozen numbers from the committed
           CSV alone). The prereg itself is a prose contract: the evaluation
           can be judged entirely from §2/§3/§3.1 with zero live choices,
           and §2 forbids value sweeps ("no other values may be tried").

NEXT:      after this merges: implement the pipeline `_by_regime` key support
           (default-preserving, behaviour-invariance regression first), then
           run the §3 evaluation exactly as frozen and PR the results with
           derivation artifacts.
