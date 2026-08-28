# GOAL-2v3 — the stacked meta-model moves to intraday granularity

Status: DESIGN (operator-directed 2026-08-27, verbatim 「go」 selecting the
granularity fork recommended in the #1070 record; the fork itself follows
from the operator's ORIGINAL GOAL-2 spec, which named the granularity
upgrade explicitly: "我需要把当前的数据粒度升级到10分钟级别或者更小的粒度…
希望这个模型能够支持我105--live trading").

## 0. Why granularity, in one paragraph

Both daily-panel routes died on the same wall: effective sample. The
conditional-blend line (orch#1027 lineage) hit n_eff=0 at h=60; the v2
quality screen (#1070, merged) reached a 5.9× cross-section and STILL could
not clear t≥1.0 because the 2016–2019 development window holds **2 BEAR
blocks** — cross-sectional width cannot buy time-series inference. At 10-min
bars a regime-day contributes ~39 observations instead of 1: the same
calendar contains ~40× the within-regime blocks. Granularity attacks the
binding constraint directly; nothing else measured does.

## 1. Data substrate (measured 2026-08-27)

| source | span | cost | role |
|---|---|---|---|
| Alpaca market-data API, `timeframe=10Min`, `feed=iex` | **2020-07-27 → today** [VERIFIED: probe returned first bar 2020-07-27T13:30Z; requests before that clamp to it] | $0 (account already provisioned) | historical panel: features + labels |
| rq105 tick plane (`intraday_ticks.jsonl`, #216 logger, ~60s cadence, 145 names) | **2026-07-02 → today** [VERIFIED: first record] | $0 (live) | serving-parity substrate; the live leg of any graduated model |

Data-quality caveat, named up front: IEX is a thin feed (single-exchange
prints). Stage I-0 includes a mandatory validation: IEX 10-min session
closes vs official daily closes **over the DEVELOPMENT window only** — the
drift bound is calibrated, and the exclusion rule designed, on development
data exclusively (review r1: running it "over the full span" would consume
the sealed evaluation window). The resulting rule is FROZEN with the
confirmatory prereg and only then applied, unchanged, to evaluation data.
A name/day exceeding the bound is excluded by RULE, not by hand.

## 2. Window declarations (the part codex must hold us to)

- **Development window: 2020-08-01 → 2024-06-30** (~4 years, contains the
  2022 bear — the BEAR blocks the daily line never had).
- **Evaluation window: 2024-07-01 → 2026-06-30, UNTOUCHED** — same
  frozen-until-prereg contract as before: no fit, no peek, no screen touches
  it; it opens only for a confirmatory prereg frozen after development
  closes.
- **Consequence declared honestly**: using 2020–2023 intraday data for
  development formally **CLOSES the daily-panel line** — its reserved
  2020–2023 evaluation window can never again be run uncontaminated. Both
  daily routes are already dead on their own evidence (n_eff=0; t=0.756<1.0
  with the ESS diagnosis), so what is being surrendered is an option on a
  twice-failed route. The operator's 「go」 accepts this trade; this
  paragraph exists so the acceptance is on the record.

## 3. Staged plan (each stage gates the next; kill criteria pre-declared)

**Stage I-0 — substrate + ESS census (no modeling).**
Universe by TRAILING ELIGIBILITY RULE, frozen now (review r2: a
full-window coverage quota is forward-looking membership): a name is
eligible on session t iff, **using only information available by t**, it
has (a) ≥60 sessions of IEX history and (b) ≥80% coverage over the trailing
60 sessions. Eligibility is re-evaluated each session; a name that decays
below the bar exits the next session. No full-window quota, no
back-inclusion, no forward knowledge. The CANDIDATE SEED is not "every name
IEX carries" (no complete historical symbol master is available): it is the
union of the current 145-name watchlist, the r2k dev-name list, and the
fundamentals-panel universe — an ex-post enumeration whose survivorship
residual (names delisted before today never enter the seed) is a recorded
limitation affecting absolute IC levels more than base-vs-base comparisons.
Fetch covers the development window only. Deliverables: coverage
census; IEX-vs-daily-close drift validation; regime labeling at 10-min
resolution (the 104 regime series upsampled + an intraday vol overlay,
frozen definition in the Stage I-0 doc); and the ESS table.

**ESS is dependence-adjusted, not a block count** (review r1: with the
regime input largely an upsampled slow 104 state, adjacent intraday blocks
inside one regime episode stay dependent — granularity does not
automatically mint independent evidence). Frozen estimator and block
construction, declared before any census data is observed:

- Blocks are within-SESSION only: a block never spans an overnight; label
  windows are within-session forward windows and a window truncated by the
  close is DROPPED (no overnight return leaks into an intraday label).
- Non-overlapping blocks of length h with gap ≥ h between consecutive
  blocks, inside each contiguous regime episode.
- The I-0 dependence measurement needs a score, and I-0 fits no model
  (review r2: IC does not exist without predictions, and raw label
  autocorrelation is NOT an IC dependence estimate). The proxy score is
  therefore a FROZEN, parameter-free baseline declared here:
  **s₀ = −(trailing 13-bar return)** (short-horizon cross-sectional
  reversal — a fixed transformation of observed prices, not a fit).
  Justification for the proxy: block-mean-IC dependence is driven by the
  shared regime-episode clock and cross-sectional co-movement, which s₀'s
  IC series experiences on exactly the same blocks as any later base; the
  Stage I-1 report must re-estimate ρ̂₁ on each real base's own OOF IC and
  re-verify the kill margin (a base whose own n_eff_adj falls below the bar
  fails regardless of the I-0 proxy).
- Dependence adjustment: per regime, estimate the lag-1 autocorrelation
  ρ̂₁ of consecutive block-mean ICs of s₀ (episode-internal pairs only) and
  set **n_eff_adj = n_blocks · (1−ρ̂₁)/(1+ρ̂₁)**, ρ̂₁ floored at 0 (a
  negative estimate never INFLATES the sample) — the AR(1)
  effective-sample correction, per [[calibrate-on-the-estimands-dependence]].
  REPORTING CONTRACT (review r2 acceptance condition): every ESS table row
  carries raw block count, episode count, usable episode-internal pair
  count, ρ̂₁, and n_eff_adj; **if a regime has <8 episode-internal pairs,
  the estimator FAILS CLOSED** — ρ̂₁ is treated as unestimable and that
  regime's n_eff_adj is reported as "unestablished", which does NOT satisfy
  the kill-gate's ≥30 requirement.

**KILL: if BEAR-regime n_eff_adj < 30 at the primary horizon (h=13) in the
development window, the route is recorded dead and we stop.** (The daily
line died at 2 raw blocks; if 40× granularity cannot produce 30
dependence-ADJUSTED units, conditioning is unfundable here too.)

**Stage I-1 — base models, life screen.**
Per the operator's spec: per-state base models (sector / regime / macro-trend
conditioned) on 10-min features, forward-chaining OOF inside the development
window only. Life-screen bar (frozen now): block-t ≥ 1.0 at the **primary horizon,
declared here before any census data exists: h = 13 bars (≈2.2h)** — the
same horizon the kill criterion uses. Secondary horizons {1, 3, 39} are
DIAGNOSTIC ONLY: reported in every attempt record, never gating, never
promotable to primary after I-0 results are observed. Block structure from
the Stage I-0 ESS table (gap ≥ h — block_length=h is the known defect; t
computed on the dependence-adjusted units). **No transformer
and no meta-learner before at least one base passes.**

**Stage I-2 — the stacked meta-learner** (xgb first; anything heavier needs
its own gate) over surviving bases' OOF outputs + slow state. Same OOF
discipline. Only a Stage I-2 pass graduates to a confirmatory prereg frozen
against the untouched evaluation window.

**Stage I-3 — serving path (later, own PRs)**: the graduated model serves
from the rq105 tick plane (the live leg), reusing the S3 serving/parity
machinery. Explicitly out of scope here; no live flip is implied anywhere in
this design (S3-c remains an explicit operator ask).

## 4. Boundaries

- All fetches and panels live in isolated research paths (scratchpad /
  committed normalized artifacts per the #1070 pattern); **no production
  path is written**; ingestion graduates to a reviewed job only if a stage
  passes.
- Alpaca data calls are read-only market data on the existing account; $0.
- The development-selection protocol continues: every attempt lands in the
  attempt record; the evaluation window stays sealed; prereg only on a pass.

## 5. What would falsify the route quickly (cheap first)

Stage I-0 is deliberately front-loaded to be the kill point: if IEX coverage
of the wide universe is too thin, or the drift validation guts the panel, or
the ESS census misses the bar, the route dies for ~$0 and ~a day, recorded
in the same attempt log — before any model exists to fall in love with.


---

## Amendment A1 (2026-08-27, from #1073 review r2) — PENDING OPERATOR ACK

The original §1 deferred the drift bound to "a pre-declared bound" without
freezing numbers, and §3's block text left bar-time alignment implicit. Both
are frozen here; **the Stage I-0 GATE run is the rerun executed from the
main commit containing this amendment** — the 2026-08-27 evening runs are
recorded as development of the drift rule and the census mechanics, not as
gate results.

1. **Drift rule, frozen numerically**: layer 1 — a name-day is excluded
   from all downstream use when |IEX last-bar close / official daily close
   − 1| > **0.01**; layer 2 — a name is excluded entirely when its layer-1
   breach rate over its ELIGIBLE days exceeds **0.05**. Declared order:
   layer 1, then layer 2 (rate over eligible days only).
2. **Canonical bar grid**: every session is reindexed to the 39 canonical
   RTH 10-minute timestamps (09:30, 09:40, …, 15:50 ET); missing intervals
   are NaN. A (name, t) observation exists only when close[t−13], close[t],
   and close[t+13] are ALL present at canonical positions — array position
   is never treated as time. A session's block requires all 13 bar-time ICs
   (t=13..25) to exist, each from ≥100 names.
3. **Sufficient-statistics artifact**: the census commits name-by-session
   eligibility membership after BOTH drift layers, the layer-1 excluded
   name-day set, and the 13 per-session bar-time IC values — enough to
   regenerate the block series and the gate value without the mutable
   vendor bar store.

Operator acknowledgement: **[PENDING — to be quoted verbatim here with date
before the gate rerun counts]**.
