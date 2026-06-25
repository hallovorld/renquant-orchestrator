# Decision — analyst-data source strategy (MCP first, FMP-paid fallback)

2026-06-25. Goal: a **COMPLETE** analyst dataset — **full watchlist coverage AND
multi-year history** — for the analyst-revision model feature. No FREE source
gives both today; this records the source decision + the MCP query approach so it
is reproducible.

## What was empirically tested this session (don't re-probe)
| Source | Coverage | History | Verdict |
|---|---|---|---|
| FMP free `/stable/grades-historical` | **~30%** (HTTP 402 plan-lock on ~70%) | 7.5y | deep but coverage-blocked ([[fmp-free-tier-covers-only-30pct]]) |
| Finnhub free `/stock/recommendation` | **broad** (live probe 136/145 returned data; 9 `no_coverage` — unverified, could be ETF/uncovered, see #25) | **~4 mo only** | broad but shallow; collected 2026-06-25 → `data/analyst_ratings_finnhub.parquet` |
| yfinance upgrades/downgrades | full | multi-year events | net-upgrade signal placebo-clean **NEGATIVE** all regimes; no PIT (rejected #23) |

→ **No free source is broad-coverage AND deep-history.** A complete-today dataset
needs a paid/entitled source. NOTE: the Finnhub producer (base-data **#25**) and
its cron (**#408**) are **still in review (CHANGES_REQUESTED → fixed, pending
re-review)** — treat Finnhub as a live-probe result, not yet established infra.

## Decision — priority order
1. **financial-analysis MCP FIRST** (FactSet / S&P Global-Kensho / Morningstar /
   LSEG). Institutional-grade IF entitled: full coverage + decades of
   estimate-revision history, at **$0 marginal cost**. **[UNVERIFIED]** In the
   **Claude Code** environment the financial-analysis MCP `authenticate` stubs
   are present (they are **NOT** in the Codex environment); but entitlement is
   unknown and the data tools have **not been exercised** (they stay deferred
   until OAuth). So this is an **expected connector to TEST**, not confirmed
   access — try the auth; only if it authenticates AND returns covered history is
   it the gold standard.
2. **FMP paid (Starter $29/mo)** if no MCP entitlement. Unlocks the 7.5y
   full-coverage `grades-historical`; **the #24 FMP fetcher works immediately —
   zero new integration, collect today**. Verify the chosen tier actually
   unlocks the previously-402 symbols with a one-call test (ADI / NFLX) before
   committing to the recurring fee.
3. **EOD Historical Data (~$20–60/mo)** as a backup vendor (analyst ratings +
   history) if FMP's tier doesn't unlock full coverage.
- In parallel, the **Finnhub daily cron (#408)** would accumulate a free
  **broad-coverage** (NOT proven full — an empty response is ambiguous `no_coverage`)
  series — a few months → usable on its own, and a cross-check on the paid source.
  **PENDING:** base-data #25 + cron #408 are still CHANGES_REQUESTED; this path is
  not live until both land, the base-data pin is bumped, and the integration is
  validated (a one-shot dry-run proving the active/no_coverage metrics + fail-closed).

## Cost discipline (account = ~$10.6k — this matters)
Monthly data fees are a real drag at this size: FMP Starter $29/mo ≈ **3.3% of
equity/yr** ($22 seen elsewhere is the annual-billing rate, not monthly).
And the analyst edge is **UNPROVEN** — the FMP preliminary +0.031 (BULL_CALM, 1
seed, 38 names) sat **inside** the ~0.036±0.046 leakage-floor noise. So:
- Prefer **free / already-entitled** (the MCP if accessible).
- If paying, default to a **one-month validation buy, NOT a recurring
  subscription**: verify the tier unlocks the previously-402 symbols (one-call
  test ADI/NFLX) → buy ONE month → pull the full history → validate → **cancel**
  unless the signal clears a pre-registered bar. Take the cheapest that works
  (FMP $22); do **not** stand up a recurring fee for unproven-edge data.
- **Validate the signal with its OWN pre-registered per-regime WF/placebo gate
  BEFORE** committing to any recurring fee — a complete historical dataset lets
  that run in days. (This is the analyst-FEATURE validation; it is **not** orch
  #190, which is the live conviction-gate *outcome* validator over the decision
  ledger — a different control. The analyst feature needs its own gate.)

## MCP query approach + prompts (reproducible)
**[UNVERIFIED — Claude Code env only.]** The function names below are the auth
entrypoints listed in the Claude Code tool registry this session; they are NOT
present in the Codex environment and have NOT been called/authenticated, so none
of this is confirmed working. Documented for reproducibility of the *attempt*,
not as verified capability — re-discover the actual tools at auth time.

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
Existing fetchers: `#24` FMP (~30%, merged infra), `#25` Finnhub (broad/shallow
accumulator — pending re-review) + cron `#408` (pending). The chosen COMPLETE
source gets a **parallel base-data fetcher**
(reuse the FMP/Finnhub `FetchResult` + store + gate patterns) writing the same
schema. The **feature-engineering + retrain PRs come AFTER** a complete dataset +
signal validation — never train an analyst feature on the shallow Finnhub window
([[deployed-but-dark-is-not-done]]).
