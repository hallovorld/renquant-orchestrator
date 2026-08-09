# L2-S sector-conditional allocation — the one execution: RECORD-ONLY, and the sector table the design promised

The single execution of the merged frozen design
(`doc/design/2026-08-09-l2-sector-conditional-allocation.md`, orch#934 +
tags #935), run 2026-08-09 with zero deviations. **Verdict under the frozen
§4 rule: RECORD-ONLY** — the global L2 stands; the per-sector×arm table
below publishes as the answer to "which sector likes which model".

Reproducibility — scoped honestly (review r1): the DURABLE, repo-only
check is `data/2026-08-09-l2s-verify.py`, which from the committed
artifacts alone re-runs every recursion, re-derives every cost from
holdings, and recomputes legs and verdict `[VERIFIED — exit 0]`.
`data/2026-08-09-l2s-backtest-derivation.py` is the PROVENANCE RECORD of
the one execution, not a durable re-derivation path: it reads a
machine-local scratchpad snapshot of the #926/#927 replay artifacts plus
sibling-repo checkouts (digest-pinned in the committed manifests; static
inputs digest-verified against the #926 manifest; OHLCV checked
SUBSTANTIVELY — the rebuilt global gross series must reproduce #927's
committed CSV day-by-day, `[VERIFIED — gate output]`). Once that
scratchpad expires, the daily / holdings / placebo artifacts can no
longer be re-derived from the repo — only re-verified. Committed
artifacts: `…-l2s-daily.csv` (541 rows: every sector×arm book
gross/cost/net, global arm books, local + mixture weight paths, the three
composite series) · `…-l2s-holdings.csv` (every holding of every book,
the cost ground truth) · `…-l2s-placebo.csv` (200 seed deltas) ·
`…-l2s-summary.json`.

## 1 · The four legs `[VERIFIED — summary + verifier recomputation]`

| leg | frozen bar | measured | result |
|---|---|---|---|
| Sharpe floor | composite ≥ global − 0.05 | **1.52 vs 0.91** (+0.61) | PASS |
| maxDD | composite ≤ global + 5pp | **−27.6% vs −30.1%** | PASS |
| sector tilt | ≥1 sector's local Hedge ends non-champion ≥ 0.40 | max non-champion ending weight **0.276** (software mom_slow) | **FAIL** |
| placebo | delta > permuted p95 | **+0.605 vs p95 +0.818** | **FAIL** |

RECORD-ONLY: the frozen rule requires all four.

## 2 · The reading — the honest one

The composite beats global-only by +10.7pp/+0.61 Sharpe net, **but the
placebo says that edge is width arithmetic, not sector information**: 200
permuted sector maps — same tier sizes, scrambled membership — produce a
p95 delta of +0.818, ABOVE the real map's +0.605. Splitting capital into
six small concentrated books plus a pooled global replica is what helps;
WHICH names share a label contributes nothing detectable. The tilt leg
agrees from the other side: no sector's local Hedge moved meaningfully off
the prior in 541 days (max ending non-champion weight 0.276) — at η=0.21
with ±5% clipping, sector-book return differences do not accumulate fast
enough to matter. Mechanically consistent: `pure-local` (m=0) and the
composite are IDENTICAL to 3 decimals, because the local paths barely left
the prior — the m_s dial never got anything to dial.

## 3 · The table the operator asked for `[VERIFIED — committed daily CSV]`

Net Sharpe of each sector×arm standalone book, 541 days, general
holdings-cost rule:

| sector (width) | panel | mom_slow | mom_fast | best |
|---|---|---|---|---|
| software (26) | 0.60 | **1.31** | 0.71 | slow |
| industrial (21) | 0.96 | **1.52** | 1.06 | slow |
| finance (20) | 0.65 | **0.90** | 0.01 | slow |
| ai_chip (19) | **1.96** | 1.48 | 1.11 | **panel** |
| consumer (16) | −0.02 | 0.01 | 0.28 | (none clears 0.3) |
| datacenter_hw (14) | **2.49** | 1.62 | 1.11 | **panel** |

Three legible facts, each a hypothesis for future work, none a verdict:
1. **The "chips → fast momentum" intuition is contradicted at allocation
   level on this history**: the panel's ai_chip book (1.96) beats fast
   momentum's (1.11) — and the panel is at its strongest precisely in the
   two AI-hardware sectors (ai_chip, datacenter_hw 2.49).
2. **Slow momentum wins the three widest traditional sectors** (software,
   industrial, finance) — consistent with #927's whole-book finding that
   net-of-cost slow was the best single arm.
3. **Consumer supports no arm** (all ≤ 0.28) — a sector where abstention
   is the only defensible position.
Caveats: single history, correlated books, no multiplicity control across
18 cells — descriptive, as §4.4 of the design scoped it.

## 4 · Two harness defects the gates caught before any number existed

1. The first calendar build lost 13 days (528 vs 541) because the
   freshest-score state was reset per day instead of carried — caught by
   the substantive invariance gate against #927's committed CSV, which
   also proves the frozen window's OHLCV history is byte-equivalent where
   it matters (appended post-window bars are why raw digests drift).
2. Pre-run synthetic controls caught a floored local path and a missing
   score-to-trade lag (recorded in the derivation header). Both fixes
   moved the implementation TO the frozen design; no design constant moved.

## 5 · What this does and does not settle

* It does NOT kill sector structure — it shows THIS mechanism (slow online
  reallocation over six thin concentrated books) cannot distinguish real
  sector labels from permuted ones on 541 days, and prices the whole
  sector question honestly: the book-structure effect (+0.61 Sharpe) is
  real but label-free.
* The §3 table is the deliverable the original MoE vision wanted — and it
  says the panel already IS the chip expert, while slow momentum is the
  broad-sector expert. Any future sector design should start from those
  two facts, in a NEW dated prereg.
* The global L2 (merged engine) remains the standing allocation design;
  its shadow-job grant request stands unchanged.
