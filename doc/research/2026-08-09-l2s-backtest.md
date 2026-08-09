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
the cost ground truth) · `…-l2s-placebo.csv` (seed + delta, 200 rows) ·
`…-l2s-placebo-maps.csv` + `…-l2s-true-map.csv` (every seed's full
ticker→label map and the frozen 159-name enumeration; the verifier
re-derives each map from its seed) · `…-l2s-summary.json`.

## 1 · The four legs `[VERIFIED — summary + verifier recomputation]`

| leg | frozen bar | measured | result |
|---|---|---|---|
| Sharpe floor | composite ≥ global − 0.05 | **1.52 vs 0.91** (+0.61) | PASS |
| maxDD | composite ≤ global + 5pp | **−27.6% vs −30.1%** | PASS |
| sector tilt | ≥1 sector's local Hedge ends non-champion ≥ 0.40 | max non-champion ending weight **0.276** (software mom_slow) | **FAIL** |
| placebo | delta > permuted p95 (190th order statistic) | **+0.605 vs p95 +0.818** | **FAIL** |

RECORD-ONLY: the frozen rule requires all four. (The placebo leg gates the
verdict but is inadmissible for label-content inference — §2.)

## 2 · The reading — the honest one

The composite beats global-only by +10.7pp/+0.61 Sharpe net, and the
placebo GATE fails: 200 permuted sector maps — same tier sizes, scrambled
membership — produce a p95 delta of +0.818 (the frozen 190th ascending
order statistic), above the real map's +0.605. Under the frozen §4 rule
that demotes ADOPT-for-shadow to RECORD-ONLY, and the demotion stands.

What the placebo leg does NOT support (review r2/r3) is the stronger
reading this report first published — "the edge is width arithmetic, not
sector information". The frozen permutation ranges over all 159 mapped
names, including the two untradable ones (SPY `benchmark`, TLT
`defensive_bonds`) that the return matrix excludes; 189/200 seeds assign
at least one eligible label to SPY or TLT `[VERIFIED — re-derived from
the committed maps this session; e.g. seed 0 maps SPY→industrial,
TLT→finance]`, so a permuted book can hold fewer investable names than
the true-map book at the same nominal width. The fixed-width control the
design intended is not preserved, and the leg is therefore INADMISSIBLE
as evidence that sector labels carry no information — it is a gate, not a
mechanism verdict. Whether the labels carry information stays OPEN; a
permutation restricted to investable names would need a NEW dated design.

The tilt leg is the one that speaks to mechanism, and it found nothing:
no sector's local Hedge moved meaningfully off the prior in 541 days (max
ending non-champion weight 0.276) — at η=0.21 with ±5% clipping,
sector-book return differences do not accumulate fast enough to matter.
Mechanically consistent: `pure-local` (m=0) and the composite are
IDENTICAL to 3 decimals, because the local paths barely left the prior —
the m_s dial never got anything to dial.

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

* It does NOT kill sector structure — the tilt leg shows THIS mechanism
  (slow online reallocation over six thin concentrated books) extracted no
  sector signal in 541 days, and the book-structure effect (+0.61 Sharpe)
  is real. Whether the labels themselves carry information is NOT settled
  either way: the placebo leg is inadmissible for that question (§2), so
  the earlier "label-free" reading is withdrawn.
* The §3 table is the deliverable the original MoE vision wanted — and it
  says the panel already IS the chip expert, while slow momentum is the
  broad-sector expert. Any future sector design should start from those
  two facts, in a NEW dated prereg.
* The global L2 (merged engine) remains the standing allocation design;
  its shadow-job grant request stands unchanged.

## 6 · Corrections (review r2/r3, 2026-08-09)

1. **p95 arithmetic**: first publication computed the placebo p95 with an
   interpolating quantile (0.817848); the frozen rule pins the 190th
   ascending order statistic. Corrected to 0.817803 in the summary, the
   derivation and the verifier `[VERIFIED — recomputed from the committed
   deltas this session]`; the 3-dp display (+0.818) and the leg outcome
   (FAIL) are unchanged.
2. **Placebo artifacts**: the frozen design requires every seed's full
   ticker→label map committed and re-derived by the verifier; first
   publication committed only an anonymous delta column. Now committed:
   the seed column, `…-l2s-placebo-maps.csv` (all 200 maps) and
   `…-l2s-true-map.csv` (the frozen enumeration); the verifier re-derives
   every map from its seed and fails on any mismatch.
3. **Placebo inference narrowed**: the "width arithmetic, not sector
   information" reading is withdrawn as inadmissible (§2's structural
   SPY/TLT leak). The RECORD-ONLY verdict is unaffected — the sector-tilt
   leg fails independently.
