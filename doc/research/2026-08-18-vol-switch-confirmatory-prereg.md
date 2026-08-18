# Vol-state deployment window — CONFIRMATORY prereg (FROZEN before any scoring)

STATUS: **frozen confirmatory prereg (docs only — the run happens AFTER this merges AND
the committed runner is reviewed).** DATE: 2026-08-18. The last standing near-term
bull-alpha lead after the kill machine closed 0/5 zero-cost candidates (emitters #992,
tail_q90 #999, universe transfer #1000). Stakes declared: REFUTED closes the near-term
bull program's discovery arm.

## 1. Hypothesis + its formation data (exposure ledger, first)

**H (one-sided):** the panel's top-decile tail skill is positive when trailing market
volatility is elevated ("ON"), and this is where the bull-side skill lives.
**Formed on**: the 08-17/18 exploratory conditional map over the 625-date clf WF corpus
(**2023-10-03..2026-03-31**; 600 dates enter after the ≥100-names filter) — COMMITTED
with this prereg as `doc/research/data/2026-08-18-tail-switch-exploratory/` (frozen
definitions, scripts, result tables, series CSVs; number→file map in its README §2).
Key formation numbers [VERIFIED — that bundle]: SPY-vol T3 spread **+0.7556 SD**
all-days / **+0.6656** bull-only with block-t **+2.86 / +3.10**
(`conditional_results.txt`), surviving vol-cohort matching (matched T3 t=**+3.12**,
`volmatched_results.txt`; BULL_VOLATILE cohort t +3.45..+3.58); ON-vs-OFF difference
NOT certified there (Welch t=**+1.56**, `welch_mde.txt`); LOBO-fragile
(`diagnostics_results.txt` §1). The confirmatory therefore runs on data the hypothesis
NEVER saw (§3).

## 2. Frozen state definition — plane-independent, PIT, deployable

**ON at date d ⇔ SPY 20-trading-day realized vol (close-to-close, sample std ddof=1,
annualized √252) > 13.5%** — the exploratory upper-tercile boundary (all-days T3 edge
0.1375 / bull-only 0.1348, committed memo `welch_mde.txt`), frozen as the rounded
constant. Sensitivity variant (reported, never decisive): expanding-window
upper-tercile (66.7th percentile of all vol20 history ≤ d) with a **504-observation
warmup from the SPY series start 2016-01-04** — threshold first defined 2018-01-31;
the 271 earlier primary-corpus days are OFF by fail-closed convention (see
CORRECTIONS #4). MEASURED (2026-08-18, `data/ohlcv/SPY/1d.parquet`, re-measured under
§3's corrected block unit via the committed `geometry_check.py`): the two definitions
agree closely on the primary corpus — 821 vs 808 ON days; **19 ON-eligible blocks
under the fixed definition, 19 under the expanding, 18 under BOTH**.
**Why not the regime label**: "BULL_VOLATILE" is three different things on the three
label planes (7% of days / 3 eligible blocks on the SERVING plane over the primary
corpus — measured, unusable; 44% on the GMM plane; 78% on the legacy plane). A deployed
window keyed to a raw PIT scalar has no detector dependence and survives the pending
regime-repair program unchanged.

## 3. Frozen corpora

- **PRIMARY (decisive): 2017-01-03..2023-09-29** — 1,697 trading days, strictly
  PRE-exploration (disjoint from the formation window). **Block unit (frozen, per the
  repo's dependence canon,
  `doc/design/2026-07-09-governor-prereg-replay-protocol.md` §1.2 unit (ii)):**
  consecutive NON-OVERLAPPING **60-trading-day** blocks — **28 complete blocks**
  (1,697 // 60; trailing 17-td remainder dropped); **19 ON-eligible** (≥15 ON days,
  fixed definition), 8 ON-dominant (≥45) [VERIFIED — committed `geometry_check.py`].
  A block's outcome = the mean spread over its ON-state weekly cross-section dates.
  The blocks are NOT treated as independent: label windows of late-block
  cross-sections extend up to 59 td into the next block, and regime persistence adds
  serial dependence — §5's inference is dependence-robust by construction (canon r6).
  (The replay protocol's "60d horizon is DESCRIPTIVE-ONLY" ruling is a sample-size
  consequence of its ~497-session pool, N_blocks < 8 there; this corpus yields
  N = 28 total / 19 ON-eligible ≥ 8, with ESS checked at run time.)
- **SECONDARY (reported, never decisive): 2017-01..2026-03** full window — larger but
  contains the formation data (contamination declared, which is WHY it cannot decide).
- Universe: the production panel dataset (292 tickers, survivor caveat DECLARED —
  survivorship is STATE-DEPENDENT: failures/delistings cluster in stressed periods, so
  it can bias high-vol and low-vol periods differently and no in-corpus construction
  removes it; the survivor-clean evidence is the later PIT-universe check and the
  live-shadow stage, §5 consequences).
- Cross-sections weekly (every 5th trading day); h=60 labels; estimand construction =
  the capacity-memo instrument: per-date top-decile (by score) DGTW-adjusted spread
  (vol×mom×beta terciles, self-excluded, ≥15/cell else flagged-unadjusted).

## 4. Frozen scoring — reuse of the reviewed refit engine

WF scores from the production recipe VERBATIM (artifact fingerprint f8fb2259; 172
features + norms + params + fwd_60d_excess; rank:pairwise objective — the SERVED
construction, not a variant), quarterly expanding refits with the 60-trading-day embargo
(C+60td ≤ d), cutoffs 2016-Q2..2023-Q3 for the primary (extended ..2025-Q4 for the
secondary), fixed seed, no search. Machinery = the tail_q90 runner's reviewed refit
engine (#996/#999 lineage) with the objective left AT PRODUCTION — cite-and-reuse, not
rewrite. Estimated runtime minutes (the 31-refit run measured 221s).

## 5. Frozen decision rule (one shot; no re-runs; no threshold search)

- **P1 (primary, one-sided):** ON-state mean spread > 0 over the **19 fixed-definition
  ON-eligible primary blocks**, decided by the canon's dependence-robust CONJUNCTION
  (`2026-07-09-governor-prereg-replay-protocol.md` §1.2, applied verbatim to the ON
  block-mean series): **(a)** Newey-West (lag 1) SE computed ON THE BLOCK SERIES,
  small-sample t with df = N_on − 1, one-sided 95% CI excludes 0; AND **(b)**
  stationary block bootstrap on the same series (expected block length 2, 10,000
  resamples, fixed seed 0), one-sided 95th-percentile CI excludes 0. BOTH must pass;
  if they disagree, the result is reported as DISAGREEMENT and P1 FAILS (conservative,
  pre-frozen). No plain iid t-test — the first draft's `block-t ≥ 2.0 (df=18)` rule
  overstated the effective sample (CORRECTIONS #1/#2).
- **Power (recomputed for this unit):** with block-σ ≈ 0.54 [ASSUMED — imported from
  the formation corpus, 0.5343 uncond / 0.5410 BULL_VOLATILE (`welch_mde.txt`); the
  primary corpus's own block-σ is unknowable before the one run]: MDE at 80% power,
  one-sided α=0.05 [DERIVED — (t.95,ν + t.80,ν)·σ/√N] = **0.32 SD at N=19** under the
  independence approximation, degrading to **0.65 SD at the frozen ESS floor of 6**.
  The exploratory effect (+0.67..+0.76) clears even the ESS-floor MDE, with thin
  margin there — "powered" holds under these stated assumptions, strongly near
  N_eff = 19, marginally at the dependence floor; realized ρ̂₁/ESS are reported with
  the verdict.
- **P2 (secondary, structural):** ON-state minus OFF-state block-mean difference > 0
  with block-t ≥ **1.0** (annotation grade, declared underpowered ~50%). P2 is **less
  level-sensitive** than P1 (both states share one survivor universe, so a uniform
  level bias partially differences out) but NOT survivor-resistant: delistings are
  state-dependent, so survivorship can in principle push the ON−OFF contrast in either
  direction (CORRECTIONS #6). P2 carries no structural/deployment consequence on its
  own — every deployment-shaped consequence below stays contingent on the later
  PIT-universe check and live-shadow evidence.
- Guards: winsorized ±50% ON-spread ≥ 0 (anti-lottery); ≥15 ON-eligible blocks AND
  realized **ESS ≥ 6** on the ON block series (ESS = N·(1−ρ̂₁)/(1+ρ̂₁), ρ̂₁ = lag-1
  autocorrelation clipped below at 0 — canon §1.2 minima) else UNMEASURABLE
  (fail-closed); positive control = the unconditional primary-corpus spread must be
  positive (instrument sanity) before any conditional read.
- **Verdicts (pre-frozen consequences):**
  - P1 AND P2 → **CONFIRMED** → authorizes ONLY a design PR for a vol-gated bull
    deployment window (shadow/sizing-first, operator-gated; no direct production
    change; survivor-clean confirmation happens at the PIT-universe / live-shadow
    stage, not in this corpus).
  - P1 only → **PARTIAL** → shadow-forward path: the deployment-window design may
    proceed but its activation burden doubles (pre-committed: ≥40 live shadow sessions
    in ON-state with positive realized spread before any operator ask).
  - P1 fails → **REFUTED** → the vol-switch line closes; the near-term bull discovery
    arm is exhausted (recorded as such; remaining leads are the #213 asset (2027 clock)
    and G-B policy).

## 6. Execution contract

Runner committed AND REVIEWED before the run (its own PR; byte-identity execution gate,
one-shot marker, the §5 guards as hard assertions, per-date embargo assertion, state
counts recomputed vs §2/§3's frozen numbers). Results as their own PR: verdict first,
ON/OFF block tables for both corpora and both state definitions, realized ρ̂₁/ESS for
the decisive block series, the vol-matched construction as tilt control (reported),
full provenance tags. This prereg tests ONE primary claim — no Holm family needed; the
sensitivity variant and secondary corpus are labeled non-decisive up front.

## Corrections (2026-08-18, review round 1 — before any run; the freeze is this PR's merge)

All geometry re-measured this session from `data/ohlcv/SPY/1d.parquet` via the committed
`doc/research/data/2026-08-18-tail-switch-exploratory/geometry_check.py` (output in that
bundle's README §3). Corrected vs the first draft (d6cc05de):

1. **Block unit**: "29 calendar 60d blocks" → **28 non-overlapping 60-TRADING-day
   blocks** (1,697 // 60; 17-td remainder dropped). The draft's ~58.5-td blocks paired
   with h=60 labels shared label windows across adjacent blocks, so its iid inference
   overstated the effective sample.
2. **P1 inference**: iid `block-t ≥ 2.0 (df=18)` → the §1.2-canonical NW-on-blocks +
   stationary-bootstrap conjunction at one-sided α=0.05 with the N ≥ 8 / ESS ≥ 6
   minima (dependence-robust; conservative DISAGREEMENT-fails rule pre-frozen).
3. **ON-eligible counts**: "19 under BOTH" → 19 (fixed) / 19 (expanding) / **18 under
   BOTH**. Unchanged and reproduced: 1,697 corpus days, 821/808 ON days, 8 ON-dominant.
4. **Expanding-variant anchor**: "from 2015" was unmeasurable — no committed SPY
   history before 2016-01-04 exists locally. Re-frozen from the series start
   2016-01-04 (504-obs warmup → threshold first defined 2018-01-31; earlier corpus
   days OFF, fail-closed). The reproduced 808 ON days confirms the original
   measurement already used this construction.
5. **MDE**: "≈0.34" → 0.32 SD at N=19 / 0.65 SD at the ESS floor [DERIVED], with the
   block-σ input explicitly tagged [ASSUMED — formation corpus].
6. **Survivorship**: P2 re-labeled less-level-sensitive, NOT "survivor-resistant";
   deployment consequences made explicitly contingent on PIT-universe / live-shadow
   evidence.
