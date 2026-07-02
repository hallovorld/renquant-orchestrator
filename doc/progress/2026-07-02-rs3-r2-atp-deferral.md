# RS-3 r2 — ATP deferral addendum

STATUS:   research addendum (docs only) under the delegated-decision protocol; triggered by
          operator cost review, which was CORRECT.
REVISION: r2 addendum to the merged RS-3 memo.
WHAT:     ATP ($99/mo) DEFERRED: 11%/yr of the current book for measurement precision is
          disproportionate; opening prints come from daily bars; Stage-1 is observe-only so
          the IEX bias is accepted + documented per #223 A5.3's second path (feed identity
          labeled per row). Re-trigger: M2 canary go-live OR book ≥$50k. FMP Starter
          confirmed subscribed (key-metrics + 10y estimates verified) — need (a) fully
          covered; it is not and was never a substitute for the tape need (b). Steady-state
          new spend now $0/mo.
WHY/DIR:  the delegation protocol at work: a recommendation challenged with a better
          argument gets revised on the record, not defended.
EVIDENCE: FMP stable key-metrics + 10-row annual estimates probes (2026-07-02); S10 used
          daily-bar opens + 10min VWAP (no live SIP dependency); book PV $10.8k.
NEXT:     collectors keep accruing under the documented IEX regime; the re-trigger
          conditions enter the M2 checklist.

## r3 (2026-07-02, Codex review): feed provenance, decision-risk, re-trigger, contradiction fixes

**Finding.** Four issues in the r2 addendum: (1) "opening prints come from daily bars" was
asserted without evidence and never established the actual producer/feed, while the repo's
own `dual_source_price_audit.py` states production ohlcv comes from yfinance and the Alpaca
loader forces `DataFeed.IEX` — neither is the "official" bars the r2 text implied; (2)
"observe-only" was conflated with "safe" — it removes execution risk but not decision risk
(a biased diagnostic can still produce a wrong go/kill call that later gates real capital);
(3) the "book ≥ $50k" re-trigger was arbitrary — ATP is still ~2.4%/yr of book at that exact
threshold, which the memo's own "11%/yr is disproportionate" logic doesn't resolve; (4) the
addendum's corrected recommendation was never propagated to the memo's own top-of-file
recommendation table/steady-state paragraph, leaving the document contradicting itself.

**Fix.** Traced the actual code (not assumed): S10's daily-open reference
(`data/ohlcv/<T>/1d.parquet`, read at `scripts/s10_open_auction_is_study.py:120`) is yfinance
per `dual_source_price_audit.py`'s own docstring; S10's true-VWAP reference
(`data/intraday/<T>/10min.parquet`) is Alpaca-sourced via the same `StockBarsRequest` path
used elsewhere in this codebase (`renquant_pipeline/kernel/data.py:571`, explicit "Force IEX
feed" comment) — IEX, not SIP. Documented both provenances explicitly in the memo, with the
known bias direction for each (yfinance's occasional divergence from official closes; IEX's
~2-3% partial-tape coverage skew). Added an explicit valid/prohibited-metric list for
decision-gating under IEX-only coverage, plus the A/B-or-SIP-evidence bar required before
promoting any currently-prohibited metric. Replaced the $50k account-size trigger with (a)
M2 canary go-live (unchanged, valid) OR (b) a named decision clearing an explicit 5%/yr-
of-book budget cap (a budget-fraction rule, not a bare dollar threshold, so it scales
correctly if ATP's price changes). Rewrote the memo's top recommendation-table row and
steady-state paragraph (previously described ATP as "conditional GO, pending entitlement
verification" and a near-certain $99/mo, contradicting the deferral below it) to state
plainly: ATP deferred, $0/mo now, re-trigger per the corrected conditions above.

**Evidence:** `grep -n "yfinance" scripts/engineering/dual_source_price_audit.py` (production
prices, docstring); `grep -n "DataFeed.IEX" -B3` in `renquant-base-data/loaders/data.py` and
`renquant-pipeline/kernel/data.py:571` (explicit "Force IEX feed" comment); `scripts/
s10_open_auction_is_study.py:120,134` (the actual read paths S10 uses).

NEXT: the A/B SIP-vs-IEX capture (already required before any ATP subscribe) will also
directly quantify how much of S10's ±80bps true-VWAP CI width is feed-driven vs. genuine —
worth folding into that capture's analysis when it eventually runs.
