# Why the model never bought AAPL: the floor logged it, conviction decided it

**Date:** 2026-07-29. Forensics, function level. Read-only.
**Bottom line:** AAPL was **above the model's own median on 12 of 13 scored
sessions**. It was blocked every session at `VetoWeakBuysTask`
(`job_panel_scoring.py:2115`) by an adaptive floor that admits only the top
~18%. But deleting that floor would not have bought it: AAPL's `mu` was
`+0.0068` against a required `+0.03`, a **4.4× shortfall**.

---

## 1. Where the scores actually live

`RenQuant/data/runs.alpaca.db` (4,774 rows), established by reading the
path-constructing code rather than guessing:
`scripts/check_score_db_health.py:53` builds `repo / "data" / f"runs.{broker}.db"`,
and that script's own warning at `:46-47` says verbatim *"Score data is actually
in `data/runs.{broker}.db`"* about the decoy.

**Recorded because it cost me a wrong conclusion:** `data/runs.db` HAS a
`score_distribution` table and it is EMPTY (0 rows). I briefly concluded "AAPL is
never scored", which was wrong. The 07-28 run `be8ee266` holds exactly 85 rows in
the real DB, matching the log line.

Also recorded: that `85` is **not** a coverage bug. The same log says
`ApplyScoresTask: panel scored 77/77 candidates, 8/8 holdings` — 77+8=85. The
scorer scores the admitted candidate set plus holdings, by design.

## 2. AAPL through the funnel

AAPL appears in `_full_candidate_snapshot` (stamped at
`job_panel_scoring.py:1876`, **after** wash-sale, earnings and vol gates) in
every scored session, and in **zero** `RealizedVolGateTask` drop lists across
all 15 logs. It passed all three.

| session | reached scan | rank_score | rank | floor | mu | first blocking gate |
|---|---|---:|---:|---:|---:|---|
| 07-08 | no — `0 candidates from 0 tickers` | — | — | — | — | upstream: no candidates |
| 07-09 | no — `0 candidates` | — | — | — | — | upstream: no candidates |
| 07-10 | yes | 0.4922 | 37/85 | 0.544 | 0.0018 | VetoWeakBuys `:2115` |
| 07-13 | yes | 0.4957 | 35/81 | 0.546 | 0.0030 | VetoWeakBuys `:2115` |
| 07-14 | no — run aborted pre-pipeline | — | — | — | — | wrapper abort |
| 07-15 | no — died on calibrator/scorer fingerprint mismatch → sell-only | — | — | — | — | `:2283` |
| 07-20 | yes | 0.5168 | 21/76 | 0.535 | 0.0106 | VetoWeakBuys `:2115` |
| 07-21 | yes | 0.5111 | 20/74 | 0.528 | 0.0086 | VetoWeakBuys `:2115` |
| 07-22 | yes | 0.5107 | 19/73 | 0.527 | 0.0084 | VetoWeakBuys `:2115` |
| 07-23 | yes | 0.5107 | 19/72 | 0.524 | 0.0084 | VetoWeakBuys `:2115` |
| 07-24 | yes | 0.5136 | **16/72** | 0.521 | 0.0095 | VetoWeakBuys (gap **−0.0077**) |
| 07-27 | yes | 0.5068 | 29/80 | 0.538 | 0.0071 | VetoWeakBuys `:2115` |
| 07-28 | yes | 0.5062 | 27/78 | 0.532 | 0.0068 | VetoWeakBuys `:2115` |
| 07-29 | yes | 0.5080 | 26/78 | 0.534 | 0.0075 | VetoWeakBuys `:2115` |
| *06-26* | yes | 0.5844 | 12/79 | 0.581 | 0.0344 | **cleared the floor (+0.0035)**, died at ConvictionGate `:2350` |

`[VERIFIED — runs.alpaca.db + logs/daily_104/*.log, this session]`

The decisive condition, `job_panel_scoring.py:2115-2117`, with 07-28 substituted:

```
if score < floor:   ->   if 0.5062 < 0.5320:   -> True
    blocked[cand.ticker] = "veto:rank_score_below_floor"
```

The floor comes from `:1996-2012`:
`floor = max(min_fl, fmean(scores) + std_mult*stdev(scores))` with
`buy_floor="adaptive_mean_std"`, `buy_floor_min=0.20`, `buy_floor_std_mult=1`.
**Recomputed from the DB for all 15 sessions, matching the logged value to 3
decimals 15/15** `[VERIFIED]` — the mechanism is reproduced, not inferred.

