# renquant105 milestone M0 — data foundation

2026-06-27. Part of the renquant105 suite (master: `…-intraday-system.md`).
**No model, no trading in M0** — data only.

## Objective + scope
Stand up the intraday data layer on a **liquid, coverage-gated universe**: select the
universe, re-activate the parked intraday cache + features, switch the daily
full-rebuild to **incremental ingestion**, add a refresh cron, and build the intraday
feature panel. Explicitly NOT in scope: any model, any scoring, any order.

## Requirements
**Functional:**
- F0.1 Universe selection: rule = top ~40–60 US large-caps by 20d ADV that have
  **complete intraday history** (the ~50% no-intraday-history names are excluded —
  the documented 2026-05-04 disable cause).
- F0.2 New `renquant-strategy-105` config skeleton with `hourly.enabled=true` /
  `minute.enabled=true` (lifting the 2026-05-04 daily-only mandate, scoped to 105).
- F0.3 **Incremental** intraday ingestion (append-only per symbol/day; not the daily
  full concat) — implemented across all **3 triplicated copies** (pipeline / base-data
  / umbrella).
- F0.4 Refresh cron (`com.renquant.intraday105-data`) keeping `data/intraday/{SYM}/…`
  fresh; idempotent + `flock`-guarded (no cron-overlap dup — reliability F37).
- F0.5 Intraday alpha158 + extras feature panel builder (re-enable
  `hourly_features.py`/`minute_features.py` + `tasks_build_hourly_panel.py`).
**Non-functional:**
- N0.1 Intraday coverage ≥ **95%** of the liquid universe (no NaN-leaf rows — the
  original calibrator-corruption cause).
- N0.2 Cache freshness during session < **2 min**; full 50-name refresh < **2 s**.
- N0.3 Panel build is reproducible + **placebo-clean** (no look-ahead via the open auction).

## Deliverables
`renquant-strategy-105` config skeleton; the liquid universe list (with the selection
rule + as-of snapshot); incremental ingestion code (×3 copies) + the refresh cron;
the intraday feature panel parquet; a **data-quality report** (coverage, freshness,
NaN/gap rates per name).

## Metrics / KPIs
| Metric | Definition | Target |
|---|---|---|
| Intraday coverage | % of universe with complete bars over the window | ≥ 95% |
| Freshness | age of newest bar vs now, in-session | < 2 min |
| NaN/gap rate | fraction of NaN-leaf / missing bars in the panel | ~0% |
| Ingestion latency | wall time to refresh 50 names | < 2 s |
| Panel completeness | rows present / expected (names × bars × days) | ≥ 99% |

## Acceptance criteria (gate to M1)
Intraday coverage ≥ **95%** on the liquid universe; freshness < **2 min** in-session;
NaN-leaf rate ≈ **0**; panel builds clean + placebo-checked; the refresh cron runs
idempotently for ≥ 5 sessions with 0 duplicate/overlap incidents.

## Expected outcome (预期) + kill condition
A ~40–60 name liquid universe with full intraday history and a clean, fresh,
incrementally-maintained feature panel. **Kill:** if even a liquid subset can't reach
≥95% coverage / NaN-free panels on IEX, the intraday data foundation is infeasible on
the free feed → stop (or re-scope to a $99 SIP feed before M1).

## Dependencies / inputs
The parked intraday infra (fetch/caches/feature builders); Alpaca free IEX (training
sufficiency confirmed); the 3 triplicated code copies.

## Risks (FMEA subset)
IEX coverage gaps (F1/F20 — DataFreshnessGate is session-day granular today, must go
intraday); triplicated-code drift (a change must touch all 3); stale cache; ghost/
off-NBBO IEX prints contaminating features.

## Effort
~1–2 weeks (universe + ingestion + cron + panel + DQ report). Mostly wiring of
existing parked code, not new infra.
