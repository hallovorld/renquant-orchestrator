# Vol-state deployment window — confirmatory prereg (doc only)

STATUS:    frozen confirmatory prereg for review. Docs only — the run happens only
           after this merges AND the committed runner is separately reviewed.

WHAT:      Commit `doc/research/2026-08-18-vol-switch-confirmatory-prereg.md`: the
           confirmatory test of the last standing near-term bull-alpha lead — the
           tail skill's volatility ON-switch. Frozen: hypothesis + its formation data
           declared first (625-day clf corpus 2023-10..2026-03); state = SPY 20d
           realized vol > 13.5% (PIT scalar, plane-independent — the regime label was
           MEASURED unusable: BULL_VOLATILE = 7% of days / 3 eligible blocks on the
           serving plane); PRIMARY corpus 2017-01..2023-09 strictly pre-exploration
           (geometry counted BEFORE the rule: 19 ON-eligible blocks under both state
           definitions); scoring = production recipe VERBATIM via the reviewed refit
           engine (#996 lineage), quarterly expanding refits + 60td embargo; decision
           rule P1 (one-sided ON>0, block-t≥2.0, powered) + P2 (ON−OFF>0, t≥1.0,
           survivor-resistant structural half); guards + pre-frozen consequences
           (CONFIRMED → shadow-first design only; PARTIAL → doubled shadow burden;
           REFUTED → the line closes and the near-term bull discovery arm is recorded
           exhausted).

WHY/DIR:   Operator-directed bull-alpha program (08-18). After 0/5 zero-cost candidates
           survived the screens (#992/#999/#1000), the vol-switch exploratory finding
           (+0.67-0.76 SD in high-vol, vol-cohort-matched clean, difference uncertified)
           is the one lead with both evidence and a powered confirmation path.

EVIDENCE:
  artifact:      the prereg + this doc. No code, no run, no live change.
  prod or exp:   neither — prereg only.
  existing data: [VERIFIED/MEASURED 08-18, counted BEFORE freezing the rule] serving-
                 plane label corpus (backtesting#114 committed CSV): BULL_VOLATILE 185
                 days total / 3 eligible primary blocks → regime-label state REJECTED;
                 SPY parquet vol-state geometry: primary 1,697 td, 821/808 ON days
                 (fixed/expanding definitions), 19 ON-eligible blocks BOTH; exploratory
                 formation numbers + power calc from the 08-18 tail-switch memo
                 (block-σ≈0.54, MDE≈0.34 vs observed ~0.7).
  best-known?:   yes — the decisive corpus is disjoint from the hypothesis's formation
                 window (the strongest anti-overfit design available without waiting
                 years); the state is a raw PIT scalar with no detector dependence
                 (survives the pending regime repair); P2 carries the survivor-resistant
                 structural claim; ONE primary claim (no family inflation); consequences
                 pre-frozen incl. the honest REFUTED outcome.
  scope:         "freezes the confirmatory. Authorizes, AFTER merge + a reviewed runner
                 PR: the refit campaign + ONE scoring run (minutes, local, $0), results
                 as a separate PR. CONFIRMED authorizes only a shadow-first deployment-
                 window design PR — never a production change; activation remains
                 operator-gated."

TESTS:     none — doc-only PR.

NEXT:      codex review → runner PR (reviewed BEFORE execution, reusing the #996 refit
           engine) → the one run → results PR → on CONFIRMED/PARTIAL, the deployment-
           window design PR (operator-gated activation).
