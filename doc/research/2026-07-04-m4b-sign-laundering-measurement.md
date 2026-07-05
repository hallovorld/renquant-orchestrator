# M4-b Sign-Laundering Measurement — Production Calibrator Audit

DATE: 2026-07-04
STATUS: VERIFIED (harness run against live DB, read-only)
TAGS: M4-b, sign-laundering, calibrator, gate-diagnostics

## Bottom line

Sign laundering is **worsening**: mean rate climbed from 3.3% (early period) to
10.1% (recent period). On the most recent full-panel run (2026-07-02), 16/83
candidates (19.3%) had raw scores in the laundering zone — negative raw signal
mapped to positive μ by the calibration curve.

## Method

Ran `sign_laundering_harness.audit_laundering_history()` against the production
`runs.alpaca.db` (read-only). For each run with both `raw_score` and `mu` columns
populated, counted candidates whose raw score falls in the laundering zone
`(neutral_raw, 0)` AND whose calibrated `mu > 0`.

Production calibrator: `panel-rank-calibration.weekly_rollback_2026-07-04.json`
- **neutral_raw = −0.2667** (updated from previously cited −0.2902; calibrator
  was refit after the 2026-07-01 fingerprint-mismatch re-stamp)

## Results (33 trading dates, 2026-04-23 → 2026-07-02)

| Metric | Value |
|--------|-------|
| Mean laundering rate | 7.9% |
| Median | 6.4% |
| Min / Max | 0.0% / 20.9% |
| Trend | worsening (3.3% → 8.0% → 10.1% by tercile) |

### Recent 5 dates (full 83-name panel)

| Date | Laundered / Scored | Rate |
|------|-------------------|------|
| 2026-06-26 | 12/79 | 15.2% |
| 2026-06-29 | 9/43 | 20.9% |
| 2026-06-30 | 13/83 | 15.7% |
| 2026-07-01 | 11/83 | 13.3% |
| 2026-07-02 | 16/83 | 19.3% |

### Period breakdown

| Period | Dates | Mean rate |
|--------|-------|-----------|
| Early (Apr–May) | 11 | 3.3% |
| Middle (early Jun) | 11 | 8.0% |
| Late (late Jun–Jul) | 11 | 10.1% |

## Prior "44/90" figure

The memory-recorded "44/90 sign-laundered" figure was NOT reproduced at the
current calibrator neutral. The highest observed count was 17/83 (20.5%) with
a −0.2902 neutral override. The 44/90 figure likely used a different definition
(e.g., "any negative raw AND positive mu" without the laundering-zone constraint,
or a different calibrator vintage).

## Implications

1. **Worsening trend is concerning** — the calibration surface is drifting further
   from the raw score distribution as time passes and market conditions shift.
2. **~15-20% laundering rate on recent runs** means roughly 1 in 5-6 buy candidates
   carries a model-contradicted signal (negative raw → positive μ). Some of these
   survive downstream gates and get bought.
3. **The matched-breadth protocol** (M4-b spec in the master plan) compares portfolio
   performance WITH vs WITHOUT laundered names — that comparison requires accumulating
   more forward returns from the decision ledger (S5 dependency).
4. **Recalibration** (fitting a new calibrator on recent data) would mechanically
   update neutral_raw and compress the laundering zone. However, per fix-wave
   protection contract rule 1, this is a behavior change requiring a separate
   operator-visible design PR.

## Data sources

- DB: `runs.alpaca.db` candidate_scores table (4,520 rows, 92 runs)
- Calibrator: `panel-rank-calibration.weekly_rollback_2026-07-04.json`
- Harness: `src/renquant_orchestrator/sign_laundering_harness.py`
- Full JSON output: saved to scratchpad (session-local)
