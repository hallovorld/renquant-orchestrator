# The relaxation did not outlive the state it named

STATUS: complete. `PENDING_UNINSTALL` is now empty. The launchd surface is clean — 0
problems. No job, schedule, config or live artifact is touched.

WHAT: `com.renquant.crypto-session` leaves the `PENDING_UNINSTALL` set in
`tests/test_run_surface_drift_check.py`, because the plist is gone from the machine.

WHY/DIR: this is the follow-up orch#832 promised, arriving the way it was designed to.
That change removed the job from the reviewed manifest and named it in a bounded
relaxation so the suite stayed green through the transition, with this note attached:

> the exact-equality assertion below goes red **the moment the plist is gone**, forcing
> this entry's deletion.

It went red today:

```
AssertionError: retired-but-still-installed set changed:
  unexpected=[] resolved=['com.renquant.crypto-session']
```

The operator ran the `launchctl bootout` + `rm` from orch#832's checklist, `retiring`
lost the label, and exact-equality did exactly what it was written to do. **A guard
that only ever passes teaches nothing; this one was built to fail on success**, and
the red is the receipt.

[VERIFIED — `launchctl list | grep -c crypto-session` → 0; the plist is absent from
`~/Library/LaunchAgents`; the suite's `resolved=[…]` names the label, 2026-08-06]

## What is deliberately NOT deleted

`tests/test_crypto_session_dead_job_evidence.py` stays, and still passes (7 tests).
The containment is over; the record of **why** is not. G2 crypto was KILLED 2026-07-18
by its preregistered gate, and the job kept firing every 900 seconds against a target
absent from both checkouts — **1,322 runs, all exit 2**, first recorded at 900 runs on
2026-08-02. Deleting the evidence alongside the relaxation would leave a future reader
with a manifest that simply never mentioned the job, which is how a decision becomes
unexplainable.

## The shape worth keeping

The bounded set is the whole mechanism: a relaxation that **names** what it relaxes,
under exact equality, cannot quietly become permanent. It expires by going red when
its own precondition changes — no expiry date to forget, no reviewer to remember.

EVIDENCE:

| claim | value | provenance |
|---|---|---|
| the plist is gone | `launchctl list` count 0; file absent | [VERIFIED — 2026-08-06] |
| the test flagged it by design | `resolved=['com.renquant.crypto-session']` | [VERIFIED — full-suite run before this change] |
| the surface is now clean | `check_launchd_surface()` → **0 problems** | [VERIFIED — live call] |
| drift suite after the change | 24 passed | [VERIFIED — `pytest -q tests/test_run_surface_drift_check.py`] |
| the evidence record survives | 7 passed | [VERIFIED — `pytest -q tests/test_crypto_session_dead_job_evidence.py`] |

artifact: none produced or modified.
prod or exp: neither. A test-side bound is narrowed to match a machine state that has
  already changed; nothing executable, scheduled or served is touched.
existing data: yes — the machine state was read (`launchctl list`, the LaunchAgents
  directory) and the failure was observed in a full-suite run. Nothing was generated.
best-known?: yes. The alternative — leaving the entry — is precisely the failure the
  exact-equality assertion exists to prevent: a relaxation outliving its cause, so the
  next unmanifested job on disk would be silently tolerated under a stale exception.
scope: one set literal and its comment in one test file, plus this doc.

NEXT: nothing pending on this thread. `PENDING_UNINSTALL` is empty and stays empty
until a future retirement declares a pending state by name — which is the only way an
entry may enter it.
