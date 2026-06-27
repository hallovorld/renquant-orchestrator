# renquant105 milestone M0 — data foundation

2026-06-27. Part of the renquant105 suite (master: `…-intraday-system.md`).
**No alpha model, NO LIVE-CAPITAL ORDERS in M0.** M0 owns the data layer **and the calibrated
cost model** (finding 2). "No order" means **no order that risks live capital**; M0 *does*
submit **paper / zero-live-risk probes** (paper or randomized shadow orders that never touch
the live book) to gather H1-representative arrival/quote/fill observations. No scoring, no
alpha model, no live-capital order.

## Objective + scope
Stand up the intraday data layer on a **point-in-time, coverage-gated universe**: select
the universe *as-of each decision date* (no look-ahead), re-activate the parked intraday
cache + features under the **pinned-subrepo ownership model** (no triplication), switch the
daily full-rebuild to **incremental ingestion**, add a refresh cron, build the
**session-horizon (open→close) forward-return surface + feature panel**, and fingerprint
**feed/cost provenance**. Explicitly NOT in scope: any model, any scoring, any order.
**M0.5 (broker contract)** is a sibling milestone below — also gating, also no **live-capital**
orders (paper / zero-live-risk probes only).

## Requirements
**Functional:**
- F0.1 **Point-in-time universe selection (finding 4 — no look-ahead/survivorship).**
  Membership for decision date `d` is computed ONLY from information available at `d`:
  **lagged 20d ADV** (as-of `d−1`), **listing eligibility** (listed & not delisted at `d`),
  **halt/delist treatment** (a name halted/delisted at `d` is handled, not silently
  dropped from history), **corporate-action mapping** (split/ticker-change aware),
  **IPO seasoning** (≥ N sessions since listing), and a **fail-closed missingness policy**
  (a name with missing required bars at `d` is excluded *for `d`*, not retroactively).
  Target ~40–60 names by ADV rank. **REMOVED** the look-ahead rule "names that have
  complete intraday history over the window" (future availability must not determine past
  membership). Each date's universe is **frozen + fingerprinted in the dataset manifest**.
- F0.1b **Two-stage universe so the coverage gate is NOT gameable (finding 3 — Codex
  holistic).** The naive flow (drop a name on `d` when bars are missing, then measure
  ≥95% coverage on the already-filtered as-of universe) is **gameable**: exclude enough
  names and coverage trivially → 100%. Fix with **two distinct, separately-recorded sets**:
  1. **`ELIGIBLE_d` (the denominator, frozen FIRST, data-quality-blind):** the
     pre-data-quality eligible universe at `d`, computed **ONLY from LAGGED reference data**
     (lagged ADV, listing eligibility, IPO seasoning, corporate-action mapping as-of `d`) —
     **WITHOUT** looking at whether intraday bars are present. This is the **fixed
     denominator** for the coverage metric.
  2. **`TRADEABLE_d ⊆ ELIGIBLE_d` (the numerator-passing subset):** the names in `ELIGIBLE_d`
     that actually have complete, non-stale bars at `d`. **Coverage = |TRADEABLE_d| /
     |ELIGIBLE_d|**, measured against the **data-quality-blind denominator** — so excluding a
     name for missing bars *lowers* coverage (it cannot be gamed to 100%). The **tradeable
     subset is recorded SEPARATELY** in the manifest (both sets fingerprinted), and the
     trading universe is `TRADEABLE_d`, but the **gate is judged on the `ELIGIBLE_d`
     denominator**.
  - **As-of vintages + raw-vs-adjusted bars (finding 3).** Corporate-actions / listing
    metadata are stored with their **as-of vintage** (what was known at `d`), and bars are
    kept in **BOTH raw and adjusted** form with the adjustment basis fingerprinted — because a
    **retrieval-timestamp fingerprint alone does NOT stop a provider's later back-adjustment**
    from leaking future split/dividend knowledge into a past bar. M0 asserts the adjustment
    basis used at scoring matches the as-of vintage; a back-adjusted bar that disagrees with
    the as-of-`d` raw bar is flagged, not silently consumed.
- F0.2 New `renquant-strategy-105` config skeleton (the NEW pinned subrepo, master §6)
  with `hourly.enabled=true` / `minute.enabled=true` (lifting the 2026-05-04 daily-only
  mandate, scoped to 105) + the point-in-time universe manifest.
- F0.3 **Incremental** intraday ingestion (append-only per symbol/day; not the daily full
  concat) — **owned by `renquant-base-data`** (the canonical data layer), consumed by
  `renquant-pipeline` via the loader contract, **pinned** by the umbrella. **NOT** three
  hand-edited copies (finding 6); ownership/paired-PR matrix + pin order in master §6.
