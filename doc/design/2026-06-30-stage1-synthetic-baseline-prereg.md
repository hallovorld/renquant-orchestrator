# renquant105 Stage-1 — Synthetic Batch-Fill Baseline PRE-REGISTRATION

STATUS: **DRAFT — UNFROZEN.** This artifact MUST be moved to `FROZEN` (status flipped + content sha computed and recorded) **before the first renquant105 canary order is placed**. While `UNFROZEN`, Stage 1 may validate **operations only** (no-leak + idempotency + reconciliation + session-boundary); it **MAY NOT** claim a comparative execution-quality PASS (RFC §9.2c / §9.3).

DATE: 2026-06-30
OWNER: orchestrator control-plane (measurement); pipeline owns the runtime IS ledger schema.
REFERENCED BY: `doc/design/2026-06-30-renquant105-intraday-decisioning-architecture.md` §9.2b / §9.2c / §9.2d / §9.3.
PURPOSE: pin every researcher degree of freedom in the **synthetic batch-fill control arm** of the Stage-1 execution-quality A/B (RFC option (a): one real intraday fill vs a quote-based synthetic batch fill), **and** the no-fill / censoring imputation DOF of the §9.2d intent-to-treat worst-case bound. These DOF can move the baseline by **more than the 10-bps acceptance gate** and could otherwise be chosen *after* canary fills are seen — so they are frozen here, before any canary data exists.

---

## 0. Freeze procedure (immutability)

1. Populate the committed default values below (those marked `<<FROZEN AT …>>` are calibrated from §3; the rest are already fixed).
2. Run the §3 calibration on the trailing 60-session window ending strictly before the readonly phase; write the fitted `k_spread`, `k_auction` and their standard errors into §2, **and** the §7 censoring caps (`IS_cap_hi`, `IS_cap_lo`) computed from the same window.
3. Flip `STATUS` to `FROZEN (<date>)`. Compute `synthetic_baseline_prereg_sha = sha256(frozen content of this file)` (git blob sha is acceptable) and record it in §6.
4. From that point the file is immutable. Every synthetic batch-fill ledger row stamps `synthetic = true` and `synthetic_baseline_prereg_sha`. **Any edit after freeze changes the sha and INVALIDATES the run.**

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
| `k_spread` | fraction of the open half-spread paid (dimensionless) | `<<FROZEN AT CALIBRATION §3>>` (initial prior 0.5) |
| `auction_slippage_proxy` | per-symbol opening-imbalance slippage, in price terms (bps × P_open) | §4 auction-imbalance treatment |
| `k_auction` | auction-slippage coefficient (dimensionless) | `<<FROZEN AT CALIBRATION §3>>` |

`k_spread` and `k_auction` are **fit once** on the §3 window and then frozen; their fitted values and standard errors are recorded here at freeze and **never re-fit** after canary data is observed.

## 3. Calibration dataset + cutoff (strictly before canary)

- **Dataset:** the trailing **60 trading sessions** of 104's *realized next-open batch fills* paired with the same-session opening reference (§1), conditioned on **symbol liquidity bucket** (so coefficients are not dominated by one name).
- **Cutoff:** the **last session before the readonly phase begins** — strictly before the canary. No session at or after canary start may enter calibration.
- **Fit:** estimate `k_spread`, `k_auction` (and residual dispersion) on that window; record point values + standard errors in §2/§5. Re-fitting after canary data invalidates the pre-registration.

## 4. Per-component treatment (each: how handled / how censored)

| Component | Treatment | Censoring / flag |
|---|---|---|
| **Spread** | charged as `k_spread * half_spread_open` against the trader | — |
| **Auction imbalance** | `auction_slippage_proxy` from the published opening imbalance (imbalance share / auction size), per liquidity bucket | if the imbalance feed is unavailable → set to `0`, flag `auction_imbalance = unavailable`. NOTE: 0 **understates** batch cost, making the batch look *better* and **raising** the bar for an intraday PASS — conservative against the intraday arm. |
| **Latency** | synthetic arm fills **at the cross** → modeled latency = **0** (stated modeling choice) | real decision→fill latency is measured only on the **real intraday** arm |
| **Fees** | same commission schedule applied to **both** arms (nets out in the difference; included for completeness) | — |
| **Rejects** | synthetic arm **cannot** be rejected (no real order) | a **real intraday reject** removes that pair's intraday fill → the **pair is censored** (RFC §9.3) and counted |
| **No-quote** | no valid open NBBO → **no synthetic fill is formed** | pair **censored**, flag `synthetic_no_quote = true`, **never imputed** |

