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
    """Write a log whose age is measured from AS_OF, not from the wall clock.

    Ageing from ``time.time()`` while the scan is asked for a FIXED ``as_of``
    makes the test a time bomb: the file's date walks forward every day while
    the cutoff (``as_of - MAX_LOG_AGE_DAYS``) stays put, so a case written as
    "40 days old, comfortably stale" eventually lands on the wrong side of the
    boundary and the suite starts failing for a reason that has nothing to do
    with the code under test.

    It detonated on 2026-08-24, and straddled a timezone while doing it:
    with age_days=40 and MAX_LOG_AGE_DAYS=14 against AS_OF=2026-07-29 the
    cutoff is 2026-07-15, and ``today - 40d`` was 2026-07-14 in PDT (pass) but
    2026-07-15 in UTC (fail) — so it was green on a workstation and red on
    every CI runner, blocking unrelated PRs.

    Anchoring to AS_OF makes the arithmetic hermetic: the same relationship
    holds on any date, in any zone.
    """
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    if age_days:
        anchor = dt.datetime.combine(AS_OF, dt.time(12, 0), tzinfo=dt.timezone.utc)
        old = (anchor - dt.timedelta(days=age_days)).timestamp()
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
    # PERMANENT: an actionable finding, so paging and rc=1 are the expected path.
    monkeypatch.setattr(U, "encoding_defect_still_present", lambda title: True)
    assert U.main(["--log-root", str(tmp_path), "--as-of", "2026-07-29",
                   "--dry-run"]) == 1
    assert sent == []
    assert U.main(["--log-root", str(tmp_path), "--as-of", "2026-07-29"]) == 1
    assert len(sent) == 1


def test_the_SAME_line_exits_0_once_the_encoder_can_send_it(tmp_path, monkeypatch):
    """The identical log line, re-tested as RESOLVED, must stop being a finding —
    it is history about a defect that is already fixed."""
    _log(tmp_path, "a.err", ENCODING_LINE)
    sent: list = []
    monkeypatch.setattr(U, "alert", lambda t, b, **kw: sent.append((t, b)))
    monkeypatch.setattr(U, "encoding_defect_still_present", lambda title: False)

    assert U.main(["--log-root", str(tmp_path), "--as-of", "2026-07-29"]) == 0
    assert sent == []


def test_the_alarm_about_undeliverable_alarms_is_itself_deliverable(tmp_path, monkeypatch):
    """The one title in this fleet that MUST NOT be able to fail the same way."""
    _log(tmp_path, "a.err", ENCODING_LINE)
    sent: list = []
    monkeypatch.setattr(U, "alert", lambda t, b, **kw: sent.append((t, b)))
    monkeypatch.setattr(U, "encoding_defect_still_present", lambda title: True)
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


# --- reported and paged are different verbs -----------------------------------
#
# Operator, 2026-08-06, quoting a push from this very scan whose seven lines were
# four TRANSIENT network timeouts and three RESOLVED entries carrying the words
# "no action needed" in their own text: "这种msg我不会看的" — and, correctly,
# "这种问题你应该自动自己修".
#
# A notification that tells the reader nothing needs doing has spent their
# attention to buy nothing. Everything is still printed; only what a person can
# act on is sent.

_PERMANENT = "undelivered alarm [PERMANENT] x1: 'x' (e) in a.log — still undeliverable"
_UNTESTABLE = "undelivered alarm [UNTESTABLE] x1: 'x' (e) in a.log — could not re-test"
_TRANSIENT = "undelivered alarm [TRANSIENT] x2: 'y' (handshake timed out) in b.log"
_RESOLVED = "undelivered alarm [RESOLVED] x1: 'z' (latin-1) in c.log — CLOSED, no action needed"


def test_a_page_of_only_TRANSIENT_and_RESOLVED_is_not_sent():
    assert U.actionable([_TRANSIENT, _RESOLVED]) == []


def test_PERMANENT_and_UNTESTABLE_still_page():
    assert U.actionable([_PERMANENT, _UNTESTABLE]) == [_PERMANENT, _UNTESTABLE]


def test_the_page_carries_ONLY_the_actionable_lines():
    """Mixing the non-actionable back into the body would restore the original
    complaint: the reader still has to sort signal from noise, on a phone."""
    assert U.actionable([_TRANSIENT, _PERMANENT, _RESOLVED]) == [_PERMANENT]


def test_nothing_actionable_means_no_alert_and_exit_0(tmp_path, monkeypatch, capsys):
    """The whole point: this run must neither page nor register as a finding."""
    sent: list = []
    monkeypatch.setattr(U, "alert", lambda *a, **k: sent.append(a))
    monkeypatch.setattr(U, "scan", lambda *a, **k: ["item"])
    monkeypatch.setattr(U, "findings", lambda items: [_TRANSIENT, _RESOLVED])

    rc = U.main(["--log-root", str(tmp_path)])

    assert rc == 0, "a non-actionable scan must not read as an ops_audit finding"
    assert sent == [], "no push for findings nobody can act on"
    out = capsys.readouterr().out
    assert _TRANSIENT in out and _RESOLVED in out, "they must still be PRINTED"
    assert "none actionable" in out


def test_an_actionable_finding_still_pages_and_exits_1(tmp_path, monkeypatch):
    """Anti-vacuity: the change must not silence the case the scan exists for."""
    sent: list = []
    monkeypatch.setattr(U, "alert", lambda *a, **k: sent.append(a))
    monkeypatch.setattr(U, "scan", lambda *a, **k: ["item"])
    monkeypatch.setattr(U, "findings", lambda items: [_TRANSIENT, _PERMANENT])

    rc = U.main(["--log-root", str(tmp_path)])

    assert rc == 1
    assert len(sent) == 1
    body = sent[0][1]
    assert _PERMANENT in body
    assert _TRANSIENT not in body


def test_the_actionable_set_is_declared_not_inferred_from_wording():
    """Matching on prose like 'no action needed' would break the moment the
    wording changed. The gate keys on the STATUS token."""
    assert U.ACTIONABLE_STATUSES == ("PERMANENT", "UNTESTABLE")
