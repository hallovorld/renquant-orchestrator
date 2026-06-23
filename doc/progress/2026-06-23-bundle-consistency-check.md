# Pre-deploy model-bundle consistency check

STATUS:   implemented (engineering roadmap #171, short-term: kill the deploy whack-a-mole).
WHAT:     scripts/check_model_bundle_consistency.py — one offline command that runs the
          FOUR consistency contracts a model bundle must satisfy before deploy, reusing the
          live preflight authorities (fingerprint_config, model_content_sha256, calibrator
          binding, wf_gate_metadata, watchlist).
WHY/DIR:  the 2026-06-23 XGB deploy hit those four contracts one-by-one IN PRODUCTION, each
          patched by hand (re-stamp WF metadata, re-fit calibrator, re-stamp config fp,
          re-stamp watchlist). All four are checkable offline → catch the whack-a-mole here.
EVIDENCE: run against the live deployed config → deploy_ready=True, all 5 contracts PASS
          (config fp f8fb2259 match, watchlist 145=145, calibrator/scorer 6fc998 match,
          wf passed=True numerics complete). 7 unit tests cover each FAIL path via a
          synthetic bundle + injected fingerprints. `[VERIFIED — live run + pytest this session]`
NEXT:     wire it as a hard pre-deploy gate in the promote/deploy flow; then the atomic
          self-consistent bundle BUILD so the contracts pass by construction.
