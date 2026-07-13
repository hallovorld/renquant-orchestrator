# Crypto Trend-Follow Portfolio — Fixed SMA50 + Systematic Scheduling (G2 v3)

- Status: DESIGN
- Date: 2026-07-13
- Author: claude (orchestrator control-plane session)
- Reviewers: operator (design decisions + capital sign-offs), codex (adversarial)
- Predecessor: `2026-07-10-crypto-trading-rfc.md` (operational infrastructure retained)
- Evidence: `doc/research/2026-07-13-crypto-trend-following-deep-research.md`

---

## 0. Context and pivots

The original crypto RFC (2026-07-10) designed a full XGB cross-sectional panel
scorer. Three signal-viability checks killed that scope:

1. **Alpha158 cross-sectional IC = −0.13** (t = −4.3, stable across 2y halves):
   real signal but concentrated in a single low-vol anomaly — not diverse alpha.
2. **Vol-rank portfolio Sharpe = 0.03**, MaxDD −65.6%: factor-isolated strategy
   doesn't beat BTC buy-and-hold.
3. **Single-ticker TA comparison** (13 strategies × 4 tradeable pairs): trend
   filters dominate, but the BEST strategy differs by pair. No single signal
   is universally optimal.

**Operator directives** (binding design inputs, not proposals):
- "可以只选sharpe最好的几个虚拟货币，然后用简单的单ticker模型来做交易分析"
- "制定crypto策略时应该更加注重三个月内的数据和走势，越近的数据越有意义"
- "每个月universe rotation太慢了，每周！"
- Live account: **20% allocation** (~$2.1k sleeve); paper: 50% (~$5.4k)
- "你要负责设计所有schedule的设计和落地"

---

## 1. Empirical evidence

Full research in `doc/research/2026-07-13-crypto-trend-following-deep-research.md`.

### 1.1 Walk-forward backtest [VERIFIED]

180d train / 90d test, rolling 90d steps, 25 bps round-trip fee, 1000-resample
bootstrap for confidence intervals. yfinance daily bars, max available history
(BTC: 11.8 years from 2014-09; ETH: 8.7 years from 2017-11).

| Pair | SMA50 Sharpe | 95% CI | P(Sharpe>0) | B&H Sharpe | MaxDD Strategy | MaxDD B&H |
|------|-------------|--------|-------------|------------|----------------|-----------|
| **BTC-USD** | **+1.36** | [+0.71, +1.85] | 100% | +0.90 | -59.6% | -83.4% |
| **ETH-USD** | **+0.60** | [+0.12, +1.47] | 98.8% | +0.05 | -59.2% | -94.0% |
| XRP-USD | -0.04 | [-0.36, +0.89] | 80.5% | +0.03 | -84.0% | — |

### 1.2 Statistical significance — honest null result [VERIFIED]

Paired t-test of daily excess returns (strategy − buy-and-hold):

| Pair | t-stat | p-value | Excess bps/day |
|------|--------|---------|----------------|
| BTC-USD | +0.12 | 0.91 | +0.4 |
| ETH-USD | -0.04 | 0.97 | -0.2 |
| XRP-USD | -1.64 | 0.10 | -13.1 |

**None are statistically significant at p < 0.05.** The Sharpe improvement
comes from reduced volatility (denominator), not higher returns (numerator).
Trend-following is a RISK MANAGEMENT tool, not an alpha strategy. Consistent
with Moskowitz-Ooi-Pedersen (2012), Liu-Tsyvinski (2021).

### 1.3 Drawdown reduction — the real value proposition

| Pair | MaxDD B&H | MaxDD SMA50 | Reduction |
|------|-----------|-------------|-----------|
| BTC-USD | -83.4% | -57.4% | 31% |
| ETH-USD | -94.0% | -59.7% | 36% |

On BTC (11 years), trend-following turns a -83% max drawdown into -57% while
maintaining similar total returns. On ETH, it turns -94% into -60%.

### 1.4 Adaptive vs fixed — adaptive loses [VERIFIED]

Walk-forward adaptive (pick best strategy on trailing 90d, apply next 90d):

