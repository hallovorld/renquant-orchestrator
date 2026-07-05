# RS-3: Data-vendor stack — preliminary vendor screen + validation plan

DATE: 2026-07-04 (revised 2026-07-05 per Codex review — downgraded from
      RECOMMENDATION to PRELIMINARY SCREEN; see §6a for what changed and why)
STATUS: PRELIMINARY VENDOR SCREEN — not yet a spend-ready recommendation.
        None of the three blocking review points (pricing, PIT-fidelity
        acceptance evidence, analyst-consensus coverage) are resolved with
        confidence as of this revision. §2.1a/§2.1b document genuine new
        evidence gathered this round that, if anything, makes the original
        Polygon pick MORE uncertain, not less.
BLOCKS: N2 (PIT revision accrual), N3 (FMP quarterly depth), M-SIG (signal substrate),
        M8 (universe expansion)

---

## Bottom line

**Leading candidate, NOT yet spend-ready: FMP Starter (keep, already active) +
Polygon.io fundamentals access (cost genuinely unresolved — see §2.1a) +
SEC EDGAR XBRL (free).** This memo previously stated a "$58/month total" and
a "RECOMMENDED" verdict. Both are downgraded here: the $29/mo standalone
"Fundamentals add-on" premise could not be confirmed against Polygon's current
public site (§2.1a), and Polygon's own documentation suggests analyst-consensus
data is a separate third-party partner integration, not part of core
fundamentals (§2.1b) — meaning the "covers all four roadmap needs" claim is
now unverified, not just unconfirmed-but-probably-right.

**What this memo now is**: a vendor screen (still useful — it correctly rules
out several vendors, see §3) plus a concrete, executable validation plan
(§4) that must run BEFORE any subscription decision. It is not an
authorization to spend.

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

### 2.1a Polygon pricing — genuinely unresolved (not just "verify before subscribing")

This round attempted to directly verify Polygon's current pricing against their
live site rather than repeat the prior web-search-sourced $29/mo figure.
Findings:

- `polygon.io/pricing` is a client-side-rendered (Next.js) page; actual plan
  prices are not present in the static HTML and require JS execution to read,
  so this could not be scraped/confirmed by a plain HTTP fetch.
- `polygon.io/pricing/fundamentals` — the URL pattern a dedicated "Fundamentals
  add-on" page would use — returns **HTTP 404**. No such page currently exists.
- Polygon's site is currently organized around per-asset-class plans (Stocks,
  Options, Indices, Futures, Forex, Crypto), each with its own tiers
  (Developer/Starter/Advanced were the tier names found in the Stocks page's
  markup). This structure does not obviously match "a $29/mo standalone
  Fundamentals add-on" — fundamentals/financials access more plausibly requires
  a **Stocks asset-class plan** at some tier, not a separate add-on product.

**Conclusion: the $29/mo figure, and therefore the $58/mo stack total, cannot
be confirmed from Polygon's current public site and may not reflect how the
product is actually sold today.** This is stronger than the prior memo's "verify
before committing" hedge — an active check found evidence pointing away from
the stated structure, not merely an unconfirmed number. Real pricing requires
either creating a Polygon account to see the live plan selector, or contacting
their sales channel. Do not treat $58/mo as a decision boundary until one of
those happens.

### 2.1b Analyst-consensus coverage — likely NOT included in Polygon fundamentals

Polygon's own documentation site (`polygon.io/docs/rest/stocks/fundamentals/financials`)
shows, in its own navigation structure, that consensus ratings and analyst data
live under a separate section: **`/rest/partners/benzinga/consensus-ratings`**,
`/rest/partners/benzinga/analyst-ratings`, `/rest/partners/benzinga/analyst-details`,
`/rest/partners/benzinga/analyst-insights` — all under a "Partners → Benzinga"
navigation branch, distinct from the core Fundamentals/Financials product.

This means: the claim that the Polygon add-on "covers all four roadmap needs"
including N3's analyst-consensus historical-revision-timeline requirement is
**not supported by what Polygon's own docs show**. Analyst consensus/ratings
data appears to require a separate Benzinga partner subscription with its own
(currently unknown) pricing, not bundled into core fundamentals. If N3/M-SIG's
analyst-revision requirement is served by this Benzinga integration, its cost
is not in the $58/mo total at all. If it is NOT served by any Polygon-affiliated
product, then FMP Starter's existing annual analyst-grades-historical remains
the only analyst-consensus source in the stack, and the "quarterly revision
timeline" gap in the original demand map (§1) is still open.

