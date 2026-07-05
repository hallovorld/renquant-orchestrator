# RS-3: Data-vendor stack memo

DATE: 2026-07-05
STATUS: RECOMMENDATION (per master plan §1, RS-3)
AC: subscription list + monthly total + per-item roadmap mapping

---

## 1. Current state

| Source | Plan | Cost | Provides | Coverage gaps |
|---|---|---|---|---|
| **FMP** | Starter ($29/mo) | $29 | Key metrics, 10y analyst estimates, income/balance/CF, ratios, 5y history, 300 req/min, 20GB/mo | No PIT revision timestamps; no historical constituent membership; no tick/intraday |
| **Finnhub** | Free | $0 | Real-time US quotes, company news, basic fundamentals, SEC filings, 60 req/min | ~4-month daily OHLCV history; limited fundamental depth; no survivorship-bias-free history |
| **IEX** | Via Alpaca (free) | $0 | Real-time quotes, 5y daily OHLCV, basic fundamentals | IEX-only tape (documented bias vs SIP); no analyst consensus; no PIT; no small/mid membership |

**Total current: $29/mo.** Adequate for 104's current 145-name large-cap universe with
batch daily decisions. Insufficient for M-SIG (needs PIT revision stream + analyst
consensus history), M7/M8 (needs survivorship-free small/mid constituent data), and
S10 (needs tick-level or 1-min intraday for IS measurement).

---

## 2. Vendor comparison matrix

Rating: ● = strong / ◐ = partial / ○ = absent or weak

| Dimension | FMP Starter | FMP Enterprise | Polygon Stocks Adv | Sharadar (Nasdaq DL) | Norgate Platinum | Finnhub Premium |
|---|---|---|---|---|---|---|
| **PIT fundamentals** | ○ point-in-time absent; snapshots only | ○ same | ○ no fundamentals | ● 20+ yr PIT quarterly; as-reported + restated | ◐ quarterly fundamentals; no as-reported | ◐ basic financials; no formal PIT |
| **Analyst consensus** | ● ratings + targets + estimates (10y) | ● same + bulk | ○ none | ○ none | ○ none | ● consensus + surprises + revisions |
| **Historical depth** | ◐ 5y daily; 30y annual fundamentals | ● 30y+ daily | ● 15y+ daily/minute | ● 20y+ daily; 20y fundamentals | ● 30y+; survivorship-free | ◐ varies by tier |
| **Small/mid coverage** | ● full US exchange (14k+) | ● same | ● full US SIP | ● ~14k US equities | ● full US; 10k+ delisted | ● 60k+ global |
| **Survivorship-free** | ○ no delisted | ○ no delisted | ○ no delisted | ● includes delisted | ● historical constituents + delisted | ○ no delisted |
| **Intraday/tick** | ○ none | ◐ 1-min (limited) | ● full SIP tick + 1-min | ○ EOD only | ○ EOD only (desktop delivery) | ◐ real-time quotes only |
| **API rate limits** | 300/min | 750/min | unlimited (paid) | bulk download (no rate limit) | desktop app (no API) | 300/min (est.) |
| **Monthly cost** | $29 | ~$79–149 | $199 ($159 annual) | ~$50–100 (per-dataset) | ~$66 (Platinum annual) | $50–100 |
| **Delivery** | REST API | REST API | REST API + WebSocket | bulk CSV/API via Nasdaq DL | desktop app + Python API | REST API + WebSocket |

**Key insight:** No single vendor covers all dimensions. The binding gaps:
- **PIT revision history** → only Sharadar provides true as-reported PIT
- **Survivorship + constituent history** → Sharadar or Norgate (M7/M8 critical)
- **Analyst consensus history** → FMP (already have) or Finnhub Premium
- **Intraday** → Polygon (but deferred per operator ATP decision)

---

## 3. Roadmap mapping

