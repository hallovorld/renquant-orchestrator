# Breadth does not buy evaluation precision — and the lever that does is gated on Stage 1

**Date:** 2026-07-29
**Status:** measurement, not a proposal. Nothing here asks for a decision.
**Reproduce every number below:**

```
python3 tools/breadth_precision_verify.py \
    --clf-corpus <corpus>/clf_wf_scores.parquet \
    --panel /Users/renhao/git/github/RenQuant/data/transformer_v4_wl200_clean.parquet
```

The script pins its inputs by sha256 and **aborts** on a mismatch, so a
different corpus cannot silently reproduce different numbers under this memo's
name. Every figure in this document is the script's own output.

| input | sha256 |
|---|---|
| `clf_wf_scores.parquet` | `1da3fcfa…5bc4efe4` |
| `clf_wf_manifest.json` | `c1cb22e2…7bd092086` |

---

## 1. Bottom line

1. Breadth is nearly useless for evaluation precision: at N=292 names/date,
   **91%** of per-date IC variance is breadth-proof `[VERIFIED — verifier]`.
   292 → 830 names buys **−2.9%** on the per-date IC standard deviation
   `[VERIFIED — verifier]`; an infinitely wide cross-section caps at **−4.4%**
   `[VERIFIED — verifier]`.
2. The binding constraint is **time**: both walk-forward corpora sit on **11**
   independent 60-day blocks `[VERIFIED — verifier / earlier this session]`.
3. The production panel holds **2,594 dates over 10.3 years = 43 blocks**
   `[VERIFIED — verifier]`, and the walk-forward corpora score only the newest
   625 of them. **We are using 24% of the available history** `[DERIVED —
   625/2594]`.
4. That unused 76% cannot be used as-is: the historical panel contains
   **zero** names that ever leave `[VERIFIED — verifier]`. It is the current
   142-name universe backfilled to 2016 — survivorship-contaminated.

**So Stage 1 is not hygiene. It is the enabler of the only lever that buys
resolving power.** Breadth was the stated Stage-2 mechanism; it is worth ~3%.
Depth is worth roughly a halving of the interval — and depth requires a
point-in-time panel, which is exactly what Stage 1 builds.

## 2. Breadth: method and result

Subsample the cross-section of the clf walk-forward corpus to `N` names per
date, recompute the per-date Spearman IC, and measure its variance against `N`.
Fit

```
Var(IC) = a + b/N
```

`b/N` is the finite-sample estimation term (shrinks with breadth); `a` is
everything else — genuine day-to-day variation in signal strength, regime, and
model instability. `a` is what breadth cannot touch.

Corpus `[VERIFIED — verifier]`: 178,191 rows, 625 score dates, 43 folds, 292
tickers, every row labelled. Restricted to the **594** dates carrying ≥250
names so the ladder is comparable across `N`; 3 draws per (date, `N`), each
seeded off `(date, N, replicate)` so the table is bit-reproducible.

| names/date `N` | Var(per-date IC) | sd |
|---:|---:|---:|
| 20 | 0.08437 | 0.2905 |
| 40 | 0.06043 | 0.2458 |
| 80 | 0.04619 | 0.2149 |
| 140 | 0.04228 | 0.2056 |
| 200 | 0.04051 | 0.2013 |
| 250 | 0.03944 | 0.1986 |
| 292 | 0.03899 | 0.1975 |

`[VERIFIED — verifier]` for every cell.

```
fit:  Var(IC) = 0.03530 + 0.9816/N        [VERIFIED — verifier]
irreducible share at N=292: 91%           [VERIFIED — verifier]
```

| `N` | sd | vs N=292 | tag |
|---:|---:|---:|---|
| 292 | 0.1966 | — | `[VERIFIED — verifier]` |
| 500 | 0.1930 | −1.8% | `[VERIFIED — verifier]` |
| **830** | **0.1910** | **−2.9%** | `[VERIFIED — verifier]` |
| 2000 | 0.1892 | −3.8% | `[VERIFIED — verifier]` |
| ∞ | 0.1879 | −4.4% | `[VERIFIED — verifier]` |

> **Correction against the first revision of this memo.** The ladder cells
> published earlier came from an unseeded run and differ in the third decimal at
> small `N` (e.g. `N=80`: 0.04832 then, 0.04619 now). Only the seeded verifier
> output is published now, because only it is reproducible. The fit, the 91%,
> and the −2.9% / −4.4% deltas are unchanged.

