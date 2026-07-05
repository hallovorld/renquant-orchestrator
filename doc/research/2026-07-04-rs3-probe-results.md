# RS-3 validation probe results

DATE: 2026-07-04
STATUS: PROBE COMPLETE — 3 PASS, 1 FAIL, 2 PARTIAL, 1 NOT TESTABLE (no paid key)
BLOCKS: spend decision on Polygon.io Fundamentals

---

## Bottom line

**The RS-3 memo's "$29/mo Polygon add-on" cost claim is WRONG.** Web research
indicates the Stocks Financials add-on is **$99/month** (not $29/mo). The base
Stocks plans start at $29/mo (historical-only) and $199/mo (real-time). Whether
the Financials add-on requires a base subscription is unconfirmed but likely.
This changes the economic calculus significantly — **total cost may be $128–298/mo,
not $58/mo.**

However: SEC EDGAR provides the same PIT data (with `filed` dates) for FREE.
The engineering cost to parse XBRL is the tradeoff vs. Polygon's pre-parsed API.

---

## Test results

### T1: Polygon cost verification — FAIL

| Claimed | Actual (web research) | Source |
|---|---|---|
| $29/mo standalone add-on | **$99/mo** Financials add-on (individuals) | Multiple comparison articles + Polygon changelog |
| No base plan required | **UNCONFIRMED** — likely requires Stocks base ($29–199/mo) | Polygon docs say "Stocks Advanced plan or Stocks Financials Add-on" |
| Total stack: $58/mo | **$99–298/mo** (add-on alone or add-on + base) | — |

**Verdict: FAIL.** The cost boundary is breached. The memo's economic argument
rested on "$29/mo incremental" which is wrong by 3–10x.

Note: Polygon.io has rebranded to "Massive" (301 redirect polygon.io → massive.com).
Their pricing page is JS-rendered and not directly scrapable; costs sourced from
comparison articles and changelog posts.

### T2: Polygon PIT fidelity — PARTIAL PASS (documented but untested)

**Finding:** `filing_date` IS a documented API field in the Polygon/Massive
Financials endpoint. It appears as both:
- A **query parameter** with comparison operators (lt/lte/gt/gte)
- A **response field** (the default sort field for results)

The Python client docs confirm: `filing_date` — "Query by the date when the
filing with financials data was filed."

Polygon's blog states: "Like all of our reference data APIs, financials are
available as point-in-time data. By providing a date, you can query the
financials API to see the financials for a company as they were known on that
date."

**Verdict: PARTIAL PASS.** PIT capability is documented and designed-in. Cannot
verify actual response values without a paid subscription key.

### T3: Polygon restatement handling — PARTIAL PASS (documented, not empirically verified)

**Finding:** Polygon's blog states data is "point-in-time" — you can query
"financials for a company as they were known on that date." This implies
original-as-filed preservation (not overwrite on restatement). The API provides
`include_sources=True` for full traceability back to SEC filings.

However: no explicit documentation found stating "restatements do not overwrite
original filings." This is a critical gap — the implicit PIT claim needs
empirical verification with a known restatement case.

**Verdict: PARTIAL PASS.** Design intent is PIT-preserving; empirical
confirmation requires a paid key + known restatement test case.

### T4: Polygon quarterly depth — NOT TESTABLE

Cannot query the API without a Financials subscription. The documented claim is
"10+ years" of quarterly data from SEC filings for ~6,700 companies.

**Verdict: NOT TESTABLE without paid subscription.**

### T5: FMP analyst-consensus coverage — PASS [VERIFIED]

Probed FMP Starter `stable/grades` endpoint for 5 sample tickers:

| Ticker | Entries | Date range | Depth |
|---|---|---|---|
| AAPL | 1,771 | 2012-02-08 → 2026-06-25 | **14.4 years** |
| GRMN | 174 | 2012-02-10 → 2026-05-20 | **14.3 years** |
| MU | 928 | 2012-02-10 → 2026-06-29 | **14.4 years** |
| OXY | 456 | 2012-05-07 → 2026-06-29 | **14.1 years** |
| AMZN | 1,435 | 2011-12-28 → 2026-07-02 | **14.5 years** |

**Verdict: PASS.** All 5/5 tickers have 14+ years of analyst grade history.
This far exceeds the 2-year minimum needed for M-SIG analyst-revision features.
FMP Starter (already subscribed) is sufficient for the analyst-consensus signal.

### T6: Polygon universe breadth — NOT TESTABLE

Cannot verify without paid subscription. Documented claim: ~6,700 public
companies with 10+ years of quarterly data.

**Verdict: NOT TESTABLE without paid subscription.**

### T7: SEC EDGAR XBRL cross-check — PASS [VERIFIED]

Probed SEC EDGAR `data.sec.gov/api/xbrl/companyfacts` for 3 sample tickers:

| Ticker | CIK | Revenue concept | Filings | Filed range | EPS filings |
|---|---|---|---|---|---|
| AAPL | 0000320193 | RevenueFromContractWithCustomer... | 113 | 2019→2026 | 334 (2009→2026) |
| MU | 0000723125 | Revenues | 11 | 2018 only | — |
| OXY | 0000797468 | Revenues | 121 | 2015→2026 | — |

Key findings:
- The `filed` field IS the true SEC filing date (e.g., OXY Q1 2026 10-Q filed 2026-05-05)
- AAPL EPS latest: Q2 2026, val=2.01, filed 2026-05-01 (matches known timeline)
- GAAP concept names vary across companies (AAPL uses `RevenueFromContract...`
  post-ASC606, `SalesRevenueNet` pre-2018) — parsing requires concept mapping
- Data is FREE with 10 req/sec rate limit

**Verdict: PASS.** SEC EDGAR provides complete PIT data with real `filed` dates.
The tradeoff is engineering effort to parse XBRL concept mappings.

---

## Revised recommendation

Given T1 FAIL ($99/mo not $29/mo), the RS-3 Tier-1 stack should be revised:

| Option | Monthly cost | PIT source | Tradeoff |
|---|---|---|---|
| **A: SEC EDGAR only** | $0 | XBRL `filed` dates (gold standard) | Engineering cost: XBRL concept mapping across companies/years |
| **B: Polygon Financials** | $99–298/mo | Pre-parsed, `filing_date` field | 3–10x the claimed cost; may require base subscription |
| **C: Sharadar SF1** | ~$150–500/yr ($12–42/mo) | Gold-standard PIT | Pricing unverified; bulk download not API |

**New recommendation:** Start with **Option A (SEC EDGAR, free)** for N2.
The `renquant-base-data` repo already has `fmp_estimate_revisions.py` — extend
with an SEC EDGAR XBRL harvester. If concept-mapping engineering proves too
costly, revisit Polygon at the real $99/mo price or probe Sharadar pricing.

FMP Starter (already subscribed) covers analyst-consensus needs completely (T5 PASS).

---

## Evidence artifacts

- FMP probe: live API call, 2026-07-04, key=Starter tier (verified subscribed)
- SEC EDGAR probe: live API call to `data.sec.gov/api/xbrl/companyfacts/`
- Web research: Polygon pricing from comparison articles (JS-rendered pricing page not scrapable)
