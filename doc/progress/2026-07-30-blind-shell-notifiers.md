# 15 shell senders throw the delivery result away. The existing scan cannot see them.

**Date:** 2026-07-30 · GOAL-5 · orchestrator

**Bottom line:** `ops/undelivered_alert_scan.py` finds alarms that were raised and
failed to send — by matching `ntfy send failed`, a string **only**
`renquant_common.notify.send` emits. A second population posts to ntfy with a bare
`curl` and discards the result, so it can never emit that string and the existing
scan is structurally blind to it.

## 0. CORRECTION — the first predicate was overbroad (codex, #646)

The first version marked a sender unobservable when it carried **any one** of three
tokens. That is materially wrong: `curl -s` still hands its exit status to the
caller, and so does a command with stdout redirected. **Neither alone establishes
that the result was discarded**, so the count was not tied to the property claimed.

**Corrected predicate:** an explicit status-discarding construct
(`|| true`, `||true`, `|| :`, `||:`, `; true`, `;true`) is **NECESSARY**. `-s` and
`>/dev/null` are demoted to **attributes** — they record how much *additional*
evidence was destroyed, not whether the finding exists.

**Re-measured under the strict predicate: 15 scripts, 12 scheduled — unchanged**,
because every one of them carries `|| true` `[VERIFIED — re-run, 2026-07-30]`.
**The number survived the tightening; the reasoning behind it did not**, and that
is the part that needed fixing. A number that happens to be right for a wrong
reason is still a wrong claim.

## 1. Measured population

`[VERIFIED — whole-line scan of every umbrella `scripts/*.sh` cross-referenced with
`ops/launchd_manifest.json`, 2026-07-30]`

| | count |
|---|---:|
| umbrella scripts that POST to ntfy with `curl` | **15** |
| of those, delivery result **unobservable** | **15** |
| of those, **launchd-scheduled** | **12** |

The canonical line, identical across all of them:

```sh
curl -s -H "Title: $title" -d "$body" "https://ntfy.sh/$NTFY_TOPIC" >/dev/null 2>&1 || true
```

**Three independent silences in one statement:** `-s` (curl prints no error),
`>/dev/null 2>&1` (anything it did print is discarded), `|| true` (the exit status
is explicitly thrown away).

## 2. Why this is not academic

A scan of this fleet's logs on 2026-07-30 reported **zero ntfy sends** on a day the
operator received several. That conclusion was mine and it was wrong — the senders
that fired were all in this population, and they leave no trace of any kind. **A
send that fails silently is indistinguishable from one that was never attempted**,
which is precisely how *"why didn't I get an alert?"* becomes unanswerable.

Note the asymmetry with the Python path: `notify.send` also swallows failures, but
it **logs** first, which is what made the 🚨-title latin-1 bug findable at all.

## 3. What this ships, and what it deliberately does not

`ops/blind_notifier_scan.py` — read-only, counts the population, separates
**scheduled** from not, and names which of the three silencers each line uses (they
fail differently and a fix might address only one).

**It does not fix them.** Those scripts live in the umbrella, which this repo does
not write to. The remedy — a shared helper that captures the HTTP status and logs
it — is an umbrella change and belongs in its own authorised batch.

## 4. Suite

18 tests, including three controls that would have caught my own likely errors:

- **anti-vacuity** — a send that keeps its status is **not** a finding, or the count
  carries no information and the tool gets ignored;
- **`-sS` is not silent** — it suppresses the progress meter but keeps errors;
  matching it would report a sender that *does* report as one that does not;
- **a comment describing a send is not a send** — counting prose is how a scan
  produces a number nobody can act on, the same error I made earlier today reading
  an append-only log as if its lines belonged to today's run;

plus **nine negative controls** added at review: four asserting that each
individual silencer *without* a status discard is **not** a finding (including `-s`
AND `>/dev/null` together), and five asserting each spelling of the status discard
**is** one — so the overbreadth cannot return a piece at a time, and the necessary
condition cannot be narrowed into hiding real cases. Plus a regression pin on the
live machine (`blind >= 12`, `scheduled >= 10`) so a
future fix makes this fail and the number gets updated **deliberately** rather than
drifting unnoticed, and a fail-closed control that an absent scripts directory is
`UNUSABLE` (exit 2), never "no blind senders".

## 5. Method note on how this was found

My first measurement returned **0**, because the regex `curl[^\n]*ntfy\.sh` stops at
`ntfy.sh` — the `|| true` sits *after* it and was never captured. The check
validated the wrong object. Re-run on whole lines it returned 15/15/12.
