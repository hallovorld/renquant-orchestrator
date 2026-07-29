# GOAL-6 (proposed) — model capability: fix the ruler, then buy breadth

Date: 2026-07-28
Status: DESIGN FOR REVIEW (no experiment run yet; each stage gets its own frozen prereg)
Owner: claude · Reviewer: codex · Operator decision requested on the staging + budget

## 1. The thesis

Our models are not weak because of architecture. They are **unresolvable**,
for three reasons that are all measurable and two of which cost nothing to
fix:

**(a) Too few independent observations.** A 60-trading-day forward label over
a 142-name panel gives ~43 non-overlapping windows per 10.3 years. Tonight's
fresh PatchTST measured IC **+0.0430** with a naive t of **+5.39** — and a
block-adjusted t of **+0.70** once the label overlap is honoured. A true IC
of 0.02–0.04 is simply not separable from zero at this sample size, so every
verdict comes back "underpowered" and reads like "the model is bad".
`[VERIFIED — hf_patchtst_all_seed44_val_preds.parquet, 33,370 rows, 235 dates]`

**(b) We measure with the wrong ruler.** On the same panel, the top-decile
spread carries **t = 2.92** while full-cross-section IC carries **t = 1.15**
(2026-07-24 capacity memo). The skill is tail-driven and episodic; training
objectives and gates built on full-cross-section IC dilute the one thing we
have. The certified blend leg is exactly the recipe that stopped asking
"rank everyone" and started asking "who reaches the top decile" — effect
**+0.0687**, CI lower bound **+0.0156**, reproduced on disjoint seeds.

**(c) The universe is 142 names — and we already own 830.** Measured on
disk today: training panel **142 tickers** (2016-01-04 → 2026-04-28, 353,548
rows); fund panel **292**; SEC fundamentals coverage **830**. We are training
on 17% of the cross-section we have already paid for and rebuilt as-filed
(base-data#52: 830 tickers, ~630k as-filed facts).
`[VERIFIED — direct parquet reads, 2026-07-28]`

## 2. What each data lever is actually worth

| lever | independent observations | portfolio effect | cost | verdict |
|---|---|---|---|---|
| **hourly bars** | **unchanged** — 6.5× more rows describing the SAME 60-day outcomes | none at this horizon | large (storage, build, compute) | **NO.** Intraday open→close alpha already measured net-NEGATIVE: σ_oc ≈ 152bp, net edge −6.4bp at IC 0.03. Only relevant if the predicted horizon itself changes — a different system (105 is engineering, not alpha). |
| **more years** (10.3 → 20) | 43 → ~86 windows → t × **1.4** | none directly | high: pre-2016 PIT fundamentals are sparse; 2008–2015 is a different regime | **LATER.** Real but sub-linear, and it buys regime risk with the power. |
| **breadth 142 → 830** | per-date IC sampling noise 1/√N: **0.084 → 0.035**; decomposing the observed per-date IC σ of 0.1224 leaves true time-variation ≈ 0.089, so σ falls to ≈ 0.096 → t × **~1.3** | **the big one**: top decile goes 14 → 83 names, idiosyncratic noise in the traded book falls ≈ **2.4×** at unchanged IC | **≈ zero acquisition** — the data is on disk | **YES, FIRST.** Also removes the survivorship bias that inflates every backtest we quote. |
| **right statistic** (tail spread as the primary) | unchanged | uses the skill we already measured (t 2.92 vs 1.15) | **zero** | **YES, FIRST.** |
| **shorter label for MEASUREMENT** (fwd_20d already in the panel) | 43 → ~129 windows → t × **1.7** | smaller per-trade edge, higher turnover — an economics question, separate from detection | zero | **YES for power diagnostics**, not automatically for trading. |

Honest ceiling: more data makes a **real** signal detectable and tradeable;
it cannot manufacture one. The point of GOAL-6 is to move the PatchTST-shaped
question from "we cannot tell" to "we know".

## 3. Staged experiment ladder (each stage gated, each with a frozen prereg)

**Stage 0 — re-baseline the ruler (zero new data, zero training).**
Re-measure the ALREADY-TRAINED prod XGB ranker and the certified clf on the
same panel under three statistics (full-cross-section IC, top-decile spread,
top-decile hit rate) × two horizons (fwd_20d, fwd_60d), with the standard
two placebo arms and block-aware inference. Deliverable: the numeric answer
to "how much power are we discarding with the current ruler and horizon".
Gate: if the tail statistic does not beat IC on power, Stages 2+ change
shape — we would be optimising the wrong thing again.

**Stage 1 — breadth panel (data we already own).**
Build the training panel at the 830-name fundamentals universe, PIT-correct
(as-filed EDGAR vintages), with delisted names retained where history
exists. Two hard requirements:
- **freshness contract stamped into the artifact**: every panel carries its
  label horizon, its embargo, and the resulting **achievable frontier**
  (cutoff + horizon in trading days, converted to calendar), so downstream
  gates measure *lag beyond the achievable frontier* instead of raw calendar
  age. This is the direct institutionalisation of today's RenQuant#541 (a
  28d SLA that no fwd60 artifact can satisfy silently refused every weekly
  promotion for months) and orch#588.
