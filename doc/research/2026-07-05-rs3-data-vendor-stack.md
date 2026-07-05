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

**PIT terminology used throughout this memo (read before §3):**
- **Proxy PIT (snapshot accrual + `available_at`)** — what N2's minimal-viable
  snapshotter does today: append a raw fundamentals snapshot on the day it's
  observed, stamped with the observation date. This answers "what did we see
  on date X" for dates AFTER accrual started (2026-07-02). It does NOT answer
  "what was reported as of a past date" for any date before accrual started,
  and it cannot recover a value that was later restated unless the restated
  version happened to be snapshotted before the correction.
- **True PIT (as-reported + restated history)** — what a vendor like Sharadar
  sells: for any historical `period_of_report_date`, the exact figure AS
  ORIGINALLY FILED, plus every subsequent restatement with its own filing
  date, going back 20+ years. This answers "what was reported as of date X"
  for ANY past date, including before we started accruing anything ourselves.
- These are not interchangeable. A task whose acceptance test only needs
  "did we correctly capture what we saw starting today" is satisfied by proxy
  PIT. A task whose acceptance test needs "what would this signal have looked
  like in 2015" requires true PIT and cannot be retrofitted from our own
  accrual — see N2/M-SIG contract below for which is which.

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

## 3. Roadmap mapping — data contracts + acceptance tests

Per-task contract: exact fields required, PIT semantics required (proxy vs true —
see terminology above), constituent-history requirement, delivery cadence, and the
first acceptance test that would validate the vendor choice actually satisfies the
task (not just "vendor has the data" — a falsifiable pass/fail check).

### N2 — PIT revision accrual

- **Fields**: raw fundamentals snapshot as returned by FMP's `key-metrics`/
  `financial-statements` endpoints (EPS, revenue, book value, key ratios) —
  whatever fields the snapshotter currently persists, unchanged.
- **PIT semantics required**: **proxy PIT only**, by the master plan's own spec
  (§1: "minimal-viable snapshotter OK; write-time `available_at`; no backfill").
  N2 does NOT require true PIT — its acceptance criterion is about accrual
  discipline going forward, not historical reconstruction.
- **Constituent-history**: none required (single-snapshot-per-day append).
- **Delivery cadence**: daily batch.
- **Vendor**: FMP Starter (current) — correctly sized for this contract. Do
  NOT read this as "FMP is a PIT solution" — FMP is a proxy-PIT accrual
  substrate for N2 specifically because N2 only asks for proxy PIT.
- **First acceptance test** (already the master-plan AC, restated as a check):
  3 consecutive daily snapshot appends with `available_at` correctly stamped
  + a missed-day alert firing if a day is skipped. This is running (ACTIVE) —
  verify via the snapshotter's own append log, not this memo.
- **Spend trigger**: none — N2 is satisfied by the current $29/mo stack.

### N3 — FMP harvest

- **Fields**: 10y analyst estimates (target price, EPS/revenue estimates,
  rating), income/balance/CF statements, 5y daily history.
- **PIT semantics required**: none (this is a current-state fundamentals +
  estimates harvest, not a revision-history task).
- **Constituent-history**: none (fixed 145-name large-cap universe).
- **Delivery cadence**: batch (harvest job, not real-time).
- **Vendor**: FMP Starter (current).
- **First acceptance test**: ≥95% field-coverage across the current universe
  with 0 plan-locked (HTTP 402) errors — this is the existing harvest job's
  own pass criterion; already ACTIVE and passing per orchestrator#409.
- **Spend trigger**: none.

### M-SIG — signal stack (C1 revision drift specifically)

- **Fields**: analyst estimate revision deltas (current estimate vs prior
  estimate, per ticker per period) for signal #1 (revision drift); quality
  metrics for signal #2; price/momentum for signal #3 (existing).
