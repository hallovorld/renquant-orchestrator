# Progress — META score attribution deep dive (2026-07-11)

## What

Mechanistic attribution of why the live XGB panel's META score FELL (raw −0.047 → −0.176,
60d mu 0.019 → 0.006) across 2026-07-06..07-10 while META rallied +11.5%. Follow-up to the
META no-buy forensics (PR #473); operator framed it as "根本问题".

## Outcome

**Verdict: LEARNED model behavior, not a serving artifact.** STD60
(`rolling_std(close,60)/current_close` — price in the denominator) explains 74% of the
decline: the rally itself deflated META's dispersion feature across 29 learned split
thresholds sitting at the training mean. Panel-wide the same mechanism moved the whole
cross-section (33% of META's Δ common / 67% idiosyncratic on the 37-name common set).
Not anti-momentum: the model simultaneously top-ranks FTNT (+98%/60d) because its
dispersion is huge. Full evidence, SHAP tables, partial-dependence proof, and the
fundamentals-coverage finding in `doc/research/2026-07-11-meta-score-attribution.md`.

Key checks [VERIFIED]:
- Same model all week (sha `5211f6be…` in all 3 run bundles == file on disk == weekly
  rollback copies).
- Offline reproduction of recorded `raw_panel`: corr 0.983-0.984 per day; META delta
  reproduced at 95%.
- Fund-freshness clip bug (base-data #26 / pipeline #151): fixed AND feed rebuilt
  (axis to 2026-07-10). Cleared as driver. NEW finding: ey/b2p/gp coverage is broken
  (META never finite; 67-317 of 826 finite) → median-imputed = valuation-blind.
- `demean_cross_sectional: false` in pinned + live config — the 06-25 monitored
  exception is no longer active; recorded mu has no demean (memory note stale).

## Follow-ups (recommended, not implemented)

1. base-data: repair earnings_yield/book_to_price/gross_profitability coverage in
   `sec_fundamentals_daily.parquet` + alert on per-column imputed share.
2. decision-ledger: forward-validate the STD60 rebound tilt (faded low-STD60 cohort vs
   admitted high-STD60 cohort, fwd-60d excess).
3. Monitor scored-universe size swings (41→88 in one session).

## Boundaries

Read-only on all production paths; DB copied before opening; isolated git worktree;
no git in the live umbrella tree or primary checkouts; local compute only. Research +
progress docs only — no code, no config, no gate changes.