## 5. Uncertainty band + the overlap PASS rule

- **Band source:** per-fill uncertainty propagated from (i) the calibration **standard errors** of `k_spread`, `k_auction` and (ii) the **residual dispersion** of the §3 calibration fit.
- **Aggregation:** propagate to a confidence interval on the **matched-pair median IS difference** `Δ = median(IS_intraday_real) − median(IS_batch_synthetic)` (e.g. bootstrap over matched admitted pairs combined with the parameter-uncertainty draws).
- **PASS rule (overlap-aware):** the intraday arm PASSES execution-quality **only if the one-sided upper confidence bound of `Δ` lies BELOW the +10-bps inferiority margin** — i.e. the CI of the *difference* must **exclude** the +10-bps margin, **not merely the point estimate**. If the +10-bps margin **overlaps** the band, the result is "**not distinguishable**" → **NOT a PASS**.

## 6. Immutable fingerprint (stamped in every ledger row)

- On freeze: `synthetic_baseline_prereg_sha = <<sha256 / git-blob sha of this frozen file — recorded at freeze>>`.
- **Every** ledger row carrying a synthetic batch fill stores `synthetic = true` **and** `synthetic_baseline_prereg_sha`.
- Any post-freeze change to this model changes the sha and is therefore detectable in the ledger → such a run is **invalidated**.

## 7. No-fill / censoring imputation (RFC §9.2d — the ITT worst-case bound)

The Stage-1 execution-quality estimand is **intent-to-treat over the admitted pre-treatment pair set** (RFC §9.2 / §9.2d): no admitted pair is dropped for an arm's no-fill, because intraday no-fill / no-trigger is **not missing-at-random**. Each censored *cell* (one arm of one pair) is imputed to a frozen, **adversarial-against-PASS** cap, so the worst executions cannot vanish from the median. These caps are researcher DOF and are frozen here, from the **pre-canary** calibration window of §3 — never from canary data.

| DOF | Frozen value | Meaning |
|---|---|---|
| `IS_cap_hi` | `<<FROZEN AT CALIBRATION §3>>` = **95th percentile** of the §3 calibration-window realized 104 next-open IS distribution (bps) | imputed for a censored **intraday** cell (intraday no-trigger / reject / unfilled-at-close) — assume the missing intraday execution was as **bad** as this cap |
| `IS_cap_lo` | `<<FROZEN AT CALIBRATION §3>>` = **5th percentile** of the same distribution (bps) | imputed for a censored **batch** cell (synthetic no-quote, §4) — assume the missing batch execution was as **good** as this cap |
| `c_max` | **0.10** (10% of admitted pairs) | max censored fraction at which the IS gate is **evaluable**; above it the gate is **NOT evaluable** → operations-only + fix the censoring cause |

- **Why these directions:** a censored intraday cell → `IS_cap_hi` (push intraday cost UP) and a censored batch cell → `IS_cap_lo` (push batch cost DOWN) both **enlarge** `Δ = IS_intraday − IS_batch`. The §5 one-sided upper CB of Δ is then computed on the **imputed-complete admitted set**; **PASS requires that worst-case upper CB to stay below the +10-bps margin.** If the gate survives the maximally-adversarial imputation, censoring cannot have manufactured the PASS.
- **Support proxy, stated:** no intraday IS distribution exists strictly before canary, so the §3 batch IS distribution is the only frozen reference; the 95th/5th percentiles are a deliberately conservative support proxy for the worst/best plausible execution. This choice is frozen.
- **Reported alongside (not a gate):** the **complete-case** Δ (censored cells dropped) is reported with the worst-case Δ and the per-cause censoring counts each session-window; a complete-case-PASS / worst-case-FAIL split → **NOT a PASS** (RFC §9.2d).
- **Critical-cause censoring** (intraday reject from invalid order/state/contract) independently triggers the RFC §9.3 Tier-1 HARD halt regardless of `c_max`; it is never *only* censored.
- `IS_cap_hi`, `IS_cap_lo`, `c_max` are part of the frozen content → covered by `synthetic_baseline_prereg_sha`; changing any after canary invalidates the run.

---

## Gate-readiness statement

Until this artifact is `FROZEN` (status flipped, calibration values written, `synthetic_baseline_prereg_sha` recorded), the Stage-1 execution-quality (IS) acceptance in RFC §9.3 **cannot be evaluated**, and Stage 1 is limited to validating **operations only**.