| Pair | Adaptive | Fixed SMA50 | Verdict |
|------|----------|-------------|---------|
| BTC | +1.31 | **+1.53** | Fixed wins |
| ETH | +0.74 | +0.73 | Tie |
| XRP | -0.11 | +0.06 | Both fail |

**Adaptive selection does NOT beat fixed SMA50.** It adds selection noise
without improving risk-adjusted returns. The v2 design proposed per-pair
adaptive selection — this is **WITHDRAWN** based on empirical evidence.

### 1.5 Broad universe — 20 pairs, full history [VERIFIED]

| Tier | Pairs | Full-history SMA50 Sharpe |
|------|-------|---------------------------|
| **Core** | BTC (+1.53), ETH (+0.85) | Strong trend, long history |
| **Strong** | SOL (+1.72), AVAX (+0.83), ADA (+0.66), NEAR (+0.64) | Good but shorter history |
| **Marginal** | DOGE (+0.47), MATIC (+0.52), LINK, LTC, AAVE | Positive but low conviction |
| **Excluded** | XRP (+0.05), UNI (-0.31), FIL (-0.47), ARB (-0.32) | Trend-following doesn't work |

17/20 (85%) pairs have positive SMA50 Sharpe. Mean +0.39, median +0.38.

### 1.6 Transaction cost sensitivity [VERIFIED]

| Pair | 0 bps | 25 bps | 50 bps | 100 bps |
|------|-------|--------|--------|---------|
| BTC-USD | +1.53 | +1.36 | +1.20 | +0.90 |
| ETH-USD | +0.73 | +0.60 | +0.48 | +0.27 |

BTC robust at 100 bps/side. ETH fragile above 50 bps.

### 1.7 Regime analysis [VERIFIED]

All strategies fail in bear regime (BTC < SMA200). Bull Sharpe +2.15 (BTC),
Bear Sharpe -0.55. The value is reducing -83% drawdowns to -57%, not avoiding
losses entirely.

### 1.8 Critical correction — 2-year window was misleading

| Pair | 2y Sharpe | Full-history Sharpe | Direction |
|------|-----------|---------------------|-----------|
| UNI | +1.53 | -0.31 | **REVERSED** |
| XRP | +0.97 | +0.05 | **Near-zero** |
| BTC | +0.87 | +1.53 | **IMPROVED** |

The initial 2-year backtest overstated UNI and XRP. Only BTC and ETH are
reliable trend-following candidates on full history.

### 1.9 Limitations

- **Data source**: yfinance only, no cross-check with Alpaca bars.
- **Survivorship bias**: 3/20 currently-listed pairs have negative Sharpe;
  delisted/failed pairs would be worse. The 85% positive rate is an upper bound.
- **No excess return significance**: the strategy's value is drawdown reduction,
  not alpha. If the operator wants excess return, trend-following is the wrong tool.
- **Bear-market underperformance**: the strategy still loses in bear markets
  (just less than buy-and-hold).

### 1.10 Academic support

- **Moskowitz, Ooi, Pedersen (2012)**: canonical time-series momentum paper
- **Liu and Tsyvinski (2021)**: crypto momentum at 1–4 week horizons, ~3% excess weekly (gross)
- **Reijnders (2020)**: crypto trend-following Sharpe 0.5–1.5, 255% annualized (walk-forward)
- **Tan and Pedersen (2026)**: adaptive portfolio construction for crypto trend-following

---

## 2. Signal design — fixed SMA50 trend filter

### 2.1 Signal rule

```
signal[pair] = 1 (LONG)  if  close[pair] > SMA50[pair]
               0 (CASH)  otherwise
```

One signal, all pairs, no parameters to tune or select. SMA50 = 50-day simple
moving average of daily closing price.

### 2.2 Why SMA50, why fixed

1. **Best on the primary pair**: BTC walk-forward Sharpe +1.53 (full history),
   beating all alternatives including adaptive selection (+1.31).
