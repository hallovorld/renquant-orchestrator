# Analyst-data source strategy — decision recorded

STATUS:   decision/reference PR. No code change. Records the source plan + the MCP query
          method so it's reproducible (operator: "记一下策略 + MCP 的 prompt").
WHAT:     doc/decisions/2026-06-25-analyst-data-source-strategy.md.
DECISION: complete analyst data (full coverage + multi-year history) needs a paid/entitled
          source — no free one gives both (FMP free 30%/7.5y; Finnhub free full/4mo; yfinance
          full/multi-yr but signal-negative). Priority: (1) financial-analysis MCP
          (FactSet/S&P/Morningstar — $0 if entitled, try OAuth first); (2) FMP paid Starter
          ~$22/mo (the #24 fetcher works immediately, collect today); (3) EOD Historical Data.
          Finnhub cron (#408) accumulates a free full-coverage series meanwhile.
COST:     account ~$10.6k → $22/mo ≈ 2.5% equity/yr; edge UNPROVEN (FMP prelim inside noise).
          Prefer free/entitled; cap paid at ~$22–50/mo; VALIDATE (WF / #190) before a recurring fee.
MCP:      recorded the auth flow (authenticate → operator authorizes → complete_authentication →
          data tools load) + the intended per-ticker queries (consensus distribution history +
          estimate-revision counts) + the map to the shared (ticker,period,consensus,...) schema.
NEXT:     try the MCP OAuth (FactSet or S&P) — if entitled, build an MCP-backed base-data fetcher;
          else FMP $22 upgrade (verify ADI/NFLX unlock) → collect today via the #24 code. Then a
          complete dataset → signal validation → (only then) feature-engineering + retrain PRs.
