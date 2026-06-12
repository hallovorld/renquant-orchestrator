# Night Report — 2026-06-12 (epic/model-edge-experiments)

## Shipped tonight (each its own commit, each with executable proofs)

| # | Commit | What | Plan ref |
|---|---|---|---|
| 1 | census_ci.py | reproducible metrics w/ SHAs; ruled buy_blocked=**17** | I.1 |
| 2 | live_state_v2_prototype.py | parses REAL prod state; round-trip; unknown-key quarantine | III.4 |
| 3 | gate_registry_prototype.py | verdict algebra; 2,000 randomized property proofs | III.4 |
| 4 | artifact_resolver_prototype.py | one resolution authority; #114-class impossible | III.5 |
| 5 | agent_breaker_prototype.py | G2: runaway loop bounded at cap; TRADING_OFF dominates | Week-0 |
| 6 | gtc_catastrophe_planner_prototype.py | G1: **broker stops = NONE today**; plan computed, idempotent | Week-0 |
| 7 | score_drift_audit_prototype.py | PSI audit; live run flags CRITICAL (pin-stack change day) | L6 |
| 8 | alert_lifecycle_prototype.py | 121 daily warnings → 2 notifications + scope block | L6 §12.3 |
| 9 | config_schema_prototype.py | typed top level; sign-flip typo caught at load | S1-PR6 |
| 10 | decision_pnl_attribution_prototype.py | 594-day decision↔outcome join | III.6 |
| 11 | drph_core.py | canonicalizer, fingerprint, localizing diff | S1-PR3 |
| 12 | staleness_preflight.py | cutoff-based; **prod = FAIL (18.9 months)** | #106 §2.3 |
| 13 | broker_reconciliation_sm.py | explicit transitions incl. the real GE/META/HON event | III.4 |
| 14 | pit_reader.py | publication-lag enforced; look-ahead = API impossibility | III.2 |
| 15 | bug1_pipeline_divergence_probe.py | **bug #1 RESOLVED**: hand-pipeline methodology defect; native −0.0915 stands | IV.3 |
| 16 | label_uniqueness_stats.py | ESS of 346k-row panel ≈ **5,901** (uniqueness ~1/59) | #106 contracts |
| 17 | secrets_scan.py | 10 repos clean: no tracked .env, no keys in history | §16.4 |
| 18 | backup_tier1.py | first restore-verified backup ever; 14-snapshot retention | §16.3 |
| 19 | clock_tz_audit.py | **217 naive time sources**; next DST 2026-11-01 | III.4 |
| 20 | fstore_incremental_poc.py | incremental ≡ full (rtol 1e-12); speedup honest-noted | III.3 |
| 21 | renovate_subrepos.json | auto pin-bump PRs config, deploy-ready | §14 |
| 22 | decision_ledger.py | DDL+writer; false-BEAR autopsy = ONE query (real backfill) | IV/III.6 |
| 23 | env_fingerprint.py | env_sha completes the run fingerprint; mutation diffs | III.5 |
| 24 | dual_source_price_audit.py | **IBM 4.4% CRITICAL divergence; LEAN AAPL export 7 weeks stale** | L6 |

## Running on the GPU while you slept (#106, operator-ordered)
- **cross-stock strict A/B** (`xstock_strict_trainfit_seed44`, same recipe/
  cutoff as prod) — ETA ~05:30; paired comparison vs prod's val year is the
  morning's first analysis (DSR/PBO protocol per #109 errata).
- **3-seed variance chain** (seeds 45, 46, prod recipe) queued behind it.

## Findings that need operator eyes
1. Broker-side stops = NONE (G1) — approve S0-PR-G1 wiring ASAP.
2. Staleness preflight FAILs prod (18.9 months past cutoff) — the fresh-
   cutoff retrain needs the panel extension (daily pipeline work).
3. Attribution headline (selected < vetoed next-day return over 594 mixed-era
   days) — needs era/horizon conditioning before conclusions; table now exists.
4. LEAN daily export silently stale 7 weeks (AAPL) — staleness audit catch.
5. ESS ≈ 5,901: tempers #106-1.2 model-scaling expectations.

## Multi-agent caveat
Branch races with codex occurred twice tonight (commits landing on local
main, silent push losses). All recovered; the §14 fixes are not optional.
