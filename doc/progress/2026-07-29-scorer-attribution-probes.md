# Progress: function-level attribution of the live panel scorer

STATUS:   delivered. One committed probe + behavioural tests + a findings doc.
          No production surface touched, no config or artifact written.

WHAT:     `scripts/scorer_attribution_probe.py` — three read-only probes on
          `panel-ltr.alpha158_fund.json`: (A) feature bloat from the booster's
          own gain table, (B) average marginal effect over N random z-space
          baselines, (C) whether the upstream realized-vol gate truncates the
          feature the model relies on most.
          `tests/test_scorer_attribution_probe.py` — 8 behavioural tests.
          `doc/research/2026-07-29-scorer-attribution-volatility-and-profitability.md`.

WHY/DIR:  The operator asked twice for the AAPL signal inversion to be traced
          "具体到 function level". The score DB cannot answer it — per-day
          feature matrices are not retained — but the artifact carries
          `booster_raw_json`, so the attribution is recoverable from the
          artifact alone. Committing the probe means the next person re-runs it
          instead of re-deriving it.

EVIDENCE: artifact:   `panel-ltr.alpha158_fund.json` (kind=panel_ltr_xgboost,
                      trained_date=2026-06-21, label=fwd_60d_excess,
                      172 feature_cols, panel_shape 721335x292x2570) +
                      `data/ohlcv/*/1d.parquet` + the PINNED strategy-104
                      `strategy_config.json` watchlist. All opened READ-ONLY.
          command:    `<umbrella>/.venv/bin/python scripts/scorer_attribution_probe.py
                       --artifact <...>/prod/panel-ltr.alpha158_fund.json
                       --ohlcv-dir <umbrella>/data/ohlcv
                       --strategy-config <pinned>/configs/strategy_config.json`
          headline:   STD60 marginal effect +0.2301 and gross_profitability
                      +0.2098 dominate; QTLU30 is the top GAIN feature (3.7%)
                      at +0.0022 effect; MA20 holds 1.8% of gain and moves the
                      score +0.0000 (sd 0.0000) from all 400 baselines; 66 of
                      172 features (38%) never split on; the 60% vol gate drops
                      35 names carrying 3.09x the kept median STD60, with
                      spearman(STD60, ann vol) = +0.821.
                      AAPL rose +19.13% (rank 8/145) while its STD60 FELL
                      0.0639 -> 0.0469 — it was marked down for rallying
                      CALMLY, not for rallying.
  prod or exp:      EXPERIMENT/diagnosis. Nothing written outside this branch.
  existing data:    Yes — the artifact and OHLCV already on disk; no retrain,
                    no refetch, no compute spend.
  best-known?:      Yes for the attribution question. The probe also CORRECTED
                    an earlier reading of mine in two places: (1) I had framed
                    this as a pure volatility model, but gross_profitability
                    measures +0.2098, within 10% of STD60 — it is a volatility
                    AND profitability model; (2) my first cut reported
                    book_to_price as "~zero marginal effect" when its sd is
                    0.0777 — it is SIGN-UNSTABLE, not inert. The script now
                    separates the two classes, since calling a conditional
                    feature dead weight would license deleting it.
  scope:            `renquant-orchestrator` only: one script, one test file,
                    two docs. No pin advanced, no umbrella change.

SCOPE/LIMITS:
          The -7.84σ feature-move figure in §1 covers 10 of 172 features =
          21.8% of gain, so NO total score delta is attributed and the doc says
          so. The doc does NOT claim mean-reversion is the wrong objective and
          does NOT recommend adding momentum features as a fix: a prior sealed
          result has mom_12_1/mom_6_1/reversal/MA200/52wk-high all failing the
          20/60d bar on 104, with regime-conditioned momentum as the surviving
          lead. Probe B's baselines are standard normal in z-space, which is
          the space the artifact standardises into (`feature_means`/
          `feature_stds`), but it is not the empirical joint distribution — the
          numbers are average marginal effects, not per-name explanations.
          Probe C's correlation is REPORTED (+0.821) rather than assumed
          because STD60 is a price-dispersion ratio and the gate thresholds
          annualised RETURN volatility; they are different quantities.

VERIFICATION:
          `python3 -m pytest tests/test_scorer_attribution_probe.py -q` -> 8
          passed. The tests train a tiny booster whose driver feature is known
          BY CONSTRUCTION and assert the probes recover it — a source-grep test
          would pass on a probe that names the wrong feature, which is the one
          failure mode that matters here. They also cover: `never_split_on`
          arithmetic for features declared but absent from the booster (the
          live 172-vs-106 case), seed determinism, the price-ratio family
          classification against the definitions read in §1, the truncation
          ratio on a synthetic calm/volatile OHLCV tree, and a missing ticker
          directory. The full-artifact run in the doc was executed against the
          live artifact READ-ONLY and its output is pasted verbatim.

NEXT:     The doc's §6 point 1 is the open thread and is deliberately left
          open: whether a reversion/momentum balance can be built here is a
          question for a PREREGISTERED screen, not for this diagnosis. §4 hands
          that screen a mechanism to test (serve-time truncation of the
          volatility axis) rather than a factor list to fish through.
