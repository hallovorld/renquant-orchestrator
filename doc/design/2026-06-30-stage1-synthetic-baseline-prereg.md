# renquant105 Stage-1 — Synthetic Batch-Fill Baseline PRE-REGISTRATION (FREEZE TEMPLATE)

STATUS: **FREEZE TEMPLATE — NOT YET FROZEN.** This file is the *template* for the Stage-1 synthetic-baseline pre-registration. The **PROCEDURE** (§1–§5, §7) is already pinned wording — not a researcher degree of freedom once this RFC merges — but the fitted **numerical outputs** are still placeholders (`<<FROZEN AT CALIBRATION §3>>`). It therefore does **not** yet freeze all values, and must not be cited as if it does. A separate **calibration/freeze PR** must (i) run the §3 procedure exactly as written, (ii) write the fitted numbers into §2/§5/§7, (iii) flip this `STATUS` to `FROZEN (<date>)`, and (iv) commit the detached fingerprint sidecar (§6). **That freeze PR MUST MERGE before the readonly phase begins — not merely before canary** — because readonly already reveals pair composition, opening references, missingness, and modeled synthetic outcomes, so any tuning of coefficients or caps after readonly is a leak. Readonly and canary run-creation **fail closed** on an unfrozen (`STATUS ≠ FROZEN`) or fingerprint-mismatched artifact (§0/§6). While this file is a template (not `FROZEN`), Stage 1 may validate **operations only** (no-leak + idempotency + reconciliation + session-boundary); it **MAY NOT** claim a comparative execution-quality PASS (RFC §9.2c / §9.3).

DATE: 2026-06-30
OWNER: orchestrator control-plane (measurement); pipeline owns the runtime IS ledger schema.
REFERENCED BY: `doc/design/2026-06-30-renquant105-intraday-decisioning-architecture.md` §9.2b / §9.2c / §9.2d / §9.3.
PURPOSE: pin every researcher degree of freedom in the **synthetic batch-fill control arm** of the Stage-1 execution-quality A/B (RFC option (a): one real intraday fill vs a quote-based synthetic batch fill), **and** the no-fill / censoring imputation DOF of the §9.2d intent-to-treat sensitivity analysis. These DOF can move the baseline by **more than the 10-bps acceptance gate** and could otherwise be chosen *after* readonly/canary evidence is seen — so both the procedure (now) and its fitted numbers (at freeze, before readonly) are pinned, before any readonly or canary data exists.

---

## 0. Freeze procedure (immutability) + when it must happen

**The PROCEDURE in §1–§5 and §7 is pinned by this committed template and ceases to be a researcher DOF once the RFC merges.** Only the fitted numerical outputs (`k_spread`, `k_auction`, their §5 bootstrap dispersion, and the §7 caps) remain to be populated. The freeze steps:

1. Run the §3 calibration **exactly as specified** on the trailing 60-session window ending strictly before the readonly phase; write the fitted `k_spread`, `k_auction`, their §5 **calibration-coefficient** bootstrap dispersion (the outer-loop diagnostic — the full joint CB of `Δ` is computed at gate-evaluation over canary, §5.1), the §5.2 **readiness inputs** (`σ̂²_sess`, the derived `S_ready`), the §5.4 **serial-dependence diagnostic outcome + block length** (`1` or `L*`), and the §7 caps (`IS_cap_hi`, `IS_cap_lo`) into §2/§5/§7. No step of the procedure may be altered — only the numbers are filled in.
2. Flip `STATUS` to `FROZEN (<date>)`.
3. Compute the **detached canonical fingerprint** (§6) over the frozen file bytes and commit it to the sidecar `2026-06-30-stage1-synthetic-baseline-prereg.sha256`. The hash is **NOT** written inside this file (this is what removes the self-reference — see §6).
4. **This freeze PR MUST MERGE before the readonly phase starts.** From merge onward the file is immutable; every synthetic batch-fill ledger row stamps `synthetic = true` and the §6 fingerprint. **Any edit after freeze changes the hash and INVALIDATES the run.**
5. **Run-creation guard (fail-closed).** Readonly *and* canary run-creation MUST (a) require `STATUS == FROZEN`, and (b) recompute the §6 fingerprint over this file's bytes and require it to equal BOTH the sidecar value AND the value about to be stamped in the ledger. A missing sidecar, `STATUS ≠ FROZEN`, or any mismatch → **run-creation aborts** (no readonly, no canary). This is why the freeze must precede readonly, not just canary.

