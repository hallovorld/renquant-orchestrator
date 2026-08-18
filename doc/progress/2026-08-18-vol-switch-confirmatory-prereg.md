# Vol-state deployment window — confirmatory prereg (doc only)

STATUS:    frozen confirmatory prereg for review. Docs only — the run happens only
           after this merges AND the committed runner is separately reviewed.

WHAT:      Commit `doc/research/2026-08-18-vol-switch-confirmatory-prereg.md` + the
           formation-evidence bundle
           `doc/research/data/2026-08-18-tail-switch-exploratory/`: the confirmatory
           test of the last standing near-term bull-alpha lead — the tail skill's
           volatility ON-switch. Frozen: hypothesis + its formation data declared
           first (625-date clf corpus 2023-10..2026-03, committed bundle); state =
           SPY 20d realized vol > 13.5% (PIT scalar, plane-independent — the regime
           label was MEASURED unusable: BULL_VOLATILE = 7% of days / 3 eligible
           blocks on the serving plane); PRIMARY corpus 2017-01..2023-09 strictly
           pre-exploration, unit = 28 non-overlapping 60-TRADING-day blocks per the
           replay-protocol §1.2 dependence canon (geometry counted BEFORE the rule:
           19 ON-eligible fixed / 19 expanding / 18 both); scoring = production
           recipe VERBATIM via the reviewed refit engine (#996 lineage), quarterly
           expanding refits + 60td embargo; decision rule P1 (one-sided ON>0 via the
           §1.2 dependence-robust conjunction: NW-on-blocks + stationary bootstrap,
           α=0.05 one-sided, ESS≥6 fail-closed; MDE 0.32 SD at N=19 / 0.65 at the
           ESS floor) + P2 (ON−OFF>0, t≥1.0, annotation-grade; less level-sensitive,
           NOT survivor-proof); guards + pre-frozen consequences (CONFIRMED →
           shadow-first design only; PARTIAL → doubled shadow burden; REFUTED → the
           line closes and the near-term bull discovery arm is recorded exhausted).
           Review round 1 corrections are listed visibly in the prereg's CORRECTIONS
           section (block unit, inference, counts, expanding-variant anchor, MDE,
           survivorship wording).

WHY/DIR:   Operator-directed bull-alpha program (08-18). After 0/5 zero-cost candidates
           survived the screens (#992/#999/#1000), the vol-switch exploratory finding
           (+0.6656..+0.7556 SD in high-vol, vol-cohort-matched clean, difference
           uncertified — now a committed bundle, see EVIDENCE) is the one lead with
           both evidence and a powered confirmation path.

EVIDENCE:
  artifact:      the prereg + this doc + the committed formation bundle
                 `doc/research/data/2026-08-18-tail-switch-exploratory/` (frozen
                 definitions, scripts, result tables, series CSVs, geometry_check.py).
                 No run, no live change.
  prod or exp:   neither — prereg only.
  existing data: [VERIFIED — re-measured 2026-08-18 via the committed
                 geometry_check.py on data/ohlcv/SPY/1d.parquet, counted BEFORE
                 freezing the rule] primary corpus 1,697 td; 821/808 ON days
                 (fixed/expanding); 28 non-overlapping 60-td blocks; 19 ON-eligible
                 (fixed) / 19 (expanding) / 18 BOTH; 8 ON-dominant. [VERIFIED — prior
                 work, backtesting#114 committed CSV] BULL_VOLATILE 185 days / 3
                 eligible primary blocks on the serving plane → regime-label state
                 REJECTED. Formation numbers [VERIFIED — committed bundle]: T3 spread
                 +0.7556/+0.6656 SD, matched-T3 t=+3.12, Welch t=+1.56,
                 block-σ 0.5343/0.5410. Power [DERIVED — (t.95+t.80)·σ/√N,
                 σ=0.54 ASSUMED from the formation corpus]: MDE 0.32 SD at N=19,
                 0.65 SD at the ESS=6 floor, vs observed +0.67..+0.76.
  best-known?:   yes — the decisive corpus is disjoint from the hypothesis's formation
                 window (the strongest anti-overfit design available without waiting
                 years); the state is a raw PIT scalar with no detector dependence
                 (survives the pending regime repair); the unit + inference follow the
                 repo's frozen dependence canon (replay protocol §1.2: NW-on-blocks +
                 stationary bootstrap, ESS minima); P2 is the less-level-sensitive
                 structural annotation (survivor-clean evidence arrives only at the
                 PIT-universe / live-shadow stages); ONE primary claim (no family
                 inflation); consequences pre-frozen incl. the honest REFUTED outcome.
  scope:         "freezes the confirmatory. Authorizes, AFTER merge + a reviewed runner
                 PR: the refit campaign + ONE scoring run (minutes, local, $0), results
                 as a separate PR. CONFIRMED authorizes only a shadow-first deployment-
                 window design PR — never a production change; activation remains
                 operator-gated."

TESTS:     doc-only PR; the committed `geometry_check.py` was executed 2026-08-18 and
           reproduces every frozen §2/§3 geometry number (output: bundle README §3).

NEXT:      codex review → runner PR (reviewed BEFORE execution, reusing the #996 refit
           engine) → the one run → results PR → on CONFIRMED/PARTIAL, the deployment-
           window design PR (operator-gated activation).
