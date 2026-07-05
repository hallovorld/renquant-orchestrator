# RenQuant-105 As-Built Architecture

> Intraday session decisioning system. This documents **what is implemented**
> as of 2026-07-04. Stage-1 and Stage-2 code delivered; NOT YET armed
> (shadow-first mandate).

## Purpose

105 evolves 104 from post-close batch (盘后) to during-session real-time
decisioning (盘中). The goal is execution quality, NOT intraday alpha
(Phase −1 measured net edge NEGATIVE: −6.4bps @IC 0.03 vs 220bps breakeven).
Holding period stays multi-day.

**S10 preliminary signal (2026-07-04, EXPLORATORY):** Open-auction IS
measurement on 36 matched live buys showed fills approximately competitive
with VWAP (mean −35 bps, CI includes zero). This is a directional signal,
NOT a definitive conclusion — see `doc/research/2026-07-04-open-auction-is-measurement.md`
§Data quality caveats for join-key, dedup, and outlier-exclusion limitations
that must be resolved before the §9.4 entry-leak thesis can be confirmed or
rejected.

## Architecture

```
104 daily run (class-A frozen signals)
  ↓
Session scheduler (Stage-1)
  → triple gate: config enabled + env flag + kill-switch absent
  → NYSE calendar session bounds (half-day aware)
  → 12-min tick cadence (720s default)
  → per-tick: capture class-C/D inputs → run_intraday_decision_tick (pipeline)
  → shadow decision log (JSONL, append-only)
  → entry window policy (entries stop at close − 30min; exits always allowed)
  → session manifest (frozen class-A/B + fingerprints)

Stage-2 live executor (dark, unarmable today)
  → quintuple gate: config mode=live + authorization file + env flag
    + kill-switch absent + canary envelope available
  → canary envelope: allowlist + cumulative loss budget + session ceiling
  → write-ahead action journal
  → dead-man switch
```

## Signal Contract (Four Classes)

| Class | Content | Timing | Mutability |
|---|---|---|---|
| A | Daily panel scores, calibrated μ/σ, regime label | Frozen at session start | Immutable within session |
| B | Book state, cash, positions, pending orders | Captured at session start | Immutable within session |
| C | Live account state (positions, fills, orders) | Polled every tick (GET-only) | Changes between ticks |
| D | Live quotes (bid/ask/mid per watchlist name) | Polled every tick | Changes between ticks |

## Key Modules (all in renquant-orchestrator)

| Module | Role | Tests |
|---|---|---|
| `intraday_session_scheduler.py` | Stage-1 session scheduler — shadow mode only, triple gate, tick loop | 53 |
| `intraday_live_executor.py` | Stage-2 gate + state-book integration — quintuple gate, canary enforcement | 187 |
| `entry_timing_policy.py` | 3 entry-timing policies (baseline/delay-fixed/gap-reversion-trigger) + shadow evaluator | 29 |
| `entry_timing_shadow.py` | Entry-timing shadow data collector (JSONL pilot) | — |
| `intraday_quote_logger.py` | Live tick feed collector (class-D quotes) | — |
| `intraday_pairing_logger.py` | Class-A/D pairing collector (signal vs reality) | — |
| `intraday_session_inputs.py` | Signal integrity guards: leak detection, staleness, fingerprinting | — |
| `intraday_replay_audit.py` | Replay harness: re-runs shadow decisions against persisted inputs for sim-parity verification | — |
| `intraday_session_runner.py` | Integration layer: wires quintuple gate → live or shadow, software stops each tick | 18 |
| `software_stop.py` | Per-position hard + trailing stops (shadow-observe, then fold into live decisions when armed) | 21 |

### Cross-repo Slices

| Module | Repo | Role |
|---|---|---|
| `order_state_machine.py` | renquant-execution | Slice-1: order lifecycle FSM with economic/audit invariants (113 tests) |
| `intraday_decisioning.py` | renquant-pipeline | Slice-2: `run_intraday_decision_tick` — decision on live state with sim-parity pinned (18 tests) |

## Stage-2 Authorization Gate (Quintuple Gate)

All five must hold, evaluated independently every session:

