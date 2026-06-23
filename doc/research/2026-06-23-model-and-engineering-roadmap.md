# Model capability + engineering quality — restructured roadmap (2026-06-23)

A research-backed re-prioritization of the two main-line goals: (1) upgrade model
capability, (2) raise engineering quality. Grounded in the existing plans (roadmap.md,
patchtst-improvement-plan, bull-calm-recovery, #108 eng rails) but deliberately not
limited to them — new directions are flagged **[NEW]** with the evidence.

---

## 0. The central diagnosis (why a re-prioritization is needed)

Two facts from the historical record + the 2026-06-23 live deploy:

1. **One specific stack has been exhausted — not "incremental tweaks" in general.**
   The narrow, repo-supported claim: **the current alpha158+light-fundamentals feature
   set on the current `fwd_60d_excess` label family has not produced a robust
   placebo-clean BULL_CALM edge**, despite extensive work on that stack (feature pruning,
   σ-wire, macro overlay, asset embeddings, multi-horizon, PatchTST DOE 70/81 trials,
   4 architectures). The docs note "60d slow persistence IS the placebo" and "alpha158+fund
   is the constraint; would require an alternate data source." This is evidence that *this
   stack* is tapped, which motivates exploring **new alpha sources, better labels, and
   rigorous neutralization** — as hypotheses to validate in-repo, NOT a proven verdict that
   all incremental work is dead.

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

### Short-term (days–2wk) — cheapest decisive moves on EXISTING data

- **[DONE — REJECTED] Idiosyncratic-residual neutralization (was the cheapest first move).**
  The BULL_CALM symptom (placebo IC ≈ real IC) is the textbook signature of *factor/drift
  contamination*, so the cheap first test was: residualize the *label* against industry +
  beta (+ trailing-momentum drift) and re-measure per regime on the panel we already have.
  **Now run end-to-end and rejected by the per-regime WF gate.** A cheap *aggregate* audit
  looked positive (resid OOS IC +0.0342 ≥ raw +0.0321), but the decisive *per-regime +
  placebo* test reversed it: the momentum/drift-neutralized label **destroys** the BULL_CALM
  signal (placebo-clean BULL_CALM IC raw **+0.0240** vs neutralized **−0.0291**) — in
  BULL_CALM the edge *is* momentum continuation, so neutralizing it removes exactly what
  works. The gate caught a cheap false positive. Full record (spec/data/folds/raw outputs):
  `doc/research/2026-06-23-residual-neutralization-evidence.md`. **Consequence:** this tested
  residual-neutralization path is rejected (strong evidence against momentum/drift-neutralized
  labels in BULL_CALM) — not a verdict that *all* in-repo relabeling is closed; the next cheap
  in-repo bet is drift-free *labels* (untested), with acquired data still the conditional path.

#### Conditional bets (NOT cheap — gated on a data-acquisition prerequisite)

- **[NEW, CONDITIONAL] Analyst-revision / fundamental-momentum factor.** *This is an
  external-data acquisition project, not a local feature experiment* — the repo has no
  committed estimate-revision data source, ingestion contract, or licensing path. **Prereq:
  decide + commit a source (e.g. the financial-analysis MCP / a vendor feed) with a
  repeatable build path.** The *hypothesis* is strong (estimate-revision momentum shows
  ~+13.6% FF6-adjusted alpha in the literature; AQR's "fundamental momentum"; revisions are
  more persistent than returns; it diverged from the model's sizing live on 06-23), but it
  is a hypothesis to validate after acquisition, not a cheap first move. *Success (post-build):
  BULL_CALM placebo-clean IC ≥ +0.02 standalone or as an additive lift.*

### Mid-term (2–6wk) — labels + signal diversity

- **[TRIAL RUN — INCONCLUSIVE; harness underpowered] Label engineering: trend-scanning.** Every
  metric disagreed: placebo-clean IC → trend-scan better (but the IC null is leaky, +0.036±0.046, and
  the embargo-gap explanation was tested and refuted); naive portfolio-P&L → raw better; **hardened
  P&L (90d embargo + non-overlapping 60d rebal + 10bps cost) → a WASH** (BULL_CALM raw +0.162/Sh1.80
  vs trend-scan +0.114/Sh2.21, n=10; ALL tied). With n≈10 non-overlapping windows + the leakage floor,
  trend-scan and raw are **statistically indistinguishable** — no demonstrable edge in either direction.
  Full record: `doc/research/2026-06-23-trendscan-label-evidence.md`.
- **[TRACK CONCLUSION] No demonstrable cheap in-repo model edge — and this harness can't decide.** The
  three cheap levers (neutralization, fundamental-momentum, trend-scanning) yielded **no measurable
  improvement** over the incumbent raw-label model (first two clearly negative; trend-scanning a wash).
  Two takeaways: (1) the cheap "relabel/reweight the same panel" axis has **no demonstrable payoff** —
  stop spending on it; (2) this in-repo harness is **underpowered** (a +0.036 shuffled-IC leakage floor,
  n≈10 non-overlapping windows, a simplified recipe ≠ the production pipeline), so it is the wrong
  instrument to adjudicate marginal model changes — deciding one needs the real pipeline + a powered,
  costed backtest. Either way the cheaper, **unambiguous** live-P&L lever is **construction** (next bullet
  + §1 long-term): the 2026-06-23 book was 78% cash and sized backwards vs upside — a *construction*
  failure, not a signal failure, and the larger live loss. Meta-labeling, if used, attaches as a
  conviction/sizing filter on the **raw** model, not as a new base label.
- **[CONDITIONAL — behind the scorer-lineup reopen trigger] Diverse-signal ensemble.**
  `doc/decisions/2026-06-12-scorer-lineup-decision.md` shelved the ensemble and bars further
  ensemble work unless a reopen trigger fires (WF passes ensemble while failing the primary
  retrain; shadow dominates primary ≥1 quarter; sustained BULL_CALM losses). So this is NOT
  a normal mid-term track — it is a *future conditional branch*: IF a reopen trigger fires,
  the right form is orthogonality of *signal* (technical XGB + the analyst-revision factor +
  a residual-reversal signal, consensus-gated via the merged conviction gate / trade-review
  skill), not the same-features fusion that was shelved.
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

The current alpha158+fund × 60d-label stack has not yielded a robust placebo-clean
BULL_CALM edge. The cheapest in-repo hypothesis — **rigorous neutralization (predict the
idiosyncratic residual)** — has now been **tested and rejected** by the per-regime WF gate
(`doc/research/2026-06-23-residual-neutralization-evidence.md`): in BULL_CALM the edge *is*
momentum continuation, so neutralizing the label destroys the regime signal. That leaves
**drift-free labels** (in-repo, untested) and — *conditional on acquiring the data* —
**orthogonal signals (analyst-revision fundamental-momentum)** as the remaining model bets;
relabeling the same panel is spent. In parallel, **make the build emit a self-consistent
bundle and the deploy atomic+reversible**, so model iteration stops paying the fragility tax
we paid by hand all of 2026-06-23. Model-track update: the **drift-free-label trial is RUN and
INCONCLUSIVE** — trend-scanning beat raw on placebo-clean IC but the verdict flipped with every
metric and dissolved into noise under a hardened (embargo + non-overlap + cost) P&L test (n≈10;
see `doc/research/2026-06-23-trendscan-label-evidence.md`). Net: no demonstrable cheap in-repo edge
from any of the 3 levers, AND the in-repo harness is underpowered to decide marginal model changes.
The cheaper, **unambiguous** live-P&L move is therefore **construction** (QP sizing by conviction),
and on the engineering track the **self-consistent bundle build**
(engineering — now in PR as `model_bundle`).

## Sources (new directions)
- Analyst-revision / fundamental-momentum alpha: [AlphaArchitect](https://alphaarchitect.com/economic-momentum/),
  [analyst-sentiment normalization (+13.6% FF6 alpha)](https://www.mdpi.com/2227-7072/14/1/4),
  [Guerard, earnings forecasts & revisions (FactSet)](https://go.factset.com/hubfs/Symposium%20Images/Guerard_EARNINGS%20FORECASTS%20AND%20REVISIONS,%20PRICE%20MOMENTUM,%20AND%20FUNDAMENTAL%20DATA.pdf)
- Labels: [meta-labeling efficacy (Hudson & Thames)](https://hudsonthames.org/does-meta-labeling-add-to-signal-efficacy-triple-barrier-method/),
  [triple-barrier / trend-scanning comparison](https://www.mql5.com/en/articles/19253)
- Neutralization → residual alpha: [cross-sectional factor neutralization + bias correction](https://arxiv.org/html/2507.07107)
