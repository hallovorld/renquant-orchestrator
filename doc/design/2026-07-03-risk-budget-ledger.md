# Risk-budget ledger (107 sprint D3) — observe-only budgets / consumption / runway

DATE: 2026-07-03 · STATUS: implemented (read-only analysis tool, no prod wiring)
Package: `src/renquant_orchestrator/risk_budget/` (`budget.py`,
`attribution_bridge.py`, `report.py`) + `ops/renquant104/` wrapper + plist
(files only — install is a separate operator action).

## Objective

The 107 route's risk terms exist as prose in three places (the G* bar's
DD ≤ 15% HARD, RS-1 §2's β 0.6 planning heuristic, the pinned strategy
config's regime/per-name caps) and as a shadow sub-budget in pipeline #157 —
but nothing measures how much of any of them the book is actually using.
This module makes the budgets DATA (limit + kind + provenance) and measures
CURRENT consumption from read-only sources. It renders a statement; it never
gates, sizes, or trades.

## Budgets (as data, each with lineage)

| budget | limit | kind | source |
|---|---|---|---|
| max_drawdown | 0.15 | HARD | G* bar (#230 §4, master plan §0) |
| book_beta | 0.6 | planning | RS-1 §2 `β_max = 0.15/0.25` (PROVISIONAL per RS-1 itself; `sleeve.beta_max` mirrors) |
| per_name_concentration | per-regime | hard (existing) | pinned `regime_params[*].max_position_pct` — CONSUMED, not redefined |
| sleeve_dd_sub_budget | `sleeve.dd_budget_pct` (0.15) | sub-budget | pipeline #157 `ParkingSleeveShadowTask` |

Context controls reported WITHOUT breach semantics (they are enforcement that
already exists elsewhere): per-regime `cash_reserve_pct`,
`max_positions_per_sector`, per-regime `max_sector_weight_pct`, and the
regime detector's vol-gate thresholds.

## Consumption readers (budget.py) — measured, never assumed

- **Running max-DD**: `portfolio_daily_metrics` live equity curve (EOD-only,
  starts 2026-04-23 — both boundaries stamped into the statement). Breach
  driver = running max drawdown, conservative against the pipeline's own
  stamped `high_water_mark` when that exceeds the measured peak (two recorded
  sources that disagree are both reported).
- **β**, two measured views: (a) realized book β — OLS of book daily returns
  on SPY returns from the DB's persisted closes; (b) point-in-time
  composition Σ w_i·β_i with per-name β from the umbrella ohlcv daily closes
  (63-session window), plus the sleeve leg (w_SPY·1.0 + w_SGOV·0.0, the SGOV
  ≈ 0 simplification stated explicitly) when a sleeve shadow state exists.
  RS-1 §2's own first weakness is that β_pos = 1.0 was ASSUMED — this module
  closes that exact gap; a name with too few observations is censored, never
  imputed to 1. The DB's `beta_spy_252d` column is NULL on every live row
  (measured 2026-07-03) — recorded as censored-at-source.
- **Concentration**: latest run's `ticker_daily_state` weights → HHI (book
  and invested-normalized), effective N, top-name % vs the live regime's
  cap. The recorded `pipeline_runs.cash` column is inconsistent with
  PV − Σ positions on the live DB (~13% of book, 2026-07-02) — cash weight
  is derived from positions and the identity gap is surfaced.
- **Burn/runway**: consumption delta per session over a trailing window;
  runway = remaining budget / burn when burning, an explicit not-burning
  state otherwise.
- **Sleeve**: reads the #157 shadow JSONL (`sleeve_contribution_pct`,
  `dd_budget_consumption_pct`, running max) and evaluates the RS-1 reversal
  inputs (negative 3-month contribution AND >50% sub-budget consumption).
  The log does not exist today (flag default-OFF) — an explicit absent
  state.

## Attribution bridge (attribution_bridge.py)

Consumes the merged attribution engine (`renquant_orchestrator.attribution`)
— round trips + the five-leg identity with its enforced sum-check — and only
aggregates: per-leg totals over full history AND over the current DD window
(peak date → as-of), censored legs counted with reasons (#253 boundary
first-class). Leg semantics are restated in the output: MARKET/SIGNAL are
decision-quality dollars on intended notional; TIMING/SIZING/COST require
confirmed fills; negative legs are the DD-budget consumers.

## Statement + breach semantics (report.py)

Per budget, on its consumption fraction: `> 0.80` → WARN (exit 2),
`>= 1.00` → CRITICAL (exit 1), censored can never breach (a silent skip is
not a pass, but an unmeasurable budget must not fake a reading). Process exit
code = worst across budgets, same 0/1/2 convention as the rq104
scorer-identity monitor; the ops wrapper ntfys on WARN/CRITICAL/crash.
Writer refuses umbrella `data/`/`runtime/` paths (identical guard to the
attribution reporter).

## First real statement (2026-07-02 close) — the findings

- **book_beta CRITICAL 124%**: pt-composition β ≈ 0.745 vs the 0.6 planning
  budget. Driver: MU β = 4.29 (63d, verified against raw ohlcv; MU $366 →
  $976 over the window) at 9.1% weight = 0.391 of book β on its own —
  65% of the whole budget in one name. Realized book β is 0.394 (n=48,
  R² 0.14) because the book was less deployed over the trailing window; the
  breach driver is the conservative (point-in-time) view.
- **max_drawdown OK at 50.2% consumed**: running max DD 7.5% (06-02 → 06-11)
  vs 15%; current DD 4.3%; burn ≈ 1.4% of budget/session over the last 21
  sessions → runway ≈ 53 sessions at that pace.
- **per_name_concentration WARN 81.3%**: PANW 9.8% vs the BULL_CALM 12% cap.
- **Leg finding**: SIZING is the only negative leg — −$1,182 full-history,
  −$1,206 inside the current DD window (shrinkage stack + whole-share
  artifacts), while TIMING is +$180 and COST $0 recorded. Caveat stated in
  the statement: 74/99 records have TIMING/SIZING/COST censored by the #253
  fill-confirmation boundary, so the June-era leg picture is partial by
  construction until the umbrella-side fill writer lands.
- **sleeve_dd_sub_budget CENSORED**: shadow log absent (flag default-OFF).

## Non-goals / boundaries (the ownership line)

- No gates, no sizing, no trading behavior, no broker calls: orchestrator =
  orchestration/research/audit tooling only. If the β CRITICAL reading is to
  CHANGE behavior (e.g. a β-aware cap), that is a strategy/pipeline design
  PR — explicitly out of scope here and flagged as the follow-up decision.
- Budgets are not invented here: every limit cites the doc or config that
  owns it; per-name/regime caps are read from the PINNED strategy config
  (pinned runtime copy preferred over the sibling checkout).
- Run DB `mode=ro`; output writer refuses prod paths; no imputation anywhere
  — censored eras propagate with machine-readable reasons.
