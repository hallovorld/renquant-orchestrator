# 104 zblend evaluability POC

STATUS:   complete for orchestration-level audit; not a return-efficacy verdict.
WHAT:     adds a read-only daily-run audit, committed 2026-08-04 evidence, and
          focused tests for whether a panel-versus-zblend comparison is evaluable.
WHY/DIR:  zblend is currently an equal-z-sum serving rule, but a post-switch
          production-versus-shadow pair cannot establish value if it lacks an
          independent panel control or mature forward labels.
EVIDENCE:
artifact:      `doc/research/evidence/2026-08-05-zblend-evaluability-poc.json`
prod or exp:   exp — read-only audit over persisted production and shadow run
               bundles; no live-path mutation. `[VERIFIED — scripts/research_zblend_evaluability_poc.py; 2026-08-05]`
existing data: latest complete 2026-08-04 production and shadow books each had
               88 names, 87 common, Top-10 overlap 10/10, Spearman
               `0.999744842167`, recorded scorer `blend` in both populated
               identity-stamped rows, and zero mature `fwd_60d` values.
               `[VERIFIED — doc/research/evidence/2026-08-05-zblend-evaluability-poc.json + focused pytest; 2026-08-05]`
best-known?:   yes — for the persisted 2026-08-04 run pair, this is the
               best-known evaluability read; it returns `NOT_EVALUABLE`, not a
               return verdict. `[VERIFIED — script + evidence JSON; 2026-08-05]`
scope:         this repository only audits persisted orchestration run bundles;
               no scorer, training, backtest, or execution behavior changes.
NEXT:     pipeline/backtesting owners restore a same-day full-universe `panel`
          control, preregister S2 estimand/costs/dependent-label inference, and
          evaluate mature prospective outcomes before any efficacy claim or
          adaptive blend-weight change.
