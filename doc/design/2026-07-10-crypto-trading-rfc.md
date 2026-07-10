# Crypto Trading Capability RFC — Alpaca Spot, 24/7 Loop, Sleeve (GOAL-2)

- Status: DRAFT — design-first; this RFC merges before any implementation PR
- Date: 2026-07-10
- Author: claude (orchestrator control-plane session)
- Reviewers: codex (adversarial), operator (capital sign-offs only)
- Scope: NEW capability — Alpaca spot crypto trading for the RenQuant multi-repo
  system, as an isolated sleeve. Independent of the cash-drag lane; this RFC and
  its implementation PRs touch NOTHING in the Deployment Governor / D6 protocol /
  shadow-AB lanes.

---

## 1. Goal + operator decisions

**Goal.** Enable crypto trading on Alpaca for the 104/105 system family. The
CAPABILITY is the mandate; the model is designed together with the pipeline (not
capability-first). The end state is a small, isolated, 24/7 crypto sleeve driven
by a WF-gated cross-sectional model, with the same governance discipline as 104
(3-tier gate, placebos, decision ledger, staged canary).

**Operator decisions (2026-07-10) — fixed inputs, not open questions:**

1. **Capital**: a sleeve carved from the existing ~$10.7k account. Design for
   **$1–2k**; the exact number is set at canary sign-off.
2. **Direct to model**: pipeline + model designed together — no capability-only
   phase that ships dark.
