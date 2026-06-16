# RFC — Replace the threshold regime carve-outs with a statistical regime model (HMM / Markov-switching)

**Status:** RFC / awaiting review (no code change here)
**Motivation:** operator question after the 2026-06-11 false-BEAR — *"is the regime
rule too specific / narrow / not generic enough? Is there an industry standard?
Any lib / package / open source?"*
**Companion:** the 2026-06-11 false-BEAR incident audit, now folded into the
system feature map / git history; pipeline PR #112 (the **stopgap** patch).

---

## 0. Executive summary

The current regime layer is an **accreted stack of hand-tuned threshold
carve-outs** — 5-day / 20-day vol & return cutoffs, a Hurst test, a CUSUM
change-point flag, a GMM, and a hard-BEAR override — wired together by magic
numbers (0.25, 0.35, −0.04, −0.08, 1.5, 200). It has **no unifying model and no
persistence**: every bar is judged independently, so a single anomalous bar can
flip the whole book (2026-06-11: one 5-day vol blip → `hard_bear` → all buys
blocked). PR #112 is a correct **stopgap** (require-both + 200-DMA trend filter),
but the operator's instinct is right: **this is the crudest tier of regime
detection.**

The industry / academic standard is a **statistical regime model with a
transition matrix** — the **Markov-switching model (Hamilton 1989)** / **Gaussian
HMM**. Its transition probabilities make regimes **sticky by construction**, which
**structurally eliminates the single-bar false-flip** class of bug. The reference
libraries are **already installed** in our venv (`statsmodels`, `hmmlearn`,
`arch`). This RFC proposes a **shadow-first migration** to such a model, A/B'd
against the current detector.

---

## 1. Where we are vs. the standard (tiers of regime detection)

| Tier | Method | Persistence? | In our stack |
|---|---|---|---|
| 1 | **Threshold rules** (vol > X, ret < Y) | ✗ none | ← the BEAR override + 5d/20d cutoffs |
| 2 | **Trend filters** (Faber 200-DMA; TS-momentum) | weak (lagging MA) | added by #112; CTA-standard |
| 3 | **Gaussian Mixture (GMM)** clustering | ✗ (no time dynamics) | `ctx.gmm` exists, partly used |
| 4 | **HMM / Markov-switching (Hamilton 1989)** | ✅ transition matrix | **proposed core** |
| 5 | **(MS-)GARCH** conditional-vol regimes | ✅ | candidate vol channel |
| 6 | **Change-point / jump models** (CUSUM, BOCPD, Nystrup jumps) | ✅ | CUSUM fragment exists |

We are operating at **Tier 1** with a Tier-2 patch. The standard sits at **Tier 4**.

---

## 2. Why a transition-matrix model is the *generic* cure

The 2026-06-11 bug is not a bad threshold — it is the **absence of memory**. A
threshold detector computes `P(bear | today's bar)`. A Markov-switching / HMM
computes the **smoothed** `P(state_t | all bars)`, where consecutive states are
linked by a transition matrix `A[i,j] = P(state_t=j | state_{t-1}=i)`. Empirically
`A` is **strongly diagonal** (regimes persist for weeks–months; cf. Hamilton's GNP
model: high-state persistence ≈ 0.90 → expected duration ≈ 10 periods). Therefore:

- A **single** anomalous bar moves the smoothed state probability only marginally
  — it cannot, by itself, flip the regime. **Persistence is built in**, not bolted
  on via ad-hoc cooldown/hysteresis counters (which we currently hand-maintain in
  `RegimeFinalizeTask`).
- Regime **boundaries are learned** from the data's own covariance structure, not
  set by magic numbers — directly answering "too specific / not generic."
- It yields **calibrated probabilities** (a real `confidence`), replacing the
  current `conf=0.50` placeholder and enabling principled size-scaling.

This is the canonical academic *and* practitioner approach to financial regime
detection (Hamilton 1989; Kim & Nelson 1999; Ang & Bekaert 2002 regime-switching
asset allocation; Nystrup et al. 2017–2020 for the modern HMM/jump-model line).

---

## 3. Libraries / open source (already available unless noted)

| Library | Role | In venv |
|---|---|---|
| `statsmodels.tsa.regime_switching.MarkovRegression` / `MarkovAutoregression` | Hamilton Markov-switching — the reference implementation | **✅ installed** |
| `hmmlearn` (`GaussianHMM`, `GMMHMM`) | go-to Python HMM for financial regime detection | **✅ installed** |
| `arch` (Kevin Sheppard) | GARCH / conditional-vol regime channel | **✅ installed** |
| `sklearn.mixture.GaussianMixture` | GMM (Tier 3), already used | **✅ installed** |
| `ruptures` (C. Truong) | offline/online change-point (PELT/CUSUM) | ⬜ optional add |
| `jumpmodels` (Nystrup) | statistical jump models (sparse, robust HMM cousin) | ⬜ optional add |