| Task | Data need | Best vendor | Fallback | Status |
|---|---|---|---|---|
| **N2** PIT revision accrual | Daily PIT fundamental snapshots with `available_at` | FMP Starter (current — snapshot-based, not true PIT) | Sharadar (true PIT) or SEC EDGAR raw (free, parsing cost) | ACTIVE — snapshotter running |
| **N3** FMP harvest | 5y analyst estimates + fundamentals | FMP Starter (current) | Finnhub Premium | ACTIVE — harvest running |
| **M-SIG** signal stack | Revision deltas (signal #1), quality metrics (signal #2), momentum (signal #3) | FMP (revisions via estimate diff) + price data (existing) | Sharadar (true revision history via as-reported diffs) | BLOCKED on S5/S8 |
| **M7** down-cap screen | Survivorship-free small/mid OHLCV + fundamentals + constituent history | Norgate Platinum or Sharadar | Build from SEC + exchange lists (months of work) | NOT STARTED |
| **M8** cluster-wave 1 | Expanded universe fundamentals + prices | FMP Starter (covers 14k+ names) | — | BLOCKED on M7 |
| **S10** IS study extension | Intraday 1-min or tick for fill analysis | Polygon Stocks Advanced | IEX via Alpaca (biased) | DEFERRED (ATP $99 → operator cost pushback) |

---

## 4. Recommended stack

### Tier 1: Current (no new spend)

| Vendor | Plan | Cost | Serves |
|---|---|---|---|
| FMP | Starter | $29/mo | N2 (snapshot PIT), N3 (analyst+fundamentals), M-SIG (revision proxy), M8 (universe prices) |
| Finnhub | Free | $0 | Real-time quotes, news, SEC filings |
| IEX/Alpaca | Free | $0 | Live trading quotes, 5y OHLCV |

**Total: $29/mo.** Sufficient for NOW + most SHORT tasks.

### Tier 2: Add for MID tasks (recommended, needs operator approval)

| Vendor | Plan | Cost | Serves | When needed |
|---|---|---|---|---|
| Norgate | Platinum (annual) | ~$66/mo ($788/yr) | M7 down-cap screen (survivorship-free 30y + delisted + historical constituents) | Before M7 starts (Aug–Sep target) |

**Total: $95/mo.** Norgate is the only vendor providing survivorship-bias-free
constituent history — mandatory for honest M7/M8 backtests. Sharadar is an
alternative (~$50–100/mo via Nasdaq Data Link) but Norgate's desktop delivery +
Python API (`norgatedata`) is better documented for systematic backtesting.

### Tier 3: Add for advanced tasks (deferred)

| Vendor | Plan | Cost | Serves | When needed |
|---|---|---|---|---|
| Polygon | Stocks Advanced | $199/mo ($159 annual) | S10 intraday IS study (full SIP tick data) | If S10 shows material edge (P ≈ 0.65) |
| Sharadar | Core Fundamentals | ~$50–100/mo | True PIT as-reported history (upgrade N2 from snapshot to genuine PIT) | If M-SIG revision signal shows promise and needs deeper history |

**Total if all: $295–345/mo.** Only add after gated evidence (S10 materiality,
M-SIG signal IC).

---

## 5. Decision status

| Item | Authorization | Action |
|---|---|---|
| FMP Starter $29/mo | ✅ AUTHORIZED + SUBSCRIBED | Running (key-metrics + 10y estimates verified) |
| Finnhub free | ✅ No spend | Running |
| IEX via Alpaca | ✅ No spend | Running (IEX bias documented + accepted) |
| Norgate Platinum ~$66/mo | ❓ NEEDS APPROVAL | Recommended for M7; defer until M7 starts |
| Polygon $199/mo (ATP) | ❌ DEFERRED | Operator cost pushback (2026-07-02); re-trigger at M2 canary or book scale-up |
| Sharadar ~$50–100/mo | ❓ NEEDS APPROVAL | Only if M-SIG revision signal demands true PIT history |

**Bottom line:** Current $29/mo stack covers NOW + SHORT. The only new spend
recommended before August is Norgate Platinum ($66/mo) for M7 — but only when M7
actually starts. Everything else is gated on evidence from tasks not yet ready.

---

Sources:
- [Polygon.io Pricing](https://polygon.io/pricing)
- [Norgate Data Subscription](https://norgatedata.com/prices.php)
- [Norgate Stock Market Packages](https://norgatedata.com/stockmarketpackages.php)
- [FMP Pricing Plans](https://site.financialmodelingprep.com/pricing-plans)
- [Finnhub Pricing](https://finnhub.io/pricing)
- [Nasdaq Data Link / Sharadar](https://data.nasdaq.com/databases/SF1)
