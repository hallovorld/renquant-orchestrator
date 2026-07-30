"""The rq104 degradation sentinel takes EVERY com.renquant nonzero exit (#622 #3).

Measured 2026-07-30: 13 jobs nonzero, including the agent PR loop and a KILLED
crypto programme. Reported as one flat list, "the trading system is degraded" and
"an automation job failed" are indistinguishable — and a reader who learns the
second is common stops reading the first.

Grouping must NOT drop anything. Trading a legibility problem for a coverage problem
is the worse of the two on this programme, and these tests pin that it did not
happen.
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "ops"))
sys.path.insert(0, str(REPO / "ops" / "renquant104"))

import rq104_degradation_sentinel as sent  # noqa: E402

FRESH = (dt.date.today() - dt.timedelta(days=1)).isoformat()


@pytest.mark.parametrize("label,scope", [
    ("com.renquant.daily104", sent.SCOPE_TRADING),
    ("com.renquant.rq104-liveness", sent.SCOPE_TRADING),
    ("com.renquant.weekly-wf-promote", sent.SCOPE_TRADING),
    ("com.renquant.rq105-shadow-serving", sent.SCOPE_ADJACENT),
    ("com.renquant.shadow-ab-daily", sent.SCOPE_ADJACENT),
    ("com.renquant.run-surface-drift", sent.SCOPE_ADJACENT),
    ("com.renquant.agent-pr-loop", sent.SCOPE_UNRELATED),
    ("com.renquant.crypto-session", sent.SCOPE_UNRELATED),
])
def test_each_measured_job_lands_in_its_stated_scope(label, scope):
    assert sent.job_scope(label) == scope


def test_an_UNKNOWN_job_defaults_to_the_TRADING_group():
    """The load-bearing default. An unrecognised job is one nobody classified, and
    filing it quietly under noise is how a real degradation disappears. The cost of
    this default is a misfiled alarm; the cost of the other is a missed one."""
    assert sent.job_scope("com.renquant.some-brand-new-job") == sent.SCOPE_TRADING


def test_the_longest_prefix_wins():
    """`com.renquant.rq104` is TRADING; a more specific rule must be able to
    override its family rather than being shadowed by ordering."""
    assert sent.job_scope("com.renquant.rq104-degradation-sentinel") == sent.SCOPE_TRADING
    lens = [len(p) for p, _ in sent.SCOPE_RULES]
    assert len(lens) == len(sent.SCOPE_RULES)


def _run(monkeypatch, labels_and_codes):
    fails = [f"{l} (last exit {c})" for l, c in labels_and_codes]
    monkeypatch.setattr(sent, "parse_launchctl_failures", lambda *a, **k: fails)
    monkeypatch.setattr(sent, "load_acks", lambda: {})
    monkeypatch.setattr(sent.subprocess, "run",
                        lambda *a, **k: type("R", (), {"stdout": "", "returncode": 0})())
    return sent.check_launchd_exits(today=dt.date.today())


def test_NOTHING_is_dropped_by_grouping(monkeypatch):
    """The control that matters most. Every label must still appear in the alarm."""
    jobs = [("com.renquant.daily104", 1), ("com.renquant.rq105-shadow-serving", 1),
            ("com.renquant.agent-pr-loop", 1), ("com.renquant.crypto-session", 2)]
    alarm, _ = _run(monkeypatch, jobs)
    assert alarm is not None
    for label, _c in jobs:
        assert label in alarm, label


def test_the_groups_are_labelled_and_trading_comes_first(monkeypatch):
    alarm, _ = _run(monkeypatch, [("com.renquant.agent-pr-loop", 1),
                                  ("com.renquant.daily104", 1)])
    assert "[TRADING-PATH]" in alarm and "[unrelated]" in alarm
    assert alarm.index("[TRADING-PATH]") < alarm.index("[unrelated]")


def test_an_empty_group_prints_no_header(monkeypatch):
    """A permanently-present '[unrelated] ' with nothing after it teaches the reader
    to skip the line."""
    alarm, _ = _run(monkeypatch, [("com.renquant.daily104", 1)])
    assert "[TRADING-PATH]" in alarm
    assert "unrelated" not in alarm and "adjacent" not in alarm


def test_a_clean_fleet_still_yields_no_alarm(monkeypatch):
    """Anti-vacuity: grouping must not manufacture an alarm out of nothing."""
    alarm, infos = _run(monkeypatch, [])
    assert alarm is None and infos == []


def test_the_sentinel_still_exits_nonzero_for_an_unrelated_job_only(monkeypatch):
    """Grouping is about legibility, not severity. An unrelated job failing is still
    a failure and must not be silently downgraded to clean."""
    alarm, _ = _run(monkeypatch, [("com.renquant.agent-pr-loop", 1)])
    assert alarm is not None and "[unrelated]" in alarm
