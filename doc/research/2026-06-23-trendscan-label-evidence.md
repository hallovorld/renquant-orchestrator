# Drift-free label (trend-scanning) — evidence record (2026-06-23)

STATUS:   evidence artifact for the model-capability roadmap. Self-contained, path-pinned,
          reproducible. Companion to `2026-06-23-residual-neutralization-evidence.md`.
RESULT:   trend-scanning's *relative* edge is robust — it beats raw `fwd_60d_excess` on BULL_CALM
          placebo-clean in **3/3 seeds** (mean +0.0149) and is **far more stable** (raw's
          placebo-clean is seed-noise around zero). BUT a label-shuffle control (added below)
          exposes a **wide, mildly-positive null** in this quick harness (shuffled ALL-IC
          +0.036 ± 0.046; the embargo-gap hypothesis was tested and REFUTED, cause undetermined)
          → **absolute IC magnitudes from this harness are NOT trustworthy**; only the relative/
          stability result and the placebo-clean *difference* (which cancels the shared floor)
          survive. This is a **promote-to-the-PROPER-gate** result (full production WF sanity
          + a multi-shuffle empirical null + a sim), NOT a validated edge and NOT a deploy.

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

## Label-shuffle control — exposes a wide, leaky null (important caveat)

The third production-sanity control (after A/A=seed-stability and time-shift=the gate's placebo)
is **label-shuffle**: shuffle the training label within each date, retrain, measure OOS IC vs
raw returns — it must collapse to ~0. It does **not**. Scripts:
`scripts/experiments/2026-06-23-trendscan-label-shuffle.py` and `...-shuffle-control.py`.

| shuffled label | ALL IC | BULL_CALM IC |
|----------------|--------|--------------|
| trend-scan (run 1) | +0.0201 | −0.0024 |
| trend-scan (run 2) | +0.0371 | +0.0478 |
| raw (control)      | +0.0479 | +0.0437 |

Findings:
- **Shared, not trend-scan-specific:** the RAW label shuffles to the same floor, so it is a
  property of the FEATURES/cuts (it inflates the raw label and the production model too), not a
  defect of the trend-scan label.
- **The shuffled null is WIDE and mildly positive.** A 5-shuffle multi-seed null (script
  `scripts/experiments/2026-06-23-trendscan-embargo-test.py`): raw shuffled ALL-IC = **+0.0360
  ± 0.0457**, trend-scan **+0.0409 ± 0.0462**. The std (~0.046) is as large as the mean — a single
  shuffle is useless as a pass/fail, and absolute IC must be judged against this ~+0.036 null, not 0.
- **The embargo-gap hypothesis was TESTED and REFUTED.** I suspected the floor was a train/test
  embargo gap (the cuts use a ~1-month gap for a 60-day-forward label). Re-running the 5-shuffle
  null **with a 90-day embargo** barely moved it (raw +0.0360 → **+0.0367**; trend-scan +0.0409 →
  +0.0286, within noise). So the floor is **NOT** the embargo gap; its cause is **undetermined**
  (a feature/measurement bias, not boundary label leakage). I have no confirmed fix, so I claim none.

**Consequence (direction unchanged):** the **absolute** IC magnitudes from this quick harness are
NOT trustworthy — they sit on a wide ~+0.036 null. What survives is (a) the **relative** result
(trend-scan beats raw across seeds) and (b) the **placebo-clean difference**, because `real −
placebo` **cancels a shared floor** present equally in both terms. The stability result also
survives. The absolute "~+0.019" must be re-measured against a proper empirical multi-shuffle null
before any weight is put on it.

## Conclusion (honest)

Trend-scanning's real value is **stability and low contamination**, not a big absolute IC. The
raw label's BULL_CALM placebo-clean is seed-noise (mean +0.0038, sign-flips by seed); the
trend-scan label is reliably ~+0.019 across seeds — because its **placebo is much lower** (less
regime-persistence contamination), so a larger *fraction* of its (smaller) signal is real. That
is exactly the drift-free property we wanted, and the **relative** edge over raw is robust (3/3
seeds, +0.0149 mean).

**But do not overclaim:**
- **Absolute IC magnitudes from this harness are not trustworthy** (the label-shuffle null is wide
  and sits at a ~+0.04 leakage floor; see above). Only the *relative* result and the placebo-clean
  *difference* (which cancels the shared floor) are safe to lean on.
- It **trades overall IC** for cleaner/stabler regime signal — at the portfolio level that may or
  may not be a net win; only a **sim** decides.
- One label spec (signed max-|t| over two forward windows), one dataset/period.

## Decision

- **Graduate trend-scanning to the PROPER gate** — not a deploy. The quick harness has done its
  job (cheap triage: neutralization rejected, fundamental-momentum rejected, trend-scan is the one
  survivor on the contamination-robust metric). Before any further weight:
  1. **Establish the empirical multi-shuffle null** (the floor is ~+0.036 ± 0.046, cause
     undetermined — the embargo-gap hypothesis was refuted) and re-measure trend-scan vs raw
     placebo-clean *against that null*, not against 0;
  2. run the **full production WF sanity** (`scripts/walk_forward_sanity.py`) on the trend-scan label;
  3. then a **sim** (portfolio P&L / Sharpe, not IC) — the decisive test, since absolute IC is
     untrustworthy here; P&L does not depend on the IC null.
- This is a **promote-to-validation** decision, NOT a deploy decision.
- Pairs naturally with **meta-labeling** as a conviction filter once the base label clears the
  corrected gate.

## Reproducibility

```
RenQuant/.venv/bin/python scripts/experiments/2026-06-23-trendscan-wf-gate.py            # gate
RenQuant/.venv/bin/python scripts/experiments/2026-06-23-trendscan-seed-robustness.py     # 3-seed A/A
RenQuant/.venv/bin/python scripts/experiments/2026-06-23-trendscan-label-shuffle.py        # shuffle control
RenQuant/.venv/bin/python scripts/experiments/2026-06-23-trendscan-shuffle-control.py       # raw-vs-ts shuffle
```
Run from the `RenQuant` umbrella root. Read-only on data; writes no canonical/production path.