- F0.4 Refresh cron (`com.renquant.intraday105-data`) keeping `data/intraday/{SYM}/…`
  fresh; idempotent + `flock`-guarded (no cron-overlap dup — reliability F37).
- F0.5 **Session-horizon forward-return surface + feature panel.** Build the open→close
  (intraday-only, overnight-excluded) per-name per-session forward-return surface (the daily
  `ticker_forward_returns(fwd_1/5/…d)` surface is **insufficient** — finding 2) plus the
  intraday alpha158 + extras feature panel (re-enable `hourly_features.py`/
  `minute_features.py` + `tasks_build_hourly_panel.py`), all **bar-timestamped + session-aware**.
  **EVENT-TIME CONTRACT bound (finding 1):** the forward return is keyed from the **first
  executable quote/fill at or after `first_eligible_fill_ts`** (the master §3 chain), NOT the
  `bar_close_ts` price that produced the score — so the surface measures a *tradable* open→close
  return, not an inflated closed-bar-to-close one. Features end at the last **closed** bar.
- F0.6 **Feed/cost provenance fingerprint (finding 5).** For every dataset, persist a
  fingerprint of: feed (IEX vs SIP), subscription tier, venue coverage, adjustment basis,
  bar-construction rule, and retrieval timestamp. **Assert the historical training bars
  share the live scoring path's IEX-only microstructure**; a mismatch fails M0.
- F0.7 **M0's cost model — THREE SEPARATED LAYERS; paper probes are NOT a measured live cost
  (finding 4, Codex round-4).** Paper/shadow fills do **not** reproduce live queue priority, venue
  routing, latency, partial fills, or adverse selection, so a model "calibrated on paper probes"
  is **NOT** an "H1-representative MEASURED live cost". M0 therefore delivers **three explicitly
  separated artifacts**, never conflated, and **the H1 GO test runs on conservative BOUNDS with
  the uncertainty kept in the verdict** unless/until a representative live calibration exists:
  - **(a) Quote-derived spread BOUNDS (the gating input for a parked-alpha un-park).** From the
    historical quote series, a **conservative** round-trip cost **bound** by (ticker × time-of-day)
    = `2·(quoted_half_spread + conservative_slippage_floor + IEX_adverse_floor)`. This is a
    **bound, not a fill model** — it has no queue/partial/impact dynamics. The H1 net-edge GO
    (M1) is charged at the **conservative high end of this bound** and the verdict is reported
    **across the bound**, never at a single optimistic point.
  - **(b) Paper-WORKFLOW validation (NOT a cost number).** Paper / zero-live-risk probes validate
    the **workflow** (order submission, rejection/deficit handling, reconciliation, the
    event-time-contract capture) and the **relative** ordering of order shapes — they are used to
    exercise the pipeline, **not** to assert a live cost level. The paper-derived cost is
    explicitly labelled `paper_cost` and **never** substituted for a live cost.
  - **(c) Live-execution CALIBRATION (the ONLY thing that yields a measured live cost).** A
    measured live cost model requires **either** representative **historical live fills / market
    data** **or** a **separately operator-approved tiny live calibration experiment** (a few real
    fills under explicit operator authorization — never autonomous, never bundled into M0's
    "no-live-capital" probes). Until (c) exists, **no artifact may be called "H1-representative
    measured cost"**; the GO test uses the (a) bound + carries the uncertainty.
  - **Stratified estimator (applies to (a) and, if it exists, (c)):** cost by **(ticker ×
    time-of-day × order-type)** stratum; **min-N per stratum** (pinned `N_min ≥ 30`, set in
    config, not after seeing data); **stratification fallback** up a fixed hierarchy (ticker×ToD →
    ToD-only → pooled), recording the level used and **failing closed** for a stratum with no
    fallback; a **block-bootstrap CI** per stratum (cost charged uses the CI, not a point
    estimate); **out-of-sample calibration acceptance** (held-out slope ∈ [0.7, 1.3], bounded MAE)
    before any (c) live-calibrated estimator is accepted.
  - **Note (alpha is PARKED):** since the H1-alpha path is **parked** (master §0; Phase -1 net
    edge negative), the (c) live calibration is **not pursued now** — it is part of a future
    un-park, not the active program. The **active** use of M0's cost work is **H2** net-of-cost
    accounting, which likewise uses the conservative (a) bound + the H2.6 OOS-validated fill model
    with uncertainty propagated, never a paper number dressed as measured live cost.
