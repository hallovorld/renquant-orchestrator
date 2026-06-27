# renquant-105 Intraday — Reliability Analysis (FMEA + Fail-Safe Design)

**Status:** design / safety-gate doc (no code change). Read-only audit of the live
104 stack (`/Users/renhao/git/github/RenQuant`, `renquant-pipeline`,
`renquant-execution`, `renquant-orchestrator`) projected onto the proposed 30-min
intraday 105 system.
**Scope:** the prior 105 sketch (`doc/research/2026-06-12-intraday-trading-roadmap.md`
P0.1–P0.5; `doc/renquant-system-feature-map.md`) had **no** reliability analysis.
This is that analysis. It is a **gating doc**: 105 does not go live-armed until the
NEW mitigations marked `[105-BLOCKER]` exist and are shadow-validated.
**Operator fear addressed:** *"不靠谱的交易"* — an unintended / wrong / duplicate /
stale-priced trade. Every failure mode below is scored with a bias toward that
outcome, and the fail-safe spec is **default-deny**: no trade on any missing, stale,
or uncertain input.

---

## 0. Method

FMEA per the standard severity × occurrence × detection decomposition
(MIL-STD-1629A lineage; AIAG-VDA 2019 handbook). **RPN = S × L × D** on the
operator-requested **1–5** scales (not the classic 1–10), so RPN ∈ [1, 125]:

- **Severity (S)** 1 = cosmetic … 5 = real capital loss or an unintended live trade.
- **Likelihood (L)** 1 = rare … 5 = expected to occur in normal intraday operation.
- **Detectability (D)** 1 = caught automatically before any order … 5 = silent, only
  found post-mortem. (High D = *bad* — hard to detect.)
- **Action threshold:** any row with **S = 5 acts regardless of RPN** (per AIAG
  high-severity rule); otherwise **RPN ≥ 30** is mandatory-action, **18–29** is
  planned, **< 18** is monitored. Intraday raises the bar: the daily system fires
  the gate stack once a day; 105 fires it ~13×/session, so any non-determinism or
  partial-state failure mode gets +1 L versus 104.

The AIAG-VDA handbook notes RPN has known math defects (different S/L/D triples
collapse to the same product); we therefore treat RPN as a **triage sort key**, not
a verdict, and let the S=5 override and the explicit blocker list drive scope.

---

## 1. FMEA Table

Columns: **Component · Failure Mode · Effect · Cause · S · L · D · RPN · 104
mitigation (today) · NEW 105 mitigation**. "Unintended/bad trade" rows are marked
**⚠BAD-TRADE**.

### 1.1 Intraday data feed (Alpaca IEX — REST poll + planned websocket)

| # | Failure mode | Effect | Cause | S | L | D | RPN | 104 mitigation | NEW 105 mitigation |
|---|---|---|---|---|---|---|---|---|---|
| F1 ⚠ | **Stale IEX bar served as fresh** → trade on ghost/off-NBBO price | Buy/sell at a price that no longer exists; bad fill | Free IEX feed lags SIP; `fetch_intraday_bars` returns cache on timeout (`data_cache.py` returns stale cache + WARNING) | 5 | 4 | 4 | **80** | `DataFreshnessGate` is **NYSE-session-day** granular only — a 30-min-old intraday bar passes | **[105-BLOCKER]** bar-age gate in *minutes*: reject if `now_ny − bar.close_ts > 1.5 × bar_interval`; **fail-closed to no-trade**, never serve stale cache into a buy decision (only sells may use last-good per shorting mandate) |
| F2 ⚠ | **Websocket disconnect mid-session**, silent | Decisions on frozen prices; missed exits | TCP drop / Alpaca maintenance; no WS client exists yet (REST-only today) | 5 | 4 | 3 | **60** | n/a (no WS) | Heartbeat on WS; on gap > N s → mark feed UNHEALTHY → `skip_buys` + reconcile via REST; if REST also stale → **`NO_NEW_RISK`** (data-health failure; exits stay allowed), escalate to **`CANCEL_OPEN_ORDERS`** if the feed disagrees with broker |
| F3 ⚠ | **Acting on a partial (not-yet-closed) bar** | Signal computed on a half-formed bar; whipsaw entry | Polling at :15 reads the :00–:30 bar still forming | 5 | 4 | 4 | **80** | none (daily bars are always closed) | **[105-BLOCKER]** only consume bars where `bar.close_ts ≤ now`; drop the current forming bar; assert `bar_count == expected_closed_bars(session, now)` |
| F4 | Feed lag spike (latency blowout) | Decisions on minutes-old data | IEX congestion / network | 4 | 3 | 4 | 48 | none | p99 feed-lag SLO monitor; lag > threshold → degrade to sell-only |
| F5 | NBBO crossed / locked or zero/negative price tick | Garbage feature inputs | Bad print, halt auction | 5 | 2 | 3 | 30 | runtime feature clip ±5σ (`runtime_features.py`) masks but does not reject | Sanity gate: reject bar if `high<low`, price ≤ 0, or spread > X% → fail-closed |
| F6 | Symbol halted / LULD pause | Order rejected or queued at reopen at bad price | Single-stock halt | 4 | 2 | 3 | 24 | none | Pre-submit halt check via broker clock/asset status; skip halted symbol |
| F7 | Credential rotation / 401 cascade | Whole feed dark | `.env` ALPACA keys rotated | 4 | 2 | 2 | 16 | broker preflight `P-BROKER-CONNECT` (HARD) at run start | Per-window credential freshness probe; 401 → UNHEALTHY → no-trade |

