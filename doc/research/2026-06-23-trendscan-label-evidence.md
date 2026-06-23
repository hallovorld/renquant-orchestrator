# Drift-free label (trend-scanning) — evidence record (2026-06-23)

STATUS:   evidence artifact for the model-capability roadmap. Self-contained, path-pinned,
          reproducible. Companion to `2026-06-23-residual-neutralization-evidence.md`.
RESULT:   trend-scanning is the **first in-repo label to BEAT the raw `fwd_60d_excess` label on
          the metric that matters** — BULL_CALM placebo-clean IC **+0.0224 vs raw +0.0188** —
          but the margin is **thin** and it **costs overall IC**. Promote to the full gate +
          a sim, NOT to deploy.

After the momentum/drift-neutralization retrain was rejected
(`2026-06-23-residual-neutralization-evidence.md`), the roadmap's next untested in-repo model
lever is **drift-free labels**. This records the trend-scanning trial.

---

## Hypothesis

The 60d-excess label's slow drift IS the BULL_CALM placebo (a flat-but-high name scores the
same as a steadily-trending one). A **trend-scanning** label (Lopez de Prado) instead measures
the *statistical significance of the forward trend* — it rewards persistent, clean trends and
penalises noisy ones. If that is more "drift-free", its placebo (regime-persistence) component
should be lower and its BULL_CALM signal cleaner.

## Label construction (faithful + feasible in-repo)

- Data: `data/alpha158_291_fundamental_dataset_multih.parquet` carries RAW cumulative forward
  excess returns at h ∈ {5,10,20,60} (`fwd_{h}d_excess_raw`).
- Forward cum-return path per row: R(0)=0, R(5)=r5, R(10)=r10, R(20)=r20, R(60)=r60.
- For each candidate window (endpoints 20 and 60) fit OLS `R ~ h` (with intercept) and take the
  slope **t-statistic**; the trend-scan label = the SIGNED t-stat of the window with the larger
  |t| (the most statistically significant forward trend). This is the trend-scanning label.
- Regime label merged from the GMM regime dataset by (ticker, date).
- Sanity: rank-corr(trend-scan, raw `fwd_60d_excess`) = **0.751** — a genuinely different target,
  not the raw label relabeled.

## Gate (identical to the neutralization trial → directly comparable)

6-cut WF (test 2020→2025), XGB `rank:pairwise` d=5 η=0.05 (production params), features =
alpha158+fund base (regime probs excluded). IC measured vs RAW `fwd_60d_excess`, segmented per
regime. PLACEBO = label shifted +60d (predict t+120). placebo-clean = real − placebo. Within
this harness, raw vs trend-scan is apples-to-apples (same data, same gate).

### Per-regime WF summary (mean over 6 cuts), IC vs raw `fwd_60d_excess`

| variant   | kind    | ALL     | BULL_CALM | BEAR    | BULL_VOL |
|-----------|---------|---------|-----------|---------|----------|
| raw       | real    | +0.0671 | +0.0323   | +0.3202 | +0.0637  |
| raw       | placebo | +0.0455 | +0.0135   | +0.2509 | +0.0523  |
| trendscan | real    | +0.0468 | +0.0182   | +0.2402 | +0.0333  |
| trendscan | placebo | +0.0138 | **−0.0042** | +0.1559 | +0.0072 |

**BULL_CALM placebo-clean IC (real − placebo):**
- raw label:        +0.0323 − 0.0135 = **+0.0188**
- trend-scan label: +0.0182 − (−0.0042) = **+0.0224**  (≥ the +0.02 bar AND ≥ raw)

Per-cut detail: `doc/research/2026-06-23-trendscan-wf-gate.csv`.

## Conclusion (honest)

Trend-scanning is the **first in-repo lever to beat the raw label on BULL_CALM placebo-clean
IC** (+0.0224 vs +0.0188). The win is **not** from a stronger raw signal — the trend-scan
*real* IC is lower everywhere (ALL +0.047 vs +0.067; BULL_CALM +0.018 vs +0.032). It wins
because its **placebo is much lower** (BULL_CALM placebo −0.004 vs +0.014): the label carries
**less regime-persistence contamination**, so a larger *fraction* of its (smaller) signal is
real. That is exactly the drift-free property we wanted.

**But do not overclaim:**
- The margin over raw is **thin** (+0.0036 placebo-clean).
- It **trades overall IC** for cleaner regime signal — at the portfolio level that may or may
  not be a net win; only a sim decides.
- One label spec (signed max-|t| over two forward windows), one dataset/period.
- It has **not** been through the full production WF sanity (A/A + label-shuffle + time-shift)
  nor a backtest/sim.

## Decision

- **Graduate trend-scanning to the next validation stage** (the cheapest in-repo lever that has
  NOT failed): run the full production WF sanity suite on the trend-scan label, then a sim that
  measures portfolio P&L / Sharpe (not just IC) to see whether the cleaner-but-smaller signal is
  a net win net of the overall-IC cost. Only then consider a gated retrain/deploy.
- This is a **promote-to-validation** decision, NOT a deploy decision.
- Pairs naturally with **meta-labeling** as a conviction filter (a stronger base signal than the
  prior AUC-0.55 meta-label) — a follow-up once the base trend-scan label clears the full gate.

## Reproducibility

```
RenQuant/.venv/bin/python scripts/experiments/2026-06-23-trendscan-wf-gate.py
```
Run from the `RenQuant` umbrella root. Read-only on data; writes no canonical/production path.