2. **Robust to costs**: Sharpe +0.90 even at 100 bps/side (§1.6).
3. **Zero overfitting risk**: no trainable parameters, no selection procedure.
4. **Adaptive selection disproven**: walk-forward test shows adaptive does NOT
   beat fixed SMA50 (§1.4). Strategy selection on 90-day windows adds noise.
5. **Academically grounded**: SMA/EMA trend filters are the standard in
   Moskowitz et al. (2012) and Reijnders (2020).

### 2.3 Implementation — `crypto_trend_signal.py` (renquant-base-data)

```python
@dataclass(frozen=True)
class TrendSignalConfig:
    sma_period: int = 50
    min_bars: int = 60            # 50 + warmup
    crypto_ohlcv_dir: Path | None = None

@dataclass(frozen=True)
class PairSignal:
    pair: str
    signal: int                   # 1 = long, 0 = cash
    close: float
    sma50: float                  # SMA50 value for audit
    bar_date: date

@dataclass(frozen=True)
class SignalSnapshot:
    as_of_date: date
    signals: list[PairSignal]
    universe_hash: str
    n_long: int
    n_cash: int
    digest: str                   # sha256 for session scheduler gate

def compute_signals(
    pairs: list[str],
    cfg: TrendSignalConfig,
    as_of: date | None = None,
) -> SignalSnapshot:
    """Compute fixed SMA50 trend signal for each pair."""
```

The `digest` field maps directly to `crypto_session.py`'s
`SignalSnapshot.digest()` for gate #7/#10 verification.

---

## 3. Universe selection — weekly 90d Sharpe rotation

### 3.1 Selection rule

**Every Sunday 00:00 UTC** (weekly, not monthly — operator directive),
re-rank the eligible pairs from the watchlist:

```
sharpe_90d[pair] = mean(ret[pair, last 90d]) / std(ret[pair, last 90d]) × √365
```

Selection:
1. Pair must have ≥ 90 bars in the lookback window.
2. **Pair must NOT be in the exclusion list** (XRP, UNI, FIL, ARB — trend-
   following empirically fails on these pairs per §1.5).
3. **90d Sharpe > 0** (no negative-Sharpe pairs).
4. **Top-N by Sharpe** (N = `universe_top_n`, default 5).

### 3.2 Why weekly

- Monthly is too slow for crypto regime changes (operator directive).
- Daily would cause excessive universe churn and sizing instability.
- Weekly balances responsiveness with stability: a pair that crashes hard
  exits the universe within 7 days, not 30.

### 3.3 Universe transition rules

When the universe changes at the weekly rotation:

- **New entrant**: if signal = LONG, open position at next available tick.
- **Dropped pair with position**: if signal was LONG, EXIT at next tick
  (don't hold positions in pairs outside the active universe).
- **Dropped pair without position**: no action needed.
- **Retained pair**: keep existing position/signal/strategy assignment.

---

## 4. Portfolio construction

### 4.1 Capital allocation (operator-specified)

| Environment | Allocation | Amount |
|-------------|-----------|--------|
| Live account | 20% of account value | ~$2,140 |
| Paper account | 50% of paper value | ~$5,350 |

The sleeve budget is a **hard cap** enforced at two layers:
1. Pipeline sizing: `available = min(sleeve_budget, crypto_buying_power)`
2. Orchestrator preflight: assert `sum(open_crypto_positions + pending_crypto_buys) ≤ sleeve_budget`

### 4.2 Position sizing

```
For each pair in active universe:
    if signal[pair] == LONG:
        target_weight[pair] = 1 / n_active
        target_notional[pair] = sleeve_budget × target_weight[pair]
    else:
        target_weight[pair] = 0

Constraints:
    max_single_position = 0.40 × sleeve_budget        # 40% cap
    min_order_notional  = max(10.0, pair.min_order_usd) # Alpaca minimums
```

**Equal-weight rationale**: with ≤5 uncorrelated trend-following positions,
mean-variance optimization adds estimation error without meaningful
diversification benefit. The trend filter itself is the primary risk tool.

### 4.3 Rebalancing triggers

| Trigger | Frequency | Action |
|---------|-----------|--------|
| Signal flip (LONG↔CASH) | Daily check | Open/close position |
| Universe rotation | Weekly (Sunday) | Add/remove pairs |
| Drift > 15% from target weight | Daily check | Resize toward target |
| Sleeve budget change | On config update | Resize all positions |

**No intra-day rebalancing**: the 15-min tick loop checks risk rails only;
sizing decisions are daily at the signal refresh.

### 4.4 Cash management

- When a pair's signal flips to CASH, that allocation goes to CASH (not
  redistributed). This avoids concentration spikes.
