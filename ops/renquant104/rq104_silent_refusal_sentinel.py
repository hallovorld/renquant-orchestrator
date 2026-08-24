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

2026-08-18 — four MEASURED classification defects, fixed here
------------------------------------------------------------
Re-measured against the real dated logs of `weekly_wf_promote`,
`conditional_retrain_104` and `retrain_panel` (as-of 2026-08-18):

D1  A DELEGATOR'S "acted" WAS THE CHILD'S EXIT CODE, NOT A PROMOTION.
    `conditional-retrain104` and `retrain-panel104` print
    "Gated WF promote chain complete" / "delegated weekly_wf_promote PASS"
    from `if bash scripts/weekly_wf_promote.sh; then` — i.e. from the child
    exiting 0. Since the 2026-08-04 operator directive, weekly_wf_promote's
    CALM_FRESH branch (scripts/weekly_wf_promote.sh:513-520) **exits 0 on a
    REFUSAL**: the gate rejected the candidate, the served model is fresh
    under RFC#210, "governance nominal, calm notify, exit 0". A pure refusal
    therefore reads as ACTION, and one such run CLEARS the whole streak —
    the exact blindness this module exists to prevent, re-created one layer
    up. Fixed by CORROBORATION (see ``Corroborator``): a delegator's success
    claim is only "acted" when the CHILD's own dated log for that date
    carries the child's own action evidence. Two new non-acting outcomes
    keep the failure modes distinguishable in the alarm:
      * ``uncorroborated`` — child log exists, carries no promotion.
      * ``unwitnessed``    — child wrote NO dated log at all. That is the
        live 2026-08-16 shape: weekly_wf_promote's orch#799 fail-closed
        `exit 2` (scripts/weekly_wf_promote.sh:211) fires BEFORE the
        `exec >> "$LOG"` redirect at :235, so no dated child log is ever
        created. Today that path exits non-zero and the delegator says
        FAIL; a wrapper that ever swallowed it would otherwise clear the
        streak on a run that provably never even opened its log.

