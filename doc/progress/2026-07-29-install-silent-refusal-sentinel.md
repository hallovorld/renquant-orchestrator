# Progress: silent-refusal sentinel installed (operator-authorised)

STATUS:   INSTALLED on this machine and registered in the reviewed manifest in the
          same batch, per the containment/run-surface rule.

WHAT:     Adds `ops/renquant104/com.renquant.rq104-silent-refusal-sentinel.plist`
          (weekly, Sunday 08:11) and its `ops/launchd_manifest.json` entry.

WHY/DIR:  Operator authorised the machine landing 2026-07-29. The sentinel was merged
          as code in orch#592 but unwired — code that nothing runs guards nothing.
          Cadence: the job it watches runs Saturday 05:30, so patrolling Sunday
          morning is late enough that the run has finished and its dated log exists,
          early enough that a chronic refusal surfaces within a day.

EVIDENCE: `launchctl list` shows `com.renquant.rq104-silent-refusal-sentinel` loaded
          `[VERIFIED — launchctl, 2026-07-29]`; the run-surface drift scan reports NO
          launchd drift after the install `[VERIFIED — ops/run_surface_drift_check.py]`
          because the manifest entry landed in the same batch. The digest convention
          matches the scanner's own `program_args_digest` (sha256 over
          `json.dumps(program_args)`), checked against the function rather than
          assumed. What it will alarm on, measured earlier against the real logs: a
          span of 4 non-acting weekly runs, 3 of which crashed.

NEXT:     Its first patrol is the coming Sunday. Revert if needed:
          `launchctl bootout gui/$(id -u)/com.renquant.rq104-silent-refusal-sentinel`
          then remove `~/Library/LaunchAgents/com.renquant.rq104-silent-refusal-sentinel.plist`
          and drop the manifest entry.
