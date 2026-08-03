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

#: non-acting runs before alarming (not necessarily temporally consecutive —
#: see inaction_streak). 3 keeps a single legitimate refusal (a genuinely
#: stale input for one week) quiet while catching the chronic case within a
#: month. The 2026-07-28 incident ran for MONTHS.
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
    #: matches a run that DECLINED (the job ran, decided, and did nothing).
    #: ``None`` means the job has NO refusal vocabulary — its only silent classes are
    #: skip and failure (e.g. an anomaly-gated chain either completes or fails; there
    #: is no line meaning "looked and declined"). A never-matching placeholder regex
    #: here would be a guessed pattern, which this module forbids.
    refusal_re: str | None
    #: matches a run that ACTED (the job ran, decided, and did something)
    action_re: str
    #: matches a run that FAILED before deciding (crash / hard error). These
    #: are a SECOND silent class: measured 2026-07-28, the weekly retrain's
    #: 07-11 and 07-18 runs died on `CorpusRefreshError` and the 07-03 run
    #: hit the same error yet still printed `finished rc=0`.
    failure_re: str = r"Traceback \(most recent call last\)|CorpusRefreshError|^\w*Error:"
    #: Dated logs are normally `<log_dir>/YYYY-MM-DD.log`. Some jobs write
    #: `<prefix>YYYY-MM-DD.log` into a directory SHARED with other jobs --- rq105/
    #: holds six jobs' logs. Without this the finder skips them entirely (the whole
    #: stem is not a date), and a finder that merely stripped any prefix would read
    #: a SIBLING job's logs. Required for both discovery and attribution.
    log_stem_prefix: str = ""


#: Registry. A job belongs here when "it ran successfully" and "it did its
#: job" are different statements.
WATCHED: tuple[WatchedJob, ...] = (
    # FOUNDING LANE RETIRED 2026-08-02: weekly-retrain-patchtst (the 2026-07-28
    # incident this module was built for) was booted out under the operator's
    # Grant B (decision orch#741; manifest removal orch#755; bootout executed
    # 22:48Z, verified unloaded). A watch on a job that can never write another
    # log is either eternal noise or eternal false-quiet — the lane goes, the
    # doctrine (and this module) stays.
    # SECOND LANE, added 2026-07-30. Same shape as the first: the job's entire
    # purpose is to produce an artifact, it can decline, and declining is a normal
    # exit. Both patterns were read off the REAL dated logs before being written
    # here, not guessed:
    #   refusal  logs/rq105/batch_scores_export_2026-07-30.log
    #            "run <id> fails class-A health evidence: full_buy_run(pipeline_flags)
    #             — ... refusing to export"
    #   action   logs/rq105/batch_scores_export_2026-07-29.log
    #            "exported 85/85 frozen blend scores (coverage 100.0%) from ..."
    #
    # NOT added on the strength of a current incident. Measured 2026-07-30 the
    # refusal streak is ONE (07-30 refused, 07-29 exported 85/85 at 100% coverage),
    # and this module's own doctrine is that a single refusal is a legitimate gate
    # doing its job. The lane is added for COVERAGE: today nothing would notice if
    # that one became twenty.
    WatchedJob(
        name="rq105-batch-scores-export",
        log_dir=os.path.join(RQ, "logs/rq105"),
        log_stem_prefix="batch_scores_export_",
        refusal_re=r"refusing to export",
        action_re=r"exported\s+\d+/\d+\s+frozen blend scores",
    ),
    # THIRD-FIFTH LANES, added 2026-08-01 after the #724 registry-completeness pass.
    #
    # DOCTRINE AMENDMENT, stated where it applies: this module requires patterns read
    # off reality, not guessed. For a job that has NEVER succeeded inside its log
    # window, no action line exists in any log — and refusing to watch it for that
    # reason would exclude exactly the jobs a silent-refusal sentinel exists for. For
    # those jobs the action pattern is read off the EMITTER SOURCE (the literal echo
    # in the wrapper script), and a test pins the pattern to that source line so a
    # reworded emitter breaks the test instead of silently blinding the watch.
    WatchedJob(
        name="weekly-wf-promote",
        log_dir=os.path.join(RQ, "logs/weekly_wf_promote"),
        # refusal read off the REAL 2026-08-01 dated log; REJECTED on 6 of the last 8
        # dated logs at review time.
        refusal_re=r"WF gate REJECTED staged model",
        # action read off the emitter, scripts/weekly_wf_promote.sh:412 — no PASS has
        # ever appeared in the 54-log window.
        action_re=r"weekly_wf_promote PASSED",
        failure_re=(r"Promote FAILED|Smoke test FAILED|Snapshot freshness backstop "
                    r"FAILED|Traceback \(most recent call last\)"),
    ),
    WatchedJob(
        name="conditional-retrain104",
        log_dir=os.path.join(RQ, "logs/conditional_retrain_104"),
        # No refusal vocabulary: a triggered run completes or fails, and a no-trigger
        # day prints "No anomaly triggers fired" — a healthy idle that must classify
        # as SKIP, not as a refusal streak. Measured 2026-08-01: 59 dated logs, 22
        # trigger-fired, 22 chain FAILED, 0 completed.
        refusal_re=None,
        # emitter: scripts/conditional_retrain_104.sh:105
        action_re=r"Gated WF promote chain complete",
        failure_re=(r"Gated WF promote chain FAILED|Trigger check FAILED|"
                    r"Traceback \(most recent call last\)"),
    ),
    WatchedJob(
        name="retrain-panel104",
        log_dir=os.path.join(RQ, "logs/retrain_panel"),
        # No refusal vocabulary: it delegates to weekly_wf_promote and reports
        # PASS/FAIL; "already ran today" is a SKIP. Measured 2026-08-01: 19 dated
        # logs, 7 delegated runs, 7 FAIL, 0 PASS.
        refusal_re=None,
        # emitter: scripts/retrain_panel.sh:72
        action_re=r"delegated weekly_wf_promote PASS",
        failure_re=(r"delegated weekly_wf_promote FAIL|"
                    r"Traceback \(most recent call last\)"),
    ),
)

