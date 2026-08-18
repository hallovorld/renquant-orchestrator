# Vol-state deployment window — CONFIRMATORY prereg (FROZEN before any scoring)

STATUS: **frozen confirmatory prereg (docs only — the run happens AFTER this merges AND
the committed runner is reviewed).** DATE: 2026-08-18. The last standing near-term
bull-alpha lead after the kill machine closed 0/5 zero-cost candidates (emitters #992,
tail_q90 #999, universe transfer #1000). Stakes declared: REFUTED closes the near-term
bull program's discovery arm.

## 1. Hypothesis + its formation data (exposure ledger, first)

**H (one-sided):** the panel's top-decile tail skill is positive when trailing market
volatility is elevated ("ON"), and this is where the bull-side skill lives.
**Formed on**: the 08-18 exploratory conditional map over the 625-day clf WF corpus
(**2023-10-03..2026-03-31**), COMMITTED IN THIS PR as
`doc/research/data/2026-08-18-tail-switch-formation/` (DEFINITIONS.md written before any
conditional statistic was computed; the four derivation scripts; the three result logs;
the intermediate series CSVs; input = the committed clf lineage bundle
`renquant-model doc/research/data/2026-08-01-clf-wf-lineage-bundle/clf_wf_scores.parquet`).
Formation numbers, from those committed logs: SPY-vol T3 spread +0.67-0.76 SD, block-t
+2.86..+3.10 (y_z10 T3 +0.76 t=+2.86 all-days / +0.67 t=+3.10 bull-only), vol-cohort-
matched T3 +10.7%/60d t=+3.12, block-σ≈0.54 (the §5 power input); ON-vs-OFF difference
NOT certified there (Welch t≈+1.56/+1.30); LOBO-fragile (t→~2.1). The confirmatory
therefore runs on data the hypothesis NEVER saw (§3).

## 2. Frozen state definition — plane-independent, PIT, deployable

**ON at date d ⇔ SPY 20-trading-day realized vol (close-to-close, annualized √252) >
13.5%** — the exploratory tercile boundary, frozen as a constant. Sensitivity variant
(reported, never decisive): expanding-window upper-tercile from 2015 with a 504-day
warmup. MEASURED (2026-08-18, committed-labels + SPY parquet, counted BEFORE this rule):
the two definitions agree closely on the primary corpus (821 vs 808 ON days; **19
ON-eligible blocks under BOTH**).
**Why not the regime label**: "BULL_VOLATILE" is three different things on the three
label planes (7% of days / 3 eligible blocks on the SERVING plane over the primary
corpus — measured, unusable; 44% on the GMM plane; 78% on the legacy plane). A deployed
window keyed to a raw PIT scalar has no detector dependence and survives the pending
regime-repair program unchanged.

## 3. Frozen corpora

- **PRIMARY (decisive): 2017-01-03..2023-09-29** — 1,697 trading days, strictly
  PRE-exploration (disjoint from the formation window). Geometry counted before the
  rule: 29 calendar 60d blocks; **19 ON-eligible** (≥15 ON days), 8 ON-dominant (≥45).
- **SECONDARY (reported, never decisive): 2017-01..2026-03** full window — larger but
  contains the formation data (contamination declared, which is WHY it cannot decide).
- Universe: the production panel dataset (292 tickers, survivor caveat DECLARED).
  Survivorship can bias BOTH levels and, in principle, the ON−OFF contrast itself —
  failures/delistings are state-dependent, so surviving-through-volatility selection can
  inflate high-vol-period spreads specifically. No claim here is called
  survivor-resistant; the survivor-independent evidence is the live-shadow burden every
  consequence in §5 carries (live data has no survivorship).
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

- **P1 (primary, one-sided, well-powered):** ON-state mean spread > 0 with block-t ≥
  **2.0** over the 19 ON-eligible primary blocks (df=18; one-sided). Exploratory
  observed ~+0.7 SD vs MDE ≈0.34 → powered; a miss is evidence, not bad luck.
- **P2 (secondary, structural):** ON-state minus OFF-state block-mean difference > 0
  with block-t ≥ **1.0** (annotation grade, declared underpowered ~50%). P2 is LESS
  level-sensitive than P1 (a within-corpus contrast), but it is NOT survivor-resistant:
  state-dependent delisting can bias the contrast too. The survivor-independent leg of
  every outcome is the live-shadow burden below.
- Guards: winsorized ±50% ON-spread ≥ 0 (anti-lottery); ≥15 ON-eligible blocks else
  UNMEASURABLE (fail-closed); positive control = the unconditional primary-corpus spread
  must be positive (instrument sanity) before any conditional read.
- **Verdicts (pre-frozen consequences):**
  - P1 AND P2 → **CONFIRMED** → authorizes ONLY a design PR for a vol-gated bull
    deployment window (shadow/sizing-first, operator-gated; no direct production
    change). ACTIVATION of any window remains contingent on live-shadow evidence
    (pre-committed: ≥20 ON-state live shadow sessions with positive realized spread) —
    the survivor-free confirmation no backtest on this panel can provide.
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
ON/OFF block tables for both corpora and both state definitions, the vol-matched
construction as tilt control (reported), full provenance tags. This prereg tests ONE
primary claim — no Holm family needed; the sensitivity variant and secondary corpus are
labeled non-decisive up front.
