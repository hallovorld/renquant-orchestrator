# Model capability + engineering quality — restructured roadmap (2026-06-23)

A research-backed re-prioritization of the two main-line goals: (1) upgrade model
capability, (2) raise engineering quality. Grounded in the existing plans (roadmap.md,
patchtst-improvement-plan, bull-calm-recovery, #108 eng rails) but deliberately not
limited to them — new directions are flagged **[NEW]** with the evidence.

---

## 0. The central diagnosis (why a re-prioritization is needed)

Two facts from the historical record + the 2026-06-23 live deploy:

1. **The technical-feature × 60d-label combo is exhausted.** alpha158 + light
   fundamentals on `fwd_60d_excess` has been pushed hard — feature pruning, σ-wire,
   macro overlay, asset embeddings, multi-horizon, PatchTST DOE (70/81 trials hit a
   structural ceiling), 4 architectures — and there is **no robust placebo-clean edge
   in BULL_CALM**, the regime the market sits in ~78% of the time. The docs already
   note "60d slow persistence IS the placebo" and "alpha158+fund is the constraint;
   would require an alternate data source." → **Incremental model/feature tweaks on the
   same data+label are a dead end. The frontier is new ALPHA SOURCES, better LABELS, and
   rigorous NEUTRALIZATION.**

2. **Engineering fragility taxes every model iteration.** The 2026-06-23 XGB deploy hit
   *four* consistency guards in PROD — WF-metadata absent, calibrator/scorer fingerprint
   mismatch, config-fingerprint mismatch, watchlist 142≠145 — each patched by hand
   (re-stamp, re-fit, re-stamp, re-stamp). The weekly promote chain was *silently broken
   for a month* (manifest path bug). The model is not built through a pipeline that emits
   a self-consistent, deploy-ready bundle. → **Until the build→deploy is clean and atomic,
   every model experiment is slow and error-prone. Engineering is the force-multiplier.**

Prioritization principle: **engineering-clean first as the enabler, in parallel with the
cheapest-highest-evidence new-alpha bets.**

---

## 1. MODEL CAPABILITY

### Short-term (days–2wk) — cheap, high-evidence, new orthogonal signal

- **[NEW] Analyst-revision / fundamental-momentum factor.** Estimate-revision momentum is
  one of the best-documented cross-sectional signals: a standardized analyst-sentiment
  framework shows a **+13.6% annualized alpha after the Fama-French 6 factors**, and AQR
  runs it as "fundamental momentum" alongside price momentum; revisions are *more
  persistent than returns*. We *empirically* saw it bite on 2026-06-23 — analyst
  target-implied upside diverged sharply from the model's sizing. Insider-trade and raw
  sentiment were tried and rejected, but **revision momentum specifically has not been**.
  Build it as a feature (estimate Δ, rating-change, target-price drift, margin trend) and
  measure per-regime placebo-clean IC. *Success: BULL_CALM placebo-clean IC ≥ +0.02
  standalone or as an additive lift.*
- **[NEW] Idiosyncratic-residual audit.** The BULL_CALM symptom (placebo IC > real IC) is
  the textbook signature of *factor/drift contamination*, not stock-selection alpha. Do a
  per-date OLS residualization of the label against industry + log-mktcap (+ beta) and
  re-measure: is the *residual* predictable in BULL_CALM? This is a 1-day measurement that
  tells us whether the regime weakness is "no idiosyncratic alpha" (then we need new data)
  or "alpha buried under drift/factor" (then better neutralization recovers it). Existing
  config has `neutralize_features` but the label is not residualized.

### Mid-term (2–6wk) — labels + signal diversity

- **[NEW] Label engineering: trend-scanning + meta-labeling.** The 60d label's drift IS
  the placebo. Trend-scanning labels (look-forward best-fit trend t-stat) gave the
  strongest uplift in the literature comparison (**Sharpe +37%, Sortino ~2×**) vs modest
  triple-barrier. Pair with **meta-labeling as a conviction filter** on a *better* base
  signal (the prior meta-label "AUC 0.55" was on a weak base). This directly attacks the
  drift-entangled-label root cause the docs flag but only proposed 20d (marginal) for.
- **[NEW] Diverse-signal ensemble (not diverse-architecture).** The shelved ensemble was
  two models on the *same* features. The win is orthogonality of *signal*: combine
  (a) technical XGB, (b) the analyst-revision factor, (c) the residual-reversal signal —
  consensus-gated (ties into the merged conviction gate + the trade-review skill). Diverse
  signals beat diverse models.
- **BULL_CALM specialist** (existing Track C, kept) — but trained to predict the
  *neutralized residual* with the new features, not raw 60d excess.

### Long-term (6wk+) — architecture + alt-data + construction

- Cross-stock attention / iTransformer + soft regime conditioning (FiLM) — already planned
  (Tier 2, #126 3/3 positive, deployable); re-scope onto the new label/features.
- **[NEW] Alt-data** once the residual audit proves the technical set is the ceiling:
  options-implied (skew, IV term structure), short interest, supply-chain/ETF-flow.
- **[NEW] Cost/capacity-aware construction.** At $10.6k with whole-share lumpiness, blend
  model-μ with analyst-implied-μ in the QP and size by conviction, not share price (the
  2026-06-23 book was 78% cash and sized backwards vs upside — a construction failure, not
  a signal failure).

### Do-not-redo (already rejected — see roadmap.md): vol-adjusted label, insider signal,
multi-horizon ensemble, σ-wire 3-condition, per-sector pure-alpha label, macro overlay,
asset embeddings, Boyd rotation, hard-routed regime gate, raw 292-universe.

---

## 2. ENGINEERING QUALITY

### Short-term (days–2wk) — kill the whack-a-mole

- **Canonical self-consistent model bundle.** The #1 fix. One build emits an atomic,
  fingerprinted bundle `{model, paired calibrator, config-fingerprint, watchlist,
  sector-map, WF-metadata}` — so a deploy can never hit the 4-guard sequence we hit by
  hand on 2026-06-23. Extends the existing ModelAcceptanceGate to *guarantee* pairing +
  fingerprint at build time, validated by a self-consistency check.
- **Atomic, validated, reversible deploy.** Replace the pin/lock/.subrepo_runtime/manual
  hand-edit dance with one `promote <bundle>` that: verifies bundle self-consistency →
  runs a readonly daily-full and asserts it produces buys → atomically swaps the pin →
  is one-command reversible. (This session's deploy was 6 manual error-prone steps.)
- **Wire observability (existing #133 decision-ledger, unwired).** Persist every gate
  verdict; add a daily "is it trading / model-health / cash-deployed" alert. The account
  was sell-only for weeks without clear surfacing.
- **Execute the dead-code deletion** (existing mandate): transformer_v4 / qlib_v5 /
  custom patchtst_scorer / doe_sweep, then the broader 0-import sweep. Less surface = fewer
  guards to trip.

### Mid-term (2–6wk) — registry + CI + provenance airtight

- **Model registry (existing #108 S3 — MLflow staging/shadow/prod).** Models get stages,
  provenance, and atomic stage transitions — the durable home for the bundle above.
- **CI integration test that catches model↔config drift PRE-deploy.** The 4 guards fired
  in PROD, not CI. Build a bundle in CI → run full preflight + a readonly daily-full →
  assert buys. Drift caught before it reaches the live tree.
- **Finish #108 S1/S2 wiring** (ArtifactResolver into all manifest/retrain scripts;
  GateRegistry/ledger into the runner) — already merged but unwired.
- **Harden the weekly promote chain** (just fixed the GBDT manifest-uri bug, #141) with a
  monitor that alerts if no promote ran / the chain errored.

### Long-term (6wk+) — structure

- **Multi-subrepo split** (existing backlog): training / engine / artifacts / integration,
  contract-tested, artifacts moving with full provenance. Reduces the cross-repo deploy
  complexity that produced this session's fragility.
- **Single pinned runtime image + state out of git** (existing #108 S3).

---

## 3. The one-paragraph thesis

The model has squeezed what the technical-feature × 60d-label combo holds; the next real
edge is **orthogonal data (analyst-revision fundamental-momentum)**, a **drift-free label
(trend-scanning + meta-labeling)**, and **rigorous neutralization to predict the
idiosyncratic residual** — that, not another architecture, is how BULL_CALM gets an edge.
In parallel, **make the build emit a self-consistent bundle and the deploy atomic+
reversible**, so model iteration stops paying the fragility tax we paid by hand all of
2026-06-23. Cheapest first move on each track: the **analyst-revision factor** (model) and
the **self-consistent bundle build** (engineering).

## Sources (new directions)
- Analyst-revision / fundamental-momentum alpha: [AlphaArchitect](https://alphaarchitect.com/economic-momentum/),
  [analyst-sentiment normalization (+13.6% FF6 alpha)](https://www.mdpi.com/2227-7072/14/1/4),
  [Guerard, earnings forecasts & revisions (FactSet)](https://go.factset.com/hubfs/Symposium%20Images/Guerard_EARNINGS%20FORECASTS%20AND%20REVISIONS,%20PRICE%20MOMENTUM,%20AND%20FUNDAMENTAL%20DATA.pdf)
- Labels: [meta-labeling efficacy (Hudson & Thames)](https://hudsonthames.org/does-meta-labeling-add-to-signal-efficacy-triple-barrier-method/),
  [triple-barrier / trend-scanning comparison](https://www.mql5.com/en/articles/19253)
- Neutralization → residual alpha: [cross-sectional factor neutralization + bias correction](https://arxiv.org/html/2507.07107)
