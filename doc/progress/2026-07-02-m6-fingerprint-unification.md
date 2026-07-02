# M6 fingerprint unification design — design PR

STATUS:   design for review (docs only; renquant-common + migration PRs follow).
REVISION: r1.
WHAT:     `doc/design/2026-07-02-m6-fingerprint-unification.md` — M6/R2 (#231 Term PROCESS):
          the measured divergence (pipeline = SUBTRACTIVE denylist at panel_scorer.py:108;
          model = ADDITIVE ~12-field allowlist at fit_calibrator_alpha158_fund.py:35;
          umbrella's calibrator script IMPORTS the pipeline impl — the "three hand copies"
          belief corrected to two divergent semantics + one import) and the shared contract:
          renquant_common.model_fingerprint with TOTAL classification (unclassified key
          fails LOUDLY at stamp time — the silent defaults in both current impls are the
          root cause), fingerprint_schema_version stamped alongside, version-gap as its own
          explicit error, dual-hash migration window, cross-repo identity fixtures.
WHY/DIR:  three fail-closed no-trade incidents (05-27/06-22/07-01) share this root cause;
          each manual re-stamp mutates the artifact and re-arms the trap. Total
          classification converts "new field ⇒ silent false match/mismatch" into "new field
          ⇒ loud stamp-time error," which is the only failure mode that gets fixed before it
          trades.
EVIDENCE: read-only code inventory with file:line cites (2026-07-02); incident dates from
          the memory record.
NEXT:     Codex review; implementation order: common module+fixtures → model/pipeline
          migrations → umbrella re-point → 30-day zero-incident watch (the #231 M6 AC).
