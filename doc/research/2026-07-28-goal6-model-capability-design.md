# GOAL-6 — Model Capability Program: Design Document

| field | value |
|---|---|
| Document | GOAL-6 design, revision 1 |
| Date | 2026-07-28 |
| Status | **FOR REVIEW** — no experiment executed; each stage carries its own frozen prereg |
| Author | claude |
| Adversarial reviewer | codex |
| Decision owner | operator |
| Decisions requested | §10 (D1–D4) |
| Supersedes | — |

---

## 1. Executive summary

**Finding.** The measurement apparatus cannot see the effect sizes we are
looking for. With today's panel (142 names, 60-trading-day labels, 10.3
years) the minimum detectable per-date IC at 80% power is **0.052**.
Published and internally plausible equity cross-sectional ICs are
**0.02–0.04**. A model with genuine, tradeable edge is therefore
*statistically invisible* to our current setup, and every verdict returns
"underpowered" — which then gets read, wrongly, as "the model is bad". That
misreading happened in this very session and had to be retracted within the
hour.

**Root causes, in order of remediation cost:**

1. **Wrong primary statistic (cost: zero).** The skill in this book is
   tail-driven: top-decile spread carries t = 2.92 where full-cross-section
   IC carries t = 1.15 on the same panel. We train and gate on the weaker
   statistic.
2. **Unused breadth (cost: ~zero).** The training panel is **142** tickers;
   SEC fundamentals coverage already on disk is **830**. We model 17% of the
   cross-section we have already paid for and rebuilt as-filed.
3. **Horizon-driven sample starvation (cost: an economics decision).** A
   60-trading-day label over 10.3 years yields ~43 non-overlapping windows.
   The panel already carries `fwd_20d_excess`, which triples that.

**Recommendation.** A four-stage program that fixes measurement first and
spends on capacity last. Stages 0–1 require **no new data purchase and no
new compute budget**. The expected outcome is not "a better model" directly;
it is **the ability to tell whether a model is better** — currently absent,
and a precondition for every other model investment.

**Cost.** Stage 0: ~2 compute-hours, $0. Stage 1: ~8–20 compute-hours, $0
(local/MPS; data already owned). Stage 2: ≤$25 cloud, matching the existing
authorised envelope. Stage 3: not costed until Stages 0–2 land.

---

## 2. Problem statement, quantified

### 2.1 The power model

Per-date rank IC estimated on a cross-section of `N` names has sampling
variance ≈ `1/(N−3)`. Across `T_eff` **independent** periods, the standard
error of the mean IC is

```
SE(mean IC) = sqrt( σ_true² + 1/(N−3) ) / sqrt(T_eff)
MDE(80% power, α = 0.05 two-sided) ≈ 2.80 × SE
T_eff = trading_days / label_horizon      (non-overlapping windows)
```

Measured decomposition on the fresh PatchTST validation set (33,370 rows,
235 dates, N = 142) `[VERIFIED — direct parquet read]`:

```
observed per-date IC variance  0.01498
  = true IC time-variation     0.00779   (σ_true = 0.0882)
  + sampling noise             0.00719   (= 1/139)
```

Roughly **half** of the dispersion we observe is pure estimation noise from
a thin cross-section. That is the term breadth removes.

### 2.2 What each configuration can actually detect

`[DERIVED — from the measured decomposition above; projection, not measurement]`

| scenario | N | horizon | T_eff | SE(mean IC) | **MDE @80%** | detects IC 0.03? |
|---|---|---|---|---|---|---|
| **today** | 142 | 60d | 43 | 0.0186 | **0.0521** | **no** |
| breadth only | 830 | 60d | 43 | 0.0144 | 0.0404 | no |
| horizon only | 142 | 20d | 130 | 0.0107 | 0.0301 | marginal |
| **breadth + horizon** | 830 | 20d | 130 | 0.0083 | **0.0233** | **yes** |
| + history to 20y | 830 | 20d | 252 | 0.0060 | 0.0167 | yes, with margin |

The production admission bar `min_oos_mean_ic = 0.01` sits **five times
below** what today's apparatus can resolve. We are gating on a number we
cannot measure.

### 2.3 The second lever: the statistic itself

Power is not only a function of sample size. On the same 2026-07-24 panel
measurement, the tail statistic carried **t = 2.92** against **t = 1.15**
for full-cross-section IC — a ratio of ~2.5×. Since t scales as √T,
switching the primary statistic to the tail spread is worth roughly the same
as **~6× more data**, at zero cost. This is the single highest-leverage
change in the program and it is free.

### 2.4 Business impact

