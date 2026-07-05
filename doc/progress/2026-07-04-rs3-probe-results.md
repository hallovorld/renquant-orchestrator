# RS-3 validation probe execution

STATUS: probe complete; fixed per Codex review (evidence-quality round).
WHAT: `doc/research/2026-07-04-rs3-probe-results.md` — 7 acceptance tests
      (T1-T7) from the RS-3 validation plan, executed with live API calls.
ROUND-2 FIX: Codex flagged two overclaims — (1) T1's Polygon-cost verdict was
      labeled FAIL on non-official sourcing (comparison articles/changelog
      posts; official pricing page confirmed twice this round to be an
      unscrapable JS-rendered SPA with no pricing API); a fresh re-check
      surfaced a THIRD-PARTY-CONFLICTING $29/mo claim vs. the original $99/mo
      finding, neither official — downgraded T1 to HIGH-RISK/UNVERIFIED rather
      than assert either number as settled; (2) "SEC EDGAR provides the same
      PIT data for FREE" overclaimed proven equivalence — corrected to: EDGAR
      is a verified free RAW PIT source (T7 PASS, real `filed` dates), NOT
      proven equivalent to Polygon's pre-parsed surface in concept
      normalization/restatement handling/coverage convenience.
KEY FINDING (revised): SEC EDGAR XBRL ($0, T7 PASS [VERIFIED]) and FMP Starter
      analyst-consensus (14+ years, T5 PASS [VERIFIED]) are the only two
      claims this probe actually confirmed. Polygon's cost is genuinely
      unresolved, not falsified.
REVISED RECOMMENDATION: proceed with SEC EDGAR XBRL harvester ($0, confirmed)
      for N2/M-SIG PIT needs — because it's the only confirmed-cost option,
      not because Polygon is proven too expensive. FMP Starter (already
      subscribed) covers analyst-consensus.
NEXT: build SEC EDGAR XBRL concept-mapping harvester in renquant-base-data
      (renquant-orchestrator#350 / renquant-base-data#40, already in flight).
      If Polygon is revisited, get an official quote directly rather than
      third-party price citations.
