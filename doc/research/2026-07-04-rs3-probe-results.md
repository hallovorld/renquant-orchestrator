# RS-3 validation probe results

DATE: 2026-07-04
STATUS: PROBE COMPLETE — 3 PASS, 1 HIGH-RISK (unofficial sourcing), 2 PARTIAL, 1 NOT TESTABLE (no paid key)
BLOCKS: spend decision on Polygon.io Fundamentals

---

## Bottom line

**The RS-3 memo's "$29/mo Polygon add-on" cost claim cannot be confirmed either
way from official sources, and that unresolvability is itself the finding.**
Polygon/Massive's real pricing page is a JS-rendered SPA with no scrapable
content and no documented public pricing API — neither this round's web
research nor a fresh re-check (2026-07-05) could reach an authoritative price.
Third-party sources conflict: comparison articles and changelog posts point to
a **$99/month** Financials add-on (this round's original finding), while a
separate fresh search surfaced a competing claim of **$29/month** attributed to
the same product. Neither is an official checkout/plan-page citation, and no
source resolves whether a base Stocks subscription ($29–199/mo) is additionally
required. Given genuinely conflicting non-official evidence, T1 is downgraded
from FAIL to **HIGH-RISK / UNVERIFIED** — the cost boundary the RS-3 memo
depends on is not acceptance-test-grade confirmed in either direction, and the
prudent stance for a spend decision is to treat the original "$58/mo" figure as
unreliable pending an official quote (e.g. contacting Polygon sales/support, or
starting a trial and reading the live checkout page) rather than replacing it
with an equally unverified different number.

Separately, SEC EDGAR is confirmed (T7, live-verified) to provide free raw XBRL
facts with real `filed` dates — genuinely valuable as a free PIT **source**.
That is NOT the same claim as "the same PIT data" as Polygon: this probe did
not prove equivalence to Polygon's pre-parsed financials surface in concept
normalization (different XBRL tags for the same economic concept across
issuers/eras — see T7 detail below), restatement handling, or ticker-coverage
convenience. The real tradeoff is zero data cost vs. real engineering
complexity to build the parsing/normalization layer Polygon would otherwise
provide pre-built — exactly the gap `renquant-orchestrator#350` /
`renquant-base-data#40`'s SEC EDGAR harvester is being built to close.

---

## Test results

### T1: Polygon cost verification — HIGH-RISK / UNVERIFIED

| Claimed | Third-party research (conflicting) | Source |
|---|---|---|
| $29/mo standalone add-on | **$99/mo** Financials add-on (individuals) per one round of research | Multiple comparison articles + Polygon changelog |
| $29/mo standalone add-on | **$29/mo** per a separate, later re-check | Search-engine synthesis citing unspecified/indirect sources |
| No base plan required | **UNCONFIRMED** either way — possibly requires Stocks base ($29–199/mo) | Polygon docs say "Stocks Advanced plan or Stocks Financials Add-on" |
| Total stack: $58/mo | **UNVERIFIED** — could plausibly range $58–298/mo depending on which claim is true | — |

**Verdict: HIGH-RISK / UNVERIFIED, not FAIL.** Neither the original $99/mo
finding nor a fresh re-check's competing $29/mo claim traces to an official
Polygon/Massive pricing page, checkout flow, or documented pricing API — both
are third-party-sourced (comparison articles, changelog posts, indirect search
synthesis) and cannot be reconciled from public information. That the evidence
base produced two *different* numbers on two separate attempts is itself proof
this is not acceptance-test-grade evidence for a definitive verdict in either
direction. This does not clear Polygon's cost boundary — it means the boundary
is genuinely unknown pending an official quote, and the RS-3 memo's original
"$58/mo" figure should be treated as unconfirmed, not superseded by a different
unconfirmed number.

Note: Polygon.io has rebranded to "Massive" (301 redirect polygon.io → massive.com).
Their pricing page is JS-rendered and not directly scrapable — confirmed
independently twice (2026-07-04 and 2026-07-05 re-checks), including attempts
against the FAQ/knowledge-base and announcement-blog pages, none of which
exposed pricing text or embedded pricing JSON. No documented public pricing API
was found. Costs in the table above are sourced from comparison articles,
changelog posts, and indirect search-engine synthesis — none official.

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

**Verdict: PASS** for what was actually tested: SEC EDGAR provides free, raw
XBRL facts with real `filed` dates — a genuine PIT ground-truth source. This
does NOT establish equivalence to Polygon's pre-parsed financials surface —
concept mapping (the `RevenueFromContractWithCustomer...` vs `Revenues` vs
`SalesRevenueNet` variation observed above, across issuers and accounting eras)
must be built and maintained by the consumer, and restatement handling /
coverage convenience were not tested here at all. The tradeoff is real
engineering effort (concept-mapping + resumability + normalization), not a
free equivalent swap-in for Polygon's API.

---

## Revised recommendation

Given T1 is HIGH-RISK/UNVERIFIED (the claimed $58/mo cost boundary is not
confirmed by any official source, and third-party sourcing itself conflicts
between $29/mo and $99/mo), the RS-3 Tier-1 stack should not be selected on
the basis of an unresolved cost claim either way:

| Option | Monthly cost | PIT source | Tradeoff |
|---|---|---|---|
| **A: SEC EDGAR only** | $0 (verified, T7 PASS) | XBRL `filed` dates (gold standard) | Engineering cost: XBRL concept mapping across companies/years |
| **B: Polygon Financials** | UNVERIFIED — third-party sources conflict between $29–99/mo add-on, possibly + a $29–199/mo base plan | Pre-parsed, `filing_date` field (documented, T2/T3 not empirically tested) | Real cost unknown pending an official quote; may still be materially higher than assumed |
| **C: Sharadar SF1** | ~$150–500/yr ($12–42/mo) | Gold-standard PIT | Pricing unverified; bulk download not API |

**Recommendation: proceed with Option A (SEC EDGAR, free and independently
verified) for N2** — not because Option B is proven too expensive, but because
Option A's cost ($0) and PIT capability (T7 PASS) are the only ones actually
confirmed this round, while Option B's economics remain genuinely unresolved.
The `renquant-base-data` repo already has `fmp_estimate_revisions.py` as a
precedent pattern — extended with an SEC EDGAR XBRL harvester
(`renquant-orchestrator#350` / `renquant-base-data#40`). If a future need
arises to revisit Polygon, get an official quote directly (sales contact or a
live trial checkout) rather than relying on third-party price citations again.

FMP Starter (already subscribed) covers analyst-consensus needs completely (T5 PASS).

---

## Evidence artifacts

- FMP probe: live API call, 2026-07-04, key=Starter tier (verified subscribed)
- SEC EDGAR probe: live API call to `data.sec.gov/api/xbrl/companyfacts/`
- Polygon/Massive pricing: NOT independently verifiable. Confirmed twice
  (2026-07-04 and 2026-07-05) that `polygon.io/pricing/*` 301-redirects to
  `massive.com/pricing/*`, which is a JS-rendered SPA with no pricing text or
  embedded JSON in the raw HTML. `massive.com/pricing/fundamentals` returns
  HTTP 404. Knowledge-base/FAQ and announcement-blog pages checked
  (`/knowledge-base/categories/financials`,
  `/knowledge-base/article/what-fields-can-i-expect-from-polygons-financials-api`,
  `/blog/announcing-polygon-io-financials-...`) — none expose pricing. Third-
  party sourcing conflicts between rounds ($99/mo vs. a later $29/mo claim from
  indirect search synthesis); neither traces to an official page.