---

## 1. Opening reference field + timestamp (one field, named)

- **Primary reference:** the official **primary-listing opening-auction print** (the consolidated opening cross from the symbol's primary exchange) on session T.
- **`event_time`:** the auction publication timestamp on session T.
- **Fallback (named, deterministic):** if a symbol has **no opening auction** on session T, use the **first consolidated NBBO midpoint at or after 09:30:00 ET**, and flag the row `ref_source = nbbo_fallback` (default `ref_source = opening_auction`).
- This is the price the 104 after-close batch would realistically transact against acting next-open on the same frozen T-1 signal.

## 2. Fill-model formula + ALL parameter values

```
synthetic_batch_fill = P_open + side_sign * ( k_spread * half_spread_open + k_auction * auction_slippage_proxy )
```

| Symbol | Definition | Source / value |
|---|---|---|
| `P_open` | the §1 opening reference price | opening-auction print (or NBBO-midpoint fallback) |
| `side_sign` | `+1` for buys (pay up), `-1` for sells | order side |
| `half_spread_open` | `0.5 * (ask_open - bid_open)` in price terms | consolidated NBBO at the §1 `event_time` |
| `k_spread` | fraction of the open half-spread paid (dimensionless), box-constrained `0 ≤ k_spread ≤ 1` (§3.4) | `<<FROZEN AT CALIBRATION §3>>` |
| `auction_slippage_proxy` | per-symbol opening-imbalance slippage, in price terms (§4 transform) | §4 auction-imbalance treatment |
| `k_auction` | auction-slippage coefficient (dimensionless), box-constrained `k_auction ≥ 0` (§3.4) | `<<FROZEN AT CALIBRATION §3>>` |

`k_spread` and `k_auction` are **fit once** by the §3 procedure and then frozen; their fitted values and their §5 **calibration-coefficient** bootstrap dispersion are recorded here at freeze and **never re-fit** after readonly/canary data is observed. (The full joint upper CB of `Δ` also folds in evaluation-sample uncertainty and is computed at gate-evaluation over the canary window — §5.)

## 3. Calibration procedure (frozen) — dataset, estimator, and every fitting DOF

Every fitting degree of freedom is pinned here; only the numbers produced by *running* this procedure are populated at freeze.

**3.1 Dataset + cutoff.** The trailing **60 trading sessions** of 104's *realized next-open batch fills*, each paired with its same-session opening reference (§1). **Cutoff = the last session strictly before the readonly phase begins** (hence strictly before canary). No session at or after readonly start may enter calibration.

**3.2 Response + regressors.** For each calibration fill the response is the realized **signed implementation shortfall in price terms**, `IS_obs = side_sign * (fill_price - P_open)`. The two regressors are `x1 = half_spread_open` (§2) and `x2 = auction_slippage_proxy` (§4, in price terms). The model is fit **through the origin (no intercept)**: `IS_obs = k_spread * x1 + k_auction * x2 + e`, matching the §2 fill formula exactly.

**3.3 Liquidity buckets + pooling.** Symbols are assigned to **3 liquidity buckets** by tercile of trailing **20-session median dollar-ADV** (bucket edges computed on the §3.1 window and frozen). Coefficients `(k_spread, k_auction)` are fit **per bucket**. **Sparse-bucket rule:** a bucket with fewer than **`N_bucket_min = 200`** calibration fills is **pooled into the next-more-liquid bucket** before fitting (if the most-liquid bucket is itself sparse, pool into the next-less-liquid); pooling is applied transitively until every fitted group has ≥ 200 fills. The post-pooling bucket→coefficient assignment is frozen and applies identically at serving time.

**3.4 Estimator + loss + constraints.** Within each (pooled) bucket, `(k_spread, k_auction)` are estimated by **Huber robust regression** (M-estimator, Huber tuning constant **`c = 1.345 * s`**, where `s` is the MAD-scaled residual scale re-estimated by IRLS to convergence, tol `1e-8`, max 100 iterations), **subject to box constraints `0 <= k_spread <= 1` and `k_auction >= 0`** (a spread fraction cannot be negative or exceed one half-spread; auction slippage cannot subsidise the trader). The constrained fit is solved by **projected IRLS** (project onto the box each iteration). **Observations are equal-weighted within a (pooled) bucket** — no inverse-variance weighting; the Huber loss already down-weights residual outliers.

**3.5 Outlier / pre-cleaning policy.** Before fitting, calibration `IS_obs` is **winsorized** at the **bucket-wise 1st/99th percentile** (winsorize, not drop — preserves N). Rows with a missing/zero `half_spread_open`, or without a two-sided open NBBO, are **excluded** from calibration and logged. This pre-cleaning governs only the *calibration fit*; it is distinct from the §7 caps, which govern the *live censored cells*.

**3.6 Frozen outputs.** Running §3.1–§3.5 yields, per (pooled) bucket, the point estimates `k_spread`, `k_auction`, the §5 **calibration-coefficient** bootstrap joint distribution (outer-loop diagnostic), and (from the same window's `IS_obs`) the §7 caps. Running §3 **also** yields the §5.2 pre-canary readiness inputs — the **session-level cluster variance `σ̂²_sess`** and the derived **minimum-independent-session count `S_ready`** — and the §5.4 **serial-dependence diagnostic outcome + resulting block length** (`1` or the stationary-bootstrap `L*`). All of these numbers are written into §2/§5/§7 at freeze and **never re-fit** after readonly/canary data is observed. The §5.1 gate CB itself (which additionally block-resamples the canary window) and the §5.2 **achieved** half-width are **evaluated at gate time, not at freeze** — only the procedure, `σ̂²_sess`, `S_ready`, and the block length are frozen now.

## 4. Per-component treatment (each: how handled / how censored)

**Imbalance→price transform (frozen):** `imbalance_ratio = paired_imbalance_shares / total_auction_paired_shares` (dimensionless, in `[0, 1]`); `auction_slippage_proxy = imbalance_ratio * P_open` (price terms). The `k_auction` coefficient (§3) scales this proxy, and `side_sign` in the §2 formula charges it in the adverse direction (a deliberately conservative choice).

| Component | Treatment | Censoring / flag |
|---|---|---|
| **Spread** | charged as `k_spread * half_spread_open` against the trader | — |
| **Auction imbalance** | `auction_slippage_proxy` from the transform above (published opening imbalance), scaled by `k_auction` per liquidity bucket | if the imbalance feed is unavailable → set to `0`, flag `auction_imbalance = unavailable`. NOTE: 0 **understates** batch cost, making the batch look *better* and **raising** the bar for an intraday PASS — conservative against the intraday arm. |
| **Latency** | synthetic arm fills **at the cross** → modeled latency = **0** (stated modeling choice) | real decision→fill latency is measured only on the **real intraday** arm |
| **Fees** | same commission schedule applied to **both** arms (nets out in the difference; included for completeness) | — |
| **Rejects** | synthetic arm **cannot** be rejected (no real order) | a **real intraday reject** removes that pair's intraday fill → the **pair is censored** (RFC §9.3), imputed as an *intraday* cell under §7 (`IS_cap_hi`) and counted |
| **No-quote** | no valid open NBBO → **no synthetic fill is formed** | pair **censored**, flag `synthetic_no_quote = true`; the censored **batch** cell is **imputed under §7** (`IS_cap_lo`) — see §7 (this reconciles the earlier "never imputed" wording with the §9.2d ITT scheme) |

## 5. Uncertainty procedure (frozen) — JOINT bootstrap + PRE-CANARY power/precision readiness + the overlap PASS rule

Every resampling **and readiness** DOF is pinned here. The reported bound must propagate **BOTH** sources of uncertainty in the estimand: **(i) calibration-coefficient** uncertainty (the fitted synthetic model) **and (ii) evaluation-sample** uncertainty (the canary sessions/pairs whose median intraday IS and synthetic-batch IS define `Δ`). Two things are pinned: **(A)** the joint (nested) session-block bootstrap that propagates both sources (§5.1); **(B)** a **pre-canary power/precision readiness rule** (§5.2) that fixes — *before any canary data exists* — the minimum number of **independent sessions** the canary must accrue for a one-sided 95% bound to have credible tail resolution against the 10-bps margin.

**What changed from r8, and why (answers Codex round-8).** r8 fixed (A) but set evaluability from an **arbitrary floor** (`M_admit_min = 10` admitted pairs / `S_eval_min = 3` distinct sessions per resample) and **discarded + redrew** low-diversity resamples. That is invalid for a one-sided 95% non-inferiority decision about a 10-bps margin: ten fills **clustered by session are not ten independent observations**; a percentile bootstrap over ~3 session clusters has **no credible tail resolution or coverage guarantee**; and **discarding/redrawing low-diversity resamples does not create information** — it conditions away valid sampling variability and can make the interval **anti-conservative**. r9 therefore (i) derives readiness from the **independent-session count + a pre-canary precision/power calculation** on the calibration cluster variance (§5.2), (ii) **removes** the discard-redraw *evaluability* mechanism and confines any discard to **pure numerical degeneracy** (§5.3), and (iii) **justifies or replaces the one-session block** with a pre-canary serial-dependence diagnostic (§5.4). The joint-bootstrap mechanics (§5.1), aggregation and PASS rule (§5.5) are otherwise unchanged.

### 5.1 Joint (nested) session-block bootstrap — propagate both sources (mechanics unchanged from r8)

- **Confidence level:** **one-sided 95%** (matching the RFC §9.3 reject gate); the gate uses the one-sided **upper** 95% confidence bound of `Δ`.

- **Two disjoint resampling universes (the cross-fit boundary):**
  - **CALIBRATION universe** = the 60 pre-readonly calibration sessions of §3.1.
  - **EVALUATION universe** = the canary/admitted sessions (the readonly/canary window over which the `Δ` estimand is defined).
  - These universes are **DISJOINT by construction**: the §3.1 calibration cutoff **is** the readonly/canary boundary, so **no canary session can enter the calibration fit** and no calibration session can enter the evaluation median. **This split IS the cross-fit boundary** — coefficients are always fit on calibration resamples and applied to (never fit on) evaluation resamples.

- **Resampling unit + blocking (both universes):** a **session-level block bootstrap** — the resampling unit is the **session**, resampled with replacement, **block length per §5.4** (all fills/pairs within a drawn block stay together), so intra-session cross-sectional correlation **and the matched-pair structure** are preserved. Individual fills or pairs are **NEVER** resampled independently.

- **Nested / paired draw (per replication `b = 1 … B`):**
  1. **Outer — calibration resample (coefficient uncertainty):** draw session-blocks with replacement from the **CALIBRATION** universe and **re-fit** `(k_spread, k_auction)` per bucket by the full §3.4 constrained-Huber procedure on that resample. Parameter + residual dispersion enter through the re-fit itself (NOT an assumed Gaussian from analytic SEs, NOT a separate parameter draw).
  2. **Inner — evaluation resample (sample uncertainty), drawn INDEPENDENTLY:** **independently** (a separate RNG substream, never index-paired to the outer draw) draw session-blocks with replacement from the **EVALUATION** universe.
  3. **Statistic:** on the evaluation resample, form each admitted pair's synthetic batch fill with **this replication's** re-fit coefficients, apply the §7 adversarial imputation to every censored cell, and compute `Δ*_b = median(IS_intraday_real) − median(IS_batch_synthetic)` over that replication's **§7 imputed-complete admitted set** (the frozen gate scenario).

  Because step 1 (calibration) and step 2 (evaluation) are drawn **independently**, the `{Δ*_b}` distribution carries **both** the coefficient variability (step 1) **and** the canary-session/pair sampling variability (step 2).

- **Exact independence / cross-fitting rule:** the calibration-session draw and the evaluation-session draw use **two independent RNG substreams** (seed below), are **never coupled or index-paired**, and operate on the **disjoint** universes above. Coefficients are **only ever** fit on calibration resamples and **only ever** applied to evaluation resamples — **no canary session ever enters a calibration fit** (the cross-fit boundary is the readonly/canary split). The coefficient error and the evaluation-sample error are therefore propagated **jointly but without leakage**.

- **Repetitions:** **`B = 10000`** replications (only numerically-undefined redraws under §5.3 do not count toward `B`).
- **Seed:** fixed **`rng_seed = 20260630`** (NumPy `SeedSequence(20260630)`, PCG64), **spawned into two independent child streams** `spawn(2) → [calibration_stream, evaluation_stream]`; recorded so the interval is exactly reproducible.

### 5.2 Pre-canary power/precision readiness (replaces the arbitrary floor — answers Codex round-8)

Gate **readiness is decided upfront from the independent-session count and a pre-canary precision calculation on the calibration cluster variance** — never by censoring bootstrap draws. Sessions, not fills, are the independent unit, so the readiness threshold is expressed in **distinct independent sessions**.

- **Readiness target (frozen procedure parameter, one-sided):** the **maximum admissible one-sided 95% CI half-width** of `Δ` at gate evaluation is **`HW_target = 4 bps`**, where the half-width `HW = (upper 95% CB of Δ) − Δ̂`. Rationale: `HW_target` must sit **materially inside** the 10-bps inferiority margin so a near-zero point estimate can be resolved below the margin and a genuinely inferior arm cannot earn a PASS from a wide interval (4 bps leaves a point estimate up to +6 bps still resolvable below +10). **Equivalent power reading:** this is the precision at which the one-sided non-inferiority test has ≥ ~0.8 power to place the upper 95% CB below +10 bps when the true `Δ = 0`; the half-width form is registered as primary because it needs **no assumed true value**.
- **Pilot cluster variance (frozen at calibration):** from the §3.1 calibration window compute the **session-level (cluster) variance of the per-session median signed-IS difference**, `σ̂²_sess` (bps²) — the *between-session* variance of the session-level statistic, the correct dispersion unit because sessions, not fills, are independent. Written at freeze as **`σ̂²_sess = <<FROZEN AT CALIBRATION §3>>`**. Because no intraday IS distribution exists strictly before canary, the calibration (batch-side) session dispersion is the frozen **proxy** for the canary session dispersion — a stated approximation, made honest by the achieved-half-width confirmation below.
- **Minimum independent sessions (frozen at calibration):**
  `S_ready = max( S_floor , ⌈ ( z_0.95 · σ̂_sess / HW_target )² ⌉ )`, with `z_0.95 = 1.645` and a hard **`S_floor = 20` distinct sessions** so a one-sided 95th-percentile bootstrap has cluster-level tail resolution **regardless of a small pilot variance** (this floor is what directly answers "three clusters have no credible tail resolution"). `S_ready = <<FROZEN AT CALIBRATION §3>>`. The closed form is a cluster-normal **planning projection**; the **binding** check is the achieved half-width below.
- **Evaluability rule — the gate becomes evaluable ONLY when BOTH hold:**
  1. the canary has accrued **`S_distinct ≥ S_ready`** distinct **independent** sessions, each contributing ≥ 1 admitted pair; **and**
  2. the **achieved** one-sided 95% CI half-width from the §5.1 joint bootstrap over the **actual** canary sessions is **`HW ≤ HW_target`**.
  Condition 2 closes the proxy loophole: if the realized canary session dispersion exceeds the pilot estimate, `S_ready` sessions may not deliver `HW_target`, and the gate stays non-evaluable until they do (or forever, if the sampling cause is not fixed).
- **If the target is NOT met by end-of-canary (pre-registered):** the gate **stays NON-EVALUABLE → operations-only**. The operator MAY (a) **extend the canary** to accrue more independent sessions **under the frozen procedure** — adding frozen-procedure sessions tunes nothing, because `HW_target`, `S_ready`, `σ̂²_sess`, the §5.4 block length, the bootstrap, and the §7 caps are all frozen — or (b) fix the sampling/dispersion cause and re-run; the operator **MUST NOT** force a PASS or a FAIL from underpowered data. An underpowered canary yields **no execution-quality verdict**, only the operations verdict (RFC §9.2c / §9.3).

### 5.3 Numerical-degeneracy guard (NOT an evaluability or power mechanism)

The **only** discard permitted is for a **computationally-undefined** replication; it does **NOT** substitute for §5.2 and does **NOT** condition on session diversity:

- A replication is **numerically degenerate** *only if* its `Δ*_b` is **undefined** — i.e. its evaluation resample contains **zero admitted pairs** (median undefined) or its calibration resample leaves a **fitted bucket empty** (coefficient undefined). Such a replication is discarded and redrawn from the same substream up to **`R_numeric_max = 20`** attempts; only a computable `Δ*_b` counts toward `B`.
- **Low-diversity-but-computable resamples are RETAINED.** A with-replacement session draw that collapses onto few distinct sessions but still yields a defined `Δ*_b` carries **real** sampling variability and is **kept** — censoring it is the anti-conservative move Codex flagged, and it is now explicitly forbidden.
- A **tiny** base guard **`M_admit_min = 2`** admitted pairs (a difference of medians needs ≥ 2) guards only against an **undefined base statistic**; it is **numerical, not evidential**, and does **not** substitute for the §5.2 `S_ready` / `HW_target` threshold. Once `S_distinct ≥ S_ready ≥ 20`, undefined resamples are vanishingly rare, so this guard essentially never fires; if `R_numeric_max` is exhausted at the **base** level the cause is a data-plane defect → gate **NON-EVALUABLE** (operations-only), not a computed gate.

### 5.4 Block length — pre-canary serial-dependence diagnostic (justify OR replace the 1-session block)

Session clustering preserves *intra*-session dependence but a **1-session block assumes away cross-session autocorrelation / regime runs**. That assumption is pre-registered to be **tested, and replaced if it fails**, on the calibration session series (the only pre-canary proxy):

- **Diagnostic (frozen):** on the §3.1 calibration **session-level** series of the per-session median signed-IS difference, run (i) a **Ljung–Box** test at lags 1…5 and (ii) a **Wald–Wolfowitz runs test** on the sign of the session statistic, at a pre-set level **`α_dep = 0.10`**.
- **Branch (frozen procedure; the resulting block length is a fitted output):**
  - **Pass** (fail to reject *both* → no material cross-session dependence): **block length = 1 session** — the r8 assumption, now justified rather than assumed.
  - **Fail** (either rejects): switch to a pre-registered **stationary (Politis–Romano) block bootstrap** with a **data-driven mean block length `L*`** from the **Politis–White (2004) automatic block-length selector** computed on the calibration session series. `L*` is written at freeze.
- **Frozen output:** the diagnostic outcome and the resulting **block length (`1` or the stationary-bootstrap `L*`)** are `<<FROZEN AT CALIBRATION §3>>` and apply identically to **both** universes' session resampling in §5.1.
- **Gate-time fragility re-check (reported, not a silent override):** at gate evaluation the same diagnostic is recomputed on the **canary** session series; if it now shows material dependence the frozen block length does not cover, the window report **flags the bound as potentially anti-conservative** (a fragility flag alongside the §7.2 grid), so the operator sees the frozen block may understate serial dependence.

### 5.5 Aggregation + overlap PASS rule (unchanged from r8)

- **Aggregation:** the **one-sided upper 95% confidence bound of `Δ`** is the **95th percentile of the `{Δ*_b}` distribution over the `B` valid replications** — reflecting **both** the calibration-coefficient and the evaluation-sample variability. Because the EVALUATION universe is the canary window, **this joint CB can only be COMPUTED at gate-evaluation time (after canary), not at freeze**; what is recorded at freeze (§2/§3.6) is the **calibration-coefficient** bootstrap dispersion (the outer-loop diagnostic), `σ̂²_sess`, `S_ready`, `HW_target`, and the §5.4 block length. The **achieved half-width `HW`** (§5.2) is reported with the bound.
- **PASS rule (overlap-aware):** the intraday arm PASSES execution-quality **only if the gate is EVALUABLE (§5.2) AND that one-sided upper 95% CB of `Δ` lies BELOW the +10-bps inferiority margin** — the interval must **exclude** +10 bps, not merely the point estimate. If the gate is **non-evaluable**, or +10 bps lies within the interval, the result is "**not distinguishable / underpowered**" → **NOT a PASS**.

### 5.6 Frozen resampling + readiness DOF

The two-universe cross-fit split, the §5.4 diagnostic (Ljung–Box lags 1…5 + runs test) + `α_dep = 0.10` + the pass/fail branch, `B = 10000`, `rng_seed = 20260630` (spawned into 2 child streams), the one-sided-95% level, `HW_target = 4 bps`, `S_floor = 20`, `z_0.95 = 1.645`, the `S_ready` formula, the §5.2 evaluability rule (`S_distinct ≥ S_ready` **AND** achieved `HW ≤ HW_target`) and its not-met handling, `M_admit_min = 2`, and `R_numeric_max = 20` are **all part of the frozen content** (§6 fingerprint). Only the **fitted** `k_spread` / `k_auction` (and their calibration-coefficient bootstrap dispersion), **`σ̂²_sess`**, **`S_ready`**, the **§5.4 diagnostic outcome + block length**, and the §7 caps remain `<<FROZEN AT CALIBRATION §3>>`.

## 6. Immutable fingerprint (detached, single canonical algorithm)

- **Algorithm (one, canonical):** `synthetic_baseline_prereg_sha` = **SHA-256** (lowercase hex) of the **exact committed byte content** of this file (`2026-06-30-stage1-synthetic-baseline-prereg.md`) — UTF-8, LF line endings, single trailing newline. **No other algorithm is permitted** (the earlier "sha256 / git-blob sha" ambiguity is removed).
- **Detached storage (removes the self-reference):** the hash is **NOT written inside this file**. It is stored in a committed sidecar `2026-06-30-stage1-synthetic-baseline-prereg.sha256` created by the freeze PR, and stamped into **every** synthetic batch-fill ledger row as `synthetic_baseline_prereg_sha` (alongside `synthetic = true`). Because the hash never appears in the hashed bytes, computing/recording it does **not** change the hashed content.
- **Verification (fail-closed):** readonly and canary run-creation recompute SHA-256 over this file's bytes and require it to equal BOTH (i) the sidecar value and (ii) the value about to be stamped in the ledger, AND require `STATUS == FROZEN` (§0.5). Any mismatch, a missing sidecar, or a non-FROZEN status **aborts run-creation**. Any post-freeze edit changes the hash and is therefore detectable → the run is **invalidated**.

## 7. No-fill / censoring — ITT adversarial censoring-sensitivity analysis (RFC §9.2d)

The Stage-1 execution-quality estimand is **intent-to-treat over the admitted pre-treatment pair set** (RFC §9.2 / §9.2d): no admitted pair is dropped for an arm's no-fill, because intraday no-fill / no-trigger is **not missing-at-random**. Each censored *cell* (one arm of one pair) is imputed to a frozen, **adversarial-against-PASS** value so the worst executions cannot vanish from the median. These caps are researcher DOF and are frozen here, from the **pre-canary** calibration window of §3 — never from canary data.

> **This is a CHOSEN adversarial SENSITIVITY SCENARIO — NOT a Manski/worst-case support bound.** The caps in §7.1 are the empirical **95th / 5th percentiles** of a *pre-canary batch* IS distribution; by construction **~5% of observed calibration outcomes already lie beyond each cap**, and that batch distribution is **not** guaranteed to bound the (unobserved) intraday execution outcomes. So these caps do **not** define the mathematical support and this is not a hard Manski bound. Instead we (i) gate on this frozen adversarial scenario **and** (ii) require the §7.2 sensitivity grid + tipping point, so the fragility of a PASS to the cap choice is explicit.

### 7.1 Frozen adversarial caps (researcher DOF → pre-registered)

| DOF | Frozen value | Meaning |
|---|---|---|
| `IS_cap_hi` | `<<FROZEN AT CALIBRATION §3>>` = **95th percentile** of the §3 calibration-window realized 104 next-open IS distribution (bps) | imputed for a censored **intraday** cell (intraday no-trigger / reject / unfilled-at-close) — assume the missing intraday execution was as **bad** as this cap |
| `IS_cap_lo` | `<<FROZEN AT CALIBRATION §3>>` = **5th percentile** of the same distribution (bps) | imputed for a censored **batch** cell (synthetic no-quote, §4) — assume the missing batch execution was as **good** as this cap |
| `c_max` | **0.10** (10% of admitted pairs) | max censored fraction at which the IS gate is **evaluable**; above it the gate is **NOT evaluable** → operations-only + fix the censoring cause |

- **Why these directions:** a censored intraday cell → `IS_cap_hi` (push intraday cost UP) and a censored batch cell → `IS_cap_lo` (push batch cost DOWN) both **enlarge** `Δ = IS_intraday − IS_batch`. The §5 one-sided upper CB of Δ is computed on the **imputed-complete admitted set**; **the gate requires that adversarial-scenario upper CB to stay below the +10-bps margin.** If the gate survives the maximally-adversarial-within-scenario imputation, censoring within the frozen scenario cannot have manufactured the PASS.
- **Second non-evaluability trigger (from §5.2):** independent of `c_max`, the gate is **also NON-EVALUABLE** whenever the §5.2 **pre-canary power/precision readiness** is not met — the canary has fewer than **`S_ready`** distinct independent sessions, **OR** the **achieved** one-sided 95% CI half-width exceeds **`HW_target = 4 bps`**. Same **operations-only** handling: **extend the canary under the frozen procedure** to accrue more independent sessions, or fix the sampling/dispersion cause and re-run; **never force a PASS/FAIL from underpowered data**. (The separate tiny §5.3 numerical-degeneracy guard, `M_admit_min = 2`, guards only an undefined statistic and is **not** an evidence threshold — it does not substitute for this readiness rule.)

### 7.2 Sensitivity grid + tipping point (REQUIRED report, not optional)

Because §7.1 is a chosen scenario and not a hard support bound, the freeze report and **every** session-window report MUST include a **cap-severity grid**: recompute the §5 upper-CB-of-Δ PASS rule with the intraday cap set to the **{90, 95, 97.5, 99}th** percentile and the batch cap mirrored to the **{10, 5, 2.5, 1}th** percentile of the §3 distribution (severity increases left→right; **95/5 is the frozen gate row**). Report, per grid point, PASS/FAIL of the upper-CB rule, and the **tipping-point percentile** at which the gate flips PASS↔FAIL. The frozen **95/5 scenario is the gate**; the grid is reported so the operator can see whether a PASS is **robust** across the grid or **fragile** at the frozen point (a PASS that holds only at ≤95/≥5 and fails by 97.5/2.5 is flagged **fragile**). The grid definition here is part of the frozen content.

- **Support proxy, stated:** no intraday IS distribution exists strictly before canary, so the §3 batch IS distribution is the only frozen reference; the 95th/5th percentiles are a deliberately conservative *scenario* proxy for the worst/best plausible execution — **not** a support bound. This choice is frozen.
- **Reported alongside (not a gate):** the **complete-case** Δ (censored cells dropped) is reported with the adversarial-scenario Δ and the per-cause censoring counts each session-window; a complete-case-PASS / adversarial-scenario-FAIL split → **NOT a PASS** (RFC §9.2d).
- **Critical-cause censoring** (intraday reject from invalid order/state/contract) independently triggers the RFC §9.3 Tier-1 HARD halt regardless of `c_max`; it is never *only* censored.
- `IS_cap_hi`, `IS_cap_lo`, `c_max`, the §7.2 grid definition, and the §3/§5 procedure are all part of the frozen content → covered by `synthetic_baseline_prereg_sha`; changing any after readonly/canary invalidates the run.

---

## Gate-readiness statement

Until this artifact is `FROZEN` (status flipped, calibration values written, detached `synthetic_baseline_prereg_sha` sidecar committed) **and that freeze PR has merged before readonly starts**, the Stage-1 execution-quality (IS) acceptance in RFC §9.3 **cannot be evaluated**, and Stage 1 is limited to validating **operations only**. Readonly and canary run-creation fail closed on a non-FROZEN or fingerprint-mismatched artifact (§0.5 / §6).
