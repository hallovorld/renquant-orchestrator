# Wire parking_sleeve into CLI + scheduled jobs

STATUS: delivered
WHAT: Wire the existing `parking_sleeve` module (S7 shadow allocator) into the
orchestrator's operational paths: CLI subcommand + scheduled job + job runner.
WHY/DIR: The module was implemented and tested (#228) but not wired into the
CLI or scheduler, making it unreachable from the operator control plane.
EVIDENCE:
- `renquant-orchestrator parking-sleeve --book-state-json <path>` works
- `renquant-orchestrator run-job parking_sleeve_shadow -- --book-state-json <path>` works
- `renquant-orchestrator scheduled-jobs` includes `parking_sleeve_shadow` (daily, ops)
- 25 parking_sleeve tests pass, 2 new CLI tests pass, scheduled_jobs counts updated
NEXT:
- Wire book-state source for automated daily post-close runs (account snapshot adapter)
- Session-tick integration for 105 real-time loop (per module docstring)
- Pre-registration gate per RS-1 section 4 / #228 section 1.3 before arming