- When a NEW signal flips to LONG, all positions are resized to equal weight.
- When ALL signals are CASH, 100% of the sleeve is in cash — this is a
  legitimate "risk-off" state, not a bug.

---

## 5. System architecture — complete module map

```
┌────────────────────────────────────────────────────────────────────┐
│                    SCHEDULING LAYER (§6)                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐ │
│  │ Weekly cron   │  │ Daily cron   │  │ 24/7 session tick loop   │ │
│  │ (universe     │  │ (signal +    │  │ (risk rails + order      │ │
│  │  rotation)    │  │  sizing)     │  │  execution + stops)      │ │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────────┘ │
└─────────┼─────────────────┼──────────────────────┼────────────────┘
          │                 │                      │
┌─────────▼─────────────────▼──────────────────────▼────────────────┐
│                    SIGNAL + PORTFOLIO LAYER                        │
│                                                                    │
│  ┌────────────────────────┐  ┌─────────────────────────────────┐  │
│  │ crypto_trend_signal.py │  │ crypto_portfolio.py             │  │
│  │ (base-data)            │  │ (pipeline)                      │  │
│  │                        │  │                                 │  │
│  │ • Universe selector    │  │ • Position sizer (equal-weight) │  │
│  │ • Strategy candidates  │  │ • Rebalance trigger engine      │  │
│  │ • Per-pair selection    │  │ • Drawdown circuit breaker (R1) │  │
│  │ • Signal snapshot      │  │ • Per-pair stop manager (R2)    │  │
│  │ • Digest computation   │  │ • Position cap enforcer (R3)    │  │
│  └────────────┬───────────┘  └──────────┬──────────────────────┘  │
│               │                         │                          │
│               │    SignalSnapshot        │    PortfolioAction[]     │
│               │                         │                          │
│  ┌────────────▼─────────────────────────▼──────────────────────┐  │
│  │ crypto_session.py (orchestrator) — 11-gate scheduler        │  │
│  │ EXISTING: gates, watermark, digest, fingerprint, stops      │  │
│  └────────────────────────────┬────────────────────────────────┘  │
└───────────────────────────────┼────────────────────────────────────┘
                                │ OrderIntent[]
┌───────────────────────────────▼────────────────────────────────────┐
│                    EXECUTION LAYER                                  │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ Alpaca crypto adapter (execution repo)                       │  │
│  │ • GTC/IOC TIF policy          • Fee model (taker/maker bps)  │  │
│  │ • Increment enforcement       • Stop-limit lifecycle         │  │
│  │ • Reconcile-before-emit       • No-short assertion           │  │
│  │ • AccountCashLedger (shared)  • Asset-class classifier       │  │
│  └──────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────┘
                                │
┌───────────────────────────────▼────────────────────────────────────┐
│                    DATA LAYER                                      │
│  ┌──────────────────┐  ┌────────────────┐  ┌───────────────────┐  │
│  │ CryptoLocalStore  │  │ ALWAYS_OPEN    │  │ pair_slug()       │  │
│  │ (base-data)       │  │ calendar       │  │ (common)          │  │
│  │ MERGED            │  │ (common)       │  │ MERGED            │  │
│  │                   │  │ MERGED         │  │                   │  │
│  └──────────────────┘  └────────────────┘  └───────────────────┘  │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ asset_class.py P1-P7 (pipeline) — MERGED, 39/39 tests       │  │
│  └──────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────┘
```

---

## 6. Scheduling — complete specification

This section defines EVERY scheduled process, its cadence, trigger, inputs,
outputs, error handling, and deployment mechanism. I own the design AND
implementation of all scheduling.

