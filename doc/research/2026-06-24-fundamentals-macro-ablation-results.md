# Results — do fundamentals / macro / analyst earn their keep? (#184 execution)

2026-06-24. Executes the pre-registered plan
`doc/research/2026-06-24-fundamentals-macro-ablation-plan.md` (#184). **Partial by
necessity** — see Scope. Leads with the conclusion; the honest caveats are not
buried.

## Bottom line
- **Fundamentals are practical-null as a feature group** in every regime: the
  alpha158+fund vs alpha158-only placebo-clean Δ stays inside the pre-registered
  ±0.01 margin AND fails the ≥5/6-window sign-consistency rule. They do not earn
  their keep for *stock selection* on this dataset.
- **The earlier 3-seed read was an artifact.** A 3-seed run had reported
  BULL_VOLATILE at a "robust" −0.0075 ± **0.0014**; that tiny sd came from
  averaging windows *before* taking the seed sd. The pre-registered 5-seed +
  per-window method gives −0.0075 ± **0.0199** (2/5 windows negative) — i.e.
  noise, not a robust negative. This is exactly the failure the ≥5-seed /
  per-window rule was written to catch.
- **Macro contributes 0 to selection by construction** (not in the scorer; only
  feeds GMM regime detection) — structural, not experimental.
- **Analyst data earns nothing usable right now:** yfinance net-upgrade is
  placebo-clean *negative* in all three regimes; the better-constructed FMP
  rating-revision is **plan-locked** on the free tier (see Analyst section).

## Result — fundamentals arm (5 seeds, per (regime × WF-window × seed))
A = alpha158(158) + fund(5) = 163 feats; B = alpha158-only = 158. Placebo-clean =
real − placebo (placebo = per-ticker label shifted +60 rows). Δ = A − B.

| regime | Δ placebo-clean (A−B) | windows Δ̄>0 | A clean | B clean | verdict |
|---|---|---|---|---|---|
| BULL_CALM | +0.0054 ± 0.0209 | 2/5 | +0.0042 | −0.0012 | practical-null |
| BEAR | +0.0081 ± 0.0306 | 1/2 | +0.3345 | +0.3264 | practical-null |
| BULL_VOLATILE | −0.0075 ± 0.0199 | 2/5 | +0.0266 | +0.0342 | practical-null |

Every regime: |Δ̄| < 0.01 and no regime has the sign holding in ≥5/6 windows. By
the plan's decision rule, fundamentals add no placebo-clean IC beyond noise.
(BEAR's high absolute IC ~0.33 is the known embargo/regime-persistence leakage
floor, not skill — trust the Δ, not the level. See [[wf-gate-embargo-leakage-floor]].)

## Analyst arm
- **yfinance net-upgrade** (trailing-90d net up/down, merged as-of): placebo-clean
  **negative** in all regimes — BULL_CALM −0.017, BEAR −0.149, BULL_VOLATILE
  −0.021. Crude event count is not a signal.
- **FMP `grades-historical` rating-revision** (the better, PIT-historical
  construction): a 2026-06-24 live probe shows the free BASIC tier **plan-locks
  ~70% of the watchlist** — HTTP 402 "Special Endpoint … not available under your
  current subscription" (a permanent ceiling, not a rate limit; clean A–L slice
  21 free / 51 premium ≈ 29% free). The single preliminary +0.031 BULL_CALM
  reading was on 38 names / 1 seed, inside the leakage-floor noise band — triage,
  not evidence, and not confirmable without paying for full coverage. Ingestion
  library (base-data #24) + cron (umbrella #402) are built and on HOLD.

## Scope — what this does and does NOT conclude
- **Run on alpha158 + fund only.** This dataset
  (`data/alpha158_291_fund_regime_dataset.parquet`, built 2026-05-08) has 158
  alpha158 + 5 fund columns and **no sentiment / PEAD-SUE columns**, so the plan's
  V5/V6 (sentiment, PEAD/SUE LOGO) arms **cannot be run here** — they are
  **DEFERRED** (need a panel with those groups merged), not concluded.
- **Does NOT license retiring the fundamentals pipeline.** Per plan rule #2, that
  needs the null to hold on the **post-#398/#401 refreshed + sanitized**
  fundamentals with freshness recorded. This dataset predates the 2026-06-23
  backfill, so its fundamentals may be the stale/corrupt vintage — a null here
  indicts the bundle's *current* value, it does not prove the *signal* is dead.
- **Underpowered for a hard "zero".** ~10 non-overlapping 60d windows (≈3–4 per
  regime) + a 0.036 ± 0.046 leakage floor. This can reject a strong group; a null
  bounds the effect as < ~0.01 IC, it does not prove exactly zero. Seeds bound
  optimizer noise only, not window sampling.

## Recommendation
- Do **not** invest further in fundamentals *data quality for the model* on this
  evidence; the marginal selection value is below the practical-null margin. (The
  fundamentals freshness/integrity gates already shipped — #143/#144/#400 — are
  still worth keeping as cheap correctness guards, independent of feature value.)
- Before any decision to **retire** the fundamentals pipeline: rerun the C−B and
  A−D1 contrasts on the refreshed+sanitized panel (a data-build task), per rule #2.
- Sentiment / PEAD-SUE value is **unknown** until a panel with those columns is
  built — that data-build is the next prerequisite, not a model change.
- Net answer to "which data is truly valuable": on current evidence, **none of
  fundamentals / macro / analyst** clears the bar for *stock selection*. The model
  is ~entirely an alpha158 technical/price model; the honest lever remains
  calibration + cost-aware construction + an entry filter, not adding weak alpha.

Harness: `/tmp/abl58.py` (XGBoost, per-regime GMM-argmax split, 6 purged WF cuts,
60d embargo, placebo = label +60d). Results: `/tmp/abl58_results.parquet`.
