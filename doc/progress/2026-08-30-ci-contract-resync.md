# CI contract resync — emitter line pins + twin parity broker digests

STATUS:   delivered. 4 pre-existing test failures fixed by re-deriving
          contracts against the current umbrella tree.
WHY/DIR:  the 4 failures were live-tree-dependent integration tests that
          drifted after reviewed upstream changes (wf_promote_outcome.sh
          shared-lib adoption shifted emitter lines; broker-resilience
          deploy #41/#286 changed broker digests). All upstream changes
          were already reviewed and merged.
EVIDENCE:
  artifact:      emitter_contract.json: 9 line pins shifted (+3 each),
                 1 wrapper digest updated. twin_parity_manifest.json:
                 3 broker digests re-pinned (broker.py, alpaca_broker.py,
                 broker_readonly.py). Re-derived via the canonical tools
                 (`recapture_emitter_contract`, `check_twin_parity
                 --write-manifest`).
                 104 tests passing from the 3 affected test files
                 [VERIFIED — pytest run 2026-08-30].
  prod or exp:   exp — no production path written; no launchd/manifest
                 change; these are CI-only contract files.
  scope:        2 data/ops contract files. No code change.
REVIEW:    codex (haorensjtu-dev).
