# What the live panel scorer actually keys on — function-level attribution

**Subject:** `backtesting/renquant_104/artifacts/prod/panel-ltr.alpha158_fund.json`
(`kind=panel_ltr_xgboost`, `trained_date=2026-06-21`, `label_col=fwd_60d_excess`,
`lookahead_days=60`, 172 declared `feature_cols`,
`panel_shape={rows: 721335, tickers: 292, dates: 2570}`).

**Reproduce every number below:**

```
<umbrella>/.venv/bin/python scripts/scorer_attribution_probe.py \
    --artifact       <umbrella>/backtesting/renquant_104/artifacts/prod/panel-ltr.alpha158_fund.json \
    --ohlcv-dir      <umbrella>/data/ohlcv \
    --strategy-config <pinned renquant-strategy-104>/configs/strategy_config.json
```

Read-only: the probe loads the artifact and OHLCV parquet and writes nothing.
It needs the umbrella venv for `xgboost`.

---

## 0. The question, and why the score DB could not answer it

AAPL rose **+19.13%** between 2026-06-26 (`$283.78`) and 2026-07-29 (`$338.08`)
— **rank 8 of 145** in the watchlist cross-section, whose median move over the
same window was **+0.05%**. Its stored score went the other way: **+0.104 →
−0.199** `[VERIFIED — this session, runs.alpaca.db]`.

The per-day feature matrices are not retained, so "which feature did this" is
not answerable from the score DB. It *is* answerable from the artifact, because
the artifact carries `booster_raw_json`. That is what these three probes do.

## 1. Verified in code: the price-ratio families put the current price in the denominator

Not from memory — read at these lines:

| definition | file:line |
|---|---|
| `MA{n} = close.rolling(n).mean() / close` | `RenQuant/scripts/build_alpha158_qlib.py:232` |
| `QTLU{n} = close.rolling(n).quantile(0.8) / close` | `RenQuant/scripts/build_alpha158_qlib.py:239` |
| `MA{n} = win_c.mean() / c_today` | `renquant-base-data/.../alpha158_ops.py:366` |
| `QTLU{n} = win_c.quantile(0.8) / c_today` | `renquant-base-data/.../alpha158_ops.py:373` |

So a rally *mechanically* pushes `MA*`, `QTLU*`, `QTLD*`, `MIN*`, `MAX*`,
`ROC*`, `RSV*` down. Across the rally window 9 of AAPL's top-10 gain features
fell, combined **−7.84σ** (MA20 −1.70σ, QTLU30 −1.30σ, KLEN −1.14σ, MA60
−1.02σ, MIN60 −0.84σ, MAX60 −0.67σ, ROC60 −0.46σ, STD60 −0.36σ, STD20 −0.01σ;
only STD30 +0.66σ) `[VERIFIED — this session]`.

**That σ figure covers 10 of 172 features = 21.8% of total gain. It therefore
does NOT explain the score delta and no total-score attribution is claimed from
it.** It is the motivation for probe B, not a conclusion.

## 2. PROBE A — the model declares 172 features and uses a fraction of them

`[VERIFIED — this session]`

| | |
|---|---:|
| declared `feature_cols` | 172 |
| ever split on by the booster | 106 |
| **never split on** | **66 (38%)** |
| top 10 share of total gain | 23% |
| top 20 | 36% |
| top 30 | 48% |
| top 50 | 68% |

Top 10 by gain: QTLU30 (3.7%), STD60 (3.3%), STD30 (2.9%), MIN60 (2.3%),
KLEN (2.2%), book_to_price (2.0%), gross_profitability (1.8%), MA20 (1.8%),
STD20 (1.6%), days_since_earnings (1.5%).

No single feature reaches 4% of gain. The gain is flat and wide — which is
exactly the shape in which gain stops being informative about behaviour, and
why probe B exists.

## 3. PROBE B — gain is not effect. This is a volatility **and profitability** model.

Average score change from moving one feature `z=−1 → z=+1`, averaged over **400
random z-space baselines** (seed 0). A single probe at the all-mean vector would
not do: trees are interactive, and the all-zero point can sit in leaves where a
feature's splits never fire, which makes a genuinely-used feature look inert.

`[VERIFIED — this session]`

