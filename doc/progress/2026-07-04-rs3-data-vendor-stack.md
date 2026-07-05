# RS-3 data-vendor stack — preliminary screen + validation plan

STATUS: DOWNGRADED from recommendation to preliminary vendor screen (round 2,
     Codex review). Not spend-ready.
WHAT: `doc/research/2026-07-04-rs3-data-vendor-stack.md` — the RS-3 deliverable
      from #231: data-vendor stack memo covering FMP tier, Polygon, Sharadar/
      Norgate, and alternatives for PIT fundamentals, analyst consensus,
      quarterly depth, and universe breadth.
WHY: roadmap items N2 (PIT revision accrual) and M-SIG (3-signal stack) are
     DATA-BOUND — no PIT fundamentals source is wired. RS-3 screens candidates
     and specifies what must be verified before any stack is spend-authorized.
ROUND 2 (Codex review — decision-quality, not prose): blocked on (1) the
     $58/mo total resting on a Polygon "$29 Fundamentals add-on" cost the memo
     itself marked unresolved, (2) a vendor feature-matrix instead of a real
     acceptance test against N2/M-SIG's actual PIT-fidelity requirement, (3)
     an unproven analyst-consensus coverage claim.
EVIDENCE gathered this round (not just hedged language):
  - Verified `polygon.io/pricing/fundamentals` returns HTTP 404 — no dedicated
    add-on pricing page exists; Polygon's real site structure is per-asset-
    class (Stocks/Options/etc.) tiered plans, which doesn't match the memo's
    "$29 standalone add-on" premise. Pricing is now marked UNRESOLVED, not
    "unconfirmed but probably $29."
  - Found via Polygon's own docs navigation that analyst-consensus/ratings
    data is served by a separate "Benzinga" partner product
    (`/rest/partners/benzinga/consensus-ratings` etc.), not core fundamentals
    — directly undermining the "covers all four roadmap needs" claim.
  - Queried SEC EDGAR's real submissions API for all 142 names in the live
    104 watchlist; found 53 genuine `10-Q/A`/`10-K/A` restatement filings.
    Built a concrete, reproducible 5-ticker acceptance probe (CVX, KO, GLD,
    GRMN, DUK — real events, real accession numbers) with explicit
    field-level pass/fail/falsification criteria for Polygon's PIT fidelity
    (see memo §4). Not run yet — no live Polygon API key this round — but
    fully specified and ready to execute.
NEXT: (1) get a Polygon trial/paid account to both confirm real pricing and
      run the §4 acceptance probe in one motion — the highest-value next
      step; (2) separately check whether the Benzinga analyst-consensus
      product is actually needed for N3, and its real price, before assuming
      FMP Starter's existing coverage suffices; (3) no spend decision until
      both resolve.
