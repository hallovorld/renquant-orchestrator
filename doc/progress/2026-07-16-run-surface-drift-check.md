# GOAL-5 AC2: run-surface drift scan

STATUS: delivered
WHAT: `ops/run_surface_drift_check.py` + committed baseline
`ops/launchd_manifest.json` (35 jobs). Alarms on: runtime repos off their
subrepos.lock.json pins or carrying uncommitted tracked changes;
orchestrator-run off origin/main or dirty; any com.renquant.* launchd
ProgramArguments differing from the reviewed manifest, unmanifested new
jobs, or manifested jobs missing from disk. Untracked files are info-only.
Disabled/.bak plists excluded. plistlib + plutil fallback (two annotated
plists have XML comments expat rejects). The umbrella live working tree is
deliberately OUT of alarm scope (operator edit surface; artifact integrity
= AC4 bundle work). deploy/ plist TEMPLATE (07:00 PT daily) — install is
operator-gated.
WHY/DIR: GOAL-5 P0 week-1 — the 07-15 silent containment (daily104 swapped
to a /tmp wrapper) and the orchestrator-run checkout's 6 un-upstreamed
hotfixes were both invisible for days. This scan makes either loud within
one firing; an intentional change updates the manifest/refs in the same
reviewed PR (see CONTAINMENT PROTOCOL).
EVIDENCE: 13 tests incl. the containment drill (daily104 swapped to
/tmp/renquant104-sell-only-guard.sh MUST alarm — it does) and a live-state
test pinning the committed manifest to this machine's actual surface.
Live scan on the current machine: OK (clean baseline).
NEXT: deploy = load the plist (operator landing); AC2 drill = benign
manifest edit → next firing alarms.