| feature | mean Δscore | sd | frac>0 | |
|---|---:|---:|---:|---|
| **STD60** | **+0.2301** | 0.1717 | 90% | |
| **gross_profitability** | **+0.2098** | 0.1940 | 82% | |
| asset_growth | +0.0434 | 0.0398 | 88% | |
| STD30 | +0.0393 | 0.0307 | 89% | |
| KLEN | +0.0367 | 0.0207 | 97% | |
| CORD60 | −0.0193 | 0.0207 | 6% | |
| surprise_momentum | +0.0176 | 0.0174 | 86% | |
| roe | −0.0175 | 0.0240 | 23% | |
| STD20 | +0.0135 | 0.0145 | 81% | |
| MAX60 | +0.0126 | 0.0108 | 91% | price-ratio |
| days_since_earnings | −0.0079 | 0.0132 | 2% | |
| MIN60 | −0.0072 | 0.0067 | 2% | price-ratio |
| mean_sentiment | −0.0045 | 0.0071 | 3% | |
| QTLU30 | +0.0022 | 0.0037 | 70% | price-ratio |
| BETA60 | −0.0021 | 0.0125 | 34% | |
| book_to_price | −0.0006 | **0.0777** | 48% | |
| ROC60 | +0.0004 | 0.0037 | 8% | price-ratio |
| MA60 | −0.0003 | 0.0008 | 0% | price-ratio |
| SUMN20 | +0.0001 | 0.0033 | 25% | |
| **MA20** | **+0.0000** | **0.0000** | **0%** | price-ratio |

Two findings, and they are different findings:

**(a) The two levers are STD60 and gross_profitability, an order of magnitude
clear of everything else.** `QTLU30` is the single largest gain feature (3.7%)
and its marginal effect is `+0.0022` — 1% of STD60's. `MA20` carries 1.8% of
gain and moves the score **exactly nowhere from any of 400 baselines**
(`mean=0.0000, sd=0.0000, frac>0=0%`).

**(b) Near-zero mean has two causes and they must not be conflated.**
- *Inert* — no effect from any baseline, `sd ≈ 0` too: **ROC60, MA60, SUMN20,
  MA20**. Dead weight.
- *Sign-unstable* — large effect whose direction flips with the baseline, so the
  average cancels: **book_to_price (sd 0.078)**. Not dead; conditional. The
  probe now reports these two classes separately, because reporting
  `book_to_price` as inert would have been wrong.

## 4. PROBE C — the model's dominant feature is truncated **before** it is scored

The realized-vol gate (`60%` annualized) runs upstream of scoring: a name it
drops has no score row at all, so this is invisible from the score DB.

`[VERIFIED — this session, 144 watchlist names with ≥61 OHLCV rows]`

| | |
|---|---:|
| spearman(STD60, annualized vol) | **+0.821** |
| gate DROPS | n=35, median STD60 **0.1586** |
| gate KEEPS | n=109, median STD60 **0.0513** |
| ratio | **3.09×** |

The model rewards high STD60 (`+0.2301`, the largest effect measured). The gate
removes, before scoring, precisely the names carrying 3.09× the kept median of
that feature — cutting at roughly the 60th percentile of the *uncapped
292-ticker panel the model was trained on*. Training and serving see different
supports of the model's most important input.

## 5. So why did AAPL score down through a +19% rally?

**AAPL's STD60 FELL 0.0639 → 0.0469 over the rally window**
`[VERIFIED — this session]`. It was not marked down for rallying. It was marked
down for **rallying calmly** — its price dispersion compressed, and price
dispersion is the model's largest lever.

The price-ratio mechanism of §1 is real in the features and **is not the
operative cause**: those features carry gain but ~zero marginal effect (§3).
Naming the mechanism without probe B would have been a plausible, well-evidenced,
wrong answer.

## 6. Operator verdict, recorded, with one point corrected

The operator's reading (2026-07-29): *"显然是设计缺陷！首先，模型应该是综合考虑动量
和均值回归；第二，172个特征显然太多太傻逼了；第三，172个特征都没有动量因子更傻逼"*

- **Point 2 — CONFIRMED by measurement.** 38% of declared features are never
  split on; top-50 of 172 carry 68% of gain; two features carry the behaviour.
- **Point 3 — CORRECTED.** Momentum features are present (`ROC60`, `MA20`,
  `MA60`, `surprise_momentum`). Three of the four are in the *inert* class.
  That is worse than absence, not better: an absent feature is a visible gap,
  whereas a feature that holds 1.8% of gain and moves the score by `0.0000`
  looks covered on every importance chart the pipeline emits.
- **Point 1 — open, and NOT free.** A prior sealed result has
  `mom_12_1`, `mom_6_1`, reversal, MA200 and 52-week-high **all failing the
  20/60d bar on 104** (memory: canonical-price-trend-no-multiday-edge), with
  *regime-conditioned* momentum named as the surviving lead. §4 supplies a
  mechanism for why an unconditional momentum factor would keep failing here:
  the volatility axis the model already leans on is truncated at serve time, so
  a momentum term fitted on the uncapped support is evaluated on a different
  one. Any "add momentum" change must be preregistered and measured, not
  asserted.

## 7. What this document does NOT claim

- No total score attribution. §1's −7.84σ covers 21.8% of gain.
- No claim that mean-reversion is the wrong objective.
- No recommendation to add momentum features as a fix (see §6, point 1).
- No claim that the vol gate is wrong. It is a risk control with its own
  rationale; §4 measures an interaction with the scorer that was not designed,
  and that is a different statement from "remove the gate".
- No P&L number anywhere. Scores are unitless.
