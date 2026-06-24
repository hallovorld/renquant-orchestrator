# Pre-deploy model-bundle self-consistency check (roadmap eng #1)

STATUS:   PR. New offline tool; no runtime/production change. Validated against the LIVE bundle.
WHAT:     `scripts/check_model_bundle_consistency.py` — runs the FOUR consistency contracts
          that the 2026-06-23 XGB deploy hit one-by-one IN PRODUCTION (each hand-patched):
          (1) artifact present, (2) config fingerprint, (3) watchlist match, (4) calibrator↔
          scorer fingerprint, (5) WF-gate metadata — all OFFLINE, before a deploy. Reuses the
          SAME authorities the live preflight uses (config_consistency.fingerprint_config,
          panel_scorer.model_content_sha256, calibrator metadata fingerprint, wf_gate_metadata),
          so a PASS here means the runtime P-* gates pass too. Exit 0 ready / 1 contract failed
          / 2 cannot evaluate. + 7 unit tests.
WHY-DIR:  the roadmap's #1 engineering fix — "make the build emit a self-consistent bundle so a
          deploy can never hit the 4-guard whack-a-mole again." This is the read-only CHECK half
          (the cheapest, highest-leverage slice); the atomic `promote <bundle>` deploy wrapper is
          the follow-up.
EVIDENCE: run against the live strategy config 2026-06-24 → `deploy_ready: true`, all 5 contracts
          pass (config fp f8fb2259 match, watchlist 145=145, calibrator↔scorer 6fc9985e match,
          wf_gate passed). 7/7 unit tests pass. `[VERIFIED — ran on live config + pytest]`
NEXT:     1) wire it into the deploy path as a hard pre-flight (block deploy on exit≠0).
          2) atomic+reversible `promote <bundle>` wrapper (verify → readonly daily-full asserts
          buys → atomic pin swap → one-command revert) — the roadmap's deploy half.
