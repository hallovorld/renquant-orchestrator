# L3 classifier prereg — frozen before any training run exists

STATUS:    design only. No training has been run; that is the point. The
           experiment executes only as specified or not at all.

WHAT:      doc/design/2026-08-09-l3-classifier-prereg.md — model class
           (logistic L2 C=1.0; depth-2 GBDT descriptive-only), frozen feature
           list with stated exclusions, expanding walk-forward with
           20-trading-day embargo, ALL-rows training with run_type-split
           metrics mandatory (live-only as a declared prereg variant),
           tau in {0.5, 0.6}, expectancy uplift as the primary metric,
           within-date label-shuffle placebo x200, the 64 trade_evaluations
           rows as a once-only external test, four-leg deterministic
           PASS/KILL, shadow-only stakes on PASS.

WHY/DIR:   The dataset (orch#928) is merged; the classifier experiment must
           be frozen before results exist to steer it — the same window
           discipline as orch#912 §10 and the BEAR exit prereg.

EVIDENCE:  artifact:      orch#928 dataset manifest (7,167 rows / 523 dates /
                          1,275 excluded / selected 135 / base rate 0.6307 /
                          live 2,189 vs sim 4,978)
                          [VERIFIED — re-measured this session: read-only
                          module rebuild, DB mode=ro, output under /tmp,
                          figures from module stdout; identical to the
                          canonical post-r1/r3 record in
                          doc/progress/2026-08-09-l3-candidate-dataset.md]
           prod or exp:   experiment — design doc only
           existing data: no meta-label entry classifier has ever been
                          trained in this system; the exit-side foundation
                          (meta-label-exit.json) is a different surface
           best-known?:   yes — first entry-filter prereg; anticipated
                          failure modes (sim-feature drift, regime
                          collinearity, base-rate drift) are in the doc so
                          they cannot be discovered as surprises
           scope:         design only; the experiment run is the next
                          deliverable and follows this document verbatim.

TESTS:     none — a prose contract; its test is that the run can be judged
           entirely from §2/§3 with zero live choices.

CORRECTION (review r1, Codex MED): the frozen evidence block cited the
           superseded pre-tie-break base rate 0.6311 from before orch#928's
           r1 correction (canonical: selected 135 / base rate 0.6307). The
           prereg is now re-frozen against a manifest re-measured this
           session by a read-only rebuild [VERIFIED — module stdout]; rows /
           dates / exclusions / run_type split unchanged (7,167 / 523 /
           1,275 / live 2,189 vs sim 4,978). Same review round: every number
           in the design doc now carries its LONG-row-10 provenance tag
           ([VERIFIED]/[DERIVED]/[ASSUMED — frozen here]), with the 64
           trade_evaluations rows and the 1,240-of-2,388 bull_calm days
           re-measured this session rather than recalled.

NEXT:      execute the experiment exactly as frozen (derivation + committed
           artifacts at the #913/#926 reproducibility standard), report
           PASS/KILL; on PASS, propose the shadow lane as its own granted
           batch.
