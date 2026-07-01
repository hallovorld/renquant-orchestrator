# renquant105 Stage-1 — Synthetic Batch-Fill Baseline PRE-REGISTRATION (FREEZE TEMPLATE)

STATUS: **FREEZE TEMPLATE — NOT YET FROZEN.** This file is the *template* for the Stage-1 synthetic-baseline pre-registration. The **PROCEDURE** (§1–§5, §7) is already pinned wording — not a researcher degree of freedom once this RFC merges — but the fitted **numerical outputs** are still placeholders (`<<FROZEN AT CALIBRATION §3>>`). It therefore does **not** yet freeze all values, and must not be cited as if it does. A separate **calibration/freeze PR** must (i) run the §3 procedure exactly as written, (ii) write the fitted numbers into §2/§5/§7, (iii) flip this `STATUS` to `FROZEN (<date>)`, and (iv) commit the detached fingerprint sidecar (§6). **That freeze PR MUST MERGE before the readonly phase begins — not merely before canary** — because readonly already reveals pair composition, opening references, missingness, and modeled synthetic outcomes, so any tuning of coefficients or caps after readonly is a leak. Readonly and canary run-creation **fail closed** on an unfrozen (`STATUS ≠ FROZEN`) or fingerprint-mismatched artifact (§0/§6). While this file is a template (not `FROZEN`), Stage 1 may validate **operations only** (no-leak + idempotency + reconciliation + session-boundary); it **MAY NOT** claim a comparative execution-quality PASS (RFC §9.2c / §9.3).

DATE: 2026-06-30
OWNER: orchestrator control-plane (measurement); pipeline owns the runtime IS ledger schema.
REFERENCED BY: `doc/design/2026-06-30-renquant105-intraday-decisioning-architecture.md` §9.2b / §9.2c / §9.2d / §9.3.
PURPOSE: pin every researcher degree of freedom in the **synthetic batch-fill control arm** of the Stage-1 execution-quality A/B (RFC option (a): one real intraday fill vs a quote-based synthetic batch fill), **and** the no-fill / censoring imputation DOF of the §9.2d intent-to-treat sensitivity analysis. These DOF can move the baseline by **more than the 10-bps acceptance gate** and could otherwise be chosen *after* readonly/canary evidence is seen — so both the procedure (now) and its fitted numbers (at freeze, before readonly) are pinned, before any readonly or canary data exists.

---

## 0. Freeze procedure (immutability) + when it must happen

**The PROCEDURE in §1–§5 and §7 is pinned by this committed template and ceases to be a researcher DOF once the RFC merges.** Only the fitted numerical outputs (`k_spread`, `k_auction`, their §5 bootstrap dispersion, and the §7 caps) remain to be populated. The freeze steps:

1. Run the §3 calibration **exactly as specified** on the trailing 60-session window ending strictly before the readonly phase; write the fitted `k_spread`, `k_auction`, their §5 **calibration-coefficient** bootstrap dispersion (the outer-loop diagnostic — the full joint CB of `Δ` is computed at gate-evaluation over canary, §5), and the §7 caps (`IS_cap_hi`, `IS_cap_lo`) into §2/§5/§7. No step of the procedure may be altered — only the numbers are filled in.
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