### 2.2 Candidates evaluated

| Vendor | Tier needed | Monthly cost | PIT capability | Quarterly depth | US coverage | Historical depth | Rate limits | Verdict |
|---|---|---|---|---|---|---|---|---|
| **FMP Premium** | Premium | ~$49–79/mo [WEB-SOURCED, verify] | No explicit PIT timestamps; data from SEC filings but no `filing_date` field in fundamentals response | Yes (quarterly unlocked) | Full US + UK/Canada | 30y | 750/min | ❌ Overpay — quarterly depth is the only gain vs Starter; no PIT |
| **Polygon.io** | Fundamentals (pricing unresolved — §2.1a) | UNRESOLVED — see §2.1a | `filing_date` and `period_of_report_date` fields exist on financial records per docs; whether they correctly distinguish original vs. amended filings for the SAME period is UNTESTED (see §4 acceptance probe) | Yes (quarterly + annual + TTM) per docs | ~6,700 public companies (10+ years); sourced from SEC EDGAR | 10+ years (back to ~2009) | Unlimited (rate-limited by HTTP connection) | ⚠️ **LEADING CANDIDATE, NOT YET VERIFIED** — pricing and PIT-fidelity and analyst-coverage all pending §4 probe |
| **Sharadar/SF1** (Nasdaq Data Link) | SF1 subscription | ~$150–500/yr [WEB-SOURCED, pricing behind login wall] | **Yes — point-in-time by design**; SF1 is the gold standard for PIT fundamentals backtesting | Yes (quarterly + annual) | 14,000+ US public companies (25 years, survivorship-bias-free with delisted coverage) | 25 years | Bulk download (no real-time API rate concern) | ⭐ Best PIT quality but pricing opaque; **UPGRADE PATH** if Polygon PIT proves insufficient |
| **Norgate Data** | Platinum | $52.50/mo ($630/yr) [VERIFIED from website] | **No historical PIT** — fundamentals are latest-report-only, no historical `as_of` snapshots | Latest quarter only (no historical quarterly series) | Active + delisted + historical index constituents (back to 1990) | 1990–present (prices); current-only (fundamentals) | Desktop app, not API-first | ❌ Excellent for survivorship-bias-free price data + index membership; **useless for PIT fundamentals** |
| **Intrinio** | Bronze+ | ~$150–250/mo [WEB-SOURCED, verify] | Yes (PIT fundamentals available) | Yes | Broad US coverage | Varies by dataset | Custom per plan | ❌ Too expensive for our book size; overkill |
| **Tiingo** | Power | $10–30/mo [WEB-SOURCED, verify] | Partial — can access "as reported" data from SEC; not a dedicated PIT database | Yes (quarterly + annual) | 5,500+ US equities, 20+ years | 20+ years | 500 unique symbols/mo (free); unlimited (Power) | ⚠️ **WATCH** — cheap, good fundamental depth, but PIT fidelity unclear. Worth a free-tier probe |
| **EODHD** | Fundamentals Feed | $59.99/mo [WEB-SOURCED, verify] | Not explicitly PIT; "as-reported" not confirmed | Yes | 120,000+ instruments globally | 30+ years | 100K+ calls | ❌ No clear PIT; more expensive than Polygon for less |
| **SimFin** | Paid tier | ~$10–30/mo [WEB-SOURCED, verify] | **Explicitly NOT PIT** (their docs state this) — includes restatements | Yes | Limited US coverage | Varies | Varies | ❌ Explicitly not PIT; unusable for leak-free backtesting |
| **SEC EDGAR XBRL** | Free (data.sec.gov) | $0 | **Yes — filing dates are in the XBRL facts**; the raw source Polygon/FMP/etc. all parse | Yes (10-Q/10-K filings) | All SEC filers | Full SEC history | 10 req/sec per IP | ✅ **FREE PIT SOURCE, and independently verified reachable this round** (see §4 — used to build the acceptance-probe fixture set). Use as backup/validation regardless of paid-vendor choice. |
| **IEX Cloud** | — | — | — | — | — | — | — | ❌ **SHUT DOWN** (Aug 2024) — no longer available |

## 3. Vendors ruled out (this part of the memo is not in question)

The Tier 3 exclusions from the prior version stand — none of the review's
concerns touched these:

| Vendor | Why not |
|---|---|
| Intrinio | $150–250/mo is disproportionate to book size (~$10.8k) |
| EODHD | $60/mo with no clear PIT advantage over Polygon at $29/mo, and its own PIT status is unconfirmed |
| SimFin | Explicitly not PIT — unusable for leak-free backtesting |
| IEX Cloud | Shut down August 2024 |
| Norgate | No PIT fundamentals capability at any tier |
| Tiingo | PIT fidelity unclear; worth a free-tier probe but don't commit spend |

