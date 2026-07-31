"""Alarms that were raised and never delivered.

Measured 2026-07-29 across the live fleet logs: seven dropped alerts in five
files. Three were an encoding defect that can never self-heal — including both
`rq105 DOWN` alarms, whose title hard-codes a leading 🚨, meaning that alarm
could never have delivered a single notification in its life while its own
output log showed collector issues on seven distinct July dates.

`renquant_common.notify.send` is deliberately built never to raise into a
monitor: it swallows, counts, logs, and returns False. Every caller ignores the
return value, and `send_failure_count()` has no consumer anywhere in the fleet.
So the evidence lived only in log lines nobody read.
"""
from __future__ import annotations

import datetime as dt
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ops"))
import undelivered_alert_scan as U  # noqa: E402

AS_OF = dt.date(2026, 7, 29)

# Verbatim lines from the live logs.
ENCODING_LINE = (
    "ntfy send failed (failure #1 in this process, "
    "title='\U0001f6a8 rq105 DOWN — 2 collector issue(s) 2026-07-28'): "
    "'latin-1' codec can't encode character '\\U0001f6a8' in position 0: "
    "ordinal not in range(256)\n"
)
TIMEOUT_LINE = (
    "ntfy send failed (failure #1 in this process, "
    "title='RUN-SURFACE DRIFT: 1 issue(s)'): "
    "<urlopen error _ssl.c:1000: The handshake operation timed out>\n"
)


def _log(tmp_path: Path, name: str, text: str, *, age_days: int = 0) -> Path:
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    if age_days:
        old = time.time() - age_days * 86400
        import os
        os.utime(p, (old, old))
    return p


# `permanent` became TWO things in this PR, and the tests below are split to match:
#
#   looked_permanent  what the LOG said        — pure text, environment-independent
#   status            re-measured against TODAY — calls the real encoder
#
# `status` therefore depends on whether `renquant_common` is importable. Measured
# 2026-07-31: in CI it is, the emoji title encodes under RFC 2047, and the encoding
# finding is **RESOLVED**; in an isolated worktree without the sibling it is
# **UNTESTABLE**. A test asserting one specific status for a real title passes in one
# environment and fails in the other — which is how these three broke.
#
# So the re-test is STUBBED wherever a status is asserted. That is not avoiding the
# question: `encoding_defect_still_present` has its own tests, and stubbing here is
# what lets all four statuses be exercised at all, including PERMANENT, which is
# otherwise unreachable on any machine whose encoder already fixes the defect.


def test_the_rq105_alarm_is_found_and_LOOKED_permanent(tmp_path):
    """The backward-looking half: what the log recorded, whatever is true today."""
    _log(tmp_path, "rq105/launchd_liveness.err", ENCODING_LINE)
    items = U.scan(str(tmp_path), as_of=AS_OF)
    assert len(items) == 1
    assert items[0].looked_permanent is True
    assert "rq105 DOWN" in items[0].title


def test_a_timeout_never_looked_permanent(tmp_path):
    _log(tmp_path, "drift.err", TIMEOUT_LINE)
    items = U.scan(str(tmp_path), as_of=AS_OF)
    assert len(items) == 1
    assert items[0].looked_permanent is False
    assert items[0].status == "TRANSIENT"


@pytest.mark.parametrize("still, expected", [
    (True, "PERMANENT"),      # today's encoder still cannot send it
    (False, "RESOLVED"),      # the defect was fixed after the log line was written
    (None, "UNTESTABLE"),     # cannot import the encoder -> claim nothing
])
def test_status_is_REMEASURED_not_recalled(tmp_path, monkeypatch, still, expected):
    """The whole point of this PR: a PERMANENT claim read out of an append-only log
    is a statement about the past, and must be re-tested before being repeated."""
    monkeypatch.setattr(U, "encoding_defect_still_present", lambda title: still)
    _log(tmp_path, "b.err", ENCODING_LINE)
    items = U.scan(str(tmp_path), as_of=AS_OF)
    assert len(items) == 1
    assert items[0].looked_permanent is True, "the log text is unchanged either way"
    assert items[0].status == expected


def test_permanent_findings_sort_first_and_say_why(tmp_path, monkeypatch):
    """Ordering is asserted with the re-test pinned, so it tests the ORDER rather
    than today's encoder."""
    monkeypatch.setattr(U, "encoding_defect_still_present", lambda title: True)
    _log(tmp_path, "a.err", TIMEOUT_LINE)
    _log(tmp_path, "b.err", ENCODING_LINE)
    lines = U.findings(U.scan(str(tmp_path), as_of=AS_OF))
    assert len(lines) == 2
    assert "[PERMANENT]" in lines[0]
    # The line must say it was RE-TESTED, not merely repeat the log's old claim —
    # that distinction is this PR's entire contribution, so it is pinned in the text
    # a human actually reads, not only in the status field.
    assert "RE-TESTED" in lines[0] and "still undeliverable" in lines[0]
    assert "[transient]" in lines[1].lower()
    assert "RE-TESTED" not in lines[1], "a transient finding was never re-tested"


