# RS-3: Data-vendor stack recommendation memo

DATE: 2026-07-04
STATUS: PRELIMINARY SCREEN + VALIDATION PLAN (delegated research per #230 §1;
        spend decision DEFERRED until probe results confirm the stack satisfies contracts)
BLOCKS: N2 (PIT revision accrual), N3 (FMP quarterly depth), M-SIG (signal substrate),
        M8 (universe expansion)

**Probe executed — see PR #348** (`doc/research/2026-07-04-rs3-probe-results.md`).
This memo is the probe DESIGN; #348 is the executed RESULTS. Outcome: **T1
(Polygon cost) downgraded to HIGH-RISK / UNVERIFIED** — the public evidence is
genuinely conflicting (one round of research found ~$99/mo for the Financials
add-on; a separate fresh re-check surfaced a competing, unofficial ~$29/mo
claim) and non-official (Polygon/Massive's real pricing page is a JS-rendered
SPA with no scrapable content or documented public pricing API — confirmed
independently twice). Neither number is acceptance-test-grade confirmed, so
this is NOT a falsification of Polygon on cost grounds — the cost boundary
this memo's Tier-1 pick assumed ($58/mo) is unconfirmed, not disproven.
**T5a/T5b/T7 PASSED** (FMP Starter analyst-consensus + target-history depth,
SEC EDGAR free raw PIT data — confirmed as a free PIT *source*, not proven
equivalent to Polygon's pre-parsed financials surface in concept normalization,
restatement handling, or coverage convenience). Recommendation revised to SEC
EDGAR harvester ($0, see PR #350) + FMP Starter (already subscribed) — chosen
on its own independently-confirmed merits, not because Polygon was ruled out.
The Bottom line / §3 Tier-1 pick below reflects the PRE-probe preliminary
screen and is superseded by that outcome — kept here for the audit trail of
what the screen assumed before validation, not as the current recommendation.

---

## Bottom line

**Preliminary recommendation (CONDITIONAL on validation probe passing): FMP Starter
(keep) + Polygon.io Fundamentals add-on ($29/mo) + SEC EDGAR XBRL (free).** Total
incremental spend: $29/month. This is the lowest-cost combination that CLAIMS
point-in-time capability via `filing_date` timestamps. However, the recommendation
is NOT yet economically verified — the probe in §5 must confirm: (a) Polygon's
base-plan dependency and real total cost, (b) PIT fidelity under restatements on our
actual ticker set, (c) analyst-consensus coverage at the depth M-SIG needs.
**Spend decision deferred until probe results are in.**

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

## 6. Validation probe (required before spend decision)

The vendor comparison above is a feature-matrix screen from docs and web research.
Before recommending spend, the following concrete acceptance tests must PASS on our
actual ticker set. Each test has a falsification criterion.

### 6.1 Probe design

**Sample tickers** (10 names spanning our watchlist + M8 candidates):
AAPL, GRMN, MU, OXY, AMZN (watchlist); COST, LLY, AVGO, URI, WM (M8 candidates)

**Sample filing dates** (known 10-Q/10-K filing dates from SEC EDGAR, pre-verified):
- AAPL 10-Q filed 2025-01-31 (FQ1 2025)
- MU 10-Q filed 2025-03-20 (FQ2 2025)
- OXY 10-K filed 2025-02-21 (FY 2024)

**Fields to validate**: revenue, net_income, eps_diluted, total_assets, filing_date

### 6.1a T3 fixture set (concrete, reproducible — not a hypothetical case)

Queried `data.sec.gov/submissions/CIK{cik}.json` for every ticker in the live
104 watchlist (142 names, from `strategy_config.json`'s `watchlist` field,
136/142 resolvable to a CIK via `sec.gov/files/company_tickers.json`) for any
`10-Q/A` or `10-K/A` filing in their recent-filings history. **53 amendment
filings found across the real watchlist.** Five selected, favoring recency,
ticker diversity, and excluding a routine incorporate-by-reference amendment:

| Ticker | Form | Period (original) | Amendment filed | Accession # |
|---|---|---|---|---|
| CVX | 10-Q/A | 2022-03-31 | 2022-05-04 | 0000093410-22-000028 |
| KO | 10-Q/A | 2024-03-29 | 2024-05-30 | 0000021344-24-000019 |
| GLD | 10-K/A | 2024-09-30 | 2024-12-19 | 0001437749-24-037938 |
| GRMN | 10-K/A | 2023-12-30 | 2024-11-29 | 0000950170-24-131914 |
| DUK | 10-Q/A | 2020-03-31 | 2020-06-02 | 0001326160-20-000172 |

(MO has a 10-K/A filed in every one of the last 9 years, always ~5 months
after the original 10-K — almost certainly a routine Part III proxy-
incorporation amendment, not a financial restatement. Excluded from the
probe sample for that reason.)

**What to compare, per (ticker, original period) pair**: pull Polygon's
`/vX/reference/financials` filtered to that `period_of_report_date`; check
whether Polygon returns **one** record (latest/restated values only) or
**two distinct timestamped records** (original-as-filed + amended, each
under its own `filing_date`); compare both `filing_date` values against the
EDGAR ground truth above.

**PASS** (per ticker): Polygon exposes the original-filing values under the
original `filing_date` AND the amendment's corrected values under the later
`filing_date` — a backtest run "as of" any date between the two filings
would see the pre-amendment numbers. **FAIL**: Polygon returns only one
record per period (silently the latest/restated values), which means a
backtest run before the amendment date would see look-ahead-biased numbers.
**Falsification of Polygon as Tier-1**: 3 or more of the 5 tickers FAIL.

### 6.2 Acceptance tests

| Test | Method | Pass criterion | Falsifies |
|---|---|---|---|
| **T1: Polygon cost verification** | Visit polygon.io/pricing (JS-rendered, not directly scrapable — fall back to cross-referencing comparison articles + Polygon's own changelog posts); zero-cost, no signup required | True incremental cost confirmed ≤$35/mo with NO base subscription required, OR base + add-on total confirmed | "Total $58/mo" claim |
| **T2: Polygon PIT fidelity** | Query Polygon `/vX/reference/financials` for the 3 sample filings; compare `filing_date` field against SEC EDGAR actual filing date | All 3 `filing_date` values match EDGAR ±1 day | Polygon as PIT source |
| **T3: Polygon restatement handling** | Concrete fixture set (see §6.1a) — 5 real restatement events found via SEC EDGAR's public submissions API on our actual watchlist. For each, compare Polygon's `/vX/reference/financials` response for that `period_of_report_date` against EDGAR ground truth | See §6.1a pass/fail criteria | PIT fidelity under restatements |
| **T4: Polygon quarterly depth** | Query all 10 sample tickers for quarterly financials going back 5 years | ≥8/10 tickers have ≥16 quarters of data (4y) with `filing_date` populated | Quarterly depth claim |
| **T5a: Recommendation-change history** | Query FMP `/api/v3/grade/<ticker>` for the 10 sample tickers; verify historical revision timeline depth | ≥8/10 tickers have ≥2 years of monthly grade history with analyst counts | N3/M-SIG recommendation-revision need |
| **T5b: Price-target history** | Query FMP `stable/price-target-news?symbol=<ticker>` for the 10 sample tickers; verify per-event historical depth (this is a distinct endpoint from `grade` — event-level target changes with `publishedDate`/`priceTarget`/`analystCompany`, confirmed live under our existing free-tier key this round: AAPL returned 100 events back to 2024-08, GRMN 21 events back to 2022-02) | ≥8/10 tickers have ≥2 years of price-target-change events | N3/M-SIG target-revision need |
| **T6: Universe breadth** | Query Polygon for total US tickers with quarterly financals available | ≥3,000 tickers with ≥8 quarters available | M8 expansion coverage |
| **T7: SEC EDGAR cross-check** | For the 3 sample filings, compare Polygon revenue/EPS against raw EDGAR XBRL `us-gaap:Revenues`/`us-gaap:EarningsPerShareDiluted` | All values match within rounding ($1 / $0.01) | Polygon data accuracy |

### 6.3 Probe execution plan

Two cost tiers among these tests, not one uniform "zero cost" probe:

1. **T1, T5a, T5b, T7 are zero-cost** — T1 via web research (comparison
   articles + Polygon's changelog, no signup/payment); T5a/T5b via our
   existing, already-subscribed FMP key; T7 via SEC EDGAR's free public API.
   These four can run without any spend decision or paid-tier access.
2. **T2, T3, T4, T6 require a live Polygon API call under the paid Financials
   tier being evaluated** — public API docs/blog claims are useful for feature
   discovery only and do NOT establish live entitlement, real endpoint
   behavior, or actual per-ticker coverage; none of T2/T3/T4/T6 should be
   marked passed from documentation alone, and none can be run without first
   approving that spend.
3. **Sequencing matters**: run the zero-cost tests (1) FIRST. T1 alone can
   falsify the Tier-1 recommendation on cost grounds before any paid-tier
   spend is needed for T2/T3/T4/T6 — do not approve the paid tier before T1
   clears.
4. **Executed outcome (PR #348, 2026-07-04, revised 2026-07-05)**: T1 was
   downgraded to HIGH-RISK / UNVERIFIED at the zero-cost stage — the public
   cost evidence is conflicting (~$99/mo per one round of research vs. a
   competing, unofficial ~$29/mo per a later re-check) and neither source is
   official (see PR #348's results doc for the full evidence table). This is
   not a confirmed falsification, but the evidence quality is too weak to
   authorize paid-tier spend on. Because T1 did not clear, T2/T3/T4/T6 were
   never run and no paid-tier spend was ever needed or requested — this is
   the "T1 inconclusive → do not escalate to paid tier" path under case 5
   below. T5a/T5b/T7 (also zero-cost) independently PASSED, confirming FMP
   Starter + SEC EDGAR jointly satisfy the analyst-consensus and PIT needs
   without needing Polygon resolved either way.
5. **T1 inconclusive (HIGH-RISK/UNVERIFIED)** → Polygon's real cost cannot be
   confirmed from public information → do not approve paid-tier spend without
   an official quote; re-evaluate Tier-1 pick using only what the zero-cost
   tests confirm (§ Executed outcome) rather than either the original $58/mo
   assumption or a stronger "disqualified" claim neither side of the evidence
   actually proves.
6. Had T1 passed: **Pass all 8 (T1-T4, T5a, T5b, T6, T7)** → recommendation
   upgrades to CONFIRMED; operator approves $29/mo. **Fail T2/T3/T4** →
   Polygon is NOT viable for PIT; escalate to Sharadar SF1 (Tier 2 probe
   required). **Fail T5a** → recommendation-history insufficient; investigate
   FMP Premium. **Fail T5b** → target-history insufficient; investigate
   Polygon/Benzinga analyst endpoints as an alternative target-history source.
   (Moot given T1's outcome, kept for completeness / future re-runs against a
   different Tier-1 candidate.)

### 6.4 Falsification: what kills the Tier-1 recommendation

- Polygon requires a $99/mo+ base subscription → cost exceeds budget threshold
- `filing_date` field is not truly PIT (overwrites on restatement) → need Sharadar
- Quarterly depth < 3 years → insufficient for WF backtesting window
- Recommendation-change OR price-target-change timeline < 1 year → M-SIG C2
  feature cannot be constructed for that dimension

## 7. Open questions (pending probe)

1. **Polygon base-plan dependency**: unverified whether the $29/mo Fundamentals
   add-on is standalone or requires a Stocks subscription ($29–99/mo).
2. **Restatement handling**: critical for PIT fidelity — does Polygon preserve
   original-as-filed data or overwrite with restated figures?
3. **Sharadar SF1 pricing**: behind login wall (~$150–500/yr unverified).
4. **Tiingo PIT capability**: "as reported" SEC data may or may not provide
   adequate `filing_date` granularity — lower priority probe.

## 8. Decision needed from operator

**Superseded by PR #348's executed results** — the zero-cost portion of this
probe (T1, T5a, T5b, T7) has already run (no operator approval was needed,
since none of those four tests touch a paid tier). T1 is HIGH-RISK/UNVERIFIED,
not FAILED: Polygon's real cost cannot be confirmed either way from public
sources (conflicting ~$99/mo vs. ~$29/mo third-party claims, no official
pricing page access), so the paid-tier tests (T2/T3/T4/T6) were never
triggered and no Polygon spend was ever requested. The decision the operator
actually needs now (see PR #350) rests on T5a/T5b/T7's independently
CONFIRMED PASS, not on Polygon being ruled out:

- [ ] Approve the SEC EDGAR XBRL harvester engineering effort ($0 spend,
      `renquant-base-data`) as the N2/M-SIG PIT source, per PR #348's revised
      recommendation — justified by SEC EDGAR + FMP Starter's own confirmed
      results, independent of Polygon's unresolved status
- [ ] Sharadar SF1: want me to get the real price? (Tier 2 contingency, only
      if the EDGAR concept-mapping engineering proves too costly)
- [ ] Polygon: NOT requested at this time — cost remains unverified, not
      disqualified; would require an official quote (sales contact or a live
      trial checkout page) to resolve if reconsidered later

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
