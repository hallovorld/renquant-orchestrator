# Idiosyncratic-residual neutralization — evidence record (2026-06-23)

STATUS:   evidence artifact for the model-capability roadmap. Self-contained, path-pinned,
          reproducible. Cited by `doc/research/2026-06-23-model-and-engineering-roadmap.md`.
RESULT:   the momentum/drift-neutralized retrain is **REJECTED by the per-regime WF gate**.
          The cheap aggregate residual audit was a **false positive** the gate caught.

This record exists so the residual-neutralization numbers in the roadmap are not naked prose:
it pins the dataset, window, residualization spec, folds/embargo, scripts, and raw outputs,
and states how the result relates to the BULL_CALM decision bar.

---

## Question

The BULL_CALM symptom (placebo IC ≈ real IC) is the textbook signature of factor/drift
contamination, not stock-selection alpha. **Hypothesis:** if we residualize the *label*
against industry + beta (+ trailing momentum/drift) and train XGB to predict that residual,
the model learns idiosyncratic alpha and the **BULL_CALM placebo-clean IC** rises to ≥ +0.02
(the signal-repair bar), letting `regime_admission` be re-enabled.

## Experiment A — cheap residual audit (aggregate, no placebo) → POSITIVE (misleading)

- Script: `scripts/experiments/2026-06-23-residual-audit.py`
- Data: `RenQuant/data/alpha158_291_fundamental_dataset.parquet`, recent ~1100 calendar days.
- Label: per-date OLS residual of `fwd_60d_excess` on **[sector dummies + BETA60]** (no momentum control).
- Eval: purged 3-fold, embargo 60d; OOS cross-sectional rank-IC measured vs **raw** `fwd_60d_excess`.
- Result: XGB on raw label OOS IC **+0.0321** (folds 0.0135 / 0.0916 / −0.0089); XGB on the
  sector+beta-residualized label OOS IC **+0.0342** (folds 0.0230 / 0.0704 / +0.0091); ratio 1.07.
- Naive read: "idiosyncratic alpha survives neutralization → neutralization retrain is the cheap win."
- **Why this is not decisive:** it is an *aggregate* OOS IC (all regimes pooled), it has **no
  placebo subtraction**, and it neutralizes sector+beta only (not the trailing-momentum drift
  that is the suspected BULL_CALM contaminant). It says nothing about BULL_CALM specifically.

## Experiment B — per-regime WF + placebo gate (decisive) → NEGATIVE

- Script: `scripts/experiments/2026-06-23-neutralized-wf-gate.py`
- Data: `RenQuant/data/alpha158_291_fund_regime_dataset.parquet` (carries the GMM regime probs).
- Regime label per date = argmax of {`regime_p_bull_calm`, `regime_p_bear`, `regime_p_bull_volatile`}.
  Row counts: BULL_CALM 336k, BULL_VOLATILE 294k, BEAR 22k (BEAR is small → noisy).
- Neutralized label = per-date OLS residual of `fwd_60d_excess` on **[sector dummies + BETA60 +
  ROC60]**. ROC60 (trailing-60d return) is the **drift/momentum control** — the new term vs Exp A,
  aimed directly at the BULL_CALM placebo root. Label corr(neutral, raw) = 0.894.
- WF: 6 cuts (train 2017→…, test 2020→2025), XGB `rank:pairwise` d=5 η=0.05 (production params),
  features = alpha158+fund base (regime probs **excluded** from features). IC measured vs **raw**
  `fwd_60d_excess`, segmented per regime. **Placebo** = shift the label +60d (predict t+120),
  retrain, same per-regime IC. "placebo-clean" = real − placebo.

### Per-regime WF summary (mean over 6 cuts), IC vs raw `fwd_60d_excess`

| variant | kind    | ALL     | BULL_CALM | BEAR    | BULL_VOL |
|---------|---------|---------|-----------|---------|----------|
| raw     | real    | +0.0635 | **+0.0319** | +0.3002 | +0.0639 |
| raw     | placebo | +0.0453 | +0.0079   | +0.2490 | +0.0517 |
| neutral | real    | +0.0349 | **−0.0172** | +0.2539 | +0.0441 |
| neutral | placebo | +0.0513 | +0.0119   | +0.2531 | +0.0579 |

**BULL_CALM placebo-clean IC (real − placebo):**
- raw label:        +0.0319 − 0.0079 = **+0.0240**  (already ≥ the +0.02 bar on this dataset/window)
- neutralized label: −0.0172 − 0.0119 = **−0.0291**  (worse — the neutralized model is anti-predictive in BULL_CALM)

Per-cut detail: `doc/research/2026-06-23-neutralized-wf-gate.csv`.

## Conclusion

**The momentum/drift-neutralized retrain does NOT recover BULL_CALM — it destroys the
BULL_CALM signal.** In BULL_CALM the model's edge *is* substantially momentum/drift
continuation; residualizing the label against ROC60 removes exactly the component that
works there, flipping the regime IC negative. Exp A's positive was an artifact of (a)
pooling regimes, (b) omitting the placebo subtraction, and (c) neutralizing sector+beta
only. The per-regime placebo gate reverses it. **This is the gate doing its job — catching
a cheap false positive before it reached a retrain/deploy.**

Secondary observation (not an action): on this regime dataset over 2020–2025 the **raw**
label's BULL_CALM placebo-clean IC is **+0.024**, i.e. already at the bar — which does not
match the live "+0.0149, placebo > real" claim. That gap is a measurement/period question
(different universe/window), logged here, not acted on.

## Decision for the roadmap

- **Drop THIS neutralization-retrain spec.** The specific sector+beta+momentum(ROC60) label
  residualization is tested and rejected for the regime it was meant to fix. This is strong
  evidence against this class of momentum/drift-neutralized labels in BULL_CALM — it is **not**
  proof that every in-repo relabeling is dead (other neutralizers / drift-free labels untested).
- The remaining model frontier: drift-free **labels** (trend-scanning + meta-labeling — still
  in-repo, untested) and — *conditional on data acquisition* — the **analyst-revision**
  factor. The cheapest test on the neutralization axis specifically has been spent.
- Engineering track (self-consistent bundle + atomic deploy) is unaffected and remains the
  parallel force-multiplier.

## Reproducibility

```
RenQuant/.venv/bin/python scripts/experiments/2026-06-23-residual-audit.py        # Exp A
RenQuant/.venv/bin/python scripts/experiments/2026-06-23-neutralized-wf-gate.py    # Exp B
```
Run from the `RenQuant` umbrella root (the scripts read `data/…` and the pinned sector map).
Both are read-only on data; neither writes any canonical/production path.
