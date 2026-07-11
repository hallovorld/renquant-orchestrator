# META score attribution 2026-07-06..07-10 — why the model got MORE bearish as META rallied +11.5%

**Question (operator):** "为什么 META 涨得这么好而模型更加看空了——这是根本问题." Live XGB panel: META raw
−0.047 → −0.176, 60d mu 0.019 → 0.006 across 2026-07-06..07-10 while META rallied +11.5%
($600.29 → $669.21). Learned anti-momentum view, or feature/pipeline artifact?

## Verdict (bottom line first)

**LEARNED model behavior — a specific, named mechanism — not a serving-feed artifact.**
One feature, **STD60** (= `rolling_std(close-level, 60d) / current_close`, qlib alpha158),
explains **74%** of META's raw-score decline. Because the *current close is the
denominator*, an orderly +11.5% rally mechanically deflates STD60 even when true return
volatility is flat-to-up. META's STD60 slid from just-above to just-below the training
mean (z +0.090 → −0.044), crossing **29 learned split thresholds** clustered exactly
there, where the model's learned response is steepest. The model has learned
"price low/mid relative to its own 60d dispersion ⇒ buy; price at the top of a calm
range ⇒ fade" — a **rebound / long-price-dispersion tilt**, not literal anti-momentum
(it simultaneously top-ranks FTNT, up +98% over 60d, *because* FTNT's dispersion is huge).
The feature was computed exactly as at training time — so this is the model's genuine
view; whether that view has *edge* in BULL_CALM is separately known to be unproven
(disclosed BULL_CALM real IC ≈ +0.0149, placebo > real, operator-override manifest).

Two real but **non-driving** artifacts were found and are flagged below (fundamentals
coverage; universe-composition swing 41→88 names).

## Evidence base — reproduction first [VERIFIED]

- **Model identity:** all three buy runs (07-06 `ebb9c2ca`, 07-07 `dc2a3247`, 07-10
  `6f9d5284`) stamped panel sha256 `5211f6be…`, which byte-matches the artifact on disk
  (`backtesting/renquant_104/artifacts/prod/panel-ltr.alpha158_fund.json`,
  trained_date 2026-07-06) **and** its weekly_rollback copies of 07-09/07-10/07-11 —
  the model was byte-stable across the whole window. The intra-week decline is therefore
  **same-model, feature-driven**. (`shasum` verified; run bundles from
  `data/runs.alpaca.db::pipeline_runs.run_bundle_json`.)
- **Score reproduction:** rebuilt the serving rows offline exactly per
  `kernel/panel_pipeline/job_panel_scoring.py::ApplyScoresTask` (alpha158 online from the
  `data/ohlcv/{T}/1d.parquet` cache + 5 fund from `sec_fundamentals_daily.parquet` as-of +
  PEAD/SUE from `earnings_surprise/` + sentiment zeroed under the BULL_CALM trained-zeroing
  gate + artifact clip/global-z transform), then scored with the pinned booster:
  per-day corr vs recorded `score_distribution.raw_panel` = **0.983 / 0.983 / 0.984**
  (mean |diff| ≈ 0.025, a stable per-name offset — OHLCV-cache re-adjustment +
  context-set approximation). META's recorded Δ(07-06→07-10) = −0.130; reproduced
  Δ = −0.124 (95%). Attribution of the *delta* is therefore trustworthy.

### Recorded numbers (runs DB, live runs)

| session | raw_panel | rank_score | mu (=expected_return, 60d) | universe n | panel mean raw | panel mean mu |
|---|---|---|---|---|---|---|
| 07-02 (old model, trained 05-18) | +0.060 | 0.568 | 0.0297 | 88 | −0.057 | 0.0198 |
| 07-06 (new model, trained 07-06) | −0.047 | 0.541 | 0.0192 | 41 | −0.118 | 0.0121 |
| 07-07 | −0.060 | 0.538 | 0.0179 | 40 | −0.130 | 0.0109 |
| 07-10 | −0.176 | 0.505 | 0.0064 | 88 | −0.211 | 0.0030 |

Note the week actually contains **two separate legs**: 07-02→07-06 is dominated by the
**weekly model swap** (scoring 07-02's features with the *new* booster gives META +0.020
vs old-model recorded +0.060, and panel mean −0.173 vs −0.057; pred corr between the two
models is only 0.39). The operator's cited window 07-06→07-10 is same-model and is what
the rest of this doc attributes.

## 1. Per-day SHAP attribution (xgboost `pred_contribs`) — top movers 07-06 → 07-10

META total Δpred = **−0.124**. Top |Δcontribution|:

| feature | Δcontrib | META raw value 07-06 → 07-10 | note |
|---|---|---|---|
| **STD60** | **−0.0912** | 0.0618 → 0.0555 | 74% of the decline; see mechanism |
| CORD60 | −0.0088 | +0.037 → +0.114 | 60d corr(price-chg rank, volume-chg rank) rose as the rally ran on volume |
| KLEN | −0.0083 | 0.0367 → 0.0300 | daily candle range shrank (calm tape) |
| gross_profitability | −0.0067 | 0.0811 → 0.0811 (imputed median) | median drift only — see §3 |
| STD30 / MIN60 / MIN10 | +0.006 / +0.0055 / +0.0050 | — | small offsets the other way |

By family: STD −0.083, CORD −0.013, FUND −0.010, KLEN −0.008, PEAD −0.005; MIN +0.010.
Momentum-direction features (ROC*) contributed ≈ nothing — META's ROC60 ≈ 0.99–1.02
(60d round-trip: May drawdown + recovery), so the model never even saw META as a
"spike" on the momentum axis. **The fade is priced off dispersion-vs-price, not momentum.**

### The STD60 mechanism, proven three ways

1. **Definition** (`kernel/panel_pipeline/alpha158_features.py:140`):
   `STD{n} = win_close.std(ddof=1) / close_today`. The rally inflates the denominator:
   META close +11.5% while trailing 60d price dispersion was roughly flat → STD60
   −10.2% (0.0618 → 0.0555). Session trace: 0.0673 (06-26) → 0.0618 (07-06) → 0.0555 (07-10).
2. **Split census:** STD60 carries 117 splits / 3.25% of total gain (STD30 4.14%,
   rank #1-2 by gain family). Between META's two z-values (+0.090 → −0.044, artifact
   train mean 0.0576/std 0.0474) the booster has **29 split thresholds** (clusters at
   z ≈ 0.067 and 0.043) — META fell through the steepest part of the learned response.
3. **Partial-dependence sweep** (META's actual 07-10 row, STD60 swept):
   raw 0.044 → pred −0.256 | 0.0557 → **−0.148** | 0.0614 → **−0.036** | 0.090 → +0.029 |
   0.150 → +0.038. The single-feature sweep reproduces the whole recorded decline;
   monotone-increasing in dispersion.

## 2. Panel-wide vs META-specific decomposition

Common-set (37 names scored on both 07-06 and 07-10, recorded values):

- Panel mean raw: −0.126 → −0.169 (**Δ −0.043**); META raw Δ **−0.130**
  → **33% common / 67% idiosyncratic.** The common leg is the *same* STD60/KLEN
  mechanism panel-wide (mean STD60 0.0686 → 0.0666; SHAP common-mean Δ: STD60 −0.0234 of
  −0.0363): a market-wide low-vol melt-up compresses price-normalized dispersion for
  everyone. The idiosyncratic leg is META's own threshold crossing (idio STD60 −0.068).
- mu: panel mean 0.0113 → 0.0071; META 0.0192 → 0.0064; **META demeaned mu
  +0.0079 → −0.0007** — relative to stable peers META went from mildly-above-consensus
  to exactly-consensus.
- **Demean config [VERIFIED]:** `demean_cross_sectional: false` in the pinned
  strategy-104 config (pin `0e5d9891`) *and* the live copy — the 2026-06-25 monitored
  exception is **no longer active**; recorded mu is the raw calibrated value. (Memory
  note "demean enabled" is stale and should be corrected.)
- **Composition caveat:** vs each day's *full* universe META's percentile was ~stable
  (58.5% → 58.0%) — but the 07-10 universe re-admitted 47 weaker names after the
  admission-freshness outage (41 → 88), so full-universe percentile understates META's
  true relative slide; the common-set numbers above are the honest comparison.

## 3. Fundamentals freshness (the prime suspect) — CLEARED as driver, but a real coverage bug

- **The serving-axis clip bug (base-data #26 / pipeline #151) is fixed AND the feed is
  rebuilt [VERIFIED]:** `data/sec_fundamentals_daily.parquet` axis extends to
  **2026-07-10** (= last session; file rebuilt daily, mtime 07-11 04:06). Not the old
  ~88d-behind clip.
- **BUT META has never had finite `earnings_yield` / `book_to_price` /
  `gross_profitability` in this feed** (0 finite rows ever). Universe-wide on 07-10:
  only **67 / 70 / 317 of 826** tickers have finite ey / b2p / gp. The serving path
  imputes the **cross-sectional median** (ey 0.0079, b2p 0.119, gp 0.081 — stable all
  week), so the model is **valuation-blind on META**: its "fundamental" features never
  see META's actual earnings power, and a rising price cannot inflate an
  expensiveness feature that is a constant median. `roe` (0.1099) and `asset_growth`
  (0.4105) are real, from fiscal 2026-03-31, available-at 2026-05-15 (normal filing-lag
  as-of logic) — constant across the week.
- Net FUND contribution to META's weekly Δ: **−0.010 of −0.124 (8%)** — not the driver.
- **Hypothesis "stale fundamentals + rising price → mechanical bearish drift" is
  REFUTED for this week.** The real (secondary) defect is *coverage*, not staleness:
  fix owner **renquant-base-data** (SEC fundamentals ratio builder — ey/b2p/gp require
  price×shares alignment that is evidently failing for ~90% of the universe, including
  META), plus a serving-side feature-health metric (imputed-share per fund column is
  already logged as real=/imputed= but not alerted on).

## 4. Controls — is "fade the rally" universal?

Same-model Δpred 07-06 → 07-10 (reproduced frame) while all of these rallied:

| name | pred 07-06 → 07-10 | biggest Δcontrib | reading |
|---|---|---|---|
| FTNT (+98%/60d, STD60 0.176) | +0.262 → +0.250 | STD60 level contrib **+0.107** | model's top pick BECAUSE dispersion is huge — chases this "spike" |
| APH | +0.065 → +0.076 | KLEN +0.010 | admitted 07-10; rose |
| NFLX (STD60 0.112) | +0.054 → +0.029 | SUMP60 −0.012 | stays positive on the dispersion axis |
| MSFT | −0.090 → −0.095 | STD60 −0.035 | same penalty as META |
| NVDA | −0.163 → −0.171 | STD60 −0.060 | same |
| AAPL | −0.151 → −0.207 | STD60 −0.046 | same |

So: **not** "fade every spike" — the model fades *low-dispersion-at-highs* names
(META and every calm mega-cap) and rewards *high-dispersion* names regardless of
direction (FTNT after doubling, NFLX). The learned axis is a rebound/long-dispersion
tilt — exactly the "vol-tilted ranker" behavior documented in the panel-exit and OXY
forensics, and consistent with training: aggregate real IC +0.054 is BEAR-inflated
(dispersion-buying pays in crash-rebounds), while in BULL_CALM the disclosed placebo-clean
IC is ≈ +0.0149 (no validated edge for this fade in the current regime).

## 5. Judgment and what would change it

- **Verdict: LEARNED.** The serving pipeline computed the features exactly as trained
  (reproduction corr 0.98+); no stale-feed, no wrong-model, no demean effect. The score
  decline is the model's genuine learned response — dominated by a single
  price-normalized dispersion feature whose denominator is the rally itself.
- **The learned view is economically fragile in this regime.** STD60's price-in-denominator
  construction makes "got more expensive vs its own recent range" and "got calmer"
  indistinguishable; in a BULL_CALM melt-up it fades exactly the strong-consensus quality
  rallies (META: street Buy, ~$834 target). Model is primary per the 2026-06-23 operator
  override — this doc changes no gate.
- **Forward validation (owner: orchestrator decision-ledger #133/#195 stream):** track
  realized fwd-60d excess of (a) low-STD60 faded names (META 07-06/07-10 marks) vs
  (b) high-STD60 admitted names (FTNT/APH/ZM/NFLX 07-10 cohort). The model's implied
  call is that (b) outperforms (a) by the mu gap (~+3.9% at 60d for FTNT vs META).
  If (a) persistently outperforms, the STD60 tilt is a training-regime artifact →
  candidate fixes are model-side (feature neutralization or regime admission), NOT
  runtime gates.
- **Artifact fixes recommended (secondary, non-driving):**
  1. base-data: repair ey/b2p/gp coverage in `sec_fundamentals_daily.parquet`
     (67-317/826 finite; META never finite) + alert on per-column imputed-share.
  2. orchestrator monitor: alert on scored-universe size swings (41 → 88 in one session
     silently reshapes every cross-sectional statistic downstream).

## Reproduction inventory (read-only; scratchpad only)

- Inputs: pinned strategy-104 `0e5d9891` (fresh clone), live artifact + rollback copies
  (sha-verified), `data/runs.alpaca.db` (copied before opening), `data/ohlcv/`,
  `data/sec_fundamentals_daily.parquet`, `data/earnings_surprise/`.
- Method: standalone loads of `alpha158_features.py` / `feature_transform.py`
  (umbrella kernel, read-only), booster from `booster_raw_json`, xgboost 2.1.4
  `pred_contribs=True`; helpers re-implemented line-for-line from
  `kernel/panel_pipeline/runtime_features.py`.
- No production path written; no git in the live tree or primary checkouts
  (isolated worktree); no network model calls; local compute only.
