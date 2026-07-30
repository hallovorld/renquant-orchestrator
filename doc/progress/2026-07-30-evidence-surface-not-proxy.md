# I measured the wrong file and published it; the scan now measures the right one   (PR pending)

STATUS:    delivered
WHAT:      A manifest entry may declare `evidence_glob` — the file a job actually
           writes — and the liveness scan uses it instead of `StandardOutPath`.
           Declared for the three rq105 jobs whose readings were wrong. Every reading
           now says which surface produced it, and the report counts how many are proxies.
WHY/DIR:   GOAL-5. Issue #621 (mine) reported four rq105 jobs at "roughly 17-19 missed
           weekday firings". **Two of them had missed none.**
EVIDENCE:  §1.
NEXT:      **37 of 40 jobs are still measured by proxy.** Each needs an `evidence_glob`
           or a statement that its StandardOutPath really is its output surface.

## §1 EVIDENCE — the correction, measured

`StandardOutPath` is where launchd puts fd 1. A wrapper that redirects into its own
dated file leaves that path untouched forever, so its mtime measures **the last time the
wrapper failed to redirect**, not the last time the job ran.

`[VERIFIED — mtime/size under RenQuant/logs/rq105/, read-only, and the scan before/after]`:

| job | before (StandardOutPath) | after (evidence_glob) |
|---|---|---|
| `rq105-session-scheduler` | NO_EVIDENCE_STALE, **18 missed** | **EVIDENCE_FRESH, 0 missed** |
| `rq105-quote-logger` | NO_EVIDENCE_STALE, **19 missed** | **EVIDENCE_FRESH, 0 missed** |
| `rq105-shadow-serving` | NO_EVIDENCE_STALE, 19 missed | NO_EVIDENCE_STALE, **12 missed** |
| `rq105-postclose` | NO_EVIDENCE_STALE, 19 missed | unchanged — **no dated logs exist at all** |

Scan totals move from `EVIDENCE_FRESH 14 / STALE 24` to `16 / 22`.

**The defect in #621 was not severity, it was kind.** session-scheduler and quote-logger
fire every session day and write **zero bytes**. That is a *silent no-op*, and the
investigation it calls for — why does the loop produce no output — is a different one
from "why did the scheduler stop". The original framing would have sent someone down the
wrong path. shadow-serving is real but 12 days stale, not 19.

## §2 What the tool now refuses to hide

Every result carries `evidence_surface` and `evidence_is_proxy`, and the report carries
`measured_by_proxy`. It currently reads **37 of 40**. A proxy measurement presented as a
direct one is exactly how the false reading got published, so the scan states which it is
rather than presenting all readings as equivalent.

A declared glob that matches **nothing** is `UNJUDGEABLE`, not a silent fall back to the
proxy — falling back would hide a broken declaration behind a measurement of a different
file, which is the same defect one level up.

## §3 A mistake in the fix itself

My first attempt to add `evidence_glob` reported "0 entries added" and I nearly moved on.
The manifest is `{"_comment": ..., "jobs": {...}}`, not the list of pairs I assumed, so
iterating gave dict **keys** and `entry[0]` was the first character of a label — a silent
no-op. The edit now asserts the expected number of matches, so a structural assumption
that is wrong fails loudly instead of quietly changing nothing. Third instance tonight of
a patch that appeared to work and did nothing.

## §4 Suite

| tree | result |
|---|---|
| `origin/main` @ d8d2517c, separate worktree | 7 failed, 4548 passed, 5 skipped, 27 warnings in 119.88s (0:01:59) |
| this branch | 7 failed, 4554 passed, 5 skipped, 27 warnings in 120.22s (0:02:00) |

`[VERIFIED — python3 -m pytest -q in both worktrees, sibling checkouts on PYTHONPATH]`

## §5 Live-surface impact

The manifest gains a descriptive field on three entries; `program_args` and
`program_args_sha256` are untouched, so this cannot cause manifest drift. The scan is
read-only and still not wired into any scheduled job.
