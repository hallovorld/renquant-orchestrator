# Why the model never bought AAPL: the floor logged it, conviction decided it

**Date:** 2026-07-29. Forensics, function level. Read-only.
**Bottom line:** AAPL was **above the model's own median on 12 of 13 scored
sessions** `[VERIFIED — SS2 per-session table, runs.alpaca.db]`. It was blocked
every session at `VetoWeakBuysTask` (`job_panel_scoring.py:2115`) by an
adaptive floor that, on these sessions, admitted the top **~18%**
`[VERIFIED — SS3 table]`. But deleting that floor would not have bought it:
AAPL's `mu` was `+0.0068` against a required `+0.03`
`[VERIFIED — runs.alpaca.db (mu) + ConvictionGateTask log line, historical
per-run, not today's config — see §0 note]`, a **4.4x
shortfall** `[DERIVED — 0.03 / 0.0068]`.

---

## 0. Provenance of every decision-driving number

LONG #10 requires a per-quantity tag, not a section-level marker.

**The sample is pinned**, because it has to be: 2026-07-28 has **three** runs
carrying 85 scored rows, and their AAPL values differ. Everything below is
run `2026-07-28-live-5b859fff`, `role='candidate'` (n=78), read from
`candidate_scores` in `data/runs.alpaca.db` opened `immutable=1`
`[VERIFIED — re-queried this session]`.

| quantity | value | provenance |
|---|---|---|
| `candidate_scores` rows, whole DB | 241,675 | `[VERIFIED — SELECT COUNT(*)]` |
| scored rows in the pinned run | 85 (78 candidate + 7 holding) | `[VERIFIED — GROUP BY role]` |
| AAPL scored sessions | 13 | `[VERIFIED — SS2 table, one row per session]` |
| sessions above the model's own median | 12 of 13 | `[VERIFIED — SS2 table]` |
| AAPL rank_score | 0.5062 | `[VERIFIED — pinned run]` |
| candidate median rank_score | 0.4776 | `[VERIFIED — pinned run]` |
| AAPL percentile | **65th** | `[VERIFIED — rank of 0.5062 among the 78]` |
| floor value | 0.532 | `[VERIFIED — logged floor_label]` |
| share admitted by the floor | ~18% | `[VERIFIED — SS3 table]` |
| share surviving floor AND mu_floor | ~6% | `[VERIFIED — SS3 table]` |
| AAPL raw_panel (`panel_score`) | **-0.2061** | `[VERIFIED — pinned run]` |
| calibrator ER=0 anchor | raw = -0.2822 | `[VERIFIED — calibrator artifact]` |
| AAPL margin above break-even | **0.076** | `[DERIVED — -0.2061 - (-0.2822)]` |
| AAPL mu | +0.0068 | `[VERIFIED — pinned run, 0.006836]` |
| required mu_floor | +0.03 | `[VERIFIED — ConvictionGateTask log line, per historical run — see note below, NOT today's strategy_config.json]` |
| mu shortfall ratio | 4.4x | `[DERIVED — 0.03 / 0.006836 = 4.39]` |
| candidates clearing mu >= 0.03 | 2 of 78 | `[VERIFIED — pinned run]` |
| cross-sectional p90 of mu | +0.0278 | `[VERIFIED — prior work, orchestrator#610]` |
| rows behind that p90 | 1,010 | `[VERIFIED — prior work, orchestrator#610]` |
| 06-26 near-miss: floor margin | +0.0035 | `[VERIFIED — SS2 table]` |
| 06-26 mu before/after demean | 0.0344 / 0.0143 | `[VERIFIED — logged; 0.0344 - 0.0201]` |
| repeat-score rate | 245/2,837 = 8.6% | `[VERIFIED — prior work, SS6]` |
| max repeat correlation | 0.92 | `[VERIFIED — prior work, SS6]` |
| legacy per-ticker Sharpe (NOT decision-relevant) | 3.49 | `[VERIFIED — frozen legacy artifact, SS4]` |

**Two figures CORRECTED by this re-query, not merely tagged.** An earlier
revision took most numbers from run `5b859fff` but `raw_panel` from a
different same-day run (`be8ee266`, which has `-0.2037`), and reported the
percentile as 67th:

| was | now | why |
|---|---|---|
| `raw_panel = -0.2037` | `-0.2061` | `-0.2037` is `be8ee266`'s value; the pinned run is `5b859fff` |
| margin `0.079` | `0.076` | follows from the corrected `raw_panel` |
| percentile `67th` | `65th` | recomputed among the 78 candidates of the pinned run |

None of this moves the conclusion — AAPL is still above the model's own
break-even and still ~4.4x short of `mu_floor` — but mixing two runs of the
same date is exactly the provenance defect the tagging rule exists to catch,
and it was only visible once each number was traced to a specific run.

**`mu_floor = 0.03` re-sourced from historical runtime logs, not today's
config.** An earlier revision tagged the required `mu_floor` to today's
`strategy_config.json` — the wrong artifact for a historical-policy claim,
since a config value read today does not prove what was resolved on a run
weeks ago. Re-sourced from `ConvictionGateTask`'s own runtime log line, which
prints the gate value it actually used that run:

