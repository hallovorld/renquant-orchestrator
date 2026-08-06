# Reported and paged are different verbs

STATUS: complete. The undelivered-alert scan still finds and prints everything it
found; it now pages only on findings a person can act on, and exits 0 when there are
none of those.

WHAT: `ACTIONABLE_STATUSES = ("PERMANENT", "UNTESTABLE")` plus an `actionable()`
filter. `main()` sends the alert built from that subset, and returns 0 — not 1 — when
the subset is empty.

WHY/DIR: operator, 2026-08-06, quoting a push this scan had just sent:

> 这种msg有意义吗？… 这种msg我不会看的，这种问题你应该自动自己修

The push carried seven lines. Four were `[TRANSIENT]` — SSL handshake timeouts and one
DNS failure. Three were `[RESOLVED]`, and each ended with the scan's **own** words:
*"the historical failure is CLOSED, no action needed"*.

**A notification whose text says nothing needs doing has spent the reader's attention
to buy nothing.** Worse, it is indistinguishable at a glance from one that matters, so
it teaches the reader to skip the channel that also carries the real alarms — the exact
failure this scan exists to prevent, committed by the scan.

## Why each excluded status is genuinely not actionable

- **TRANSIENT** — a network blip. The delivery layer now retries these itself:
  `renquant_common.notify.send` does 3 attempts with backoff (landed 2026-08-05). The
  correct response to a transient is a retry, and the code already does it. Waking a
  person adds nothing they can do.
- **RESOLVED** — by its own definition already fixed, and re-measured that way: the
  scan re-runs the historical title through *today's* encoder before classifying. A
  `[RESOLVED]` line is a statement that the gap is closed.

`PERMANENT` and `UNTESTABLE` still page, unchanged. `UNTESTABLE` deliberately stays
actionable: **could-not-check is not checked-and-found-fine**, and a scan that cannot
re-test its own claim is exactly when a human should look.

## What the existing docstring got right, and where it stopped

The module already defended reporting RESOLVED: *"Hiding it would make the fix
invisible; calling it PERMANENT would make the fix a lie."* That is correct — and it is
an argument about the **report**, not about the **page**. Nothing in it requires a push
notification. Everything is still printed to stdout, which `ops_audit` captures, so the
record the docstring wanted is intact.

## The exit code moves too, and that is the point

This scan is not a standalone job: it is an `ops_audit` member with allowed finding
exit codes `(1,)`. Returning 1 on a RESOLVED-only run made `ops_audit` report a finding
for something already fixed — a second copy of the same noise, one layer up. It now
returns 0 in that case, so the aggregate stops carrying it.

## Verified on the real logs

Running the changed scan against the live log root reproduces the operator's exact
seven findings and then:

```
undelivered-alert scan: 7 finding(s), none actionable
(TRANSIENT is retried by the sender; RESOLVED is already fixed) — printed above, not paged
rc=0
```

**The push that prompted this would not be sent.**

EVIDENCE:

| claim | value | provenance |
|---|---|---|
| the complained-of push was entirely non-actionable | 4 TRANSIENT + 3 RESOLVED, 0 PERMANENT | [VERIFIED — the operator's quoted message, reproduced by `--dry-run` on the live logs] |
| it now pages nothing and exits 0 | `none actionable … not paged`, `rc=0` | [VERIFIED — live run, 2026-08-06] |
| an actionable finding still pages and exits 1 | yes | [VERIFIED — `test_an_actionable_finding_still_pages_and_exits_1`] |
| the page body carries only actionable lines | yes | [VERIFIED — `test_the_page_carries_ONLY_the_actionable_lines`] |
| new tests | 6 | [VERIFIED — `pytest -q tests/test_undelivered_alert_scan.py`: 33 passed] |
| the new tests are load-bearing | all 6 fail against the pre-change module | [VERIFIED — `git stash push ops/…`, re-run: 6 failed] |
| two pre-existing tests updated, intent preserved | they asserted page-on-any-finding; now pinned to a PERMANENT fixture, and a new test asserts the SAME line exits 0 once RESOLVED | [VERIFIED — same suite] |

artifact: none produced or modified.
prod or exp: production alerting path — this scan runs as an `ops_audit` member. The
  change is confined to which findings are pushed and to the exit code on a
  non-actionable run; detection, classification and printing are untouched.
existing data: yes — the seven findings were read from the live fleet logs the scan
  already walks. Nothing was generated to support the change.
best-known?: yes for the stated problem. Keying on the declared STATUS token is the
  robust form; matching prose like "no action needed" would break the moment the
  wording changed, and a test pins the token set for that reason. Suppressing by count
  or cooldown was rejected — it would hide PERMANENT findings too, which is the
  opposite of the goal.
scope: one constant, one helper, and the paging/exit branch of `main()` in
  `ops/undelivered_alert_scan.py`, plus its test file. No other module, job, schedule
  or config is touched.

NEXT: the same question is worth asking of every alerting caller — **does this page
tell the reader something they can act on?** `ops/liveness_common.py::alert()` has no
notion of actionability at all, so each caller decides alone and most decide "always".
That is a broader change with its own design, and it does not belong bolted onto this
one.
