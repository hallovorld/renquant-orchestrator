# SEC EDGAR XBRL harvester

STATUS: delivered.
WHAT: `scripts/sec_edgar_harvester.py` — CLI script to harvest quarterly/annual
      financial facts from SEC EDGAR's free XBRL API with PIT `filed` dates
      preserved. 22 tests in `tests/test_sec_edgar_harvester.py`.
WHY: RS-3 identified SEC EDGAR as the free PIT ground-truth data source for
     N2 (PIT revision accrual) and M-SIG validation. No vendor subscription
     needed.
FIELDS: revenue, net_income, eps_diluted, total_assets — each with `filed_date`
     (the PIT timestamp), fiscal year/period, form (10-K/10-Q), accession number.
SAFETY: never writes to `data/` canonical paths; output to CLI-specified path
     or stdout; rate-limited to ≤10 req/sec per SEC rules; graceful error
     handling (skip + continue on failures).
NEXT: run against the full watchlist to validate coverage; cross-check with
     Polygon (RS-3 probe T7) when Polygon access is available.
