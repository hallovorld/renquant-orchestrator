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


def test_the_rq105_alarm_is_found_and_marked_permanent(tmp_path):
    _log(tmp_path, "rq105/launchd_liveness.err", ENCODING_LINE)
    items = U.scan(str(tmp_path), as_of=AS_OF)
    assert len(items) == 1
    assert items[0].permanent is True
    assert "rq105 DOWN" in items[0].title


def test_a_timeout_is_found_but_marked_transient(tmp_path):
    _log(tmp_path, "drift.err", TIMEOUT_LINE)
    items = U.scan(str(tmp_path), as_of=AS_OF)
    assert len(items) == 1
    assert items[0].permanent is False


def test_permanent_findings_sort_first_and_say_why(tmp_path):
    _log(tmp_path, "a.err", TIMEOUT_LINE)
    _log(tmp_path, "b.err", ENCODING_LINE)
    lines = U.findings(U.scan(str(tmp_path), as_of=AS_OF))
    assert len(lines) == 2
    assert "[PERMANENT]" in lines[0]
    assert "can never deliver until the code changes" in lines[0]
    assert "[transient]" in lines[1]
    assert "can never deliver" not in lines[1]


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
