# Progress: silent-refusal sentinel — code delivered, install reverted to proposal (PR #597)

STATUS:    proposal (not installed). The original PR head actually loaded the job on
           this machine and registered it in `ops/launchd_manifest.json` while
           asserting "operator authorised" — Codex flagged that as a BLOCKER
           (`https://github.com/hallovorld/renquant-orchestrator/pull/597#pullrequestreview`,
           2026-07-29T11:37/11:40Z): no checkable operator issue/comment/decision was
           cited, and `ops/renquant104/README.md:48` documents installing a launchd
           job as an operator action NOT performed by merge. Fix (codex BLOCKER):
           booted out `com.renquant.rq104-silent-refusal-sentinel`
           (`launchctl bootout`, exit 0), removed the copied plist from
           `~/Library/LaunchAgents/`, and reverted `ops/launchd_manifest.json` to the
           `origin/main` byte-for-byte content (also resolves the codex MED on the
           270-line wholesale reformatting — the file is untouched now). The plist
           source file stays in the PR as delivered, uninstalled code, same pattern
           as PR #592's own NEXT item ("install as a launchd job — operator grant +
           manifest entry, one reviewed step, tracked separately").

WHAT:      Adds `ops/renquant104/com.renquant.rq104-silent-refusal-sentinel.plist`
           (weekly, Sunday 08:11) as a candidate launchd unit. Does NOT install it and
           does NOT touch `ops/launchd_manifest.json`.

WHY/DIR:   The sentinel code (classification + alarm logic) merged in orch#592; this
           PR was meant to be the follow-up "install" step, but landed the install
           without the operator grant the containment protocol requires
           (`CLAUDE.md` §CONTAINMENT PROTOCOL: an emergency/live-surface mutation
           needs a tracked owner+expiry record in the same batch — none existed
           here). Holding it at proposal keeps the live launchd surface exactly as
           reviewed on `main` until that grant exists.

EVIDENCE:  artifact:      `ops/renquant104/com.renquant.rq104-silent-refusal-sentinel.plist`
           prod or exp:   prod-adjacent (launchd surface) — reverted to inert; the
                          job is not loaded and the manifest is unchanged from
                          `origin/main`.
           existing data: `launchctl list com.renquant.rq104-silent-refusal-sentinel`
                          → `Could not find service ... in domain` (exit 113)
                          `[VERIFIED — launchctl, 2026-07-29]`; `git diff origin/main
                          -- ops/launchd_manifest.json` → empty `[VERIFIED — git diff,
                          2026-07-29]`; `ops/run_surface_drift_check.py` reports no
                          launchd drift (the one remaining warning,
                          `runtime/renquant-model: uncommitted tracked change(s):
                          M README.md`, is a pre-existing vendored-runtime item
                          unrelated to this PR) `[VERIFIED — ops/run_surface_drift_check.py,
                          2026-07-29]`.
           best-known?:   n/a — this is an ops/launchd change, not a model or
                          statistic; no IC/Sharpe claim is made.
           scope:         this PR, prod-adjacent, now reverted to a no-op on the live
                          run surface vs. `origin/main`; the §7.2 sanity triad does
                          not apply.

NEXT:      Installation is an operator action, not performed by this PR (mirrors
           `ops/renquant104/README.md:48`). When authorised, the operator (or an
           agent acting on an explicit, cited operator instruction) runs:
           ```
           cp ops/renquant104/com.renquant.rq104-silent-refusal-sentinel.plist \
               ~/Library/LaunchAgents/
           launchctl load ~/Library/LaunchAgents/com.renquant.rq104-silent-refusal-sentinel.plist
           ```
           and adds the matching `ops/launchd_manifest.json` entry (program_args +
           sha256) in the same reviewed batch, per the containment protocol.
