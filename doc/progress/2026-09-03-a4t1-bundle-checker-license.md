# Bundle checker accepts the RFC#210 A4-T1 stamp in lockstep with the live preflight   (PR TBD)

STATUS:    delivered — companion to renquant-pipeline#308.
WHAT:      `scripts/check_model_bundle_consistency.py` `wf_gate_metadata`
           contract: when the artifact is rfc210-served AND carries the A4-T1
           stamp (`fallback_a4t1_override is True`, run id in
           `A4T1_LICENSED_RUN_IDS = {"20260831T141820Z"}`, `today <=
           fallback_a4t1_expiry`, orchestrator consumption receipt present),
           the missing Sharpe numerics / SPY cut count no longer fail the
           contract; the detail line says `a4t1=licensed(run=… until …)`.
           Any defect in the stamp (window closed, other run id, no/empty
           receipt, override not literally True, malformed expiry) or an aged-
           out artifact keeps the numerics requirement. 11 new tests.
WHY/DIR:   `make doctor` / the 13:55 PT DOCTOR page read `[RED ] bundle_consistency:
           … 'wf_3cut_sharpe_mean', 'strategy_minus_spy_sharpe_mean'] override=None`
           after the A4-T1 promotion: the licensed candidate has no round-trips,
           so it carries no Sharpe numerics, and the checker's job is "what the
           live P-WF-GATE needs for buys" — which pipeline#308 now answers with
           the same stamped, self-expiring license. Rules kept in LOCKSTEP with
           `renquant_pipeline.kernel.rfc210_license` (same fields, same run-id
           set, same expiry semantics). Direction: G-F AC4 (DOCTOR truthful).
EVIDENCE:  artifact:      ntfy "RenQuant 104 DOCTOR" 2026-09-03 13:55 PDT (bundle_consistency RED) [VERIFIED — ntfy cache]
           prod or exp:   prod ops check (doctor, non-fatal); no trading path
           existing data: `tests/test_check_model_bundle_consistency.py` + `test_bundle_consistency_ci_gate.py` + `test_model_bundle.py`: 41 passed (30 existing + 11 new) [VERIFIED — 2026-09-03 14:40 PDT]
           best-known?:   n/a — consistency check, no model claim
           scope:         "this changes one contract's acceptance for exactly the stamped A4-T1 artifact until 2026-09-07; every other artifact is judged as before"
NEXT:      merge → `-run` ff-only (system_doctor reads the orchestrator runtime checkout) → next DOCTOR shows bundle_consistency green for the served pair; after 2026-09-07 the stamp expires and the numerics requirement returns.
