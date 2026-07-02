# C3 regime-conditioned residual momentum — frozen-spec measurement (MISS)

STATUS:   research evidence (read-only measurement; one committed script + committed JSON
          evidence + memo). First formally-voting M-SIG candidate measured under the merged
          frozen spec (#243). VERDICT: MISS — recorded and dropped per design rule 5; not KILL.
REVISION: r1.
WHAT:     `scripts/c3_residual_momentum.py` + `doc/research/evidence/2026-07-02-c3/*.json` +
          `doc/research/2026-07-02-c3-residual-momentum.md`. Measures spec section 1.3:
          mom_12_1 rank-z'd, per-date OLS-residualized to sector dummies + trailing-252d
          market beta, scored ONLY in the pooled BULL_CALM+BULL_VOLATILE cell, placebo-clean
          (label shifted +horizon) per-date Spearman IC vs fwd_60d excess-SPY, moving-block
          bootstrap (block=60, n_boot=2000, seeds 42/43/44), one-sided 98.33% Bonferroni CI.
          Regime labels: the PRODUCTION task chain (pinned pipeline + pinned strategy config +
          prod GMM artifact) replayed sequentially per the build_regime_series reference.
WHY/DIR:  spec section 2a ordering — C3 is the cheapest/soonest-ready voting candidate (data
          exists now); its verdict is one of the >=2 GO votes G106 needs by 2027-Q4. The
          conditioned residual×regime cell was the last untested momentum combination
          (prospectivity affirmed in the memo section 8: no prior script computed this exact
          combination — 2026-06-23-residual-audit residualized the LABEL, regimemom used raw
          momentum on non-production regime labels).

EVIDENCE:
```
artifact:      scripts/c3_residual_momentum.py (one-command reproduce, umbrella venv) +
               doc/research/evidence/2026-07-02-c3/{c3_results,c3_per_date_ic_fwd60,
               c3_regime_series}.json (committed outputs, input SHA-256 manifest inside)
prod or exp:   experiment — read-only research measurement, no config/order/gate change
existing data: umbrella data/ohlcv/<T>/1d.parquet (142 transformer-panel tickers + SPY,
               2016-01-04..2026-07-01, split-adjusted, verified no split seams), pinned
               strategy_config.json sector_map/benchmark, prod spy-gmm-regime.json
               (trained 2026-05-22), pinned renquant-pipeline regime task chain
best-known?:   best-available substrate — the spec's S5/S8 pick-table/ledger has no
               multi-year history yet; deviation stated in memo section 7 with the
               survivorship limitation (fixed 2026 universe => optimistic bias => the MISS
               is conservative in direction)
scope:         C3 ONLY (one candidate PR at a time, design rule 5); C4/C2 unaffected
result:        conditioned placebo-clean IC -0.0040 (n=1833 daily dates, bar +0.015;
               98.33% one-sided LB ~-0.053 all seeds) => leg (a) FAILS; conditioned-minus-
               unconditioned +0.0086 but 95% CI [-0.0031,+0.0235] and 98.33% LB ~-0.004 all
               seeds include 0 => leg (b) FAILS; KILL triggers do NOT fire (cond > uncond
               point-wise; UB +0.048 not < 0.015) => MISS, sample floor met (1833 >= 600).
               Raw real IC in the cell +0.0253 is fully explained by placebo +0.0275 —
               apparent bull-regime momentum IC is label-persistence structure, not alpha.
               Verdict convention-robust: dispatch bundle (beta120/stride-21/block13/5000/
               seed42) reads diff -0.0009; block13-daily and beta120-daily agree. fwd_20d
               supporting: cond +0.0029 vs uncond +0.0004 — same story. Per-regime: BEAR
               -0.072 (momentum crash, excluded by the cell), CHOPPY +0.021 (106 dates,
               diagnostic only).
```

Interpretations resolved (full list stamped in c3_results.json + memo section 5): block=60
NOT 13 (merged spec r3 section 4 Q2 explicitly resolved the "A1 convention block=13"
question; block=13 reported as sensitivity, same verdict); beta window 252d spec-frozen
(dispatch's 120d = sensitivity); DAILY decision dates (stride-21 cannot meet the n>=600
floor — it yields 89 conditioned dates); verdict on fwd_60d (strategy horizon), fwd_20d
supporting; difference CI is PAIRED (blocks over the full series, mean(cell)-mean(all) per
resample). No frozen threshold altered anywhere.

NEXT:     C3 is CLOSED (recorded miss — do not re-pitch momentum-family candidates absent a
          genuinely new instrument, design rules 3/5). Stack rides on C4 (trend-scan label,
          after S3 lands) and C2 (quality composite, after the N3 coverage verdict, 2026-Q4);
          G106 GO still needs 2 of 3. Codex review of this PR; the M-SIG spec's own tracking
          should record C3 = MISS at its next revision (spec doc itself frozen, not touched
          by this PR).
