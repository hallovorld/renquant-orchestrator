# RS-3 validation probe execution

STATUS: probe complete; RS-3 cost claim FALSIFIED.
WHAT: `doc/research/2026-07-04-rs3-probe-results.md` — 7 acceptance tests
      (T1-T7) from the RS-3 validation plan, executed with live API calls.
KEY FINDING: Polygon Financials add-on is $99/mo (not $29/mo as RS-3 claimed).
      Cost boundary breached by 3-10x. SEC EDGAR provides the same PIT data
      for FREE (verified: `filed` field = real SEC filing date, 10+ years depth).
      FMP Starter analyst-consensus coverage = 14+ years (far exceeds need).
REVISED RECOMMENDATION: start with SEC EDGAR XBRL harvester ($0) for N2/M-SIG
      PIT needs; FMP Starter (already subscribed) covers analyst-consensus.
NEXT: build SEC EDGAR XBRL concept-mapping harvester in renquant-base-data.