1. **Config**: `intraday_decisioning.mode == "live"` in pinned strategy config
2. **Authorization file**: `data/rq105/stage2_authorization.json` — valid, unexpired,
   schema-checked; must contain `authorized_by`, `date`, `evidence` (≥5 clean shadow
   sessions + replay audits green + entry-timing report), `daily_entry_notional_cap`,
   `canary_allowlist`, `max_cumulative_loss_usd`, `expiry`
3. **Env flag**: `RENQUANT_INTRADAY_LIVE=1`
4. **Kill-switch file absent** (re-checked every cycle)
5. **Canary envelope available**: cumulative loss budget not tripped, session count
   below ceiling

Any missing gate → session runs SHADOW (fail closed). No partial arming.

## Canary Envelope (Campaign A4 — enforced)

- **Allowlist**: REQUIRED non-empty list of symbols; entries permitted only for
  allowlisted names; exits never blocked; absent/null/empty all FAIL validation
- **Cumulative loss budget**: `max_cumulative_loss_usd` (sticky trip across sessions —
  HARD halt, not per-session pause); realized + mark-to-market P&L tracked
- **Session ceiling**: `max_live_sessions` (default/hard cap = 20); at ceiling →
  envelope refuses to arm until re-authorization

## Entry-Timing Policies

| Policy | Behavior | Status |
|---|---|---|
| `baseline_open_delay` | Submit at first eligible tick after intent (control) | Shadow-evaluated |
| `delay_fixed` | Submit at `open + delay_minutes` | Shadow-evaluated |
| `gap_reversion_trigger` | Gap-up: wait for mid retrace of opening gap; gap-down: immediate | Shadow-evaluated |
| `vwap_chase` | Order slicing — explicitly OUT OF SCOPE (Stage 2+) | Declared, not implemented |

All policies have a HARD deadline (entry cutoff) after which they degrade to
SUBMIT-NOW (degradation recorded, never silently dropped).

## Collectors (launchd-scheduled)

| Collector | Output | Schedule |
|---|---|---|
| Quote logger | `data/rq105/intraday_tick_feed.jsonl` | Session hours, continuous |
| Pairing logger | `data/rq105/intraday_pairing_pilot.jsonl` | Session hours, continuous |
| Entry timing shadow | `logs/renquant105_pilot/entry_timing_policy_shadow.jsonl` | Per-tick within session |
| Liveness check | Alert-only (ntfy on missing/stale outputs) | Daily post-close |

## Software Stops (per-position)

| Type | Trigger | Default | Behavior |
|---|---|---|---|
| Hard stop | Unrealized loss ≥ hard_stop_pct from entry | 5% | Sticky exit signal, fires once per position per session |
| Trailing stop | Price drops ≥ trailing_stop_pct from session HWM | 3% | Updates HWM on new highs, fires on retracement |

Shadow-only by default (enabled=False in StopConfig). Stop signals are logged
to the shadow decision log; actual order submission requires the quintuple gate.

## Session Runner (Integration Layer)

The SessionRunner wires all 105 subsystems into one lifecycle:
1. Evaluate quintuple arming gate
2. If armed → drive LiveTickExecutor through tick loop
3. If NOT armed → delegate to SessionScheduler (shadow)
4. Software stops evaluated each tick regardless of mode
5. Kill switch checked every cycle

Safe degradation: no port_factory → always shadow. Non-session day → immediate
return with status=non_session_day.

## Current Status

- Stage-1 code: DELIVERED (PR #268 + dependencies)
- Stage-2 code: DELIVERED (PR #303 + campaign A4 canary enforcement)
- Session runner: DELIVERED (PR #335, merged)
- Software stops: DELIVERED (PR #335, merged)
- Shadow data collection: ACTIVE (collectors installed via launchd)
- Live arming: NOT YET (requires §9.3a quintuple gate + §9.4 economic authorization file + prereg)
- Entry-timing evidence: ACCUMULATING (shadow pilot)
- S10 execution leak: EXPLORATORY (2026-07-04, n=36 matched buys — see caveats in research memo)

## Cross-references

- [104 as-built](renquant-104-as-built.md) — 105 consumes 104's daily signals as frozen class-A inputs
- [106 as-built](renquant-106-as-built.md) — signal improvements from 106 feed 105's class-A quality
- [107 as-built](renquant-107-as-built.md) — 105 fills feed the attribution engine's TIMING leg
