# SEC EDGAR XBRL harvester

STATUS: revised — extraction logic relocated to renquant-base-data per Codex
     review; this repo now carries a thin scheduling wrapper only.
WHAT: `src/renquant_orchestrator/sec_edgar_harvester.py` — subprocess-invokes
      `renquant_base_data.sec_edgar_companyfacts_harvester` (base-data PR #40)
      against a ticker list or watchlist file, records provenance
      (content sha256, record/ticker counts), matching the
      `pit_revision_collector.py` wrapper pattern. 7 tests in
      `tests/test_sec_edgar_harvester.py`. The original
      `scripts/sec_edgar_harvester.py` (a full ingestion/parsing
      implementation) and its 22 tests were removed — that logic now lives
      in base-data.
WHY: RS-3 identified SEC EDGAR as the free PIT ground-truth data source for
     N2 (PIT revision accrual) and M-SIG validation. No vendor subscription
     needed.
WHY-DIR: Codex blocked the original PR on two issues: (1) repo-boundary —
     orchestrator orchestrates pinned subrepos and schedules/verifies data
     workflows, it should not be the primary home for vendor/data-source
     extraction logic; (2) an output-contract bug where
     `RevenueFromContractWithCustomerExcludingAssessedTax` mapped to a
     different field name (`revenue_alt`) than the plain `Revenues` tag
     (`revenue`) — the same economic concept splitting across output field
     names by issuer/accounting era. Both are fixed in base-data PR #40 (see
     its own progress doc for the field-normalization + resumability fixes);
     this PR now only schedules/wraps that module, matching the
     `fmp_estimate_revisions` / `pit_revision_collector.py` precedent, and
     the `AlpacaBrokerPort` (orchestrator → renquant-execution, PR #291) /
     `SoftwareStopRegistry` (umbrella → renquant-pipeline, PR #167)
     relocation precedent from earlier this session.
EVIDENCE: 2259/2261 relevant tests pass (2 pre-existing, unrelated failures
     in `test_bundle_consistency_ci_gate.py` reproduce identically on clean
     `origin/main`). `data/strategy_snapshot.json` regenerated to include
     the new module (M9 doc-alignment check).
FIELDS: revenue, net_income, eps_diluted, total_assets — each with `filed_date`
     (the PIT timestamp), fiscal year/period, form (10-K/10-Q), accession number.
SAFETY: never writes to `data/` canonical paths; output to CLI-specified path
     or stdout; rate-limited to ≤10 req/sec per SEC rules; graceful error
     handling (skip + continue on failures).
NEXT: land base-data PR #40 first, then this PR. Run against the full
     watchlist to validate coverage; cross-check with Polygon (RS-3 probe T7)
     when Polygon access is available.

## Round 2 (Codex review — provenance overwrite bug)

Codex found the wrapper's provenance filename was keyed on date alone
(`sec_edgar_harvest_<date>.json`), so two same-day harvests (a rerun, or a
second watchlist) silently overwrote each other's provenance record, losing
the earlier run's output hash/count/path. Fixed: filename now embeds a
timestamp (matching `retrain_patchtst.py`'s `weekly_%Y%m%dT%H%M%SZ`
run-artifact convention) plus a `uuid4` suffix (matching
`intraday_live_executor.py`'s `la-{uuid.uuid4().hex[:16]}` action-id
pattern), guaranteeing uniqueness per invocation regardless of timing or
identical output content. Added
`test_harvest_provenance_unique_across_same_day_reruns`, which asserts two
back-to-back harvests produce two distinct provenance files — confirmed
this collides deterministically pre-fix (both invocations construct the
identical `sec_edgar_harvest_<today>.json` path, not just a probabilistic
same-second race). 2260/2262 relevant tests pass (2 pre-existing, unrelated
`test_bundle_consistency_ci_gate.py` failures reproduce identically on clean
`origin/main`).