### 6.1 Schedule overview

| # | Process | Cadence | Trigger | When (UTC) | Deployed as |
|---|---------|---------|---------|------------|-------------|
| S1 | Data ingestion | Daily | cron | 00:05 UTC | launchd plist |
| S2 | Universe rotation | Weekly | cron | Sunday 00:10 UTC | launchd plist |
| S3 | Signal computation | Daily | cron (after S1) | 00:15 UTC | launchd plist |
| S4 | Portfolio sizing | Daily | cron (after S3) | 00:20 UTC | launchd plist |
| S5 | Session tick loop | Continuous | launchd KeepAlive | every 900s | launchd daemon |
| S6 | Reconciliation | Every tick | embedded in S5 | — | part of S5 |
| S7 | Stop maintenance | Every tick | embedded in S5 | — | part of S5 |
| S8 | Liveness monitor | Continuous | watchdog | alert if no tick > 60 min | launchd daemon |
| S9 | Performance report | Weekly | cron | Sunday 01:00 UTC | launchd plist |

### 6.2 S1 — Daily data ingestion

**Purpose**: Fetch the latest daily bar for all watchlist pairs.

```
Trigger:    00:05 UTC daily (launchd StartCalendarInterval)
Input:      watchlist (20 pairs from config)
Process:    ingest_crypto_bars(watchlist, timeframe="1d", start=yesterday, end=today)
Output:     updated parquet files in crypto_ohlcv/{SLUG}/1d.parquet
Duration:   ~30s (API call + write)
Error:      retry 3× with 60s backoff; on persistent failure, write
            data/crypto/ingestion_failure.json (S3 will detect stale data)
Depends on: Alpaca CryptoHistoricalDataClient (v1beta3), ALPACA_API_KEY env
```

**Implementation**: CLI entry point `renquant-orch crypto ingest` calling
existing `ingest_crypto_bars()` from base-data (MERGED).

### 6.3 S2 — Weekly universe rotation

**Purpose**: Re-rank pairs by trailing 90d Sharpe, select top-N, assign
per-pair strategy.

```
Trigger:    Sunday 00:10 UTC (launchd, weekly)
Input:      CryptoLocalStore bars, prior strategy assignments
Process:
  1. For each pair in watchlist:
     - Compute 90d daily returns
     - Compute 90d Sharpe (annualized √365)
  2. Filter: Sharpe > 0, ≥ 90 bars
  3. Exclude empirically-failed pairs (XRP, UNI, FIL, ARB — §1.5)
  4. Sort descending, select top-N (default 5)
  5. Write universe_selection.json
  6. If universe changed: flag positions in dropped pairs for exit at S4
Output:     universe_selection.json
Duration:   ~10s (pure computation on local data)
Error:      if <2 pairs qualify, use last week's universe + alert operator
```

### 6.4 S3 — Daily signal computation

**Purpose**: Compute today's SMA50 trend signal for each pair in the active universe.

```
Trigger:    00:15 UTC daily (after S1 completes)
Input:      universe_selection.json, bars
Process:
  1. Load active universe
  2. For each pair: compute SMA50, signal = 1 if close > SMA50 else 0
  3. Produce SignalSnapshot with digest
  4. Verify bar watermark (latest bar must be yesterday's close)
  5. Write signal_snapshot.json (consumed by S4 and S5)
Output:     signal_snapshot.json (includes digest for session gate #7/#10)
Duration:   ~2s
Error:      if bars stale (>26h), set signal=0 for that pair; if ALL stale,
            write empty snapshot (S5 will block entries via gate #8)
Depends on: S1 completion (bars freshness)
```

### 6.5 S4 — Portfolio sizing

**Purpose**: Translate signals into target positions and generate order intents.