3. **Universe**: Alpaca's full crypto pair list (~20 USD pairs) `[GUESS: exact
   count verified at Stage 0 via `TradingClient.get_all_assets(GetAssetsRequest(
   asset_class=AssetClass.CRYPTO))` — SDK-verified surface, trading/requests.py:127-139]`.
4. **Operation**: 24/7 intraday loop (105-style continuous cadence, weekends
   included). This Mac is the only execution node.

**Account prerequisite (operator action).** The Alpaca account must have the
crypto agreement enabled (dashboard action). Verification is mechanical: the SDK
`TradeAccount.crypto_status` field ([VERIFIED] alpaca-py 0.43.4,
`alpaca/trading/models.py:485,528`) must report ACTIVE on both paper and live
before Stage 0 completes. No implementation PR may assume this is done.

**Model-family choice (proposal).** A NEW model — an XGB cross-sectional panel
scorer in the existing `renquant_model_gbdt` factory harness — rather than
retargeting PatchTST. Rationale in §4. This satisfies "104/105 model family or a
new model": same factory, same governance, new asset class.

---

## 2. Asset-class abstraction audit (verified gap table)

Audit of the live checkouts, 2026-07-10, read-only. Every row cites file:line in
the named repo. "Size": XS (<½ day), S (~1 day), M (2–4 days), L (≥1 week).

### 2.1 renquant-execution

| # | Gap | Evidence (file:line) | Why it breaks for crypto | Size |
|---|---|---|---|---|
| E1 | All submit paths hardcode `TimeInForce.DAY` | `alpaca_broker.py:249-254` (place_order), `:332-337` (place_notional_order), `alpaca_broker_port.py:116` + docstring `:47` ("no order carries overnight") | Crypto accepts **GTC/IOC only** ([VERIFIED] SDK `trading/enums.py:246,249`; crypto order-type matrix `trading/enums.py:129`); and 24/7 orders must rest overnight | M |
| E2 | Fractional validation pins TIF=DAY | `broker.py:54` (`FRACTIONAL_TIME_IN_FORCE="day"`), `:132-137` (`validate_fractional_order` rejects non-DAY) | Rejects the only TIFs crypto supports — the central assumption break | M |
| E3 | Reconciliation filters `asset_class=US_EQUITY` | `alpaca_broker.py:145` (get_filled_orders), `:161` (get_open_orders) | Crypto fills/open orders become **silently invisible** to reconcile-before-emit — a correctness hazard, not an inconvenience | S |
| E4 | No fee/commission model anywhere | `paper_broker.py:99-106` (zero-fee fills), `order_math.py:66-78` (sizing ignores fees), `order_state_machine.py:830-843` (`reserved_cash = qty*price`) | Crypto has taker/maker bps fees (~25/15 bps tier-0 `[GUESS: verify schedule at Stage 0]`); cash caps, reservations and paper P&L all overstate | M |
| E5 | Fractionable-lookup fail-closed dance | `alpaca_broker.py:390-404` (`_lookup_fractionable` via `get_asset`), `:236-246`, `:318-330` | Crypto is natively fractional; equity fractionable gate could false-reject and is semantically wrong for pairs | S |
| E6 | Whole-share snap + int sizing | `alpaca_broker.py:194-199`, `order_math.py:77-78` (`int(cash//price)`) | No whole-share concept for crypto; must size in `min_trade_increment` grid ([VERIFIED] `Asset.min_order_size/min_trade_increment/price_increment`, `trading/models.py:66-68`) | S |
| E7 | Equity sub-penny price rounding | `alpaca_broker_port.py:92` (`round(price, 2 or 4)`) | Crypto uses per-asset `price_increment`, not the equity 2/4-dp rule | S |
| E8 | Broker-side stops require whole shares; no stop-limit path exists | `alpaca_broker.py:431-433,444-455` (`place_stop_order` GTC but whole-share-only); `StopLimitOrderRequest` never constructed (only listed at `broker.py:53`) | A fractional crypto position can never get a protective broker stop through the current path; crypto needs GTC **stop_limit** in native fractional qty ([VERIFIED] SDK class `trading/requests.py:460`; crypto supports market/limit/stop_limit per `trading/enums.py:129`) | M |
| E9 | DAY-expiry end-of-session sweep | `order_state_machine.py:144-154,1065-1075` (`resolve_day_expiry`), `live_commit.py:90-93` ("no GTC" classifier) | Would wrongly terminate resting GTC crypto orders at an equity close that doesn't exist | M |
| E10 | Equity market-hours gates | `alpaca_broker.py:469-470` (`get_clock().is_open`), `preopen_cancel_gate.py:83,101,587-588` (NYSE calendar) | False "market closed" nights/weekends for a 24/7 asset | S |
| E11 | Long-only by construction (compatible) | `order_state_machine.py:79-81` (`_VALID_SIDES`), `broker.py:258` | Crypto-compatible — no short path exists; add an explicit crypto no-short assertion so it stays structural | XS |
| E12 | Broker-tag state isolation (REUSE seam) | `readonly_broker.py:19-24,49-77`, `factory.py:13-50`; `OrderStateBook(account, trading_day)` + `compute_parent_intent_id` hashing account, `order_state_machine.py:177-200,486-488` | Crypto sleeve = a new broker tag (`alpaca_crypto`) — the isolation mechanism already exists | XS |

### 2.2 renquant-pipeline

| # | Gap | Evidence (file:line) | Why it breaks for crypto | Size |
|---|---|---|---|---|
| P1 | NYSE calendar hardwired into freshness | `kernel/data.py:21-31,34-57,240-249`; `kernel/typed_past/typed_data_freshness.py:32-83` (hard-fail vs last NYSE session) | Weekend crypto bars judged stale/not refreshed; freshness clock is the wrong clock | L |
| P2 | Hold/streak clocks advance on NYSE days only | `kernel/exits.py:52-105,737,752`; `kernel/pipeline/soft_exit_guards.py:15,42,107` | Positions don't age over weekends → min-hold/max-hold/horizon gates mis-fire | M |
| P3 | T+1 settlement queue on NYSE days | `kernel/execution/t2_settlement.py:14-62,92` | Crypto settles instantly, 24/7 | S |
| P4 | Annualization factor 252 | `kernel/portfolio_qp/tasks.py:473`, `kernel/vol_target.py:69` | Crypto trades ~365 d/yr; √252 understates vol | S |
| P5 | Wash-sale engine has zero asset-class awareness | `selection.py:39-180`; `kernel/pipeline/task_candidates.py:23-71` (buy block); `kernel/portfolio_qp/constraint_snapshot.py:73,262-280` (QP hard mask); `kernel/config_schema.py:55` | Crypto is property — §1091 wash-sale does NOT apply; the gate + QP mask must be bypassed per asset class (never globally) | M |
| P6 | Tax module (COMPATIBLE) | `kernel/portfolio.py:49-114`, `kernel/trade_events.py:328-334` | ST/LT 365-day property treatment applies to crypto as-is; no change — verify only | XS |
| P7 | Vol clips pin for crypto | `kernel/panel_pipeline/job_panel_scoring.py:3556-3582` (σ clip [0.05, **1.50**] annualized); `kernel/vol_target.py:24-47` (target 0.15, SPY-proxied); `kernel/panel_pipeline/global_calibrator.py:225` (ER clip ±0.20) | Crypto realized vol 60–150%+ pins the 1.50 ceiling → Kelly can't discriminate vol across names; SPY proxy meaningless | M |
| P8 | Fundamentals hard-blocks | `kernel/preflight_pipeline/tasks/fundamentals_freshness.py` (P-FUND-FRESHNESS, enabled default `:277`); `job_panel_scoring.py:229-250,1287-1293` (panel fails closed without fundamentals) | No 10-Q/fiscal calendar exists for crypto → every buy hard-blocked; scorer fail-closes | M–L |
| P9 | Slash symbols break file paths | `kernel/data.py:131-132` (`data_dir/symbol.upper()/1d.parquet`), `kernel/data_coverage.py:120-149`, `_yf_translate data.py:60-95` | `"BTC/USD"` becomes a nested `BTC/USD/` directory; cache keys collide | S–M |
| P10 | Sector map + SPY regime coupling | `task_candidates.py:74-106` (missing_sector_map block, SPY default `:94,129-137`); `task_spy_regime.py:129,147`; `regime.py:225,399`; `market_gates.py` | No GICS sector, no SPY analog; regime engine and market gates assume an equity index | M |
| P11 | No asset_class concept exists at all | `kernel/config_schema.py` (`StrategyConfigSchema`) — grep-verified absence of any `asset_class`/`instrument_type` field in `src/` | The abstraction has to be introduced and threaded to P1/P2/P5/P8/P9/P10 | M |

### 2.3 renquant-base-data

| # | Gap | Evidence (file:line) | Why it breaks for crypto | Size |
|---|---|---|---|---|
| B1 | Daily OHLCV provider = yfinance only | `loaders/data.py:230-234,252-277` (any other provider raises), `:295-404` (incremental fetch) | Needs a crypto provider branch (Alpaca `CryptoHistoricalDataClient`, [VERIFIED] `api_version="v1beta3"` `alpaca/data/historical/crypto.py:73`, `get_crypto_bars` `:80`) | M |
| B2 | Intraday bars = Alpaca **stock** IEX client | `loaders/data.py:455-545` (`StockHistoricalDataClient` + `feed=DataFeed.IEX`) | Closest template; crypto swaps to `CryptoBarsRequest` ([VERIFIED] `alpaca/data/requests.py:110`), no IEX feed (crypto feed is `CryptoFeed.US`, `alpaca/data/enums.py:92-100`); same `ALPACA_API_KEY` creds (`loaders/data.py:503-545`) | M |
| B3 | Calendar/weekday assumptions | `loaders/data.py:23-57` (NY-clock freshness via `renquant_common.market_calendar`); `pit_revision_features.py:62-64,172,189-194` (weekday<5); `alpha158_qlib_panel.py:60,221-228` (SPY ffill 5d); `watchlist_screen.py:18,50-51` (252) | Weekend rows dropped / flagged stale; annualization wrong | S–M |
| B4 | Label is SPY-excess, 60 trading days | `rawlabel_sidecar.py:60,63` (`DEFAULT_BENCHMARK_TICKER="SPY"`), `:67,132,256,287` (60td horizon) | Crypto needs its own label: no SPY, and trading-day horizons ≠ calendar-day horizons on a 365-day market | M |
| B5 | Slash symbols break the store layout | `loaders/data.py:106-107`, `loaders/data_cache.py:26-28,63-64,97-98`, `alpha158_qlib_panel.py:170,315,326,416,423` | Same nested-directory break as P9 | S |
| B6 | Manifest contract already has `asset_class` (REUSE) | `validation.py:18,22-23` (required keys incl. `asset_class`), `registry.py:20,45-70` (resolver filters by it), `manifests/example-dataset.json` | A crypto dataset registers cleanly as `asset_class:"crypto"` — no schema change | XS |
| B7 | Feature building lives here; price/volume ops reusable | `alpha158_qlib_panel.py:1-8,26-40` (imports `alpha158_ops`) — kbar/rolling/slope operators are asset-agnostic; fundamentals families (SEC/PEAD/insider/analyst) have no crypto analog | Crypto panel builder = price/volume alpha158 subset + crypto-native features (§4), in this repo | M |

### 2.4 renquant-strategy-104 (template for the new repo)

| # | Fact | Evidence (file:line) | Consequence | Size |
|---|---|---|---|---|
| S1 | Strategy repo = config + validator only | `CLAUDE.md:15-24`; layout: `configs/strategy_config{,.golden,.shadow}.json`, `src/renquant_strategy_104/config.py`, `config_drift.py`, pointer manifest + tests | The new-repo scaffold is a known, small pattern | S–M |
| S2 | Validator hard-requires equity concepts | `config.py:34-36` (benchmark ∈ watchlist), `:39-41` (sector_map covers every ticker), `:46,50-54` (equity regime taxonomy, BULL_CALM pin) | Crypto validator must drop sector-map/SPY/regime-taxonomy requirements | S |
| S3 | Equity-only config blocks to strip | `configs/strategy_config.json:485-664` (sector maps), `:159,676-684,1310` (wash-sale/tax/reentry), `:416-425` (entry_open_delay/close_cutoff), `:670-675` (T+1), `:1112-1200` (fundamentals monotone constraints) | Documented strip-list for the crypto config | — |

### 2.5 renquant-model + renquant-common

| # | Gap | Evidence | Why it matters | Size |
|---|---|---|---|---|
| M1 | WF gate has **no transaction-cost model** | grep-verified absence of `cost_bps/transaction_cost/net_of_cost/fee` across `renquant-model/src/renquant_model_gbdt`, `renquant_model_common`, and `renquant-common/src` (2026-07-10) | Crypto taker fees (~25 bps/side `[GUESS]`) × turnover can consume the entire edge at h=20; a gross-IC gate would promote a net-negative model. Fee-aware net-of-cost evaluation is a NEW capability, not a config knob | L |
| M2 | Always-open calendar mode missing | base-data header cites canonical `renquant_common.market_calendar` (`loaders/data.py:36-57`) — NYSE-only today | One canonical ALWAYS_OPEN calendar in renquant-common, consumed by base-data/pipeline/orchestrator, instead of three local hacks | M |

### 2.6 renquant-orchestrator

| # | Gap | Evidence (file:line) | Why it matters | Size |
|---|---|---|---|---|
| O1 | 105 scheduler is NYSE-session-bound | `intraday_session_scheduler.py:33-34` (injected NYSE calendar), `:107-108` (entry_open_delay 300s / close_cutoff 1800s), `:287-316` (`SessionWindows.from_bounds`) | The bones to fork (§3.5): triple gate, kill-switch file, tick loop, shadow log, manifest are all reusable; only the calendar/session model changes | M |
| O2 | Collectors are session-hours launchd jobs | `ops/renquant105/*.plist` (`StartCalendarInterval`), `intraday_quote_logger.py:31-32,262-289` (NYSE bounds) | 24/7 loop needs a `KeepAlive` daemon pattern + gap-tolerant restart, not wall-clock firing | S–M |
| O3 | ntfy topic is shared default | `daily_trading_health.py:147,515` (`NTFY_TOPIC` default `"renquant"`) | Crypto sleeve gets its own topic (`renquant-crypto`) so 24/7 alerts don't drown the equity channel | XS |

### 2.7 Alpaca SDK capability verification (alpaca-py 0.43.4, umbrella venv)

| Claim | Status | Evidence |
|---|---|---|
| Crypto historical bars, v1beta3 | [VERIFIED] | `alpaca/data/historical/crypto.py:73` (`api_version="v1beta3"`), `get_crypto_bars :80`, latest trade/quote/bar/orderbook/snapshot `:156-251` |
| Crypto live stream | [VERIFIED] | `alpaca/data/live/crypto.py:12` (`CryptoDataStream`) |
| `AssetClass.CRYPTO` (+ `CRYPTO_PERP`, out of scope) | [VERIFIED] | `alpaca/trading/enums.py:185-186` |
| TIF GTC/IOC enums | [VERIFIED] | `alpaca/trading/enums.py:246,249` |
| Crypto order types = market, limit, **stop_limit** | [VERIFIED in SDK docs] | `alpaca/trading/enums.py:129`; `StopLimitOrderRequest` class `trading/requests.py:460`. Server-side acceptance of GTC stop_limit on each pair: paper-verify at Stage 0 |
| Per-asset `min_order_size` / `min_trade_increment` / `price_increment` | [VERIFIED] | `alpaca/trading/models.py:66-68` |
| Universe discovery by asset class | [VERIFIED] | `GetAssetsRequest.asset_class` `trading/requests.py:127-139`; `TradingClient.get_all_assets` `trading/client.py:376` |
| Account crypto enablement flag | [VERIFIED] | `TradeAccount.crypto_status` `trading/models.py:485,528` |
| Fee schedule (taker ~25 bps / maker ~15 bps tier-0), non-marginable 1× buying power, no shorting, history depth (~2021+ on Alpaca; BTC-USD 2014+ on yfinance) | [GUESS] | Not verifiable from the SDK — Stage-0 paper battery items (§6) |

---

## 3. Architecture

### 3.0 Asset-class abstraction principle

One new first-class concept, threaded once: `asset_class: "crypto"` in the
strategy config (home: pipeline `kernel/config_schema.py` `StrategyConfigSchema`
— P11), consumed by calendar selection (P1), hold-clock aging (P2), settlement
(P3), annualization (P4), wash-sale bypass (P5), fundamentals-gate bypass (P8),
sector-gate bypass (P10), and symbol path encoding (P9/B5). No gate is removed
for equities; every bypass is keyed on the asset class of the running config.

**Symbol policy (fixes P9/B5/E-paths once):** canonical pair form `"BTC/USD"` in
configs and all broker/data API calls; canonical slug form `"BTC-USD"`
(slash→dash) for every file path, directory, cache key and DB key. One shared
`pair_slug()/slug_pair()` helper in renquant-common; the slug form coincides with
yfinance's crypto ticker format, so vendor cross-checks need no third form.

### 3.1 New strategy repo: `renquant-strategy-crypto`

Clone of the strategy-104 pattern (S1): configs (active/golden/shadow),
validator, drift detector, pointer manifest, tests. Owns:

- **Universe**: the ~20 Alpaca USD pairs, pinned as an explicit list snapshotted
  at Stage 0 from `get_all_assets(asset_class=CRYPTO, status=ACTIVE)` — never
  dynamic at runtime (auditable, like the 104 watchlist). Per-pair
  `min_order_size`/`min_trade_increment`/`price_increment` snapshotted alongside.
- **Sleeve budget as a HARD config cap**: `sleeve.budget_usd` (design 1000–2000;
  exact value at canary sign-off). Enforced at TWO layers: pipeline sizing
  (available = min(cash-derived, budget − crypto MV − open crypto buys)) and an
  orchestrator preflight assertion before any submit. Never a soft target.
- **Crypto risk rails**:
  - vol-scaled per-name caps: `max_position_pct` of the SLEEVE (not account),
    scaled down by realized σ relative to universe median (replaces the pinned
    σ-clip Kelly, P7);
  - 24/7 sleeve drawdown halt: sticky halt of NEW entries at
    `sleeve.max_drawdown_pct` (proposed 10%) from sleeve high-water mark,
    evaluated every tick, exits always allowed — self-serve on weekends;
  - sleeve-level kill switch: file + env flag (§3.5) — halts entries AND
    (optionally, flag-controlled) triggers protective-stop refresh.
- **Strips (S2/S3)**: no sector map, no SPY benchmark, no fundamentals gates, no
  wash-sale/tax-reentry knobs, no entry_open_delay/close_cutoff, no T+1
  settlement fields. Validator requires instead: every pair has a pinned
  increment snapshot; budget cap present; drawdown halt present; stop policy
  present.
- **Regime**: Stage-1 ships with a minimal BTC-anchored vol/trend regime flag
  (features only, no equity taxonomy); the equity `RegimeLabel` taxonomy is NOT
  reused (P10). Regime-conditioned policy is a later, evidence-gated addition.

### 3.2 renquant-execution additions

New crypto order validation seam next to the existing fractional validators
(`broker.py`), plus Alpaca adapter changes:

- **Account-scoped cash reservation ledger (§5.3 CORRECTED, NEW)**: a single
  `AccountCashLedger` keyed by the real brokerage account (not by broker tag)
  replaces per-book `reserved_cash()` as the sizing headroom source of truth
  for BOTH the 104 equity lane and the crypto sleeve — see §5.3 for the full
  design. This is the one place 104's existing sizing path gains a new call;
  everything else in this table is crypto-only.
- **Asset-class classifier**: pair-form symbol (or `get_asset().asset_class ==
  CRYPTO`) → crypto order rules; equities take the existing path untouched.
- **TIF policy (E1/E2)**: crypto orders = GTC (resting limit / protective stops)
  or IOC (immediate entry). DAY is rejected for crypto by the validator — the
  exact inverse of the equity fractional rule, same enforcement point
  (`validate_fractional_order` family).
- **No-short guard (E11)**: explicit assertion — crypto sell qty ≤ held qty;
  keeps long-only structural even if equity shorting ever lands.
- **Fee model (E4)**: `CryptoFeeModel(taker_bps, maker_bps)` config-driven from
  the strategy repo; consumed by `order_math` sizing (fees reduce affordable
  qty), `reserved_cash` (reservation includes fee), and `paper_broker` fills
  (paper P&L nets fees). Fee tier values come from the Stage-0 battery, never
  hardcoded.
- **Min notional / increment (E5/E6/E7)**: replace fractionable-lookup with the
  per-pair increment snapshot: qty rounded DOWN to `min_trade_increment`,
  reject below `min_order_size`, limit prices rounded to `price_increment`.
- **Crypto protective stop path (E8)**: `place_crypto_stop_limit(symbol, qty,
  stop, limit)` building `StopLimitOrderRequest` + `TimeInForce.GTC` in native
  fractional qty — no whole-share gate. See §5.1.
- **Lifecycle (E9)**: crypto orders are excluded from the DAY-expiry sweep;
  instead a `max_resting_age` watchdog (config) cancels+reconciles stale
  non-protective GTC orders. Protective stops are exempt from the watchdog.
- **Reconciliation (E3)**: fills/open-orders queries take the asset class of the
  running sleeve (or query both and tag), so crypto orders are visible to
  reconcile-before-emit.
- **Market-hours (E10)**: crypto paths never consult `get_clock().is_open` or
  the NYSE pre-open gate.
- **State isolation (E12)**: broker tag `alpaca_crypto` (§5.3).

### 3.3 renquant-base-data additions

- **Crypto bars ingestion (B1/B2)**: `fetch_crypto_bars` provider branch —
  `CryptoHistoricalDataClient` + `CryptoBarsRequest` (v1beta3), daily (1Day) and
  intraday (1Min/1H) timeframes, no IEX feed argument, same env creds. Store
  under a crypto namespace with slug paths: `data/crypto_ohlcv/{SLUG}/1d.parquet`
  (+ intraday analog). Vendor cross-check job against yfinance `{SLUG}` daily
  bars (two-source parity before any training run).
- **Manifests (B6)**: register datasets with `asset_class:"crypto"` — existing
  schema, no change. Fingerprint + freshness contract identical to equities but
  against the always-open calendar (M2).
- **Crypto panel builder (B7)**: price/volume alpha158 subset via the existing
  asset-agnostic `alpha158_ops` + crypto-native features (§4.2); label sidecar
  per §4.3 (raw forward return, calendar-day horizon — no SPY-excess, B4).
- **Calendar (B3)**: ingestion freshness for crypto uses the ALWAYS_OPEN
  calendar; "last completed session" = last completed UTC day.

### 3.4 renquant-pipeline additions

- **ALWAYS_OPEN calendar mode (P1/P2/P3/P4, M2)**: one canonical calendar in
  renquant-common (`market_calendar`), selected by `asset_class`: sessions =
  UTC calendar days; every day is a trading day; hold/streak clocks age in
  calendar days; settlement_days = 0; annualization = 365.
- **Wash-sale bypass (P5)**: `is_wash_sale_blocked*` and the QP wash mask are
  short-circuited when the running config's asset class is crypto (property —
  §1091 does not apply). The equity path is untouched; the bypass is asserted in
  tests both ways (crypto never blocked; equity behavior byte-identical).
