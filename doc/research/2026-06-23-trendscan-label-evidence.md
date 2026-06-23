# Drift-free label (trend-scanning) — evidence record (2026-06-23)

STATUS:   evidence artifact for the model-capability roadmap. Self-contained, path-pinned,
          reproducible. Companion to `2026-06-23-residual-neutralization-evidence.md`.
RESULT:   trend-scanning BEATS the raw `fwd_60d_excess` label on BULL_CALM placebo-clean IC
          **in all 3 seeds** (mean +0.0149 advantage) and is **far more stable** — raw's
          placebo-clean is seed-noise around zero (mean +0.0038), trend-scan is reliably
          ~+0.019. Its absolute placebo-clean averages +0.0187 (hits the +0.02 bar in 2/3
          seeds). Promote to the full gate + a sim, NOT to deploy. (The single-seed headline
          "+0.0224 vs +0.0188" below overstated the raw baseline — see Seed robustness.)

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

Per-cut detail: `doc/research/2026-06-23-trendscan-wf-gate.csv`. **The single-seed numbers above
are seed-42; read them with the seed-robustness check below — the raw baseline is seed-lucky.**

## Seed robustness (the thin margin demanded this)

The +0.0036 single-seed margin is small, so the gate was re-run across seeds {42,43,44}
(BULL_CALM placebo-clean, raw vs trend-scan). Script:
`scripts/experiments/2026-06-23-trendscan-seed-robustness.py`.

| seed | raw placebo-clean | trend-scan placebo-clean | trend-scan − raw |
|------|-------------------|--------------------------|------------------|
| 42   | +0.0188           | +0.0224                  | +0.0036          |
| 43   | **−0.0105**       | +0.0115                  | +0.0220          |
| 44   | +0.0032           | +0.0223                  | +0.0191          |
| mean | **+0.0038**       | **+0.0187**              | **+0.0149**      |

This **changes the framing** (and corrects the seed-42 headline):
- Trend-scan beats raw on BULL_CALM placebo-clean in **3/3 seeds**, and the mean advantage
  (+0.0149) is much larger than the seed-42 margin (+0.0036).
- The seed-42 **raw** baseline (+0.0188) was lucky-high: raw's placebo-clean is essentially
  **seed-noise around zero** (mean +0.0038, one seed negative). Trend-scan is **stable** (+0.0224
  / +0.0115 / +0.0223, mean +0.0187).
- Absolute bar: trend-scan clears +0.02 in **2/3** seeds; mean +0.0187 is just under +0.02.

## Conclusion (honest)

Trend-scanning's real value is **stability and low contamination**, not a big absolute IC. The
raw label's BULL_CALM placebo-clean is seed-noise (mean +0.0038, sign-flips by seed); the
trend-scan label is reliably ~+0.019 across seeds — because its **placebo is much lower** (less
regime-persistence contamination), so a larger *fraction* of its (smaller) signal is real. That
is exactly the drift-free property we wanted, and the **relative** edge over raw is robust (3/3
seeds, +0.0149 mean).

**But do not overclaim:**
- The **absolute** placebo-clean (mean +0.0187) is **just under the +0.02 bar** (clears it 2/3 seeds).
- It **trades overall IC** for cleaner/stabler regime signal — at the portfolio level that may or
  may not be a net win; only a **sim** decides.
- One label spec (signed max-|t| over two forward windows), one dataset/period.
- It has **not** been through the full production WF sanity (A/A + label-shuffle) nor a backtest/sim.

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
RenQuant/.venv/bin/python scripts/experiments/2026-06-23-trendscan-wf-gate.py          # gate
RenQuant/.venv/bin/python scripts/experiments/2026-06-23-trendscan-seed-robustness.py   # 3-seed check
```
Run from the `RenQuant` umbrella root. Read-only on data; writes no canonical/production path.
