# ZM/NFLX buy-bias forensics — the mirror image of the META fade (2026-06-10 → 2026-07-10)

**Question (operator):** the live model has repeatedly recommended buying ZM and NFLX over
recent weeks (ZM "bought" 07-07, ZM+NFLX admitted 07-10). Model capability or engineering
problem? Same four-layer rigor as the META studies (orchestrator #473 funnel / #475 STD60
attribution / #476 provenance), for the opposite side of the same tilt.

**Status:** research (read-only forensic; no production path written; no git in the live
umbrella tree or any primary checkout; authored in an isolated orchestrator clone; local
compute only).
**Sources:** `data/runs.alpaca.db` (copied to scratchpad before opening), Alpaca
account/orders/activities API (read-only GET), `logs/daily_104` + `logs/intraday_104`,
`live_state_snapshots`, the live panel artifact + its dated backups (sha-verified against
run-bundle fingerprints), the sealed #475 evidence bundle
(`renquant-artifacts store/experiments/meta-score-attribution-20260711/` — its
`contribs_*.parquet` cover ZM/NFLX on 07-06/07/10 and are reused here unmodified),
`data/sec_fundamentals_daily.parquet`, `data/ohlcv/{T}/1d.parquet`, pinned strategy-104
config `0e5d9891` (fresh clone), renquant-model PR #44 (`vol_trend_features.py` at merge
commit `62286996ea`).

---

## 1. Verdict (bottom line)

**Same chain as META — the mirror image — plus two NEW engineering findings.**