Without this program: model investment continues to produce verdicts that
cannot distinguish "no edge" from "cannot see edge", so neither promotion
nor kill decisions are defensible; the 43-fold PatchTST corpus ($18.30) and
every future corpus inherit the same ceiling. With it: the same corpora
become decidable, and the certified blend leg's forward test gains a
correctly-powered readout instead of a 120-session wait for a statistic that
may still be too weak to conclude on.

---

## 3. Options analysis

| # | option | Δ MDE | portfolio effect | cost | risk | verdict |
|---|---|---|---|---|---|---|
| A | **Tail statistic as primary** | ≈ ×2.5 effective t | aligns objective with where skill is | **zero** | mis-specification if skill is not tail-driven — falsifiable in Stage 0 | **ADOPT (first)** |
| B | **Breadth 142 → 830** | 0.052 → 0.040 (with A+C: 0.023) | top decile 14 → 83 names; idiosyncratic noise ÷ ~2.4 | ≈ zero acquisition; build + compute only | delisting/PIT correctness; small-name data quality | **ADOPT (first)** |
| C | **20d label for measurement** | ×1.7 on T_eff | separate economics (turnover) — measurement use only | zero | conflating measurement horizon with trading horizon | **ADOPT for diagnostics** |
| D | History 10.3y → 20y | ×1.4 further | none directly | high: pre-2016 PIT sparse | regime non-stationarity | **DEFER to Stage 3** |
| E | **Hourly bars** | **none at 60d/20d horizons** | none | large (storage, build, compute) | distraction | **REJECT.** Measured: intraday open→close net edge **−6.4bp** at IC 0.03 against σ_oc ≈ 152bp. 6.5× the rows describing the same forward outcomes adds no independent observations. Only in scope if the *predicted horizon* changes, which is a different system. |
| F | Bigger model / more seeds | none (power is data-side) | possible capability gain | compute | uninterpretable until A–C land | **DEFER to Stage 3** |

---

## 4. Data architecture and contracts

### 4.1 Target panel contract (Stage 1 output)

