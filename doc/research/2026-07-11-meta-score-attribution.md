# META score attribution 2026-07-06..07-10 — why the model got MORE bearish as META rallied +11.5%

**Question (operator):** "为什么 META 涨得这么好而模型更加看空了——这是根本问题." Live XGB panel: META raw
−0.047 → −0.176, 60d mu 0.019 → 0.006 across 2026-07-06..07-10 while META rallied +11.5%
($600.29 → $669.21). Learned anti-momentum view, or feature/pipeline artifact?

## Corrigendum (post-Codex-review, this section supersedes the verdict below)

Codex reviewed this PR (orchestrator #475, CHANGES_REQUESTED) and found the verdict
below overclaimed causal and economic conclusions that the underlying evidence does
not support: an off-manifold single-row PDP sweep, a non-causal SHAP decomposition,
and a reproduction with a material error bound were being read as proof of a "LEARNED
… dispersion tilt" and a "74% root cause." That review is accepted as correct. The
**defensible conclusion, and the only one this document now makes**, is:

> Same-model, approximate replay suggests sensitivity to the STD60 feature on this
> path. This does **not** establish a 74% root cause, an economic dispersion premium,
> or a reason to change the strategy.

Everything below this point is retained as **evidence of what was actually computed**
(reproduction numbers, SHAP tables, split census, PDP sweep, controls) — read it as
model-local, same-path observation, not as a validated causal or economic finding. The
stronger language originally used throughout ("LEARNED", "proven", "CLEARED",
"REFUTED", "genuine view", "economically fragile") has been walked back in place
below. See **"Known Limitations / Not Yet Established"** near the end for the full,
itemized list of what remains open and who owns closing each item (none of it is
orchestrator-repo scope). The serving-run inputs/outputs referenced here are sealed
content-addressed in `renquant-artifacts` — see the **Evidence sealing** note at the
end of this document for the link.

## STD60 confound: price-level coefficient of variation, not return volatility (UNRESOLVED)

Flagged by review and not yet resolved by anything in this document: **STD60 =
`std(trailing 60d close LEVELS, ddof=1) / current close` is a coefficient of variation
of the price level, not a measure of return volatility** in the conventional finance
sense (volatility is standardly computed from returns — e.g. the standard deviation of
daily log-returns; see the San Francisco Fed's explainer on stock market volatility:
https://www.frbsf.org/research-and-insights/publications/economic-letter/2002/10/stock-market-volatility/).

Consequence: if a name's realized *return* volatility is completely unchanged, but its
price *level* rises smoothly by +11.5% over 60 days, STD60 falls mechanically through
the denominator alone — no change in the numerator (dispersion of returns) is required
for this to happen. Nothing in this document currently distinguishes:

- (i) "the model has learned a genuine dispersion/rebound premium" — i.e. it is
  pricing something about *return risk*, from
- (ii) "the model is reacting to a **price-position confound** baked into the
  feature's own definition" — i.e. it would produce the identical score move for
  *any* calm, monotonic rally, regardless of whether realized return volatility
  changed at all.

Every SHAP/split-census/PDP result below is consistent with either (i) or (ii); none
of it rules out (ii). Distinguishing them requires re-running the identical
attribution with a genuine return-volatility feature (e.g. std of daily log returns
over the same trailing window) substituted for STD60 — a frozen-vintage ablation that
is model/pipeline work and has **not** been performed here (Known Limitations, item b).

## What the evidence base actually shows (reproduction, with its real error bound)

- **Model identity [VERIFIED]:** all three buy runs (07-06 `ebb9c2ca`, 07-07
  `dc2a3247`, 07-10 `6f9d5284`) stamped panel sha256 `5211f6be…`, which byte-matches
  the artifact on disk (`backtesting/renquant_104/artifacts/prod/panel-ltr.alpha158_fund.json`,
  trained_date 2026-07-06) **and** its weekly_rollback copies of 07-09/07-10/07-11 —
  the model was byte-stable across the whole window. The intra-week decline is
  therefore same-model. (`shasum` verified; run bundles from
  `data/runs.alpaca.db::pipeline_runs.run_bundle_json`.)
- **Score reproduction — APPROXIMATE, not exact:** rebuilt the serving rows offline
  per `kernel/panel_pipeline/job_panel_scoring.py::ApplyScoresTask` (alpha158 online
  from the `data/ohlcv/{T}/1d.parquet` cache + 5 fund from `sec_fundamentals_daily.parquet`
  as-of + PEAD/SUE from `earnings_surprise/` + sentiment zeroed under the BULL_CALM
  trained-zeroing gate + artifact clip/global-z transform), scored with the pinned
  booster. Measured directly from the reproduction run (`repro_summary.parquet`,
  sealed — see Evidence sealing):

  | day | n scored / n recorded | corr | mean\|diff\| | **max\|diff\|** |
  |---|---|---|---|---|
  | 07-06 | 44 / 41 | 0.9826 | 0.0246 | **0.1472** |
  | 07-07 | 43 / 40 | 0.9826 | 0.0253 | **0.1438** |
  | 07-10 | 88 / 88 | 0.9841 | 0.0251 | **0.1869** |

  META's recorded Δ(07-06→07-10) = −0.130; reproduced Δ = −0.124 (95% of the
  recorded move).
  - **This error bound is material, not incidental — and worse than the mean alone
    suggests.** Mean |diff| ≈0.025 against META's own 0.124 move is ~20% of the
    signal being attributed; but the **max** |diff| on some other name each day
    (0.144–0.187) is larger than META's *entire* weekly move. That is large enough
    to flip rank order or gate-decision crossings on other names/sessions even
    where it happens not to on META specifically. Day-level correlation
    (0.983–0.984) is an aggregate similarity statistic; it does **not** validate
    row-level (single-name) causal attribution — this max-error number is exactly
    the kind of control Codex's review asked this document to surface rather than
    omit. Treat the SHAP/PDP numbers below as indicative of what a *reasonably
    close* replay of the serving path shows, not as a sealed, exact reproduction.
    See Known Limitations (a) for what remains open (rank-order agreement,
    gate-decision agreement, SHAP additivity residual — none of which is computed
    here) and the **Evidence sealing** note for what has actually been committed to
    renquant-artifacts from this run.

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

**Read this section as model-representation attribution, not a causal economic test.**
SHAP/gain-based credit is not identified when predictors are correlated or jointly
generated (as the technical-feature family here is), so the percentages below describe
what the fitted model's internal representation assigns to each feature on this
approximate replay — not a proven, isolated economic driver (Ma & Tourani, 2020:
https://proceedings.mlr.press/v127/ma20a.html; Known Limitations, item d).

META total Δpred (reproduced) = **−0.124**. Top |Δcontribution|:

| feature | Δcontrib | META raw value 07-06 → 07-10 | note |
|---|---|---|---|
| **STD60** | **−0.0912** | 0.0618 → 0.0555 | largest single-feature contribution in this decomposition (~74% of the reproduced decline); see mechanism below and the confound caveat above |
| CORD60 | −0.0088 | +0.037 → +0.114 | 60d corr(price-chg rank, volume-chg rank) rose as the rally ran on volume |
| KLEN | −0.0083 | 0.0367 → 0.0300 | daily candle range shrank (calm tape) |
| gross_profitability | −0.0067 | 0.0811 → 0.0811 (imputed median) | median drift only — see §3 |
| STD30 / MIN60 / MIN10 | +0.006 / +0.0055 / +0.0050 | — | small offsets the other way |

By family: STD −0.083, CORD −0.013, FUND −0.010, KLEN −0.008, PEAD −0.005; MIN +0.010.
Momentum-direction features (ROC*) contributed close to nothing in this decomposition —
META's ROC60 ≈ 0.99–1.02 (60d round-trip: May drawdown + recovery), so on this path the
model's SHAP credit for a "spike" on the momentum axis was near zero. **On this
attribution, the fade is priced off dispersion-vs-price features, not momentum
features** — stated as a description of this SHAP decomposition, not a causal claim
about what "actually" drove the score.

### The STD60 sensitivity, shown three ways (none of these is a causal proof)

1. **Definition** (`kernel/panel_pipeline/alpha158_features.py:140`):
   `STD{n} = win_close.std(ddof=1) / close_today`. The rally inflates the denominator:
   META close +11.5% while trailing 60d price dispersion was roughly flat → STD60
   −10.2% (0.0618 → 0.0555). Session trace: 0.0673 (06-26) → 0.0618 (07-06) → 0.0555
   (07-10). This is exactly the price-level confound described above — the fact that
   the ratio fell is not, by itself, evidence of a genuine dispersion signal (see
   confound section).
2. **Split census (descriptive only):** STD60 carries 117 splits / 3.25% of total gain
   (STD30 4.14%, rank #1-2 by gain family). Between META's two z-values (+0.090 →
   −0.044, artifact train mean 0.0576/std 0.0474) the booster has **29 split
   thresholds** (clusters at z ≈ 0.067 and 0.043) that META's z-value crossed. This
   describes where the fitted tree ensemble places splits; it is not itself a test of
   whether crossing those splits reflects a real economic signal.
3. **Partial-dependence sweep — single-row, off-manifold, suggestive only:**
   sweeping STD60 on META's actual 07-10 row while holding every other feature fixed
   (ROC*, MIN*, KLEN, CORD60, and the rest of the jointly-generated technical family)
   gives raw 0.044 → pred −0.256 | 0.0557 → −0.148 | 0.0614 → −0.036 | 0.090 → +0.029 |
   0.150 → +0.038. The single-feature sweep reproduces the shape of the recorded
   decline, monotone-increasing in dispersion — **but this holds correlated features
   fixed at combinations the model may never have seen jointly with each swept STD60
   value, which is a known failure mode of PDP under correlated predictors** (Apley &
   Zhu, 2020: https://doi.org/10.1111/rssb.12377). This is presented as a suggestive,
   same-row sensitivity check, not proof that STD60 in isolation drives the score in
   any counterfactual world the model would actually encounter (Known Limitations,
   item c).

## 2. Panel-wide vs META-specific decomposition

**Same caveat as §1 applies throughout this section:** SHAP-based common/idiosyncratic
splits describe the fitted model's representation on this approximate replay, not a
causal decomposition of "why" the market moved.

Common-set (37 names scored on both 07-06 and 07-10, recorded values):

- Panel mean raw: −0.126 → −0.169 (**Δ −0.043**); META raw Δ **−0.130**
  → in this decomposition, 33% is common to the panel / 67% is META-idiosyncratic.
  The common leg tracks the same STD60/KLEN features panel-wide (mean STD60 0.0686 →
  0.0666; SHAP common-mean Δ: STD60 −0.0234 of −0.0363) — consistent with (but not
  proof of) a market-wide low-vol melt-up compressing price-normalized dispersion for
  everyone. The idiosyncratic leg is META's own threshold crossing (idio STD60
  −0.068).
- mu: panel mean 0.0113 → 0.0071; META 0.0192 → 0.0064; META demeaned mu
  +0.0079 → −0.0007 — relative to stable peers META went from mildly-above-consensus
  to exactly-consensus in this metric.
- **Demean config [VERIFIED]:** `demean_cross_sectional: false` in the pinned
  strategy-104 config (pin `0e5d9891`) *and* the live copy — the 2026-06-25 monitored
  exception is **no longer active**; recorded mu is the raw calibrated value. (Memory
  note "demean enabled" is stale and should be corrected.)
- **Composition caveat:** vs each day's *full* universe META's percentile was ~stable
  (58.5% → 58.0%) — but the 07-10 universe re-admitted 47 weaker names after the
  admission-freshness outage (41 → 88), so full-universe percentile understates META's
  relative slide on the common-set basis; the common-set numbers above are the more
  comparable measure, not a fully controlled one.

## 3. Fundamentals coverage — small measured weekly delta; NOT established as non-driving

- **The serving-axis clip bug (base-data #26 / pipeline #151) is fixed AND the feed is
  rebuilt [VERIFIED]:** `data/sec_fundamentals_daily.parquet` axis extends to
  **2026-07-10** (= last session; file rebuilt daily, mtime 07-11 04:06) — not the old
  ~88d-behind clip.
- **BUT META has never had finite `earnings_yield` / `book_to_price` /
  `gross_profitability` in this feed** (0 finite rows ever, in the data examined).
  Universe-wide on 07-10: only **67 / 70 / 317 of 826** tickers have finite ey / b2p /
  gp. The serving path imputes the **cross-sectional median** (ey 0.0079, b2p 0.119,
  gp 0.081 — stable all week). `roe` (0.1099) and `asset_growth` (0.4105) are real,
  from fiscal 2026-03-31, available-at 2026-05-15 (normal filing-lag as-of logic) —
  constant across the week.
- Net FUND contribution to META's weekly Δ, in this SHAP decomposition: **−0.010 of
  −0.124 (8%)**.
- **This small weekly delta does NOT clear the coverage bug as non-driving.** A
  near-constant, median-imputed factor can have a small week-over-week *delta* while
  still materially determining the score **level**, **rank**, or a **threshold
  crossing** — none of which this document has tested. What would actually test this:
  score META with valid as-of fundamentals vs the imputation path, compare
  observed-vs-imputed names on matched sector/size/date samples, and check whether
  missingness itself is encoded (vs silently hidden by the median fill). None of that
  has been done here (Known Limitations, item e). The original framing ("hypothesis
  REFUTED", "CLEARED as driver") is walked back: what's actually shown is that the
  measured weekly *delta* attributable to FUND is small — the level/rank question is
  open.
- The real, separately-flagged defect remains a **coverage** bug (not a staleness
  bug): fix owner **renquant-base-data** (SEC fundamentals ratio builder — ey/b2p/gp
  require price×shares alignment that is evidently failing for ~90% of the universe,
  including META), plus a serving-side feature-health metric (imputed-share per fund
  column is already logged as real=/imputed= but not alerted on).

## 4. Controls — same-model comparison across a small, hand-picked set of names

This is a **descriptive comparison on six names**, not a validated test that the model
implements a coherent "reward high dispersion" rule outside this sample.

Same-model Δpred 07-06 → 07-10 (reproduced frame) while all of these rallied:

| name | pred 07-06 → 07-10 | biggest Δcontrib | reading |
|---|---|---|---|
| FTNT (+98%/60d, STD60 0.176) | +0.262 → +0.250 | STD60 level contrib **+0.107** | this decomposition attributes the top-pick score to STD60 being large |
| APH | +0.065 → +0.076 | KLEN +0.010 | admitted 07-10; rose |
| NFLX (STD60 0.112) | +0.054 → +0.029 | SUMP60 −0.012 | stays positive on this decomposition's dispersion axis |
| MSFT | −0.090 → −0.095 | STD60 −0.035 | same STD60-attributed penalty as META |
| NVDA | −0.163 → −0.171 | STD60 −0.060 | same |
| AAPL | −0.151 → −0.207 | STD60 −0.046 | same |

On this small sample, the pattern in the decomposition is **not** "fade every spike" —
STD60 is attributed as a penalty for low-dispersion-at-highs names (META and the other
calm mega-caps) and a reward for high-dispersion names regardless of direction (FTNT
after doubling, NFLX). Whether this is a genuine, generalizable "rebound / long-
dispersion" rule the model has learned, or an artifact of the STD60 price-position
confound applied consistently across names, is **not distinguished** by this table —
see the confound section above. It is also consistent with what training-time
aggregate metrics show: aggregate real IC +0.054 is reported as BEAR-inflated, while
the disclosed placebo-clean IC in BULL_CALM is ≈ +0.0149 — i.e. no validated edge is
claimed for this regime independent of this attribution exercise.

## 5. What this document actually establishes, and what it does not

- **Established:** the live XGB panel scored META progressively lower each session
  07-06→07-10 while META rallied +11.5%, on a byte-stable model. An approximate
  offline replay (material error bound — see above) attributes most of the
  reproduced score delta to the STD60 feature via SHAP contribution and a PDP
  sensitivity sweep on META's own row.
- **Not established:** that this is a "LEARNED" economically-meaningful dispersion or
  rebound premium; that STD60 is a genuine risk signal rather than (or in addition
  to) a price-position confound; that the fundamentals coverage bug is cleared as a
  non-driver of score level/rank; or that any of this should change the strategy,
  the gate, or the model. See **Known Limitations / Not Yet Established** below for
  the itemized list.
- **If** the STD60 sensitivity does reflect a genuine learned rule (not established),
  its price-in-denominator construction would make "got more expensive vs its own
  recent range" and "got calmer" hard to distinguish — which, in a BULL_CALM
  melt-up, could mean fading strong-consensus quality rallies (META: street Buy,
  ~$834 target) for reasons that are partly or wholly a feature-definition artifact
  rather than a priced risk. This is a hypothesis raised by the data, not a finding.
  Model is primary per the 2026-06-23 operator override; this document changes no
  gate.
- **Proposed (not run) forward check:** compare realized fwd-60d excess of (a)
  low-STD60 faded names (META 07-06/07-10 marks) vs (b) high-STD60 admitted names
  (FTNT/APH/ZM/NFLX 07-10 cohort). **This comparison as stated is selection-confounded
  and unregistered** — it conditions on the model's own admission/fade decisions and
  mixes sector, size, trend, liquidity, and mu, so a result either way would not be
  interpretable as a clean test of the STD60 hypothesis. A valid version would need:
  all upstream-eligible candidates (not just admitted/faded ones), lagged signals,
  stratification by sector/size/regime on STD quantiles, purged time blocks, matured
  60-trading-day labels, block-bootstrap confidence intervals, turnover/cost
  accounting, and multiplicity control. None of that is attempted here; it is listed
  as a design sketch for a future decision-ledger workstream (Known Limitations,
  item f), not as a completed or pre-registered analysis.
- **Artifact fixes recommended (secondary, unchanged by this review):**
  1. base-data: repair ey/b2p/gp coverage in `sec_fundamentals_daily.parquet`
     (67-317/826 finite; META never finite) + alert on per-column imputed-share.
  2. orchestrator monitor: alert on scored-universe size swings (41 → 88 in one
     session silently reshapes every cross-sectional statistic downstream).

## Known Limitations / Not Yet Established (Codex review, orchestrator PR #475)

This document's evidence supports only the following defensible conclusion:

> Same-model, approximate replay suggests sensitivity to the STD60 feature on this
> path. It does not establish a 74% root cause, an economic dispersion premium, or a
> reason to change the strategy.

The six items below are open. Each requires model/pipeline/base-data work outside
this repository's scope; **this PR does not attempt that remediation** — it only
corrects this document's claims to match its current evidence and seals what was
actually computed (see Evidence sealing, below).

**(a) Reproduction parity is not sealed to a rigorous error bound — partially closed,
mostly still open.** Mean absolute raw-score error ≈0.025 vs META's 0.124 recorded
move is material; the **max** absolute error per day (0.144–0.187, now measured and
sealed — see the reproduction table above) is larger than META's entire weekly move,
confirming this can change rank order or gate-decision crossings on other
names/sessions even where it doesn't change this one. Day-level correlation
(0.983–0.984) validates aggregate similarity, not row-level attribution. What's now
sealed in renquant-artifacts: the panel artifact's full sha256 fingerprint, the
pinned strategy-104 config commit (universe/as-of snapshot), and per-day
corr/mean-error/max-error. What's **still open**: rank-order agreement across the
full universe, gate-decision agreement (would this replay have flipped any
veto/admission decision), a SHAP additivity residual check, and an independent
transform fingerprint distinct from the panel artifact (none exists as a separate
object in the current serving path — see Evidence sealing). The current replay uses
OHLCV re-adjustment and context-set approximation, not an exact serving-path replay
— it should not be called a trustworthy row-level attribution until those remaining
controls exist.

**(b) STD60 is a price-level coefficient of variation, not return volatility.** See
the dedicated caveat section above. A rising terminal price mechanically shrinks
this ratio even when return-risk is flat, and this document has not distinguished a
genuine dispersion/rebound effect from that mechanical confound. Closing this
requires a frozen-vintage ablation substituting a genuine return-volatility feature
(e.g. std of daily log returns) for STD60 and re-running the same attribution.

**(c) The PDP sweep is a single-row, off-manifold approximation.** It varies STD60
while holding ROC, MIN, KLEN, CORD60, and the rest of the jointly-generated technical
family fixed at META's actual 07-10 values — combinations the model may never have
seen jointly (Apley & Zhu, 2020: https://doi.org/10.1111/rssb.12377). Closing this
requires conditional ALE / conditional SHAP, feature-group attribution for the
correlated technical family, local support counts around each claimed split region,
and a path-consistent rescore that recomputes every dependent feature from a valid
counterfactual price path — none of which is done here.

**(d) SHAP and split-count evidence explain the model's representation, not causal
economic contribution.** Feature correlation and interaction make the 74%-style
credit non-identifiable (Ma & Tourani, 2020:
https://proceedings.mlr.press/v127/ma20a.html). Every causal-sounding statement
elsewhere in this document should be read as model-local attribution unless a
conditional analysis (per item c) is run and survives.

**(e) The fundamentals conclusion is internally too strong.** A near-constant,
median-imputed factor can have a small weekly SHAP delta (−0.010) while still
materially determining the score level, rank, or threshold crossing. The 8%-of-Δ
figure does not clear the ey/b2p/gp coverage bug as non-driving. Needs: observed-
vs-imputed names matched on sector/size/date, META scored with valid as-of
fundamentals vs the imputation path, and a check on whether missingness itself is
encoded or silently hidden.

**(f) The proposed forward test is selection-confounded and unregistered.**
Comparing low-STD60 faded names to high-STD60 admitted names conditions on the
model's own selection and mixes sector, size, trend, liquidity, and mu. A valid
version needs a pre-registered walk-forward test over all upstream-eligible
candidates, lagged signals, stratified/matched STD quantiles within sector/size/
regime, purged time blocks, matured 60-trading-day labels, block-bootstrap
confidence intervals, turnover/cost impact, and multiplicity control — plus a
separate frozen-vintage ablation (return volatility in place of STD60, or removal
of the correlated technical group). This belongs to model/base-data/pipeline
experimentation, never a runtime gate tweak, and is a design sketch only here — not
executed, not pre-registered.

**Repository placement:** this orchestration research document is an acceptable
place for this write-up, but its immutable inputs/results must be (and now are, to
the extent they exist — see below) sealed in `renquant-artifacts`; feature
definition and ablation work is model/pipeline scope; the missing-fundamentals
coverage contract is `renquant-base-data` scope. **No umbrella/runtime
implementation is proposed or made by this PR** — this remains research- and
progress-doc only.

## Evidence sealing

The serving-run inputs and outputs this document's numbers are computed from are
sealed content-addressed in `renquant-artifacts`
(`registry/meta-score-attribution-20260711.json` +
`store/experiments/meta-score-attribution-20260711/`), following the same pattern as
the prior evidence bundles in that repo (#14/#15/#16). Sealed:

- the panel artifact's full sha256 fingerprint (`5211f6bebd90ca08…4c9cf`), computed
  read-only against the live production path (not copied — the artifact itself
  stays out of this store; only its hash and the pinned config commit are sealed as
  provenance);
- the pinned strategy-104 config commit (`0e5d989137b6…1ee4ce`) and the
  `demean_cross_sectional: false` setting read directly from it (universe/as-of
  snapshot);
- `reproduce_meta.py` (the exact reproduction method/script run);
- `booster.json` (the booster extracted from the pinned panel artifact for
  standalone `xgboost.Booster` scoring) and `recorded_scores.json` (the recorded
  live serving rows compared against);
- `repro_summary.parquet` (per-ticker, per-day predicted vs. recorded raw score and
  diff — the source of the corr/mean-error/max-error table above);
- `contribs_2026-07-06/07/10.parquet` (full per-ticker SHAP contribution matrices)
  and `features_raw_2026-07-06/07/10.parquet` (the exact as-of feature snapshot fed
  to the booster each day);
- `std60_sweep.csv` (the raw partial-dependence sweep output).

**Explicitly marked absent, not fabricated:** an independent transform fingerprint
distinct from the panel artifact (none exists as a separate object in the current
serving path); rank-order/gate-decision agreement between replay and live; a SHAP
additivity residual check; conditional ALE/conditional SHAP outputs; and any
pre-registered forward-test result (none of this analysis has been run). See the
`renquant-artifacts` PR linked from this PR's description for the exact manifest.

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