## 4. Acceptance probe — concrete, executable, not yet run against live Polygon data

This section replaces the prior vague "define pass/fail criteria" placeholder.
It specifies an actual, reproducible test using REAL restatement events found
this round via SEC EDGAR's public APIs (not hypothetical examples).

### 4.1 Sample selection method (reproducible)

Queried `data.sec.gov/submissions/CIK{cik}.json` for every ticker in the live
104 watchlist (142 names, from `strategy_config.json`'s `watchlist` field,
136/142 resolvable to a CIK via `sec.gov/files/company_tickers.json`) for any
`10-Q/A` or `10-K/A` filing in their recent-filings history. **53 amendment
filings found across the real watchlist.** Five selected for the probe,
favoring recency, ticker diversity, and (for the MO case) explicitly excluding
what looks like a routine incorporate-by-reference amendment rather than a
substantive restatement:

| Ticker | Form | Period (original) | Amendment filed | Accession # |
|---|---|---|---|---|
| CVX | 10-Q/A | 2022-03-31 | 2022-05-04 | 0000093410-22-000028 |
| KO | 10-Q/A | 2024-03-29 | 2024-05-30 | 0000021344-24-000019 |
| GLD | 10-K/A | 2024-09-30 | 2024-12-19 | 0001437749-24-037938 |
| GRMN | 10-K/A | 2023-12-30 | 2024-11-29 | 0000950170-24-131914 |
| DUK | 10-Q/A | 2020-03-31 | 2020-06-02 | 0001326160-20-000172 |

(MO has a 10-K/A filed in every one of the last 9 years, always ~5 months after
the original 10-K — almost certainly a routine Part III proxy-incorporation
amendment, not a financial restatement. Excluded from the probe sample for
that reason; worth confirming before use elsewhere.)

### 4.2 What to compare

For each of the 5 (ticker, original period) pairs above:

1. Pull Polygon's `/vX/reference/financials` (or current equivalent) response
   for that ticker filtered to the same `period_of_report_date`.
2. Check whether Polygon returns **one** record for that period (the latest/
   restated values only) or **two distinct timestamped records** — one
   reflecting what was reported at the ORIGINAL filing date, one reflecting
   the AMENDED values with the amendment's filing date.
3. Compare Polygon's returned `filing_date` for each record against EDGAR's
   ground truth: original filing date vs. amendment filing date (both listed
   above, from the real EDGAR submissions data).

### 4.3 Pass / fail / falsification criteria

- **PASS** (per ticker): Polygon exposes the original-filing values under the
  original `filing_date`, AND the amendment's corrected values under the later
  `filing_date` — i.e., a backtest run "as of" any date between the two filings
  would see the pre-amendment numbers, and a backtest run after the amendment
  date would see the corrected numbers. This is the actual PIT property N2
  needs.
- **FAIL** (per ticker): Polygon returns only one record per period (silently
  the latest/restated values), with `filing_date` either missing, unchanged
  from the original, or otherwise not distinguishing the two vintages — i.e.,
  a backtest run "as of" a date before the amendment would still see restated
  (look-ahead-biased) numbers.
- **Overall falsification of Polygon as Tier-1**: if 3 or more of the 5 sample
  tickers FAIL, Polygon's `filing_date` field does not deliver genuine
  point-in-time reconstruction for restated financials, and it should not be
  adopted as the N2 PIT source regardless of price. A single FAIL is not
  disqualifying (idiosyncratic vendor coverage gaps happen) but should be
  investigated before committing.

### 4.4 Status: NOT YET RUN

This probe requires either a Polygon trial/paid API key (not available in this
research session) or manual inspection via their web UI. It is fully specified
and ready to execute — whoever obtains Polygon access next should run exactly
this comparison before any subscription commitment, not a broader/vaguer
"check PIT fidelity" pass.

## 5. Subscription list — cost column marked unresolved, not final

| Vendor | Tier | Monthly | Annual equiv | Status |
|---|---|---|---|---|
| FMP | Starter | $29 | $348 | ACTIVE [VERIFIED] |
| Polygon.io | Fundamentals (product/pricing structure unconfirmed) | **UNRESOLVED — see §2.1a** | UNRESOLVED | **NOT YET SPEND-READY** |
| SEC EDGAR | Free | $0 | $0 | Available (engineering work needed); independently reachable — used to build §4's fixture set this round |
| Benzinga (analyst consensus, if required for N3) | Unknown — separate partner product per §2.1b | **UNRESOLVED, not previously accounted for at all** | UNRESOLVED | Needs its own pricing check if N3 depends on it |

