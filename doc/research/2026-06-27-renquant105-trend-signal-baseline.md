# renquant105 trend-signal baseline — model-vs-gate bottleneck

- **Date:** 2026-06-27 (run timestamp 2026-06-27 ~13:10 PDT)
- **Scope:** READ-ONLY measurement of where renquant105 stands on its real goal — catch
  MORE (recall) and MORE-ACCURATE (precision) multi-period TREND signals — and whether the
  bottleneck is the MODEL (weak signal) or the GATE (conviction gate kills recall).
- **Reproduce:** `scripts/research_trend_signal_baseline.py --runs-db <ledger> --json`
- **Provenance:** decision ledger `data/runs.alpaca.db` under
  `/Users/renhao/git/github/RenQuant` (size 90.6 MB, mtime 2026-06-26 14:07), opened
  `mode=ro`; the analysis ran against a `/tmp` copy of that file so the canonical path was
  never opened read-write. Forward returns from `ticker_forward_returns`; scores from
  `candidate_scores`; run metadata from `pipeline_runs`. No model was trained; no order was
  placed; no canonical path was written.

## Data sufficiency — measured FIRST (the headline)

The faithful, production-scorer cross-section is the **LIVE** ledger (`run_type='live'`, one
run per date, a single `mu` per ticker). Counts as found:

| run_type | distinct run_dates | joinable rows | clean single-run x-section |
|---|---|---|---|
| live | 32 (scored) / 50 (any) | ~9.4 k | yes (1 run/date, dmu == names) |
| sim  | 560 | ~197 k | NO (see below) |

**The SIM ledger is NOT a faithful per-name production-PatchTST history** and is reported as
reference only, never as a verdict basis:

- `model_type` and `active_scorer` are **NULL on every sim row** (226,955/226,955) — the sim
  ledger does not record which scorer produced the numbers.
- sim `raw_score` ranges to **+155 … +270** per date — PatchTST raw scores are intrinsically
  NEGATIVE (~−0.198 neutral; MEMORY: patchtst-scores-intrinsically-negative). These are not
  PatchTST-native outputs.
- a sim date carries **far more distinct `mu` values than tickers** (e.g. 170 distinct mu for
  35 names) — up to 76 sim run_ids per date contribute conflicting mu for the same name, so
  there is no single clean cross-section.

**LIVE realized-trend coverage by horizon** (rank-IC dates with ≥10 names, aged by trading
sessions):

| horizon | live aged dates | span | sufficient (≥30)? |
|---|---|---|---|
| fwd_5d  | 18 | 2026-04-23 … 2026-06-11 | no |
| fwd_10d | 18 | 2026-04-23 … 2026-06-11 | no |
| **fwd_20d (primary)** | **11** | 2026-04-23 … 2026-05-22 | **no** |
| fwd_60d | 0 | — | no |

