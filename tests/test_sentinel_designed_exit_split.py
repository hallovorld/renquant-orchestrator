"""orch#1011 — the alarm could not separate "I found something" from "I crashed".

`com.renquant.weekly-wf-promote` exited 2 on 2026-08-08 and again on 2026-08-15.
The alarm fired both times. It fired the way it fires every day: one line naming
a dozen jobs, each rendered as a bare `(last exit N)`. Reading it required
knowing, from memory, which numbers are a job REPORTING and which are a job
BROKEN. Nobody does. The promote chain stayed dead for 14 days and was found by
noticing a stale artifact.

Measured against real `launchctl list` state on 2026-08-24, the alarm named nine
jobs identically. Split by `agent_inbox.DESIGNED_EXIT_CODES` they are three
different things: two pure status reports that do not belong in an alarm, four
whose documented meaning IS the problem, and three with no documented meaning at
all — the only ones that actually need a human to go look.

These tests pin the split. The load-bearing one is
`test_losing_the_map_makes_the_alarm_LOUDER`: a monitor whose own dependency
breaks must not fall silent.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOD = os.path.join(ROOT, "ops", "renquant104", "rq104_degradation_sentinel.py")


def _load():
    d = os.path.dirname(MOD)
    if d not in sys.path:
        sys.path.insert(0, d)
    spec = importlib.util.spec_from_file_location("rq104_sentinel_split", MOD)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


S = _load()


def _launchctl(*rows: tuple[str, int]) -> str:
    return "\n".join(f"-\t{code}\tcom.renquant.{label}" for label, code in rows)


#: A FIXED anchor. Every date in this file is derived from it and it is passed
#: to `check_launchd_exits`, so nothing here is compared against the wall clock.
#: A fixture aged from `today()` while the assertion asks about a fixed date is
#: a bomb with its date already set — one detonated repo-wide on 2026-08-24
#: (doc/progress/2026-08-24-undelivered-scan-test-clock-bomb.md).
AS_OF = dt.date(2026, 8, 24)


def _alarm(monkeypatch, text: str, acks: dict | None = None):
    monkeypatch.setattr(
        S.subprocess, "run",
        lambda *a, **kw: type("R", (), {"stdout": text})(),
    )
    monkeypatch.setattr(S, "load_acks", lambda: (acks or {}))
    return S.check_launchd_exits(today=AS_OF)


def _live_ack(codes: list[int], **over) -> dict:
    """An ack that is valid AS OF `AS_OF` — acked today, expiring well after."""
    ack = {
        "acked_exit_codes": codes,
        "acked_at": AS_OF.isoformat(),
        "reason": "known",
        "clears_when": "later",
        "expires_at": (AS_OF + dt.timedelta(days=7)).isoformat(),
    }
    ack.update(over)
    return ack


# --------------------------------------------------------------------------
# the three tiers
# --------------------------------------------------------------------------

def test_a_pure_status_report_leaves_the_alarm(monkeypatch):
    """`actionable=False` is agent_inbox's own word for "the code's meaning is
    known, and it is not a problem". ops-audit exiting 1 means it has findings —
    which reach the operator through the findings themselves, not through a
    launchd code that may be hours old."""
    alarm, infos = _alarm(monkeypatch, _launchctl(("ops-audit", 1)))
    assert alarm is None, f"a status report must not raise an alarm: {alarm}"
    assert any("ops-audit" in i and "findings present" in i for i in infos), infos
    assert any("designed status report" in i for i in infos), infos


def test_a_designed_code_whose_MEANING_is_the_problem_stays_loud(monkeypatch):
    """"designed" is not "fine". A model-freshness breach is documented AND bad."""
    alarm, _ = _alarm(monkeypatch, _launchctl(("rq104-model-freshness", 3)))
    assert alarm is not None
    assert "rq104-model-freshness" in alarm
    assert "model artifact is stale" in alarm, (
        "the alarm must carry the meaning, not just the number: " + alarm
    )
    assert "contract:" in alarm, "and where that meaning is defined"


def test_an_undocumented_code_says_it_is_undocumented(monkeypatch):
    alarm, infos = _alarm(monkeypatch, _launchctl(("some-new-job", 9)))
    assert alarm is not None
    assert "NO DOCUMENTED MEANING for exit 9" in alarm, alarm
    assert "needs a human" in alarm
    assert not infos


def test_the_three_tiers_are_distinguishable_in_one_reading(monkeypatch):
    """The point of the issue: one alarm, three kinds of thing, told apart."""
    alarm, infos = _alarm(monkeypatch, _launchctl(
        ("ops-audit", 1),                # designed, not actionable  -> info
        ("rq104-risk-budget", 1),        # designed, actionable      -> loud + meaning
        ("some-new-job", 9),             # unknown                   -> loud + "no meaning"
    ))
    assert len(infos) == 1 and "ops-audit" in infos[0]
    assert "ops-audit" not in alarm
    assert "budget is at or over 100%" in alarm
    assert "NO DOCUMENTED MEANING" in alarm


# --------------------------------------------------------------------------
# the job this issue is about
# --------------------------------------------------------------------------

def test_weekly_wf_promote_is_still_UNKNOWN_and_still_loud(monkeypatch):
    """The 14-day silence. agent_inbox deliberately keeps this job OUT of the
    map: its wrapper lives in the sibling umbrella repo, which this repo's CI
    does not check out, so the claim cannot be MEASURED here. An unverifiable
    contract must not buy quiet — it stays UNKNOWN, which is accurate."""
    alarm, infos = _alarm(monkeypatch, _launchctl(("weekly-wf-promote", 2)))
    assert alarm is not None and "weekly-wf-promote" in alarm
    assert "NO DOCUMENTED MEANING for exit 2" in alarm, alarm
    assert not infos, "an unverifiable contract must not move a job to INFO"


# --------------------------------------------------------------------------
# the fail direction
# --------------------------------------------------------------------------

def test_losing_the_map_makes_the_alarm_LOUDER(monkeypatch):
    """If `agent_inbox` cannot be imported, every code becomes UNKNOWN.

    This is the whole safety argument for consulting another module at alarm
    time. A monitor that goes quiet because its own dependency broke is worse
    than no monitor: it reports health it never checked. So the degraded mode is
    "alarm on everything", identical to the behaviour before this split existed.
    """
    monkeypatch.setattr(S, "designed_exit_meaning", lambda *a, **kw: None)
    alarm, infos = _alarm(monkeypatch, _launchctl(
        ("ops-audit", 1), ("rq105-shadow-serving", 4), ("rq104-risk-budget", 1),
    ))
    assert not infos, "with no map, nothing may be demoted to INFO"
    for job in ("ops-audit", "rq105-shadow-serving", "rq104-risk-budget"):
        assert job in alarm, f"{job} went quiet when the map was unavailable"


def test_the_helper_itself_returns_None_rather_than_raising(monkeypatch):
    """`designed_exit_meaning` must never propagate an exception into the alarm
    path — returning None routes the job to UNKNOWN, which is loud."""
    assert S.designed_exit_meaning("com.renquant.ops-audit", None) is None
    assert S.designed_exit_meaning("com.renquant.definitely-not-a-job", 1) is None
    known = S.designed_exit_meaning("com.renquant.ops-audit", 1)
    assert known is not None and known[3] is False, known


# --------------------------------------------------------------------------
# controls — the ack machinery must be untouched
# --------------------------------------------------------------------------

def test_an_ack_still_suppresses_an_actionable_designed_code(monkeypatch):
    """The split runs BEFORE the ack logic, so it must not have bypassed it."""
    acks = {"com.renquant.rq104-risk-budget": _live_ack([1])}
    alarm, infos = _alarm(monkeypatch, _launchctl(("rq104-risk-budget", 1)), acks)
    assert alarm is None, alarm
    assert any("acked nonzero exit" in i for i in infos), infos


def test_an_ack_that_does_not_cover_the_code_still_shouts(monkeypatch):
    acks = {"com.renquant.rq104-risk-budget":
            _live_ack([2], reason="only the WARN tier")}
    alarm, _ = _alarm(monkeypatch, _launchctl(("rq104-risk-budget", 1)), acks)
    assert alarm is not None
    assert "ACK DOES NOT COVER THIS EXIT" in alarm, alarm


def test_zero_exit_jobs_are_still_not_in_the_alarm(monkeypatch):
    alarm, infos = _alarm(monkeypatch, _launchctl(("ops-audit", 0)))
    assert alarm is None and not infos