### 1.2 Intraday cache / incremental ingestion

| # | Failure mode | Effect | Cause | S | L | D | RPN | 104 mitigation | NEW 105 mitigation |
|---|---|---|---|---|---|---|---|---|---|
| F8 ⚠ | **Parquet corruption on high-frequency write** → next read mixes stale+new | Features from corrupt panel → bad trade | 10-min cadence ⇒ 10–20 writes/min; `.tmp`+rename atomic on POSIX but contention-prone | 5 | 3 | 4 | **60** | `.tmp`+`replace` atomic write; corrupt-read → treat as miss (`intraday.py` INT-READ-RACE fix) | Single-writer ingestion process (no concurrent writers); checksum + bar-count assert on read; on mismatch → no-trade |
| F9 ⚠ | **Duplicate/overlapping bars on retry** silently overwrite good data | Wrong feature values | dedup `keep="last"` blindly trusts the later fetch | 4 | 3 | 4 | 48 | `concat → keep=last → sort_index` | Continuity assert: monotonic, no gaps in RTH; `keep="last"` only if values agree within ε, else quarantine + no-trade |
| F10 | Cold-start: no cache + fetch timeout | Run aborts (no data) | First bar of session, network down | 3 | 2 | 2 | 12 | returns `None` → downstream no-trade | Same; explicit "cold-start, no decision" ledger row |
| F11 ⚠ | **Gap-filled bar treated as real** | Decision on synthetic data | Forward-fill of a missing bar | 4 | 2 | 4 | 32 | none | Never forward-fill into a buy input; missing bar ⇒ symbol excluded this cycle (fail-closed) |

### 1.3 Feature pipeline

| # | Failure mode | Effect | Cause | S | L | D | RPN | 104 mitigation | NEW 105 mitigation |
|---|---|---|---|---|---|---|---|---|---|
| F12 ⚠ | **Train/serve feature skew** (alpha158 computed differently intraday) | Model sees out-of-distribution inputs → bad scores | 105 reuses alpha158 windows tuned on daily bars | 5 | 3 | 4 | **60** | shared low-level funcs invariant (compute == builder); `P-CONFIG-FP`, `P-FEATURE-COVER` | **[105-BLOCKER]** intraday-specific `config_fingerprint`; preflight asserts feature space + windows match the 105 training artifact, not 104's |
| F13 | NaN/inf in a feature | Garbage score | Division by zero vol on illiquid 30-min bar | 4 | 3 | 3 | 36 | `runtime_features` clip ±5σ; gates fail-SAFE to BLOCK on non-finite | Reject the *name* (not clip) when raw feature non-finite; ledger the drop |
| F14 ⚠ | **Look-ahead via current forming bar** in a rolling window | Inflated backtest, bad live entry | window includes `t` close that isn't final | 5 | 3 | 4 | **60** | daily bars always closed (no exposure) | Windows end at last *closed* bar; CI test replays a session and asserts no future leakage |

### 1.4 Model inference (GBDT + PatchTST)

| # | Failure mode | Effect | Cause | S | L | D | RPN | 104 mitigation | NEW 105 mitigation |
|---|---|---|---|---|---|---|---|---|---|
| F15 ⚠ | **Intraday model decay within a session** | Mid-day signal goes stale/wrong; bad entries late in session | model trained on close-to-close; regime shift intra-session | 5 | 3 | 5 | **75** | WF-gate at promotion only; no intra-session check | Per-session live-IC monitor on realized 30-min fwd returns; IC < floor for K bars → `skip_buys` for the session |
| F16 ⚠ | **Wrong/stale model artifact loaded** (104 weights on 105 path) | Systematically wrong scores all session | path mix-up; pin drift | 5 | 2 | 3 | 30 | `P-MODEL-ARTIFACT`, `P-PANEL-CONTRACT`, `P-WF-GATE`, `config_fingerprint` HARD-fail | Separate 105 artifact namespace + fingerprint; preflight refuses cross-system artifact |
| F17 ⚠ | **All-negative ranker mis-gated** (PatchTST raw ≈ −0.20) | raw>0 gate blocks 100% of longs *or* a flipped gate opens all | scores intrinsically negative | 5 | 2 | 2 | 20 | `signal_gate_prefer_calibrated_mu`: use μ>0 ⇔ raw>neutral_raw (BL-2 fix) | Carry the same μ-based direction gate; re-derive `neutral_raw` for the 105 model |
| F18 | Inference exception / NaN score | Name dropped | bad input row | 3 | 3 | 2 | 18 | non-finite μ/σ guarded in Kelly (K-1); name skipped | Same; ledger the skip |
| F19 ⚠ | **GBDT/PatchTST disagree, conjunction read as confidence** | False confidence sizing | treating 2 correlated models as independent votes | 4 | 3 | 4 | 48 | scorer lineup: PatchTST primary, XGB shadow-only (not a vote) | Keep XGB shadow-only; if ensembled, measure correlation, size on *joint* not product (see §4 gate-independence) |