```
Trigger:    00:20 UTC daily (after S3)
Input:      signal_snapshot.json, current positions (from broker), config
Process:
  1. Load current positions from Alpaca via reconcile-before-emit
  2. For each pair in universe:
     a. If signal=LONG and no position: compute target_notional, generate BUY intent
     b. If signal=CASH and has position: generate SELL intent
     c. If signal=LONG and has position: check drift, generate RESIZE if needed
  3. For pairs DROPPED from universe (S2): generate SELL intent
  4. Apply constraints: position cap (40%), min order ($10), sleeve budget
  5. Check risk gates: drawdown halt (R1), per-pair stop (R2)
  6. Write portfolio_actions.json (consumed by S5 for execution)
Output:     portfolio_actions.json
Duration:   ~5s (includes broker API call for positions)
Error:      if broker unreachable, skip sizing (S5 won't execute stale actions)
Depends on: S3 completion, broker API availability
```

### 6.6 S5 — Session tick loop (24/7)

**Purpose**: Execute portfolio actions, manage stops, enforce risk rails.

```
Trigger:    launchd KeepAlive daemon, ticks every 900s (15 min)
Process per tick:
  1. Reconcile-before-emit: fetch open orders + positions from broker
  2. 11-gate preflight (crypto_session.py):
     - Gates #1-3: enabled + env flag + kill switch
     - Gate #4: mode check (shadow/paper/live)
     - Gate #5: live authorization marker
     - Gate #6: quiet interval elapsed
     - Gate #7: signal snapshot present
     - Gate #8: watermark valid (not stale)
     - Gate #9: fingerprints valid
     - Gate #10: digest verified
     - Gate #11: stop coverage ready
  3. If gates pass AND portfolio_actions.json has pending actions:
     - Submit orders via Alpaca crypto adapter
     - Reserve cash via AccountCashLedger
     - Place/update protective stop-limits for filled positions
  4. Risk rails (evaluated EVERY tick, even if no actions):
     - R1: sleeve drawdown check (halt entries if MV < HWM × 0.85)
     - R2: per-pair stop check (software stop, supplement to broker stop)
     - R3: position cap check (alert if >40%)
  5. Write tick_record.jsonl (append-only audit trail)
Output:     tick_record.jsonl, order fills, stop updates
Duration:   ~3s per tick
Error:      broker timeout → skip tick, log, increment miss counter;
            3 consecutive misses → alert on renquant-crypto ntfy topic
Kill:       SIGTERM → cancel non-protective orders, write final tick record
```

### 6.7 S8 — Liveness monitor

**Purpose**: Alert if the tick loop stops heartbeating.

```
Trigger:    launchd KeepAlive daemon, checks every 300s
Process:    read last tick timestamp from tick_record.jsonl;
            if now - last_tick > 3600s → alert renquant-crypto ntfy topic
Output:     ntfy alert
```

### 6.8 S9 — Weekly performance report

**Purpose**: Generate portfolio performance summary for operator review.

```
Trigger:    Sunday 01:00 UTC (after S2 rotation)
Process:
  1. Compute sleeve P&L (realized + unrealized) for the past week
  2. Compute net-of-fee returns and Sharpe (trailing 90d)
  3. Compare vs BTC buy-and-hold over same period
  4. Report: universe composition, strategy assignments, signals,
     positions, P&L breakdown, risk rail status, trade count
Output:     reports/crypto_weekly_<date>.json
```

### 6.9 Scheduling dependencies (DAG)

```
         S1 (ingest, 00:05)
              │
    ┌─────────┤
    │         │
    │    S2 (universe, Sun 00:10)
    │         │
    └────┬────┘
         │
    S3 (signal, 00:15) ← no adaptive selection; fixed SMA50
         │
    S4 (sizing, 00:20) ← equal-weight, no optimization
         │
    S5 (tick loop, continuous) ←── S8 (liveness watchdog)
         │
    S9 (report, Sun 01:00)
```

All dependencies are enforced by **file-based signaling**: each process
writes a completion marker (`<process>_done_<date>.json`) that the next
process checks. If the upstream marker is missing or stale, the downstream
process operates in degraded mode (uses last valid output) and alerts.

### 6.10 Deployment — launchd plists

All schedules are deployed as launchd plists in `~/Library/LaunchAgents/`.