**3.6 Frozen outputs.** Running §3.1–§3.5 yields, per (pooled) bucket, the point estimates `k_spread`, `k_auction`, the §5 **calibration-coefficient** bootstrap joint distribution (outer-loop diagnostic), and (from the same window's `IS_obs`) the §7 caps. These numbers are written into §2/§5/§7 at freeze and **never re-fit** after readonly/canary data is observed. The §5 gate CB itself (which additionally block-resamples the canary window) is **evaluated at gate time, not at freeze** — only the procedure is frozen now.

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

## 5. Uncertainty procedure (frozen) — JOINT calibration+evaluation bootstrap + the overlap PASS rule

Every resampling DOF is pinned here. The reported bound must propagate **BOTH** sources of uncertainty in the estimand: **(i) calibration-coefficient** uncertainty (the fitted synthetic model) **and (ii) evaluation-sample** uncertainty (the canary sessions/pairs whose median intraday IS and synthetic-batch IS define `Δ`). The earlier (r7) procedure resampled only the calibration window and re-fit the coefficients, but computed each `Δ*` over the **FIXED** canary/admitted set — so its distribution captured coefficient uncertainty **only**, the one-sided 95% upper CB was too narrow, and it could not support the +10-bps gate. The r8 procedure below is a **joint (nested) session-block bootstrap** that also block-resamples the canary window.

- **Confidence level:** **one-sided 95%** (matching the RFC §9.3 reject gate); the gate uses the one-sided **upper** 95% confidence bound of `Δ`.

- **Two disjoint resampling universes (the cross-fit boundary):**
  - **CALIBRATION universe** = the 60 pre-readonly calibration sessions of §3.1.
  - **EVALUATION universe** = the canary/admitted sessions (the readonly/canary window over which the `Δ` estimand is defined).
  - These universes are **DISJOINT by construction**: the §3.1 calibration cutoff **is** the readonly/canary boundary, so **no canary session can enter the calibration fit** and no calibration session can enter the evaluation median. **This split IS the cross-fit boundary** — coefficients are always fit on calibration resamples and applied to (never fit on) evaluation resamples.

- **Resampling unit + blocking (both universes):** a **session-level block bootstrap** — the resampling unit is the **session**, resampled with replacement, **block length = one session** (all fills/pairs within a drawn session stay together), so intra-session cross-sectional correlation **and the matched-pair structure** are preserved. Individual fills or pairs are **NEVER** resampled independently.

- **Nested / paired draw (per replication `b = 1 … B`):**
  1. **Outer — calibration resample (coefficient uncertainty):** draw sessions with replacement from the **CALIBRATION** universe and **re-fit** `(k_spread, k_auction)` per bucket by the full §3.4 constrained-Huber procedure on that resample. Parameter + residual dispersion enter through the re-fit itself (NOT an assumed Gaussian from analytic SEs, NOT a separate parameter draw).
  2. **Inner — evaluation resample (sample uncertainty), drawn INDEPENDENTLY:** **independently** (a separate RNG substream, never index-paired to the outer draw) draw sessions with replacement from the **EVALUATION** universe.
  3. **Statistic:** on the evaluation resample, form each admitted pair's synthetic batch fill with **this replication's** re-fit coefficients, apply the §7 adversarial imputation to every censored cell, and compute `Δ*_b = median(IS_intraday_real) − median(IS_batch_synthetic)` over that replication's **§7 imputed-complete admitted set** (the frozen gate scenario).

  Because step 1 (calibration) and step 2 (evaluation) are drawn **independently**, the `{Δ*_b}` distribution carries **both** the coefficient variability (step 1) **and** the canary-session/pair sampling variability (step 2). This is the single substantive change from r7, which held the evaluation set fixed.

- **Exact independence / cross-fitting rule:** the calibration-session draw and the evaluation-session draw use **two independent RNG substreams** (seed below), are **never coupled or index-paired**, and operate on the **disjoint** universes above. Coefficients are **only ever** fit on calibration resamples and **only ever** applied to evaluation resamples — **no canary session ever enters a calibration fit** (the cross-fit boundary is the readonly/canary split). The coefficient error and the evaluation-sample error are therefore propagated **jointly but without leakage**.

- **Block length:** **one session** (frozen, both universes).
- **Repetitions:** **`B = 10000`** *valid* replications (degenerate redraws below do not count toward `B`).
- **Seed:** fixed **`rng_seed = 20260630`** (NumPy `SeedSequence(20260630)`, PCG64), **spawned into two independent child streams** `spawn(2) → [calibration_stream, evaluation_stream]`; recorded so the interval is exactly reproducible.

- **Degenerate-resample rule (pre-registered — no post-hoc DOF):**
  - **Per-replication guard (discard + redraw):** an **evaluation** resample is **degenerate** if it draws fewer than **`M_admit_min = 10`** admitted pairs with **≥ 1 uncensored arm**, or fewer than **`S_eval_min = 3`** *distinct* canary sessions (a with-replacement draw can collapse onto too few sessions). A degenerate evaluation resample is **discarded and REDRAWN** from the same `evaluation_stream` (advancing it), up to **`R_redraw_max = 100`** attempts per replication; only a valid resample's `Δ*_b` counts toward `B`. (The calibration resample is governed by the §3.3 `N_bucket_min = 200` pooling and is not separately re-guarded here.)
  - **Whole-gate non-evaluability:** if the **base** (un-resampled) admitted set has fewer than **`M_admit_min`** admitted pairs, **OR** `R_redraw_max` is exhausted on any replication (valid evaluation resamples are structurally too rare), the **entire IS gate is declared NON-EVALUABLE** → **operations-only** + fix the sampling/censoring cause + re-run the window — identical handling to the §7.1 `c_max` precondition. The gate is **never** silently computed on a degenerate sample.

- **Aggregation:** the **one-sided upper 95% confidence bound of `Δ`** is the **95th percentile of the `{Δ*_b}` distribution over the `B` valid replications** — this bound now reflects **both** the calibration-coefficient and the evaluation-sample variability. Because the EVALUATION universe is the canary window, **this joint CB can only be COMPUTED at gate-evaluation time (after canary), not at freeze**; what is recorded at freeze (§2/§3.6) is the **calibration-coefficient** bootstrap dispersion (the outer-loop diagnostic), while the reported gate bound is evaluated over the canary sessions **under this frozen procedure**.

- **PASS rule (overlap-aware):** the intraday arm PASSES execution-quality **only if that one-sided upper 95% CB of `Δ` lies BELOW the +10-bps inferiority margin** — the interval must **exclude** +10 bps, not merely the point estimate. If +10 bps lies within the interval, the result is "**not distinguishable**" → **NOT a PASS**.

- **Frozen resampling DOF:** the two-universe cross-fit split, the session block length (1), `B = 10000`, `rng_seed = 20260630` (spawned into 2 child streams), the one-sided-95% level, `M_admit_min = 10`, `S_eval_min = 3`, `R_redraw_max = 100`, and the discard-redraw / non-evaluability handling are **all part of the frozen content** (§6 fingerprint). Only the fitted `k_spread` / `k_auction` (and their calibration-coefficient bootstrap dispersion) remain `<<FROZEN AT CALIBRATION §3>>`.

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
- **Second non-evaluability trigger (from §5):** independent of `c_max`, the gate is **also NON-EVALUABLE** whenever the §5 **degenerate-resample rule** fires — the base admitted set has fewer than `M_admit_min = 10` admitted pairs, or a replication exhausts `R_redraw_max = 100` valid-evaluation-resample redraws. Same **operations-only** handling: fix the sampling/censoring cause and re-run the window; the gate is never computed on a degenerate sample.

### 7.2 Sensitivity grid + tipping point (REQUIRED report, not optional)

Because §7.1 is a chosen scenario and not a hard support bound, the freeze report and **every** session-window report MUST include a **cap-severity grid**: recompute the §5 upper-CB-of-Δ PASS rule with the intraday cap set to the **{90, 95, 97.5, 99}th** percentile and the batch cap mirrored to the **{10, 5, 2.5, 1}th** percentile of the §3 distribution (severity increases left→right; **95/5 is the frozen gate row**). Report, per grid point, PASS/FAIL of the upper-CB rule, and the **tipping-point percentile** at which the gate flips PASS↔FAIL. The frozen **95/5 scenario is the gate**; the grid is reported so the operator can see whether a PASS is **robust** across the grid or **fragile** at the frozen point (a PASS that holds only at ≤95/≥5 and fails by 97.5/2.5 is flagged **fragile**). The grid definition here is part of the frozen content.

- **Support proxy, stated:** no intraday IS distribution exists strictly before canary, so the §3 batch IS distribution is the only frozen reference; the 95th/5th percentiles are a deliberately conservative *scenario* proxy for the worst/best plausible execution — **not** a support bound. This choice is frozen.
- **Reported alongside (not a gate):** the **complete-case** Δ (censored cells dropped) is reported with the adversarial-scenario Δ and the per-cause censoring counts each session-window; a complete-case-PASS / adversarial-scenario-FAIL split → **NOT a PASS** (RFC §9.2d).
- **Critical-cause censoring** (intraday reject from invalid order/state/contract) independently triggers the RFC §9.3 Tier-1 HARD halt regardless of `c_max`; it is never *only* censored.
- `IS_cap_hi`, `IS_cap_lo`, `c_max`, the §7.2 grid definition, and the §3/§5 procedure are all part of the frozen content → covered by `synthetic_baseline_prereg_sha`; changing any after readonly/canary invalidates the run.

---

## Gate-readiness statement

Until this artifact is `FROZEN` (status flipped, calibration values written, detached `synthetic_baseline_prereg_sha` sidecar committed) **and that freeze PR has merged before readonly starts**, the Stage-1 execution-quality (IS) acceptance in RFC §9.3 **cannot be evaluated**, and Stage 1 is limited to validating **operations only**. Readonly and canary run-creation fail closed on a non-FROZEN or fingerprint-mismatched artifact (§0.5 / §6).
