# GOAL-5/#682: the 19 uninspected umbrella wrappers are now read — 0 carry the fallback

STATUS: complete (option 2 of #682, the no-authorization path).
WHAT: `check_wrapper_pythonpath_roots` gains an `inspect: "read-only-here"`
boundary mode — the scanner READS the declared wrapper across the repo boundary
(never writes, never git — the umbrella rule forbids those, not reads) and runs
the SAME fallback-idiom scan via a shared helper, so the two paths cannot
drift. An unreadable subject is a PROBLEM, not a skip. The umbrella-scripts
boundary in the reviewed manifest flips to the new mode with a corrected `why`
(the old text claimed reading was forbidden; #682 itself corrects this).
WHY/DIR: #682 measured 19 of 33 manifested wrappers (incl. daily104) inspected
by no reviewed scan; its AC wants every wrapper inspected or covered by a
boundary naming a specific inspecting mechanism, with unowned == 0.
EVIDENCE:
  artifact:      ops/run_surface_drift_check.py (_scan_wrapper_text + the
                 inspect-mode branch), ops/launchd_manifest.json (boundary),
                 tests/test_wrapper_pythonpath_roots.py (+5 tests incl. a pin
                 on the live manifest's inspect mode)
  prod or exp:   prod — the daily run-surface drift scan
  existing data: live scan after the change: 13 local + 19 cross-repo = 32 of
                 33 wrappers inspected; 1 out of scope (pinned runtime,
                 pin-governed); 0 unowned. **0 of the 19 umbrella wrappers
                 carry the fallback idiom** — the "unread is unread" gap closes
                 with a clean measured answer; the 5 known rq105 LOCAL fallback
                 findings are unchanged (their remediation is #736's sync,
                 operator-gated). `[VERIFIED — scanner run on this branch,
                 2026-08-02]`
  best-known?:   yes — supersedes the out-of-scope info line for these 19; the
                 stronger option 1 (umbrella owns the check) stays open in #682
  scope:         ops/ scanner + manifest boundary + tests; 19/19 file tests,
                 437 passed across drift/wrapper/manifest suites
                 `[VERIFIED — pytest, 2026-08-02]`
NEXT: #682 can close on merge per its AC unless the operator prefers option 1
(umbrella-owned scanner); the .subrepo_runtime boundary stays owner-mode
because pin review governs its contents. AC6 gate-design rule: N/A — a
read-only telemetry scan, no capital-admission gate.
