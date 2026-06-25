# Decision — analyst-data source strategy (MCP first, FMP-paid fallback)

2026-06-25. Goal: a **COMPLETE** analyst dataset — **full watchlist coverage AND
multi-year history** — for the analyst-revision model feature. No FREE source
gives both today; this records the source decision + the MCP query approach so it
is reproducible.

## What was empirically tested this session (don't re-probe)
| Source | Coverage | History | Verdict |
|---|---|---|---|
| FMP free `/stable/grades-historical` | **~30%** (HTTP 402 plan-lock on ~70%) | 7.5y | deep but coverage-blocked ([[fmp-free-tier-covers-only-30pct]]) |
| Finnhub free `/stock/recommendation` | **full** (136/145; 9 missing = ETFs) | **~4 mo only** | full but shallow; collected 2026-06-25 → `data/analyst_ratings_finnhub.parquet` |
| yfinance upgrades/downgrades | full | multi-year events | net-upgrade signal placebo-clean **NEGATIVE** all regimes; no PIT (rejected #23) |

→ **No free source is full-coverage AND deep-history.** A complete-today dataset
needs a paid/entitled source.

## Decision — priority order
1. **financial-analysis MCP FIRST** (FactSet / S&P Global-Kensho / Morningstar /
   LSEG). Institutional-grade: full coverage + decades of estimate-revision
   history. **$0 marginal cost IF the account is entitled** (the plugin is
   installed in this environment; it only needs OAuth). Try the auth; if entitled
   → this is the gold standard and the search stops here.
2. **FMP paid (Starter ~$22/mo)** if no MCP entitlement. Unlocks the 7.5y
   full-coverage `grades-historical`; **the #24 FMP fetcher works immediately —
   zero new integration, collect today**. Verify the chosen tier actually
   unlocks the previously-402 symbols with a one-call test (ADI / NFLX) before
   committing to the recurring fee.
3. **EOD Historical Data (~$20–60/mo)** as a backup vendor (analyst ratings +
   history) if FMP's tier doesn't unlock full coverage.
- In parallel, the **Finnhub daily cron (#408)** accumulates a free full-coverage
  series — a few months → usable on its own, and a cross-check on the paid source.

## Cost discipline (account = ~$10.6k — this matters)
Monthly data fees are a real drag at this size: $22/mo ≈ **2.5% of equity/yr**.
And the analyst edge is **UNPROVEN** — the FMP preliminary +0.031 (BULL_CALM, 1
seed, 38 names) sat **inside** the ~0.036±0.046 leakage-floor noise. So:
- Prefer **free / already-entitled** (the MCP if accessible).
- If paying, take the **cheapest that works (FMP $22)**; do **not** exceed ~$22–50/mo
  for unproven-edge data.
- **Validate the signal (WF gate / orch #190 outcome validator) BEFORE** committing
  to a recurring fee — a complete historical dataset lets that validation run in days.

## MCP query approach + prompts (reproducible)
**Auth flow** (per server, e.g. FactSet):
1. Call `mcp__plugin_financial-analysis_factset__authenticate` → returns an OAuth
   authorization URL.
2. Operator opens it in a browser, authorizes; the browser redirects to
   `http://localhost:<port>/callback?code=...&state=...` (the page may fail to
   load on a remote session — the URL in the address bar is still valid).
3. Call `mcp__plugin_financial-analysis_factset__complete_authentication` with
   that full callback URL → the server's **data tools load automatically**
   (their schemas were deferred until auth).

**What to ask for** (once the data tools are available — schemas appear on auth;
discover them, these are the intended queries per watchlist ticker):
- *"Monthly analyst consensus rating distribution (strongBuy/buy/hold/sell/
  strongSell or the vendor's rating scale) over the longest available history."*
- *"EPS / target-price estimate-revision history — count of up vs down revisions
  over trailing 1/3 months, per ticker, with timestamps (PIT)."*
- Map every result onto the **same tidy schema** the FMP/Finnhub fetchers emit:
  `(ticker, period, consensus∈[-2,2] | estimate_revision, n_analysts, source,
  fetched_at)` — so the downstream feature path stays source-agnostic.

**Server notes**: FactSet = estimate-revision gold standard; S&P Global / Kensho
(`kfinance.kensho.com`) = financials + estimates; Morningstar = ratings +
fair-value; LSEG / Aiera / Daloopa = other angles. Try FactSet or S&P first for
estimate revisions.

## Integration path
Existing fetchers: `#24` FMP (30%, infra), `#25` Finnhub (full/shallow,
accumulator). The chosen COMPLETE source gets a **parallel base-data fetcher**
(reuse the FMP/Finnhub `FetchResult` + store + gate patterns) writing the same
schema. The **feature-engineering + retrain PRs come AFTER** a complete dataset +
signal validation — never train an analyst feature on the shallow Finnhub window
([[deployed-but-dark-is-not-done]]).
