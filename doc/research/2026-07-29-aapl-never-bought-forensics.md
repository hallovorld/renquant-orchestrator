# Why the model never bought AAPL: the floor logged it, conviction decided it

**Date:** 2026-07-29 (corrected 2026-07-29 — see §0a). Forensics, function level.
Read-only.
**Bottom line:** AAPL was **above the model's own median on 11 of 13 scored
sessions** `[VERIFIED-now — scripts/aapl_admission_forensics.py]`. It was blocked
every session at `VetoWeakBuysTask` (`job_panel_scoring.py:2115`) by an
adaptive floor that, on these sessions, admitted the top **18.3%**
`[VERIFIED-now — same script, mean over the 13 sessions]`. But deleting that
floor would not have bought it: AAPL's `mu` was `+0.0068` against a required
`+0.03` `[VERIFIED-now — runs.alpaca.db (mu) + each run's own
ConvictionGateTask log line, not today's config — see §0b]`, a **4.4x
shortfall** `[DERIVED — 0.03 / 0.006836]`.

---

## 0. Provenance of every decision-driving number

LONG #10 requires a per-quantity tag, not a section-level marker.

**Everything here is reproducible by one command**, which re-derives the §2 table
and the §7 aggregates from the score DB plus the daily logs, and never from
today's `strategy_config.json`:

```
python3 scripts/aapl_admission_forensics.py --ticker AAPL \
    --since 2026-07-06 --until 2026-07-29 --extra-session 2026-06-26
```

**The window is stated once and used everywhere:** all 18 logged sessions from
**2026-07-06 to 2026-07-29**, plus **2026-06-26** (the one session AAPL cleared
the floor). AAPL was scored in **13** of them `[VERIFIED-now — script output]`;
the other 5 never reached the buy gate and are itemised in §2.

**The run for each session is pinned by runtime evidence, not by hand.** The
`VetoWeakBuysTask` log line reports the cross-section size `n` it gated on, so
the script selects the live run whose candidate row count equals that `n`; where
a date has several runs (2026-07-28 had three) the day's *last* logged gate line
is the operative one. That independently re-derives the pin used below —
`2026-07-28-live-5b859fff`, `role='candidate'`, n=78, read from
`candidate_scores` in `data/runs.alpaca.db` opened `immutable=1`
`[VERIFIED-now — re-queried this session]`.

| quantity | value | provenance |
|---|---|---|
| quantity | value | provenance |
|---|---|---|
| `candidate_scores` rows, whole DB | 241,675 | `[VERIFIED-now — SELECT COUNT(*)]` |
| `pipeline_runs` rows, whole DB | 39,728 (2,081 live) | `[VERIFIED-now — SELECT COUNT(*)]` |
| scored rows in the pinned run | 85 (78 candidate + 7 holding) | `[VERIFIED-now — GROUP BY role]` |
| AAPL scored sessions | 13 of 18 logged | `[VERIFIED-now — script, §2 table]` |
| sessions above the model's own median | **11 of 13** | `[VERIFIED-now — script; was mis-stated as 12, see §0a]` |
| AAPL rank_score | 0.5062 | `[VERIFIED-now — pinned run, 0.5061711]` |
| candidate median rank_score | 0.4776 | `[VERIFIED-now — pinned run]` |
| AAPL percentile | **65th** | `[VERIFIED-now — 51 of 78 candidates score below it]` |
| floor value | 0.532 | `[VERIFIED-now — logged VetoWeakBuysTask line, 07-28 second run]` |
| floor recomputed == logged | **13 of 13** | `[VERIFIED-now — script; was mis-stated as 15/15, see §0a]` |
| mean share admitted by the floor | **18.3%** (range 15.2–22.2) | `[VERIFIED-now — script, 13 sessions]` |
| mean share surviving floor AND mu_floor | **6.1%** (range 0.0–17.7) | `[VERIFIED-now — script, 13 sessions]` |
| AAPL raw_panel (`panel_score`) | **-0.2061** | `[VERIFIED-now — pinned run]` |
| calibrator ER=0 anchor | raw = -0.2822 | `[VERIFIED-now — `neutral_raw=-0.2822` in the 07-28 log]` |
| AAPL margin above break-even | **0.076** | `[DERIVED — -0.2061 - (-0.2822)]` |
| AAPL mu | +0.0068 | `[VERIFIED-now — pinned run, 0.006836]` |
| required mu_floor | +0.03 | `[VERIFIED-now — each run's own ConvictionGateTask log line; §0b, NOT today's strategy_config.json]` |
| mu shortfall ratio | 4.4x | `[DERIVED — 0.03 / 0.006836 = 4.39]` |
| candidates clearing mu >= 0.03 | 2 of 78 | `[VERIFIED-now — pinned run]` |
| cross-sectional p90 of mu | +0.0278 | `[VERIFIED-prior — orchestrator#610]` |
| rows behind that p90 | 1,010 | `[VERIFIED-prior — orchestrator#610]` |
| 06-26 near-miss: floor margin | +0.0035 | `[DERIVED — 0.5844 - 0.5809 recomputed floor]` |
| 06-26 mu before/after demean | 0.0344 / 0.0143 | `[VERIFIED-now — logged; 0.0344 - 0.0201]` |
| repeat-score rate | 254/2,768 = 9.2% | `[VERIFIED-now — §6, dedup rule stated there]` |
| median per-ticker distinct/dates | 0.92 | `[VERIFIED-now — §6]` |
| legacy per-ticker Sharpe (NOT decision-relevant) | 3.49 | `[VERIFIED-prior — frozen legacy artifact, §4]` |

