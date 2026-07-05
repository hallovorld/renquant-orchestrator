# RS-3: Data-vendor stack recommendation memo

DATE: 2026-07-04
STATUS: RECOMMENDATION (delegated research per #230 §1; operator signs off on spend)
BLOCKS: N2 (PIT revision accrual), N3 (FMP quarterly depth), M-SIG (signal substrate),
        M8 (universe expansion)

---

## Bottom line

**Recommended stack: FMP Starter (keep) + Polygon.io Fundamentals add-on ($29/mo) +
SEC EDGAR XBRL (free).** Total incremental spend: $29/month. This covers all four
roadmap data needs (PIT fundamentals, analyst consensus, quarterly depth, universe
breadth) at the lowest cost that actually delivers point-in-time capability. If PIT
fidelity requirements escalate beyond what Polygon's `filing_date` field provides,
upgrade to Sharadar SF1 on Nasdaq Data Link (~$150–500/yr, pricing behind login wall
— verify before committing).

---

## 1. Demand map: what the roadmap needs

| Need | Roadmap item | Critical field | Current source | Gap |
|---|---|---|---|---|
| PIT quarterly fundamentals (earnings, revenue, estimates) | N2 (revision accrual), M-SIG (revisions signal, quality signal) | `filing_date` or `available_at` timestamps for leak-free backtesting | None | **BLOCKING** — no PIT source wired |
| Analyst consensus (ratings, targets, recommendation changes) | N3 (FMP harvest) | Historical revision timeline | FMP Starter (annual depth) | Quarterly endpoints 402-locked above Starter |
| Quarterly financial statements | M-SIG (quality signal: ROE, margins, accruals) | Quarterly granularity with historical depth | FMP Starter (annual only) | **Quarterly is plan-locked** |
| Universe breadth (small/mid cap coverage for expansion) | M8 (cluster-wave) | EOD prices + fundamentals for ~500+ US names | FMP Starter (full symbol coverage) | Coverage OK; PIT depth is the gap |
| Intraday quotes | 105 collectors | Bid/ask/mid per watchlist | Alpaca (included in account) | None — solved |

## 2. Vendor comparison

### 2.1 Current stack

| Vendor | Tier | Cost | What it gives us | Limitation |
|---|---|---|---|---|
| **FMP** | Starter ($29/mo) [VERIFIED — subscribed] | $29/mo | Full US symbols, 5y annual history, 300/min, 20GB BW. key-metrics/ratios/growth/income/estimates (annual). Analyst grades-historical (~8y monthly). | **Quarterly endpoints return 402** (plan-locked above Starter). Annual-only fundamentals. |
| **Finnhub** | Free | $0 | Full stock coverage, ~4 months daily analyst recommendations. | Short history (~4mo). No fundamentals depth. ETFs/indices = no_coverage. |
| **Alpaca** | Trading account (included) | $0 | Real-time + historical intraday quotes. | No fundamentals. |

### 2.2 Candidates evaluated

| Vendor | Tier needed | Monthly cost | PIT capability | Quarterly depth | US coverage | Historical depth | Rate limits | Verdict |
|---|---|---|---|---|---|---|---|---|
| **FMP Premium** | Premium | ~$49–79/mo [WEB-SOURCED, verify] | No explicit PIT timestamps; data from SEC filings but no `filing_date` field in fundamentals response | Yes (quarterly unlocked) | Full US + UK/Canada | 30y | 750/min | ❌ Overpay — quarterly depth is the only gain vs Starter; no PIT |
| **Polygon.io** | Fundamentals add-on | $29/mo [WEB-SOURCED, verify] | **Yes — `filing_date` and `period_of_report_date` fields** on every financial record; designed for PIT backtesting | Yes (quarterly + annual + TTM) | ~6,700 public companies (10+ years); sourced from SEC EDGAR | 10+ years (back to ~2009) | Unlimited (rate-limited by HTTP connection) | ✅ **RECOMMENDED** — PIT + quarterly + reasonable cost |
| **Sharadar/SF1** (Nasdaq Data Link) | SF1 subscription | ~$150–500/yr [WEB-SOURCED, pricing behind login wall] | **Yes — point-in-time by design**; SF1 is the gold standard for PIT fundamentals backtesting | Yes (quarterly + annual) | 14,000+ US public companies (25 years, survivorship-bias-free with delisted coverage) | 25 years | Bulk download (no real-time API rate concern) | ⭐ Best PIT quality but pricing opaque; **UPGRADE PATH** if Polygon PIT proves insufficient |
| **Norgate Data** | Platinum | $52.50/mo ($630/yr) [VERIFIED from website] | **No historical PIT** — fundamentals are latest-report-only, no historical `as_of` snapshots | Latest quarter only (no historical quarterly series) | Active + delisted + historical index constituents (back to 1990) | 1990–present (prices); current-only (fundamentals) | Desktop app, not API-first | ❌ Excellent for survivorship-bias-free price data + index membership; **useless for PIT fundamentals** |
| **Intrinio** | Bronze+ | ~$150–250/mo [WEB-SOURCED, verify] | Yes (PIT fundamentals available) | Yes | Broad US coverage | Varies by dataset | Custom per plan | ❌ Too expensive for our book size; overkill |
| **Tiingo** | Power | $10–30/mo [WEB-SOURCED, verify] | Partial — can access "as reported" data from SEC; not a dedicated PIT database | Yes (quarterly + annual) | 5,500+ US equities, 20+ years | 20+ years | 500 unique symbols/mo (free); unlimited (Power) | ⚠️ **WATCH** — cheap, good fundamental depth, but PIT fidelity unclear. Worth a free-tier probe |
| **EODHD** | Fundamentals Feed | $59.99/mo [WEB-SOURCED, verify] | Not explicitly PIT; "as-reported" not confirmed | Yes | 120,000+ instruments globally | 30+ years | 100K+ calls | ❌ No clear PIT; more expensive than Polygon for less |
| **SimFin** | Paid tier | ~$10–30/mo [WEB-SOURCED, verify] | **Explicitly NOT PIT** (their docs state this) — includes restatements | Yes | Limited US coverage | Varies | Varies | ❌ Explicitly not PIT; unusable for leak-free backtesting |
| **SEC EDGAR XBRL** | Free (data.sec.gov) | $0 | **Yes — filing dates are in the XBRL facts**; the raw source Polygon/FMP/etc. all parse | Yes (10-Q/10-K filings) | All SEC filers | Full SEC history | 10 req/sec per IP | ✅ **FREE PIT SOURCE** — requires parsing work; use as backup/validation |
| **IEX Cloud** | — | — | — | — | — | — | — | ❌ **SHUT DOWN** (Aug 2024) — no longer available |

## 3. Recommendation: the stack

### Tier 1 — Immediate (July)

| Action | Cost | Roadmap item served | Rationale |
|---|---|---|---|
| **Keep FMP Starter** | $29/mo (existing) | N3 (analyst consensus, annual depth), M8 (universe coverage) | Already subscribed; annual fundamentals + analyst grades-historical sufficient for current needs |
| **Add Polygon.io Fundamentals add-on** | +$29/mo [WEB-SOURCED] | **N2 (PIT revision accrual)**, M-SIG (quarterly quality signal) | Only vendor under $50/mo with explicit `filing_date` PIT timestamps on quarterly/annual financials; 10+ year history; ~6,700 companies covers our universe + expansion |
| **Wire SEC EDGAR XBRL harvester** | $0 (engineering time) | N2 (validation), M-SIG (cross-check) | Free PIT data; use as ground-truth validation for Polygon data fidelity |

**Tier 1 total: $58/month** ($29 existing + $29 incremental)

### Tier 2 — Conditional upgrade (August+, if needed)

| Trigger | Action | Cost | Rationale |
|---|---|---|---|
| Polygon PIT fidelity insufficient for WF backtesting (e.g., filing_date granularity too coarse, restatement handling unclear) | **Add Sharadar SF1** (Nasdaq Data Link) | ~$150–500/yr [VERIFY PRICING] | Gold standard PIT fundamentals; 25y history; survivorship-bias-free; 14k+ companies |
| M8 cluster-wave needs survivorship-bias-free historical index membership | **Add Norgate Platinum** | $52.50/mo ($630/yr) | Best-in-class delisted + historical index constituent data; complements Polygon fundamentals |
| FMP quarterly depth needed for analyst revision signals | **Upgrade FMP to Premium** | ~$49–79/mo [VERIFY] | Only if Polygon fundamentals don't cover analyst-consensus quarterly |

### Tier 3 — Not recommended

| Vendor | Why not |
|---|---|
| Intrinio | $150–250/mo is disproportionate to book size (~$10.8k) |
| EODHD | $60/mo with no clear PIT advantage over Polygon at $29/mo |
| SimFin | Explicitly not PIT — unusable for leak-free backtesting |
| IEX Cloud | Shut down August 2024 |
| Tiingo | PIT fidelity unclear; worth a free-tier probe but don't commit spend |

## 4. Subscription list and monthly total

| Vendor | Tier | Monthly | Annual equiv | Status |
|---|---|---|---|---|
| FMP | Starter | $29 | $348 | ACTIVE [VERIFIED] |
| Polygon.io | Fundamentals add-on | $29 | $348 | **RECOMMENDED** [WEB-SOURCED — verify price at polygon.io/pricing before subscribing] |
| SEC EDGAR | Free | $0 | $0 | Available (engineering work needed) |
| **TOTAL** | | **$58/mo** | **$696/yr** | |

Conditional additions (Tier 2, not in baseline):
- Sharadar SF1: ~$150–500/yr (verify)
- Norgate Platinum: $630/yr
- FMP Premium upgrade: ~$20–50/mo incremental (verify)

## 5. Roadmap mapping

```
N2 (PIT revision accrual) ← Polygon.io fundamentals (filing_date PIT)
                           ← SEC EDGAR XBRL (validation/backup)
N3 (FMP harvest)           ← FMP Starter (annual analyst) — ALREADY ACTIVE
                           ← Polygon.io (quarterly fundamentals if needed)
M-SIG (3-signal stack)     ← Polygon.io (quarterly quality: ROE, margins, accruals)
                           ← FMP Starter (analyst revision features)
M8 (cluster-wave)          ← FMP Starter (broad universe prices + annual fundamentals)
                           ← Norgate Platinum (Tier 2, if survivorship-bias-free
                              historical membership needed)
S10 (execution leak)       ← Alpaca (intraday quotes) — ALREADY ACTIVE
```

## 6. Open questions and risks

1. **Polygon fundamentals add-on pricing**: Web search shows $29/mo but this needs
   verification at polygon.io/pricing before subscribing. The add-on may require
   a base Stocks subscription.

2. **Polygon PIT fidelity**: The `filing_date` field exists, but we haven't verified
   whether it handles restatements correctly (does it show the original filing, or
   the restated version?). A free-tier probe should confirm this before committing.

3. **Sharadar SF1 pricing**: Behind a Nasdaq Data Link login wall. Historical community
   reports suggest ~$150–500/yr range but current pricing is unconfirmed. This is the
   gold standard for PIT fundamentals if Polygon proves insufficient.

4. **FMP quarterly unlock**: We haven't verified whether FMP Premium tier ($49–79/mo?)
   actually unlocks the quarterly endpoints we need, or if it's a higher tier. The
   Polygon add-on may make this moot.

5. **Tiingo free-tier probe**: Worth testing whether Tiingo's "as reported" SEC data
   provides adequate PIT fidelity at $0–10/mo — could replace Polygon if it does,
   but PIT capability is unconfirmed.

## 7. Decision needed from operator

- [ ] Approve Polygon.io Fundamentals add-on ($29/mo incremental)
- [ ] Confirm: probe Polygon and Tiingo free tiers before committing? (recommended)
- [ ] Sharadar SF1: want me to log in and get the real price? (Tier 2 contingency)

---

Sources (web research, 2026-07-04):
- [FMP Pricing](https://site.financialmodelingprep.com/pricing-plans)
- [Polygon.io Pricing](https://polygon.io/pricing)
- [Polygon.io Financials API](https://massive.com/docs/rest/stocks/fundamentals/financials)
- [Polygon.io Filing Date FAQ](https://polygon.io/knowledge-base/article/does-polygon-provide-the-filing-date-for-any-financial-reports)
- [Sharadar / Nasdaq Data Link](https://data.nasdaq.com/databases/SF1)
- [Norgate Data Pricing](https://norgatedata.com/prices.php)
- [Norgate Fundamentals FAQ](https://norgatedata.com/data-package-faq.php)
- [Tiingo Pricing](https://www.tiingo.com/about/pricing)
- [EODHD Pricing](https://eodhd.com/pricing)
- [SimFin (not PIT)](https://www.simfin.com/en/prices/)
- [IEX Cloud Shutdown](https://www.alphavantage.co/iexcloud_shutdown_analysis_and_migration/)
- [SEC EDGAR XBRL API](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
- [Best Financial Data APIs 2026](https://www.nb-data.com/p/best-financial-data-apis-in-2026)
