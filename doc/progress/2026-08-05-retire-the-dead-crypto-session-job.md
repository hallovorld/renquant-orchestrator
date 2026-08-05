# Retire com.renquant.crypto-session from the reviewed surface

STATUS: complete on the reviewed surface. The plist is still installed — the
`launchctl bootout` is a separate operator grant, checklist below. Merge-inert.

WHAT: `com.renquant.crypto-session` removed from `ops/launchd_manifest.json`
(40 → 39 jobs). The drift test's `PENDING_UNINSTALL` bounded set names it, so the
suite stays green through the transition while the **scheduled** scan keeps
alarming — that alarm is the reminder to finish the uninstall and is deliberately
not silenced.

WHY/DIR: G2 crypto was **KILLED 2026-07-18** by its preregistered gate (gross edge
≈ 0 before costs; all 20 family members negative). The job kept firing anyway, every
900 seconds, against a target that exists in **neither** checkout.

| | |
|---|---|
| runs | **1,322**, all `exit 2` |
| when first recorded | **900 runs**, 2026-08-02 (orch#700) |
| target | `scripts/crypto_session_runner.py` — absent from the dev **and** run checkouts |
| still in the reviewed manifest | yes, until this change |

[VERIFIED — `launchctl print gui/<uid>/com.renquant.crypto-session`, `find` across both
checkouts, and the committed manifest, 2026-08-05]

It fires roughly 96 times a day and has done so for 18 days past the kill decision.
It sends no ntfy, so it was not among the notifications the operator was paged about —
it is the *silent* half of the same complaint: **a fleet that keeps executing decisions
that were already made and reversed.**

The evidence record from the first sighting is already committed
(`tests/test_crypto_session_dead_job_evidence.py`) — the finding was documented on
2026-08-02 and nothing acted on it for three days. That gap is the point: a recorded
finding with no owner and no expiry is indistinguishable from an unrecorded one.

## Deployment (one operator grant)

```
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.renquant.crypto-session.plist
rm ~/Library/LaunchAgents/com.renquant.crypto-session.plist
```

Revert, if the decision is ever reversed: restore the manifest entry by a reviewed
change **first**, then `launchctl bootstrap`. The plist itself is recoverable from git
history.

After the bootout, `test_retired_but_still_installed_jobs_are_exactly_the_named_set`
goes red with `resolved=['com.renquant.crypto-session']` — that is the designed prompt
to delete the `PENDING_UNINSTALL` entry in a follow-up PR. The relaxation cannot outlive
the state it names.

EVIDENCE:

| claim | value | provenance |
|---|---|---|
| manifest 40 → 39, only that job removed | verified | [VERIFIED — JSON diff] |
| the scheduled scan still alarms | `unmanifested com.renquant job on disk: com.renquant.crypto-session` | [VERIFIED — `check_launchd_surface()` after the change] |
| drift + evidence suites | 25 passed | [VERIFIED — `pytest -q`] |

NEXT: the operator grant above. Separately, the alarm-quality half of the same report —
16 jobs in a failing state, each paging daily with a generic title — is being measured
for a digest rather than N independent pages.
