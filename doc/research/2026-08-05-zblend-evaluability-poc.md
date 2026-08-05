# 104 zblend: evaluability audit and next experiment

## Decision

**Do not interpret the current 104 zblend run pair as evidence that zblend
improves returns.** The serving construction is a reasonable transparent
baseline, but the current pair has no independent panel control and its
`fwd_60d` outcomes have not matured. Keep the existing safety and serving
monitoring, but freeze performance claims and full-book expansion until the
control and a prospective S2 protocol are in place.

This is an orchestration-level audit of persisted daily run bundles. It does
not change scorer, model, backtest, or execution behavior; those changes belong
to the pipeline, model, and backtesting repositories respectively.

## What zblend means here

The deployed 104 construction is an equal-weight sum of cross-sectional
z-scores from the governed panel scorer and a chain-verified slow-momentum
ledger scorer. The component order and identities are pinned. A name must be
scored by both legs: missing values propagate, while a degenerate leg
contributes zero and marks the serving record degraded. These semantics are
frozen in [the S1 preregistration](2026-08-04-goal8-s1-zblend-prereg.md).

That is a defensible *first serving rule*: it has no fitted blend weights, is
scale-invariant within a date, is easy to replay, and fails closed on component
load errors. It is not, by itself, a proof of alpha. Z-scoring removes level
and scale, not common exposure, correlation, turnover, selection effects, or
the chance that the second component simply reproduces the first component's
ranking.

## Reproducible POC

The read-only POC at
[`scripts/research_zblend_evaluability_poc.py`](../../scripts/research_zblend_evaluability_poc.py)
selects the latest complete live run on a requested date (at least 80
candidates), verifies the recorded scorer identities, compares the actual score
books, and checks whether the selected forward label has any values. It writes
JSON only and opens SQLite with `mode=ro&immutable=1`.

Reproduction against an immutable copy of the two persisted run bundles:

```bash
python3 scripts/research_zblend_evaluability_poc.py \
  --prod-db /path/to/runs.alpaca.db \
  --blend-db /path/to/runs.alpaca_shadow_blend_mom.db \
  --run-date 2026-08-04 \
  --output /tmp/zblend-evaluability.json
```

The committed result is
[`2026-08-05-zblend-evaluability-poc.json`](evidence/2026-08-05-zblend-evaluability-poc.json).
It contains the input database SHA-256 values and run IDs so that the result
can be checked without committing a run database.

### Actual result: 2026-08-04

| Check | Observed value | Consequence |
|---|---:|---|
| Complete production run | `2026-08-04-live-a199b993` | 88 scored names |
| Complete blend-shadow run | `2026-08-04-live-2b1feb08` | 88 scored names |
| Recorded scorer on each arm | `blend` on the 5 identity-stamped records | Production is not an independent `panel` control |
| Common scored universe | 87 / 89 union, Jaccard `0.977528089888` | Books are nearly the same universe |
| Top-10 overlap | 10 / 10, Jaccard `1.0` | No top-book contrast on this date |
| Spearman score-rank correlation | `0.999744842167` | The two score books are nearly identical |
| Mean absolute score delta | `0.019607155751` | Descriptive only; score units are not return units |
| `fwd_60d` values dated 2026-08-04 | 0 | Outcome is unmatured |

`active_scorer` is populated only for five records in each candidate table;
the other 83 score rows are blank. The audit reports that coverage rather than
claiming all 88 rows are identity-stamped. The populated records are still
sufficient to reject the proposition that the production arm is a verified
panel-only baseline. The result is therefore `NOT_EVALUABLE`, not a negative
result for zblend.

## Why the existing readout cannot answer this question

[`ops/renquant104/rq104_blend_readout.py`](../../ops/renquant104/rq104_blend_readout.py)
is a valuable historical `z(prod) + z(clf)` ledger. It is not an evaluation of
the present panel-plus-slow-momentum production scorer: its fallback gives a
name with no classifier score a production-only contribution, whereas the
deployed zblend has intersection semantics and drops names missing either leg.
It also sources a different component. Reusing that ledger as evidence for the
new zblend would silently change both treatment and estimand.

## Is there a better blend method?

There is no data-supported reason to replace equal z-sum immediately. The
reasonable alternatives have different failure modes:

| Method | Benefit | Requirement before use |
|---|---|---|
| Equal z-sum (current) | Transparent, no fitted weights, stable serving baseline | Keep it as the preregistered treatment |
| Equal rank average | More resistant to score outliers and changing z-scale | Predeclare it as a second treatment, not an after-the-fact replacement |
| Fixed, out-of-fold weighted blend | Can reward a demonstrably complementary component | Frozen historical training corpus, purged/embargoed out-of-fold predictions, and a separate untouched test period |
| Regime-conditioned or learned mixture | Could adapt to conditional efficacy | Materially more degrees of freedom; only consider after the fixed blend passes a properly controlled evaluation |

The correct next move is therefore better **measurement**, not more adaptive
weighting. Fitting a weight from this one nearly identical pair would be pure
noise fitting.

## Minimal prospective protocol

1. Restore a same-day, full-universe `panel` shadow control. It must use the
   same data cutoff, candidate universe, filters, portfolio rules, costs, and
   execution assumptions as zblend; only the scorer changes. It must persist
   scorer identity, component fingerprints, selected names, and score book for
   every scheduled session.
2. Retain zblend as the treatment with the exact frozen two-leg, equal-z-sum,
   intersection rule. Do not tune weights, components, Top-N, or horizon while
   collecting this comparison.
3. Complete the existing 20-session S1 run as an operational reliability test
   only. Twenty daily runs are not twenty independent `fwd_60d` return
   observations and cannot support a performance declaration.
4. Before S2, the backtesting owner must preregister the return estimand,
   cost model, blocked/non-overlapping evaluation units, and a power analysis
   on a frozen historical corpus. The inference method must account for the
   60-session overlapping-label dependence; daily t-tests do not.
5. Run S2 prospectively, wait for labels to mature, and report all scheduled
   sessions, including failed/degraded ones. Promote only if the predeclared
   effect and risk conditions pass; otherwise retain the panel baseline.

This protocol is intentionally proportionate: it adds a real control and
prevents invalid inference, without demanding a large research program before
the already planned operational S1 check.
