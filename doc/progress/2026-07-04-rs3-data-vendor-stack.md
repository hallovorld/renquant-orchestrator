# RS-3 data-vendor stack recommendation

STATUS: research memo delivered.
WHAT: `doc/research/2026-07-04-rs3-data-vendor-stack.md` — the RS-3 deliverable
      from #231: data-vendor stack memo covering FMP tier, Polygon, Sharadar/
      Norgate, and alternatives for PIT fundamentals, analyst consensus,
      quarterly depth, and universe breadth.
WHY: roadmap items N2 (PIT revision accrual) and M-SIG (3-signal stack) are
     DATA-BOUND — no PIT fundamentals source is wired. RS-3 recommends a stack.
RECOMMENDATION: keep FMP Starter ($29/mo) + add Polygon.io Fundamentals add-on
     ($29/mo) + SEC EDGAR XBRL (free). Total = $58/month. Polygon provides
     explicit `filing_date` PIT timestamps on quarterly financials. Sharadar SF1
     is the Tier 2 upgrade if Polygon PIT fidelity proves insufficient.
NEXT: operator signs off on Polygon spend; free-tier probe of Polygon + Tiingo
      PIT fidelity before committing; wire SEC EDGAR harvester (engineering).
