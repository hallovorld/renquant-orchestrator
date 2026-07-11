# STD60 rule provenance — where "low STD60 ⇒ bearish" came from, and whether it was ever valid

**Question (operator, via #475):** "为什么模型会 short 它？这不对！" The live XGB panel fades quiet
mega-cap rallies via a learned low-STD60→bearish rule (74% of META's 07-06..07-10 score
decline — `doc/research/2026-07-11-meta-score-attribution.md`, PR #475). Where did this
rule come from in the training data, and was it ever valid out-of-sample? Is the model
rationally bearish, or structurally confused on this class of names?

## Verdict (bottom line first)

**First, the literal question: there was NO short — not a position, not an order, not an
intent [VERIFIED].** Current book = MU / GRMN / AVGO, all long; META absent. The trades
ledger contains only `buy`/`sell` actions ever; META's full history is 31 buys / 28 sells /
1 `sell_pending` (a long-exit attempt, 2026-06-02). `long_short.enabled = false` in the
pinned strategy-104 config (the Phase-2 scaffolding is dormant). "看空" this week =
raw panel score −0.176 → no-buy / low rank. Nothing was, or could have been, shorted.

**Root cause: the rule is corpus-rational but regime-confused, and the gate caught it
before it went live.** Three hypotheses survive, one is refuted:

| Hypothesis | Verdict | One-line evidence |
|---|---|---|
| H1 class confusion (quiet winners mislabeled as dead money) | **REFUTED** as stated | Low-STD60 rows are 66% *uptrend* names, and the uptrend/near-high subset had the *worst* forward returns in-corpus (−1.1%/60d excess vs +0.8% for far-from-high). The corpus genuinely taught "fade calm-at-highs". Reframe that survives: survivorship inflates the *other* end (42% of high-STD60 rows come from eventual ≥5x names; 0 delisted names in the panel). |
| H2 regime-specific pattern generalized | **SURVIVES — primary** | Feature IC: BEAR +0.150, BULL_VOLATILE +0.095, BULL_CALM +0.035 (hit 0.57); dead 2021/2022/2024 (−0.004..+0.005); **BULL_CALM 2026 in-corpus −0.088 (hit 0.15)**. The rule pays in crash-rebounds; it is absent-to-inverted in calm melt-ups — exactly this week's regime. |
| H3 feature mis-specification | **SURVIVES — the mechanism** | META 07-06→07-10: numerator (60d level-std) +0.1%, denominator (close) +11.5% ⇒ **101% of the STD60 decline is the denominator**. True risk *rose*: returns-vol60 +4.8% (z +0.60→+0.71, above panel mean all week). A returns-based vol feature moves the opposite way. |
| H4 governance (unvalidated model in primary) | **SURVIVES — terminal link** | The live booster **failed its own WF gate on exactly this failure mode** (BULL_CALM regime-IC FAIL, placebo-genuine −0.029; entry-rank monotonicity **inverted** in BULL_CALM: top-ranked +6.1% vs bottom-ranked +19.7%) and went live via `manual_override: true` (2026-07-06 freshness promote). The gate was right. |

**Chain:** qlib-STD60's price-in-denominator construction (H3) + a survivor-only,
rebound-rich training corpus (H1'/H2) → rank objective learns an *unconditional*
"fade calm-at-highs, chase dispersion" tilt → WF gate correctly fails it in BULL_CALM →
freshness-policy override puts it live anyway (H4) → an orderly +11.5% META rally
mechanically deflates STD60 through the split-threshold cluster and the model fades the
strongest-consensus name in the universe while its true risk rises.

## 0. Model identity and training window [VERIFIED]

- Live booster: `backtesting/renquant_104/artifacts/prod/panel-ltr.alpha158_fund.json`,
  `kind=panel_ltr_xgboost`, trained_date **2026-07-06**, train_run_id `240f9b27`
  (byte-stable across 07-06..07-11 per #475; `panel_scoring.kind=xgb` in the pinned config).
- Training corpus: `data/alpha158_291_fundamental_dataset.parquet` — row count matches the
  artifact `panel_shape` exactly (722,775 rows × 292 tickers × 2,580 dates), mtime = train date.
  **Window: 2016-01-04 → 2026-04-08**, label `fwd_60d_excess` (60-trading-day return minus
  SPY, then **cross-sectional z per date**; features global-z on train stats, clip ±5).
  The final fit uses the FULL panel (`renquant_model_gbdt/panel_trainer.py`; CV folds are
  diagnostic). So the model saw everything through 2026-04-08, incl. the 2026 melt-up's
  first months; genuine post-training OOS is only 2026-04-09 → now.
- Replication basis for this doc: raw STD60/labels recomputed from `data/ohlcv/{T}/1d.parquet`
  (STD60 replicates the corpus feature up to its global-z transform; Spearman-based results
  are invariant to the corpus's monotone z transforms). Regime labels:
  `renquant_common.hmm_regime_labels.compute_hmm_regime_labels` (v2026-05-31 detector, the
  gate's convention). All t-stats below are overlap-adjusted (n_eff = n_dates / horizon) —
  conservative, because 60d labels overlap.

## 1. H1 — what actually lives in low STD60, and what happened to it (train window)

Per-date STD60 quintiles, label = CS-z of fwd-60d excess (what the ranker optimized):

| STD60 quintile | mean label (z) | t_adj | mean raw fwd60 excess | n rows |
|---|---|---|---|---|
| Q1 (lowest) | **−0.089** | −2.7 | −0.5% | 145,816 |
| Q2 | −0.064 | −2.8 | | 143,746 |
| Q3 | −0.033 | −1.8 | | 143,929 |
| Q4 | +0.044 | +1.8 | | 143,746 |
| Q5 (highest) | **+0.142** | +3.0 | **+4.0%** (median +1.4% — heavy right skew) | 145,538 |

The corpus monotonically taught "low dispersion ⇒ below-consensus forward return". Now the
population and trend split inside Q1 — the H1 test:

- **Population: Q1 is NOT dead money.** 66.5% of Q1 rows have positive 120d trailing
  return; 37.2% are within 5% of their 52-week high; only 7.5% are ≥20% below it.
  Low-STD60 in this universe ≈ calm mega-caps and steady risers.
- **The uptrend subset was NOT the good subset:**

| Q1 cell | mean label (z) | mean raw fwd60 excess | t_adj (raw) | n rows |
|---|---|---|---|---|
| Q1 & up-120d | −0.087 | −0.56% | −0.9 | 96,906 |
| Q1 & down-120d | −0.110 | −1.01% | −1.3 | 42,443 |
| Q1 & near 52wk high (≤5% off) | **−0.104** | **−1.12%** | −1.4 | 54,190 |
| Q1 & far from high (≥20% off) | **−0.011** | **+0.76%** | +0.4 | 10,941 |
| Q1 & up & near-high (the META class) | −0.103 | −1.10% | −1.4 | 52,477 |

  In absolute terms Q1-uptrend names still MADE money (+2.7%/60d raw, t 3.0) — they just
  lagged SPY slightly and lagged the cross-section clearly. **So H1 as stated is refuted:
  the model is not confusing quiet compounders with dead money — its corpus genuinely says
  quiet-at-highs names underperform the panel over the next 60d.** META's own history
  agrees: 10% of META's rows fall in Q1, and those rows carry mean label z −0.30
  (−0.12 even restricted to uptrend) — dominated by the calm-before-collapse episodes
  (2018, late-2021→2022 −65%). The corpus's freshest META rows (Feb–Apr 2026) all carry
  label z −0.33..−0.70 (raw −6..−20% excess): **recency taught "fade META" too.**
- **The surviving kernel of H1 — survivorship confusion at the TOP of the feature:** the
  panel contains **zero names that exit before 2026** (every ticker's history reaches
  2026; the universe is today's watchlist applied back to 2016). 84 of 292 names are
  ≥5x since 2016-listing; they contribute **42.1% of Q5 rows vs 15.7% of Q1 rows**. In a
  corpus where every high-vol name survived (by construction), "chase dispersion / fade
  calm" is systematically inflated: the blown-up high-vol losers that would have balanced
  the lesson are absent. The learned tilt's *magnitude* is a universe-construction artifact
  even where its *sign* is corpus-true.

## 2. H2 — was the rule ever valid, by era and regime (train + OOS)

Per-date Spearman IC of STD60 vs fwd-60d excess (positive = high dispersion outperforms;
invariant to the corpus z-transforms). Pooled 2016–2026: **+0.064, hit 0.64, t_adj 2.35**
— the rule was genuinely learnable. But it is concentrated:

| year | mean IC | hit | | regime (HMM) | mean IC | hit | n dates |
|---|---|---|---|---|---|---|---|
| 2016 | +0.087 | 0.75 | | BEAR | **+0.150** | 0.78 | 317 |
| 2017 | +0.063 | 0.76 | | BULL_VOLATILE | **+0.095** | 0.74 | 705 |
| 2018 | +0.042 | 0.64 | | BULL_CALM | +0.035 | 0.57 | 1,464 |
| 2019 | +0.029 | 0.48 | | CHOPPY | +0.007 | 0.54 | 93 |
| 2020 | **+0.213** | 0.90 | | | | | |
| 2021 | +0.005 | 0.51 | | | | | |
| 2022 | −0.004 | 0.49 | | | | | |
| 2023 | **+0.117** | 0.71 | | | | | |
| 2024 | **−0.022** | 0.46 | | | | | |
| 2025 | **+0.122** | 0.72 | | | | | |
| 2026 (to 04-08) | +0.027 | 0.64 | | | | | |

- The rule's profit lives in **shock-rebound periods**: 2020 (+0.213), 2023 (+0.117),
  2025 (+0.122), and BEAR/BULL_VOLATILE regimes. It was **dead for years at a time**:
  2021/2022/2024 ≈ 0; the CV fold-2 span (2021-02→2023-09, where the model's own OOS IC
  was −0.013) has feature IC +0.019, hit 0.53, t 0.31.
- **BULL_CALM — the current regime — is the weak spot, and it is getting worse:**
  BULL_CALM-by-year: 2018 −0.073, 2019 −0.019, 2024 −0.026, and **2026 in-corpus −0.088
  with hit rate 0.15** (n=20 dates, small-n caveat). BULL_CALM 2024-26 pooled: +0.017,
  t_adj 0.27 — statistically nothing. This matches the gate's independent finding
  (BULL_CALM model IC +0.021, hit 0.503, placebo-genuine **negative**, §4).
- **Post-training OOS (2026-04-09 →, thin by construction):** the April–May swoon-rebound
  *paid* the rule — fwd-20d IC +0.128 (44 dates, hit 0.80; BULL_VOLATILE dates +0.181).
  The mid-June→July calm melt-up **inverted** it: June 11–30 entry dates, forward return
  truncated at 07-10: IC **−0.019, hit 0.38** (13 dates; truncated-horizon caveat). The
  four full-60d OOS dates (Apr 9–14, crash trough) show +0.164.

**H2 verdict: SURVIVES.** The relationship is real but regime-conditional
(rebound/dispersion-buying), and the model learned it *unconditionally*. In the regime the
book actually lives in (BULL_CALM melt-up), it had no placebo-clean edge in training, was
negative in the corpus's own most recent BULL_CALM slice, and is inverting OOS so far.
The model is "rationally bearish" only in the sense that its corpus and objective told it
so; on this class of names in this regime it is structurally miscalibrated.

## 3. H3 — the feature is mis-specified for steady risers (definitions, not counterfactuals)

`STD60 = std(close, 60d, ddof=1) / close_today` (qlib alpha158;
`kernel/panel_pipeline/alpha158_features.py`). Decomposition for the fade week
[VERIFIED, computed from the same OHLCV cache the pipeline uses]:

| | META 07-06 | META 07-10 | Δ |
|---|---|---|---|
| close | 600.29 | 669.21 | **+11.5%** |
| STD60 numerator (60d level-std) | 37.11 | 37.15 | **+0.1%** |
| STD60 | 0.0618 | 0.0555 | **−10.2%** |
| STD60 z (artifact train stats 0.0575/0.0474) | +0.090 | −0.043 | crosses the 29-split cluster (#475) |
| STD60 if denominator frozen at 07-06 close | — | 0.0619 | **denominator share of decline = 101%** |
| returns-vol 60d (std of daily returns) | 0.0268 | 0.0281 | **+4.8%** |
| returns-vol z (train-panel stats 0.0200/0.0113) | +0.60 | +0.71 | rose, stayed ABOVE panel mean |
| detrended STD60 (std of linear-fit residuals / close) | 0.0360 | 0.0409 | +14% — residual risk rose |

- **The entire STD60 decline is the rally itself** (numerator flat, denominator +11.5%).
  Every risk definition that is not price-level-anchored moved the OTHER way. META never
  was a "calm" name this week — its returns-vol sat at z ≈ +0.6..+0.7 (42–45% annualized)
  the whole time. A returns-based vol feature would not have crossed the training mean,
  let alone a bearish threshold cluster.
- **The feature also mistakes trend for risk at the top end:** FTNT (the model's top pick)
  has STD60 z +2.48, but **92% of its STD60 variance is the trend component** (its own
  doubling inside the window); residual vol is modest (returns-vol z +1.4). The learned
  axis rewards FTNT for its *rally* and punishes META for its *rally* — same feature,
  same mechanism, opposite sign purely by where the trend sits in the 60d window.
- Cross-sectionally STD60 and returns-vol rank-correlate only **0.70** (weekly sampled,
  508 dates), so training could not distinguish them; but in time series, **23% of
  uptrend ticker-weeks show STD60 falling while returns-vol is flat or rising** (n=440k)
  — the mechanical mis-signal fires on roughly one in four rising-name weeks.

**H3 verdict: SURVIVES.** "Got more expensive vs its own 60d range" and "got calmer" are
indistinguishable in this feature by construction. The claim rests on the definitions
above, not on swapping a feature into a trained booster (which is not honestly possible).

## 4. H4 — the gate saw exactly this and said no; the override put it live [VERIFIED]

From the live artifact's own `metadata.wf_gate_metadata` (gate run 2026-07-06T23:22,
gate_version 2):

- `wf_reason`: **FAIL** — "benchmark_ok=False, regime_ok=False; mean Sharpe +0.778 …
  SPY +1.081, ΔSharpe −0.303, beat SPY Sharpe 1/3, beat SPY APY 0/3".
- `sanity_reason`: **FAIL** — genuine placebo-adjusted IC +0.0081 < +0.020 required
  (aligned real +0.0651, placebo +0.0570).
- `sanity_regime_ic`: **FAIL in BULL_CALM, BULL_VOLATILE, CHOPPY.** BULL_CALM: mean IC
  +0.021, median +0.002, **hit rate 0.503** (a coin flip), placebo-genuine IC **−0.029**
  (placebo *beats* real). Only BEAR passes (+0.330, hit 0.96, genuine +0.335).
- `trade_monotonicity`: **FAIL** — "score monotonicity failed in active regime(s):
  BULL_CALM": entry_rank_score Spearman −0.077 vs realized returns; **top-ranked entries
  returned +6.1% vs bottom-ranked +19.7% (spread −13.7pp, n=110 BULL_CALM trades)**. The
  gate measured, on simulated WF trades, precisely the behavior the operator observed this
  week: in BULL_CALM the model's ranking is anti-predictive.
- `manual_override: true` — "2026-07-06 operator-directed freshness promote per model
  freshness governance policy (NO model >28d; freshness > strict gate). genuine_ic=+0.008
  below 0.020 threshold due to structural embargo leakage floor (~+0.04 placebo on 60d
  label). real_ic=+0.055 is positive."
- Lineage: the 07-05 candidate (`eeee9542`) failed identically and was NOT overridden
  (never went live). XGB has been primary since the 2026-06-23 operator re-promotion
  (reversing 06-05 PatchTST; the OXY forensics already called this booster family
  "unvalidated"). The freshness policy (2026-06-30, RFC #210 lineage) is being exercised
  weekly, so **every weekly XGB now reaches primary through the override path, and the
  regime-level FAIL travels with it silently.**

**H4 verdict: SURVIVES.** The root-cause chain terminates at "known-unvalidated model in
primary": the gate's BULL_CALM regime-IC and monotonicity checks flagged exactly this
tilt, four days before the META misread. The gate was right; the override discarded the
regime-specific part of its verdict while citing (correctly) the embargo-leakage floor
for the pooled number. Nothing here says the freshness policy is wrong — it says the
override currently carries **no regime-scoped consequence** (see fix F4).

## 5. Fix menu (owners, effort, and the evidence that justifies each)

| # | Fix | Owner | Effort | Evidence gate before build |
|---|---|---|---|---|
| F1 | **Returns-based vol feature** (std of 60d daily returns, plus 20/30d) replacing or alongside the STD family in the alpha158-fund recipe; optionally a detrended level-std | renquant-model (feature spec) + base-data rebuild | M (feature builder + retrain + WF gate) | H3 is already sufficient to *add* it as a candidate; promotion still requires the standard placebo-clean WF pass. Success = BULL_CALM regime-IC no longer placebo-dominated. |
| F2 | **Trend-interaction features** (e.g. sign(ret-120d) × vol-z, distance-from-52wk-high) so the ranker can condition dispersion on trend instead of fading all calm names | renquant-model | M | H1 table (§1): the corpus itself separates near-high vs far-from-high low-vol names (−1.1% vs +0.8%); an interaction lets the model learn that split. Same WF gate applies. |
| F3 | **Per-feature-family regime-stability screen at training time**: before a family (STD/ROC/…) is admitted, require its univariate regime-conditional IC to be placebo-clean-stable, or emit it with a monotone/zero constraint in failing regimes | renquant-model (training pipeline) | M-L | H2 (§2): STD60's edge is BEAR/BULL_VOLATILE-only; an automated screen would have surfaced the BULL_CALM inversion at training time instead of at the WF gate. |
| F4 | **Regime-scoped override consequences on the weekly rail** (#467 gate path — NOT runtime gate hacks): when a booster is promoted via freshness override with `sanity_regime_ic` FAIL in the active regime, the promote record must carry a named exposure consequence (e.g. shadow-demote or reduced buy-budget in that regime) rather than full primary silently | renquant-orchestrator (weekly rail, #467 design already exists) | S-M design, M impl | H4 (§4): FAIL verdict + this week's realized misread. This is governance wiring, not a new gate. |
| F5 | **Corpus survivorship remediation**: add delisted/failed names to the training universe (or at minimum stamp a survivorship disclosure into the dataset provenance and artifact metadata) | renquant-base-data + renquant-model | L (data acquisition) | §1: 0 pre-2026 exits, 42%/16% Q5/Q1 share from ≥5x survivors. Justified for the next corpus rebuild; not a quick fix. |
| F6 | **Forward validation cohort** (already recommended in #475): decision-ledger tracking of low-STD60 faded vs high-STD60 admitted cohorts | renquant-orchestrator (#133/#195 stream) | S | Running evidence for/against F1-F3 promotion decisions. |

Recommended path: **F1+F2 in the next scheduled retrain cycle (they are one recipe change),
F4 as the immediate governance patch on the #467 rail, F6 to accumulate live evidence.**
F3 next; F5 on the next corpus rebuild. No runtime scoring hacks anywhere.

## 6. Answer to the operator, plainly

模型没有做空 META，也不可能做空（做空开关是关的，账本里从未有过 short）。它只是把 META 的分数打得很低。
这个低分来自一条真实学到的规则："60 日价格离散度低 = 未来跑输"。这条规则在训练语料里确实成立
（尤其是 2020/2023/2025 的暴跌反弹段），但 (a) 它的特征定义把"稳步上涨"错当成"平静"（META 本周
STD60 下跌的 101% 来自分母上涨，真实波动率反而上升了 4.8%）；(b) 它只在 BEAR/回弹期有效，在当前
BULL_CALM 融涨期无效甚至反向（语料内 2026 BULL_CALM IC −0.088，命中率 15%）；(c) 门控 7 月 6 日就
发现了这一点（BULL_CALM 排名单调性倒挂 −13.7pp）并判 FAIL，是 freshness 覆盖把它放进主模型的。
所以：模型按它学到的世界观是"理性"的，但那个世界观在这类股票、这个 regime 上是结构性错的 —
修复在特征与训练侧（F1/F2/F3），治理在 #467 周轨（F4），不动运行时打分。

## Reproduction inventory (read-only; scratchpad only)

- Inputs [all read-only]: `data/alpha158_291_fundamental_dataset.parquet` (training corpus,
  row-count-matched to artifact), `data/ohlcv/{T}/1d.parquet` (292 names + SPY, through
  2026-07-10), live artifact + `.previous` + weekly_rollback copies,
  `data/runs.alpaca.db` (`trades`, `live_state_snapshots`; opened `mode=ro`), pinned
  strategy-104 config via `.subrepo_runtime`.
- Method: raw STD60 / returns-vol / trend metrics and forward-excess labels recomputed
  from the OHLCV cache (corpus stores global-z features + CS-z labels; all Spearman/quintile
  results are invariant to those monotone transforms; economic magnitudes reported from the
  raw recomputation). Regime labels via `renquant_common.hmm_regime_labels`
  (v2026-05-31 detector). t-stats overlap-adjusted with n_eff = n_dates/horizon.
- Scripts: scratchpad `std60_provenance.py`, `std60_followup.py` (session scratchpad;
  not committed). No production path written; no git in the live umbrella tree or any
  primary checkout (this doc authored in an isolated orchestrator worktree); no Modal /
  network compute; local only.