**Non-functional:**
- N0.1 Intraday coverage ≥ **95%** measured as **|TRADEABLE_d| / |ELIGIBLE_d|** against the
  **data-quality-blind `ELIGIBLE_d` denominator** (F0.1b — NOT against the already-filtered
  as-of universe, which is gameable), point-in-time, not over the full window. No NaN-leaf rows
  (the original calibrator-corruption cause).
- N0.2 Cache freshness during session < **2 min**; full 50-name refresh < **2 s**.
- N0.3 Panel build is reproducible + **placebo-clean** (no look-ahead via the open auction).

## Deliverables
`renquant-strategy-105` config skeleton + the **point-in-time universe manifest** (per-date
frozen + fingerprinted); the base-data-owned incremental ingestion code (one canonical copy
+ a contract test the pipeline imports) + the refresh cron; the **session-horizon forward-
return surface** + the intraday feature panel parquet; the **feed/cost provenance
fingerprints**; **the CALIBRATED COST MODEL ARTIFACT (finding 2)** — the stratified
(ticker × time-of-day × order-type) cost estimator with per-stratum CIs, the stratification
fallback table, the minimum-N record, and the out-of-sample calibration report — built from the
measured arrival/quote/fill sample (existing 104 fills + paper / zero-live-risk H1-representative
probes); a **data-quality report** (point-in-time coverage, freshness, NaN/gap rates per name).

## Metrics / KPIs
| Metric | Definition | Target |
|---|---|---|
| Point-in-time coverage | **|TRADEABLE_d| / |ELIGIBLE_d|** (data-quality-blind denominator, F0.1b — not gameable) | ≥ 95% |
| Eligible/tradeable split recorded | both `ELIGIBLE_d` (lagged-ref-only) and `TRADEABLE_d` fingerprinted per date | 100% of dates |
| As-of vintage + raw/adjusted bars | corp-action/listing metadata stored with as-of vintage; bars kept raw AND adjusted, basis fingerprinted | 100% of dates |
| Freshness | age of newest bar vs now, in-session | < 2 min |
| NaN/gap rate | fraction of NaN-leaf / missing bars in the panel | ~0% |
| Ingestion latency | wall time to refresh 50 names | < 2 s |
| Panel completeness | rows present / expected (names × bars × days) | ≥ 99% |
| Universe-manifest fingerprint | per-date frozen universe hash present | 100% of dates |
| Feed/cost provenance | feed/tier/venue/adjustment/bar-rule/retrieval fingerprinted | 100% of datasets |
| Cost-model stratum coverage | strata (ticker×ToD×order-type) at/above N_min (else fallback recorded) | 100% calibrated or fallback-tagged |
| Cost-model min-N per stratum | measured fills/probes per calibrated stratum | ≥ **N_min** (pinned, e.g. 30) |
| Cost-model OOS calibration | predicted-vs-realized cost slope (held-out) | slope ∈ **[0.7, 1.3]**, bounded MAE |
| Cost-model CI present | per-stratum block-bootstrap CI on the cost estimate | 100% of strata |

## Acceptance criteria (gate to M1)
Point-in-time coverage ≥ **95%** measured as **|TRADEABLE_d| / |ELIGIBLE_d|** against the
**data-quality-blind `ELIGIBLE_d` denominator** (F0.1b — the gate cannot be gamed by excluding
names), with both sets + the as-of vintage + raw/adjusted bar basis fingerprinted; freshness <
**2 min** in-session;
NaN-leaf rate ≈ **0**; panel + session-horizon return surface build clean + placebo-checked;
**every date's universe is frozen + fingerprinted**; **feed/cost provenance fingerprinted**
and historical-vs-live IEX microstructure parity asserted; the refresh cron runs idempotently
for ≥ 5 sessions with 0 duplicate/overlap incidents; ingestion code lands as **one
base-data-owned copy** with a passing pipeline contract test (no triplication).
**Cost model (finding 4 — three separated layers, NOT a paper-as-measured-live conflation):** the
**(a) quote-derived spread BOUND** estimator EXISTS as an M0 artifact, stratified, with every
traded stratum at/above **N_min** or covered by the recorded fallback hierarchy, a **per-stratum
block-bootstrap CI**, and an out-of-sample calibration check (slope ∈ [0.7, 1.3], bounded MAE);
**(b) paper-WORKFLOW** validation is recorded as `paper_cost` and **NOT** treated as a live cost;
**(c) live-execution calibration** is **deferred** (it needs representative historical live fills
or a separately operator-approved tiny live experiment — and is moot while H1-alpha is parked).
A future M1 un-park is **charged at the conservative (a) bound with the uncertainty kept in the GO
test**, never a paper number called "measured live cost", and never the 11 bps placeholder.

