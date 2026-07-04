# Progress: execution_audit test fix for renquant-execution's new n_skipped field

STATUS:   fixed; test-only change, no production behavior change.
WHAT:     `tests/test_native_execution_payload.py`'s
          `test_build_readonly_execution_payload_does_not_connect_to_broker`
          asserted an exact `execution_audit` dict that no longer matches
          `renquant_execution.execution_payload()`'s current output.
WHY-DIR:  `renquant-execution#22` (fractional order support, merged) added
          an `n_skipped` field to the audit dict. This orchestrator test
          pins the whole dict by equality, so it went stale the moment CI's
          multirepo checkout picked up execution's new main — reproduces
          identically on orchestrator's own main, unrelated to any
          orchestrator-side change.
EVIDENCE: Reproduced the failure on unmodified `main` first (confirming it
          wasn't specific to any in-flight PR), then added `n_skipped: 0` to
          the one affected assertion (the other `execution_audit` assertion
          in this file is the no-trade bridge-context path, a different
          code path, unaffected). 1588/1588 tests pass.
NEXT:     none — this is a complete, self-contained fix.