## 3. Corroboration that needs no fit

| corpus | names/date | mean IC | CI half-width | resolves? |
|---|---:|---:|---:|---|
| PatchTST | 142 | +0.0310 | 0.0562 | no |
| clf | 292 | +0.0608 | 0.0733 | no |
| prod XGB | — | +0.0731 | 0.1004 | no |

`[VERIFIED — measured earlier this session, moving-block bootstrap,
block_length=60]`

The clf corpus has **twice** PatchTST's cross-sectional width and a **wider**
interval. Both sit on 11 blocks. Width is not the axis the interval sits on.

## 4. Depth: the lever that is actually available

| quantity | value | tag |
|---|---:|---|
| panel date range | 2016-01-04 … 2026-04-28 | `[VERIFIED — verifier]` |
| panel dates | 2,594 | `[VERIFIED — verifier]` |
| span | 10.3 years | `[VERIFIED — verifier]` |
| 60-day blocks available | 43 | `[VERIFIED — verifier]` |
| blocks actually scored | 11 | `[VERIFIED — earlier this session]` |
| share of history used | 24% | `[DERIVED — 625/2594]` |

If the interval scaled as `1/sqrt(blocks)`, moving 11 → 43 blocks would take
PatchTST's half-width from 0.0562 to about **0.028** `[DERIVED — 0.0562 ×
sqrt(11/43); assumes 1/sqrt scaling, which the measured subsample curve decays
slightly slower than, so treat as optimistic]`. That is the first bound in this
programme that would sit below the point estimates being chased.

## 5. Why the unused history cannot simply be scored

| probe | result | tag |
|---|---:|---|
| tickers in panel | 142 | `[VERIFIED — verifier]` |
| tickers present on the final date | 142 | `[VERIFIED — verifier]` |
| tickers that ever appear but are absent at the end | **0** | `[VERIFIED — verifier]` |

Zero exits over 10.3 years is not a property of the market; it is the signature
of a universe list assembled today and backfilled. Scoring 2016–2023 on this
panel would buy blocks and import survivorship bias into the very statistic the
blocks were bought to sharpen.

This is precisely the defect GOAL-6 Stage 1 exists to remove.

## 6. What this does NOT say

It measures the precision of the **evaluation**, not the quality of the
**model**. Conflating those would be a serious error:

- A wider training panel may well produce a **better model** — more rows, more
  sector coverage, less overfitting to a narrow universe. Nothing here bears on
  that, and nothing here argues against building the 830-name panel.
- A wider **tradeable** universe has independent value: the top decile of 830
  is 83 candidates against 29, which changes portfolio construction and
  capacity.
- **Stage 1's survivorship justification is strengthened, not weakened.** §5 is
  an additional reason to build it, not a substitute reason.

What it does say: if Stage 2 is scoped, budgeted, or sequenced on the premise
that *breadth* will make results resolvable, that premise is off by roughly an
order of magnitude, and the depth lever should be costed alongside it.

## 7. Caveats

- Restricting to dates with ≥250 names means the `N=292` row occasionally draws
  from a slightly smaller pool; if anything this **understates** how flat the
  curve is. `[ASSUMED — direction argued, not measured]`
- The `a + b/N` form is fitted, not derived. It tracks the ladder closely
  (predicted 0.03865 vs measured 0.03899 at `N=292`) `[DERIVED — fit residual]`,
  but `N=2000` and `N=∞` are extrapolations.
- `a` is corpus- and model-specific. A signal with genuinely stabler day-to-day
  strength would carry a smaller `a`. Re-measure per corpus rather than assuming
  breadth helps more elsewhere. `[ASSUMED]`
- §4's 11 → 43 projection assumes the effect is stationary across 2016–2026. It
  is not obviously so (COVID, the 2022 rate shock). More blocks drawn from more
  heterogeneous regimes may raise `a` as well as raise the block count.
  `[ASSUMED — not measured]`

## 8. Provenance

Both inputs read **read-only**. The clf corpus lives in the quarantined scratch
namespace, as its own prereg requires; the panel is a production data file and
was opened for read only. No production data, config, or artifact was modified.
Corpus completeness `[VERIFIED — manifest]`: 43/43 folds, no smoke-only folds,
178,191/178,191 rows labelled, leakage contract enforced in code per fold
(`effective_train_cutoff_date + lookahead_days < first OOS score date`, raising
`AssertionError` rather than warning).