1. **The picks are the long side of the exact #475/#476 dispersion tilt** `[VERIFIED as
   model-representation attribution]`. On every ZM/NFLX admission day, under every model
   vintage live in the window (trained 05-18, 06-21, 07-06 — all three), STD60 is the #1
   positive SHAP contributor, and the STD family contributes MORE than each name's entire
   positive score: ex-STD, ZM is −0.012..−0.028 and NFLX is −0.053..−0.077 — neither
   would have been admitted without the dispersion credit (§4). META was faded for LOW
   STD60 z; ZM/NFLX were admitted for HIGH STD60 z by the same splits.
2. **NFLX is the FTNT mirror — its "dispersion" is trend-confounded** `[VERIFIED
   mechanically]`. 86.5% of NFLX's 60d level-variance is a monotone TREND (a −31%/60d
   crash); its genuine returns-vol is the cross-sectional MEDIAN (51st pct). The model
   credits it +0.08..+0.10 of raw score for "dispersion" it does not have in returns
   space — a crash artifact of the price-in-denominator level-std feature (H3). The #44
   v2 features de-rank NFLX by ~30 percentile points (§5).
3. **ZM is NOT trend-confounded — it is genuinely high-dispersion** (trend share 13%,
   resid-vol 86th pct, ret-vol 70th pct). For ZM the model is faithfully executing the
   learned "chase dispersion" rule itself — the rule whose BULL_CALM record is the
   problem (both live models FAILED BULL_CALM regime-IC and trade-monotonicity — the
   07-06 model's entry-rank spread is **−13.7pp**, the 06-21 model's **−2.3pp** — and
   both reached primary via operator override, §6). The v2 features do NOT de-rank ZM;
   only the gated retrain / override-consequence lane addresses it.
4. **Valuation blindness (base-data #43): ZM yes, NFLX no** `[VERIFIED]`. ZM's
   earnings_yield/book_to_price have NEVER been finite in the serving feed (0/3148 rows;
   median-imputed every day — same class as META). NFLX has real ey/b2p/roe (only
   gross_profitability imputed). Honesty note: fixing ZM's ey would more likely RAISE its
   score (its true earnings yield is above the imputed median) — blindness is a real
   defect but it is NOT what put ZM on the buy list (§5).
5. **Scoreboard — be honest: the picks have not lost money** (§3). Total realized ZM/NFLX
   P/L over 4 weeks = **−$3.68** (one 3-share NFLX round trip). ZM paper recommendations
   are BEATING SPY (+5.0pp / +0.9pp / +3.8pp excess to 07-10); NFLX paper recs mildly
   lag (−0.7pp / −2.2pp); the 07-10 cohort is 0 days old; no 60d label is mature. The
   street agrees with both picks (ZM Moderate Buy ~$115 target = +32%; NFLX Strong Buy
   ~$113 = +54%). The defensible indictment is the REASON for the picks (an unvalidated,
   gate-failed, override-promoted dispersion rule + a trend-confounded feature), not the
   outcomes to date.
6. **NEW finding A — the only realized loss was manufactured by the EXIT plane, not the
   entry** `[VERIFIED]`. NFLX filled 3 sh @ $72.62 (06-24 open); the next morning
   `ModelProtectionExitTask` sold it @ $71.39 at the open (−1.69%) on
   `mu=-0.0505<=tau=0.0 strikes=3/3` from the HOLDING re-score plane — while a same-day
   replay of the live panel booster scores NFLX **+0.066** (bullish). The buy plane and
   exit plane are different models; the per-ticker NFLX admission model carried
   `live_train_end=2026-04-23` (63 days stale). NFLX closed +2.8% above the sale price by
   07-10 (§7.1).
7. **NEW finding B — 06-25 live-tree incident collateral, two production defects**
   `[VERIFIED from logs/snapshots/hashes; producer attribution not re-established]`:
   (a) the prod panel artifact silently REGRESSED from the 06-21 model to the 05-18 model
   between the 06-25 and 06-26 sessions and stayed regressed for 5 sessions
   (06-26..07-02) — a 39-45-day-old model in primary, violating the freshness policy that
   was later used to justify the 07-06 override; unalerted. (b) NFLX's wash-sale stamp
   (`last_sell_dates[NFLX]=2026-06-25`, written 06-25 13:42Z after the loss sale)
   VANISHED from live state by 06-26 — so the 07-10 NFLX buy submission happened 15 days
   into the 30d wash-sale window with the gate blind (it would have been a wash-sale
   re-entry had it filled) (§7.2).
8. **Fact check on the premise: ZM was never actually bought.** All 5 ZM broker orders
   (06-22, 06-23, 06-24-retry, 07-07, 07-10) were canceled before fill — post-close DAY
   orders are canceled by the pre-open gate and only re-submitted if the name re-qualifies
   at the next morning's re-selection, which ZM never did (§2.2). "ZM bought 07-07" was an
   intent notification; the order was canceled 80 minutes later. Economic exposure from
   these picks so far: one day of 3 NFLX shares.

One-sentence root cause: **the same unvalidated, override-promoted dispersion tilt that
faded META is what buys ZM/NFLX — NFLX via the identical trend-confound that made FTNT
rank #1 (a crash reads as "dispersion"), ZM as a faithful execution of the learned rule
on a genuinely-choppy name — while the only realized damage came from exit-plane/state
engineering defects (stale-model whipsaw exit; wash-sale stamp loss; silent model
regression), not from the entries themselves.**

## 2. Layer 1 — FACTS

### 2.1 Every ZM/NFLX scoring/admission in the window `[VERIFIED — runs DB]`

Panel raw score / cross-sectional rank / calibrated 60d mu / outcome. Floor =
`max(0.20, mean+1σ)` of the day's rank_score cross-section; conviction bar mu ≥ 0.03.
Model vintage per session verified from run-bundle `artifact_hashes.panel` + the
`Artifact loaded: … trained=` log line.

| session | model (trained) | ZM raw / rank# / mu → outcome | NFLX raw / rank# / mu → outcome |
|---|---|---|---|
| 06-10 | PatchTST era | −0.181 / — / 0.008 → floor veto | −0.224 / — / −0.013 → floor veto |
| 06-11 | PatchTST era | −0.166 / — / 0.016 → floor veto | −0.143 / — / 0.027 → kelly_zero |
| 06-22 | XGB 06-21 | +0.074 / **#7/81** / 0.031 → **SUBMITTED** | +0.097 / **#6/81** / 0.034 → **SUBMITTED** |
| 06-23 | XGB 06-21 | +0.071 / **#7/81** / 0.031 → **SUBMITTED** | +0.087 / **#6/81** / 0.033 → **SUBMITTED** |
| 06-24 | XGB 06-21 | +0.063 / #4/73 / 0.030 → not selected | +0.106 / holding / 0.034 → held + **9-sh TOP-UP submitted** |
| 06-25 | XGB 06-21 | +0.073 / #2/76 / 0.031 → mu_below_floor | wash-blocked same-day (`loss sale $-3.68 0d ago`) |
| 06-26 | **XGB 05-18 (regressed)** | +0.031 / #24/79 / 0.028 → floor veto | −0.124 / #52/79 / 0.014 → floor veto |
| 06-29..07-02 | XGB 05-18 (regressed) | +0.098..+0.107 / #8-14 / 0.033-0.035 → floor/not-selected | −0.123..−0.153 / #52-55 / 0.012-0.014 → floor veto |
| 07-06 | XGB 07-06 | +0.115 / **#3/35** / 0.035 → not selected | +0.085 / **#4/35** / 0.032 → not selected |
| 07-07 | XGB 07-06 | +0.102 / **#1/33** / 0.034 → **SUBMITTED** | +0.084 / #3/33 / 0.032 → not selected |
| 07-08/09 | XGB 07-06 | not scored (universe outage, 0 candidates — #473 §5) | not scored |
| 07-10 | XGB 07-06 | +0.087 / **#5/85** / 0.032 → **SUBMITTED** | +0.077 / **#6/85** / 0.031 → **SUBMITTED** |

Sizes: every submission was 2-3 whole shares, $147-$219 (the 06-24 NFLX top-up: 9 sh,
$647, never filled). NFLX's mid-window collapse to rank #52-55 is a MODEL-SWAP effect,
not a view change: it coincides exactly with the silent 06-26 regression to the 05-18
booster (§7.2), which scores NFLX negative while both fresh vintages score it positive.

### 2.2 Broker truth — orders and fills `[VERIFIED — Alpaca orders/activities API]`

| submitted (UTC) | order | outcome |
|---|---|---|
| 06-23 04:20 | ZM buy 2 + NFLX buy 3 (from 06-22 run) | both canceled 05:06Z |
| 06-23 21:07 | ZM buy 2 + NFLX buy 3 | canceled 06-24 03:24Z |
| 06-24 05:23 | ZM buy 2 (retry) | canceled 05:39Z |
| 06-24 11:00 | NFLX buy 3 (pre-open resubmission) | **FILLED 3 @ 72.62 at 13:30Z open** |
| 06-24 21:07 | NFLX buy 9 (top-up) | canceled 21:50Z |
| 06-25 13:30 | NFLX SELL 3 (model_protection) | **FILLED 3 @ 71.3934** |
| 07-07 21:36 | ZM buy 2 | canceled 22:56Z same evening |
| 07-10 21:07 | ZM 2 + NFLX 2 (+ FTNT 2, APH 1) | all canceled 07-11 14:04Z (Saturday; next session Monday) |

Net: **ZM 5 buy orders, 0 fills — the position never existed.** NFLX 5 buy orders, 1
fill (3 shares, held ~24h). The cancel-then-morning-reselect loop is a deliberate
mechanism (pre-open cancel gate: `adapters/runner.py:90-108` +
`logs/alerts/preopen_cancel_ledger.jsonl`); ZM never survived the morning re-check
(06-24: `candidate_not_selected` — outranked for the day's slots; 07-08: universe
outage; 07-13: pending). Consequence for reporting: ntfy "BUY ZM" messages are
intent-plane, and the `trades` table records only `buy_pending` rows — nothing
distinguishes filled from canceled intents without hitting the broker API (§8, fix 4).

## 3. Layer 1 — SCOREBOARD (honest, both directions)

Recommendation-cohort forward returns, decision close → 07-10 close, vs SPY
`[VERIFIED — OHLCV cache]`:

| pick | rec date | px → 07-10 | return | SPY | **excess** |
|---|---|---|---|---|---|
| ZM | 06-22 | 84.34 → 89.76 | +6.43% | +1.42% | **+5.01pp** |
| ZM | 06-23 | 86.44 → 89.76 | +3.83% | +2.91% | +0.92pp |
| ZM | 07-07 | 85.68 → 89.76 | +4.76% | +0.97% | **+3.79pp** |
| ZM | 07-10 | 89.76 | — | — | 0 days old |
| NFLX | 06-22 | 72.88 → 73.37 | +0.67% | +1.42% | −0.74pp |
| NFLX | 06-23 | 72.82 → 73.37 | +0.76% | +2.91% | −2.16pp |
| NFLX | 07-10 | 73.37 | — | — | 0 days old |

Executed P/L: NFLX buy 3 @ 72.62 (06-24 open) → protection sell 3 @ 71.3934 (06-25
open) = **−1.69% = −$3.68 realized** — the entire realized cost of four weeks of
ZM/NFLX activity. NFLX then closed 07-10 at 73.37, **+2.77% above the sale price**: the
loss was the exit whipsaw, not the entry (§7.1).

**Honest reading:** at the model's own 60-trading-day horizon NO label in this window is
mature; on partial horizons the ZM picks are winning and the NFLX picks are roughly
flat-to-lagging. The operator's discomfort is not (yet) supported by outcomes — it is
supported by the *reasons* (§4-§6). Do not confuse the two: if these names are cut by
hand while the attribution says "the rule is unvalidated", record that as a judgment
call, not as "the model lost money."

Street cross-check (2026-07, account prices are real 2026 post-split levels): ZM $89.76
vs consensus Moderate Buy, avg target ~$115-117 (+32%,
[stockanalysis.com](https://stockanalysis.com/stocks/zm/forecast/),
[MarketBeat](https://www.marketbeat.com/stocks/NASDAQ/ZM/forecast/),
[TipRanks](https://www.tipranks.com/stocks/zm/forecast)); NFLX $73.37 vs consensus
Strong Buy (24 Buy/8 Hold/0 Sell), avg target ~$113 (+54%,
[stockanalysis.com](https://stockanalysis.com/stocks/nflx/forecast/),
[MarketBeat](https://www.marketbeat.com/stocks/NASDAQ/NFLX/forecast/),
[TipRanks](https://www.tipranks.com/stocks/nflx/forecast)). The street is long BOTH
names — the picks are not street-contrarian; the concern is that the model holds them
for reasons that do not survive inspection.

## 4. Layer 2 — ATTRIBUTION (per-day SHAP, reproduction verified first)

**Method and claims discipline.** Identical to #475 (post-Codex form): standalone replay
of the serving path (`job_panel_scoring.py::ApplyScoresTask` — alpha158 online from the
OHLCV cache, 5 fund as-of + context-median fill, PEAD/SUE, sentiment zeroed under the
BULL_CALM gate, artifact clip/global-z, pinned booster, xgboost `pred_contribs=True`).
All SHAP statements below are **model-representation attribution on an approximate
replay, not causal economic findings** (Ma & Tourani 2020; Apley & Zhu 2020 — see #475
Known Limitations, which apply verbatim here).

**Reproduction fidelity, disclosed:**

- **07-06/07/10 (XGB 07-06):** read directly from the SEALED #475 bundle
  (renquant-artifacts #18; day corr 0.983-0.984, mean|diff| 0.025). Row-level: **ZM
  reproduces EXACTLY (diff 0.000000 all three days)** — its serving row is fully
  cache-deterministic (all price features + imputed ey/b2p; §5.2). NFLX diffs
  −0.019..−0.047 (its real fundamentals moved between the then-serving feed and the
  rebuilt feed) — treat NFLX July SHAP as approximate.
- **06-22/23/24/25 (XGB 06-21, from the byte-verified `bak_prestamp_20260703T110653`
  = run-recorded sha `04d7a381`):** fresh replay, day corr 0.950-0.966, mean|diff|
  0.062-0.077 — coarser than July (the June serving feed differed more from today's
  rebuilt feed); ZM row diffs +0.04..+0.05, NFLX −0.04..−0.05. Signs and rank ordering
  reproduce; magnitudes are ±0.05.
- **06-30/07-02 (XGB 05-18, recovered byte-exact from the umbrella's committed history,
  GitHub ref `c9dc6ce7e3`):** ZM and FTNT reproduce EXACTLY (diff 0.0000); NFLX diff
  ≈ −0.10 (recorded −0.147, replayed −0.057 — same sign, unreliable magnitude).

### 4.1 The decomposition that decides the question

Total raw score vs the STD-family (STD5/10/20/30/60) SHAP total, per admission day:

| day (model) | name | total | STD family | **ex-STD** |
|---|---|---|---|---|
| 06-22 (06-21) | ZM | +0.128 | +0.140 | **−0.012** |
| 06-22 (06-21) | NFLX | +0.050 | +0.117 | **−0.067** |
| 06-23 (06-21) | ZM | +0.112 | +0.140 | **−0.028** |
| 06-23 (06-21) | NFLX | +0.039 | +0.115 | **−0.076** |
| 07-06 (07-06) | ZM | +0.115 | +0.129 | **−0.015** |
| 07-06 (07-06) | NFLX | +0.054 | +0.120 | **−0.066** |
| 07-07 (07-06) | ZM | +0.102 | +0.125 | **−0.023** |
| 07-07 (07-06) | NFLX | +0.065 | +0.118 | **−0.053** |
| 07-10 (07-06) | ZM | +0.087 | +0.111 | **−0.023** |
| 07-10 (07-06) | NFLX | +0.029 | +0.106 | **−0.077** |

Admission that day required raw ≈ +0.07..+0.09 (rank floor) AND mu ≥ 0.03 (their mu
was 0.031-0.035, i.e. barely above the bar). **In this decomposition, remove the STD
family and both names score negative — below the panel mean, nowhere near admission,
on every single day.** The picks are, representationally, pure dispersion-credit picks.

Top single features (07-07 ZM, the rank-#1 day): STD60 **+0.094** (raw 0.0990,
z +0.87), STD30 +0.026, vs MIN60 −0.017, gross_profitability −0.012, CORD60 −0.011.
NFLX (07-10): STD60 **+0.080** (raw 0.1122, z +1.15), STD30 +0.022, vs roe −0.018,
SUMP60 −0.015, MIN60 −0.015. Same features, same splits, opposite side of the same
z-thresholds that faded META (META 07-10 STD60 z −0.04 → −0.09 contribution; #475's
29-split cluster at z ≈ 0.043-0.067 sits exactly between META and ZM/NFLX).

The May-18 (regressed) model is partially different in representation — for ZM it
leans on imputed-vintage `asset_growth` (+0.093) plus STD60 (+0.058); for NFLX it
flips negative via `roe` (−0.083). Its NFLX fade (#52-55 mid-window) is therefore not
"the same model changing its mind" but a different, staler booster with a different
representation (§7.2).

## 5. Layer 3 — HONEST-VIEW CHECK

### 5.1 Are they genuinely high-dispersion, or STD60-confounded like FTNT?

From OHLCV (07-10 snapshot; 144 watchlist names with fresh prices; percentiles are
cross-sectional). `trend%` = share of the 60d level-variance explained by a linear
trend fit (FTNT's #475 figure was "92% trend"); `rvol60` = std of daily returns (v2
F1); `resid60` = detrended level-std / close (v2 F2 `resid_vol_60d`):

| name | STD60 (z, pct) | **trend%** | rvol60 (pct) | resid60 (pct) | roc60 / ret120 |
|---|---|---|---|---|---|
| **NFLX** | 0.1122 (+1.15, 0.81) | **86.5%** | 0.0223 (**0.51**) | 0.0416 (**0.51**) | **−31.0%** / −16.7% |
| **ZM** | 0.0892 (+0.67, 0.72) | **12.9%** | 0.0335 (0.70) | 0.0840 (**0.86**) | +8.9% / +10.1% |
| FTNT | 0.1755 (+2.49, 0.92) | 90.7% | 0.0356 (0.72) | 0.0540 (0.67) | +100.1% / +106.4% |
| APH | 0.0874 (+0.63, 0.70) | 33.0% | 0.0305 (0.65) | 0.0721 (0.81) | +7.0% / +3.1% |
| META | 0.0555 (−0.04, 0.49) | 45.8% | 0.0281 (0.60) | 0.0412 (0.51) | +1.0% / +7.8% |
| MU (honest mover) | 0.2371 (+3.79, 0.99) | 82.0% | 0.0662 (**0.98**) | 0.1014 (0.93) | +110.3% / +190.9% |

(06-22 snapshot agrees: NFLX trend% 76.6, rvol pct 0.48; ZM trend% 32.0, resid pct 0.93.)

- **NFLX = the FTNT mirror, confirmed.** Its 81st-percentile STD60 is 86.5%
  trend — but the trend is a **−31% crash**, not FTNT's +100% rally. In genuine
  returns-vol it is the panel MEDIAN (51st pct both on rvol60 and resid60). The
  +0.08..+0.10 dispersion credit that constitutes its entire positive score is an
  artifact of `std(close levels)/close` reading a monotone fall as "dispersion." The
  model is not "buying the dip" on any fundamental/reversal reasoning visible in the
  attribution — it is paying a dispersion premium to a name whose dispersion is
  fictitious. (Same H3 mechanism as #476, opposite trend sign.)
- **ZM = genuinely choppy, NOT confounded.** Trend share 12.9% (a rangebound
  84→90→83→90 whipsaw); resid-vol 86th pct, ret-vol 70th pct, downside semivol 66th
  pct. An honest returns-based feature set still calls ZM high-dispersion. So ZM's
  admission is the *learned rule itself* operating as designed — and that rule is the
  one the WF gate scored anti-predictive in BULL_CALM on simulated trades
  (entry-rank spread −13.7pp, §6). Whether "long genuine dispersion" has any BULL_CALM
  edge is exactly the unvalidated H2 question; nothing here validates it either way.
- MU control: an honest mover (98th pct returns-vol) — the feature families agree on
  it; note MU is where the tilt and reality coincide.

### 5.2 Valuation blindness (base-data #43 axis) `[VERIFIED on the live feed]`

`data/sec_fundamentals_daily.parquet` (axis through 2026-07-10):

| feature | ZM | NFLX |
|---|---|---|
| earnings_yield | **NEVER finite (0/3148)** → imputed cross-sectional median 0.0079 daily | real, 0.0171 |
| book_to_price | **NEVER finite (0/3148)** → imputed ~0.119 | real, 0.1007 |
| gross_profitability | real, 0.0793 | imputed (no GrossProfit tag), 0.0811 |
| roe / asset_growth | real (0.0427 / 0.1105) | real (0.1697 / 0.1714) |

- **ZM is valuation-blind on the price-ratio axis — the META class of hole** (multi-class
  share-tag / shares-wipe lineage, base-data #43). This is why ZM's replay is
  byte-exact: its served row contains no live fundamental that can drift.
- **Directional honesty:** on 07-07 the imputed ey contributed only −0.007 to ZM. ZM's
  true earnings yield at $89.76 is ABOVE the imputed median (ZM is GAAP-profitable with
  large net cash), so serving real ratios would, if anything, have made ZM look
  *cheaper* and scored it *higher* in this model's representation. #43 is the right fix
  for input honesty and it does cover ZM — but it is NOT the mechanism that bought ZM,
  and nobody should expect it to suppress these picks.
- **NFLX is not valuation-blind** (only gp imputed, −0.008 contribution). Its problem is
  §5.1, not #43.

## 6. Governance (H4) — both models in the window were override promotions `[VERIFIED from artifact metadata]`

- **XGB trained 2026-06-21** (live 06-22..06-25; the model that submitted the June
  ZM/NFLX buys and the NFLX fill): `gate_verdict_before_override=False`;
  `sanity_reason: FAIL regime sanity IC: BULL_CALM,CHOPPY` (BULL_CALM mean IC +0.0234,
  hit 0.534); `trade_monotonicity: FAIL in BULL_CALM` (spearman −0.068, top-vs-bottom
  entry-rank spread **−2.31pp**, n=82); promoted via
  `operator_authorized_override=True`, 2026-06-22T21:13Z, reason "全放宽 + 上 XGB …
  disclosed risks: weak_BULL_CALM_ic_0.0149, edge_partly_BEAR_concentrated,
  lags_SPY_APY_0of3".
- **XGB trained 2026-07-06** (live 07-06..now; the model that ranked ZM #1 on 07-07 and
  admitted ZM+NFLX on 07-10): `manual_override=true` (freshness promote per the NO-model
  >28d policy) after failing wf_reason, sanity (genuine IC +0.008), BULL_CALM regime IC
  (placebo-genuine −0.0295) and BULL_CALM trade-monotonicity (spearman −0.077, spread
  **−13.67pp**, n=110) — re-verified directly from the live artifact this session
  (matches #476 §4).
- **XGB trained 2026-05-18** (live 06-26..07-02 via the silent regression §7.2): not
  promoted at all in that window — it re-entered primary through a live-tree file
  reversion, with no gate event of any kind.

Every ZM/NFLX admission in four weeks was therefore produced by a model that either
failed its BULL_CALM checks and was overridden, or re-entered production without any
promotion event. The gate keeps measuring the exact behavior observed here (long-side
rank inversion in BULL_CALM); the override lane keeps shipping it. That is #476-H4 /
F4 (#479) territory, unchanged — this document adds the long-side confirmation.

## 7. NEW engineering findings (not in the META chain)

### 7.1 Exit-plane whipsaw manufactured the only realized loss `[VERIFIED]`

Timeline (all times UTC): 06-24 11:00 NFLX buy resubmitted → 13:30 filled @72.62. The
holding's re-scored expected_return then fell 0.0675 (06-24 morning state) → −0.0087
(06-24 evening run) → **−0.0505 (06-25 13:30Z run)** →
`ModelProtectionExitTask [NFLX]: EXIT thesis_breached mu=-0.0505<=tau=+0.0000
strikes=3/3` (`logs/intraday_104/2026-06-25.log:220`) → sold @71.3934 at the open —
the local low; NFLX closed 07-10 +2.77% above it.

The protection mu is the HOLDING re-score (`task_sell.py`: `hs.expected_return`, set in
the intraday sell pass — per-ticker/NGBoost lineage, NOT the panel). The per-ticker
NFLX admission model in that window: `trained_date=2026-04-30`,
`live_train_end=2026-04-23` (63 days stale; the same vintage class that later collapsed
the whole universe on 07-08, #473 §5). The panel booster that had JUST bought NFLX
scores it +0.066 (replayed) on the same 06-25 data — the buy plane and the exit plane
disagreed by ~0.12 raw, and the stale plane won, at market open, on a 1.3%-down day,
inside 24h of entry. A 3-strike debounce did not help because the strikes accrued on
intraday re-evaluations of the SAME stale view (3 evaluations across ~18h).

This is a plane-coherence defect, not a bad model opinion: whatever the dispersion
rule's merits, buying on model A's +0.10 and force-selling 24h later on model B's
−0.05 (model B being 2 months stale) converts noise into realized losses and resets
wash-sale clocks (which then got lost — §7.2b).

### 7.2 The 06-25 live-tree incident silently regressed production state `[VERIFIED effects; producer not re-attributed]`

Between the 06-25 and 06-26 sessions (the window of the known 2026-06-25 live-tree git
checkout/recovery incident — memory "recovery checkout clobbers code hotfixes"; 18
intraday FAILs on 06-26):

- **(a) The prod panel artifact regressed 06-21 → 05-18.** Run bundles: sessions
  06-22..25 stamp panel sha `04d7a381` (trained 06-21, byte-recovered from
  `bak_prestamp_20260703T110653`); sessions 06-26..07-02 stamp `5ce63326`, and the
  06-26+ logs read `Artifact loaded: … trained=2026-05-18`. The recorded 06-26..07-02
  scores replay byte-consistently under the COMMITTED 05-18 artifact (GitHub
  `c9dc6ce7e3`: ZM/FTNT reproduce to 0.0000) and NOT under the 06-21 booster (panel
  corr 0.32) — i.e. prod reverted to the last *committed* artifact vintage, exactly
  what a working-tree checkout does to an uncommitted deployed file. A 39-45-day-old
  model held primary for 5 sessions, unalerted, in direct conflict with the 28d
  freshness policy — and by 07-03 04:06 PT the 06-21 file was back (the prestamp backup
  captured it), meaning production flipped models twice more without any promotion or
  alert. NFLX's mid-window rank collapse (#6 → #52) was this swap, not a view change.
- **(b) NFLX's wash-sale stamp was erased.** `STATE-EXT-SELL: NFLX disappeared from
  broker without runner sell — stamping wash-sale clock today (2026-06-25)`
  (`intraday_104/2026-06-25.log:452`); snapshot 06-25 13:42Z contains
  `last_sell_dates[NFLX]=2026-06-25` (10 keys). The next snapshot (06-26 17:00Z) has 7
  keys and **no NFLX**; the live file today still has no NFLX. The 06-25 loss sale
  (−$3.68) therefore protects nothing after day 0: the **07-10 NFLX buy submission went
  out 15 days into the 30d window with `blocked_wash=0`** — only the unrelated order
  cancel (§2.2) prevented an actual wash-sale re-entry. Note this is a *different* hole
  than the #428 stamp-date bug (fixed): here the stamp was written correctly and then
  lost with the rest of the 06-25/26 state churn; wash-sale enforcement currently has a
  single, mutable, unreconciled point of failure (`live_state.last_sell_dates`).

### 7.3 Intent-vs-fill observability

The `trades` table records `buy_pending` rows only; no fill/cancel outcome row exists
(NFLX 06-22/23 shows 3 pending rows → 1 actual fill; ZM shows 5 pendings → 0 fills;
the 06-25 NFLX sell fill exists only at the broker). Any downstream consumer of the
DB (or of ntfy messages) systematically overcounts "buys". This forensic had to go to
the broker API to establish basic facts — that lookup belongs in the pipeline.

## 8. Layer 4 — fix mapping

**Covered by the EXISTING stack (no new mechanism needed):**

1. **renquant-model #44 (vol_trend_v2, MERGED)** — F1 `ret_vol_{20,60}d` /
   `ret_semivol_down_60d`, F2 `resid_vol_60d` + trend interactions. Quantified on these
   names (§5.1): switching STD60 → ret_vol/resid_vol **de-ranks NFLX by 30 percentile
   points** (0.81 → 0.51 on both) — it would no longer read as high-dispersion at all;
   FTNT de-ranks 20-26pp; META's fade-side distortion also shrinks (0.49 → 0.60/0.51,
   i.e. it stops looking "calm"). **ZM is essentially unmoved (0.72 → 0.70/0.86)** —
   correctly, because its dispersion is real. The preregistered baseline-vs-v2
   comparison (#476 §7) remains the required next step before any retrain promotes.
2. **F4 / #479 (override consequences)** — §6 shows the long side of the same pattern:
   two override promotions + one un-promoted regression, all carrying BULL_CALM
   long-side rank inversion. Nothing new to design; this document is additional
   evidence for regime-scoped consequences on the weekly rail.
3. **base-data #43** — covers ZM's never-finite ey/b2p (META-class hole). Honest
   expectation set in §5.2: it fixes input integrity; it will not suppress ZM picks.
4. **Gated retrain (freshness-vs-gate policy)** — unchanged; note the irony recorded in
   §7.2a: the freshness policy used to justify overrides was itself violated for 5
   sessions by the silent regression, unalerted.

**NOT covered — new fixes this document proposes (owners per subrepo model):**

5. **Exit/entry plane coherence** (owner: renquant-pipeline). ModelProtectionExitTask
   consumes a holding re-score from a model plane that can be months staler than the
   panel that bought the name. Minimum: stamp the mu-producing model's identity+vintage
   on every protection exit record, fail-closed the protection mu when its producer is
   past the freshness gate (the 07-08 universe gate already fail-closes admissions on
   exactly this), and alert on buy-plane/exit-plane sign disagreement at exit time.
6. **Durable wash-sale ledger** (owner: renquant-pipeline runner state, with the
   orchestrator monitor as the checker). `last_sell_dates` must be reconcilable from
   broker fills (the #428 fill-date logic already fetches them): a daily invariant
   check "every broker loss-sale in the last 30d has a live stamp" would have caught
   the 06-26 erasure within a day. Wash-sale enforcement should not be erasable by
   state churn.
7. **Model-identity regression tripwire** (owner: renquant-orchestrator monitor layer,
   sibling of the #473 §8 universe-collapse alert). Alert whenever the loaded panel
   `trained_date`/sha changes without a promotion event, or regresses to an older
   vintage. Both the 06-26 regression (5 sessions dark) and the 07-03 flip-back would
   have paged.
8. **Fill-truth in the runs DB** (owner: renquant-execution/pipeline). Record order
   outcome (filled/canceled + fill px) against each `buy_pending`/`sell_pending` row;
   ntfy buy notices should say "submitted (fills at next open pending pre-open
   re-check)".

## 9. Known limitations

- All SHAP statements are model-representation attribution on approximate replays
  (fidelity disclosed per vintage in §4); the #475 limitations (off-manifold PDP,
  correlated-feature non-identifiability, no conditional ALE, no rank-order/gate
  agreement seal for the June replays) carry over verbatim. ZM's July rows are the
  exception: byte-exact reproduction.
- The scoreboard is horizon-immature (no 60d label matures before ~mid-September for
  the July cohort); §3's "picks have not lost money" is a statement about partial
  horizons, not a validation of the rule. The #476 §7 preregistered design remains the
  only way to score the rule itself.
- §7.2's producer attribution (WHO reverted the tree on 06-25 and re-restored on 07-03)
  is inferred from the known incident class + file/hash/log evidence of effects; the
  mutation itself is not re-attributed here (same posture as #473 §5 on the 07-08
  outage).
- The trend-share/percentile computations use today's OHLCV cache for historical
  as-of dates (same re-adjustment caveat as #475's replay).
- June replay context used the current pinned watchlist (145) rather than the June-era
  config; this affects context-median fills only (disclosed in the fidelity numbers).

## 10. Reproduction inventory (read-only; scratchpad only)

- Inputs: `data/runs.alpaca.db` (copied before opening), Alpaca `/v2/orders` +
  `/v2/account/activities/FILL` (GET only), `logs/daily_104/*`, `logs/intraday_104/*`,
  `panel-ltr.alpha158_fund.json` + `.bak_prestamp_20260703T110653` (sha-matched to run
  bundles: `5211f6be…`, `04d7a381…`), committed 05-18 artifact fetched from GitHub ref
  `c9dc6ce7e3` (sha `5a1e4e14…`; run-recorded `5ce63326…` is its re-stamped live
  variant — booster-level identity established by exact score replay, not file hash),
  sealed #475 bundle (renquant-artifacts #18), `sec_fundamentals_daily.parquet`,
  `ohlcv/{T}/1d.parquet`, strategy-104 pin `0e5d9891` (fresh clone),
  renquant-model `vol_trend_features.py` @ `62286996ea`.
- Method: `reproduce_meta.py` from the sealed #475 bundle, re-pointed at the June/May
  artifacts and June run-ids (2-line diff each); v2 features computed with the merged
  #44 module verbatim; trend-share = 1 − var(OLS residuals)/var(levels) on the 60d
  close window; scoreboard from the OHLCV cache closes.
- No production path written; no git operation in the live umbrella tree or any primary
  checkout (this doc authored in a fresh isolated clone); no Modal/cloud compute; the
  only network calls were read-only GETs (Alpaca, GitHub raw) and two WebSearch queries
  for the street consensus.