```
com.renquant.crypto.ingest.plist        → S1 (daily 00:05 UTC)
com.renquant.crypto.universe.plist      → S2 (Sunday 00:10 UTC)
com.renquant.crypto.signal.plist        → S3 (daily 00:15 UTC)
com.renquant.crypto.sizing.plist        → S4 (daily 00:20 UTC)
com.renquant.crypto.session.plist       → S5 (KeepAlive daemon)
com.renquant.crypto.liveness.plist      → S8 (KeepAlive watchdog)
com.renquant.crypto.report.plist        → S9 (Sunday 01:00 UTC)
```

**Deployment procedure** (machine-landing = ask-first per operating rules):
1. Generate plists from templates in `ops/crypto/*.plist.template`
2. Operator approves the batch
3. `launchctl load` each plist
4. Verify with `launchctl list | grep renquant.crypto`

**Mac sleep handling**: launchd does NOT wake a sleeping Mac. Policy:
- S5 (tick loop) tolerates arbitrary gaps via reconcile-before-emit
- Broker-resident GTC stop-limits protect positions while asleep
- S1-S4 catch up on wake (process stale markers, re-run if needed)
- Keeping the node awake (pmset/caffeinate) is a separate machine-landing
  action — the system works without it, awake just improves latency

---

## 7. Risk management

### 7.1 Risk hierarchy (most-restrictive-wins)

All risk gates bind ENTRIES only — exits always allowed (RFC §5.4).

| # | Rule | Threshold | Action | Check frequency |
|---|------|-----------|--------|----------------|
| R1 | Sleeve drawdown | MV < HWM × 0.85 | Halt all entries (sticky, manual reset) | Every tick (S5) |
| R2 | Per-pair stop | Price < entry × 0.88 | Exit pair, cooldown 14 days | Every tick (S5) |
| R3 | Position cap | Weight > 40% of sleeve | Block increases, alert | Every tick (S5) |
| R4 | Freshness | Bar > 26h stale | Block entry for that pair | S3 + every tick |
| R5 | Hold clock | Position < 24h | No exit (except R2 stop) | S4 |
| R6 | Kill switch | File exists | Halt all entries | Every tick (S5) |
| R7 | Env flag | Not set | Halt all entries | Every tick (S5) |
| R8 | Quiet interval | 00:00-00:15 UTC | No entries | Every tick (S5) |

### 7.2 Broker-resident protective stops

Every filled position gets a GTC stop-limit sell order at the broker:

```
stop_price  = entry_price × (1 - stop_pct)        # 12% below entry
limit_price = stop_price × (1 - limit_band_bps/1e4) # 200 bps below stop
```

Lifecycle: place on fill → cancel/replace on resize → cancel on exit.
Missing stop = gate #11 block (no new entries until resolved).

---

## 8. Configuration

```json
{
  "crypto_trading": {
    "enabled": false,
    "mode": "shadow",
    "asset_class": "crypto",
    "sleeve": {
      "budget_usd_live": 2140,
      "budget_usd_paper": 5350,
      "max_drawdown_pct": 0.15,
      "max_position_pct": 0.40
    },
    "signal": {
      "strategy": "SMA50",
      "sma_period": 50,
      "min_bars": 60
    },
    "universe": {
      "watchlist": [
        "BTC-USD", "ETH-USD", "SOL-USD", "AVAX-USD", "ADA-USD",
        "NEAR-USD", "DOGE-USD", "MATIC-USD", "LINK-USD", "LTC-USD",
        "AAVE-USD", "DOT-USD", "ATOM-USD", "BCH-USD", "APT-USD", "OP-USD"
      ],
      "excluded_empirically": ["XRP-USD", "UNI-USD", "FIL-USD", "ARB-USD"],
      "top_n": 5,
      "rotation_cadence": "weekly",
      "rotation_day": "sunday",
      "min_sharpe_90d": 0.0
    },
    "risk": {
      "stop_pct": 0.12,
      "stop_limit_band_bps": 200,
      "stop_cooldown_days": 14,
      "drift_rebalance_pct": 0.15
    },
    "scheduling": {
      "tick_cadence_seconds": 900,
      "ingest_utc_hour": 0, "ingest_utc_minute": 5,
      "signal_utc_hour": 0, "signal_utc_minute": 15,
      "sizing_utc_hour": 0, "sizing_utc_minute": 20,
      "universe_day": "sunday", "universe_utc_hour": 0,
      "liveness_max_gap_seconds": 3600
    },
    "execution": {
      "taker_fee_bps": 25,
      "maker_fee_bps": 15
    }
  }
}
```

