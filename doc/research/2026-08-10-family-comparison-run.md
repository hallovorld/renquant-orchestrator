# Family comparison ran: no separation detected between served and replay under the prespecified low-power CI

STATUS: the ONE execution of the merged design freeze
`doc/design/2026-08-09-family-comparison-freeze.md` (orch#951). No
verdict authority (the doc grants none). Task #26's outcome increment.

## 1. What ran

Exactly the frozen table: window 2026-05-20..07-31; SERVED =
`ticker_daily_state.panel_score` (canonical run/day, the record verified
in orch#948/#949/#950); REPLAY = the mean of the three fold-8 xgb_mom
boosters from the harness's frozen seed tuple (42,43,44), trained by the
harness recipe on the frozen corpus (sha asserted, 708,723 rows,
purged 0 — expected: the 91-day fold gap exceeds the ~84-day label
window by construction); k=5; per-day intersection universe with
coverage accounting; stationary bootstrap 5/2000/99.

The runner was mechanically rehearsed BEFORE this run on a synthetic
fixture (4 controls: planted-effect, no-information null, coverage
fail-closed, skip rule — all PASS; 4 bugs caught and fixed pre-run,
including a vacuous boundary assertion and nondeterministic tie order).

r2 (review P0 relocation): all model internals (fold-8 training,
normalization, scoring) live in renquant-model
`scripts/family_comparison_replay_scorer.py` (model#220), which
publishes the hash-pinned predictions artifact
`doc/design/frozen/2026-08-10-family-comparison-replay-predictions.csv`
(7,592 rows, sha b549940e…; committed pytest controls carry the
rehearsal fixture — the auditable control surface). This repo's runner
is JOIN-ONLY: it asserts the predictions and extension-parquet shas
against the model#220 manifest, joins labels and the live record, and
computes the frozen table. The r2 rerun reproduced r1's daily table
BYTE-IDENTICALLY [VERIFIED — diff clean, 2026-08-10].

## 2. Units — read this first

`fwd_5d_excess` in the corpus is **CSZScoreNorm: the per-day
cross-sectional z-score of 5d excess return** (builder docstring,
`build_alpha158_qlib.py:66`; verified: per-day mean ≡ 0, std ≡ 1 across
the corpus). Every number below is in per-day σ units, NOT raw return.
(Recorded plainly because the raw-return misreading was almost published:
the label tail — e.g. WDC 2026-06-11 at 6.37 — looked like a data defect
until checked against the OHLCV file, where the true 5d move is +41%,
i.e. ≈6σ that day. The tail is the convention, not a defect.)

## 3. Result [VERIFIED — committed runner outputs, exit 0]

| quantity | value (per-day σ of 5d excess) |
|---|---|
| days compared / skipped | 31 / 5 |
| SERVED top-5 mean excess-z | +0.113 |
| REPLAY top-5 mean excess-z | +0.096 |
| mean daily diff (SERVED − REPLAY) | **+0.017** |
| median daily diff | +0.024 |
| bootstrap 95% CI on the diff | **[−0.154, +0.189]** |
| oracle top-5 (plumbing control) | +1.668 — strongly positive as constructed; sane as a top-5-of-~90 z mean |

**No separation detected under this prespecified low-power CI:** the CI
spans ±0.15-0.19σ around a +0.017σ point estimate. Failure to reject is
NOT evidence of equivalence — the statement this table carries is only
that neither family measurably outperformed the other AT THIS POWER.
Both arms are mildly positive in top-5 selection.

## 4. Reading (no verdict — the doc grants none)

1. The serving-fidelity line (#948-#950) showed the traded RECORD is
   trustworthy; this table now shows the traded family's top-5 selection
   quality on realized 5d outcomes shows no detected separation from
   the validated replay family's — on 31 days, k=5, 5d horizon; an
   equivalence claim would need an equivalence test at far higher power.
2. 31 autocorrelated days at a 5d horizon is a LOW-POWER window; the CI
   width says exactly that. This diagnostic cannot arbitrate a serving
   change by itself — and per the frozen doc it may not: any
   serving-change proposal runs its own prereg.
3. Interpretations fixed as the only computable readings (flagged during
   rehearsal): the outcome benchmark is the labelled subset of the
   per-day intersection (unlabelled names cannot contribute to either
   side); the oracle lives as a `_daily.csv` column and a summary line.
4. Bearing on the qp re-enable chain (the 05-23 recorded condition):
   this is diagnostic INPUT, not the required "WF shows
   benchmark-relative alpha survives the strict admission gate" evidence
   — that evidence remains unbuilt.

## 5. Reproduction

```
python doc/research/data/2026-08-10-family-comparison-runner.py \
  <replay-predictions.csv>  # model#220 artifact, sha-asserted \
  <alpha158_extension_fund.parquet> <runs.alpaca.db> \
  data/2026-08-10-family-comparison
```
Four arguments: the model#220 predictions artifact (sha asserted against
its manifest), extension fund parquet (sha asserted; orch#948 recipe),
DB, out prefix. The model-side scorer's own reproduction recipe lives
with model#220.
Committed evidence (`…_daily.csv`, `…_coverage.csv`, `…_summary.json`)
is the runner's verbatim output. Rehearsal report and fixture live in
session scratch (controls summarized in §1; the runner asserts SEEDS and
the fold-8 train end against the harness text at startup).
