# renquant105 milestone M0 — data foundation

2026-06-27. Part of the renquant105 suite (master: `…-intraday-system.md`).
**No model, no trading in M0** — data only.

## Objective + scope
Stand up the intraday data layer on a **point-in-time, coverage-gated universe**: select
the universe *as-of each decision date* (no look-ahead), re-activate the parked intraday
cache + features under the **pinned-subrepo ownership model** (no triplication), switch the
daily full-rebuild to **incremental ingestion**, add a refresh cron, build the
**session-horizon (open→close) forward-return surface + feature panel**, and fingerprint
**feed/cost provenance**. Explicitly NOT in scope: any model, any scoring, any order.
**M0.5 (broker contract)** is a sibling milestone below — also gating, also no orders.

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
- F0.6 **Feed/cost provenance fingerprint (finding 5).** For every dataset, persist a
  fingerprint of: feed (IEX vs SIP), subscription tier, venue coverage, adjustment basis,
  bar-construction rule, and retrieval timestamp. **Assert the historical training bars
  share the live scoring path's IEX-only microstructure**; a mismatch fails M0. Capture a
  **measured** arrival/quote/fill sample (by ticker × time-of-day × order type) to seed the
  M1 cost model — the §A `11 bps` is an explicit placeholder this measurement replaces.
**Non-functional:**
- N0.1 Intraday coverage ≥ **95%** of the as-of universe (no NaN-leaf rows — the original
  calibrator-corruption cause), measured **point-in-time**, not over the full window.
- N0.2 Cache freshness during session < **2 min**; full 50-name refresh < **2 s**.
- N0.3 Panel build is reproducible + **placebo-clean** (no look-ahead via the open auction).

## Deliverables
`renquant-strategy-105` config skeleton + the **point-in-time universe manifest** (per-date
frozen + fingerprinted); the base-data-owned incremental ingestion code (one canonical copy
+ a contract test the pipeline imports) + the refresh cron; the **session-horizon forward-
return surface** + the intraday feature panel parquet; the **feed/cost provenance
fingerprints** + the measured cost sample; a **data-quality report** (point-in-time
coverage, freshness, NaN/gap rates per name).

## Metrics / KPIs
| Metric | Definition | Target |
|---|---|---|
| Point-in-time coverage | % of the as-of universe with complete bars at each date | ≥ 95% |
| Freshness | age of newest bar vs now, in-session | < 2 min |
| NaN/gap rate | fraction of NaN-leaf / missing bars in the panel | ~0% |
| Ingestion latency | wall time to refresh 50 names | < 2 s |
| Panel completeness | rows present / expected (names × bars × days) | ≥ 99% |
| Universe-manifest fingerprint | per-date frozen universe hash present | 100% of dates |
| Feed/cost provenance | feed/tier/venue/adjustment/bar-rule/retrieval fingerprinted | 100% of datasets |

## Acceptance criteria (gate to M1)
Point-in-time coverage ≥ **95%** on the as-of universe; freshness < **2 min** in-session;
NaN-leaf rate ≈ **0**; panel + session-horizon return surface build clean + placebo-checked;
**every date's universe is frozen + fingerprinted**; **feed/cost provenance fingerprinted**
and historical-vs-live IEX microstructure parity asserted; the refresh cron runs idempotently
for ≥ 5 sessions with 0 duplicate/overlap incidents; ingestion code lands as **one
base-data-owned copy** with a passing pipeline contract test (no triplication).

## Expected outcome (预期) + kill condition
A ~40–60 name **point-in-time** universe and a clean, fresh, incrementally-maintained
feature panel + session-horizon return surface, with feed/cost provenance fingerprinted.
**Kill:** if even a liquid subset can't reach ≥95% point-in-time coverage / NaN-free panels
on IEX, OR the historical bars cannot be shown to share the live IEX microstructure, the
intraday data foundation is infeasible on the free feed → stop (or re-scope to a SIP feed,
which is itself a fresh parity/cost experiment, before M1).

## Dependencies / inputs
The parked intraday infra (fetch/caches/feature builders); Alpaca free IEX (training
sufficiency to be *proven* by the provenance fingerprint, not assumed); the base-data-owned
ingestion primitive + pipeline loader contract (one canonical copy, master §6).

---

## M0.5 — Broker-contract checkpoint (finding 8; gating; no orders)
Encode the post-PDT broker contract before any size/leverage assumption is trusted. The
verified live flags (`pattern_day_trader=False`, `daytrade_count=0`, 4× BP) are NOT proof
the account is operationally unconstrained — the new regime is real-time intraday-margin
deficits + broker pre-trade checks, and Alpaca is **deprecating** the old PDT/day-trade fields.
- F0.5.1 Use the **current** `buying_power` / intraday-margin fields (not the deprecated
  PDT/day-trade fields) for every sizing/admissibility decision.
- F0.5.2 **Test rejection + margin-deficit handling in paper/shadow:** submit order
  sequences that should be rejected (insufficient BP, margin deficit) and assert the system
  fails closed (no silent retry, no double-submit) and reconciles.
- F0.5.3 Define **leverage caps independent of the broker maximum** (our cap ≤ broker max;
  the broker max is a ceiling, not a target).
- F0.5.4 **Fail closed on Alpaca API field migration/deprecation:** a missing/renamed field
  → NO_NEW_RISK, alert, operator review — never a guessed default.
**Acceptance:** all four encoded + shadow-tested; only then is the account described as
"operationally clear". **Until M0.5 passes, no live-size assumption is valid.**

## Risks (FMEA subset)
IEX coverage gaps (F1/F20 — DataFreshnessGate is session-day granular today, must go
intraday); **stale provenance / look-ahead universe** (mitigated by point-in-time
membership + per-date fingerprint); stale cache; ghost/
off-NBBO IEX prints contaminating features.

## Effort
~1–2 weeks (universe + ingestion + cron + panel + DQ report). Mostly wiring of
existing parked code, not new infra.