### 0a. Corrections applied after the first merge

Three counts in the merged revision did not survive re-derivation. The root
cause was a **window mismatch**: §0's aggregates were computed over sessions
from 2026-07-06 onward, while §2's funnel table started at 2026-07-08. The two
sessions where AAPL was **below** the median — 07-06 and 07-07 — were therefore
inside the denominator but missing from the table, so the ratio could not be
checked against the evidence printed beside it.

| was | now | why |
|---|---|---|
| above median `12 of 13` | **`11 of 13`** | 07-06 (43rd pct) and 07-07 (42nd pct) are both below the median; only 11 of the 13 are above `[VERIFIED-now]` |
| floor match `15/15` | **`13/13`** | only 13 sessions were scored at all; 15 was the count of *table rows*, 4 of which are non-scored sessions `[VERIFIED-now]` |
| 07-24 percentile `79th` | **`78th`** | 56 of 72 candidates score below AAPL = 77.8% `[VERIFIED-now]` |
| `runs.alpaca.db (4,774 rows)` | *removed* | not reproducible against any table in the DB; `candidate_scores` = 241,675 and `pipeline_runs` = 39,728. The nearest match, `score_distribution`, is 4,858 today `[VERIFIED-now]` |

`~18%` and `~6%` **survive** re-derivation and are now stated precisely (18.3%
and 6.1%) — but only once 07-06 and 07-07 are included, which is why the
missing rows mattered: on the 11 sessions the table actually printed, the
floor-and-mu share is 4.8%, not 6.1% `[VERIFIED-now]`.

**Two figures CORRECTED by the earlier re-query, retained for the record.** An
earlier revision took most numbers from run `5b859fff` but `raw_panel` from a
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

### 0b. `mu_floor = 0.03` is sourced from runtime logs, not today's config

**`mu_floor = 0.03` re-sourced from historical runtime logs, not today's
config.** An earlier revision tagged the required `mu_floor` to today's
`strategy_config.json` — the wrong artifact for a historical-policy claim,
since a config value read today does not prove what was resolved on a run
weeks ago. Re-sourced from `ConvictionGateTask`'s own runtime log line, which
prints the gate value it actually used that run:

```
$ grep -h 'ConvictionGateTask.*mu_floor' logs/daily_104/2026-07-{06,07,10,13,20,21,22,23,24,27,28,29}.log \
      logs/daily_104/2026-06-26.log
2026-07-06 ... ConvictionGateTask: dropped  1 candidate(s) (mu_floor=0.03)
2026-07-07 ... ConvictionGateTask: dropped  2 candidate(s) (mu_floor=0.03)
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

`[VERIFIED-now]`: `mu_floor=0.03` on **13/13** scored sessions. The stronger
statement, also re-measured: across **all 169** retained `daily_104` logs there
are 20 `ConvictionGateTask` gate lines and **every one of them reads
`mu_floor=0.03`** — no other value has ever been resolved on this surface
`[VERIFIED-now — grep -ho 'mu_floor=[0-9.]*' logs/daily_104/*.log | sort | uniq -c
→ "20 mu_floor=0.03"]`.

This is the resolved runtime value for each specific historical run, not an
inference from the current file — it answers the objection that a config read
today cannot establish what a run weeks ago actually used. The extraction script
re-parses these same lines, so the claim is re-checkable rather than pasted.

## 1. Where the scores actually live

`RenQuant/data/runs.alpaca.db` — 241,675 `candidate_scores` rows over 39,728
`pipeline_runs` (2,081 of them live) `[VERIFIED-now — SELECT COUNT(*)]`.
Established by reading the path-constructing code rather than guessing:
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
the window's logs. It passed all three.

**This table now covers the whole declared window** — every logged session from
07-06 to 07-29, plus 06-26 — so the ratios in §0 and §7 can be checked against
it. The merged revision started this table at 07-08 while computing its
aggregates from 07-06, which hid the only two below-median sessions (§0a).

| session | reached scan | rank_score | rank | pct | floor | mu | first blocking gate |
|---|---|---:|---:|---:|---:|---:|---|
| 07-06 | yes | 0.5125 | 20/35 | 43rd | 0.565 | 0.0090 | VetoWeakBuys `:2115` — **below median** |
| 07-07 | yes | 0.5085 | 19/33 | 42nd | 0.554 | 0.0076 | VetoWeakBuys `:2115` — **below median** |
| 07-08 | no — `0 candidates from 0 tickers` | — | — | — | — | — | upstream: no candidates |
| 07-09 | no — `0 candidates` | — | — | — | — | — | upstream: no candidates |
| 07-10 | yes | 0.4922 | 37/85 | 56th | 0.544 | 0.0018 | VetoWeakBuys `:2115` |
| 07-13 | yes | 0.4957 | 35/81 | 57th | 0.546 | 0.0030 | VetoWeakBuys `:2115` |
| 07-14 | no — aborted after "Step 2: Exporting LEAN watchlist" (42-line log) | — | — | — | — | — | wrapper abort |
| 07-15 | no — died on calibrator/scorer fingerprint mismatch → sell-only | — | — | — | — | — | `:2283` |
| 07-16 | no — **no log file retained**; session not assessable | — | — | — | — | — | n/a |
| 07-17 | no — `FATAL: on 'feat/g4-training-metadata-wiring' (expected main)` | — | — | — | — | — | branch guard, pre-pin-align |
| 07-20 | yes | 0.5168 | 21/76 | 72nd | 0.535 | 0.0106 | VetoWeakBuys `:2115` |
| 07-21 | yes | 0.5111 | 20/74 | 73rd | 0.528 | 0.0086 | VetoWeakBuys `:2115` |
| 07-22 | yes | 0.5107 | 19/73 | 74th | 0.527 | 0.0084 | VetoWeakBuys `:2115` |
| 07-23 | yes | 0.5107 | 19/72 | 74th | 0.524 | 0.0084 | VetoWeakBuys `:2115` |
| 07-24 | yes | 0.5136 | **16/72** | 78th | 0.521 | 0.0095 | VetoWeakBuys (gap **−0.0077**) |
| 07-27 | yes | 0.5068 | 29/80 | 64th | 0.538 | 0.0071 | VetoWeakBuys `:2115` |
| 07-28 | yes | 0.5062 | 27/78 | 65th | 0.532 | 0.0068 | VetoWeakBuys `:2115` |
| 07-29 | yes | 0.5080 | 26/78 | 67th | 0.534 | 0.0075 | VetoWeakBuys `:2115` |
| *06-26* | yes | 0.5844 | 12/79 | 85th | 0.581 | 0.0344 | **cleared the floor (+0.0035)**, died at ConvictionGate `:2350` |

**Row accounting** `[VERIFIED-now — scripts/aapl_admission_forensics.py, which
prints a reason line for each non-gating session]`: 19 rows = 17 retained logs in
07-06..07-29, plus 07-16 (no log retained), plus 06-26. Of the **18 sessions with
a log**, **13 gated buys and scored AAPL** and 5 did not (2 no-candidates, 1
wrapper abort, 1 sell-only, 1 branch guard). Every ratio in this note has 13 as
its denominator.

The decisive condition, `job_panel_scoring.py:2115-2117`, with 07-28 substituted:

```
if score < floor:   ->   if 0.5062 < 0.5320:   -> True
    blocked[cand.ticker] = "veto:rank_score_below_floor"
```

The floor comes from `:1996-2012`:
`floor = max(min_fl, fmean(scores) + std_mult*stdev(scores))` with
`buy_floor="adaptive_mean_std"`, `buy_floor_min=0.20`, `buy_floor_std_mult=1`.
The parameters are not asserted either — the script parses `min=0.20` and
`mean+1.00*std` out of the log line itself, so a change of floor mode would
surface as a recompute mismatch rather than silently validating the wrong
arithmetic. **Recomputed from the DB for every scored session, matching the
logged value to 3 decimals 13/13** `[VERIFIED-now — script]` — the mechanism is
reproduced, not inferred.

## 2b. This is not "the model disliked AAPL"

AAPL sat **above the model's own median on 11 of 13 scored sessions**
`[VERIFIED-now — §2 table]` (07-28: 0.5062 vs median 0.4776 = 65th percentile;
07-24, its best session, = 78th). The two exceptions are **07-06 (43rd) and
07-07 (42nd)**, both thin cross-sections (n=35 and n=33).

Measured rather than assumed: the floor admitted **5–18 names per session**,
i.e. **15.2–22.2%** of the cross-section, mean **18.3%**
`[VERIFIED-now — script, 13 sessions]`. Equivalently the floor sat at the
77.8th–84.8th percentile of the day's scores. (`mean + 1σ` is the ~84th
percentile only for a normal cross-section; these are Platt-compressed and
mildly skewed, hence the spread. That is a measurement, not a property.)

**The accurate statement is: AAPL was mid-pack and the floor took the top
18.3% on average.**

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

**AAPL was never held and never bought live**: of the **84** AAPL
`candidate_scores` rows in live runs, **0** carry `role='holding'` (the column is
`role`, not `is_holding` — the merged revision named a column that does not
exist), and **0 of 126** AAPL `trades` rows are live: all 126 are `-sim-`
`[VERIFIED-now — GROUP BY role and by run-id kind]`.

## 5. The honest negative

AAPL's `raw_panel` fell from **+0.1040 (06-26) to −0.1988 (07-29)** — moving
*against* the price rally throughout
`[VERIFIED-now — panel_score in runs 3d74ce5c and 34603e64]`.

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
first pass was polluted by same-date reruns — the rate is single-digit percent,
not the 38.5% of the first pass. Re-measured now, with the dedup rule stated so
it is reproducible: **last** live run per `(ticker, date)`, `role='candidate'`,
non-null `panel_score` → **254/2,768 = 9.2%** of consecutive date-pairs
byte-identical, per-ticker distinct/dates median **0.92**
`[VERIFIED-now — re-queried this session]`.

The merged revision reported `245/2,837 = 8.6%` for this. The **median 0.92
reproduces exactly**, which identifies the rule, but the pair count does not
(the DB has gained a session since). The tie-break matters and is worth stating:
taking the **first** run per date instead gives **213/2,768 = 7.7%**
`[VERIFIED-now]`. Every variant lands in 7–10% and none is anywhere near 38.5%,
so the conclusion does not turn on the choice.

The repeats cluster on weekend and holiday boundaries and hit many tickers at
once (AAPL, ABBV, ADI all repeat on 06-09→06-10), which is feature-frame reuse
across non-trading days, not staleness.

## 7. The design question this raises (an observation, not a proven mechanism)

Over the 13 scored sessions the `mean + 1σ` floor admitted a mean **18.3%** of
the cross-section (range 15.2–22.2%), and combined with the absolute `mu_floor`
(#610) the two gates left a mean **6.1%** admitted (range 0.0–17.7%)
`[VERIFIED-now — scripts/aapl_admission_forensics.py, per-session columns in §2]`.

Both aggregates depend on the full 13-session window: computed over only the 11
sessions the merged §2 table printed, the floor-and-mu share is **4.8%**, not
6.1% `[VERIFIED-now]`. That sensitivity is precisely why the window is now
declared once in §0 and the table covers all of it.

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
   edge level cannot establish it. 18.3% is what mean+1σ admits on *these*
   score distributions; the admitted share under mean+kσ depends on the
   distribution's shape, so a skewed or differently-compressed cross-section
   would admit a different fraction. The measured spread is itself the
   counter-example: 15.2% to 22.2% across the 13 sessions, so the share is not
   even constant within this sample `[VERIFIED-now]`.

Testing it properly would mean varying the realised edge and showing the
admitted share does not move — which this note does not do. What remains is
the sample-specific measurement above, plus the fact that the codebase's own
authors considered breadth-throttling under mean+kσ a real enough concern to
build a quantile alternative for it.

Neither is a bug. Both are gates doing what they are configured to do. The open
question, stated precisely in #610, is whether `mu_floor = 0.03` is an
**economic** hurdle or a **statistical** one — because if statistical, it is
mis-set by construction.