- **reproduction gate**: on the 142-name overlap, the new panel must
  reproduce the existing panel's statistics within tolerance, else STOP.
  A breadth expansion that also silently changes the recipe is uninterpretable.

**Stage 2 — breadth retrain of the CERTIFIED recipe.**
Retrain the top-decile classifier (the recipe that already passed screen →
frozen prereg → disjoint-seed confirmation) on 830 names, and compare against
its 142-name self through the same frozen chain. Preregistered prediction:
IC roughly unchanged, decile-spread t up by ~2× from the portfolio-noise
term. Failing that prediction is informative and must be reported as such.

**Stage 3 — capability, only after 0–2.**
Only once measurement and breadth are fixed do architecture/capacity changes
become interpretable: seed ensembling (cheap variance reduction), model
capacity (the current PatchTST is 68k parameters on 353k rows — plausibly
underfit), and horizon economics. PatchTST's own fate is decided separately
by the running 43-fold prereg (model#85), independent of GOAL-6.

## 4. Acceptance criteria (proposed)

- **AC1** Stage-0 measurement report merged, with the free-power multiplier
  quantified per statistic × horizon, placebo-matched.
- **AC2** An 830-name PIT panel exists as a reviewed artifact, carrying a
  machine-readable freshness contract (horizon, embargo, achievable
  frontier), and passing the 142-name reproduction gate.
- **AC3** The certified recipe retrained on breadth clears its frozen
  comparison prereg — or the failure is reported with equal prominence.
- **AC4** The tail statistic is wired as a **co-primary** in the gate
  (renquant-pipeline), not merely used in research notebooks.
- **AC5** Nothing reaches production except through the standard chain
  (artifact → reviewed config → pin advance → sync). No production path is
  edited to make an experiment work.

## 5. Repo boundaries (multirepo, non-negotiable)

| repo | owns in GOAL-6 |
|---|---|
| **renquant-base-data** | universe expansion + PIT as-filed panel construction + the freshness-contract stamp. The panel builder lives here; nowhere else writes it. |
| **renquant-model** | training recipes, the evaluation-statistics module (tail spread + block-aware inference), prereg + results docs. |
| **renquant-pipeline** | gate/admission changes that consume the new statistic; the freshness rule that reads the stamped frontier. Canonical kernel — the umbrella fork mirrors, never leads. |
| **renquant-orchestrator** | this goal doc, the prereg registry, scheduling of the new builds, cross-repo sequencing. **No panel internals, no model internals.** |
| **RenQuant (umbrella)** | pins only, plus fork mirrors until the fork is retired. |

Anti-pattern this table exists to prevent: implementing panel or model
internals in the orchestrator because it is the repo the session starts in.

## 6. What is NOT in scope

Hourly/intraday data (§2 evidence), new vendors or spend, any change to the
live buy path, and PatchTST's verdict (owned by model#85). GOAL-6 buys
resolution, not a new trading rule.
