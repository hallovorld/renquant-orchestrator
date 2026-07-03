# M3 haircut AC-FAIL verdict: independent adversarial verification — WEAKENED
# (harm claim OVERTURNED as statistics; "not demonstrably helpful" + the
# blocking decision UPHELD)

DATE: 2026-07-03
TARGET: `doc/research/2026-07-02-m3-haircut-replay.md` +
`doc/research/evidence/2026-07-02-m3/*.json` + `scripts/m3_haircut_replay.py`
(merged). The M3 verdict blocked the `mu - k*SE > floor` config change and
shaped M4-b's design premise. Its own memo flags it as fragile (retired-era
outcomes, fwd_20d substituted for fwd_60d, SE a stability proxy, BEAR
unmeasured). This is an independent recomputation with own code — own SQL,
own SE implementation, outcomes recomputed from the ohlcv parquets, own
bootstrap (exact enumeration, not Monte Carlo) — plus the positive control
the original lacked.

Reproduce: `python3 scripts/m3_independent_verification.py` (sqlite
`mode=ro`; ~9 s). Evidence:
`doc/research/evidence/2026-07-03-m3-verification/m3_verification.json`.

## Verdict

| Claim | Ruling |
|---|---|
| **Strong claim: "the haircut is actively harmful at k=1.0/20d"** (delta −0.51 pp, block-5 CI [−0.89, −0.01] excluding 0) | **OVERTURNED as an inferential claim.** The point estimate and CI reproduce exactly, but the significance machinery is shown (by exact enumeration + a null control) to fire in the harm direction 28.4% of the time under a no-effect null (nominal 2.5%). A calibrated within-date permutation test gives p = 0.31. The negative delta is a noise-compatible point estimate, not evidence of harm. |
| **Weak claim: "the haircut is not demonstrably helpful"** (the #231 M3 AC: config PR only if the replay shows more losers than winners removed) | **UPHELD.** In every one of 15 reconstruction variants the fwd_20d haircut removes more winners than losers on point counts; no cell at any horizon/k shows a significantly positive delta under any inference engine; the thin-margin AC recomputes exactly as published (share 39.5% → 23.7%/20.0%, nowhere near ~0); the SE-undefined fixture hole (OXY/GRMN) stands. |
| **Decision consequence** | **UPHELD: keep the config change blocked.** The gate required positive evidence; there is none. But M4-b or any successor should NOT treat "the haircut hurts" as an established fact — only "unproven, with a winner-skewed removal pattern in one BULL_CALM window on retired scorers". |

Overall: **WEAKENED** — the verdict's conclusion survives; its strongest
evidentiary pillar (the significant harm cell) does not.

## What was recomputed and what it showed

### C1. Headline harm cell (fwd_20d, k=1.0) — reproduction exact, significance not credible

Own-code reproduction from the raw tables matches the published numbers
exactly: 26 canonical dates, 1,769 mu rows, 430 floor-clearing, 301 with SE,
universe 191 rows / 8 dates, 50 removed = 28W/22L, delta −0.51 pp; their
seeded MC block-5 CI reproduces to 1e-15 ([−0.887, −0.011] pp). Their SE
values match mine on all 1,769 rows (0 mismatches). `ticker_forward_returns`
matches an independent close-to-close recompute from the ohlcv parquets on
all 191 universe rows (max abs diff 0.0, zero winner-label flips) — the
outcome data itself is clean.

The inference does not hold up:

- **Exact enumeration replaces Monte Carlo.** With 8 dates and block length
  5, the circular block bootstrap has exactly 8^2 = 64 possible resamples.
  The "CI excludes 0" event rests on exactly **1 atom of 64** (exact
  P(delta >= 0) = 1.56%, two-sided p = 3.1%). Block-1: p ~ 0.10 (not
  significant, as their memo conceded). Block-3: 2.1%; block-4: 1.6%. The
  spec'd block-13 was degenerate. Significance is a block-length choice.
- **Null control (C3) shows the machinery is broken at this n.** Under
  within-date permutation of the real outcomes (no true effect by
  construction), the exact block-5 CI excludes zero **in the harm direction
  28.4% of the time** (nominal 2.5%; help direction 1.6%). With ~1.6
  effective blocks the bootstrap grossly underestimates variance, and the
  right-skew of the outcomes (HPE +59 pp, AMAT +45 pp rows) makes the
  spurious exclusions land almost entirely on the harm side — exactly the
  direction the study reported. The reported significance event happens
  under pure noise ~1 time in 3.5.
- **Calibrated tests find nothing.** Within-date permutation test (valid
  under within-date exchangeability, anti-conservative w.r.t. cross-date
  ticker dependence, i.e. the true p is larger): **p_one_sided = 0.31**.
  Naive i.i.d. anchor: kept-vs-removed gap −1.95 pp against a 13.6 pp row
  std → t = −0.87 under the most favorable possible independence
  assumption; clustering only widens this. Ticker-cluster bootstrap:
  CI [−1.92, +0.69] pp, P(delta >= 0) = 0.24.
- **Sensitivity grid (15 one-knob variants).** Sign of the delta: negative
  in all 15 — the *direction* is robust. Nominal exact-block-5 significance
  is not: it dies under SE-window-excludes-current-run (p=.056), no era
  stratification (p=.17), or min_obs=4 (p=.36, delta −0.11 pp); it
  strengthens under min_obs=5 (−0.98 pp) and run-threshold 30 (−0.77 pp);
  it is unchanged under ddof=0, window=5, either dedup repair, parquet
  outcomes, total-return outcomes, and era=fine. Notable: the original
  dedup rule silently picks a zero-mu run on 2026-05-08 (a mu-bearing
  same-day run exists — but its mu scale is uncalibrated ~0.0006, so
  repairing the dedup changes nothing material). fwd_20d for 06-04+ is
  unresolvable even from the parquets (only 19 post-06-04 trading days
  exist); their outcome window was genuinely maximal.

### C2. "Removed set were winners" (+5.9% vs +3.9%) — reproduces, but is a handful of names

Exact reproduction (removed +5.89%, kept +3.94%). Composition: the 50
removed rows span 39 tickers, but the **top-5 tickers account for ~100% of
the removed set's total excess** (HPE +59/+32 pp, AMAT x4 +35..+45 pp, CSCO
+28 pp, IBM, BAC). Removed winner counts by cost threshold: 32W/18L at
0 bps, 28W/22L at 11/25/50 bps — direction stable, never significant
(ticker-cluster P(delta>=0)=0.24). The mechanism is real as a description
of this window: a few May semis/hardware winners had volatile mu streams.
It is not evidence the haircut systematically removes winners.

