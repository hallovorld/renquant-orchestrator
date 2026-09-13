# The run-surface drift scan now sees a contained pin   (ops/run_surface_drift_check.py)

STATUS:    delivered — one new check, `check_pin_lineage`, wired into
           `check_git_surfaces` for every runtime repo in `subrepos.lock.json`.
WHAT:      A deployed pin must be an ancestor of the runtime checkout's
           `origin/main`. If it is not, the scan raises
           `runtime/<repo>: pinned commit <sha> is NOT on origin/main (<sha>) —
           an unmerged commit is deployed (containment or a PR head); lift it by
           merging its PR and re-aligning, or revert the pin`. A checkout without
           an `origin/main` ref reports an INFO line and is not judged; a missing
           checkout or empty pin stays silent (the existing checkout check owns
           those). `origin/main` is whatever the pin-align step last fetched into
           the runtime checkout — the scan performs no fetch and stays read-only —
           so a PR merged after that fetch reads as off-main for one morning and
           clears on the next align.
WHY/DIR:   2026-09-12 two unmerged PR heads (renquant-pipeline#310,
           renquant-strategy-104#107) were deployed to the live runtime under
           CLAUDE.md §5 containment: the LIVE lock was edited (uncommitted) and
           the runtime re-aligned. On 2026-09-13 07:00 the scan reported one
           issue — the pre-existing watchlist-trainability one — and nothing about
           the containment [VERIFIED `logs/rq104/run_surface_drift_2026-09-13.log`].
           Every existing check was satisfied by construction: the runtime sat
           exactly at the edited lock and was clean; the umbrella was on `main`
           equal to `origin/main` because the edit was never committed; and the
           scan reads the umbrella's git metadata as files, so it cannot see an
           uncommitted working-tree change. §5(c) names this scan as the designed
           reminder to lift or legitimize a persisting containment; for the pin
           shape of containment that reminder did not exist. Lineage is the
           property that separates a reviewed pin from a contained one, and it is
           readable with the same read-only git queries the scan already runs in
           the runtime checkouts (never in the umbrella).
EVIDENCE:  artifact:      `ops/run_surface_drift_check.py` (+`_git_rc`, +`check_pin_lineage`, wiring in `check_git_surfaces`, docstring bullet a.)
           prod or exp:   prod ops surface — one new alarm on an existing daily job; reads git refs, writes nothing, changes no pin
           existing data: `tests/test_run_surface_drift_check.py` +5 (`TestPinLineage`): on-main silent; off-main alarms while the old checkout check stays silent on the same repo; no origin/main → INFO; missing repo / empty pin → silent; end-to-end through `check_git_surfaces` with a real lock file: the containment shape alarms, moving the pin back onto main silences it — 5 passed; the whole file 49 passed / 5 skipped (pre-existing launchctl skips) [VERIFIED 2026-09-13 ~08:0x PDT]. Non-vacuous against the LIVE runtime (function call only, no scan run, nothing paged): 2 of 9 runtime repos alarm — `runtime/renquant-pipeline: pinned commit 235d3c5e2a77 is NOT on origin/main (faf1416a342b)` and `runtime/renquant-strategy-104: pinned commit d2f27e2879b6 is NOT on origin/main (799821245b0e)`, exactly the two containment pins; the other seven read `on origin/main` [VERIFIED 2026-09-13 ~08:0x PDT]
           best-known?:   n/a — monitoring; no model claim
           scope:         "this adds one read-only lineage check to the daily drift scan; it does not change what the scan does with the umbrella, the launchd surface, or any pin"
NEXT:      After merge + `-run` sync the 07:00 scan will alarm every morning on
           the 2026-09-12 containment until pipeline#310 and strategy-104#107
           merge and the runtime is re-aligned — that alarm is the point; do not
           silence it. Follow-up (not here): the dawn pin-identity check could
           carry the same lineage line in its receipt.
