# RS-3 data-vendor stack — preliminary screen + validation plan

STATUS: preliminary screen delivered; spend DEFERRED until validation probe passes.
WHAT: `doc/research/2026-07-04-rs3-data-vendor-stack.md` — the RS-3 deliverable
      from #231: vendor screen (10 vendors evaluated) + concrete 8-test validation
      probe with falsification criteria.
WHY: roadmap items N2 (PIT revision accrual) and M-SIG (3-signal stack) are
     DATA-BOUND — no PIT fundamentals source is wired.
PRELIMINARY RECOMMENDATION (conditional on probe): keep FMP Starter ($29/mo) +
     add Polygon.io Fundamentals add-on ($29/mo) + SEC EDGAR XBRL (free).
     Total = $58/month. CONDITIONAL on: T1 (cost verification), T2-T3 (PIT
     fidelity + restatement handling), T4 (quarterly depth), T5a/T5b (analyst
     recommendation + price-target coverage).
NEXT: operator approves running the validation probe (§6.3); probe
      results determine whether Polygon is the Tier-1 choice or Sharadar SF1
      is required instead.

## Round 2 (Codex review)

Fixed two blocking probe-design gaps plus one tightening:

1. **T3 concrete fixture** — replaced "find a known restatement" with a real,
   reproducible 5-ticker fixture (CVX, KO, GLD, GRMN, DUK), found by querying
   SEC EDGAR's `submissions/CIK{cik}.json` for every ticker in the live 104
   watchlist (142 names) and pulling every `10-Q/A`/`10-K/A` amendment filing.
   53 amendments found; 5 selected for diversity/recency, with real accession
   numbers for both the original and amended filings, and explicit
   pass/fail/falsification criteria (§6.1a). Reused this exact fixture from a
   prior investigation round (closed PR #343) rather than re-deriving it.

2. **T5 scope mismatch** — §1's demand map states the analyst-consensus
   requirement as "ratings, targets, recommendation changes," but the original
   T5 only tested FMP's `grade` endpoint (recommendation-change history).
   Investigated FMP's actual documented API surface and found a genuinely
   distinct endpoint, `stable/price-target-news`, that returns an event-level
   historical timeline of individual price-target changes (`publishedDate`,
   `priceTarget`, `analystCompany` per event) — confirmed LIVE against the
   real FMP key already in use (not just docs): AAPL returned 100 events back
   to 2024-08-02, GRMN 21 events back to 2022-02-28. Chose option (b) —
   broadened T5 into T5a (recommendation history, via `grade`) + T5b (price-
   target history, via `price-target-news`) — since real data confirms the
   target dimension is genuinely testable, not just a documented feature.
   Note: FMP's older `/api/v4/price-target` endpoint is dead for
   post-Aug-2025 subscribers (confirmed via live 402/legacy-endpoint error);
   `price-target-news` is the current, working replacement.

3. **§6.3 tightening** — the "public API docs/examples" framing for a
   zero-cost probe was imprecise: docs establish feature discovery only, not
   live entitlement or real coverage. Rewrote to state explicitly which tests
   require a live Polygon call (T2/T3/T4/T6/T7, none of which are docs-only)
   versus which were already spot-checked live this round (T5a/T5b, against
   the existing FMP key).
