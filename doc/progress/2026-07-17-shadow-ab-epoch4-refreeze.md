# Two-arm shadow-ab: epoch-3 retirement + epoch-4 refreeze at current pins

STATUS: delivered (operational refreeze; sanctioned surface)
WHAT: the two-arm harness fail-closed at PRECHECK from 2026-07-14 onward
because the GOAL-5/G4 deployments of 07-16/17 (orchestrator 28b1d2ba,
pipeline 7108f514, strategy-104 0d45d960, artifacts/base-data advances)
legitimately moved the runtime world past the epoch-3 manifest frozen
2026-07-11 (pins-20260710-final). Rotation performed per the epoch-2
precedent: epoch-3 state archived
(archive/epoch3-freeze-20260717T221343Z/ with EPOCH-NOTE), a new
run_manifest.json written at the current runtime HEADs
(data_revision pins-20260717-goal5-g4, 9 repos), shadow_ab_freeze.json
retired (the runner self-creates epoch-4's on the first real session per
protocol), counters reset to zero. PRECHECK verified passing: 9 repos
resolved, clean.

FREEZE BOUNDARY (binds the G1 v4 null fit, RenQuant#494 §4.7): epoch-3
counted attempted_pairs=4 / excluded_pairs=3, and per renquant-model#60's
PIT parity backfill ALL epoch-3-era sessions are schedule-mismatched under
the close-anchored as-of contract. Epoch-3 sessions are NOT poolable with
epoch-4+ sessions for the ≥40-paired-session null calibration; the fit
uses epoch-4+ only (and epoch-4 itself may be superseded if model#61's
next-open re-registration changes the session convention — in that case
the fit starts from the post-schedule-freeze epoch).

WHY/DIR: G1's paired-session accumulation was silently stalled since
07-14 (surfaced by the AC1 sentinel's launchd sweep on its first firing);
this restores it at a consistent world.
EVIDENCE: PRECHECK PASS — 9 repos verified (2026-07-17T22:13Z rotation).
NEXT: first epoch-4 session at the next 14:35 PT firing (2026-07-20
Monday, next NYSE session day); the runner self-freezes epoch-4 then.
