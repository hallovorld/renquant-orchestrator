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

## Round 3 (Codex review — §6.3 vs §8 contradiction)

§6.3 correctly said T2/T3/T4/T6 may need Polygon's paid tier; §8 still framed
the *whole* probe as "zero cost, uses free tiers + existing FMP key." Both
couldn't be the contract.

Resolved using PR #348's actual executed results (this memo's own validation
plan, run the same day): T1, T5a, T5b, T7 are genuinely zero-cost (T1 via web
research — comparison articles + Polygon's changelog, no signup; T5a/T5b via
the existing FMP key; T7 via SEC EDGAR's free API) and ALL FOUR were run
without needing any spend decision. T1 FAILED first (real cost $99–298/mo,
not $58/mo per PR #348), which made the paid-tier tests T2/T3/T4/T6 moot —
they were never run and no Polygon spend was ever requested. So the "zero
cost" claim in §8 was true in outcome (nothing was ever paid for), but the
original wording implied the *entire* 8-test probe was zero-cost by
construction regardless of outcome, when §6.3 itself said otherwise for
T2/T3/T4/T6. Rewrote §6.3 to explicitly split the zero-cost tests from the
paid-tier-gated ones and state the sequencing rule (run zero-cost first; T1
alone can falsify before any paid-tier spend is needed), and rewrote §8 to
reflect that the zero-cost path already ran, Polygon was already disqualified,
and the operator decision now needed is the SEC EDGAR harvester effort (PR
#350), not a Polygon spend approval. Added a cross-reference at the top of
the memo pointing to PR #348 as the executed-results follow-on, since this
memo is now the probe DESIGN record and #348 is the RESULTS record.
