# Progress: breadth does not buy evaluation precision (GOAL-6 Stage 2 input)

STATUS:   delivered (measurement + research doc). This is NOT a proposal and
          asks for no decision; it replaces an assumption in GOAL-6 Stage 2
          scoping with a measured number.

WHAT:     `doc/research/2026-07-29-breadth-does-not-buy-evaluation-precision.md`.
          Subsampled the clf walk-forward corpus cross-section to N names/date
          and measured per-date IC variance as a function of N. Fitted
          `Var(IC) = 0.03535 + 0.9814/N`. At N=292 the breadth-proof term is
          91% of the variance; 292 -> 830 names narrows the per-date IC sd by
          2.9%, and an infinitely wide cross-section caps at 4.4%.

WHY/DIR:  GOAL-6 sequences Stage 1 (830-name PIT panel) into Stage 2 "breadth
          retraining", partly on the premise that breadth improves measurement.
          That link was inherited intuition, never measured. It is correct in
          direction and roughly an order of magnitude too small to matter.

          Corroborated without the fit: the clf corpus has TWICE PatchTST's
          cross-sectional width (292 vs 142 names) and a WIDER confidence
          interval (half-width 0.0733 vs 0.0562). Both sit on 11 independent
          60-day blocks. Time is the binding constraint, not width.

EVIDENCE: artifact: `scratchpad/clf-wf/clf_wf_scores.parquet` (178,191 rows,
                    625 score dates, 43 folds, 292 tickers, all rows labelled),
                    READ-ONLY; analysis via `renquant_model_common.lag_alignment`.
  prod or exp:      EXPERIMENT/measurement. No production data, config, or
                    artifact written. Corpus lives in the quarantined scratch
                    namespace.
  existing data:    Yes — measured this session, not recalled. Ladder N in
                    {20,40,80,140,200,250,292} over the 594 dates carrying >=250
                    names, 3 draws per (date,N). Fit tracks the ladder closely
                    (predicted 0.03871 vs measured 0.03899 at N=292; 0.08445 vs
                    0.08485 at N=20). An earlier session measured a different
                    corpus at `Var(IC) = 0.01877 + 1.065/N` — different `a`,
                    same conclusion about which term dominates.
  best-known?:      Yes for this corpus. Explicitly NOT claimed: that breadth
                    fails to improve the MODEL. This measures evaluation
                    precision only; a wider training panel may still produce a
                    better model, and a wider tradeable universe has independent
                    value. Stage 1's survivorship justification is untouched —
                    a biased panel is wrong at any width.
  scope:            `renquant-orchestrator` docs only. No pin advanced, no
                    umbrella change, no live surface touched.

SCOPE/LIMITS:
          Restricting to dates with >=250 names means the N=292 row occasionally
          draws from a slightly smaller pool, which if anything UNDERSTATES how
          flat the curve is. The `a + b/N` form is fitted, not derived, so
          N=2000 is an extrapolation. `a` is corpus- and model-specific and
          should be re-measured per corpus rather than assumed.

NEXT:     GOAL-6 Stage 2 scoping should carry this number. If Stage 2 is
          budgeted on breadth making results resolvable, that premise needs
          restating; resolving these effects needs more independent TIME blocks.
          Stage 1 proceeds on its own survivorship grounds regardless.