#: Lanes that have the shape but CANNOT be watched yet, with the measured reason.
#: Recorded rather than silently omitted --- an unwatched lane that nobody wrote
#: down is indistinguishable from one that was considered and cleared.
#: 2026-08-01: `weekly-wf-promote` was REMOVED from this registry and promoted to
#: WATCHED. Its recorded reason — "dated log surface last wrote 2026-05-24" — was
#: re-measured FALSE: 54 dated logs exist through 2026-08-01, with REJECTED decision
#: lines on 6 of the last 8. A registry of measured reasons must retire entries whose
#: measurements no longer hold, or it becomes the thing it guards against.
UNWATCHABLE_LANES = {
    "_retired_weekly-wf-promote_see_WATCHED": (
        "has a matching refusal line (\"refusing to spend sim compute on "
        "non-comparable WF evidence\") but its DATED log surface last wrote "
        "2026-05-24 --- the job now writes only stdout.log/stderr.log, which this "
        "sentinel deliberately does not read because an append-only stream cannot "
        "be attributed to a run. Watching it needs the dated surface restored first."
    ),
}


@dataclass(frozen=True)
class RunOutcome:
    day: dt.date
    outcome: str  # "refused" | "acted" | "undecided"


def _dated_logs(log_dir: str, *, as_of: dt.date,
                stem_prefix: str = "") -> list[tuple[dt.date, Path]]:
    """Dated run logs, newest first, within MAX_LOG_AGE_DAYS.

    Non-dated files (stdout.log / stderr.log) are IGNORED: they are appended
    across runs, so a single old refusal in them would pin the streak forever.
    """
    out: list[tuple[dt.date, Path]] = []
    d = Path(log_dir)
    if not d.is_dir():
        return out
    for p in d.glob(f"{stem_prefix}*.log"):
        stem = p.stem
        if stem_prefix:
            if not stem.startswith(stem_prefix):
                continue
            stem = stem[len(stem_prefix):]
        try:
            day = dt.date.fromisoformat(stem)
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
    if job.refusal_re and re.search(job.refusal_re, text):
        return "refused"
    return "undecided"


def read_outcomes(job: WatchedJob, *, as_of: dt.date) -> list[RunOutcome]:
    outcomes: list[RunOutcome] = []
    for day, path in _dated_logs(job.log_dir, as_of=as_of,
                                 stem_prefix=job.log_stem_prefix):
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
