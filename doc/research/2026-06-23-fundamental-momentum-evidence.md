# Fundamental-momentum factor — evidence record (2026-06-23)

STATUS:   evidence artifact for the model-capability roadmap. Self-contained, path-pinned,
          reproducible. Informs the CONDITIONAL "analyst-revision / fundamental-momentum"
          roadmap bet.
RESULT:   **REJECTED.** Realized fundamental momentum (from in-repo SEC fundamentals) does NOT
          add a placebo-clean BULL_CALM edge — adding it HURTS, and its standalone signal is
          almost entirely regime-persistence (placebo), not stock selection.

## Why this experiment

The roadmap lists an **analyst-revision / fundamental-momentum** factor as a CONDITIONAL bet
gated on acquiring external estimate-revision data (proprietary: IBES/FactSet/Zacks/S&P; not
in-repo, and the financial-analysis MCPs need a one-time operator OAuth). Before paying that
acquisition cost, the cheap question is: does the **self-serviceable cousin** — *realized*
fundamental momentum, which we CAN build from in-repo SEC fundamentals — carry a BULL_CALM
edge? If yes, it pre-justifies acquiring the (forward-looking) estimate-revision data; if no,
the bet rests entirely on the as-yet-unowned estimate data.

## Construction (fully autonomous, in-repo)

- Data: `data/sec_fundamentals_daily.parquet` (earnings_yield, book_to_price,
  gross_profitability, roe, asset_growth — daily, 2016–2026, 829 tickers).
- Features: for each of the 5 factors, the trailing **63d (~1Q)** and **252d (~1Y)** change
  (improving fundamentals) → 10 fundamental-momentum features. Merged into the regime panel by
  (ticker, date); feature coverage 0.91.
- Gate: the SAME per-regime + placebo WF gate as the neutralization and trend-scan trials.
  Variants: BASE (existing alpha158+fund features), BASE+FM (+ the 10 FM features), FM_ONLY.

## Per-regime WF summary (mean over 6 cuts), IC vs raw `fwd_60d_excess`

| variant | kind    | ALL     | BULL_CALM | BEAR    | BULL_VOL |
|---------|---------|---------|-----------|---------|----------|
| BASE    | real    | +0.0635 | +0.0319   | +0.3002 | +0.0639  |
| BASE    | placebo | +0.0453 | +0.0079   | +0.2490 | +0.0517  |
| BASE+FM | real    | +0.0552 | +0.0223   | +0.2580 | +0.0581  |
| BASE+FM | placebo | +0.0550 | +0.0289   | +0.2632 | +0.0521  |
| FM_ONLY | real    | +0.0348 | +0.0211   | +0.1192 | +0.0350  |
| FM_ONLY | placebo | +0.0241 | +0.0202   | +0.1142 | +0.0178  |

**BULL_CALM placebo-clean IC (real − placebo):**
- BASE:    +0.0319 − 0.0079 = **+0.0240**
- BASE+FM: +0.0223 − 0.0289 = **−0.0066**  (adding FM *hurts*: placebo rises, real falls)
- FM_ONLY: +0.0211 − 0.0202 = **+0.0009**  (standalone signal is ~all regime-persistence)

Per-cut detail: `doc/research/2026-06-23-fundmom-wf-gate.csv`.

## Conclusion

**Realized fundamental momentum is not an orthogonal BULL_CALM edge.** The standalone FM signal
is almost entirely placebo (regime persistence: real +0.0211 vs placebo +0.0202 ⇒ clean
+0.0009), and *adding* it to the base actually **degrades** the base's placebo-clean BULL_CALM
IC (+0.0240 → −0.0066) — the FM features import persistence/drift the base model then leans on.

## Decision

- **Drop realized fundamental momentum** as a BULL_CALM lever (do-not-redo).
- This does **not** test *forward* analyst estimate-revision, which is economically different
  (forward-looking consensus changes are more persistent and less stale than realized
  fundamentals) — but the cheap proxy did **not** pre-justify acquiring that data. So the
  estimate-revision bet now rests entirely on its own (operator-gated) data acquisition, with
  no free pre-evidence in its favour. Recommend: do **not** prioritise the estimate-revision
  acquisition on the strength of fundamental momentum; revisit only if the trend-scanning label
  (the one promising in-repo lever) clears its full gate and a diversifying signal is wanted.

## Reproducibility

```
RenQuant/.venv/bin/python scripts/experiments/2026-06-23-fundmom-wf-gate.py
```
Run from the `RenQuant` umbrella root. Read-only on data; writes no canonical/production path.