- **Tax property-mode (P6)**: NO code change — the existing ST/LT 365-day
  holding-period model applies to crypto as-is; the crypto config simply omits
  wash-sale knobs. A test pins that crypto sell decisions never consult
  wash-sale state.
- **Vol handling (P7, CORRECTED — Codex review, 2026-07-10)**: crypto config
  gets its own σ clip (proposed [0.20, 3.00] annualized-365). The prior
  "BTC-proxied (not SPY) OR absolute" phrasing left an unresolved ambiguity
  identical to the one Codex's review just corrected on the Deployment
  Governor RFC's "voltarget" L1 candidate: a benchmark-proxied portfolio-vol
  target is WRONG whenever the selected slate's own correlation structure
  diverges from the proxy's (here: a slate concentrated in low-BTC-beta alts
  would have its true portfolio vol systematically mis-estimated by a
  BTC-proxy). This RFC has no real selected-portfolio covariance estimator
  today (the Governor RFC's own resolution was to REMOVE its analogous
  voltarget arm rather than ship a proxy, for the same reason — no portfolio-
  covariance infrastructure exists yet in this codebase). Frozen resolution:
  **ABSOLUTE vol target only** (a fixed annualized-365 target level, no
  benchmark/proxy comparison of any kind) — the per-name vol-scaled caps
  (§3.1) already do the cross-sectional risk discrimination the pinned clip
  can't; a portfolio-level BENCHMARK-relative vol target is explicitly OUT
  OF SCOPE for v1 and would need a real portfolio-covariance estimator
  (reusing whatever the Governor track eventually builds, if it does) before
  being reconsidered.