**Verdict: data is INSUFFICIENT to faithfully measure the primary (fwd_20d / fwd_60d)
baseline on the production scorer.** The faithful live ledger only began ~2026-05-04 (the
#133 decision-ledger wiring), and a 20-session label needs 20 trading days to realize, so the
realized-trend window is ~5 weeks. The 11 fwd_20d dates also fall in a single ~4-week window
with heavily **overlapping** 20-session forward windows — effectively ~1–2 independent
observations, not 11. This is the documented "gate validation blocked by unwired ledger"
note closing as the ledger ages, not yet closed.

Per the study's hard rule, **no fabricated baseline and no unfaithful sim proxy is used for
the verdict.** The numbers below are reported as DIRECTIONAL-ONLY, with the live ones flagged
thin and the sim ones flagged not-validation-grade.

## Measured numbers (DIRECTIONAL — do not treat as validated)

### 1. Signal accuracy (precision lens) — rank-IC vs the 0.036 leakage floor

LIVE (faithful scorer, thin):

| horizon | mu rank-IC (IC_IR, n) | raw rank-IC | vs 0.036 floor |
|---|---|---|---|
| fwd_5d  | +0.017 (IR 0.09, 18d) | +0.012 | **below** floor |
| fwd_10d | +0.051 (IR 0.33, 18d) | +0.047 | just above |
| fwd_20d | +0.173 (IR 0.95, 11d) | +0.014 (8d) | above (mu); raw below |
| fwd_60d | n=0 | n=0 | — |

SIM (reference only, NOT validation-grade): mu-IC +0.09/+0.13/+0.15/+0.17 across
5/10/20/60d over ~423 dates — all "above floor" but on the unfaithful sim ledger the
validator's own docstring calls leakage-inflated in-sample; the existing
`validate_conviction_gate.py` reports the same +0.176 headline and it is ~100% sim-driven
(0 live dates have a realized fwd_60d).

Reading: the only short-horizon LIVE signal that is faithfully measurable (fwd_5d) sits AT or
BELOW the leakage floor; fwd_10d is barely above; the fwd_20d +0.173 is encouraging but rests
on ~1–2 effective independent observations and a `mu` cross-section that is dominated by
`panel_ltr_xgboost` (408 rows) with only 85 `hf_patchtst` rows in the entire live ledger — so
it is NOT a clean "PatchTST trend signal" number.

### 2/3. Trend recall & precision (primary fwd_20d, book=8, LIVE, 11d — directional)

- Real up-trends per date (top-decile positive fwd_20d): **mean 5.1 names**.
- **Recall** (real trends caught): model top-8 = **0.245**, top-quintile = **0.326**,
  gate-admitted set = **0.183**.
- **Precision** of the model top-8: **0.75** realized positive, **0.44** in the positive
  top-tercile. Gate-admitted precision: 0.61 positive / 0.39 top-tercile.

So the model's top names are reasonably *accurate* (75% up), but the ranking *catches* only
~25% of the day's real trends.

### 4. GATE impact and the KILLED-WINNER decomposition (the bottleneck answer)

Live conviction gate `(mu − mean(mu)) ≥ 0.03`, demean=True, over 32 live dates:

- mean **5.5 admits / 54 names** per date; **44% of dates admit 0 names**; the gate passes
  only **~15% of the mu>0 names**. This reproduces the documented near-zero-admit behaviour.

Killed-winner decomposition of lost real trends (fwd_20d, 11 aged dates, directional):

- **`missed_by_model` = 0.755** — 76% of real trends are ones the MODEL ranked OUTSIDE its
  top-8. The signal never surfaced them.
- **`killed_by_gate` = 0.209** — 21% of real trends are ones the model DID rank top-8 but the
  GATE then rejected.

→ **The MODEL is the dominant bottleneck (~3.6× the gate); the GATE is a real but secondary
drag.** Even a perfect, fully-open gate would recover only the ~21% of trends the model
already ranked high; the ~76% the model never ranks high are unreachable by gate redesign.

### 5. Staleness

LIVE fwd_20d per-date IC, older half vs recent half: **+0.244 → +0.113 (Δ −0.130)**. A
decaying direction consistent with the live model being frozen at its train-cutoff
(2024-11 weights / 2026-02-10 data; MEMORY: verify-freshness). The sample is far too thin
(5 vs 6 dates) to size the freshness lever with confidence, but the sign matches the
staleness hypothesis and is worth re-measuring once ≥30 aged dates accrue.

## VERDICT

**(a) Baseline recall & precision for multi-period trends (directional, thin live data):**
on the primary fwd_20d the model catches ~**25%** of the day's real up-trends in its top-8
(~33% in its top-quintile) and the names it does surface are ~**75%** correct on direction.
This is a precision-decent / recall-poor profile.

**(b) Bottleneck = MODEL (primary), GATE (secondary) — i.e. BOTH, MODEL-led.** The
killed-winner decomposition is decisive: **76% of lost trends are model-ranked-low
(model bottleneck) vs 21% gate-rejected-but-model-ranked-high (gate bottleneck)** — the model
is ~3.6× the larger leak. The gate is genuinely tight (0 admits 44% of days, ~15% of mu>0
names) and worth fixing, but opening it cannot recover the trends the model never ranks.

**(c) Staleness gap:** directionally present (recent IC ≈ half the older IC), consistent with
the stale train-cutoff, but the live sample is too thin to size the lever — re-measure when
the ledger ages.

**(d) Single highest-leverage move for "更多更准":** improve the MODEL's trend RANKING
(recall) — a fresher-data retrain aligned to the multi-day trend target — NOT a gate redesign
and NOT more orthogonal alpha. Rationale: 76% of the recall loss is the model failing to rank
real trends highly; gate redesign addresses at most the 21% slice. Concretely: (i) refresh
the training data past the 2026-02-10 vintage and retrain on a directional multi-day
(fwd_10/20d) trend label so the score is optimized for the recall objective; (ii) THEN
revisit the gate as a clear-but-smaller second lever. This is a research direction, not a
deployment decision — it needs the live ledger to first age past ≥30 fwd_20d dates
(~mid-Aug-2026) so the baseline and any retrain delta can be validated faithfully rather than
on the unfaithful sim proxy.

## Caveats / honesty ledger

- Every LIVE number rests on **8–18 dates inside a single ~5-week window** with overlapping
  forward windows → DIRECTIONAL, not significance-tested. Do not act on a sign alone.
- The live `mu` cross-section is **not pure PatchTST** (dominated by `panel_ltr_xgboost`;
  only 85 `hf_patchtst` rows ledger-wide), so "the model" here is the live scorer mix, not
  the documented PatchTST primary in isolation.
- The SIM ledger numbers are **reference only** (NULL scorer, non-PatchTST raw, conflicting
  per-name mu) and are excluded from the verdict.
- UNBLOCK to a validated baseline: let the live ledger age to ≥30 fwd_20d dates, and/or wire
  faithful per-name PatchTST score history with scorer provenance (#133 follow-through), then
  re-run this script.
