# GOAL-2v2 development-window attempt record — 2026-08-27 (attempts 1–3)

Protocol: the operator-acknowledged development-selection design (orch#1061
thread, ack 2026-08-26): **2016–2019 is the declared, consumed development
window; every attempt is enumerated here; a confirmatory prereg freezes only
after development closes and only on a screen pass; 2020–2023 stays
untouched.** This document is the durable copy of the attempt log posted on
the #1061 thread the same day.

## 0. Data engineering (all free, all isolated — no production path written)

- **Route correction first**: the 2021 valuation-coverage cliff in
  `sec_fundamentals_daily.parquet` is a UNIVERSE-EXPANSION cliff — of 563
  tickers valuation-covered only from 2021, **520 have price history starting
  2021** in `data/ohlcv/` (≤2016: 14). The earlier "backfill 535 names,
  230→750, 3.3×" claim was retracted on the thread.
- **Real widening route**: `alpha158_r2k_dataset.parquet` holds **1,301
  names with ≥400 development-window days** of prices+features and ZERO
  fundamentals coverage. SEC companyfacts harvested for them
  (`sec_edgar_companyfacts_harvester.py` + `harvest_equity_shares.py`
  supplement; 1,239/1,301 with equity+income facts; PIT `filed` dates;
  production overwrite-forward semantics).
- **Labels without prices** [VERIFIED to machine precision on 4 ground-truth
  tickers]: the dataset's `ROC20` is a GLOBAL affine transform of
  close_{t−20}/close_t with **β=2.288396, α=−2.326484**, so exact 20d
  forward returns are `β/(ROC20(t+20)−α) − 1`. Reconstruction error ≤1e−15.
- Combined development-window cross-section: **median 1,360 names/day**
  (~5.9× the K5 screen).

## 1. Attempts (the enumeration the protocol requires)

| # | estimand | oof_ic | block_t | verdict |
|---|---|---|---|---|
| 1 | equal-weight z composite (roe+gp+asset_growth) | +0.0001 | 0.49 | **METHOD ERROR** — not K5's estimand; `asset_growth` entered unsigned (it is a negative factor). Recorded, not evidence. |
| 2 | K5-faithful per-fold XGB quality base (K5 folds + hyperparams verbatim) | **+0.0125** | **0.756** | FAILS the ≥1.0 life-screen bar |
| 3 | attempt 2 cut by K5 approx-regime | BEAR +0.0252 / CALM +0.0147 / VOL +0.0042 | BEAR: 2 blocks, t 0.09 | Ordering replicates; **no regime has the blocks to clear any bar** |

Scripts: `scripts/experiments/g2v2_rescreen_quality{,_xgb,_regime_cut}.py`,
`harvest_equity_shares.py`, `build_backfill_panel.py`. Reports + ticker
lists: `doc/research/data/2026-08-27-g2v2-devday/`. The harvested JSONL
(~420MB) is re-fetchable deterministically from SEC companyfacts using the
committed ticker lists; it is not committed.

## 2. The finding

Widening the universe 5.9× raised the point estimate 30% and cleanly
replicated the regime ordering (BEAR > CALM > VOLATILE — the conditioning
premise points the right way), and **still cannot buy significance**: the
binding constraint is the factor's year-scale nonstationarity (2017 +0.055 /
2018 −0.018 / 2019 +0.021) and the development window's **2 BEAR blocks**.
This is the `effective-sample-before-decision-rule` constraint, in the same
place it killed the conditional-blend line.

**No attempt passed. The daily-panel route does not graduate to a
confirmatory prereg.**

## 3. The fork (operator decision; all three keep 2020–2023 untouched)

a. **Granularity** — the operator's original spec named 10-minute-or-finer
   data; regime blocks multiply ~40× per calendar year; the live rq105 tick
   plane is the natural substrate (GOAL-2 becomes a consumer of the 105 data
   plane).
b. **History** — extend development back past 2016; requires purchased
   price+fundamentals history predating every current dataset.
c. **Hold** — accrue the shadow-fleet record; revisit when BEAR blocks grow.