### 1.5 Gate stack (G1–G8 + signal-direction + freshness)

Mapped to live tasks in `kernel/pipeline/task_gates.py`, aggregated by `GateRegistry`
(lattice `allow < halve < block`, **max-join**, risk-monotone). 104 gates already
**fail-SAFE to BLOCK** on non-finite inputs (audits MG-1/MG-2/G-1).

| # | Gate | Failure mode | Effect | S | L | D | RPN | 104 mitigation | NEW 105 mitigation |
|---|---|---|---|---|---|---|---|---|---|
| F20 ⚠ | **G-Freshness** (`DataFreshnessGate`) too coarse for intraday | passes a 30-min-stale bar → ⚠BAD-TRADE | session-day granularity only | 5 | 4 | 4 | **80** | session-day check | minute-level bar-age (see F1); this is the single most important 105 gate change |
| F21 ⚠ | **G-Signal-direction** misconfigured for 105 model | opens longs model is bearish on | wrong `neutral_raw` / μ off | 5 | 2 | 2 | 20 | `long_signal_ok` raw>0 ∧ μ>0 conjunction | re-validate per 105 artifact; CI placebo (§4) |
| F22 | **G-VelocityCrash / G-EMA50** (market gates) stale SPY | macro gate blind | SPY OHLCV missing | 4 | 2 | 2 | 16 | fail-SAFE BLOCK on missing/non-finite SPY | intraday SPY freshness same as F1 |
| F23 ⚠ | **Gate-config drift** (a gate silently disabled) | a guard you think is on is off | `enabled: false` left in 105 config | 5 | 2 | 4 | **40** | `config_fingerprint` covers config; ledger shows verdicts | preflight asserts the *expected gate set* is present and enabled; ledger row per gate every cycle |
| F24 ⚠ | **Non-independent gates → false aggregate confidence** | conjunction looks safe but all 8 gates keyed off one stale feed | shared upstream (one feed, one clock) | 5 | 3 | 5 | **75** | gates are independent *logically* but share data inputs | gate-independence audit (§4): tag each gate's input source; require ≥2 gates keyed off *independent* sources before a buy |
| F25 | DrawdownGate / FlattenCooldown miss intraday DD | buys into an intra-session crash | DD computed on daily HWM | 4 | 3 | 3 | 36 | daily-HWM `skip_buys`, hysteresis | intraday HWM + intraday DD halt (ties to §3 P&L breaker) |

### 1.6 QP / sizing

| # | Failure mode | Effect | Cause | S | L | D | RPN | 104 mitigation | NEW 105 mitigation |
|---|---|---|---|---|---|---|---|---|---|
| F26 ⚠ | **QP infeasible → wrong fallback** | unintended sizing | solver INFEASIBLE | 4 | 2 | 2 | 16 | returns **zero-trade** fallback (fail-closed), logs diagnostics | keep zero-trade fallback; alert on repeat infeasibility |
| F27 ⚠ | **Sizing on stale price / wrong notional** | over-size, breach notional | price input stale | 5 | 2 | 3 | 30 | Kelly `isfinite` guards (K-1); QP per-asset/budget/sector caps | recompute notional on the *fresh* bar at submit; AgentBreaker notional cap as backstop |
| F28 | Cash-drag penalty over-deploys | concentration | `λ_cash` forces deployment | 3 | 2 | 2 | 12 | hard `w_upper`, sector cap, 0.35 concentration | same caps; intraday per-name cap can be tighter |

### 1.7 Broker / order submission

