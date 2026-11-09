# 2026-11-05 — rq105 quote logger: enforce a request timeout (stop the "collector hung" pages)

STATUS:   delivered, awaiting review — zero reviews at head.
WHAT:     `AlpacaQuoteSource` now wraps the alpaca-py client's `_session.request`
          so every call defaults to `timeout=self._timeout_sec` (20 s); an
          explicit per-call timeout still wins. If the library layout ever
          drops `_session.request` the source raises (fail closed) instead of
          silently running without a timeout. 3 tests.
WHY/DIR:  `timeout_sec` was stored in `__init__` and never used; alpaca-py's
          `RESTClient` creates a bare `requests.Session()` and calls
          `session.request(method, url, **opts)` with no timeout. On a
          half-open socket the call blocks forever, the collector process stays
          alive, `intraday_ticks.jsonl` stops growing, and the watchdog kills
          it only after 900 s of silence. Result: the same "🚨 rq105 DOWN — tick
          feed frozen (collector hung)" page twice on 2026-11-05 (15:22Z, 19:14Z)
          and a 15-30 min hole in the tick record each time. With a timeout the
          failed batch raises inside `sample_once`, which already catches and
          skips the sample, so the loop recovers on the next cadence tick.
EVIDENCE: see §4(b) below.
  artifact:      src/renquant_orchestrator/intraday_quote_logger.py, tests/test_intraday_quote_logger.py (52 passed).
  prod or exp:   exp — takes effect when merged AND `renquant-orchestrator-run` is synced (merged ≠ deployed) and the collector restarts.
  existing data: logs/rq105/quote_logger_crash_2026-11-05.log [VERIFIED 2026-11-05 11:2x PST]: two SILENT STALL kills (frozen 1461 s and 1890 s, collector PID alive), last log line before each = `quote batch failed (RemoteDisconnected)`. alpaca-py 0.43.4 `RESTClient` source [VERIFIED by inspect]: one `self._session.request(method, url, **opts)` call site, no timeout argument.
  best-known?:   yes — anti-vacuity: with the source change stashed the 3 new tests fail (3 failed / 49 passed); with it 52 pass.
  scope:         orchestrator src + tests only; no data/config/artifact touched. Does not address WHY Alpaca drops connections (upstream/network); it bounds the damage to one skipped sample.
NEXT:     merge, then sync `-run` (ask-first) and let KeepAlive restart the collector; the watchdog stays as the backstop.
