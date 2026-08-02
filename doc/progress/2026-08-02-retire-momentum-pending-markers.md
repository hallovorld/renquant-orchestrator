# 2026-08-02 — retire the momentum PENDING_INSTALL markers (post re-executed install)

STATUS: complete

WHAT: The two pre-install narrative comments under
`com.renquant.momentum-train-weekly` in `ops/launchd_manifest.json`, the
momentum label in the drift test's `PENDING_INSTALL` bounded set, and the
job's pending-install surface test (inverted to assert the retirement) — the
same three surfaces the reverted #759 round 1 touched, now legitimate.

WHY/DIR: The markers' own contract: they describe a merged-but-dark job, and
step (c) of Grant C was RE-EXECUTED after the corrected-order gates all
merged (pipeline#255, RenQuant#554, orch#761; record orch#759) — plist
installed, `launchctl bootstrap gui/502` verified loaded (Sat 05:00),
orchestrator-run at `315767af`. A pending marker over an installed job would
teach the drift scan to trust a stale state.

EVIDENCE:
- artifact: this PR's diff; containment trail scratchpad `grant-c-step2.log`
  (re-run block, timestamped)
- prod or exp: reviewed surfaces only; the machine change (install) already
  executed under the standing Grant C authorization
- existing data: drift + job-surface tests measure the REAL machine state:
  18 + 21 pass with the job loaded
- best-known?: yes — the tests assert against launchctl, not a fixture
- scope: the three marker surfaces; entry, schedule comment, evidence_glob,
  program_args_sha256 untouched

NEXT: none — the inverse rot (job uninstalled with no marker) stays caught by
the drift test's exact-equality set.