## Expected outcome (预期) + kill condition
A ~40–60 name **point-in-time** universe and a clean, fresh, incrementally-maintained
feature panel + session-horizon return surface, with feed/cost provenance fingerprinted, **plus
the calibrated stratified cost-model artifact** (per-stratum CIs + OOS calibration) that M1
consumes — so the cost gate is measured, not the 11 bps placeholder, before M1 runs.
**Kill:** if even a liquid subset can't reach ≥95% point-in-time coverage / NaN-free panels
on IEX, OR the historical bars cannot be shown to share the live IEX microstructure, the
intraday data foundation is infeasible on the free feed → stop (or re-scope to a SIP feed,
which is itself a fresh parity/cost experiment, before M1).

## Dependencies / inputs
The parked intraday infra (fetch/caches/feature builders); Alpaca free IEX (training
sufficiency to be *proven* by the provenance fingerprint, not assumed); the base-data-owned
ingestion primitive + pipeline loader contract (one canonical copy, master §6).

---

## M0.5 — Broker-contract checkpoint (finding 8; gating; NO LIVE-CAPITAL ORDERS)
Encode the post-PDT broker contract before any size/leverage assumption is trusted. The
verified live flags (`pattern_day_trader=False`, `daytrade_count=0`, 4× BP) are NOT proof
the account is operationally unconstrained — the new regime is real-time intraday-margin
deficits + broker pre-trade checks, and Alpaca is **deprecating** the old PDT/day-trade fields.
**"No order" = no live-capital order; the rejection-sequence probes below are PAPER /
ZERO-LIVE-RISK orders** (paper account or randomized shadow), consistent with M0's
zero-live-risk probe semantics — they never risk the live book.
- F0.5.1 Use the **current** `buying_power` / intraday-margin fields (not the deprecated
  PDT/day-trade fields) for every sizing/admissibility decision.
- F0.5.2 **Test rejection + margin-deficit handling with PAPER / ZERO-LIVE-RISK probes:**
  submit order sequences (on the paper account / shadow path, **never live capital**) that
  should be rejected (insufficient BP, margin deficit) and assert the system fails closed (no
  silent retry, no double-submit) and reconciles.
- F0.5.3 Define **leverage caps independent of the broker maximum** (our cap ≤ broker max;
  the broker max is a ceiling, not a target).
- F0.5.4 **Fail closed on Alpaca API field migration/deprecation:** a missing/renamed field
  → NO_NEW_RISK, alert, operator review — never a guessed default.
**Acceptance:** all four encoded + shadow-tested; only then is the account described as
"operationally clear". **Until M0.5 passes, no live-size assumption is valid.**

## H2.0 — arrival-price + IS CAPTURE (observability/TCA; finding 2; gating for H2; NO LIVE-CAPITAL ORDERS)
**Moved OUT of M2 into this M0-class data milestone so H2 is independent of M1/M2 (master §7.0
DAG — this is the edge that breaks the round-3 cycle).** H2.0 builds the **per-104-order-intent
arrival-price capture + the implementation-shortfall (IS) module** that both H2 and M2 need:
- F0.6.1 **Per-intent arrival/fill record** (bar-timestamped, session-aware, event-time-contract
  bound — finding 1): for every 104 order intent persist `decision/arrival ts`, **arrival NBBO
  mid** at the decision instant, the 104 selection + size (given/immutable), the intraday IEX
  bars over the execution window, and the realized fill(s). Overnight excluded; all ts via
  `live.clock`.
- F0.6.2 **IS module (Perold):** `IS = (exec − arrival_mid)·side + delay + opportunity_cost`,
  net of the M0 cost model. This is the module **M2 CONSUMES and H2 CONSUMES** — neither owns it.
**Acceptance:** the capture wiring + IS module exist and reconcile against 104's real fills;
**no dependence on M1/M2** (entry = Phase -1 GO; runs parallel to M0). H2 (master `…-H2-…`) and
M2 both consume this artifact.

## Risks (FMEA subset)
IEX coverage gaps (F1/F20 — DataFreshnessGate is session-day granular today, must go
intraday); **stale provenance / look-ahead universe** (mitigated by point-in-time
membership + per-date fingerprint); stale cache; ghost/
off-NBBO IEX prints contaminating features.

## Effort
~1–2 weeks (universe + ingestion + cron + panel + DQ report). Mostly wiring of
existing parked code, not new infra.
