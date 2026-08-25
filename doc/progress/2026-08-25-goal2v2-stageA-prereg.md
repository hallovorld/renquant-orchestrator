# GOAL-2v2 Stage-A prereg PR

STATUS: TERMINAL RECORD (r4). The K5 screen ran during review at the
operator's request and returned its frozen result: no base passed. Under
the document's own terms Stage A stops here; 2020–2023 is not run. This PR
merges as the RECORD of that stop. The successor development-selection
design (2016–2019 declared consumed, attempts enumerated, confirmatory
prereg frozen after development) requires operator acknowledgement first,
since it amends #1061's frozen-before-fit contract.

§4(b) — everything below MEASURED before writing, not assumed:
- OHLCV panel: 2,790 tickers, ~50% begin ≤2016-01, median ~2,604 rows
  [MEASURED — 200-ticker sample read 2026-08-25].
- Macro inputs already in the committed stores: VIXCLS, DGS10, T10Y2Y,
  BAMLH0A0HYM2 from 2016-03 [MEASURED — parquet reads]; SPY 2016-01→
  present; sector map present. Train start 2016-07 gives ≥3mo warm-up.
- All four base families are price-only BECAUSE the fundamental axis's
  historical depth is unmeasured — deferred to a later stage rather than
  asserted ([[asserted-instead-of-measured]]).

Frozen content: forward-chaining fold dates (embargo ≥20td, gaps verified in
the table); universe rule (list materialized + sha'd pre-outcome); four base
recipes with provenance channels and pre-2020 citations per #1061 §1;
generic xgb constants; meta inputs; paired block-t decision rule vs two
pre-named baselines (B1 selected on OOF only); ex-ante MDE with minimum
effect of interest ΔIC=0.010; four kills incl. assembled n_eff<12 (the
ceiling-vs-measured distinction from #1061 r2/r3) and a 0b-α-style
provenance review with per-base quarantine. C3 §7 survivorship disclosure
carried verbatim. No production path is written; bulk intermediates go to a
NEW data/goal2v2/ directory no production job reads.

WHY/DIR: operator approved the GOAL-2v2 direction 2026-08-25; the mandated
order is prereg → codex → runner. The runner PR follows this merge and may
refuse but not reinterpret.