- **Gate bypasses (P8/P10)**: P-FUND-FRESHNESS, sector-map gate, SPY regime/
  market gates are disabled by asset class (not by hand-editing shared
  defaults); panel scorer runs in a declared "no-fundamentals feature set" mode
  so it fail-closes only on inputs crypto actually has.
- **Symbols (P9)**: pipeline reads/writes bars via the slug helper.

### 3.5 Orchestrator: 24/7 crypto session scheduler

Fork of the 105 scheduler BONES (`intraday_session_scheduler.py`) — the parts
that carry over unchanged are exactly its safety spine: triple gate (config
enabled + env flag + kill-switch file absent, re-checked every tick), fixed tick
cadence, append-only shadow decision log, atomic session manifest with
fingerprints, and the `assert_shadow_never_submits` runtime assertion evaluated
on every tick (`intraday_session_scheduler.py:354-383`). What changes:

- **Always-open session model**: a "session" = one UTC calendar day
  (00:00–24:00 UTC) — this is a bookkeeping boundary for manifests/ledger/
  liveness, not a market boundary. `SessionWindows` in always-open mode has no
  open-delay or close-cutoff (`entry_open_delay`/`close_cutoff` are equity
  concepts, O1).
- **Leakage-proof session contract (FROZEN — Codex review, 2026-07-10; a clock
  boundary alone is not a leakage proof)**: reuses the decision-snapshot-
  digest PATTERN already established for the D6-§2a shadow-A/B protocol
  (`doc/design/2026-07-09-governor-prereg-replay-protocol.md` §2a) — freeze a
  digest of the exact inputs a decision may consume, verify consumption
  against it, fail closed on mismatch — applied here to the daily crypto
  signal instead of a paired-arm experiment:
  - **Watermark**: session D's class-A signal may consume price bars ONLY up
    through the daily bar that CLOSES at `D 00:00:00 UTC` (i.e. day D-1's
    full UTC day). A bar is eligible only once base-data's ingestion job has
    marked it "closed and fetched" — not merely "timestamp has passed" — so
    a late-arriving vendor bar cannot silently backfill into an
    already-frozen signal.
  - **Quiet interval (exact endpoints)**: `[D 00:00:00 UTC, D 00:15:00 UTC)`
    — no NEW entries may be submitted in this 15-minute window, every day,
    regardless of when the signal computation actually finishes inside it.
    Exits and protective-stop maintenance are NEVER subject to this window
    (105 §10 precedence rule, §5.4). If signal computation has not produced
    a valid, digest-verified snapshot by `D 00:15:00 UTC`, entries stay
    fail-closed (see below) until it does — the window is a minimum, not a
    guarantee the signal is ready.
  - **Signal snapshot digest (concrete)**: at signal-compute time, materialize
    an immutable snapshot file containing: the frozen bar-close watermark
    timestamp, the pinned pair-universe list + its snapshot hash (§3.1), the
    model+calibrator artifact identity (same `model_content_sha256`/
    `calibrator_content_sha256` convention already unified elsewhere in this
    project), and the session date D. Hash this canonically
    (sha256, sorted-keys JSON — same construction style as
    `compute_decision_snapshot_digest` in orchestrator's
    `native_live_context.py`) into `signal_snapshot_digest`. Every entry
    decision within session D must load the signal via this digest and
    independently re-verify it; a mismatch (mutated snapshot file, wrong
    model identity, stale watermark) fails that decision closed.
  - **Fail-closed / retry**: if no valid `signal_snapshot_digest` exists for
    session D (compute job hasn't run, failed, or produced a rejected
    watermark), ALL entries for session D are blocked — not degraded, not
    retried with a stale prior-day signal. The compute job itself may retry
    on transient failure (e.g. a data-fetch timeout) up to a bounded number
    of attempts within the quiet window and shortly after; once session D's
    watermark has passed without a valid snapshot, D is a no-entry day,
    logged and alerted, not silently rolled forward to D+1's signal.
  - **Persistence**: `signal_snapshot_digest` (plus its full input identity:
    watermark, universe hash, model/calibrator identity, session date) is
    stamped into every tick's bundle for session D — not just once per
    session — so a replay audit can verify every entry decision that day
    actually consumed the frozen snapshot, the same way the D6-§2a run
    bundle is verified per-session.