### C3. Positive control (the lambda-sweep lesson — absent from the original)

Planted synthetic outcomes on the real universe where high-dispersion names
ARE losers (outcome = base − slope·rank(haircut deficit k·SE−margin) +
date shock + idio noise, noise matched to the real data: sigma_idio 13.4 pp,
sigma_date 1.9 pp; kept-minus-removed gap calibrated):

| planted gap (kept−removed) | exact block-5 detection | permutation detection |
|---|---|---|
| +2 pp (mirror of the claimed effect) | 35.6% | 13.0% |
| +4 pp | 57.4% | 26.6% |
| +8 pp | 88.6% | 64.0% |

The machinery CAN find a true planted positive (89% at 8 pp) — the harness
works. But at the effect size the study claims to have detected (2 pp),
block-5 detection is 35.6% against a 28-30% false-positive rate — a
likelihood ratio of ~1.2. **A significant cell at this sample size carries
almost no information either way.** (First planting attempt used rank(SE)
directly; the kept/removed rank(SE) gap is only ~0.05, forcing a slope whose
injected variance swamps the signal — documented in the script, not used.)

### C4. Thin-margin orthogonality — UPHELD

Recomputed independently: thin-margin share of admitted 39.5% → 23.7%
(k=0.5) / 20.0% (k=1.0); margin/SE p50 = 1.28, p90 = 11.0 (their published
quantiles reproduce to the last digit once one matches their
`statistics.stdev`-returns-exact-0.0 filter convention; numpy returns ~1e-19
for constant windows, and a 1e-9 tolerance gives p50 = 1.44 / p90 = 13.4 —
same qualitative claim). Spearman(margin, SE) = +0.31: margin and stability
are indeed near-orthogonal-to-weakly-positively-related; the haircut does
not zero out thin-margin admits. "Thin-margin buys → ~0 NOT MET" stands.

### C5. fwd_20d substitution + multiple comparisons — say it plainly

The 6 horizon-x-k cells: exactly **one** (fwd_20d k=1.0) is nominally
significant, with exact two-sided p = 0.031. fwd_10d k=1.0: p = 0.68;
fwd_5d k=1.0: p = 0.60; all k=0.5 cells positive-delta with p ~ 0.47-0.58.
Bonferroni threshold for 6 cells at 0.05 is 0.0083 — the headline cell
misses it by 4x. One-of-six at a boundary-grazing 0.03, measured at a
substituted horizon (fwd_20d for a 60d-native mu), with a machinery whose
empirical size is ~30%: this does not survive a multiple-comparisons look,
even before the null-control result. The harm claim rests entirely on that
single cell; the not-helpful claim does not (it needs only the absence of
any significantly positive cell, which all engines agree on).

## Honest limits of this verification

- Same retired-era data, same watchlist survivorship, same fwd_60d
  unresolvability as the original — nothing here validates or indicts mu.
- The permutation test's within-date exchangeability destroys cross-date
  ticker dependence; its p = 0.31 is if anything an *underestimate* of the
  true p. This only strengthens the overturning of the harm claim.
- The null/positive controls inherit the 8-date universe; they measure THIS
  study's machinery at THIS n, which is the relevant question.
- Nothing here re-litigates the M3 route chosen (observe-only thin-margin
  alert; revisit after S5 panel-era outcomes + a real persisted per-name
  uncertainty band). That route remains correct — and per this verification
  it should be argued from "insufficient evidence", not from "the haircut
  removes winners".

## Consequences

1. **Config change stays blocked** (AC not met; unchanged).
2. **Strike "actively harmful" from the standing record.** M4-b and any
   future haircut design should treat M3 as: *no evidence of help, harm
   unproven, sample uninformative at the claimed effect size*. The
   pre-declared "replay inconclusive" branch of the master plan is the
   accurate label after all — the original memo's closing claim that "the
   replay is not inconclusive" is the one sentence this verification
   overturns.
3. **Method note for future ledger replays** (S5 forward re-run): with
   <~15 dates, report exact-enumeration tail masses instead of MC quantile
   CIs, always pair a null control (empirical size) with any significance
   claim, and treat the date-block bootstrap as unusable when
   n_dates/block_len < ~4.
