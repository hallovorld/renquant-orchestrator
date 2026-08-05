# 2026-08-05 — GOAL-3: the 42-candidate work list is really a 5-candidate work list

## What the census left open

orch#814 landed a duplicate-definition census: 42 names in
`renquant_orchestrator` defined in more than one file, none exported, and its own
output insisted a duplicate is **a candidate, not a verdict**. Its NEXT said:
read down the list, retrain Tasks first.

Reading four of them (in review) found **zero** twins — each Task is instantiated
only by its own module-local job. That is a result about four names. This
measures the property behind it, for all 42.

## The measurement `[VERIFIED — this session]`

For each duplicate name, how many modules import it **by name**:

| reachability | count | what it means |
|---|---|---|
| never imported by name | **29** | module-local; nothing refers to the name, so no caller can reach the "other" definition |
| exactly one source module | **8** | unambiguous at every import site |
| **MULTI-SOURCE** | **5** | a reader could expect one implementation and get another |

The five:

| name | imported from |
|---|---|
| `main` | 33 CLI modules — each importing its own; the degenerate case |
| `connect` | `decision_ledger`, `decision_pnl_attribution`, `renquant_common.decision_ledger`, `attribution.ledger`, `risk_budget.budget` |
| `render_markdown` | `attribution.report`, `risk_budget.report` |
| `emit_alert` | `outage_monitor`, `weekly_promote_monitor` |
| `default_tick_feed_path` | `realtime_data_plane`, `intraday_quote_logger` |

**So the work list is 4 names, not 42** (`main` is noise). That is a 90 %
reduction in what a human has to read, and it is derived rather than asserted.

## What this does NOT say

- **Multi-source is not a defect.** `from a import J` and `from b import J` are
  each unambiguous; the risk is a *reader* assuming the wrong one, not the
  interpreter resolving wrongly. None of these five is a twin in the pipeline
  sense (one implementation shadowing another behind a shared export) — the
  orchestrator exports 3 names and none of the 42 is among them.
- **29 "never imported" is not a clean bill.** It means nothing refers to those
  names *inside this package*; a script or a test could still import a module
  path directly. It removes them from the confusion work list, not from
  existence.
- Nothing here judges whether any duplicate should be de-duplicated. Two
  implementations of `emit_alert` may be perfectly reasonable.

## Why it belongs in the tool rather than a comment

The census already prints a work list. A work list that does not say which items
a caller can actually confuse invites the next reader to do all 42 — which is how
the four already-read ones got read in review rather than by design.

Suites: 23 tests in this file (5 new), incl. one bound to the live breakdown ·
5686 passed, 2 skipped `[VERIFIED — measured]`.
