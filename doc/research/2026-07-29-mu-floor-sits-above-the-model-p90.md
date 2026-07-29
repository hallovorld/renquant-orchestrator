# The buy gate asks for +3.0%; the model's 90th percentile offers +2.78%

**Date:** 2026-07-29. Measurement, from the live score DB. No fix applied.
**Bottom line:** `mu_floor = 0.03` sits **above the 90th percentile** of the
expected returns the model actually produces. Admission is therefore ~8% by
construction, independent of edge. And the adaptive rank floor that gets the
blame in the logs is **redundant** — every name clearing `mu` also clears it.

---

## 1. The distribution the gate is applied to

Live score DB `data/runs.alpaca.db` (opened `mode=ro&immutable=1`), query
`SELECT mu FROM score_distribution WHERE date BETWEEN '2026-07-08' AND
'2026-07-29'` — no `is_holding` filter (counts every scored row, held or
not), calendar dates 2026-07-08 … 07-29, 1,010 scored rows
`[VERIFIED — score_distribution, above query, this session: n=1010]`. This
is a **pooled, date-level** read, not a per-trading-session one — see the
caveat after the table in §2: one date (07-28) carries 255 rows, 3× any
other date in the sample, so "date" and "session" are not interchangeable
here and the finding below is scoped to the pooled distribution.

| quantity | value |
|---|---:|
| pooled median `mu` | **−0.0005** |
| pooled p90 | **+0.0278** |
| pooled max (ever) | +0.0484 |
| share clearing `mu >= 0.03` | **80/1010 = 7.9%** |

All four rows `[VERIFIED — score_distribution, above query, this session:
median=-0.0004987, p90=0.027716 (linear-interpolated percentile), max=
0.048436, count(mu>=0.03)=80]`.

The gate asks for **+3.00%** over 60 days. The **median** name is offered
**−0.05%**. The **90th percentile** name is offered **+2.78%** — still short.

Per date, the pass count is 2–17 out of 76–255 rows
`[VERIFIED — §2 table below]` (see §2 table for the
per-date breakdown; 07-28 is the outlier both in row count and pass count).

## 2. The rank floor is redundant

`VetoWeakBuysTask` uses `buy_floor = "adaptive_mean_std"`, i.e.
`max(0.20, mean + 1σ)` of the day's `rank_score` (population σ). Per date:
`SELECT rank_score, mu FROM score_distribution WHERE date = ?`; `floor =
max(0.20, mean(rank_score) + pstdev(rank_score))`; `pass rank floor =
count(rank_score >= floor)`; `` pass mu>=.03 = count(mu >= 0.03) ``;
`pass BOTH = count(rank_score >= floor AND mu >= 0.03)`. Applying both gates
to the same rows
`[VERIFIED — score_distribution, per-date query + formula above, this
session — every n/pass-rank/pass-mu/pass-both cell below reproduced exactly]`:

| date | n | pass rank floor | pass `mu>=.03` | pass BOTH |
|---|---:|---:|---:|---:|
| 07-20 | 79 | 16 (20%) | 6 (8%) | **6** |
| 07-21 | 78 | 16 (21%) | 5 (6%) | **5** |
| 07-22 | 77 | 16 (21%) | 3 (4%) | **3** |
| 07-23 | 77 | 17 (22%) | 3 (4%) | **3** |
| 07-24 | 76 | 14 (18%) | 2 (3%) | **2** |
| 07-27 | 84 | 17 (20%) | 6 (7%) | **6** |
| 07-28 | 255 | 53 (21%) | 17 (7%) | **17** |
| 07-29 | 84 | 19 (23%) | 6 (7%) | **6** |

07-28's row count (255) is ~3x any other date in this table; the DB read did
not record whether that is one trading session or several runs pooled under
one date, so it is reported as-is rather than assumed to be a single session.

**`pass BOTH` equals `pass mu` on every date in the sample.** The `mu`
survivors are a strict subset of the rank-floor survivors, so the rank floor
never removes a name that `mu` would have kept. Compound admission is
48/810 = **5.93%**
`[DERIVED — sum of the "pass BOTH" and "n" columns above: 48/810]`, which is
just the `mu` rate.

Consequence for reading logs: `veto:rank_score_below_floor` is what gets
LOGGED, and it is not what decides. The AAPL forensics reached the same
conclusion from the other direction — AAPL was blocked at
`job_panel_scoring.py:2115` on every date in the sample, but its `mu` was
`+0.0068`
`[VERIFIED — score_distribution, SELECT mu WHERE date='2026-07-28' AND
ticker='AAPL', this session: 0.006836]`
against a required `+0.03`, a 4.4× shortfall, so deleting the rank
floor would not have bought it.

## 3. What this is and is not

**It is not a bug.** Both numbers are doing what they are configured to do.

**It is not "the model is bad" either.** A calibrated expected return near zero
for the median name is what a cross-sectionally-normalised score SHOULD produce
— half the names are below average by construction.

**What it is: the gate and the calibrator are not co-calibrated.** An absolute
threshold of +3.0% applied to a distribution whose p90 is +2.78% admits ~8%
regardless of how much edge the model has. If the calibrator were rescaled
tomorrow with no change in ranking skill, the admission rate would move a lot —
which means the current rate is a property of the calibration, not of the
opportunity set.

## 4. Why this matters more than the three constraints already filed

Previously filed, all real, all downstream of this one:
`renquant-pipeline#223` (wash-sale has no materiality floor),
`renquant-pipeline#224` (misleading skip message),
`orchestrator#608` (whole-share rounding skips expensive names).

Those act on the **2–17 names per date that get this far** (§2 table). This
one decides how many names get that far at all. On 07-24 the answer was
**2 of 76**; on 07-29, **6 of 84**; on the 07-28 outlier date, **17 of 255**.

## 5. What I am NOT claiming

- **Not** that `mu_floor` should be lowered. A lower floor admits names the
  model does not claim +3% for; whether that is profitable is exactly the
  untested question, and lowering a live capital gate on the strength of a
  distributional observation is the error this programme has already been
  burned by.
- **Not** that the calibrator is wrong. I measured its output distribution, not
  its accuracy. Whether `mu = +0.0068` is a *correct* forecast for AAPL is a
  separate, harder question that needs realised returns.
- **Not** an estimate of what a different floor would have earned.

## 6. The question this raises, stated precisely

Is `mu_floor = 0.03` an economic threshold (a real hurdle rate: costs, capital
cost, opportunity cost) or a statistical one (a percentile of model output)? If
economic, the finding is that the model rarely clears the hurdle and the honest
response is to stop expecting deployment. If statistical, it is mis-set by
construction and should be expressed as a percentile so it tracks the
distribution instead of drifting against it.

That distinction is answerable from the config's own provenance and is the
cheapest next step. It is not answerable by me guessing.

## 7. Provenance

All figures `[VERIFIED — this session]` from `data/runs.alpaca.db` opened
`mode=ro&immutable=1`, and the live config
`.subrepo_runtime/repos/renquant-strategy-104/configs/strategy_config.json`.
Nothing was written; no order placed; no config changed.