| property | requirement |
|---|---|
| universe | the 830-name SEC fundamentals coverage, PIT-resolved per date (a name enters when its first as-filed fact is available, not when it exists today) |
| survivorship | delisted names **retained** for the period they traded; the panel must not be a today-alive list. Current 142-name panel is alive-today and is the reason quoted backtest APY is inflated |
| point-in-time | as-filed EDGAR vintages (base-data#52, ~630k facts), never restated values |
| labels | `fwd_20d_excess`, `fwd_60d_excess` both materialised; label NaN where the forward window has not closed — never dropped at source (this is the defect chain behind RenQuant#541) |
| **freshness contract** | machine-readable block stamped into the artifact: `label_horizon_trading_days`, `embargo_trading_days`, `achievable_frontier_date` (= max labelled date + horizon, trading→calendar via BDay), `build_timestamp`. Gates must measure **lag beyond the achievable frontier**, never raw calendar age |
| identity | content digest + recipe id + provenance schema version, matching the round-8 contract already used by the clf artifacts |

### 4.2 Why the freshness contract is a first-class requirement

Today's root-cause finding: the weekly PatchTST retrain has been silently
refused for months because a 28-calendar-day SLA was applied to a source
whose frontier is structurally ~91 days behind by construction. The job
exited `rc=0` every Saturday and kept the old pin; the served artifact
reached **622 days** stale. Any new panel that does not publish its own
achievable frontier reproduces that failure mode. `[VERIFIED — RenQuant#541,
weekly log 2026-07-25]`

### 4.3 Interfaces between repos

| repo | owns | produces / consumes |
|---|---|---|
| **renquant-base-data** | the panel builder, universe resolution, PIT vintages, freshness-contract stamping | produces the panel artifact + its contract; consumes EDGAR/vendor raw |
| **renquant-model** | training recipes; the evaluation-statistics module (tail spread, block-aware inference); preregs and results | consumes the panel artifact; produces model artifacts + calibrators + evidence docs |
| **renquant-pipeline** | gates and admission that consume the new statistic; the frontier-aware freshness rule (canonical kernel) | consumes artifact contracts; the umbrella fork mirrors, never leads |
| **renquant-orchestrator** | sequencing, the prereg registry, scheduling of new builds, this document | holds **no** panel internals and **no** model internals |
| **RenQuant (umbrella)** | pins; fork mirrors until the fork is retired | — |

Anti-pattern this table exists to prevent: implementing panel or model
internals in the orchestrator because it is where sessions start. Two
architecture violations have already been caused that way.

---

## 5. Staged plan

Each stage: entry criteria → work → exit criteria. **No stage begins before
its own frozen prereg is merged.** A stage that fails its exit criteria stops
the program at that stage; it does not "mostly pass".

### Stage 0 — Re-baseline the ruler
- **Entry:** none (uses artifacts and panels already on disk).
- **Work:** re-measure the already-trained prod XGB ranker and the certified
  clf under {full-cross-section IC, top-decile spread, top-decile hit rate}
  × {20d, 60d}, with the two standard placebo arms and block-aware inference.
- **Exit (all required):** the free-power multiplier is quantified per
  statistic × horizon with matched placebos; the tail statistic's advantage
  is confirmed or refuted at fold level; a recommendation for the Stage-2
  primary statistic is stated numerically.
- **Kill condition:** if the tail statistic does *not* outperform IC in
  power, options A and the Stage-2 design change shape — we would otherwise
  optimise the wrong objective at scale.
- **Owner repo:** renquant-model. **Cost:** ~2 compute-hours, $0.

### Stage 1 — Breadth panel
- **Entry:** Stage 0 exited; panel contract (§4.1) reviewed.
- **Work:** build the 830-name PIT panel in renquant-base-data with the
  freshness contract stamped.
- **Exit (all required):** (i) **reproduction gate** — on the 142-name
  overlap the new panel reproduces the existing panel's per-date statistics
  within a preregistered tolerance; (ii) survivorship check — delisted names
  present with correct final dates; (iii) look-ahead check — no row's
  features postdate its as-filed availability; (iv) the freshness contract
  is machine-readable and a gate can consume it.
- **Kill condition:** reproduction gate fails → the expansion also changed
  the recipe and results would be uninterpretable. Stop and diagnose.
- **Owner repo:** renquant-base-data. **Cost:** ~8–20 compute-hours, $0.

### Stage 2 — Breadth retrain of the certified recipe
- **Entry:** Stages 0–1 exited; comparison prereg frozen.
- **Work:** retrain the top-decile classifier — the recipe that already
  passed screen → frozen prereg → disjoint-seed confirmation (+0.0687, CI
  lower bound +0.0156) — on 830 names, and compare against its 142-name self
  through the identical chain.
- **Preregistered prediction:** IC broadly unchanged; the decile-spread
  fold-level t rises materially from the portfolio-noise term. Failure to
  reproduce this prediction is itself a finding and is reported with equal
  prominence.
- **Exit:** the frozen comparison rule returns GO / KILL / UNDERPOWERED, and
  the verdict is registered.
- **Owner repo:** renquant-model. **Cost:** ≤$25 cloud (existing envelope).

### Stage 3 — Capacity (not before)
Seed ensembling, model capacity (the current PatchTST is 68k parameters
against 353k rows — plausibly underfit), history extension to 20 years, and
horizon economics. Not costed until Stages 0–2 land, because none of it is
interpretable at MDE 0.052.

---

## 6. Validation strategy

| layer | check | fails the stage if |
|---|---|---|
| panel correctness | reproduction on the 142-name overlap | statistics diverge beyond preregistered tolerance |
| PIT integrity | every feature value's as-filed availability ≤ its row date | any violation |
| survivorship | delisted names present; universe size varies by date | universe is constant = today's list |
| label integrity | unresolved forward windows are NaN, not dropped | max labelled date == max panel date |
| freshness | achievable frontier computed and stamped; a gate reads it | absent or unreadable |
| statistical | placebo arms per statistic; block-aware inference everywhere | any absolute IC reported without its matched placebo |

---

## 7. Risk register

| # | risk | likelihood | impact | mitigation | detection |
|---|---|---|---|---|---|
| R1 | Breadth adds names with poor/void fundamentals, injecting noise that offsets the power gain | medium | medium | per-name coverage floor preregistered; report results with and without the low-coverage cohort as a preregistered split | Stage-1 coverage report |
| R2 | Delisting/PIT history incomplete → survivorship persists in a new coat | medium | **high** (invalidates every downstream claim) | explicit survivorship exit criterion; universe-size-by-date curve must show entries and exits | Stage-1 exit check |
| R3 | Look-ahead through restated fundamentals | low (as-filed rebuild landed) | **high** | as-filed vintages only; row-level availability assertion | Stage-1 PIT check |
| R4 | The tail statistic's edge is an artifact of the 2026-07-24 window | medium | high (would misdirect the objective) | Stage 0 re-measures it fold-level with placebos before anything is built on it | Stage-0 exit |
| R5 | 20d horizon has edge but does not survive turnover costs | medium | medium | horizon used for *measurement* first; trading-horizon change is a separate economics decision with its own prereg | Stage-0 report |
| R6 | Scope creep into architecture before measurement lands | **high** (it is the tempting move) | medium | Stage 3 is gated on Stages 0–2 exits; explicit in this document | review |
| R7 | New panel enters production informally | low | **high** (live path) | AC5: artifact → reviewed config → pin advance → sync, no exceptions | run-surface drift scan |
| R8 | Compute/wall-clock overruns on local hardware | medium | low | MPS-first (measured 11.6× faster than CPU tonight); cloud only inside the authorised envelope; `caffeinate` on any run >15 min (5 hours were lost to machine sleep today) | per-stage timing report |

---

## 8. Rollout and rollback

The program produces **artifacts and evidence**, not a live behaviour change.
Nothing in Stages 0–2 touches the live buy path.

If Stage 2 returns GO, promotion follows the standard chain and no shortcut:
artifact into the store → reviewed config change in the strategy repo → pin
advance in the umbrella → operator-authorised sync. Rollback is the pin
revert, which is already exercised and documented.

The new panel does **not** replace the existing one on merge. It lands
side-by-side under its own identity; the production recipe continues to read
the current panel until a separate, preregistered switch decision is made.

---

## 9. Schedule and critical path

| stage | wall clock | blocking dependency |
|---|---|---|
| 0 | ~1 session | none — can start immediately |
| 1 | 1–2 sessions | Stage 0 exit (defines which statistics the panel must support) |
| 2 | 1 session compute + review latency | Stage 1 exit |
| 3 | not scheduled | Stages 0–2 |

Critical path is Stage 1's PIT/survivorship correctness, not compute.

---

## 10. Decisions requested

- **D1** — Approve the staging and the principle "measurement before
  capacity"? (Alternative: go straight to a bigger model; §2.2 says the
  result would be unreadable.)
- **D2** — Approve breadth target **830** (full fundamentals coverage) versus
  a smaller intermediate (e.g. 400 liquid names) to reduce R1/R2 exposure on
  the first build?
- **D3** — Is the 20d horizon approved for **measurement** only, with any
  trading-horizon change deferred to its own economics prereg?
- **D4** — Confirm Stage 2 may draw on the existing ≤$25 cloud envelope, or
  set a separate budget.

---

## Appendix A — power derivation

For Spearman rank IC on `N` names, the Fisher-transformed estimator has
variance ≈ `1/(N−3)`; for the magnitudes here the untransformed
approximation is adequate. Treating per-date IC as `IC_t = μ + ε_t` with
`Var(ε_t) = σ_true² + 1/(N−3)`, the mean over `T_eff` independent periods has
`SE = sqrt(σ_true² + 1/(N−3)) / sqrt(T_eff)`. Two-sided α = 0.05 at 80%
power requires `|μ| ≥ (1.96 + 0.84) × SE = 2.80 × SE`.

`T_eff` is the count of **non-overlapping** label windows: overlapping
60-day labels on consecutive dates are not independent observations, which
is precisely the error that produced tonight's naive t = +5.39 against a
block-adjusted t = +0.70 on the same numbers.

σ_true = 0.0882 is measured, not assumed, from the decomposition in §2.1;
every MDE in §2.2 follows from it by the formula above and is labelled a
projection.

## Appendix B — provenance of every number used

| number | source | tag |
|---|---|---|
| IC +0.0430, naive t +5.39, block t +0.70, placebo −0.0008 | `hf_patchtst_all_seed44_val_preds.parquet`, 33,370 rows, 235 dates, computed 2026-07-28 | [VERIFIED] |
| per-date IC σ = 0.1224 | same | [VERIFIED] |
| panel 142 tickers / 353,548 rows / 2016-01-04 → 2026-04-28 | `data/transformer_v4_wl200_clean.parquet` | [VERIFIED] |
| fund panel 292 tickers | `data/alpha158_291_fundamental_dataset.parquet` | [VERIFIED] |
| fundamentals coverage 830 tickers | `data/sec_fundamentals_daily.parquet` | [VERIFIED] |
| tail spread t = 2.92 vs IC t = 1.15 | 2026-07-24 capacity/identity memo | [VERIFIED — prior work] |
| clf certified effect +0.0687, CI lower +0.0156 | model#74/75/76 confirmatory chain | [VERIFIED — prior work] |
| intraday net edge −6.4bp, σ_oc ≈ 152bp | Phase −1 intraday study | [VERIFIED — prior work] |
| `min_oos_mean_ic` = 0.01 | `renquant_pipeline.model_admission._check_oos_ic` | [VERIFIED — code] |
| all MDE figures in §2.2 | derived from the above via Appendix A | [DERIVED] |
