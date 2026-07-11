# STD60 rule provenance — where "low STD60 ⇒ bearish" came from, and whether it was ever valid

**Question (operator, via #475):** "为什么模型会 short 它？这不对！" The live XGB panel fades quiet
mega-cap rallies via a learned low-STD60→bearish rule (74% of META's 07-06..07-10 score
decline — `doc/research/2026-07-11-meta-score-attribution.md`, PR #475). Where did this
rule come from in the training data, and was it ever valid out-of-sample? Is the model
rationally bearish, or structurally confused on this class of names?

> **2026-07-11 revision note.** Codex (CHANGES_REQUESTED, orchestrator#476) found the
> original version of this document overclaimed a root-cause **verdict** from
> hypothesis-generating evidence. Four specific gaps: (1) the only computation lived in
> uncommitted scratch scripts against mutable local files, not sealed/reproducible
> evidence; (2) the OOS claim rested on far too few dates to establish a regime
> conclusion, and mixed a 60d-trained target with a 20d-truncated calculation; (3) the
> era/regime/feature screens are post-hoc selection on the same corpus with no
> preregistered, selection-adjusted inference plan (data-snooping — White 1996/2000,
> *A Reality Check for Data Snooping*, https://doi.org/10.1111/1468-0262.00152); (4)
> univariate IC plus PDP/SHAP-style reasoning cannot establish that the fitted model
> learned an unconditional causal rule, given correlated features and PDP's off-manifold
> extrapolation behavior (Apley & Zhu, https://doi.org/10.1111/rssb.12377). This revision
> reframes every claim below as a **hypothesis**, not a verdict; marks the OOS evidence as
> descriptive-only; flags the post-hoc-selection exposure explicitly; and states what
> mechanism-establishing work (conditional ALE/SHAP, local support counts, grouped-
> attribution residuals, frozen-model ablations) is still outstanding. A sealed,
> content-addressed evidence bundle for the parts that could be independently
> re-verified this session is in `renquant-artifacts` — see §6. **No fix or promotion
> recommendation should be read from this document; §5 is a candidate-hypothesis list for
> the preregistered test plan in §7, not a build queue.**

## Hypotheses (bottom line first) — not a verdict

**First, the literal question: there was NO short — not a position, not an order, not an
intent [VERIFIED].** Current book = MU / GRMN / AVGO, all long; META absent. The trades
ledger contains only `buy`/`sell` actions ever; META's full history is 31 buys / 28 sells /
1 `sell_pending` (a long-exit attempt, 2026-06-02). `long_short.enabled = false` in the
pinned strategy-104 config (the Phase-2 scaffolding is dormant). "看空" this week =
raw panel score −0.176 → no-buy / low rank. Nothing was, or could have been, shorted. This
part is a direct ledger/config fact, not a causal claim, and is unaffected by the
reframing below.

**Everything past that point is a set of live hypotheses, not an established root cause.**
H1 (class confusion) is refuted by the in-corpus population check in §1 — but that check
is itself descriptive/post-hoc (§1 caveat). H2 (regime-conditional pattern learned
unconditionally), H3 (feature mis-specification / price-in-denominator mechanism), and H4
(a model that failed its own gate reached primary via freshness override) remain **live
hypotheses consistent with** the evidence gathered so far. None of H2/H3/H4 is yet
established as *the* validated causal mechanism for the model's behavior — that requires
the preregistered, selection-adjusted test plan in §7, which does not exist yet.

| Hypothesis | Status (hypothesis, not verdict) | One-line evidence | Outstanding to call this validated mechanism |
|---|---|---|---|
| H1 class confusion (quiet winners mislabeled as dead money) | **Refuted, as stated** — but on a post-hoc, in-corpus, descriptive check | Low-STD60 rows are 66% *uptrend* names, and the uptrend/near-high subset had the *worst* forward returns in-corpus (−1.1%/60d excess vs +0.8% for far-from-high). Reframe that survives as a live hypothesis: survivorship inflates the *other* end (42% of high-STD60 rows come from eventual ≥5x names; 0 delisted names in the panel). | The quintile/subset cuts (Q1, ±5%/≥20% high-distance, up/down-120d) were chosen after seeing the data; a preregistered version of this split has not been run (§7 point 3). |
| H2 regime-specific pattern generalized | **Live hypothesis — primary candidate, not validated** | Feature IC: BEAR +0.150, BULL_VOLATILE +0.095, BULL_CALM +0.035 (hit 0.57); dead 2021/2022/2024 (−0.004..+0.005); BULL_CALM 2026 in-corpus −0.088 (hit 0.15, n=20 dates). The rule's edge concentrates in crash-rebound eras/regimes in-corpus. | Era/regime bucketing here is post-hoc selection on the same corpus (§7 point 3); the post-training OOS evidence is a handful of dates and is descriptive-only, not confirmatory (§2 caveat, §7 point 2). |
| H3 feature mis-specification | **Live hypothesis — mechanical decomposition independently reproduced; causal-mechanism claim not established** | META 07-06→07-10: numerator (60d level-std) +0.1%, denominator (close) +11.5% ⇒ 101% of the STD60 decline is the denominator; returns-vol60 rose +4.8%. This numerator/denominator/returns-vol arithmetic was independently recomputed from OHLCV in the 2026-07-11 evidence-sealing session (§6) and matches the original figures. | That the *fitted booster's* learned response is driven by this channel — as opposed to a correlated proxy feature, given STD60 correlates with other trend/vol features — is not established; needs conditional ALE/SHAP, local support counts, grouped-attribution residuals, and frozen-model ablations (§7 point 4). |
| H4 governance (unvalidated model in primary) | **Empirically confirmed as a governance/process fact (independently re-verified this session directly from the live artifact, §6); does not by itself establish which of H1-H3 explains the mis-score** | The live booster's own `metadata.wf_gate_metadata` FAILs the BULL_CALM regime-IC and trade-monotonicity checks (placebo-genuine IC −0.029; entry-rank spread −13.7pp) and reached primary via `manual_override: true` (2026-07-06 freshness promote). | This establishes the gate flagged a real BULL_CALM problem and was overridden — a fact about process, not a proof that H2 or H3 is the operative mechanism behind this specific META misread. |

**Hypothesized chain (not established):** qlib-STD60's price-in-denominator construction
(H3) plus a survivor-only, rebound-rich training corpus (H1'/H2) *may* combine so that the
rank objective learns an unconditional "fade calm-at-highs, chase dispersion" tilt; the WF
gate's regime-IC/monotonicity checks failed in BULL_CALM (H4, confirmed); a freshness
override put the model live anyway (H4, confirmed); an orderly +11.5% META rally
mechanically deflated STD60 (H3, confirmed mechanically) while the model's rank fell. Each
link that says "confirmed" is a re-verified fact (§6); each link that says "may" is the
part the preregistered test plan (§7) still needs to adjudicate.

## 0. Model identity and training window [VERIFIED — independently re-verified 2026-07-11]

- Live booster: `backtesting/renquant_104/artifacts/prod/panel-ltr.alpha158_fund.json`,
  `kind=panel_ltr_xgboost`, trained_date **2026-07-06**, train_run_id `240f9b27`
  (byte-stable across 07-06..07-11 per #475; `panel_scoring.kind=xgb` in the pinned config).
  File sha256 `5211f6bebd90ca088c7fe2492cae1845369b80b84e53ed347d3c27d7a864c9cf`
  (re-hashed 2026-07-11; matches the sha cited in #475 as stable all week).
- Training corpus: `data/alpha158_291_fundamental_dataset.parquet` — row count independently
  re-read with pandas in the 2026-07-11 sealing session: **722,775 rows × 292 unique
  tickers × 2,580 unique dates**, matching the artifact `panel_shape` field exactly.
  **Window: 2016-01-04 → 2026-04-08** (re-verified via `date.min()/date.max()`), label
  `fwd_60d_excess` (60-trading-day return minus SPY, then **cross-sectional z per date**;
  features global-z on train stats, clip ±5). Corpus file sha256
  `9a495e28b95acee44730a73e0a63f59115092386a6413ec71e98b9b868b81319`.
  The final fit uses the FULL panel (`renquant_model_gbdt/panel_trainer.py`; CV folds are
  diagnostic). So the model saw everything through 2026-04-08, incl. the 2026 melt-up's
  first months; genuine post-training OOS is only 2026-04-09 → now.
- STD60 feature stats used for z-scoring (`feature_means`/`feature_stds` at index 131 in
  the artifact's `feature_cols`): mean **0.057549**, std **0.047428** — re-read directly
  from the artifact file in the sealing session; matches the "0.0575/0.0474" figures used
  throughout §3.
- Replication basis for the rest of this doc: raw STD60/labels recomputed from
  `data/ohlcv/{T}/1d.parquet` (STD60 replicates the corpus feature up to its global-z
  transform; Spearman-based results are invariant to the corpus's monotone z transforms).
  Regime labels: `renquant_common.hmm_regime_labels.compute_hmm_regime_labels`
  (v2026-05-31 detector, the gate's convention). All t-stats below are overlap-adjusted
  (n_eff = n_dates / horizon) — conservative, because 60d labels overlap.
  **Reproduction status:** the model-identity facts above and the §3/§4 sections marked
  [VERIFIED] were independently re-derived in the 2026-07-11 evidence-sealing session
  directly from the live artifact/OHLCV/corpus files (read-only) and are sealed in
  `renquant-artifacts` (§6). The §1/§2 per-date quintile and per-year/regime IC tables were
  **not** re-derived in that session — the scripts that produced them
  (`std60_provenance.py`, `std60_followup.py`) were uncommitted session scratch artifacts
  from the original research pass and are not available to re-run. Those tables are sealed
  **as-reported** (a verbatim transcript of this document's own numbers), not as
  independently reproduced computation — see §6 for the exact split.

## 1. H1 — what actually lives in low STD60, and what happened to it (train window)

> **Post-hoc selection caveat (Codex point 3):** the quintile cut, the up/down-120d split,
> and the ±5%/≥20% distance-from-52wk-high bands below were chosen after inspecting the
> data, on the same corpus used to fit the live model. This is a hypothesis-generating
> descriptive exercise, not a preregistered, selection-adjusted test. Treat the sign of the
> result as suggestive, not confirmatory, until it is re-run under a predeclared candidate
> set with purged/embargoed walk-forward evaluation (§7).
>
> **Reproduction status:** the tables below are sealed **as-reported** from the original
> research session (§0); they were not independently re-derived in the 2026-07-11 sealing
> pass.

Per-date STD60 quintiles, label = CS-z of fwd-60d excess (what the ranker optimized):

| STD60 quintile | mean label (z) | t_adj | mean raw fwd60 excess | n rows |
|---|---|---|---|---|
| Q1 (lowest) | **−0.089** | −2.7 | −0.5% | 145,816 |
| Q2 | −0.064 | −2.8 | | 143,746 |
| Q3 | −0.033 | −1.8 | | 143,929 |
| Q4 | +0.044 | +1.8 | | 143,746 |
| Q5 (highest) | **+0.142** | +3.0 | **+4.0%** (median +1.4% — heavy right skew) | 145,538 |

The corpus (descriptively) associates "low dispersion" with "below-consensus forward
return". Now the population and trend split inside Q1 — the H1 test:

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
  lagged SPY slightly and lagged the cross-section clearly. **So H1 as originally stated is
  refuted on this descriptive check:** the corpus does not appear to confuse quiet
  compounders with dead money — it associates quiet-at-highs names with underperforming the
  panel over the next 60d. META's own history is directionally consistent: 10% of META's
  rows fall in Q1, and those rows carry mean label z −0.30 (−0.12 even restricted to
  uptrend) — dominated by the calm-before-collapse episodes (2018, late-2021→2022 −65%).
  The corpus's freshest META rows (Feb–Apr 2026) carry label z −0.33..−0.70 (raw −6..−20%
  excess).
- **The surviving kernel of H1 as a live hypothesis — survivorship confusion at the TOP of
  the feature:** the panel contains **zero names that exit before 2026** (every ticker's
  history reaches 2026; the universe is today's watchlist applied back to 2016). 84 of 292
  names are ≥5x since 2016-listing; they contribute **42.1% of Q5 rows vs 15.7% of Q1
  rows**. In a corpus where every high-vol name survived (by construction), "chase
  dispersion / fade calm" could be systematically inflated in magnitude even if its sign
  reflects something real — this remains a hypothesis pending the corpus-rebuild work in
  §5/§7.

## 2. H2 — was the rule ever valid, by era and regime (train + OOS)

> **Post-hoc selection caveat (Codex point 3):** the year and HMM-regime buckets below are
> a post-hoc partition of the same training corpus, not a preregistered candidate set.
> **OOS underpowered caveat (Codex point 2):** the "post-training OOS" bullet below covers
> a total of a few dozen thin windows and, for the full 60-trading-day horizon the model
> was actually trained on, only **four** mature entry dates (Apr 9–14). Four dates cannot
> establish a regime conclusion in either direction. The June→July figure uses a **20-day
> truncated** forward return because 60 trading days have not yet elapsed from those entry
> dates — it is **not comparable** to the trained 60d target and is reported here as
> **descriptive only**, not as evidence that the rule "inverted" out-of-sample. No fix or
> promotion decision should be read from either OOS figure.
>
> **Reproduction status:** as with §1, these tables are sealed as-reported from the
> original session, not independently re-derived in the 2026-07-11 sealing pass.

Per-date Spearman IC of STD60 vs fwd-60d excess (positive = high dispersion outperforms;
invariant to the corpus z-transforms). Pooled 2016–2026: **+0.064, hit 0.64, t_adj 2.35**
in-corpus. This concentrates unevenly across eras/regimes:

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

- In-corpus, the rule's edge concentrates in **shock-rebound periods**: 2020 (+0.213),
  2023 (+0.117), 2025 (+0.122), and BEAR/BULL_VOLATILE regimes; it is near zero for
  years at a time: 2021/2022/2024 ≈ 0; the CV fold-2 span (2021-02→2023-09, where the
  model's own OOS IC was −0.013) has feature IC +0.019, hit 0.53, t 0.31.
- **BULL_CALM — the current regime:** BULL_CALM-by-year: 2018 −0.073, 2019 −0.019,
  2024 −0.026, and 2026 in-corpus −0.088 with hit rate 0.15 (**n=20 dates — small-n
  caveat**). BULL_CALM 2024-26 pooled: +0.017, t_adj 0.27 — not distinguishable from
  noise at this sample size. This is directionally consistent with the gate's independent
  finding (BULL_CALM model IC +0.021, hit 0.503, placebo-genuine **negative** — §4,
  independently re-verified).
- **Post-training OOS (2026-04-09 →, thin by construction — descriptive only, per the
  caveat above):** a 20-day-forward calculation over Apr–May entry dates shows +0.128
  (44 dates, hit 0.80); a 20-day-truncated calculation over June 11–30 entry dates shows
  −0.019 (13 dates, hit 0.38). The **only** dates with a completed, trained-horizon-matched
  60-day forward return are Apr 9–14 (four dates), showing +0.164. **None of these figures
  — individually or together — are statistically sufficient to conclude the rule "paid" in
  one window and "inverted" in another; they are reported as descriptive context only.**

**H2 status: live hypothesis, primary candidate, not validated.** The relationship looks
regime-conditional in-corpus (rebound/dispersion-buying) and the model's objective does not
condition on regime, so it is plausible the model learned it unconditionally. But the
in-corpus regime split is post-hoc, and the OOS evidence is underpowered by roughly an
order of magnitude relative to what the caveat above requires for a regime-generalization
claim. This is not yet established as the mechanism.

## 3. H3 — the feature is mis-specified for steady risers (definitions, mechanically verified)

`STD60 = std(close, 60d, ddof=1) / close_today` (qlib alpha158;
`kernel/panel_pipeline/alpha158_features.py`). Decomposition for the fade week
[VERIFIED — independently recomputed from `data/ohlcv/META/1d.parquet` in the 2026-07-11
sealing session using the same rolling-std/ddof=1 definition; matches the original figures
to within rounding]:

| | META 07-06 | META 07-10 | Δ |
|---|---|---|---|
| close | 600.29 | 669.21 | **+11.5%** |
| STD60 numerator (60d level-std) | 37.107 (re-verified) | 37.145 (re-verified) | **+0.1%** |
| STD60 | 0.06182 (re-verified) | 0.05551 (re-verified) | **−10.2%** |
| STD60 z (artifact train stats 0.057549/0.047428, re-verified §0) | +0.090 (re-verified) | −0.043 (re-verified) | crosses the 29-split cluster (#475) |
| STD60 if denominator frozen at 07-06 close | — | 0.0619 | **denominator share of decline = 101%** |
| returns-vol 60d (std of daily returns) | 0.02683 (re-verified) | 0.02811 (re-verified) | **+4.8%** |
| returns-vol z (train-panel stats 0.0200/0.0113 — **as-reported, not re-verified**) | +0.60 | +0.71 | rose, stayed ABOVE panel mean |
| detrended STD60 (std of linear-fit residuals / close — **as-reported, not re-verified**) | 0.0360 | 0.0409 | +14% — residual risk rose |

- **The STD60 decline in this window is arithmetically the price rally, not a change in
  dispersion** (numerator flat at +0.1%, denominator +11.5%) — this row of the table is
  independently reproduced, not merely reported. Over the same window, 60-day
  returns-volatility (a definition that does not divide by the current price level) rose
  rather than fell. This is a fact about the **feature's definition and this one ticker's
  price series**, not yet a fact about what the fitted booster's learned response is driven
  by (see the outstanding-work note below).
- **As-reported, not independently re-derived this session:** the claim that "92% of
  FTNT's STD60 variance is the trend component" and the claim that "23% of uptrend
  ticker-weeks show STD60 falling while returns-vol is flat or rising (n=440k)" both rest
  on the original session's scratch computation and were not rebuilt in the 2026-07-11
  sealing pass. They are transcribed as-reported in §6's sealed bundle, flagged as
  unverified in this pass.
- **Outstanding before this becomes an established mechanism (Codex point 4):** the
  definitional decomposition above shows the feature *can* conflate "rallying" with
  "calming down" for one name in one week. It does **not** show that the fitted XGB's
  learned response is actually driven by this channel in isolation, as opposed to a
  correlated feature standing in for it (STD60 correlates with other trend/momentum/vol
  features in the recipe) or a partial-dependence artifact from evaluating implausible
  feature combinations off the training manifold (Apley & Zhu 2020). Establishing "the
  model learned this specific unconditional rule" requires conditional ALE/SHAP (not
  marginal PDP), local support counts per evaluated point, grouped-attribution residuals
  across the correlated feature family, and frozen-model ablations — none of which have
  been run. Until then, H3 is a well-evidenced **candidate mechanism**, not a demonstrated
  one.

**H3 status: live hypothesis — mechanical decomposition independently verified; causal
mechanism not established.**

## 4. H4 — the gate's own record, and the override [VERIFIED — independently re-verified 2026-07-11]

From the live artifact's own `metadata.wf_gate_metadata`, re-read directly from
`panel-ltr.alpha158_fund.json` in the 2026-07-11 sealing session (gate run
2026-07-06T23:22:50Z, gate_version 2; all figures below matched the document's original
citations exactly on re-read):

- `wf_reason`: **FAIL** — "benchmark_ok=False, regime_ok=False; mean Sharpe +0.778 …
  SPY +1.081, ΔSharpe −0.303, beat SPY Sharpe 1/3, beat SPY APY 0/3".
- `sanity_reason`: **FAIL** — genuine placebo-adjusted IC +0.0081 < +0.020 required
  (aligned real +0.0651, placebo +0.0570).
- `sanity_regime_ic`: **FAIL in BULL_CALM, BULL_VOLATILE, CHOPPY.** BULL_CALM: mean IC
  +0.0211, median +0.0015, **hit rate 0.5034** (a coin flip), placebo-genuine IC
  **−0.0295** (placebo *beats* real). Only BEAR passes (+0.330, hit 0.96, genuine +0.335).
- `trade_monotonicity`: **FAIL** — "score monotonicity failed in active regime(s):
  BULL_CALM": entry_rank_score Spearman −0.077 (BULL_CALM: −0.077, n=110) vs realized
  returns; **top-ranked entries returned +6.07% vs bottom-ranked +19.74% (spread −13.67pp,
  n=110 BULL_CALM trades)**. The gate measured, on simulated WF trades, a BULL_CALM
  anti-predictive ranking — consistent with (not proof of) the behavior observed this
  week for META specifically.
- `manual_override: true`, `manual_override_reason`: "2026-07-06 operator-directed
  freshness promote per model freshness governance policy (NO model >28d; freshness >
  strict gate). genuine_ic=+0.008 below 0.020 threshold due to structural embargo leakage
  floor (~+0.04 placebo on 60d label). real_ic=+0.055 is positive." (`real_ic` field:
  0.05464, re-verified.)
- Lineage: the 2026-07-05 candidate (`train_run_id=eeee9542`,
  `panel-ltr.alpha158_fund.previous.json`) shows `passed: False`,
  `manual_override: None` — **re-verified this session**: it failed the same wf_reason
  check (mean Sharpe +0.776, ΔSharpe −0.305) and was NOT overridden, i.e. never went live.
  XGB has been primary since the 2026-06-23 operator re-promotion (reversing 06-05
  PatchTST). The freshness policy (2026-06-30, RFC #210 lineage) is exercised weekly, so
  every weekly XGB reaching primary through the override path carries this same
  regime-level FAIL silently forward — this is a structural governance observation, not
  a per-model hypothesis.

**H4 status: independently confirmed governance/process fact, not a full causal
explanation.** The live booster failed its own BULL_CALM regime-IC and monotonicity
checks and reached primary via freshness override — this part is re-verified directly from
the artifact, not inferred. What it does **not** establish is *why* the model is
regime-confused in BULL_CALM (that is H2's and H3's territory, both still open
hypotheses), nor that the override itself was the wrong call (the freshness-vs-strict-gate
tradeoff is a separate, already-decided policy question, out of scope here).

## 5. Candidate hypotheses for the test plan (NOT a fix menu, NOT recommended actions)

The items below are candidates to evaluate under the preregistered plan in §7. None of them
should be built, promoted, or treated as a recommendation on the strength of this document
alone — that is precisely the gap Codex's review identified.

| # | Candidate change to test | Owner | Effort | What would need to be shown first |
|---|---|---|---|---|
| C1 | **Returns-based vol feature** (std of 60d daily returns, plus 20/30d) as an addition/alternative to the STD family in the alpha158-fund recipe; optionally a detrended level-std | renquant-model (feature spec) + base-data rebuild | M (feature builder + retrain + WF gate) | H3's mechanical decomposition motivates testing this, but it is a candidate for the preregistered comparison in §7, not a standing recommendation; still subject to the standard placebo-clean WF pass. |
| C2 | **Trend-interaction features** (e.g. sign(ret-120d) × vol-z, distance-from-52wk-high) so the ranker could in principle condition dispersion on trend | renquant-model | M | H1's descriptive split motivates this hypothesis; needs to be tested under the same preregistered plan, not built ad hoc from the post-hoc split in §1. |
| C3 | **Per-feature-family regime-stability screen at training time** | renquant-model (training pipeline) | M-L | Depends on H2 being validated (not just observed in-corpus) under a purged/embargoed walk-forward design (§7). |
| C4 | **Regime-scoped override consequences on the weekly rail** (#467 gate path) | renquant-orchestrator (weekly rail) | S-M design, M impl | H4's confirmed FAIL+override record already justifies discussing this as a governance-wiring question independent of H1-H3; still a design decision, not something this doc can greenlight unilaterally. |
| C5 | **Corpus survivorship remediation / disclosure** | renquant-base-data + renquant-model | L (data acquisition) | Motivated by the descriptive §1 finding (0 pre-2026 exits, 42%/16% Q5/Q1 survivor share); a corpus-rebuild-scale change, not a quick fix. |
| C6 | **Forward validation cohort** (decision-ledger tracking of low-STD60 faded vs high-STD60 admitted cohorts) | renquant-orchestrator (#133/#195 stream) | S | Would accumulate genuinely out-of-sample live evidence going forward; does not require waiting on C1-C5. |

No runtime scoring changes, and no promotion of C1/C2, should happen ahead of the
preregistered test plan in §7. C4 (governance wiring) and C6 (evidence accumulation) are
the only items that do not themselves make an accuracy/mechanism claim and could be
discussed on their own governance merits.

## 6. Evidence sealing and reproduction status (2026-07-11)

A content-addressed evidence bundle for this document is sealed in `renquant-artifacts`
(see the PR/registry entry linked from this repo's PR body). What is sealed and its status:

- **Independently re-verified in the 2026-07-11 sealing session** (fresh sha256 hashes,
  fresh reads against the live artifact/OHLCV/corpus files, read-only): §0 model-identity
  facts (trained_date, train_run_id, config_fingerprint, panel_shape rows/tickers/dates,
  STD60 feature_means/feature_stds), the full §4 `wf_gate_metadata` record (wf_reason,
  sanity_reason, sanity_regime_ic per-regime detail, trade_monotonicity per-regime detail,
  manual_override/manual_override_reason, real_ic, the 07-05 candidate's non-overridden
  FAIL), and the §3 META STD60/returns-vol numerator-denominator decomposition recomputed
  directly from OHLCV.
- **Sealed as-reported, NOT independently re-derived in this session:** the §1 STD60
  quintile/subset tables, the §2 per-year and per-regime IC tables and the post-training
  OOS IC figures, and the §3 FTNT trend-decomposition and cross-sectional
  rank-correlation/mis-signal-rate figures. These were computed by uncommitted scratch
  scripts (`std60_provenance.py`, `std60_followup.py`) in the original research session;
  those scripts are not present in this worktree or any committed location and could not
  be re-run. The sealed bundle records these numbers as a verbatim transcript of this
  document, explicitly labeled as unverified-in-this-pass, rather than silently presenting
  them with the same evidentiary weight as the re-verified facts above.
- This split — what is independently reproducible today vs. what only exists as a
  scratch-session transcript — is itself the clearest evidence for Codex's point 1. Closing
  it requires the committed, reproducible pipeline described in §7, not a better writeup of
  the existing numbers.

## 7. Required next artifact: a preregistered, cross-repo experiment design

Nothing in H2/H3 should be treated as validated, and no MoE/regime-gated architecture
should be considered, before the following exists and runs — this is the artifact Codex's
review requires, and it is currently **not started**:

- **Ownership, split across repos** (mirrors the subrepo operating model):
  - `renquant-model`: the feature/ablation design — the returns-vol and trend-interaction
    candidate features (C1/C2), the frozen-model ablation harness, and the conditional
    ALE/SHAP + grouped-attribution-residual tooling needed to test H3 as a mechanism claim
    rather than a definitional one.
  - `renquant-pipeline`: training metadata — ensuring the preregistered candidate set,
    the purged/embargoed walk-forward split points, and the frozen artifact identities used
    for ablation are stamped and carried through training, not reconstructed after the
    fact.
  - `renquant-base-data`: coverage/survivorship — the delisted/failed-name gap identified
    in §1 (C5), and confirmation that the OHLCV/corpus coverage used for any re-run matches
    what the preregistration declares in advance.
  - `renquant-artifacts`: sealed evidence — every table, IC series, regime label set, and
    frozen-model ablation result from the preregistered run sealed content-addressed,
    the same way §6 seals what exists today.
  - `renquant-orchestrator`: the experiment ledger — the preregistration document itself
    (candidate set, evaluation design, and decision rule declared *before* the run), and
    the resulting comparison report.
- **Design requirements** (from Codex's review, point 3): a **predeclared candidate set**
  (not a post-hoc year/regime scan); **purged/embargoed expanding walk-forward** evaluation
  with **date-block resampling**; and reported **uncertainty** — not point estimates — for
  IC, calibration, rank spread, net return, turnover, and drawdown.
- **Comparison to run first:** baseline (current STD-family recipe) vs. a returns-vol/
  trend-feature redesign (C1+C2), evaluated under the design above. This comparison must
  complete, with a result, before any regime-gated or mixture-of-experts (MoE) architecture
  is considered.
- **Bar for even discussing MoE:** MoE is not justified by one ticker/week. Before it is
  discussed as an option, the redesign above must show (a) stable ex-ante regime
  interactions (not a post-hoc regime split), (b) sufficient expert occupancy per regime
  arm, (c) gate stability over time, and (d) a **double-OOS** result — i.e. an OOS
  comparison against the simpler feature-redesign baseline (C1+C2), not just against the
  current STD-family recipe.

Until this experiment exists and reports, this document's status remains: **hypotheses
plus a constrained test plan**, not a root-cause verdict, and production scoring behavior
is unchanged.

## 8. Answer to the operator, plainly (factual parts stand; causal parts reframed as hypotheses)

模型没有做空 META，也不可能做空（做空开关是关的，账本里从未有过 short；这一条是账本/配置事实，
[VERIFIED]）。它只是把 META 的分数打得很低。

这个低分**可能**来自一条在训练语料里观察到的规则："60 日价格离散度低 → 未来跑输"（尤其是
2020/2023/2025 的暴跌反弹段）。但这仍然是**假设，不是已验证的结论**：(a) 特征定义确实会把"价格
上涨"和"离散度下降"混淆——META 本周 STD60 下跌的 101% 来自分母上涨，真实波动率反而上升了
4.8%（这一条已在本次证据封存中独立复算验证）；但这不足以证明模型学到的就是这条机制，还需要
conditional ALE/SHAP 等分析（Codex 意见第 4 点）；(b) 语料内该规则在 BEAR/回弹期强、在 BULL_CALM
弱甚至为负，但这个 regime 切分是事后选择（Codex 意见第 3 点），样本外（OOS）证据只有个位数天数，
不足以下"反转"的结论（Codex 意见第 2 点）；(c) 门控 7 月 6 日确实发现了 BULL_CALM 排名单调性倒挂
（−13.7pp）并判 FAIL，是 freshness 覆盖把它放进主模型的——这一条是已独立复核的事实。

所以：门控的判断本身是对的；模型在这类股票、这个 regime 上表现异常也是事实；但"为什么"——是特征
定义问题、是训练语料的 regime 混淆、还是两者的组合——目前仍是待验证的假设，需要 §7 的跨仓库预注册
实验来回答，不是本文档可以单方面下结论的。不建议在该实验完成前对特征或训练流程做任何改动。

## Reproduction inventory (read-only; scratchpad only)

- Inputs [all read-only]: `data/alpha158_291_fundamental_dataset.parquet` (training corpus,
  row-count-matched to artifact, sha256 sealed in §6), `data/ohlcv/{T}/1d.parquet` (292
  names + SPY, through 2026-07-10), live artifact + `.previous` + weekly_rollback copies,
  `data/runs.alpaca.db` (`trades`, `live_state_snapshots`; opened `mode=ro`), pinned
  strategy-104 config via `.subrepo_runtime`.
- Method: raw STD60 / returns-vol / trend metrics and forward-excess labels recomputed
  from the OHLCV cache (corpus stores global-z features + CS-z labels; all Spearman/quintile
  results are invariant to those monotone transforms; economic magnitudes reported from the
  raw recomputation). Regime labels via `renquant_common.hmm_regime_labels`
  (v2026-05-31 detector). t-stats overlap-adjusted with n_eff = n_dates/horizon.
- Scripts: original session's scratchpad `std60_provenance.py`, `std60_followup.py`
  (session scratchpad; not committed, not available for re-run — see §6). The 2026-07-11
  sealing-session re-verification used ad hoc read-only Python (pandas/hashlib) against the
  same files, also not committed (this is a research doc, not a pipeline change); the exact
  values it produced are sealed in `renquant-artifacts` (§6) so they do not depend on this
  scratch code being preserved. No production path written; no git in the live umbrella
  tree or any primary checkout (this doc authored in an isolated orchestrator worktree); no
  Modal / network compute; local only.