---

## 9. Deliverables

| # | Repo | What | Size | Status |
|---|------|------|------|--------|
| T-1 | base-data | `crypto_trend_signal.py`: fixed SMA50 trend filter + signal snapshot + digest | S | NEW |
| T-2 | pipeline | `crypto_portfolio.py`: equal-weight sizer + rebalance triggers + risk gates R1-R3 + drawdown breaker | S | NEW (reuses `portfolio.update_drawdown_circuit_breaker`) |
| T-3 | orchestrator | `crypto_scheduling.py`: S1-S4 + S8-S9 coordination + file-based DAG + completion markers | M | NEW |
| T-4 | orchestrator | `ops/crypto/*.plist.template`: 7 launchd plist templates for all scheduled processes | S | NEW |
| T-5 | orchestrator | Wire signal→portfolio→session: adapt `crypto_session.py` to consume new SignalSnapshot format | S | ADAPT existing |
| T-6 | execution | Crypto order adapter: GTC/IOC TIF, increment, fees, reconciliation (RFC D-C4 subset) | M | Designed in RFC |
| T-7 | execution | GTC stop-limit protective path + lifecycle (RFC D-C5 subset) | M | Designed in RFC |
| T-8 | orchestrator | CLI commands: `crypto ingest`, `crypto universe`, `crypto signal`, `crypto status`, `crypto report` | S | NEW |

**Already merged (reused directly):**
CryptoLocalStore, ingest_crypto_bars (base-data) · asset_class P1-P7, 39 tests (pipeline) · crypto_session 11-gate scheduler (orchestrator) · ALWAYS_OPEN calendar, pair_slug (common) · drawdown circuit breaker (pipeline portfolio.py) · crypto order validation (execution crypto.py) · stage-0 battery (orchestrator)

---

## 10. Staged rollout

| Stage | Duration | What | Gate |
|-------|----------|------|------|
| **0** | ~3 days | Ingest bars, verify signal computation, operator enables crypto | Bars ingested, signal matches yfinance, crypto_status=ACTIVE |
| **1** | ≥ 7 days | Shadow: all S1-S9 running, no orders | 7 clean days incl. 1 weekend, zero gate failures |
| **2** | ≥ 14 days | Paper: orders on paper account ($5.4k sleeve) | 14 days, zero Tier-1 defects |
| **3** | ≥ 30 days | Live canary: $500 on live account | DD < 15%, fees within estimates, operator sign-off |
| **4** | ongoing | Full live sleeve: $2.1k (20% account) | Operator sign-off, monthly BTC-baseline review |

---

## 11. Acceptance criteria (G2)

1. **AC-1**: Shadow S1-S9 run ≥ 7 consecutive clean days with weekly universe
   rotation, daily signal computation, and portfolio sizing.
2. **AC-2**: Paper orders execute on Alpaca for ≥ 14 days with correct TIF,
   stops, fees, and reconciliation.
3. **AC-3**: Live canary ($500) runs ≥ 30 days, max DD < 15%.
4. **AC-4**: Full sleeve net-of-fee performance reviewed monthly against BTC
   buy-and-hold; persistent 3-month underperformance = wind-down trigger.

---

## 12. Non-goals

- No XGB/PatchTST/neural model — signal is mechanical trend filter.
- No cross-sectional scoring — each pair independent.
- No perpetuals/futures/margin/shorting/leverage.
- No intraday re-scoring — daily signal + intraday risk rails only.
- No equity strategy behavior changes (asset-class-keyed bypasses only).
- No cash-drag lane coupling (Governor/D6/shadow-AB untouched).