- **PIT semantics required**: **true PIT for backtesting; proxy PIT is
  sufficient for live signal generation going forward.** This is the
  distinction codex flagged — be precise about which sub-need applies:
  - *Live, forward-looking revision drift* (what C1 actually measures per the
    master plan: "the PIT clock matures ~2027-01, started 2026-07-02") only
    needs OUR OWN proxy-PIT accrual to keep running — it does not need a
    vendor's historical PIT at all, because the signal is defined on deltas
    observed after accrual start. No vendor purchase accelerates this; time
    does.
  - *A historical backtest of C1 prior to 2026-07-02* would need true PIT
    (Sharadar) — because our own accrual has no history before that date and
    cannot be reconstructed retroactively from a proxy source.
- **Constituent-history**: none (existing 104 universe).
- **Delivery cadence**: daily batch (matches N2).
- **Vendor**: FMP (current, revision-proxy) for the live signal; Sharadar
  only if a historical (pre-2026-07-02) backtest of C1 is explicitly
  requested — which is not currently planned per the master plan's own
  "pending by design" status for C1.
- **First acceptance test**: not yet defined — C1 is "pending by design"
  (master plan, PIT clock immature) and has no acceptance test until enough
  proxy-PIT history has accrued to run S-REL's standard positive-control
  battery on it. Do not treat this memo as authorizing Sharadar spend for
  M-SIG; see spend trigger below.
- **Spend trigger**: authorize Sharadar (~$50–100/mo) ONLY if/when C1's
  first live-signal read (post sufficient proxy-PIT accrual, no earlier
  than ~2027-01 per the master plan) shows a positive IC AND a specific
  historical-backtest request is made that proxy PIT cannot answer. Do not
  pre-purchase against a signal that has not yet cleared its own gate.

### M7 — down-cap MVP screen

- **Fields**: full OHLCV + basic fundamentals for the expanded (~14k+ name)
  small/mid universe.
- **PIT semantics required**: none directly, but the screen's own gate
  ("frozen thresholds BEFORE running") requires the underlying backtest to
  be survivorship-bias-free, which is a constituent-history requirement
  (below), not a PIT one.
- **Constituent-history**: **required** — historical index/exchange
  membership as of each backtest date, including delisted names, or the
  down-cap screen's IC/BR estimate is inflated by survivorship bias. This is
  the dimension only Norgate or Sharadar provide (current stack: none).
- **Delivery cadence**: batch (one-time historical pull for the backtest;
  no live feed needed for the go/no-go memo itself).
- **Vendor**: Norgate Platinum (recommended) — desktop + `norgatedata`
  Python API is better documented for this one-off systematic backtest use
  than Sharadar's bulk-CSV delivery.
- **First acceptance test**: pull Norgate's historical constituent list for
  one past date (e.g. 2015-01-01) for a known index subset, cross-check
  against a public historical constituent record (e.g. an archived index
  fact sheet or a free secondary source) for ≥95% name-match — confirms the
  survivorship-free claim is real before running the full M7 backtest on it.
- **Spend trigger**: authorize Norgate (~$66/mo) when M7 is scheduled to
  start (master plan: Aug–Sep target) — not before, since M7 has not started
  and the subscription would otherwise sit idle.

### M8 — cluster-wave 1

- **Fields**: fundamentals + prices for ~100 additional quality names beyond
  the current universe.
- **PIT semantics required**: none.
- **Constituent-history**: none directly for M8 itself (it depends on M7's
  down-cap screen output, not a fresh survivorship pull).
- **Delivery cadence**: batch.
- **Vendor**: FMP Starter (current) — already covers 14k+ names, no new
  spend needed once the M7-selected name list exists.
