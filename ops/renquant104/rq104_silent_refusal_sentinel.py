#!/usr/bin/env python3
"""Silent-refusal sentinel (GOAL-5 AC5: a refusal repeated is an incident).

The failure this exists for, measured 2026-07-28: the weekly PatchTST retrain
job (`com.renquant.weekly-retrain-patchtst`, Sat 05:30) had been doing its
work correctly for months — training a fresh fold, fitting its calibrator,
writing the manifest — and then DECLINING at the freshness gate:

    source[fast] rawlabel: cutoff=2026-04-28 age=88d sla=28d OFF-SLA
    promote: refused — NOT FRESH (expected on a stale panel; old pin kept)
    ═══ weekly_retrain_patchtst finished rc=0 ═══

Exit code 0. No alert. The served artifact reached **622 days** stale while
every liveness checker reported the job healthy, because the job WAS healthy:
it ran, it succeeded, and it decided to do nothing. Liveness checkers answer
"did it run"; degradation sentinels watch the live buy path. Neither one asks
the question that mattered: **did it keep declining?**

A single refusal is a legitimate gate doing its job. A refusal repeated N
times running is one of:
  * a gate whose threshold cannot be satisfied by construction (the actual
    2026-07-28 root cause — a 28-calendar-day SLA applied to a source whose
    frontier is structurally ~91 days behind), or
  * an upstream input that stopped advancing, or
  * a recipe that can no longer produce a promotable candidate.
All three are incidents. None of them raise anything today.

Design notes:
  * READ-ONLY. Job logs are only read; nothing is written, no state is kept.
    The streak is recomputed from the logs on every run, so there is no
    counter to drift or reset.
  * The registry below is the extension point: a job qualifies when it can
    exit 0 while declining to act. Add the (log dir, refusal marker, run
    marker) triple and it is watched.
  * Runs with NO promote decision line at all are SKIPPED, not counted as
    successes. A job that failed before reaching its decision has not
    "succeeded" — counting it as one would silently reset a real streak.
    That asymmetry is deliberate: this sentinel fails toward alarming.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from liveness_common import alert  # noqa: E402

RQ = os.environ.get("RQ_ROOT", "/Users/renhao/git/github/RenQuant")

#: consecutive declining runs before alarming. 3 keeps a single legitimate
#: refusal (a genuinely stale input for one week) quiet while catching the
#: chronic case within a month. The 2026-07-28 incident ran for MONTHS.
STREAK_N = int(os.environ.get("RQ104_REFUSAL_STREAK_N", "3"))

#: A dated job log is only considered when it is at most this old, so a job
#: that stopped running entirely does not keep re-alarming on ancient logs
#: (that is the liveness checker's domain, not this one's).
MAX_LOG_AGE_DAYS = int(os.environ.get("RQ104_REFUSAL_MAX_LOG_AGE_DAYS", "90"))


@dataclass(frozen=True)
class WatchedJob:
    """A job that can exit 0 while declining to do its work."""
    name: str
    log_dir: str
    #: matches a run that DECLINED (the job ran, decided, and did nothing)
    refusal_re: str
    #: matches a run that ACTED (the job ran, decided, and did something)
    action_re: str
    #: matches a run that FAILED before deciding (crash / hard error). These
    #: are a SECOND silent class: measured 2026-07-28, the weekly retrain's
    #: 07-11 and 07-18 runs died on `CorpusRefreshError` and the 07-03 run
    #: hit the same error yet still printed `finished rc=0`.
    failure_re: str = r"Traceback \(most recent call last\)|CorpusRefreshError|^\w*Error:"


#: Registry. A job belongs here when "it ran successfully" and "it did its
#: job" are different statements.
WATCHED: tuple[WatchedJob, ...] = (
    WatchedJob(
        name="weekly-retrain-patchtst",
        log_dir=os.path.join(RQ, "logs/weekly_retrain_patchtst"),
        refusal_re=r"promote:\s*refused",
        action_re=r"promote:\s*(promoted|advanced|applied)",
    ),
)


@dataclass(frozen=True)
class RunOutcome:
    day: dt.date
    outcome: str  # "refused" | "acted" | "undecided"


def _dated_logs(log_dir: str, *, as_of: dt.date) -> list[tuple[dt.date, Path]]:
    """Dated run logs, newest first, within MAX_LOG_AGE_DAYS.

    Non-dated files (stdout.log / stderr.log) are IGNORED: they are appended
    across runs, so a single old refusal in them would pin the streak forever.
    """
    out: list[tuple[dt.date, Path]] = []
    d = Path(log_dir)
    if not d.is_dir():
        return out
    for p in d.glob("*.log"):
        try:
            day = dt.date.fromisoformat(p.stem)
        except ValueError:
            continue
        if (as_of - day).days > MAX_LOG_AGE_DAYS or day > as_of:
            continue
        out.append((day, p))
    return sorted(out, key=lambda t: t[0], reverse=True)


def classify_run(text: str, job: WatchedJob) -> str:
    """Classify one run: acted / refused / failed / undecided.

    Order matters. An ACTION anywhere wins over everything else: a run that
    refuses one candidate and then promotes another has acted, and treating
    it as a refusal would manufacture a streak out of a healthy job. A crash
    marker outranks a refusal because a run that died did not choose to
    decline — it never got to decide (measured 2026-07-28: the 07-03 run hit
    `CorpusRefreshError` AND printed `promote: refused` AND exited rc=0).
    """
    if re.search(job.action_re, text):
        return "acted"
    if re.search(job.failure_re, text, flags=re.MULTILINE):
        return "failed"
    if re.search(job.refusal_re, text):
        return "refused"
    return "undecided"


def read_outcomes(job: WatchedJob, *, as_of: dt.date) -> list[RunOutcome]:
    outcomes: list[RunOutcome] = []
    for day, path in _dated_logs(job.log_dir, as_of=as_of):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        outcomes.append(RunOutcome(day, classify_run(text, job)))
    return outcomes


@dataclass(frozen=True)
class InactionStreak:
    """Non-acting runs, newest first, plus what was skipped to assemble them.

    ``runs`` is NOT necessarily a temporally-contiguous run of dates —
    ``skipped`` records every `undecided` run that sits between two of
    them. Reporting both, rather than folding skipped runs silently into
    the count, is what keeps the word "consecutive" honest (see `check`).
    """
    runs: tuple[RunOutcome, ...]
    skipped: tuple[RunOutcome, ...]


def inaction_streak(outcomes: list[RunOutcome]) -> InactionStreak:
    """Leading run of NON-ACTING runs, newest first.

    `refused` and `failed` both count: from the served artifact's point of
    view they are the same event — another cycle passed and nothing was
    promoted. Only an `acted` run breaks the streak. `undecided` runs are
    skipped rather than breaking it (fail toward alarming: a run we cannot
    classify is not evidence of recovery) — but they ARE recorded, because
    silently absorbing them into a "consecutive" count would let a real gap
    (a run this sentinel can't read) hide behind a claim of contiguity it
    can't back up.

    Counting failures alongside refusals is not a stylistic choice: the
    2026-07-28 measurement found the weekly job's recent cycles were a MIX
    (07-03 refused, 07-11 failed, 07-18 failed, 07-25 refused). A
    refusals-only rule scores that as a streak of 2 and stays silent through
    four consecutive months of a model going stale.
    """
    streak: list[RunOutcome] = []
    skipped: list[RunOutcome] = []
    for o in outcomes:
        if o.outcome in ("refused", "failed"):
            streak.append(o)
        elif o.outcome == "acted":
            break
        else:
            skipped.append(o)
    return InactionStreak(tuple(streak), tuple(skipped))


def check(job: WatchedJob, *, as_of: dt.date) -> str | None:
    ia = inaction_streak(read_outcomes(job, as_of=as_of))
    if len(ia.runs) < STREAK_N:
        return None
    detail = ", ".join(f"{o.day.isoformat()}:{o.outcome}" for o in ia.runs[:6])
    n_failed = sum(1 for o in ia.runs if o.outcome == "failed")
    if ia.skipped:
        span = (f"{len(ia.runs)} non-acting runs spanning "
                f"{len(ia.skipped)} unclassifiable run(s) not counted as "
                f"acted-or-not ({', '.join(o.day.isoformat() for o in ia.skipped[:3])})")
    else:
        span = f"{len(ia.runs)} consecutive runs"
    return (
        f"job '{job.name}' has not acted on {span} "
        f"({detail}"
        + (f"; {n_failed} of them CRASHED" if n_failed else "")
        + f"). A gate refusing once is the gate working; nothing being "
        f"promoted cycle after cycle means the gate cannot be satisfied, its "
        f"input stopped advancing, or the job is failing before it decides. "
        f"Check {job.log_dir}."
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--as-of", default=None, help="YYYY-MM-DD (default: today)")
    ap.add_argument("--dry-run", action="store_true",
                    help="print findings, send no alert")
    args = ap.parse_args(argv)
    as_of = (dt.date.fromisoformat(args.as_of) if args.as_of
             else dt.date.today())

    findings = [msg for job in WATCHED
                if (msg := check(job, as_of=as_of)) is not None]
    for msg in findings:
        print(msg)
    if findings and not args.dry_run:
        alert("RenQuant SILENT REFUSAL", " | ".join(findings))
    if not findings:
        print(f"silent-refusal sentinel: {len(WATCHED)} job(s) checked, "
              f"no refusal streak >= {STREAK_N} as of {as_of}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