D2  A CAUGHT TRACEBACK IS EVIDENCE, NOT A CRASH.
    `classify_run` tested `crash_re` BEFORE the failure/refusal verdicts,
    and the WF gate DELIBERATELY logs caught tracebacks as sanity evidence
    before deciding. Measured: 14/14 weekly runs that reached a terminal
    verdict were labelled CRASHED (13 of them had printed "WF gate REJECTED
    staged model — production unchanged."). Fixed: a crash claim now
    requires the ABSENCE of a decision verdict (``_reached_a_decision``).

D3  crash_re MISSED THE ONE REAL CRASH.
    logs/weekly_wf_promote/2026-06-06.log:7 —
      "weekly_wf_promote.sh: line 141: 93085 Segmentation fault: 11
       \"$PYTHON\" scripts/smoke_test_model.py"
    A process killed by a signal produces neither a traceback nor
    `^\\w*Error:`, so the run was labelled `failed`. Fixed: `crash_re` now
    recognises signal-death/abort signatures. The wrapper's follow-on
    "Smoke test FAILED — aborting weekly promote (no train)." is an ABORT,
    not a decision (``abort_re``), so it does not suppress the crash verdict.

D4  failure_re OMITTED "Training FAILED".
    8 real Step-3 training failures (2026-07-31, 07-23, 07-17, 07-16, 07-11,
    07-10, 07-09, 07-04) matched nothing, classified `undecided`, and were
    DROPPED from the tally — silently shrinking the very streak the module
    counts. Fixed, together with the other unmatched terminal verdicts read
    off the current wrapper and off the log corpus.
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


#: Signal-death / abort signatures (D3, measured 2026-06-06 and 2026-06-07:
#: `Segmentation fault: 11` from the shell's job-status report). A process
#: killed by a signal prints no traceback and no `Error:` line, so the
#: original crash_re could not see the ONE genuine hard crash in the corpus.
#:
#: The `: <signo>` / `(core dumped)` suffix is REQUIRED on every alternative,
#: deliberately: bare "Killed" and "Terminated" are ordinary English that
#: appear in log prose, and a crash marker that fires on prose is worse than
#: one that misses. macOS (this fleet) always prints the signal number; the
#: `(core dumped)` form is there so a Linux runner is not silently unwatched.
HARD_KILL_RE = (
    r"(?:Segmentation fault|Bus error|Abort trap|Illegal instruction|"
    r"Trace/BPT trap|Floating point exception|Killed|Terminated|Quit)"
    r"(?::\s*\d+|\s*\(core dumped\))"
)


@dataclass(frozen=True)
class Corroborator:
    """The CHILD job whose own log must confirm a DELEGATOR's success claim.

    D1. `conditional_retrain_104.sh:104` and `retrain_panel.sh:71` both wrap
    the child in `if bash scripts/weekly_wf_promote.sh; then` and print their
    success line off the child's EXIT CODE. That exit code stopped meaning
    "something was promoted" on 2026-08-04, when the operator directive made
    the CALM_FRESH reject path exit 0 (a reject while the served model is
    fresh is the healthy steady state of RFC#210 governance — correct for the
    operator's pager, fatal for a success signal derived from it).

    So the delegator's claim is corroborated against the SAME evidence the
    child lane itself is watched on: the child's own action line, in the
    child's own dated log, for the SAME date. No evidence, no "acted".

    Known and accepted: if the child ran TWICE on one date (weekly at 04:00,
    then an anomaly-triggered rerun at 13:10) the child's dated log is
    append-mode and holds both runs, so an earlier genuine promotion
    corroborates the later delegation. That is not a false clear — the served
    artifact really did change that day, which is exactly the estimand.
    """
    #: the WATCHED lane this corroborates against, for the alarm text
    name: str
    log_dir: str
    #: the CHILD's own action pattern — deliberately the identical constant
    #: the child lane is registered with, so the two cannot drift apart
    action_re: str
    log_stem_prefix: str = ""


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
    #: matches a run whose OWN vocabulary says it FAILED (a delegated gate's
    #: FAIL echo, a chain's "FAILED" line). These runs decided and reported
    #: failure — non-acting, but NOT crashes, and the alarm must not call
    #: them CRASHED (2026-08-03 diagnosis of the first scheduled finding: 9
    #: of retrain-panel104's 11 "CRASHED" runs were honest delegated WF-gate
    #: FAILs). Empty = the job has no non-crash failure vocabulary.
    failure_re: str = ""
    #: matches a run that DIED before deciding (crash / hard error) — the
    #: original SECOND silent class: measured 2026-07-28, the weekly retrain's
    #: 07-11 and 07-18 runs died on `CorpusRefreshError` and the 07-03 run
    #: hit the same error yet still printed `finished rc=0`.
    #:
    #: D3 (2026-08-18): signal death is a crash too, and it was invisible
    #: here — the one genuine hard crash in the whole corpus
    #: (logs/weekly_wf_promote/2026-06-06.log:7, SIGSEGV in the pre-flight
    #: smoke test) printed neither a traceback nor an `Error:` line.
    #:
    #: A crash marker is NOT on its own a crash verdict. `classify_run` only
    #: calls a run crashed when it never reached a decision — the WF gate
    #: logs caught tracebacks as sanity EVIDENCE and then decides (D2).
    crash_re: str = (r"Traceback \(most recent call last\)|CorpusRefreshError|"
                     r"^\w*Error:|" + HARD_KILL_RE)
    #: FAILURE lines that mean "aborted BEFORE deciding", not "decided
    #: against". Used only by `_reached_a_decision`: an abort must not
    #: suppress a crash verdict, or the 2026-06-06 SIGSEGV goes on reading as
    #: an ordinary `failed` because the wrapper politely echoed
    #: "Smoke test FAILED — aborting weekly promote (no train)." after it.
    #: These lines still count as `failed` — they are real non-actions.
    abort_re: str = ""
    #: The CHILD lane whose log must corroborate this job's action claim
    #: (D1). ``None`` = this job's action line is its own evidence.
    corroborator: Corroborator | None = None
    #: Dated logs are normally `<log_dir>/YYYY-MM-DD.log`. Some jobs write
    #: `<prefix>YYYY-MM-DD.log` into a directory SHARED with other jobs --- rq105/
    #: holds six jobs' logs. Without this the finder skips them entirely (the whole
    #: stem is not a date), and a finder that merely stripped any prefix would read
    #: a SIBLING job's logs. Required for both discovery and attribution.
    log_stem_prefix: str = ""


# ── weekly_wf_promote's vocabulary, hoisted ──────────────────────────────────
# Both delegating lanes are corroborated against the CHILD's action pattern.
# Hoisting it to a module constant is what makes "the SAME evidence" a fact
# rather than a comment: there is one string, used by the child's own lane and
# by both corroborators, so the three cannot drift apart.
WEEKLY_WF_PROMOTE_LOG_DIR = os.path.join(RQ, "logs/weekly_wf_promote")
WEEKLY_WF_PROMOTE_ACTION_RE = (r"weekly_wf_promote PASSED|"
                               r"weekly_wf_promote FALLBACK-PROMOTED")

#: Every non-action terminal verdict this wrapper can print. Read off BOTH the
#: current emitter (scripts/weekly_wf_promote.sh) and the real log corpus:
#:
#:   Training FAILED                    :419/:424 — 12 logs, incl. the 8 runs
#:                                       D4 was dropping (2026-07-31 … 07-04).
#:                                       Both wordings ("— production artifact
#:                                       unchanged." and the pre-2026-06
#:                                       "— prior production artifact still in
#:                                       place", 2026-05-17) share this stem.
#:   WF manifest stamping/... FAILED    :449 — emitter only, never observed.
#:   Fallback promote FAILED            :544 — emitter only, never observed.
#:   Promote FAILED                     :640 — emitter only, never observed.
#:   Snapshot freshness backstop FAILED :670 — emitter only, never observed.
#:   Smoke test FAILED                  :277 — 3 logs. ABORT, see abort_re.
#:   WF gate FAILED — production unchanged.  HISTORICAL: 2026-05-24, from a
#:       wrapper revision that predates the RFC#210 rewrite; the line no
#:       longer exists in the script, so it is deliberately NOT contracted in
#:       emitter_contract.json (the re-capture tool would refuse on zero emit
#:       sites). It is kept because that log is still inside the 90-day
#:       window and dropping it would re-open D4 for one more run.
WEEKLY_WF_PROMOTE_FAILURE_RE = (
    r"Training FAILED|"
    r"WF gate FAILED — production unchanged\.|"
    r"WF manifest stamping/recipe validation FAILED|"
    r"Fallback promote FAILED|"
    r"Promote FAILED|"
    r"Smoke test FAILED|"
    r"Snapshot freshness backstop FAILED"
)

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
        log_dir=WEEKLY_WF_PROMOTE_LOG_DIR,
        # refusal read off the REAL 2026-08-01 dated log; REJECTED on 6 of the last 8
        # dated logs at review time. The RFC#210 fallback's own REFUSE line
        # (scripts/weekly_wf_promote.sh:494) is a second refusal verdict; today it is
        # always followed by the REJECTED line at :501, but the watch must not depend
        # on that coupling holding.
        refusal_re=(r"WF gate REJECTED staged model|"
                    r"RFC#210 fallback verdict: REFUSE"),
        # action read off the emitter, scripts/weekly_wf_promote.sh — no PASS has
        # ever appeared in the log window.
        # FALLBACK-PROMOTED added 2026-08-04 (RenQuant#559 Step 4b): an
        # RFC#210 freshness-fallback promotion IS an action — the served
        # artifact changed; counting it as a refusal would keep alarming
        # over a lane that just acted (the #101 design says the streak
        # clears honestly on fallback).
        action_re=WEEKLY_WF_PROMOTE_ACTION_RE,
        failure_re=WEEKLY_WF_PROMOTE_FAILURE_RE,
        # D3. The pre-flight smoke test aborts BEFORE Step 3 ever runs
        # (scripts/weekly_wf_promote.sh:276-280), so this line is the wrapper
        # reporting that it never got to decide — including when the reason it
        # never got to decide was a SIGSEGV (2026-06-06). It must not count as
        # a decision, or the crash it is reporting reads as an ordinary FAIL.
        abort_re=r"Smoke test FAILED",
    ),
    WatchedJob(
        name="conditional-retrain104",
        log_dir=os.path.join(RQ, "logs/conditional_retrain_104"),
        # No refusal vocabulary: a triggered run completes or fails, and a no-trigger
        # day prints "No anomaly triggers fired" — a healthy idle that must classify
        # as SKIP, not as a refusal streak. Measured 2026-08-01: 59 dated logs, 22
        # trigger-fired, 22 chain FAILED, 0 completed.
        refusal_re=None,
        # emitter: scripts/conditional_retrain_104.sh:147/151 (RenQuant#603/#604,
        # orch#1052 re-pin): "chain complete" was an exit-code echo that read
        # CALM_FRESH refusals as success; the wrapper now names the outcome it
        # POSITIVELY established from the child's own markers. Both PROMOTED and
        # RAN, NOTHING PROMOTED are completed decisions (the gate declining is
        # the gate working), so both count as action here.
        action_re=r"Gated WF promote chain (PROMOTED|RAN, NOTHING PROMOTED)",
        # OUTCOME UNVERIFIED is the wrapper reporting its own contract drifted
        # (exit 2) — a failure to establish, never an action and never silence.
        failure_re=(r"Gated WF promote chain FAILED"
                    r"|Gated WF promote chain OUTCOME UNVERIFIED"
                    r"|Trigger check FAILED"),
        # D1: this line is printed off `if bash scripts/weekly_wf_promote.sh`
        # — the CHILD'S EXIT CODE — and the child now exits 0 on a CALM_FRESH
        # refusal. Corroborate against what the child itself printed.
        corroborator=Corroborator(
            name="weekly-wf-promote",
            log_dir=WEEKLY_WF_PROMOTE_LOG_DIR,
            action_re=WEEKLY_WF_PROMOTE_ACTION_RE,
        ),
    ),
    WatchedJob(
        name="retrain-panel104",
        log_dir=os.path.join(RQ, "logs/retrain_panel"),
        # No refusal vocabulary: it delegates to weekly_wf_promote and reports
        # PASS/FAIL; "already ran today" is a SKIP. Measured 2026-08-01: 19 dated
        # logs, 7 delegated runs, 7 FAIL, 0 PASS.
        refusal_re=None,
        # emitter: scripts/retrain_panel.sh:94/98 (RenQuant#603/#604, orch#1052
        # re-pin — same reasoning as conditional-retrain104 above).
        action_re=r"delegated weekly_wf_promote (PROMOTED|RAN, NOTHING PROMOTED)",
        # FAIL(ED)? deliberately matches the RETIRED pre-#603 "FAIL" line too:
        # historical logs in the scan window keep classifying as the honest
        # failures they were. Only the retired SUCCESS vocabulary is dropped —
        # that is the half that lied.
        failure_re=(r"delegated weekly_wf_promote FAIL(ED)?"
                    r"|delegated weekly_wf_promote OUTCOME UNVERIFIED"),
        # D1: same shape as conditional-retrain104 — the PASS echo is the
        # child's exit code wearing the delegator's vocabulary.
        corroborator=Corroborator(
            name="weekly-wf-promote",
            log_dir=WEEKLY_WF_PROMOTE_LOG_DIR,
            action_re=WEEKLY_WF_PROMOTE_ACTION_RE,
        ),
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


#: Every outcome that is NOT an action. `undecided` is absent on purpose: it
#: is neither, and `inaction_streak` records it separately rather than
#: counting it (see there).
NON_ACTING = ("refused", "failed", "crashed", "uncorroborated", "unwitnessed")


@dataclass(frozen=True)
class RunOutcome:
    day: dt.date
    #: "acted" | "refused" | "failed" | "crashed" | "uncorroborated"
    #: | "unwitnessed" | "undecided"
    outcome: str


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


def _terminal_verdicts(text: str, job: WatchedJob) -> list[str]:
    """Every terminal-verdict line the run printed (the matched substrings)."""
    alts = [p for p in (job.action_re, job.failure_re, job.refusal_re) if p]
    if not alts:
        return []
    union = "|".join(f"(?:{p})" for p in alts)
    return [m.group(0) for m in re.finditer(union, text, flags=re.MULTILINE)]


def _reached_a_decision(text: str, job: WatchedJob) -> bool:
    """Did the run print a verdict meaning it DECIDED about the candidate?

    D2. This is the guard on the crash verdict. The WF gate deliberately logs
    caught tracebacks as sanity EVIDENCE and then decides — measured
    2026-08-18, 14 of 14 weekly runs that printed a terminal verdict were
    being labelled CRASHED on the strength of that evidence, 13 of them right
    after printing "WF gate REJECTED staged model — production unchanged."
    A crash claim is a claim about what the run did NOT get to do, so it must
    rest on the ABSENCE of a decision, never on the presence of a traceback.

    `abort_re` carves out the failure lines that report the opposite — the
    run bailed out before deciding. Those are still `failed` (real
    non-actions), they just do not veto a crash verdict.
    """
    for hit in _terminal_verdicts(text, job):
        if job.abort_re and re.search(job.abort_re, hit):
            continue
        return True
    return False


def _corroborate(c: Corroborator, day: dt.date | None) -> str:
    """Resolve a DELEGATOR's success claim against the child's own log (D1).

    Returns "acted" only on the child's own action evidence for that date.
    Every other path is NON-acting, with the reason kept distinct so the
    alarm names what it actually saw.
    """
    if day is None:
        # No date, no way to find the child's log. Fail toward alarming.
        return "uncorroborated"
    path = (Path(c.log_dir) /
            f"{c.log_stem_prefix}{day.isoformat()}.log")
    try:
        child = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        # The child never opened a dated log at all. weekly_wf_promote's
        # orch#799 fail-closed `exit 2` (:211) fires BEFORE the
        # `exec >> "$LOG"` redirect at :235, so this is a real, reachable
        # state — and the one where believing the delegator would be worst.
        return "unwitnessed"
    return "acted" if re.search(c.action_re, child) else "uncorroborated"


def classify_run(text: str, job: WatchedJob, *,
                 day: dt.date | None = None) -> str:
    """Classify one run. See `RunOutcome.outcome` for the vocabulary.

    Order matters. An ACTION anywhere wins over everything else: a run that
    refuses one candidate and then promotes another has acted, and treating
    it as a refusal would manufacture a streak out of a healthy job — except
    that for a DELEGATING job the action line is only the child's exit code,
    so it must be corroborated (D1). A crash is claimed only when the run
    reached no decision at all (D2). Crash, failure and refusal stay SEPARATE
    outcomes so the alarm can say which it saw (2026-08-03: the first
    scheduled finding glossed 9 delegated WF-gate FAILs as "CRASHED").
    """
    if re.search(job.action_re, text):
        if job.corroborator is None:
            return "acted"
        return _corroborate(job.corroborator, day)
    if (not _reached_a_decision(text, job)
            and re.search(job.crash_re, text, flags=re.MULTILINE)):
        return "crashed"
    if job.failure_re and re.search(job.failure_re, text, flags=re.MULTILINE):
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
        outcomes.append(RunOutcome(day, classify_run(text, job, day=day)))
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

    The same logic extends to the two D1 outcomes: `uncorroborated` and
    `unwitnessed` are runs where a DELEGATOR claimed success and the child's
    log did not back it. Nothing was promoted, so the streak must survive
    them — that is the whole point of not trusting the exit code.
    """
    streak: list[RunOutcome] = []
    skipped: list[RunOutcome] = []
    for o in outcomes:
        if o.outcome in NON_ACTING:
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
    n_crashed = sum(1 for o in ia.runs if o.outcome == "crashed")
    n_uncorr = sum(1 for o in ia.runs if o.outcome == "uncorroborated")
    n_unwit = sum(1 for o in ia.runs if o.outcome == "unwitnessed")
    child = job.corroborator.name if job.corroborator else "the delegate"
    if ia.skipped:
        span = (f"{len(ia.runs)} non-acting runs spanning "
                f"{len(ia.skipped)} unclassifiable run(s) not counted as "
                f"acted-or-not ({', '.join(o.day.isoformat() for o in ia.skipped[:3])})")
    else:
        span = f"{len(ia.runs)} consecutive runs"
    return (
        f"job '{job.name}' has not acted on {span} "
        f"({detail}"
        + (f"; {n_crashed} of them CRASHED" if n_crashed else "")
        + (f"; {n_failed} of them reported FAIL (the job's own verdict, "
           f"not a crash)" if n_failed else "")
        + (f"; {n_uncorr} of them CLAIMED SUCCESS while {child}'s own log for "
           f"that date shows no promotion (the wrapper reports its child's "
           f"exit code, and a CALM_FRESH refusal exits 0)"
           if n_uncorr else "")
        + (f"; {n_unwit} of them CLAIMED SUCCESS while {child} wrote no dated "
           f"log at all for that date (it exited before opening one)"
           if n_unwit else "")
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