| # | Failure mode | Effect | Cause | S | L | D | RPN | 104 mitigation | NEW 105 mitigation |
|---|---|---|---|---|---|---|---|---|---|
| F29 ⚠ | **Duplicate order on retry/timeout** | double position; ⚠BAD-TRADE | **equities path has NO `client_order_id` dedup**; timeout→retry→2 orders | 5 | 4 | 4 | **80** | options path is idempotent; **equities are not**; AgentBreaker caps *count* (25) but does not dedup | **[105-BLOCKER]** deterministic `client_order_id = hash(symbol, side, qty, session_bar_ts)`; broker rejects the dup. (SEC 15c3-5(c)(1)(ii) duplicative-order control.) |
| F30 ⚠ | **Broker error/timeout swallowed; partial fill unknown** | position state diverges from broker | `place_order` has no try/except; exception propagates with fill state unknown | 5 | 3 | 4 | **60** | minimal; `_assert_account_active`, expected-account env guard | reconcile loop: after every submit, poll order status; on unknown → mark UNRECONCILED → **`FULL_HALT`** (order-state integrity failure — order state is untrustworthy), no further orders until operator |
| F31 ⚠ | **Order sent to wrong account** | trades in the wrong book | account mix-up | 5 | 1 | 2 | 10 | `RENQUANT_EXPECTED_LIVE_ACCOUNT` hard match | keep; assert per submit |
| F32 ⚠ | **Slippage blowout on market order** | fills far from decision price | 105 uses MARKET orders, DAY TIF; thin 30-min liquidity | 5 | 3 | 3 | **45** | none (market orders only) | **[105-BLOCKER]** marketable-limit (limit = NBBO ± cap bps) instead of pure market; reject if implied slippage > X bps (15c3-5 erroneous-order price band) |
| F33 ⚠ | **Runaway order loop** | many orders fast | agent/pipeline loop bug | 5 | 2 | 2 | 20 | AgentBreaker P1 (≤25 orders/day) + P2 (≤$5k/day) | per-*session* and per-*window* sub-caps (e.g. ≤3 orders/window), not just per-day; message-rate throttle (FINRA 15-09) |

### 1.8 State persistence

| # | Failure mode | Effect | Cause | S | L | D | RPN | 104 mitigation | NEW 105 mitigation |
|---|---|---|---|---|---|---|---|---|---|
| F34 ⚠ | **`live_state.json` read-modify-write race** across overlapping cycles | lost holding/entry-date → wrong wash/exit decision | no atomic swap on live_state; intraday cadence increases overlap | 4 | 3 | 4 | 48 | v2 schema lossless round-trip; `parse()` fails loud on missing entry_date | single-writer + atomic swap (`.tmp`+rename) for live_state; run-lock (F38) removes the overlap |
| F35 | AgentBreaker counters lost on restart | day budget resets mid-session | in-process counters not persisted | 4 | 2 | 3 | 24 | by design (the durable kill-state marker is the surface) | persist intraday order/notional counters keyed by trading_date so a restart can't refill the budget |
| F36 | Decision-ledger write contention | missing forensic rows | multiple agents on one DB | 2 | 2 | 2 | 8 | WAL + 5s busy_timeout; `INSERT OR IGNORE` idempotent | same; ledger is append-only and idempotent already |

### 1.9 Cron / scheduler (launchd)

