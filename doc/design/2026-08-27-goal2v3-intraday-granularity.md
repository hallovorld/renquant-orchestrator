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
closes vs official daily closes over the full span; a name/day whose drift
exceeds a pre-declared bound is excluded by RULE, not by hand.

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
Fetch 10-min bars for the current 145-name watchlist + the r2k dev names
where IEX carries them, development window only. Deliverables: coverage
census; IEX-vs-daily-close drift validation; regime labeling at 10-min
resolution (the 104 regime series upsampled + an intraday vol overlay,
frozen definition in the Stage I-0 doc); and the ESS table — non-overlapping
within-regime block counts at h ∈ {1, 3, 13, 39} bars (10-min bars: 39/day).
**KILL: if BEAR-regime n_eff < 30 blocks at h=13 in the development window,
the route is recorded dead and we stop.** (The daily line died at 2 blocks;
if 40× granularity cannot produce 30, conditioning is unfundable here too.)

**Stage I-1 — base models, life screen.**
Per the operator's spec: per-state base models (sector / regime / macro-trend
conditioned) on 10-min features, forward-chaining OOF inside the development
window only. Life-screen bar (frozen now): block-t ≥ 1.0 on the primary
horizon for at least one base, with the block structure from the Stage I-0
ESS table (gap ≥ h — block_length=h is the known defect). **No transformer
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