```
$ grep -h 'ConvictionGateTask.*mu_floor' logs/daily_104/2026-07-{10,13,20,21,22,23,24,27,28,29}.log logs/daily_104/2026-06-26.log
2026-07-10 ... ConvictionGateTask: dropped 11 candidate(s) (mu_floor=0.03)
2026-07-13 ... ConvictionGateTask: dropped 11 candidate(s) (mu_floor=0.03)
2026-07-20 ... ConvictionGateTask: dropped 12 candidate(s) (mu_floor=0.03)
2026-07-21 ... ConvictionGateTask: dropped 10 candidate(s) (mu_floor=0.03)
2026-07-22 ... ConvictionGateTask: dropped 11 candidate(s) (mu_floor=0.03)
2026-07-23 ... ConvictionGateTask: dropped 12 candidate(s) (mu_floor=0.03)
2026-07-24 ... ConvictionGateTask: dropped 12 candidate(s) (mu_floor=0.03)
2026-07-27 ... ConvictionGateTask: dropped 11 candidate(s) (mu_floor=0.03)
2026-07-28 ... ConvictionGateTask: dropped 18 candidate(s) (mu_floor=0.03)
2026-07-28 ... ConvictionGateTask: dropped 12 candidate(s) (mu_floor=0.03)
2026-07-29 ... ConvictionGateTask: dropped 13 candidate(s) (mu_floor=0.03)
2026-06-26 ... ConvictionGateTask: dropped 13 candidate(s) (mu_floor=0.03
             demeaned xs_mean=+0.0201)
```

`[VERIFIED — grepped this session]`: `mu_floor=0.03` on 11/11 available
session logs, i.e. every session AAPL was scored in that has a retained log.
This is the resolved runtime value for each specific historical run, not an
inference from the current file — it directly answers the reviewer's
objection that a config read today cannot establish what a run weeks ago
actually used.

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
0.5062 vs median 0.4776 = 65th percentile `[VERIFIED — §0]`; 07-24 = 79th). `mean + 1σ` sits near
the ~84th percentile by construction, so it admits only 12-15 of ~75 names.

**The accurate statement is: AAPL was mid-pack and the floor only takes the top
~18%.**

## 3. The deeper cause: the floor logged it, conviction decided it

Even with the adaptive floor deleted, AAPL is not bought.

`raw_panel = −0.2061` while the calibrator's ER=0 anchor sits at
`raw = −0.2822`, so AAPL is genuinely **above** the model's own break-even — by
0.076 `[DERIVED — §0]`, which the calibrator maps to `mu = +0.0068`. That is a claimed **+0.68%
over 60 days against a required +3.0%**: a **4.4× shortfall**.

On 07-28 only **2 of 78** candidates in the entire cross-section had
`mu >= 0.03`; on 07-24, **zero of 72** did
`[VERIFIED — §2 funnel table, 07-24 total = 72]`. This is corroborated
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
−0.1881; 07-27 and ONE of 07-28's runs both −0.2037), which is consistent with
a stale as-of feature axis and would be a real defect if confirmed.

Run-level precision, since §0 pins a different 07-28 run: 07-22 and 07-23 each
have a single distinct AAPL `panel_score` across all their runs (−0.1881 both),
while **07-28 has two** (−0.2061 and −0.2037). The repeat with 07-27 is against
the −0.2037 run (`be8ee266`), not the §0-pinned `5b859fff`
`[VERIFIED — distinct panel_score per run_date, re-queried this session]`. The
conclusion below is unaffected — it rests on the deduplicated population rate,
not on this pair.

**Tested and rejected.** Deduplicating to one row per `(ticker, date)` — the
first pass was polluted by same-date reruns — gives **245/2,837 = 8.6%** of
consecutive date-pairs byte-identical, with a per-ticker distinct/dates median
of **0.92** `[VERIFIED]`. The repeats cluster on weekend and holiday boundaries
and hit many tickers at once (AAPL, ABBV, ADI all repeat on 06-09→06-10), which
is feature-frame reuse across non-trading days, not staleness.

## 7. The design question this raises (an observation, not a proven mechanism)

On the 13 measured sessions, the `mean + 1σ` floor admitted roughly the top
**18%** of the cross-section `[VERIFIED — the per-session table in §3]`, and
combined with the absolute `mu_floor` (#610) the two gates left about **6%**
admitted `[VERIFIED — §3 table, admitted/scored per session]`.

**What this does NOT establish.** An earlier revision of this section claimed
the floor throttles breadth "regardless of edge," citing a code comment. That
citation was wrong on two counts and the claim is withdrawn:

1. The comment lives in the `adaptive_quantile` branch
   (`job_panel_scoring.py:1966-1973`), where it is the stated *motivation for
   replacing* mean+kσ — not a description of the mode this note analyses. The
   surface actually running here is `adaptive_mean_std`
   (`:2010-2040`), which computes `floor = max(buy_floor_min, mean +
   std_mult*stdev)` `[VERIFIED — read this session at those lines]`.
2. "Regardless of edge" is a claim about invariance, and 13 sessions at one
   edge level cannot establish it. ~18% is what mean+1σ admits on *these*
   score distributions; the admitted share under mean+kσ depends on the
   distribution's shape, so a skewed or differently-compressed cross-section
   would admit a different fraction.

Testing it properly would mean varying the realised edge and showing the
admitted share does not move — which this note does not do. What remains is
the sample-specific measurement above, plus the fact that the codebase's own
authors considered breadth-throttling under mean+kσ a real enough concern to
build a quantile alternative for it.

Neither is a bug. Both are gates doing what they are configured to do. The open
question, stated precisely in #610, is whether `mu_floor = 0.03` is an
**economic** hurdle or a **statistical** one — because if statistical, it is
mis-set by construction.