- **Cadence**: default 900 s (15-min tick). Rationale: 105 uses 180 s for
  equity-session hours; 24/7 at 180 s = 480 ticks/day of API load for a sleeve
  whose signal is daily — 15 min bounds cost/rate-limit exposure while keeping
  intraday risk-rail latency ≤ 15 min. Cadence is config, not code.
- **Kill switch**: own file (`data/crypto/kill_switch`) + own env flag
  (`RENQUANT_CRYPTO_TRADING`, default OFF) — both separate from the 105 equity
  flags so one sleeve can be halted without touching the other.
- **ntfy separation (O3)**: topic `renquant-crypto` for all sleeve alerts.
- **Ops (O2)**: launchd `KeepAlive` daemon (not `StartCalendarInterval`);
  restart-safe: on start, reconcile-before-emit (broker open orders + ledger),
  never replay missed ticks (skip-not-queue, same as 105's overrun rule).
- **Run bundles**: every session persists a bundle (config fingerprint, universe
  snapshot hash, signal version, tick count, halts) — CLAUDE.md run-bundle rule
  applies unchanged.
- **Mode ladder**: shadow → paper → canary-live, same downgrade-by-default
  posture as 105 Stage 1 (`mode:"live"` in config downgrades to shadow until
  the arming gate of §6 exists).

Boundary compliance (CLAUDE.md): the orchestrator schedules, provenances and
gates rollout; broker mechanics live in execution; decision/sizing internals in
pipeline; training in the model factory; config/policy in the strategy repo.

---

## 4. Model design — crypto cross-sectional panel scorer

### 4.1 Family and harness

**XGB (GBDT) panel scorer in the existing `renquant_model_gbdt` factory
harness**, published to renquant-artifacts and consumed by `artifact_path` pin —
identical lifecycle to 104. Why XGB and not PatchTST: (a) the current 104
primary is the operator-re-promoted XGB — same family keeps one governance
story; (b) ~20 names × ~5–9 years of daily bars is a small-data regime where
GBDT on engineered features is the defensible prior; (c) PatchTST's fingerprint/
contract complexity (the recurring calibrator-fingerprint incidents) is weight
we should not carry into a new asset class on day one.

### 4.2 Features — price/volume only (NO fundamentals exist)

- alpha158 **price/volume subset** (kbar, rolling stats, slope/resi/rsquare —
  the asset-agnostic operators already in `alpha158_ops`, B7);
- crypto-native additions: multi-horizon momentum (5/10/20/60/90 calendar-day),
  realized vol (7/30d, annualized-365), drawdown depth from rolling 90d high,
  volume z-score (30d), Amihud illiquidity, rolling BTC-beta and BTC-residual
  momentum (cheap orthogonality diagnostics, NOT label neutralization — the
  equity neutralization-retrain rejection stands as a prior: measure first).
- Explicitly absent: fundamentals, analyst, sentiment, on-chain (out of scope
  v1 — a later, evidence-gated addition).

### 4.3 Label + horizon

- **Label (FROZEN — Codex review, 2026-07-10; not a post-hoc choice)**: raw
  forward return over **h = 20 calendar days** on the daily UTC bar axis,
  cross-sectionally ranked at scoring time, is the PRIMARY label, frozen
  BEFORE any WF evidence is consulted. BTC-excess return is registered as a
  PRE-REGISTERED DIAGNOSTIC ONLY — computed and reported alongside the
  primary result, never substituted for it, and never used to select which
  label "worked better" after seeing WF output (that would be the exact
  post-selection bias this freeze exists to prevent). Rationale for raw-as-
  primary: cross-sectional ranking already keeps BTC beta implicit in every
  score without hard-wiring an explicit alt-tilt the way a BTC-excess label
  would; BTC-excess risks systematically rewarding low-BTC-beta names
  regardless of their own raw quality, which is a design choice, not a
  free diagnostic swap.
- Why 20d (vs the equity 60td ≈ 3 months): crypto regime/momentum cycles are
  faster and 365-day markets compound faster; h=20 keeps ≥ 60 non-overlapping
  label windows over 5 years for WF evaluation. h ∈ {10, 20, 40} is swept in
  research, but 20d is the pre-registered primary — no post-hoc horizon
  shopping.

### 4.4 Governance — same gates as 104, plus fees

- WF gate: purged walk-forward with embargo ≥ h, shuffled-label + time-shift
  placebos, DSR/PBO, 3-tier promotion — the identical discipline, run in the
  model factory. The equity embargo-leakage-floor lesson applies: trust
  placebo-clean DIFFERENCES, not absolute IC.
- **ONE authoritative net-cost model (CORRECTED — Codex review, 2026-07-10;
  fee-only is insufficient for a stop-limit, thin-weekend venue)**: a single
  cost-accounting primitive — fees (taker/maker bps), spread/slippage,
  increment rounding (loss from `min_trade_increment` truncation), and
  rejected/unfilled/resting-order handling (an order that rests and never
  fills is a zero-fee, zero-fill outcome that a naive "assume it fills at
  mid" backtest would over-credit) — used IDENTICALLY by WF-gate replay
  evaluation AND live runtime accounting (paper P&L, reservation sizing,
  QP/rotation cost-kappa — one number, every consumer, per §4.7's turnover-
  sensitivity risk). Net evaluation: `net = gross − cost_model(...)` at the
  strategy's realized rebalance turnover. A crypto model that passes gross
  and fails net is a FAIL. **Stage 0 calibrates and bounds EACH component**
  from the paper battery (§6): fee bps from fill receipts, spread/slippage
  from paper-order fill-price-vs-quote deltas, rounding loss computed exactly
  from the pinned increment snapshot (§3.1, deterministic, no calibration
  needed), and resting/rejected-order rates from the battery's own order
  outcomes — no component ships uncalibrated.
  - **Repo split (D-C8, CORRECTED)**: the generic cost-accounting PRIMITIVE
    (the shared math above) lives in `renquant-model`-common/shared code, so
    equities inherit it later without a crypto-specific gate polluting
    shared code. The BTC-baseline comparison and the crypto promotion
    DECISION (below) stay entirely in `renquant-model`, asset-specific,
    consuming the shared primitive rather than reimplementing it.
- **Small-breadth honesty**: 20 names with high mutual BTC correlation is an
  effective breadth of maybe 5–8 — IR = IC·√breadth punishes this. The gate
  must therefore include a **BTC-only baseline** (renquant-model-owned, not
  shared code — see repo split above): the panel model must beat
  buy-and-hold BTC and a naive BTC-timing rule net of fees on the WF windows,
  or it does not promote. If the panel cannot beat the trivial baselines, the
  sleeve does not deserve a model — that is a legitimate NO-GO outcome and the
  capability work (§3) still stands for a later attempt.
- Per-symbol tournament: optional later; v1 is panel-only.

### 4.5 Serving

Daily cadence, 105-style split: the panel scores once per UTC day after the
`D 00:00:00 UTC` daily bar closes (the watermark defined in §3.5's frozen
leakage-proof session contract), producing the `signal_snapshot_digest` that
governs every entry decision for session D; the 24/7 loop consumes the frozen
ranking and does entry timing + risk rails intraday (class C/D). No intraday
re-scoring in v1 (mirrors the 105 Stage-1/Stage-3 boundary).

### 4.6 Training data

- Primary: Alpaca crypto daily bars v1beta3 (depth `[GUESS]` ~2021+ — verified
  at Stage 0); Secondary/backfill + cross-check: yfinance (`BTC-USD` 2014+,
  most majors 2017+ `[GUESS]`). Two-source parity check (B-audit pattern) is a
  hard prerequisite to the first training run; disagreements > tolerance
  quarantine the pair.
- **Survivorship bias (CORRECTED — Codex review, 2026-07-10)**: the original
  proposal ("universe = Alpaca's CURRENT list, bias mitigated by the
  BTC-baseline gate") understated the problem. A current active-pair list
  cannot define a defensible 5–9 year cross-sectional training universe:
  delisted/rug-pulled/late-listed pairs are absent from that list EXACTLY
  when their history would hurt the model, and no BTC-baseline comparison
  corrects for the panel itself being built from survivors.

  **PIT source inventory (candidates named, each marked)**: the ideal fix is
  point-in-time listing/tradability INTERVALS per pair, so the eligible
  universe can be snapshotted at every training/replay date. Candidates:
  - **Alpaca assets endpoint**: [VERIFIED — NO history] `TradingClient.
    get_all_assets` (§2.7) returns only the CURRENT asset list/status; no
    historical-snapshot or as-of-date parameter exists anywhere in the
    alpaca-py 0.43.4 surface. Cannot provide PIT intervals by itself.
  - **Alpaca listing/delisting announcements** (blog / changelog / release
    notes): [GUESS] listing dates likely reconstructible by hand;
    COMPLETENESS (quiet delistings, temporary halts) unverified. Stage-0
    investigation item.
  - **Web-archive snapshots of Alpaca's supported-crypto docs page**:
    [GUESS] snapshot density over 2021–2026 unverified; if dense, yields
    coarse (weeks-granularity) tradability intervals. Stage-0 item.
  - **CoinGecko exchange-tickers/listings history**: [GUESS] CoinGecko
    tracks per-exchange tickers, but whether Alpaca is covered as an
    exchange and whether HISTORICAL intervals (not just current state) are
    exposed via API is unverified. Stage-0 item.
  - **CoinMarketCap historical universe snapshots**: [GUESS] market-wide
    PIT rank/cap snapshots exist but say nothing about Alpaca tradability —
    usable only as an upper-bound eligibility screen, never as the
    tradability source.
  **Stage-0 bounded investigation (timeboxed ≤1 day, part of the paper
  battery report)**: attempt to reconstruct per-pair tradability intervals
  from the sources above. If a defensible interval table results (every
  pair's listing date sourced; delistings/halts accounted for), tier 1
  below is UPGRADED to a PIT-gated panel (eligible universe re-snapshotted
  at every training/replay date) and the model card says so. If not, the
  pre-registered WEAKER claim below stands (per Codex's explicit fallback)
  — we do not build a point-in-time system with no real data behind it,
  and we never call the result a 5-year panel validation of the current
  universe.

  **Frozen resolution — two separate, explicitly-scoped evidence tiers,
  never conflated**:
  1. **Historical WF panel (EXPLORATORY, survivor-only by construction)**:
     restricted to a SMALL, explicitly-labeled subset of pairs that have
     been continuously major/liquid across the FULL evaluation window on
     BOTH Alpaca and the yfinance cross-check (expected: BTC, ETH, and a
     short list of long-established large-caps — the exact list is
     determined at Stage 0 from the actual two-source coverage overlap, not
     guessed here). This is NOT a "5-year panel validation" of the current
     ~20-pair universe — it is directional, hypothesis-generating evidence
     on a deliberately survivor-biased subset, labeled as such everywhere it
     is reported (model card, WF gate output, any operator-facing summary).
     It may inform model-family/feature choices; it may NOT alone justify a
     promotion decision for the full universe.
  2. **Full current-universe validation (PROSPECTIVE, not survivorship-
     biased)**: the actual ~20-pair CURRENT universe is validated ONLY
     forward — Stage 1's ≥14-day shadow window and Stage 2's canary weeks
     (§6) are genuinely out-of-sample with respect to which pairs exist
     today, so they carry none of the historical panel's bias. The
     BTC-baseline gate (§4.4) and placebos apply to BOTH tiers, but tier 2
     is the decision-grade evidence for whether the full-universe strategy
     is promoted to canary/full sleeve — not tier 1.
  - The model card must state which tier any reported metric comes from; a
    metric from tier 1 must never be presented as if it were tier 2
    evidence.

### 4.7 Named crypto-specific risks (pre-registered in the model card)

1. **Regime nonstationarity** — 2017/2021/2022-style cycle breaks; WF windows
   must span at least one full drawdown cycle; the sticky sleeve drawdown halt
   (§3.1) is the runtime backstop, not the model.
2. **24/7 vol clustering + weekend liquidity holes** — weekend realized vol and
   spreads differ; the fee/slippage model uses taker pricing (worst case), and
   the canary must cross ≥ 2 full weekends before scale-up (§6).
3. **Fee-adjusted turnover sensitivity** — at 25 bps taker each way, a
   20d-horizon strategy re-ranked daily can churn its edge away; turnover enters
   the WF cost model (above) AND the runtime QP/rotation cost-kappa for crypto
   is set from the same schedule — one number, two enforcement points.
4. **Single-venue prices** — Alpaca crypto quotes/fills are Alpaca-venue
   (`CryptoFeed.US`); bars may deviate from consolidated global prices.
   Accepted and documented for a $1–2k sleeve; the vendor cross-check bounds it.

---

## 5. Risk & ops — 24/7 on one Mac

### 5.1 Machine-death exposure: broker-resident GTC stop-limits

The equity lane's known weakness (software stops need the loop alive; broker
stops need whole shares, E8) inverts for crypto: **every filled crypto position
gets a broker-resident GTC stop-limit sell** in native fractional qty
([VERIFIED] SDK supports stop_limit for crypto + GTC TIF, §2.7; server-side
acceptance paper-verified at Stage 0). If this Mac dies, sleeps, or loses
network, a RESTING ORDER persists at the broker — strictly BETTER than the
current equity fractional case, where no order rests at all. **This is NOT an
execution guarantee (CORRECTED — Codex review, 2026-07-10; the original
phrasing "downside protection persists" implied broker-residency alone
bounds loss, which it does not)**: a stop-LIMIT can gap through in a fast
move without filling at all — the order rests, triggers, and then may not
execute if the market gaps past the limit price before it can. The honest
claim is narrower: broker residency means the STOP ORDER survives machine
death; it does not mean the position is guaranteed to exit at or near the
stop price. See the residual-risk note below and §4.7 item 2.

- Stop distance: vol-scaled from the per-name realized σ (proposed
  stop = entry − 2.0×σ_20d,daily, floored at −10% and capped at −25% from
  entry); limit band below stop by a config bps buffer (crypto has no LULD;
  a pure stop-market does not exist for crypto per the SDK order-type matrix).
- Lifecycle: cancel/replace on position change; protective stops are exempt
  from the resting-age watchdog (§3.2); reconcile-before-emit treats a missing
  protective stop as a Tier-1 defect (alert + re-place before any new entry).
- Residual risk (honest): a stop-LIMIT can gap through in a flash crash;
  accepted for sleeve size, recorded in the model card.

### 5.2 Mac sleep / weekends

- launchd does NOT wake a sleeping Mac. Policy: the loop must tolerate
  arbitrary gaps — on wake: reconcile-before-emit, recompute risk rails, skip
  (never replay) missed ticks. GTC stops carry the tail while asleep.
- Keeping the node awake (pmset schedules / caffeinate) is a MACHINE-LANDING
  action → ask-first, one grant per batch, per the operating rules. The design
  works without it (gaps + broker stops); staying awake only improves rail
  latency.
- **Liveness**: 24/7 dead-man alert (fork of the rq105 liveness pattern) — if
  no tick heartbeat for > max_gap (proposed 60 min), page `renquant-crypto`
  topic. Weekend expectation is alerts-only: the sticky drawdown halt and
  broker stops are the self-serve defenses; no operator action is assumed.

### 5.3 Sleeve isolation from equity strategies

- **State**: broker tag `alpaca_crypto` → `live_state.alpaca_crypto.json` +
  `runs.alpaca_crypto.db` (existing seam: pipeline `kernel/state_paths.py:4-15`,
  execution `readonly_broker.py:19-24`); `parent_intent_id` hashes the account
  tag (`order_state_machine.py:177-200`) so dedup keys can never collide with
  equity intents. Zero writes to any equity state file, DB, or config.
- **Ledger**: crypto decisions go to the sleeve DB with `asset_class` stamped;
  equity dashboards/attribution are unaffected.
- **Cash (CORRECTED — Codex review, 2026-07-10)**: the sleeve shares the ONE
  brokerage buying-power balance with the 104 equity lane. The original
  proposal ("cadence separation + a local sleeve cap means 104 needs no
  change") is FALSE under concurrent snapshots: `OrderStateBook` is
  per-`account` (i.e. per broker TAG — `alpaca` for equity, `alpaca_crypto`
  for the sleeve, `order_state_machine.py:486-488`), and `reserved_cash()`
  (`:830-843`) is computed from ONLY that book's own open parent intents.
  Two independent books sizing `broker_cash - reserved_cash` from two
  independent LOCAL views of the same real account can each believe headroom
  exists that the other has already spent — a genuine concurrent
  double-reservation, not a documentation gap. Cadence separation (104 sizes
  once post-close; crypto ticks every 15 min) does NOT bound this: the crypto
  loop can submit between two 104 batch runs, and 104's own batch can start
  mid-way through a crypto entry's order lifecycle.

  **Fix — account-scoped reservation ledger (execution-owned, NEW, D-C4)**:
  a single `AccountCashLedger`, keyed by the REAL brokerage account (not by
  broker tag), tracking the SUM of all open buy-order cash reservations
  across every sleeve/tag sharing that account. Backed by one SQLite table
  (`data/account_cash_ledger.<account>.db`, WAL mode for concurrent
  readers/writers from the 104 batch process and the crypto 24/7 loop) with
  a single-writer-transaction reserve/release protocol:
  - `reserve(sleeve_tag, parent_intent_id, amount) -> bool`: atomically
    checks `broker_cash - SUM(all active reservations across all tags) -
    amount >= 0` and, if true, inserts the reservation row in the SAME
    transaction; returns `False` (reservation refused) on insufficient
    headroom — the caller's order placement must not proceed. This is the
    ONLY path either sleeve may size a buy against; `OrderStateBook.
    reserved_cash()` becomes a PER-TAG diagnostic view, no longer the
    headroom source of truth.
  - `release(parent_intent_id)`: called on fill/cancel/reject, in the same
    transaction as the state-machine transition that already handles that
    event — a reservation that's never released on every terminal path is
    the fail mode this ledger exists to prevent, so release is wired into
    the SAME lifecycle hooks `OrderStateBook` already has for fill/cancel/
    reject, not a separate cleanup pass.
  - `broker_cash` is re-fetched from the broker (not cached) at the START of
    each `reserve()` transaction, so a real balance change (a fill on either
    sleeve) is visible to the next reservation attempt from EITHER sleeve.
  - **Ledger reconciliation (orphan sweep)**: every sleeve's existing
    reconcile-before-emit step additionally reconciles the ledger — an
    ACTIVE reservation whose `parent_intent_id` has no corresponding broker
    open order AND no in-flight local lifecycle state is an ORPHAN (crashed
    process between reserve and submit, or a missed release): it is
    released, counted, and alerted. Orphaned-reservation count > 0 is a
    reportable defect (it means a lifecycle hook missed a terminal path);
    sustained orphans are a Tier-1 halt for the sleeve producing them.
    Inversely, a broker open buy order with NO ledger reservation is the
    graver defect (headroom leak — some path submitted without reserving)
    and halts that sleeve's entries immediately.
  - Both 104's existing sizing path and the new crypto sizing path (D-C4)
    call `reserve()` before submitting any buy order; a `False` return is
    treated as `insufficient_buying_power_headroom` (the existing
    `EntryDecision` reason string, `:470` — reused, not duplicated) and the
    order is not placed, exactly like today's per-book headroom check, only
    now consulting a shared account-level source of truth instead of a
    per-tag local one.
  - **Alternative considered — broker-side segregated sub-account**: Alpaca
    does not expose sub-accounts for a single retail account (verified
    against the SDK surface cited in §2.7 — no segregation/sub-account
    endpoint exists in `alpaca-py` 0.43.4's `TradingClient`); this option is
    not available and is dropped, not merely deprioritized.
  - This ledger is D-C4 scope (renquant-execution), landing BEFORE the
    crypto order-validation seam goes live, and 104's existing sizing path
    gains exactly one new call (`reserve()`) — a small, testable change, not
    the "NO change" the original proposal claimed.
- **Blast radius**: worst-case total loss of the sleeve = 9–19% of the account
  — bounded by construction (the HARD sleeve budget cap, now enforced via the
  reservation ledger rather than a locally-checked soft view), before any
  rail fires.

### 5.4 Halts (most-restrictive-wins, entries only — exits always allowed)

kill-switch file/env · sleeve drawdown halt (sticky) · reconciliation mismatch ·
missing protective stop · stale data (last daily bar > 26h old, or class-D quote
staleness per tick) · budget cap reached. All six bind entries only; none may
ever block a protective exit (the 105 §10 precedence rule carries over
verbatim).

---

## 6. Staged rollout (each stage gated; capital steps = operator sign-off)

| Stage | What runs | Gate to advance | Est. duration |
|---|---|---|---|
| **0 — Prereqs + paper battery** | Operator enables crypto agreement (live + paper); `crypto_status==ACTIVE` recorded; paper battery verifies EMPIRICALLY: pair list + increments snapshot, GTC/IOC acceptance, **GTC stop_limit acceptance per pair**, fee schedule from fill receipts, non-marginable BP behavior; data backfill + two-source parity | All [GUESS] rows of §2.7 converted to [VERIFIED] in a recorded battery report | ~1 week |
| **1 — Shadow 24/7** | Scheduler in shadow (no orders, `assert_shadow_never_submits`); full decisions logged; model trained + WF-gated (net-of-fees + BTC baseline) in parallel; Codex adversarial review of model card | ≥ 14 consecutive clean shadow days incl. 2 weekends; replay audit green; model promoted through the 3-tier gate | 2–3 weeks |
| **2 — $500 canary** | Live entries, allowlist = BTC/USD + ETH/USD + top-3 liquidity; loss budget $75 sticky; all §5 rails armed; broker stops verified live on first fill | ≥ 2 weeks incl. 2 full weekends, zero Tier-1 defects, realized fees within battery estimate; **operator sign-off** | 2+ weeks |
| **3 — Sleeve full** | $1–2k (operator sets number), full ~20-pair universe | **Operator sign-off**; thereafter monthly review vs BTC baseline; persistent underperformance net of fees = wind-down trigger | ongoing |

Rollback at every stage: kill switch → cancel non-protective orders → exits per
rails → stage frozen pending review. No stage may be skipped; no capital step
without the operator.

---

## 7. Deliverables (repo-correct PR list)

Merge order top-to-bottom; orchestrator flips last and stays default-OFF until
everything above is merged AND pinned (105 §8 pattern).

| ID | Repo | Deliverable | Size |
|---|---|---|---|
| D-C1 | renquant-common | ALWAYS_OPEN calendar mode in `market_calendar` + `pair_slug` symbol helper (M2, P9/B5) | M |
| D-C2 | renquant-base-data | Crypto bars ingestion (daily+intraday, v1beta3) + slug store + manifests (`asset_class:"crypto"`) + yfinance cross-check job (B1/B2/B3/B6) | M |
| D-C3 | renquant-base-data | Crypto panel builder: price/volume alpha158 subset + crypto-native features + h=20 calendar-day label sidecar (B4/B7, §4.2–4.3) | M |
| D-C4 | renquant-execution | Account-scoped cash reservation ledger (§5.3 CORRECTED — touches 104's existing sizing path with one new `reserve()` call); crypto order validation: asset-class classifier, GTC/IOC TIF policy, no-short assert, increment/min-notional snapshot enforcement, fee model, DAY-sweep exclusion + resting-age watchdog, reconciliation asset-class fix (E1–E7, E9–E11) | L |
| D-C5 | renquant-execution | Crypto GTC stop-limit protective path, fractional qty + cancel/replace + missing-stop Tier-1 check (E8, §5.1) | M |
| D-C6 | renquant-pipeline | `asset_class` config field + calendar-mode threading: freshness, hold clocks, settlement=0, annualization 365 (P1–P4, P11) | L |
| D-C7 | renquant-pipeline | Asset-class gate bypasses: wash-sale (+QP mask), fundamentals, sector/SPY gates; crypto σ-clip + vol-target params; equity behavior byte-identical tests (P5, P7, P8, P10) | M |
| D-C8a | renquant-model-common (shared) | Generic net-of-cost accounting primitive: fees/spread-slippage/increment-rounding/rejected-order cost model, consumed identically by replay and runtime (M1, §4.4 CORRECTED) — asset-agnostic, no crypto-specific logic | M |
| D-C8b | renquant-model | Crypto net-of-cost WF evaluation (consumes D-C8a) + BTC-baseline comparison + crypto promotion decision in the gate harness — asset-specific, not shared code (M1, §4.4) | M |
| D-C9 | renquant-model | Crypto XGB panel training config + model card + artifact publication (§4) | M |
| D-C10 | NEW repo `renquant-strategy-crypto` | Scaffold: configs (active/golden/shadow), validator, drift detector, universe+increment snapshot, sleeve budget cap, risk rails, stop policy (§3.1) | M |
| D-C11 | renquant-orchestrator | 24/7 crypto session scheduler (fork of 105 bones): always-open sessions, frozen leakage-proof session contract (watermark + quiet window + signal_snapshot_digest, §3.5), kill switch + env flag, ntfy topic, run bundles, launchd KeepAlive ops, liveness (§3.5, §5.2) | L |
| D-C12 | renquant-orchestrator | Stage-0 paper battery runner + report format; Stage-1 shadow replay audit for crypto sessions (§6) | M |
| D-C13 | renquant-artifacts | Crypto model registry entry + promotion contract (consumes existing schema) | S |

Every PR: own progress doc, Codex review, never self-merge — unchanged rules.

---

## 8. Explicit non-goals

- **No perpetuals/futures/derivatives** — `AssetClass.CRYPTO_PERP` exists in the
  SDK (`trading/enums.py:186`) and is explicitly out of scope.
- **No margin, no shorting, no leverage** — long-only spot, 1× cash.
- **No cross-exchange anything** — Alpaca custody only; no wallets, no
  transfers, no arbitrage, no on-chain data in v1.
- **No behavior change to equity strategies' decisions** — every pipeline
  change is bypass-by-asset-class with equity-path byte-identical tests;
  separate state/DB/ntfy/kill-switch. ONE exception, load-bearing not
  incidental: 104's sizing path gains a single new call into the shared
  `AccountCashLedger.reserve()` (§5.3 CORRECTED) — this is REQUIRED for
  crypto to safely share the account's cash, not an optional touch; it is
  tested to be a no-op headroom-wise for 104 when the crypto sleeve is
  disabled (ledger with zero crypto reservations reduces to the existing
  per-book check byte-for-byte).
- **No cash-drag lane coupling** — this RFC does not touch the Deployment
  Governor / D6 protocol / shadow-AB lanes, and its implementation PRs may not
  either.
- **No intraday re-scoring in v1** — daily frozen signal + intraday timing/risk
  only (the 105 Stage-1/Stage-3 boundary).
- **No day-trading mandate** — h=20d holding intent; the 24/7 loop exists for
  timing + risk latency, not churn (fee model punishes churn by design).
- **No wash-sale engine changes for equities** — the crypto bypass is keyed on
  asset class; §1091 handling for equities is untouched.

---

## 9. Resolved design questions (Codex review, 2026-07-10 — no longer open)

The three questions this section originally posed are now FROZEN decisions,
not open questions, per Codex's first review round:

1. **Leakage-proof session contract (§3.5)**: RESOLVED — not just "a clock
   boundary," but the full frozen contract in §3.5 (exact watermark, a
   `[D 00:00, D 00:15)` UTC quiet interval, an immutable
   `signal_snapshot_digest` reusing the D6-§2a decision-snapshot pattern,
   fail-closed entries with no stale-signal fallback, per-tick bundle
   persistence). See §3.5 for the full mechanism — it is no longer a design
   question but a specified contract an implementation PR must satisfy
   exactly.
2. **Label benchmark (§4.3)**: RESOLVED — raw 20-day forward return is the
   FROZEN primary label, decided before any WF evidence; BTC-excess is a
   pre-registered diagnostic only, never a post-hoc substitute. See §4.3.
3. **Fee-aware gate placement (§4.4, D-C8)**: RESOLVED — split, per Codex's
   explicit instruction: generic net-of-cost evaluation PRIMITIVES (the fee/
   slippage/rounding/rejected-order cost-accounting math itself) live in
   shared `renquant-model`-common code so equities inherit them for free
   later without an asset-specific gate in shared code; the BTC-baseline
   comparison and the crypto promotion DECISION stay entirely in
   `renquant-model`, asset-specific and never in the shared common path. See
   the revised D-C8a/D-C8b split in §7 and §4.4.