Reference notebooks/tutorials are mainstream: statsmodels' Markov-switching
examples (Hamilton GNP, Kim–Nelson–Startz, Filardo time-varying), the `hmmlearn`
"market regime" example, and the widely-cited QuantStart "Hidden Markov Models for
Regime Detection" walkthrough. **No proprietary dependency is required.**

---

## 4. Proposed design (shadow-first)

**Model.** A small **Gaussian HMM / Markov-switching** with **K=3–4 states** fit on
a low-dimensional feature vector per bar — e.g. `[SPY daily return, rolling
realized vol]` (optionally a trend term). Start with `statsmodels MarkovRegression`
(mean+variance switching on SPY returns) as the reference; cross-check with
`hmmlearn GaussianHMM` on `[ret, vol]`. Emit **smoothed state probabilities**.

**Regime mapping.** Order states by `(mean, vol)` and map to the existing labels
`{BULL_CALM, BULL_VOLATILE, CHOPPY, BEAR}` (low-vol/positive-drift → BULL_CALM;
high-vol/negative-drift → BEAR; etc.). `confidence = max_k P(state=k)`.

**Trend overlay (keep the good part of #112).** Gate the *offensive* posture with a
200-DMA sanity filter so the book is never fully bearish while SPY is in a
confirmed uptrend — best-practice hybrid (HMM core + trend overlay).

**Persistence/hysteresis.** Comes **free** from the transition matrix; retire the
hand-maintained `transition_uncertainty_bars` cooldown (or keep as a thin floor).

**Crisis safety net.** Retain the unconditional 20-day GFC routes (35% vol / −8%
ret) as a fast hard-stop independent of the fitted model (a fitted model can lag a
gap-crash); the HMM replaces the **over-sensitive 5d carve-out and the GMM
confidence-veto**, not the catastrophe stop.

**Artifact + cadence.** Fit weekly (cf. the existing weekly retrain), persist the
fitted model as a pinned artifact (like `prod/spy-gmm-regime.json`), score daily.
Deterministic + reproducible per the pinned-subrepo model.

---

## 5. Migration plan (no flag day)

1. **Shadow:** add a `MarkovRegimeShadowTask` that fits/loads the HMM and **logs**
   its label + probabilities alongside the live threshold detector — **decides
   nothing**. Collect ≥ several weeks of paired labels.
2. **Backtest A/B:** replay the trailing window with regime = {threshold vs HMM};
   measure (§6). Promote only on improvement.
3. **Cutover behind a config flag** (`regime.engine: "threshold" | "hmm"`), default
   `threshold` until the A/B clears, then flip. Keep the threshold engine available
   for rollback.

---

## 6. Validation metrics

- **False-BEAR rate:** fraction of `hard_bear` days where SPY > 200-DMA and 20-day
  drawdown < 5% (2026-06-11 must be **0**).
- **Regime stability:** average regime duration / flip count (HMM should be far
  less jumpy than the threshold detector).
- **Label agreement** with an ex-post trend/drawdown oracle on labeled history
  (SVB, Aug-2024, COVID, 2022 bear).
- **Economic:** buy-admission count, turnover, and **net-of-cost PnL / Sharpe** on
  replay — the only test that ultimately matters.

---

## 7. Risks & mitigations

- **HMM instability / label-switching / fit-window sensitivity:** fix K, seed, and
  a sufficient lookback; order states deterministically by (mean,vol); persist a
  pinned artifact; weekly refit only. Cross-validate statsmodels vs hmmlearn.
- **Model lag on gap-crashes:** keep the unconditional 20-day GFC hard-stop.
- **Overfitting the regime count:** prefer K=3 (bull/chop/bear) unless BIC clearly
  supports 4; report BIC/AIC.
- **Scope creep:** this RFC is the regime engine only; the buy-floor (P2),
  wash-sale (P3), and drawdown gate (P1) from the audit remain separate.

---

## 8. Recommendation

Ship the #112 stopgap now (book must trade). In parallel, **build the HMM /
Markov-switching engine in shadow** using the already-installed `statsmodels` /
`hmmlearn`, A/B it, and cut over behind a flag. That replaces the bespoke,
memory-less threshold carve-outs with the **generic, industry-standard,
persistence-bearing** model the operator asked for — while keeping the
catastrophe stop and a trend overlay as belt-and-suspenders.

## References
- Hamilton, J. (1989). *A New Approach to the Economic Analysis of Nonstationary
  Time Series and the Business Cycle.* Econometrica.
- Kim, C-J. & Nelson, C. (1999). *State-Space Models with Regime Switching.* MIT Press.
- Ang, A. & Bekaert, G. (2002). *International Asset Allocation with Regime Shifts.* RFS.
- Nystrup, Madsen, Lindström (2017–2020). *Regime-based asset allocation; learning
  HMMs with persistent states by penalizing jumps.*
- Faber, M. (2007). *A Quantitative Approach to Tactical Asset Allocation.* (200-DMA)
- Moskowitz, Ooi, Pedersen (2012). *Time Series Momentum.* JFE.
- Bollerslev (1986) GARCH; Sheppard, `arch`. Page (1954) CUSUM; Adams & MacKay
  (2007) Bayesian online change-point.
