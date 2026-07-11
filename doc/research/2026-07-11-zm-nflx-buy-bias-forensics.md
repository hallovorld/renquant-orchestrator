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

> **2026-07-11 revision note.** Codex (CHANGES_REQUESTED, orchestrator#484) found the
> original version of this document repeatedly promoted approximate attribution and thin
> realized samples into causal/trading conclusions. Five specific gaps: (1) SHAP
> subtraction (the "ex-STD" score) is not a counterfactual rescore — it does not by
> itself prove either name would fail the admission floor without an exact serving-path
> replay, a SHAP additivity-residual check, and a feature intervention that preserves the
> remaining feature vector; (2) the post-hoc `vol_trend_v2` recomputation cannot
> establish what a trained model would rank NFLX as, absent the actual trained v2
> artifact, an immutable training vintage, the exact scoring config, and a
> full-population OOS result; (3) the claim that recovering ZM's valuation ratios would
> likely raise its score is not established — the model's transform, imputation
> behavior, feature interactions, and retraining response to real fundamentals are
> unknown; (4) one realized NFLX round trip and a handful of immature paper cohorts
> cannot diagnose an exit defect or rank a strategy, and street analyst targets are not
> evidence for a pipeline investigation; (5) claims resting on local wash-sale/exit-plane
> state were not consistently separated from broker-truth claims that would require
> broker reconciliation. This revision reframes every SHAP-subtraction claim as an
> attribution hypothesis (new §4.0); removes the v2-recomputation "de-rank"/remedy
> language and keeps only the descriptive feature-value fact (§5.1, §8); removes the ZM
> valuation score-direction claim (§5.2); rewrites the scoreboard section to state its
> population, horizon, cost/slippage, corporate-action, and benchmark gaps explicitly and
> removes the street-target citations entirely (§3); and re-labels every local-state
> finding to separate it from any broker-truth conclusion it does not establish (§7).
> **No runtime gate, retrain, or strategy-flag change should follow from this document
> until a preregistered, full-cross-section experiment (#476 §7) validates the
> hypothesis** — unchanged from the original PR body, repeated here per Codex's final
> instruction. See §9 for the itemized correction mapped to each of Codex's five points.

## 1. Verdict (bottom line — hypotheses, not a validated root cause; see §9)

**Same chain as META — the mirror image — plus local engineering findings.**

1. **Hypothesis: the picks are the long side of the exact #475/#476 dispersion tilt**
   `[attribution hypothesis on an approximate replay, NOT a counterfactual proof — see
   §4.0]`. On every ZM/NFLX admission day, under every model vintage live in the window
   (trained 05-18, 06-21, 07-06 — all three), STD60 is the #1 positive SHAP contributor
   in this replay, and the STD family's SHAP credit exceeds each name's entire replayed
   score: ex-STD, ZM is −0.012..−0.028 and NFLX is −0.053..−0.077. **This is SHAP-
   subtraction attribution on this model's current representation, not a rescore of an
   actual model trained or re-scored without STD** — no exact serving-path replay, SHAP
   additivity-residual check, or feature intervention preserving the remaining feature
   vector was performed (§4.0). It does not prove either name would fail the admission
   floor absent the dispersion credit; it is a hypothesis consistent with the same
   STD60 mechanism §475/§476 documented on the fade side. META was faded for LOW STD60 z;
   ZM/NFLX were admitted for HIGH STD60 z by the same splits — that symmetry is the
   observation, not a proof of counterfactual admission failure.
2. **NFLX is the FTNT mirror — its "dispersion" is trend-confounded** `[VERIFIED
   mechanically on the feature definitions; NOT a trained-model rank or remedy result]`.
   86.5% of NFLX's 60d level-variance is a monotone TREND (a −31%/60d crash); its
   genuine returns-vol is the cross-sectional MEDIAN (51st pct). The model credits it
   +0.08..+0.10 of raw score for "dispersion" it does not have in returns space — a
   crash artifact of the price-in-denominator level-std feature (H3), same mechanism as
   #476. **Recomputing NFLX's raw feature VALUES under the #44 v2 definitions
   (ret_vol_60d/resid_vol_60d) moves its cross-sectional percentile from 81st to 51st
   (§5.1) — this is a fact about the recomputed numbers, not a remedy or a rank result.**
   #44 ships these features disabled behind an experiment-id gate; no model has been
   trained on them, so there is no trained v2 artifact, no immutable training vintage,
   no scoring config, and no full-population OOS result to say what a trained scorer
   would actually rank NFLX as (§8).
3. **ZM is NOT trend-confounded — its recomputed dispersion features stay high**
   (trend share 13%, resid-vol 86th pct, ret-vol 70th pct). For ZM the model is executing
   the same learned "chase dispersion" pattern (§4.0) — the pattern whose BULL_CALM
   record is the problem (both live models FAILED BULL_CALM regime-IC and trade-
   monotonicity — the 07-06 model's entry-rank spread is **−13.7pp**, the 06-21 model's
   **−2.3pp** — and both reached primary via operator override, §6). ZM's recomputed v2
   feature values barely move (72nd → 70th/86th pct, §5.1) — descriptively consistent
   with real dispersion, not itself a validated re-rank result (same caveat as item 2);
   only the gated retrain / override-consequence lane addresses ZM, and that lane remains
   unexecuted.
4. **Valuation blindness (base-data #43): ZM's ey/b2p are never finite; NFLX's are real**
   `[VERIFIED that ey/b2p are never finite for ZM; NOT established what serving real
   values would do to its score]`. ZM's earnings_yield/book_to_price have NEVER been
   finite in the serving feed (0/3148 rows; median-imputed every day — same class as
   META). NFLX has real ey/b2p/roe (only gross_profitability imputed). **This document
   does not establish, and does not claim, what direction serving real ey/b2p would move
   ZM's score** — the model's transform, imputation behavior, feature interactions, and
   retraining response to real (vs. imputed) fundamentals are not tested here. #43 is a
   real input-integrity defect on its own terms; it should not be read as a
   pick-suppression or pick-promotion mechanism in either direction (§5.2).
5. **No performance or exit-quality conclusion can be drawn from this sample** (§3). The
   only realized outcome is one 3-share NFLX round trip (−$3.68); the rest is 3 ZM and 2
   NFLX paper-recommendation cohorts, all under 20 days old against the model's own 60d
   horizon, with no out-of-sample holdout, no population beyond these 2 names, no
   slippage/cost accounting beyond the two real fills, and no corporate-action handling
   tested. §3 states the realized fill prices and cohort-return arithmetic as facts, but
   explicitly declines to characterize the strategy, the exit, or the rule as
   winning/losing/well- or badly-timed on this basis. The defensible indictment remains
   the REASON for the picks (an unvalidated, gate-failed, override-promoted dispersion
   pattern + a trend-confounded feature), not any performance read of these seven
   pick-days.
6. **The local exit-plane record shows a stale-model disagreement at the sell decision**
   `[the fills and the local mu/tau/strikes log line are VERIFIED; the "buy plane scored
   +0.066" comparison is an approximate REPLAY, not a recorded live score — see §7.1]`.
   NFLX filled 3 sh @ $72.62 (06-24 open, broker-confirmed); the next morning
   `ModelProtectionExitTask` sold it @ $71.39 at the open (−1.69%, broker-confirmed) on
   `mu=-0.0505<=tau=0.0 strikes=3/3` from the HOLDING re-score plane (a local log line,
   verified). A same-day REPLAY of the live panel booster (same June reproduction
   fidelity as §4, disclosed corr 0.950-0.966) scores NFLX +0.066 — this is a
   reconstructed counterfactual, not NFLX's actual recorded panel score that day (NFLX
   was wash-blocked from panel admission on 06-25, so it was not live-scored that day).
   The buy plane and the local per-ticker exit plane are different models; the
   per-ticker NFLX admission model carried `live_train_end=2026-04-23` (63 days stale).
   NFLX closed +2.8% above the sale price by 07-10 — a fact about the subsequent price
   path, not a performance verdict on the exit (§3). This supports a local plane-
   coherence finding, not a claim requiring broker reconciliation beyond the fill prices,
   which are independently confirmed (§7.1).
7. **06-25 live-tree incident collateral, two LOCAL-STATE defects** `[VERIFIED as
   local-state/ledger facts from logs/snapshots/hashes; producer attribution not
   re-established; NOT a broker-reconciled claim — see §7.2]`: (a) the prod panel
   artifact (a local served file) silently REGRESSED from the 06-21 model to the 05-18
   model between the 06-25 and 06-26 sessions and stayed regressed for 5 sessions
   (06-26..07-02) — a 39-45-day-old model in primary, violating the freshness policy
   later used to justify the 07-06 override; unalerted. This is a file/artifact-identity
   fact (byte-exact replay match to the committed 05-18 artifact), not a broker-side
   claim. (b) NFLX's local wash-sale stamp (`last_sell_dates[NFLX]=2026-06-25`, written
   06-25 13:42Z after the loss sale) VANISHED from local live state by 06-26 — a verified
   ledger-integrity fact. Because of it, the internal wash-sale gate had no record to
   block against when the 07-10 NFLX buy was submitted 15 days into the 30d window
   (`blocked_wash=0`). **This is a ledger-integrity near-miss, not a broker-side
   wash-sale event: the order did not fill** (§2.2, canceled 07-11), so no actual
   wash-sale re-entry occurred this time; confirming what a fill would have meant would
   require broker-side reconciliation not performed here (§7.2).
8. **Fact check on the premise: ZM was never actually bought** `[VERIFIED — Alpaca
   orders/activities API, §2.2]`. All 5 ZM broker orders (06-22, 06-23, 06-24-retry,
   07-07, 07-10) were canceled before fill — post-close DAY orders are canceled by the
   pre-open gate and only re-submitted if the name re-qualifies at the next morning's
   re-selection, which ZM never did (§2.2). "ZM bought 07-07" was an intent notification;
   the order was canceled 80 minutes later. Economic exposure from these picks so far:
   one day of 3 NFLX shares.

One-sentence summary (hypothesis, not a verdict): **the same STD60 dispersion-attribution
pattern that #475/#476 documented on the fade side is also present, symmetrically, on
every ZM/NFLX admission day — NFLX via the same trend-confound mechanism that made FTNT
rank #1 in #476 (a crash reads as "dispersion" in this feature's definition), ZM on a
name whose recomputed dispersion features look high regardless of definition — while the
only REALIZED dollar loss traces to a local exit-plane/state-tracking discrepancy (a
stale per-ticker exit model; a lost local wash-sale stamp; a silently regressed local
artifact), not to the entries themselves. None of this is established as a causal or
counterfactual proof, and no runtime, gate, or strategy change should follow from it
before the preregistered cross-section experiment (#476 §7) runs (§9).**

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

## 3. Layer 1 — SCOREBOARD (facts only; no performance conclusion drawn — Codex point 4)

**Scope stated explicitly, per Codex's review:** population = 2 names (ZM, NFLX); 7
total recommendation-cohort pick-days (4 ZM, 3 NFLX) plus 1 realized round trip;
pre-entry horizon = 0-19 calendar days against the model's own 60-**trading**-day label
(none of the 7 cohorts has a matured label); costs/slippage = only the two real fills
(§2.2) carry actual execution prices — the paper-cohort "returns" below use unadjusted
daily closes with no slippage, commission, or borrow-cost model; corporate actions = not
audited for ZM/NFLX/SPY over this window; benchmark = SPY close-to-close **price**
return (not total return, so not dividend-adjusted); no out-of-sample holdout exists —
every number below is in-sample by construction (post-hoc on names the model itself
selected). **Absent all of the above, no performance, exit-quality, or strategy-ranking
conclusion can be drawn from this sample.** What follows are the raw facts only.

Recommendation-cohort forward price returns, decision close → 07-10 close, vs SPY close
`[VERIFIED — OHLCV cache; price return only, no cost/slippage/corporate-action
adjustment]`:

| pick | rec date | px → 07-10 | return | SPY | excess |
|---|---|---|---|---|---|
| ZM | 06-22 | 84.34 → 89.76 | +6.43% | +1.42% | +5.01pp |
| ZM | 06-23 | 86.44 → 89.76 | +3.83% | +2.91% | +0.92pp |
| ZM | 07-07 | 85.68 → 89.76 | +4.76% | +0.97% | +3.79pp |
| ZM | 07-10 | 89.76 | — | — | 0 days old |
| NFLX | 06-22 | 72.88 → 73.37 | +0.67% | +1.42% | −0.74pp |
| NFLX | 06-23 | 72.82 → 73.37 | +0.76% | +2.91% | −2.16pp |
| NFLX | 07-10 | 73.37 | — | — | 0 days old |

Realized (broker-confirmed) fills: NFLX buy 3 @ 72.62 (06-24 open) → protection sell 3 @
71.3934 (06-25 open) = **−1.69% = −$3.68 realized**, the only executed P/L from four
weeks of ZM/NFLX activity. NFLX closed 07-10 at 73.37, i.e. above the sale price — a
fact about that one trade's subsequent price path, not a performance verdict on the exit
decision (see §7.1 for what is and is not established about why the exit fired).

**What this section does NOT establish:** whether the dispersion pattern "works,"
whether the exit was well- or badly-timed net of costs, or how ZM/NFLX would perform
under a proper walk-forward, cost-adjusted, matured-label design. The #476 §7
preregistered cross-section comparison is the only design in this document set that
could answer that; it has not been run. A prior version of this section included a
"street cross-check" citing analyst price targets for ZM/NFLX — that citation has been
removed. Street consensus price targets are not evidence for a pipeline/model
investigation regardless of direction.

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

### 4.0 What the ex-STD subtraction is, and is not `[Codex point 1]`

**The "ex-STD" column in §4.1 is a SHAP-subtraction attribution exercise on an
approximate replay of the current model — it is not a counterfactual rescore.**
Specifically, none of the following was done:

- **No exact serving-path replay.** The reproduction fidelity disclosed above (July: ZM
  exact, NFLX diff −0.019..−0.047; June: both names diff ±0.04..±0.05; May: ZM/FTNT
  exact, NFLX diff ≈−0.10) means the "total" column in §4.1 is itself an approximate
  reproduction of the live recorded score, not the live recorded score.
- **No SHAP additivity-residual check.** This document does not verify that the sum of
  all per-feature SHAP contributions plus the base value reconstructs the replayed
  prediction to a stated tolerance; the STD-family total is subtracted from the replayed
  total, not cross-checked against an independent additivity residual.
- **No feature intervention preserving the remaining feature vector.** Subtracting the
  STD family's SHAP credit assumes the rest of the feature vector's contribution would
  be unchanged if STD were actually removed from the model. Under correlated features
  (STD60 correlates with other trend/vol features in the recipe — the same point #475's
  Known Limitations item (d) and #476's H3 caveat make), this assumption is not valid:
  SHAP explains this fitted model's current representation; it does not predict what a
  model *without* STD, or given a masked/imputed STD input, would score these names.
  Establishing that requires an actual frozen-model ablation (retrain or masked re-score
  preserving the joint feature distribution) — not performed here.

**Replay error vs. the actual admission margin — a coarse cross-check computed from this
document's own numbers, not a precise one (the admission floor itself is only known to
±0.02 as an approximate raw-score equivalent, §2.1):** on NFLX's three admission days,
the LIVE RECORDED raw score (§2.1, ground truth, not replayed) was +0.097 (06-22),
+0.087 (06-23), +0.077 (07-10) against a stated floor of "raw ≈ +0.07..+0.09" — i.e.
NFLX's actual admission margin over the floor's stated range was already thin-to-negative
on two of its three admission days (06-23 and 07-10), before any STD attribution is
applied. The disclosed replay/reproduction noise for NFLX (±0.02-0.05 in July, ±0.04-0.05
in June) is the **same order of magnitude** as this margin. This means the ex-STD numbers
in §4.1 (computed on the replayed total, which can differ from the live recorded score by
an amount comparable to NFLX's own admission margin) should be read as **consistent
with**, not proof of, "would not clear the floor" — the noise band alone is material at
this margin, independent of the deeper counterfactual-validity problem above. ZM's July
admissions reproduce exactly (diff 0.000000, disclosed above), so this specific noise
concern does not apply to ZM's 07-07/07-10 rows; it does apply to ZM's June rows
(disclosed diff +0.04..+0.05) and to all of NFLX's rows.

**What this establishes:** on this approximate replay, the STD family is consistently
the dominant positive contributor, and removing its credit leaves both names negative —
an attribution **hypothesis** consistent with the same STD60 mechanism #475/#476
documented on the fade side. **What it does not establish:** that either name would
actually fail to be admitted by a model trained or re-scored without the STD family, or
by the real serving path at its full reproduction fidelity. That requires the
frozen-model ablation and additivity-residual work above, which is the same outstanding
item #476 §7 already scoped for the preregistered experiment.

### 4.1 The decomposition that motivates the hypothesis (see §4.0 for what it does not establish)

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
was 0.031-0.035, i.e. barely above the bar — itself a thin margin, see §4.0). **In this
decomposition, remove the STD family's SHAP credit and both names' replayed total scores
negative — below the panel mean, on every single day.** Per §4.0, this is an attribution
hypothesis about the model's current representation, not a proof that either name would
fail admission without STD; read the picks as **representationally STD-dominated on
this replay**, not as proven "pure dispersion-credit picks" in a counterfactual sense.

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

**What this table is, and is not (Codex point 2):** `trend%`/`rvol60`/`resid60` are
recomputed feature **values** under the v2 definitions, placed within today's
cross-sectional distribution — they describe where NFLX/ZM/FTNT/META would sit
numerically under an alternative feature definition, computed directly from OHLCV. They
are not the output of any trained model, and they do not by themselves establish a
re-rank or a remedy result (§8) — no model has been trained on these features (#44 ships
them disabled behind an experiment-id gate).

- **NFLX = the FTNT mirror, mechanically.** Its 81st-percentile STD60 is 86.5%
  trend — but the trend is a **−31% crash**, not FTNT's +100% rally. In genuine
  returns-vol it is the panel MEDIAN (51st pct both on rvol60 and resid60). On this
  attribution, the +0.08..+0.10 dispersion credit that constitutes its entire positive
  replayed score is consistent with an artifact of `std(close levels)/close` reading a
  monotone fall as "dispersion" — the same H3 mechanism as #476, opposite trend sign;
  this is the same attribution-hypothesis-not-proof caveat as §4.0, applied to this
  specific mechanism.
- **ZM's recomputed dispersion features stay genuinely high, unlike NFLX's.** Trend
  share 12.9% (a rangebound 84→90→83→90 whipsaw); resid-vol 86th pct, ret-vol 70th pct,
  downside semivol 66th pct. An honest returns-based feature set still calls ZM
  high-dispersion, unlike NFLX. So on this attribution, ZM's admission is consistent
  with the same STD-dominance pattern operating on a name whose dispersion is not a
  trend artifact — not a proof that this specific pattern, rather than some other
  mechanism, explains ZM's admission (§4.0). That pattern is the one the WF gate scored
  anti-predictive in BULL_CALM on simulated trades (entry-rank spread −13.7pp, §6).
  Whether "long genuine dispersion" has any BULL_CALM edge is exactly the unvalidated H2
  question from #476; nothing here validates it either way.
- MU control: an honest mover (98th pct returns-vol) — the feature families agree on
  it; note MU is where the tilt and reality coincide.

### 5.2 Valuation blindness (base-data #43 axis) `[VERIFIED that ey/b2p are never finite
for ZM; NOT established what serving real values would do to ZM's score — Codex point 3]`

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
- **What this document does NOT establish (Codex point 3):** a prior version of this
  section stated that recovering ZM's real ey/b2p "would likely raise its score." That
  claim is removed. On 07-07 the imputed ey's SHAP contribution to ZM was −0.007 in this
  replay — a fact about the imputed value's attribution on that one day, not a statement
  about what a real (non-imputed) value would produce. The model's transform,
  imputation-vs-real interaction effects (ey/b2p may interact non-linearly with
  sector/size/other fundamental features), and its retraining response if real
  fundamentals were available for ZM's full history are not established by anything in
  this document. #43 is a real input-integrity defect on its own terms (ZM's served row
  is missing two fundamental axes entirely); this document takes no position on whether
  fixing it would raise, lower, or not materially move ZM's score.
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

### 7.1 Local exit-plane state shows a stale-model disagreement at the sell decision
`[fills, log line, and per-ticker model vintage: VERIFIED local-state/broker facts; the
"buy plane +0.066" figure is a REPLAY, not a recorded score — Codex point 5]`

Timeline (all times UTC), each step labeled by evidence class:

- 06-24 11:00 NFLX buy resubmitted → 13:30 **FILLED @72.62** `[broker-confirmed, §2.2]`.
- The holding's re-scored expected_return (local state) fell 0.0675 (06-24 morning) →
  −0.0087 (06-24 evening) → **−0.0505 (06-25 13:30Z)** `[local snapshot/log values,
  VERIFIED as recorded]` → `ModelProtectionExitTask [NFLX]: EXIT thesis_breached
  mu=-0.0505<=tau=+0.0000 strikes=3/3` (`logs/intraday_104/2026-06-25.log:220`)
  `[VERIFIED log line — a local-state fact about what the runner decided and why]` →
  sold **@71.3934** `[broker-confirmed, §2.2]`. NFLX closed 07-10 at 73.37, above the
  sale price — a fact about the subsequent price path, not a characterization of the
  exit's quality (§3).
- The protection mu is the HOLDING re-score (`task_sell.py`: `hs.expected_return`, set
  in the intraday sell pass — per-ticker/NGBoost lineage, NOT the panel). The per-ticker
  NFLX admission model in that window: `trained_date=2026-04-30`,
  `live_train_end=2026-04-23` (63 days stale; the same vintage class that later
  collapsed the whole universe on 07-08, #473 §5) — **VERIFIED** directly from the
  artifact metadata.
- **The "+0.066" comparison is a replay, not a recorded score, and is disclosed as
  approximate:** NFLX was wash-blocked from panel admission on 06-25 itself (§2.1), so it
  was not live-scored by the panel path that day; the +0.066 figure is a reconstruction
  using the same June reproduction method disclosed in §4 (day corr 0.950-0.966, NFLX
  row diff up to ±0.05). Read the "buy plane vs. exit plane disagreed by ~0.12 raw"
  framing as an approximate, same-day cross-check between two model planes' views, not a
  byte-exact comparison. A 3-strike debounce did not prevent the exit because the
  strikes accrued on intraday re-evaluations of the SAME stale per-ticker view (3
  evaluations across ~18h) — this part is a fact about the debounce mechanism's design,
  independent of the replay caveat.

**What this establishes:** a local-state fact — the per-ticker exit model that fired the
sell was 63 days stale relative to the panel that had just bought the name, and the
decision to sell traces to that stale plane's own recorded mu, not to any external
(broker) signal. **What this does not establish:** a formal "exit defect" ranking or a
claim requiring broker-side reconciliation beyond the fill prices, which are
broker-confirmed — the counterfactual "the panel would have kept holding" is an
approximate replay, not a recorded fact, and no population-level exit-quality conclusion
follows from one trade (§3). Whatever the dispersion pattern's merits, this trade
mechanically converted a 24h stale-model disagreement into a realized loss and reset a
wash-sale clock whose local record then vanished (§7.2b) — both are local-state
observations, not broker-truth claims beyond the fill prices themselves.

### 7.2 The 06-25 live-tree incident and two LOCAL-STATE defects `[VERIFIED effects as
local-state/ledger facts; producer attribution not re-established; NOT broker-reconciled
claims — Codex point 5]`

Both findings below are LOCAL-STATE facts (served-artifact identity and local
ledger/snapshot contents); neither requires or claims broker-side confirmation beyond
what's already broker-confirmed in §2.2 (the actual fills). Between the 06-25 and 06-26
sessions (the window of the known 2026-06-25 live-tree git checkout/recovery incident —
memory "recovery checkout clobbers code hotfixes"; 18 intraday FAILs on 06-26):

- **(a) The prod panel artifact regressed 06-21 → 05-18 — a local file/artifact-identity
  fact.** Run bundles: sessions 06-22..25 stamp panel sha `04d7a381` (trained 06-21,
  byte-recovered from `bak_prestamp_20260703T110653`); sessions 06-26..07-02 stamp
  `5ce63326`, and the 06-26+ logs read `Artifact loaded: … trained=2026-05-18`. The
  recorded 06-26..07-02 scores replay byte-consistently under the COMMITTED 05-18
  artifact (GitHub `c9dc6ce7e3`: ZM/FTNT reproduce to 0.0000) and NOT under the 06-21
  booster (panel corr 0.32) — i.e. prod reverted to the last *committed* artifact
  vintage, exactly what a working-tree checkout does to an uncommitted deployed file.
  This is established from sha/hash comparisons and byte-exact replay against the cited
  GitHub ref — independently reproducible, not inferred. A 39-45-day-old model held
  primary for 5 sessions, unalerted, in direct conflict with the 28d freshness policy —
  and by 07-03 04:06 PT the 06-21 file was back (the prestamp backup captured it),
  meaning production flipped models twice more without any promotion or alert. NFLX's
  mid-window rank collapse (#6 → #52) was this swap, not a view change. **Producer
  attribution (WHO/WHAT caused the revert) is not re-established here** — see §9(f).
- **(b) NFLX's local wash-sale stamp was erased — a ledger-integrity finding, not a
  broker-side wash-sale event.** `STATE-EXT-SELL: NFLX disappeared from broker without
  runner sell — stamping wash-sale clock today (2026-06-25)`
  (`intraday_104/2026-06-25.log:452`); snapshot 06-25 13:42Z contains
  `last_sell_dates[NFLX]=2026-06-25` (10 keys) `[VERIFIED local snapshot content]`. The
  next snapshot (06-26 17:00Z) has 7 keys and **no NFLX**; the live file today still has
  no NFLX `[VERIFIED local snapshot content]`. This is a verified LOCAL STATE fact: the
  internal control's own record of the loss sale disappeared. Consequence, stated
  precisely: the **07-10 NFLX buy submission went out 15 days into the internal 30d
  window with `blocked_wash=0`** — the internal gate had nothing to block against,
  because its own record was gone. **This does not, by itself, establish that a
  prohibited broker-side wash-sale re-entry occurred or would have occurred** — the order
  was canceled before fill (§2.2, broker-confirmed), so no re-entry, wash-sale or
  otherwise, actually happened this time. What is established is a near-miss: the
  internal control that is supposed to prevent this class of re-entry was blind on this
  day, and would have had nothing to stop the order had it filled instead of being
  canceled for the unrelated pre-open reason. Confirming what an actual fill would have
  meant at the broker/tax-reporting level would require broker-side reconciliation, which
  has not been performed here. Note this is a *different* hole than the #428 stamp-date
  bug (fixed): here the stamp was written correctly and then lost with the rest of the
  06-25/26 state churn; wash-sale enforcement currently has a single, mutable,
  unreconciled point of failure (`live_state.last_sell_dates`).

### 7.3 Intent-vs-fill observability

The `trades` table records `buy_pending` rows only; no fill/cancel outcome row exists
(NFLX 06-22/23 shows 3 pending rows → 1 actual fill; ZM shows 5 pendings → 0 fills;
the 06-25 NFLX sell fill exists only at the broker). Any downstream consumer of the
DB (or of ntfy messages) systematically overcounts "buys". This forensic had to go to
the broker API to establish basic facts — that lookup belongs in the pipeline.

## 8. Layer 4 — candidate fix mapping (NOT a validated or ready-to-build list)

> **No runtime gate, retrain, or strategy-flag change should follow from this document
> until the preregistered, full-cross-section experiment (#476 §7) validates the
> hypothesis.** Everything below is a candidate follow-up conditional on that
> experiment where noted, not a confirmed fix or a "ready" mapping — matching Codex's
> final instruction on this PR.

**Candidates already scoped by the EXISTING stack (status as of this document, none
validated as a fix for these names):**

1. **renquant-model #44 (vol_trend_v2 feature code, MERGED but DISABLED)** — F1
   `ret_vol_{20,60}d` / `ret_semivol_down_60d`, F2 `resid_vol_60d` + trend interactions,
   shipped behind an experiment-id gate, off by default; no model has been trained on
   these features. **Descriptive fact only (§5.1):** recomputing NFLX's raw feature
   VALUES under the v2 definitions moves its cross-sectional percentile from 81st to
   51st (both ret_vol_60d and resid_vol_60d); FTNT's recomputed percentile moves
   20-26pp; META's recomputed percentile moves from 49th to 60th/51st; ZM's barely moves
   (72nd → 70th/86th). **This is not a remedy, a rank result, or a prediction of what a
   trained scorer would do** — there is no trained v2 artifact, no immutable training
   vintage, no scoring config, and no full-population out-of-sample result. The
   preregistered baseline-vs-v2 comparison (#476 §7) is the required next step, and it
   has not started; until it runs and reports, nothing here should be read as
   validating or ruling out v2 as a fix.
2. **F4 / #479 (override consequences)** — §6 shows the long side of the same pattern:
   two override promotions + one un-promoted regression, all carrying BULL_CALM
   long-side rank inversion. Nothing new to design; this document is additional
   evidence for discussing regime-scoped consequences on the weekly rail — a governance
   design question independent of whether H2/H3 (the STD60 mechanism hypotheses) are
   ever validated.
3. **base-data #43** — covers ZM's never-finite ey/b2p (META-class hole). This is an
   input-integrity fix; per §5.2, this document takes no position on whether fixing it
   would suppress, promote, or not materially change ZM's score.
4. **Gated retrain (freshness-vs-gate policy)** — unchanged; note the irony recorded in
   §7.2a: the freshness policy used to justify overrides was itself violated for 5
   sessions by the silent regression, unalerted.

**Independent candidates from the LOCAL-STATE findings (§7) — not gated on the STD60
hypothesis experiment above, still unbuilt proposals, owners per subrepo model:**

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

## 9. Known Limitations / Not Yet Established (Codex review, orchestrator PR #484)

This document's evidence supports the following defensible conclusion, and no more:

> On an approximate replay, ZM and NFLX show the same STD-family SHAP dominance pattern
> that #475/#476 documented on META's fade side, mirrored to the buy side. This is an
> attribution hypothesis about the fitted model's current representation, not a
> counterfactual proof that either name would fail admission absent STD; not a validated
> remedy from unmodeled v2 features; not an established valuation-score direction for
> ZM; not a performance or exit-quality verdict from a thin, immature sample; and not a
> broker-reconciled claim beyond the two fills this document independently confirmed.
> **No runtime gate, retrain, or strategy-flag change should follow from this document
> until the preregistered, full-cross-section experiment (#476 §7) validates the
> hypothesis.**

The items below are open, mapped to Codex's five review points:

**(a) SHAP subtraction is not a counterfactual rescore (Codex point 1).** §4.0 states
what was and was not done: no exact serving-path replay, no SHAP additivity-residual
check, no feature intervention preserving the remaining feature vector. The ex-STD
numbers in §4.1 describe this model's current representation on an approximate replay;
they do not prove either name would fail the admission floor without STD. The
replay-error-vs-margin comparison in §4.0 shows the disclosed NFLX noise band
(±0.02-0.05) is the same order of magnitude as NFLX's own admission margin on two of its
three admission days — a further reason this cannot be read as a clean result. Closing
this requires the same conditional ALE/SHAP, frozen-model ablation, and additivity-
residual work #476 §7 already scoped for the STD60 hypothesis generally.

**(b) The vol_trend_v2 recomputation is not a remedy or a rank result (Codex point 2).**
#44 ships v2 feature code disabled behind an experiment-id gate; no model has been
trained on it. The percentile-point figures in §5.1/§8 describe recomputed feature
VALUES only. Establishing what a trained scorer would do requires the actual trained v2
artifact, an immutable training vintage, the exact scoring config, and a full-population
out-of-sample result — none of which exist. The preregistered baseline-vs-v2 comparison
(#476 §7) is the artifact that would close this; it has not started.

**(c) The ZM valuation-score-direction claim is removed (Codex point 3).** §5.2 no
longer states that recovering ZM's ey/b2p would likely raise its score. The model's
transform, imputation-vs-real interaction effects, and retraining response to real
fundamentals for ZM are not established by anything in this document. #43 remains a real
input-integrity defect independent of any score-direction claim.

**(d) Thin-sample performance/exit claims are removed or caveated (Codex point 4).** §3
now states the population (2 names, 7 pick-days, 1 realized trade), the pre-entry
horizon (0-19 days against a 60-trading-day label, none matured), the absence of
slippage/cost/corporate-action treatment beyond the two real fills, the benchmark
definition (SPY price return, not total return), and the absence of an out-of-sample
holdout. No performance or exit-quality conclusion is drawn from this sample. Street
analyst price targets have been removed entirely — they are not evidence for this
pipeline/model investigation.

**(e) Local-state facts are separated from broker-truth claims (Codex point 5).** §7.1
and §7.2 now label each claim as either a verified LOCAL STATE fact (served-artifact
identity, log lines, live-state snapshot contents) or a claim that would require broker
reconciliation not performed here. The wash-sale finding (§7.2b) is restated as a
ledger-integrity near-miss — the internal control's own record was missing, and the
order was independently canceled before fill (broker-confirmed), so no actual wash-sale
re-entry occurred; whether a hypothetical fill would have constituted a broker/tax-level
wash-sale event is not established here. The exit-plane finding (§7.1) separates the
broker-confirmed fill prices and the verified local log line from the approximate
same-day panel replay (+0.066), which is disclosed as a reconstruction using the same
June reproduction fidelity as §4, not a recorded score.

**(f) Sealed-input / run-ID / transition-provenance status, stated explicitly per Codex
point 5.** §7.2(a)'s model-regression finding rests on run-bundle SHA fields and a
byte-exact replay match against the committed 05-18 GitHub artifact — both independently
reproducible from the cited refs. §7.2's producer attribution (WHO reverted the tree and
re-restored it) is inferred from the known incident class plus these file/hash/log
effects; the mutation itself is not re-attributed here, matching the posture already
used in #473 §5 for the 07-08 outage. §7.1's per-ticker model vintage
(`live_train_end=2026-04-23`) is read directly from artifact metadata (verified); the
counterfactual "the panel would have kept holding" is not a recorded run and would need
a genuine no-lookahead replay of that exact session to establish beyond the approximate
reconstruction already disclosed.

**Pre-existing limitations (carried over, unchanged in substance):**

- All SHAP statements are model-representation attribution on approximate replays
  (fidelity disclosed per vintage in §4); the #475 limitations (off-manifold PDP,
  correlated-feature non-identifiability, no conditional ALE, no rank-order/gate
  agreement seal for the June replays) carry over verbatim. ZM's July rows are the
  exception: byte-exact reproduction.
- The trend-share/percentile computations use today's OHLCV cache for historical
  as-of dates (same re-adjustment caveat as #475's replay).
- June replay context used the current pinned watchlist (145) rather than the June-era
  config; this affects context-median fills only (disclosed in the fidelity numbers).

**Repository placement, unchanged:** this remains a research/forensics document; no
umbrella/runtime implementation is proposed or made by this PR.

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
  for street consensus, made in the original research pass. Disclosed for completeness;
  the street-consensus citation itself was removed from §3 in the 2026-07-11 revision
  (Codex point 4) since it is not evidence for this pipeline/model investigation.