def test_a_RESOLVED_finding_sorts_last_and_is_still_reported(tmp_path, monkeypatch):
    """RESOLVED is reported rather than dropped — the module says hiding it would
    make the fix invisible. Pinned so that intent cannot regress silently."""
    monkeypatch.setattr(U, "encoding_defect_still_present", lambda title: False)
    _log(tmp_path, "a.err", TIMEOUT_LINE)
    _log(tmp_path, "b.err", ENCODING_LINE)
    lines = U.findings(U.scan(str(tmp_path), as_of=AS_OF))
    assert len(lines) == 2
    assert "RESOLVED" in lines[1].upper()
    assert "[PERMANENT]" not in " ".join(lines)


def test_repeats_of_one_defect_collapse_to_one_line(tmp_path):
    """A permanent defect repeats identically every run; a screenful of the
    same line reads as noise instead of one bug to fix once."""
    _log(tmp_path, "a.err", ENCODING_LINE * 9)
    lines = U.findings(U.scan(str(tmp_path), as_of=AS_OF))
    assert len(lines) == 1
    assert "x9" in lines[0]


def test_distinct_titles_stay_distinct(tmp_path):
    _log(tmp_path, "a.err", ENCODING_LINE + TIMEOUT_LINE)
    assert len(U.findings(U.scan(str(tmp_path), as_of=AS_OF))) == 2


def test_stale_logs_are_ignored(tmp_path, monkeypatch):
    """A long-dead job's ancient failures must not alarm forever."""
    monkeypatch.setattr(U, "MAX_LOG_AGE_DAYS", 14)
    _log(tmp_path, "old.err", ENCODING_LINE, age_days=40)
    assert U.scan(str(tmp_path), as_of=AS_OF) == []


def test_recent_logs_are_kept(tmp_path, monkeypatch):
    monkeypatch.setattr(U, "MAX_LOG_AGE_DAYS", 14)
    _log(tmp_path, "new.err", ENCODING_LINE, age_days=3)
    assert len(U.scan(str(tmp_path), as_of=AS_OF)) == 1


def test_both_log_and_err_extensions_are_scanned(tmp_path):
    _log(tmp_path, "x.log", ENCODING_LINE)
    _log(tmp_path, "y.err", TIMEOUT_LINE)
    assert len(U.scan(str(tmp_path), as_of=AS_OF)) == 2


def test_a_clean_fleet_is_silent(tmp_path):
    _log(tmp_path, "ok.log", "rq105 liveness OK 2026-07-29\n")
    assert U.scan(str(tmp_path), as_of=AS_OF) == []
    assert U.findings([]) == []


def test_missing_log_root_is_silent(tmp_path):
    assert U.scan(str(tmp_path / "nope"), as_of=AS_OF) == []


def test_main_exit_codes_and_dry_run(tmp_path, monkeypatch, capsys):
    _log(tmp_path, "a.err", ENCODING_LINE)
    sent: list = []
    monkeypatch.setattr(U, "alert", lambda t, b, **kw: sent.append((t, b)))
    assert U.main(["--log-root", str(tmp_path), "--as-of", "2026-07-29",
                   "--dry-run"]) == 1
    assert sent == []
    assert U.main(["--log-root", str(tmp_path), "--as-of", "2026-07-29"]) == 1
    assert len(sent) == 1


def test_the_alarm_about_undeliverable_alarms_is_itself_deliverable(tmp_path, monkeypatch):
    """The one title in this fleet that MUST NOT be able to fail the same way."""
    _log(tmp_path, "a.err", ENCODING_LINE)
    sent: list = []
    monkeypatch.setattr(U, "alert", lambda t, b, **kw: sent.append((t, b)))
    U.main(["--log-root", str(tmp_path), "--as-of", "2026-07-29"])
    title = sent[0][0]
    title.encode("latin-1")          # must not raise
    assert title.isascii()


def test_clean_fleet_exits_zero(tmp_path, capsys):
    assert U.main(["--log-root", str(tmp_path), "--as-of", "2026-07-29"]) == 0
    assert "no dropped alarms" in capsys.readouterr().out


@pytest.mark.parametrize("quote", ["'", '"'])
def test_both_title_quotings_parse(tmp_path, quote):
    line = (f"ntfy send failed (failure #1 in this process, "
            f"title={quote}some title{quote}): boom\n")
    _log(tmp_path, "q.err", line)
    items = U.scan(str(tmp_path), as_of=AS_OF)
    assert len(items) == 1 and items[0].title == "some title"
