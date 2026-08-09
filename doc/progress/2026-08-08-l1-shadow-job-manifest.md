# L1 exposure-shadow job — manifest legitimisation (operator grant 「开」)

STATUS:    the job is INSTALLED and LOADED (com.renquant.l1-exposure-shadow,
           weekdays 15:30 local, production venv + sibling-src PYTHONPATH);
           this PR is the same-batch reviewed-surface update the containment
           protocol requires. Until it merges, the run-surface drift scan
           correctly alarms "unmanifested job" — that alarm is the DESIGNED
           reminder and is being closed by review, not silenced.

WHAT:      ops/launchd_manifest.json += com.renquant.l1-exposure-shadow with
           program_args and program_args_sha256 computed by the drift check's
           own recipe (sha256(json.dumps(program_args))).

WHY/DIR:   Operator granted the L1 shadow phase 2026-08-08 ("开"); orch#920
           (the logger) merged; issue #921 tracks the installation with
           literal revert steps. The job logs target-vs-achieved exposure
           components daily; no orders, no config.

EVIDENCE:  artifact:      installed plist (plutil-linted, bootstrapped,
                          launchctl-listed) [VERIFIED — install session];
                          module import verified under the PRODUCTION venv
                          (RenQuant/.venv) with the sibling-src PYTHONPATH
                          [VERIFIED — import run]; drift check flags exactly
                          the expected unmanifested-window finding
           prod or exp:   prod run surface — under the standing operator grant
           existing data: 39 manifest entries; this adds the 40th
           best-known?:   n/a — ops change
           scope:         one manifest entry + this record. Schedule 15:30
                          weekdays = after daily104 (13:55 + runtime) so the
                          snapshot is fresh and the stale-snapshot refusal
                          passes without the override flag.

TESTS:     drift check run twice this session: before the manifest edit it
           alarms on the unmanifested job (expected window); the entry's
           digest is computed by the checker's own recipe so post-merge the
           finding closes. Logger behaviour itself: 6 tests, orch#920.

NEXT:      first scheduled row next trading day (Mon); confirm the row lands
           and the drift finding closes post-merge; then weekly gap digest
           in the ops report, and L2's paper-bandit engine.

CORRECTIONS (review r1):
           r1 caught the entry sitting at the manifest TOP LEVEL instead of
           under "jobs" — the only surface the consumers read
           (run_surface_drift_check.py and kernel_surface_census.py index
           manifest["jobs"]), so at the r1 head the reviewed surface was
           still missing the job and this doc's "finding closes post-merge"
           claim was false. Fixed: entry moved under "jobs" (sorted
           position; digest unchanged and re-verified against the checker's
           recipe), and the same rewrite's accidental —-escaping of
           unrelated entries reverted. Re-run on the fixed head:
           check_launchd_loaded_undeclared = 0 problems, and
           check_launchd_surface / check_launchd_loaded report no
           l1-related findings [VERIFIED — in-session run, 2026-08-08].
