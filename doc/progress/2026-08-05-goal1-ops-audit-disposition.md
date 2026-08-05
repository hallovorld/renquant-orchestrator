# 2026-08-05 — GOAL-1: nine of eleven detectors fire daily and nothing is ever dispositioned

## What I checked, and what I expected to find

I went looking for the ack-ledger findings the audit reports (two `acked_at`
stamps lagging their real edit, one 08-16 expiry cliff) expecting them to be
**dark** — unrun, unseen. They are not: `ack_ledger_audit.py` is detector 8 of 11
inside `ops_audit.py`, and `com.renquant.ops-audit` is scheduled and running
`[VERIFIED — `launchctl list`, and three dated logs on disk]`.

**The finding is the opposite of the one I went looking for.**

## Measured `[VERIFIED — this session]`

| date | detectors | ok | findings | acks |
|---|---|---|---|---|
| 2026-08-03 | 11 | 0 | **10** | 0 |
| 2026-08-04 | 11 | 1 | **10** | 0 |
| 2026-08-05 | 11 | 2 | **9** | 0 |

- **82–91 % of detectors fire on every run**, and the job exits 1 every time.
- **`ops_audit_acks.json` does not exist** — in this repo *or* in the run
  checkout the scheduled job reads from. Zero findings have ever been
  dispositioned.

The trend is genuinely improving (`ok` 0 → 1 → 2, findings 10 → 9), so this is
not static noise. But every finding reads exactly like every other one, and that
is how a reader learns to skip all of them.

This is the same disease this project keeps meeting from different directions:
a three-claim P0 sitting two-thirds fixed for four days (orch#726); a sentinel
alarming nine hours before the session it watches (orch#811). The alarms are not
wrong — they are **undifferentiated**.

## What lands

`ops/ops_audit_disposition_trend.py` — turns the dated logs into the two numbers
the audit's own output cannot show from a single run: **is it getting quieter**,
and **has anything ever been dispositioned**.

The discipline in it is the same discipline the findings themselves keep needing:

- **one run refuses to call a trend** — two points make a line, one makes a
  number;
- **a log with no summary is RECORDED as unparsed**, not skipped: a day the
  audit failed to report is a fact about the audit;
- **a missing ledger line leaves acks UNKNOWN, not zero** — absence of the line
  is not evidence of zero acks;
- **any single ack stops the call-out** — one disposition means the mechanism is
  in use, and claiming otherwise would be the false positive that discredits the
  measurement.

## What this does NOT say

It does not say the nine findings are wrong, or that they should be acked.
Several are things I have been working on all night. It says only that **nothing
distinguishes them**, and that the mechanism built for exactly that
(`ops_audit_acks.json`) has never been used.

Nor does it change any alarm: read-only, no schedule, no suppression.

Suites: 11 new tests, incl. one bound to the live logs that fails if the audit
ever starts dispositioning · full suite green.