- **First acceptance test**: wave-1 IC within noise band of the existing
  145-name baseline (master plan's own AC) — a modeling/backtest check, not
  a data-vendor check; this task needs no new vendor spend.
- **Spend trigger**: none (blocked on M7, not on data).

### S10 — full open-auction IS study extension

- **Fields**: intraday 1-min or tick-level trade/quote data for the existing
  watchlist, extended across full history + a collector corpus.
- **PIT semantics required**: none.
- **Constituent-history**: none.
- **Delivery cadence**: needs historical tick/1-min depth, not necessarily
  real-time (this is a retrospective IS study, not a live feed requirement).
- **Vendor**: Polygon Stocks Advanced (full SIP tick) — IEX-via-Alpaca is a
  documented-biased fallback (IEX-only tape, not full SIP).
- **First acceptance test**: already defined by the task itself (master plan
  §1: "bps/entry with CI; feeds §9.4 prereg") — this is POC-C's own
  materiality gate (P ≈ 0.65 per the master plan), not something this memo
  needs to add. What this memo adds: do not purchase Polygon before POC-C's
  extension is run and shows the material-edge signal is not an artifact of
  the smaller original sample.
- **Spend trigger**: unchanged from the existing operator decision — deferred
  pending materiality; re-trigger at M2 canary or book scale-up (per
  2026-07-02 operator note), not a new recommendation from this memo.

---

## 4. Recommended stack

### Tier 1: Current (no new spend)

| Vendor | Plan | Cost | Serves |
|---|---|---|---|
| FMP | Starter | $29/mo | N2 (proxy PIT — satisfies N2's own spec, not a true-PIT substitute), N3 (analyst+fundamentals), M-SIG (live revision signal via proxy), M8 (universe prices) |
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
| Sharadar | Core Fundamentals | ~$50–100/mo | True PIT as-reported history — a HISTORICAL BACKTEST capability for M-SIG C1 (pre-2026-07-02 dates our own proxy accrual cannot cover), not an upgrade to N2 itself, whose own spec only requires proxy PIT | Only if a pre-accrual-start historical backtest of C1 is explicitly requested after C1's live signal (proxy-PIT-based) clears its own gate — see §3 M-SIG spend trigger |

**Total if all: $295–345/mo.** Only add after gated evidence (S10 materiality,
M-SIG signal IC) — see per-task spend triggers in §3, which are the authoritative
gating language; this table is a cost summary, not an independent recommendation.

---

## 5. Decision status

| Item | Authorization | Action |
|---|---|---|
| FMP Starter $29/mo | ✅ AUTHORIZED + SUBSCRIBED | Running (key-metrics + 10y estimates verified) |
| Finnhub free | ✅ No spend | Running |
| IEX via Alpaca | ✅ No spend | Running (IEX bias documented + accepted) |
| Norgate Platinum ~$66/mo | ❓ NEEDS APPROVAL | Recommended for M7; defer until M7 starts |
| Polygon $199/mo (ATP) | ❌ DEFERRED | Operator cost pushback (2026-07-02); re-trigger at M2 canary or book scale-up |
| Sharadar ~$50–100/mo | ❓ NEEDS APPROVAL | Only for a historical (pre-2026-07-02) backtest of M-SIG C1 — not needed for C1's live signal, which runs on our own proxy-PIT accrual; not currently requested (C1 is "pending by design" per the master plan) |

**Bottom line:** Current $29/mo stack covers NOW + SHORT, including N2's full
PIT-accrual contract (proxy PIT is what N2's own spec requires — this is not a
gap). The only new spend recommended before August is Norgate Platinum ($66/mo)
for M7 — but only when M7 actually starts. Sharadar and Polygon are each gated on
a specific future trigger (§3), not a general "would be nice to have" — do not
authorize either until its named trigger condition is met.

---

Sources:
- [Polygon.io Pricing](https://polygon.io/pricing)
- [Norgate Data Subscription](https://norgatedata.com/prices.php)
- [Norgate Stock Market Packages](https://norgatedata.com/stockmarketpackages.php)
- [FMP Pricing Plans](https://site.financialmodelingprep.com/pricing-plans)
- [Finnhub Pricing](https://finnhub.io/pricing)
- [Nasdaq Data Link / Sharadar](https://data.nasdaq.com/databases/SF1)