## 2b. This is not "the model disliked AAPL"

AAPL sat **above the model's own median on 12 of 13 scored sessions** (07-28:
0.5062 vs median 0.4776 = 67th percentile; 07-24 = 79th). `mean + 1σ` sits near
the ~84th percentile by construction, so it admits only 12-15 of ~75 names.

**The accurate statement is: AAPL was mid-pack and the floor only takes the top
~18%.**

## 3. The deeper cause: the floor logged it, conviction decided it

Even with the adaptive floor deleted, AAPL is not bought.

`raw_panel = −0.2037` while the calibrator's ER=0 anchor sits at
`raw = −0.2822`, so AAPL is genuinely **above** the model's own break-even — by
0.079, which the calibrator maps to `mu = +0.0068`. That is a claimed **+0.68%
over 60 days against a required +3.0%**: a **4.4× shortfall**.

On 07-28 only **2 of 78** candidates in the entire cross-section had
`mu >= 0.03`; on 07-24, **zero did** `[VERIFIED]`. This is corroborated
independently in orchestrator#610, which measured the pooled `mu` p90 at
`+0.0278` — below the `0.03` gate — across 1,010 scored rows.

So `veto:rank_score_below_floor` is what gets **logged**; `mu_floor` is what
**decides**.

The one genuine near-miss is **06-26**: AAPL cleared the floor by +0.0035 with
`mu = 0.0344 > 0.03` and was killed by the then-active `demean_cross_sectional`
branch (`:2350`, `0.0344 − 0.0201 = 0.0143 < 0.03`). That flag is now `false`,
so that specific block would not recur.

## 4. Two things that are NOT the explanation

**The per-ticker model is decision-irrelevant.** `AAPL Manual 2026-07-26 3.49
981 2026-06-23` decodes via `live/runner.py:483-491` as
`SYMBOL, TYPE, TRAINED, SHARPE, ROWS, TRAIN END` — so a 2026-06-23 training
cutoff, 36 days stale. But `bypass_ticker_gate: true` and the DB records
`active_scorer='panel_ltr_xgboost'`. The 3.49 Sharpe is the frozen legacy
tournament, not the scorer that decides.

**The whole-share price bias is not AAPL's cause.** AAPL never reached
`SizeAndEmitTask` — it died two tasks earlier every session. That bias is real
and biting, though: on 07-28 **SPG at $236.69** was the only name to clear both
model gates and was then killed at `task_selection.py:612-616` (`if shares < 1`,
`remaining_cash=$6868`) → `0 orders placed`. At $230-260 AAPL would hit that
identical wall if it ever cleared the model (orchestrator#608).

**AAPL was never held and never bought live**: 0 rows with `is_holding=1` across
all 64 AAPL score rows, and 0 of 126 AAPL trade rows are live (all `-sim-`).

## 5. The honest negative

AAPL's `raw_panel` fell from **+0.104 (06-26) to −0.199 (07-29)** — moving
*against* the price rally throughout `[VERIFIED]`.

**That is a signal story, not a plumbing defect.** I read admission plumbing,
not feature attribution, and I cannot say which of the 172 features drove it
without a SHAP run on the pinned artifact — which needs the per-day feature
matrices, and those are not retained.

## 6. A lead I chased and CLOSED

`raw_panel` is byte-identical on some consecutive pairs (07-22/07-23 both
−0.1881; 07-27/07-28 both −0.2037), which is consistent with a stale as-of
feature axis and would be a real defect if confirmed.

**Tested and rejected.** Deduplicating to one row per `(ticker, date)` — the
first pass was polluted by same-date reruns — gives **245/2,837 = 8.6%** of
consecutive date-pairs byte-identical, with a per-ticker distinct/dates median
of **0.92** `[VERIFIED]`. The repeats cluster on weekend and holiday boundaries
and hit many tickers at once (AAPL, ABBV, ADI all repeat on 06-09→06-10), which
is feature-frame reuse across non-trading days, not staleness.

## 7. The design criticism that does survive

A floor at `mean + 1σ` on a Platt-compressed calibrator throttles breadth to
~16% **regardless of edge** — a concern the code itself documents at
`:1939-1946`. Combined with an absolute `mu_floor` sitting above the
calibrator's own p90 (#610), the two gates compound to admit ~6% of the
cross-section.

Neither is a bug. Both are gates doing what they are configured to do. The open
question, stated precisely in #610, is whether `mu_floor = 0.03` is an
**economic** hurdle or a **statistical** one — because if statistical, it is
mis-set by construction.