| # | Failure mode | Effect | Cause | S | L | D | RPN | 104 mitigation | NEW 105 mitigation |
|---|---|---|---|---|---|---|---|---|---|
| F37 ⚠ | **Cron overlap → duplicate orders** | two cycles submit the same intent | **no run-lock**; launchd assumed single-exec; a slow cycle overlaps the next 30-min fire | 5 | 4 | 4 | **80** | none (launchd only); per-run timestamped dirs reduce *artifact* collision but not order collision | **[105-BLOCKER]** flock-based run-lock keyed on `trading_date+window`; second fire exits immediately; combined with F29 idempotency |
| F38 ⚠ | **Clock / timezone / session-boundary error** | run on wrong session; day-roll at midnight Pacific not NYSE | 217 naive time sources repo-wide (intraday roadmap §4 P0.3); machine is Pacific | 5 | 3 | 4 | **60** | `live/clock.py` provides DST-proof `trading_date`/`ny_now`; `deadman_check` RTH uses NYSE calendar | **[105-BLOCKER]** route *all* session math through `live.clock`; CI lint bans naive `datetime.now()`/`date.today()` in 105 paths; DST-transition test (2026-11-01) |
| F39 ⚠ | **Watchdog/process hang** mid-session | frozen, no exits | hung process | 5 | 2 | 2 | 20 | `deadman_check.py` (P0.5): heartbeat > 180s stale during RTH → writes the durable halt marker (legacy TRADING_OFF maps to **`FULL_HALT`** under the 105 state machine); never auto-clears | keep; heartbeat from the 105 loop; 5-min launchd cadence → **`FULL_HALT`** (liveness failure: the decision loop is dead, so even exits can't be trusted); never auto-clears |
| F40 | Early-close / half-day mis-handling | run after close | holiday calendar | 3 | 2 | 2 | 12 | `_is_nyse_trading_day` + RTH window in `deadman`/`clock` | session windows from NYSE calendar; no fixed 16:00 assumption |

**Top RPN / S=5 action list (the "不靠谱交易" hot-list):**
F1, F3, F20 (stale/partial bar → bad price), F29, F37 (duplicate orders),
F30 (unreconciled broker error), F24/F15 (false confidence / intra-session decay),
F32 (slippage), F12/F14 (feature skew/look-ahead), F38 (clock). All of these are
either **[105-BLOCKER]** or carry an S=5 override.

---

## 2. Intraday-specific NEW failure modes — concrete mitigations

These do not exist in the daily 104 world and must be designed in:

1. **Stale IEX bar → ghost/off-NBBO trade (F1, F20).** Daily freshness is
   session-granular; intraday needs **minute granularity**. *Mitigation:* bar-age
   gate `now_ny − bar.close_ts > 1.5 × interval ⇒ no buy`; sells may use last-good
   per the shorting/exit mandate but log it. Never feed `data_cache`'s
   stale-cache-on-timeout fallback into a *buy*.

2. **Websocket disconnect mid-session (F2).** *Mitigation:* WS heartbeat; gap →
   feed UNHEALTHY → `skip_buys` + REST reconcile; double-failure → **`NO_NEW_RISK`**
   (data-health failure; exits stay allowed), escalating to **`CANCEL_OPEN_ORDERS`** on
   feed/broker disagreement.

3. **Partial (forming) bar (F3, F14).** *Mitigation:* consume only
   `bar.close_ts ≤ now`; drop the forming bar; assert expected closed-bar count.

4. **Feed lag (F4).** *Mitigation:* p99 lag SLO; breach → degrade to sell-only.

5. **Intra-session model decay (F15).** *Mitigation:* live-IC monitor on realized
   30-min forward returns; IC < floor for K bars ⇒ `skip_buys` rest of session.

6. **Non-independent gates → false confidence (F24).** *Mitigation:*
   gate-independence audit (§4) — a conjunction of 8 gates all keyed off one stale
   feed is **one** point of failure, not eight. Require ≥2 independent input sources.

7. **Slippage blowout (F32).** *Mitigation:* marketable-limit orders with a bps cap;
   reject if implied slippage exceeds the band (15c3-5 price control).

8. **Runaway losses (F25, §3).** *Mitigation:* intraday HWM + **daily-loss circuit
   breaker** (the 104 gap) — see §3.

9. **Clock / TZ / session boundary (F38).** *Mitigation:* all time math through
   `live.clock`; CI ban on naive datetimes in 105 paths; DST test.

10. **Duplicate orders on cron overlap (F29, F37).** *Mitigation:* run-lock +
    deterministic `client_order_id`. Idempotency is the single highest-leverage fix
    against "不靠谱的交易".

---

## 3. Fail-safe design spec

### 3.1 Default-deny (fail-closed on every uncertain input)
The pipeline's resting state is **no trade**. A buy is admitted only when *every*
required input is present, fresh, finite, and in-distribution. This already holds in
104 (preflight HARD-fails, gates fail-SAFE to BLOCK on non-finite, QP returns
zero-trade on infeasible, `data_cache` returns `None` on cold-start). 105 extends it:

- Missing/stale/partial bar ⇒ exclude that name this cycle (never substitute).
- Feed UNHEALTHY ⇒ `skip_buys` (exits still allowed).
- Unreconciled broker state ⇒ `FULL_HALT` (order-state integrity failure).
- Any preflight HARD failure ⇒ `PreflightFailed` → exit, **zero orders**.

### 3.2 Kill-switch STATE MACHINE + precedence (finding 7)
A single all-or-nothing `TRADING_OFF` flag is **wrong** for risk reduction: a breaker that
prevents liquidation *increases* risk. 105 therefore defines **distinct states** with explicit
exit semantics. States, from most to least dominant (a higher state subsumes the lower ones'
restrictions):

| State | New buys | Reduce-only / exits | Cancel open orders | Trigger(s) | Recovery authority |
|---|---|---|---|---|---|
| **`FULL_HALT`** | ✗ | ✗ (order-state/account-identity integrity emergency ONLY) | ✓ | unreconciled broker state (F30), wrong-account (F31), decision-loop dead / heartbeat-stale (F39) — i.e. order state or identity is untrustworthy. **NOT a drawdown breach.** | operator only (out-of-band marker, never auto-clears) |
| **`CANCEL_OPEN_ORDERS`** | ✗ | ✓ | ✓ | feed/broker disagreement, stale-but-recoverable | auto-recover when inputs healthy + operator ack |
| **`NO_NEW_RISK`** | ✗ | **✓ (exits ALLOWED)** | ✓ | **daily-loss breaker (§3.3)**, drawdown skip, **deep drawdown `dd < −20%` → `NO_NEW_RISK` + controlled flatten / reduce-only via the protective-sell path (§3.3 `≤ −L_flatten`)**, feed UNHEALTHY / data-health double-failure (F2), intra-session decay | auto-clear on the next clean session OR operator |
| **`NORMAL`** | ✓ (if all gates pass) | ✓ | ✓ | — | — |

Precedence: `FULL_HALT > CANCEL_OPEN_ORDERS > NO_NEW_RISK > NORMAL` (max-dominance, like the
gate lattice). **Both the daily-loss breaker AND a deep-drawdown breach (`dd < −20%`) map to
`NO_NEW_RISK` (+ controlled flatten / reduce-only), NOT `FULL_HALT`** — a drawdown is a
market-risk event, and losing money is exactly when you must be able to *exit*; halting exits
would TRAP risk. Only order-state/account-identity integrity failures (unreconciled broker
state, wrong account, a dead decision loop) reach `FULL_HALT`, where even exits are paused
until an operator reconciles.

**Exit price authority + staleness:** in `NO_NEW_RISK`/`CANCEL_OPEN_ORDERS`, exits may use the
**last-good price** up to a **max staleness of 1.5× bar interval** (the F1 bar-age bound); beyond
that, exits use a marketable-limit at the freshest available NBBO. **Broker/feed disagreement:**
if the broker position/price disagrees with our feed beyond a tolerance → escalate to
`CANCEL_OPEN_ORDERS` (do not place new exits on a disputed price) and reconcile (F30).

Underlying enforcement layers (defence-in-depth, independent, lower layers don't trust upper):
1. The **state marker** (durable file; `FULL_HALT`/`NO_NEW_RISK` recorded with reason+time).
2. **AgentBreaker caps** (P1 ≤25 orders/day, P2 ≤$5k/day) — hard, counts-only-on-success,
   no retry-loop; 105 adds **per-session/per-window sub-caps** + a message-rate throttle (FINRA 15-09).
3. **`skip_buys`** is the legacy name for the `NO_NEW_RISK` buy-side block (allows exits).
4. **Gate-stack `block`** (max-join over the lattice). 5. **Preflight** (run won't start armed).

### 3.3 P&L daily-loss circuit breaker (the 104 gap — `[105-BLOCKER]`)
104 has **no absolute daily-loss stop**: the drawdown breaker blocks *buys* on a
~20% peak-to-trough DD and allows sells; the weekly APY monitor only *alerts*.
105 adds a **hard intraday loss breaker** that maps to **`NO_NEW_RISK`, NOT `FULL_HALT`**
(finding 8 — exits must stay allowed when losing money):
- Track intraday realized+unrealized P&L vs session-open equity.
- `session_pnl_pct ≤ −L_halt` (**−5%**, the single consistent threshold across the FMEA,
  metrics, M2, M3) ⇒ enter **`NO_NEW_RISK`**: halt new buys, **exits/reduce-only ALLOWED**,
  alert, require operator review to return to `NORMAL`. Hysteresis to avoid flap.
- `≤ −L_flatten` (deeper than −5%, e.g. −8%, and the **deep-drawdown `dd < −20%`** breach)
  ⇒ controlled flatten / reduce-only via the existing protective-sell path (governor-throttled,
  §3.6) — still within `NO_NEW_RISK` (exits are the point). A drawdown breach NEVER escalates to
  `FULL_HALT`: trapping exits during a sell-off would *increase* risk.
- NaN/inf P&L ⇒ fail-SAFE to **`NO_NEW_RISK`** (mirror the DC-1/Issue-07 guards).
- (`FULL_HALT`, where even exits pause, is reserved for broker/account-integrity failures —
  unreconciled state / wrong account — never for a P&L loss.)

### 3.4 Shadow-first, intraday-trading-DISABLED-by-default
- 105 ships **flag-off and shadow-only**: it scores, sizes, and writes a run bundle +
  decision ledger but submits **no live orders**. (Matches how the intraday governor
  and intraday SellOnlyPipeline ship today — primitive present, unwired.)
- Promotion to live-armed requires: ≥N sessions shadow with **zero would-be
  duplicate/stale-price orders**, live-IC ≥ floor, and every `[105-BLOCKER]` closed.
- The arming flag is a single, audited config switch; default is **OFF**.

### 3.5 Pre-trade hard limits — SEC Rule 15c3-5 pattern (applied automatically, pre-trade)
Even as a retail account on Alpaca (not a broker-dealer), adopt the 15c3-5 *control
pattern* because it is the right shape for "prevent the bad trade before it leaves":
- **Credit/capital threshold (15c3-5(c)(1)(i)):** per-day notional cap (AgentBreaker
  $5k) + per-order notional cap + buying-power check pre-submit.
- **Erroneous-order price/size band (15c3-5(c)(1)(ii)):** reject if price deviates
  > X% from last NBBO (slippage band, F32) or qty/notional exceeds per-order max.
- **Duplicative-order control (15c3-5(c)(1)(ii)):** deterministic `client_order_id`
  (F29).
- **Automatic + pre-trade + under our exclusive control (15c3-5(d)):** all the above
  run in-process **before** `submit_order`, not as post-hoc review.
- **Regular review (15c3-5(e)):** a periodic (≥ quarterly) self-review of these
  controls, analogous to the rule's annual CEO certification, recorded in `doc/`.

### 3.6 Idempotency / dedup for cron (`[105-BLOCKER]`)
- **Run-lock:** `flock` on a lockfile keyed `trading_date+window`; a second launchd
  fire while one is running exits immediately (F37).
- **Order idempotency:** deterministic `client_order_id`; broker rejects the
  duplicate (F29). The two together make an overlapping/retried cycle a no-op rather
  than a double trade.
- **Ledger idempotency:** already `INSERT OR IGNORE` on `(run_id, scope, gate)`.

### 3.7 Recovery procedures
- **Stale/UNHEALTHY feed:** auto → `skip_buys`; operator → verify Alpaca status,
  refresh, confirm freshness, resume.
- **State marker set:** `FULL_HALT` (deadman / unreconciled / wrong-account) and
  `CANCEL_OPEN_ORDERS` require the operator to read the marker (it records why + when), fix
  root cause, and clear it (the system never auto-clears `FULL_HALT`). **`NO_NEW_RISK`**
  (the daily-loss breaker, drawdown skip, feed UNHEALTHY) keeps **exits allowed** and may
  auto-clear on the next clean session, or on operator review — it is NOT a full stop.
- **Unreconciled order (F30):** query broker order/position truth, reconcile
  `live_state`, then clear the `FULL_HALT` marker.
- **Corrupt cache (F8):** quarantine the parquet, re-fetch from Alpaca, bar-count
  assert, resume.
- **DST / clock incident:** `live.clock` is the single authority; re-run with correct
  `trading_date`.

### 3.8 Operator runbook invariants
No git operations on the live tree; no overwriting canonical prod data paths;
experiments in worktrees/separate files. (Carried from operating-model memory.)

---

## 4. Decision reliability (not just uptime)

Uptime ≠ correctness. A 100%-available system that places confident, wrong trades is
worse than a down one. These checks target the *decision*:

### 4.1 Gate-independence verification
The `GateRegistry` aggregate is **max-join** over a lattice — risk-monotone, so
adding a gate can never *increase* permissiveness. But independence of *verdicts* is
not independence of *inputs*: if all gates read one stale feed, the conjunction is a
single point of failure dressed as eight.
- **Action:** tag every gate with its input source(s). Build an input→gate matrix.
  Require that admitting a buy depends on ≥2 *independent* sources (e.g. price feed
  **and** model artifact **and** SPY macro), so no single stale input can pass the
  whole stack. CI test asserts the matrix has no single-source dominator for buys.

### 4.2 Placebo-testing the conjunction
- Feed the live gate stack **shuffled-label / random scores** and confirm the buy
  admission rate collapses to ~chance (the stack should reject noise). This is the
  decision-level analogue of the WF-gate placebo floor already used in research.
- Feed **known-bad inputs** (stale bar, NaN feature, negative price, forming bar) and
  assert each fails closed. Run as a CI "red-team" session replay.

### 4.3 Decision-ledger killed-winner audit
- The ledger (`decision_ledger.py`, `verdicts_for(as_of, scope)`) already turns "why
  was this run sell-only / why was X blocked?" into one SQL query.
- **Action:** nightly job joins ledger `block`/`halve` verdicts against realized
  forward returns of the *blocked* names → quantify **killed winners** (names a gate
  blocked that then rallied) vs **avoided losers**. A gate that mostly kills winners
  in a regime is regime-gated off (precedent: panel-exit mis-fires in BULL_CALM;
  buy-quality gates `disabled_in_regimes`).

### 4.4 Quantified false-positive trade rate (the headline target)
Define **FP-trade** = an order that, in shadow/replay, *should not* have fired
(stale-price, duplicate, forming-bar, wrong-account, slippage-band breach, or a name
the ledger+forward-return audit flags as a clear killed-loser-inverse).
- **Target SLO: FP-trade rate ≤ 0.5% of submitted orders, with ZERO tolerance for the
  two worst classes — duplicate orders and stale-price orders (both must be exactly
  0** in any rolling 20-session window before live-arming, and continuously after).
- Measured automatically every session from the run bundle + ledger; any nonzero
  duplicate or stale-price FP auto-sets **`FULL_HALT`** (a zero-tolerance correctness/integrity
  breach — the order path is untrustworthy) pending review.

---

## 5. Availability / reliability SLOs (real-account trading)

| Domain | SLO | Rationale / enforcement |
|---|---|---|
| **Duplicate orders** | **0** (hard) | F29/F37 idempotency + run-lock; any occurrence ⇒ `FULL_HALT` (integrity breach) |
| **Stale-price trades** | **0** (hard) | F1/F20 bar-age gate; fail-closed |
| **FP-trade rate** | **≤ 0.5%** of orders | §4.4; nonzero worst-class ⇒ halt |
| **Bar freshness at decision** | ≥ 99% of cycles use a bar ≤ 1.5× interval old | feed monitor; else degrade |
| **Decision-loop liveness** | heartbeat ≤ 180 s during RTH | `deadman_check` → `FULL_HALT` (liveness failure; F39) |
| **Order reconciliation** | 100% of submits reconciled to broker truth ≤ 60 s | F30 reconcile loop |
| **Daily-loss breaker** | trips to **`NO_NEW_RISK`** (exits allowed) within 1 cycle of **−5%** session P&L | §3.3 (consistent −5% across FMEA/metrics/M2/M3) |
| **Feed availability (decision-grade)** | ≥ 99.5% of RTH minutes | WS heartbeat + REST fallback |
| **Mean time to halt (MTTH)** | ≤ 1 cycle (≤ ~30 min) from a detectable bad state to no-trade | kill-switch hierarchy |
| **Recovery (MTTR)** | operator-paced; system stays fail-closed until explicit re-enable | the `FULL_HALT`/`CANCEL_OPEN_ORDERS` markers never auto-clear (`NO_NEW_RISK` may auto-clear on a clean session, §3.2) |
| **Controls self-review** | ≥ quarterly | 15c3-5(e)-style review recorded in `doc/` |

**Deliberate non-goal:** *trade availability* is **not** an SLO. The system is allowed
— indeed required — to refuse to trade. We optimize *correctness of action*, not
order count. A quiet, fail-closed session is a success, not an outage.

---

## 6. Implementation gating (summary of `[105-BLOCKER]`s)

Before 105 is live-armed, all must exist + be shadow-validated:
1. **Minute-level bar-age freshness gate** (F1/F3/F20).
2. **Deterministic `client_order_id` dedup** for equities (F29).
3. **flock run-lock** keyed trading_date+window (F37).
4. **All session math via `live.clock`** + CI ban on naive datetimes (F38).
5. **Intraday daily-loss circuit breaker → `NO_NEW_RISK`** (§3.3 — closes the 104 gap;
   exits allowed, threshold −5%, finding 7).
6. **Intraday `config_fingerprint`** + preflight feature-space match (F12/F14/F16).
7. **Marketable-limit + slippage band** instead of raw market orders (F32).
8. **Order reconcile loop** → UNRECONCILED ⇒ `FULL_HALT` (F30).
9. **Gate-independence matrix + placebo CI** + FP-trade SLO meter (§4).
10. **Kill-switch state machine** (`FULL_HALT`/`CANCEL_OPEN_ORDERS`/`NO_NEW_RISK`) with the
    daily-loss breaker mapped to `NO_NEW_RISK` (§3.2, finding 7).
11. **Broker-contract checks (M0.5)** — current `buying_power`/intraday-margin fields,
    rejection/deficit handling, leverage caps independent of broker max, fail-closed on
    Alpaca field migration (finding 8).

Everything else (feed health WS, live-IC decay monitor, per-window sub-caps,
governor wiring) is high-priority but can follow behind the flag, shadow-first.

---

## References
- **SEC Rule 15c3-5** (Market Access Rule), 17 CFR 240.15c3-5 — pre-trade financial
  controls: credit/capital thresholds (c)(1)(i); erroneous- and duplicative-order
  controls (c)(1)(ii); automatic, pre-trade, exclusive control (d); regular review /
  CEO certification (e). https://www.law.cornell.edu/cfr/text/17/240.15c3-5
- **FINRA Regulatory Notice 15-09** — effective practices for algorithmic-trading
  risk controls: quick-disable kill switch, message-rate throttles, controls to catch
  unintended results. https://www.finra.org/rules-guidance/notices/15-09
- **FINRA Market Access Rule guidance / 2024 oversight report** — pre-trade blocks,
  duplicative/erroneous-order controls, periodic testing.
  https://www.finra.org/rules-guidance/guidance/reports/2024-finra-annual-regulatory-oversight-report/market-access-rule
- **FMEA methodology** — RPN = Severity × Occurrence × Detection (MIL-STD-1629A
  lineage; AIAG-VDA 2019 FMEA Handbook, which also documents RPN's math limitations
  and the high-severity action override).

### Code anchors (104, read-only audit)
- Preflight: `renquant-pipeline/.../kernel/preflight.py`
- Gate stack: `kernel/pipeline/task_gates.py`, `kernel/gate_registry.py`,
  `kernel/pipeline/signal_direction.py`, `kernel/market_gates.py`
- DataFreshness: `kernel/pipeline/task_data_freshness.py`
- AgentBreaker: `renquant-orchestrator/.../agent_breaker.py`
- Decision ledger: `renquant-orchestrator/.../decision_ledger.py`
- Drawdown breaker: `renquant-pipeline/.../kernel/pipeline/task_drawdown.py`
- Broker (no equities dedup; market orders): `renquant-execution/.../alpaca_broker.py`
- Intraday data/cache: `renquant-pipeline/.../kernel/data.py` (`fetch_intraday_bars`),
  `kernel/intraday.py`, `renquant-base-data/.../loaders/data_cache.py`
- Clock authority: `RenQuant/live/clock.py`; deadman: `RenQuant/scripts/deadman_check.py`
- Intraday governor (unwired): `doc/memory/mid-term/intraday-governor.md`
- Prior 105 sketch: `doc/research/2026-06-12-intraday-trading-roadmap.md` (P0.1–P0.5)
