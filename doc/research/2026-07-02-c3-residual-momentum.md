# C3 — regime-conditioned residual momentum: exploratory measurement — VERDICT: UNADJUDICATED

STATUS: EXPLORATORY/SENSITIVITY research measurement (read-only on all production data; one
committed script + committed JSON evidence). Was originally submitted as C3, the first
formally-voting candidate of the merged M-SIG stack (`doc/design/2026-07-02-m-sig-signal-stack-spec.md`,
PR #243) — Codex review found this run's SUBSTRATE (regime labels + universe membership)
carries future contamination that invalidates a formal confirmatory verdict; downgraded per
that review (round 2). **This is no longer C3's formal vote.**

**VERDICT: UNADJUDICATED — substrate/provenance limitations, NOT a tested-and-failed MISS.**
This run's regime labels and universe membership were NOT the ones knowable on each historical
decision date (see §6/§7 for the two specific contamination mechanisms), and neither a
production-emitted historical regime-label history nor point-in-time universe/delisting data
exists anywhere in this codebase (searched; none found — see §8). Genuine point-in-time
reconstruction is therefore not achievable within this fix's scope. A "MISS" implies the
frozen hypothesis was validly tested on point-in-time inputs and failed its bar; that is NOT
what happened here — the substrate itself is contaminated with hindsight, so the test that
was run is not the confirmatory test the spec calls for. The computed statistics below
(conditioned placebo-clean IC ≈ −0.004 vs. the +0.015 bar, conditioned-minus-unconditioned
difference ≈ +0.0086 with a CI spanning zero on every seed) remain USEFUL EXPLORATORY EVIDENCE
— they are simply not eligible to cast C3's formal GO/KILL vote. C3 does NOT close under this
run; a genuinely point-in-time rerun (or an accepted substitute substrate) remains open future
work, not a settled negative.

## 1. What was measured (frozen estimand, spec section 1.3)

`mom_12_1` (252-trading-day price return excluding the most recent 21 days), cross-sectionally
rank-z scored per date, then orthogonalized per date to sector + market beta by OLS; the
residual is the C3 score. Evaluated ONLY in the pooled `BULL_CALM + BULL_VOLATILE` regime
cell, on placebo-clean differences (never absolute IC), verdict on fwd_60d excess-vs-SPY.

Frozen decision rule applied exactly as merged (spec sections 1.3 + 2a):

- GO iff (a) conditioned-cell placebo-clean IC one-sided 98.33% (Bonferroni k=3) CI lower
  bound > 0.015, AND (b) the conditioned-minus-unconditioned paired-difference one-sided
  98.33% CI lower bound > 0 — on all seeds {42, 43, 44}.
- KILL iff the conditioned 98.33% upper bound < 0.015 (spec), or conditioned <= unconditioned
  point-wise (measurement-dispatch frozen rule).
- Otherwise MISS/INCONCLUSIVE (mechanical rule output — see below).

**This mechanical rule, applied to THIS run's substrate-contaminated inputs, computes
MISS/INCONCLUSIVE (§2). Per the header verdict, that mechanical output does NOT get to stand
as C3's formal vote, because the inputs it was computed on are not the point-in-time inputs
the rule presumes — the governing verdict for C3 is UNADJUDICATED, not MISS.**

No threshold was altered. Where the measurement dispatch and the merged spec differed on
non-threshold mechanics, the MERGED SPEC governs the verdict and the dispatch variant is
reported as a labeled sensitivity (section 4 below); the verdict is identical under both.

## 2. Headline numbers (gating configuration: fwd_60d, daily cadence, beta 252d, block 60)

| Cell | n dates (clean) | mean real IC | mean placebo IC | mean placebo-clean IC | hit rate |
|---|---:|---:|---:|---:|---:|
| **Conditioned (BULL_CALM+BULL_VOLATILE)** | **1,833** | +0.0253 | +0.0275 | **−0.0040** | 0.531 |
| Unconditional (all regimes) | 2,266 | +0.0214 | +0.0323 | −0.0126 | 0.504 |
| BULL_CALM alone | 1,662 | +0.0271 | +0.0293 | −0.0031 | 0.533 |
| BULL_VOLATILE alone | 171 | +0.0094 | +0.0103 | −0.0125 | 0.509 |
| BEAR alone | 327 | −0.0037 | +0.0673 | −0.0719 | 0.343 |
| CHOPPY alone | 106 | +0.0290 | +0.0071 | +0.0210 | 0.538 |

Conditioned − unconditioned difference: **+0.0086**.

Block-bootstrap CIs (block=60, n_boot=2000; all three seeds reported, none cherry-picked).
**Round-2 correction**: the conditioned-cell bootstrap previously pre-filtered to an
in-cell-only array before drawing blocks, which could splice together regime episodes
separated by a calendar gap as if they were contiguous trading days (see §11). Recomputed
below with `block_bootstrap_conditional_mean`, which draws blocks from the FULL dated series
with the regime mask carried through — no single block can span a gap larger than its own
length. Point estimates are unchanged (they don't depend on the bootstrap); CIs shift
slightly:

| Seed | Conditioned clean: 95% CI | 98.33% one-sided LB | Difference: 95% CI | 98.33% one-sided LB |
|---|---|---:|---|---:|
| 42 | [−0.0527, +0.0452] | −0.0569 | [−0.0031, +0.0235] | −0.0039 |
| 43 | [−0.0497, +0.0449] | −0.0546 | [−0.0035, +0.0244] | −0.0043 |
| 44 | [−0.0534, +0.0470] | −0.0596 | [−0.0028, +0.0231] | −0.0038 |

Effective block coverage (diagnostic, §11): 37 of 37 non-overlapping 60-day blocks over the
gating series contain ≥2 conditioned-cell dates — the BULL_CALM+BULL_VOLATILE cell is dense
enough (81.3% of all dates, §6) that this particular series happens not to exhibit the sparse
long-gap pathology the fix targets; the fix is a genuine methodology correction regardless of
whether this specific dataset was materially affected by the bug it closes.

- Leg (a): FAILS decisively — the conditioned point estimate (−0.0040) is below zero, let
  alone the +0.015 bar; every seed's 98.33% LB is ~−0.05 to −0.06.
- Leg (b): FAILS — the difference is positive (+0.0086) but every CI (95% two-sided AND
  98.33% one-sided) includes zero.
- KILL triggers: none fire (conditioned > unconditioned point-wise; conditioned UB ~+0.047
  is not < 0.015).
- Sample floor: met (1,833 conditioned clean dates >= 600; 37 effective 60-day blocks, all
  usable).

**These statistics remain informative exploratory evidence (§ intro) — they do not, on their
own, adjudicate C3 given the substrate contamination in §6/§7.**

**Reading**: the raw real IC in the bull cell (+0.0253) would naively look promising — and is
entirely explained by the placebo (+0.0275). Residual momentum's apparent bull-regime IC is
overlapping-horizon / regime-persistence label structure, not stock-selection alpha. This is
the placebo-clean-differences discipline (design rule 2, the ~+0.04 embargo-floor lesson)
doing exactly its job. The one cell where conditioning genuinely changes the picture is BEAR
(placebo-clean −0.072 — the classic momentum crash), which the conditioned cell excludes; that
exclusion is what produces the positive-but-not-significant +0.0086 difference.

## 3. Supporting horizon fwd_20d (never gates; block=20)

Conditioned +0.0029 vs unconditional +0.0004 (difference +0.0025, 95% CI [−0.0077, +0.0124]).
Same shape: nothing anywhere near the bar. Per-regime (clean): BULL_CALM +0.0116,
BULL_VOLATILE −0.0730, BEAR −0.0058, CHOPPY −0.0229.

## 4. Sensitivities (labeled; none gate; all agree with the verdict)

| Variant | n cond. dates | cond. clean | uncond. clean | diff | diff 95% CI |
|---|---:|---:|---:|---:|---|
| GATING (beta252, daily, block60) | 1,833 | −0.0040 | −0.0126 | +0.0086 | [−0.0031, +0.0235] |
| Dispatch bundle (beta120, stride-21, block13, 5000 boots, seed 42) | 89 | −0.0141 | −0.0133 | −0.0009 | [−0.0114, +0.0124] |
| block13 on gating series (daily, seed 42) | 1,833 | −0.0040 | −0.0126 | +0.0086 | [−0.0010, +0.0194] |
| beta120, daily, block60 | 1,833 | −0.0030 | −0.0120 | +0.0090 | [−0.0032, +0.0243] |

The verdict is NOT convention-fragile: under the dispatch's own stated convention the result
is if anything weaker (the stride-21 grid flips the difference slightly negative), and the
narrower block=13 CI still includes zero.

## 5. Interpretations resolved (every one stamped into the evidence JSON)

1. **block=60, not 13**: the measurement dispatch said "block=13, the A1 convention — state as
   resolved interpretation." Resolution: the merged spec r2/r3 explicitly resolved this open
   question (spec section 4 Q2) to block=60 = the fwd_60d label horizon, noting block=13 "was
   never actually adopted anywhere in this codebase as a block-size convention." block=13 is
   reported as a sensitivity; identical verdict.
2. **Beta window 252d** (spec-frozen fit window, section 1.3); the dispatch-stated 120d is a
   sensitivity; identical verdict.
3. **Daily decision dates**, per the spec's shared default ("daily Spearman rank IC", n>=600
   floor — a stride-21 grid structurally cannot meet the floor: it yields 89 conditioned
   dates); dispatch's stride-21 is a sensitivity.
4. **n_boot=2000, seeds {42,43,44} all reported** (spec shared default) for the gate;
   dispatch's 5000/seed-42 used in its sensitivity bundle.
5. **CI level**: one-sided 98.33% (Bonferroni k=3, spec section 2a) governs; two-sided 95%
   reported alongside. GO requires the rule to hold on all three seeds.
6. **Residualization form**: the spec 1.3 formula is realized as per-date cross-sectional OLS
   of the rank-z momentum on [const + sector dummies + trailing-window beta]: the "sector
   factor" is the per-date sector mean and the "market factor" the per-date cross-sectional
   premium on beta. Residuals verified orthogonal to beta per date (corr ~1e-15).
7. **Labels**: fwd_20d/fwd_60d PRICE-return excess vs SPY, clipped ±0.5 (repo label
   convention); verdict on fwd_60d, the strategy horizon; fwd_20d supporting only.
8. **Placebo**: label shifted +horizon within ticker (the fwd_h window starting at t+h);
   placebo-clean = real − placebo per date, defined only where both exist (the clean series
   therefore ends ~2×horizon before the last bar, 2026-01 for fwd_60d).
9. **Conditioned cell pooled** (BULL_CALM ∪ BULL_VOLATILE) per spec 1.3; per-regime cuts
   reported as mandatory diagnostics only.
10. **Difference CI is paired** (spec 1.3 leg (b)): blocks are resampled from the FULL dated
    series and mean(in-cell) − mean(all) recomputed per resample — not two separate CIs
    compared by eye. The conditioned-cell-only CI resamples blocks over the conditioned
    subseries in date order (this repo's regime-sliced convention).
11. **Min 30 names per date** for both the 17-parameter cross-sectional regression and each
    IC (~2× parameters; the reference diagnostic's min_names=5 would be meaningless under a
    17-regressor residualization).
12. **Beta min_periods = window/2**; names with less paired history are excluded from that
    date's cross-section (no imputation), consistent with the spec's missingness stance.

## 6. Regime-label reconstruction fidelity

Labels come from TODAY'S production regime task chain — `HurstTask → CUSUMTask → GMMTask →
BEAROverrideTask → RegimeFinalizeTask` — imported from the PINNED
`.subrepo_runtime/repos/renquant-pipeline` sources and driven exactly as
`renquant_backtesting.analysis.analyze_manifest_sanity_placebo::build_regime_series` drives
them (same ctx contract, same sequential expanding-history replay), with the PINNED strategy
config (`.subrepo_runtime/repos/renquant-strategy-104/configs/strategy_config.json`, which
carries the 2026-06-11 false-BEAR-fix keys the umbrella copy lacks) and the production GMM
artifact (`backtesting/renquant_104/artifacts/prod/spy-gmm-regime.json`). All input hashes
are stamped in the evidence manifest. Known fidelity gaps, stated honestly:

- The GMM artifact was trained 2026-05-22 on the full SPY history — regime labels for dates
  before that are IN-SAMPLE for the GMM component (a limitation shared by every historical
  regime reconstruction with today's pinned artifact, including the reference diagnostic).
- The replay carries `RegimeState` forward sequentially from a fresh state at 2016, rather
  than the states production actually persisted day by day; and it replays TODAY'S pinned
  code/config over history, not the (older) code production ran on those dates.
- Resulting mix over 2,386 scored dates: BULL_CALM 1,744 / BEAR 329 / BULL_VOLATILE 196 /
  CHOPPY 117 — the conditioned cell is 81.3% of dates, consistent with the known "~79% of
  live time" BULL_CALM-dominance prior.

**Round-2 investigation: is a genuinely point-in-time rerun achievable?** Codex's review
required checking before defaulting to a reclassification. Searched this codebase
(`/Users/renhao/git/github/RenQuant`, including `.subrepo_runtime` sources and the
`runs.alpaca.db` schema) for: (a) any historical, production-EMITTED regime-label history
(i.e. regime classifications actually computed and recorded at the time, using only
data available as of each historical date) — none found; no regime-label history table,
file, or walk-forward-trained regime model exists; (b) point-in-time universe/delisting
data (a historical record of tradeable-universe membership per date, including names
later delisted/removed) — none found. Both searches returned zero results. Building either
from scratch (a genuine walk-forward regime model retrained at each historical date, or a
reconstructed historical universe with delisting records) is a materially larger effort than
this fix's scope — it would be a new data-engineering task, not a bootstrap/verdict
correction. **Conclusion: point-in-time reconstruction is NOT achievable within reasonable
scope for this round; the honest verdict is UNADJUDICATED (see header), not a rerun.**

## 7. Substrate + survivorship limitation

- **Substrate deviation, stated**: spec design rule 1 prescribes the S5/S8 durable
  pick-table + ledger substrate. That ledger has no multi-year history (it began collecting
  in June 2026), so this measurement — as directed by the measurement dispatch — runs on the
  durable committed umbrella OHLCV parquets (`data/ohlcv/<T>/1d.parquet`) over the 142
  unique tickers of `data/transformer_v4_wl200_clean.parquet`. This is committed, durable
  data (not an ad-hoc /tmp panel), but it is NOT the pick-table substrate.
- **Survivorship (round-2 correction: direction is NOT identified)**: the 142-name universe is
  fixed as of the 2026 panel and applied over the full 2017–2026 window; names are in the
  panel partly because they survived and mattered in 2026. The prior round of this doc claimed
  "survivorship makes the result conservative" — that claim is UNSUPPORTED and has been
  removed. Omitting delisted/removed names can raise OR lower momentum IC (surviving winners
  bias momentum's cross-sectional dispersion upward in some regimes and downward in others
  depending on which names would have been removed and when), can alter sector residuals (the
  sector composition of survivors differs from the true historical universe), and can change
  regime-conditioned differences in either direction (a regime's true conditioned effect could
  be attenuated or amplified by which names happen to survive into the fixed panel). This
  measurement does not identify the bias direction; it is a genuine, uncharacterized limitation
  of the substrate, not a conservative one.
- Prices are split-adjusted but not dividend-adjusted (price returns on both legs; the
  residual cross-sectional dividend-yield tilt is a stated, second-order limitation).
- Data hygiene: 142/142 tickers loaded; 8 single-day |return|>40% events across 10.5 years
  (AFRM/AMD/APP/OXY/RBLX/SMCI/SOFI/ZM — all verified earnings/news gaps, no split seams;
  NFLX's 10:1 2025-11-17 split shows no price seam).

## 8. Prospectivity claim — CORRECTED (round 2): weaker than originally stated

**What can actually be affirmed: no prior script in this repo's git history computed this
exact residual×regime×block-bootstrap combination before 2026-07-02.** The two nearest prior
artifacts are materially different measurements: `scripts/experiments/2026-06-23-residual-audit.py`
residualized the LABEL (fwd_60d_excess on sector+BETA60) to test an XGB retrain hypothesis —
no momentum signal, no regime conditioning, no block bootstrap; `scripts/regimemom.py`
conditioned RAW (un-residualized) mom_12_1 on a NON-production regime label (SPY 200-DMA
trend × expanding vol terciles), horizons fwd_20d/fwd_5d, Newey-West t-stats — no
residualization, no production BULL_CALM/BULL_VOLATILE labels, no block bootstrap, no fwd_60d.

**What that does NOT establish (the prior round's claim was too strong and has been
withdrawn): genuine prospectivity/confirmatory status.** "No identical prior script existed"
only rules out this EXACT combination having been run before — it does not establish that the
hypothesis, thresholds, transformations, universe, replay convention, or inspected outcomes
were fixed BEFORE this specific run's results were observed. Two things weaken the claim
further: (1) the merged spec (PR #243) and this result are BOTH dated 2026-07-02 — same-day
sequencing does not by itself demonstrate the freeze preceded result access; (2) `scripts/
experiments/2026-06-23-residual-audit.py` and `scripts/regimemom.py`, both acknowledged above,
are PRIOR momentum-family audits in this same codebase — their existence means the author(s)
of this measurement were not approaching momentum-family signals with a genuinely blank prior.
A specific-combination novelty check is necessary but not sufficient for prospectivity; a real
preregistration would additionally require a demonstrable timestamp for the frozen protocol
that provably precedes any access to this run's results, which does not exist here. This
measurement's evidentiary status is therefore EXPLORATORY, consistent with the corrected
verdict in the header.

## 9. Reproduce

```
/Users/renhao/git/github/RenQuant/.venv/bin/python \
    scripts/c3_residual_momentum.py --out doc/research/evidence/2026-07-02-c3
```

(Umbrella venv required — the production regime chain is Python>=3.10. Runtime ~4 minutes.
Deterministic: fixed seeds, pinned inputs; input SHA-256 hashes in the evidence manifest.)

Evidence: `doc/research/evidence/2026-07-02-c3/c3_results.json` (full stats, CIs, verdict,
manifest, interpretations), `c3_per_date_ic_fwd60.json` (per-date real/placebo/clean IC +
regime — sufficient to recompute every bootstrap independently), `c3_regime_series.json`
(the full reconstructed regime series).

## 10. Consequence for the M-SIG stack — CORRECTED (round 2): C3 does NOT close here

**This run casts NO formal vote (neither GO nor a design-rule-5 recorded MISS) — the prior
round's "C3 resolves as a recorded MISS... C3 is closed under design rule 3/5" language is
withdrawn.** A substrate-contaminated measurement cannot close a candidate under a rule that
presumes a valid confirmatory test was run. C3 remains OPEN pending either: (a) a rerun on
genuinely point-in-time regime labels and universe membership (not currently buildable within
reasonable scope — no historical regime-label history or point-in-time universe/delisting data
exists anywhere in this codebase, per the search in §6/§7), or (b) an explicit operator/design
decision to accept this substrate as a permanent limitation and re-adjudicate C3 under an
amended, honestly-scoped protocol. Until one of those happens, the M-SIG stack's dependency on
C3 (spec section 2a's operational order, alongside C4 and C2) is UNRESOLVED, not satisfied by
a MISS — this is a real open item for the stack, not a closed one. The exploratory statistics
in §2 (conditioned placebo-clean IC ≈ −0.004, difference ≈ +0.0086 with CI spanning zero) are
informative context for whoever picks this up next, but should not be read as having settled
the question.

## 11. Conditioned-cell bootstrap fix (round 2)

**Bug.** The conditioned-cell CI (§2's "Conditioned clean" columns) previously computed
`cond_vals = vals[in_cell]` — filtering to ONLY in-regime dates — BEFORE drawing 60-day
blocks from that filtered array via `block_bootstrap_means`. If two regime episodes are
separated by a calendar gap (e.g. an intervening BEAR/CHOPPY stretch), the filtered array
places the last in-cell date of one episode directly adjacent, in ARRAY POSITION, to the
first in-cell date of the next episode — so a single drawn "60-day block" spanning that
position could splice together dates that are actually months apart on the calendar, no
longer representing a genuine 60-trading-day dependence block. The difference-leg bootstrap
(`block_bootstrap_diff`) was already correct: it draws blocks from the FULL dated series with
the in-cell mask carried through per date, never pre-filtering.

**Fix.** New `block_bootstrap_conditional_mean` applies the SAME carried-mask pattern to the
conditioned-cell mean: blocks are drawn from the full dated series (so every single block's
underlying dates are genuinely contiguous trading days — a block can never silently collapse
a calendar gap larger than its own length), and only the in-cell values within each drawn
block are averaged. `effective_block_coverage` reports, as a diagnostic (not a bootstrap
statistic), how many of the full non-overlapping blocks over the actual series contain ≥2
in-cell observations — for this specific series, 37/37 (the BULL_CALM+BULL_VOLATILE cell is
81.3% of dates, dense enough that this dataset doesn't exhibit the sparse-episode pathology
severely, though the fix is a genuine correctness fix regardless of how much this particular
run was affected).

**Proof.** `tests/test_c3_residual_momentum.py` constructs a synthetic series with two
30-observation regime episodes separated by a 170-observation off-regime gap and directly
inspects single-block index spans (not aggregate resample means, which legitimately combine
multiple independently-drawn blocks in any moving-block bootstrap and are not themselves a
clean discriminator): every non-trivial single block drawn from the OLD pre-filtered approach
splices both episodes together; NO single block drawn from the FIXED full-series approach can
span both episodes, since a 45-length window cannot reach across a genuine 170-position gap.

**Effect on this run's numbers**: point estimates are unchanged (they don't depend on the
bootstrap); CIs shift by roughly 0.001-0.005 (e.g. seed 42's conditioned 98.33% LB moves from
−0.0549 to −0.0569) — small for this dataset given the high block coverage, but the fix
applies to every future run of this script regardless of episode density.