Do not treat any total (including the prior "$58/mo") as a decision boundary
until §2.1a/§2.1b/§4 are resolved.

## 6. Decision needed from operator

- [ ] Nothing to approve yet. This is a screen + validation plan, not a spend
      ask.
- [ ] If operator wants to unblock N2/M-SIG faster than a full validation
      cycle allows: authorize creating a Polygon trial/paid account so §4's
      probe can actually be run (this is the single highest-value next step —
      it resolves pricing AND PIT-fidelity in one motion, since account
      creation shows the live plan selector).
- [ ] Separately: someone should check whether Benzinga's consensus-ratings
      product (§2.1b) is needed for N3, and if so get its real pricing, before
      assuming FMP Starter's existing annual analyst-grades-historical is
      sufficient.

## 6a. What changed in this revision and why (Codex round 2)

Codex blocked the prior version on three points: (1) the $58/mo total rested
on a cost the memo itself marked unresolved, (2) the methodology was a vendor
feature-matrix, not an acceptance test against real requirements, (3) the
analyst-consensus coverage claim was unproven for the specific depth N3/M-SIG
needs.

This round did NOT simply hedge language. It:
- Attempted to directly verify Polygon pricing against their live site — found
  a 404 on the expected "Fundamentals add-on" pricing URL and a page structure
  that doesn't match the memo's premise (§2.1a). This is genuine new evidence,
  and it points toward the original claim being MORE likely wrong, not just
  unconfirmed.
- Found, via Polygon's own docs navigation, that analyst-consensus/ratings
  data is served by a separate "Benzinga" partner product, not core
  fundamentals (§2.1b) — directly relevant to whether the stack "covers all
  four roadmap needs" as claimed.
- Queried SEC EDGAR's real submissions data for every name in the live 104
  watchlist (142 tickers) and found 53 genuine historical restatement/
  amendment filings, then built a concrete 5-ticker acceptance probe (§4)
  from real events (CVX, KO, GLD, GRMN, DUK) with explicit pass/fail/
  falsification criteria — not run yet (no Polygon API access this round),
  but fully specified and ready to execute.

Net effect: the memo's overall recommendation strength is downgraded from
RECOMMENDATION to PRELIMINARY SCREEN, matching what was actually verified
versus what remains open. This is not a return to the status quo — the
demand map (§1) and vendor exclusions (§3) are unaffected by this round's
findings and remain valid; only the specific Polygon pick and its cost/
coverage claims are downgraded pending §4.

---

Sources (web research, 2026-07-04; live-site verification 2026-07-05):
- [FMP Pricing](https://site.financialmodelingprep.com/pricing-plans)
- [Polygon.io Pricing](https://polygon.io/pricing) — client-rendered, prices not confirmable via plain fetch (§2.1a)
- [Polygon.io Financials API docs](https://polygon.io/docs/rest/stocks/fundamentals/financials) — nav shows Benzinga partner section for analyst/consensus data (§2.1b)
- [Polygon.io Filing Date FAQ](https://polygon.io/knowledge-base/article/does-polygon-provide-the-filing-date-for-any-financial-reports)
- [Sharadar / Nasdaq Data Link](https://data.nasdaq.com/databases/SF1)
- [Norgate Data Pricing](https://norgatedata.com/prices.php)
- [Norgate Fundamentals FAQ](https://norgatedata.com/data-package-faq.php)
- [Tiingo Pricing](https://www.tiingo.com/about/pricing)
- [EODHD Pricing](https://eodhd.com/pricing)
- [SimFin (not PIT)](https://www.simfin.com/en/prices/)
- [IEX Cloud Shutdown](https://www.alphavantage.co/iexcloud_shutdown_analysis_and_migration/)
- [SEC EDGAR company tickers](https://www.sec.gov/files/company_tickers.json) — used this round to map the real 104 watchlist to CIKs
- [SEC EDGAR submissions API](https://data.sec.gov/submissions/) — used this round to find the 53 real amendment filings behind §4's probe design
- [SEC EDGAR full-text search](https://efts.sec.gov/LATEST/search-index) — used to spot-check amendment filings
- [Best Financial Data APIs 2026](https://www.nb-data.com/p/best-financial-data-apis-in-2026)
