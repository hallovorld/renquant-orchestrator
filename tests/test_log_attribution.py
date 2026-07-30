"""A line in an append-only log belongs to no date until it is attributed.

Three real misreads on 2026-07-30, all mine, none caught by a tool:

  1. `launchd_dawn_preflight.out` — a historical `No module named 'live'` reported
     as today's failure; today's run reached a decision and exited 0.
  2. `preopen_gate/stderr.log` — nearly told the operator six pending orders were
     cancelled this morning. That happened 2026-06-23. Today: `cancelled=[]`.
  3. `rq104_shadow_scorer_sentinel.log` — an mtime of 14:45 read as "ran today", at
     14:26. The file was 2026-07-29.

Two were caught by re-reading, one by noticing 14:45 has not happened at 14:26.
That is not a control. These are.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
_S = importlib.util.spec_from_file_location("la", REPO / "ops" / "log_attribution.py")
la = importlib.util.module_from_spec(_S)
_S.loader.exec_module(la)

D30 = dt.date(2026, 7, 30)
UMBRELLA = Path("/Users/renhao/git/github/RenQuant")


# --- THE THREE REAL TRAPS, as regression fixtures ------------------------------

def test_trap1_an_undated_append_only_out_file_is_UNATTRIBUTABLE(tmp_path):
    p = tmp_path / "launchd_dawn_preflight.out"
    p.write_text("Error while finding module specification for 'live.runner'\n"
                 "dawn preflight attestation OK (decision reached)\n")
    status, lines, why = la.lines_for_date(p, D30)
    assert status == la.UNATTRIBUTABLE
    assert lines == [], "returning the whole file IS the defect"
    assert "append-only" in why


def test_trap2_only_TODAYS_lines_come_back_from_a_timestamped_stream(tmp_path):
    p = tmp_path / "stderr.log"
    p.write_text(
        "2026-06-23 06:15:06 PREOPEN_CANCEL: cancelled 6 pending order(s): AVGO,PANW\n"
        "2026-07-30 06:15:06 PREOPEN-GATE: PASS - severity within +/-2.0 sigma.\n"
        "2026-07-30 06:15:06 Done. Action=pass, cancelled=[], considered=0.\n")
    status, lines, _ = la.lines_for_date(p, D30)
    assert status == la.ATTRIBUTED_BY_TIMESTAMP
    assert len(lines) == 2
    assert not any("PREOPEN_CANCEL" in l for l in lines), \
        "the June cancellation must not surface as today's evidence"


def test_trap3_a_dated_file_for_ANOTHER_day_is_UNATTRIBUTABLE(tmp_path):
    p = tmp_path / "job_2026-07-29.log"
    p.write_text("shadow scorer NOT ACTIONABLE\n")
    status, lines, why = la.lines_for_date(p, D30)
    assert status == la.UNATTRIBUTABLE and lines == []
    assert "not 2026-07-30" in why


# --- attribution rules ----------------------------------------------------------

def test_a_dated_filename_attributes_the_WHOLE_file(tmp_path):
    p = tmp_path / "daily_2026-07-30.log"
    p.write_text("no timestamps here at all\nsecond line\n")
    status, lines, _ = la.lines_for_date(p, D30)
    assert status == la.ATTRIBUTED_BY_FILENAME and len(lines) == 2


def test_a_date_INSIDE_a_line_is_not_the_lines_own_date(tmp_path):
    """A date anywhere in a line is usually DATA — a cutoff, a trained_date. Loose
    matching would invent evidence, which is worse than refusing."""
    p = tmp_path / "s.log"
    p.write_text("trained_date=2026-07-30 effective_cutoff=2026-07-30\n"
                 "another line mentioning 2026-07-30\n")
    status, lines, _ = la.lines_for_date(p, D30)
    assert status == la.UNATTRIBUTABLE and lines == []


def test_a_mostly_unstamped_stream_is_UNATTRIBUTABLE(tmp_path):
    """Under half the lines timestamped means most are continuations (tracebacks,
    tables). Filtering would silently drop the body of every multi-line record."""
    p = tmp_path / "s.log"
    p.write_text("2026-07-30 12:00 Traceback (most recent call last):\n"
                 + "  File x, line 1\n" * 9)
    status, lines, why = la.lines_for_date(p, D30)
    assert status == la.UNATTRIBUTABLE and lines == []
    assert "multi-line" in why


def test_a_missing_file_is_UNATTRIBUTABLE_not_empty_success(tmp_path):
    status, lines, _ = la.lines_for_date(tmp_path / "nope.log", D30)
    assert status == la.UNATTRIBUTABLE and lines == []


def test_a_bracketed_timestamp_is_recognised(tmp_path):
    p = tmp_path / "s.log"
    p.write_text("[2026-07-30 06:00:01] started\n[2026-07-29 06:00:01] older\n")
    status, lines, _ = la.lines_for_date(p, D30)
    assert status == la.ATTRIBUTED_BY_TIMESTAMP and len(lines) == 1


# --- anti-vacuity ---------------------------------------------------------------

def test_the_happy_path_actually_RETURNS_lines(tmp_path):
    """If everything were UNATTRIBUTABLE the tool would be useless and every test
    above would pass for the wrong reason."""
    p = tmp_path / "x_2026-07-30.log"
    p.write_text("a\nb\nc\n")
    status, lines, _ = la.lines_for_date(p, D30)
    assert status == la.ATTRIBUTED_BY_FILENAME and lines == ["a", "b", "c"]


# --- CLI ------------------------------------------------------------------------

def test_the_cli_exits_3_and_prints_NO_lines_when_unattributable(tmp_path, capsys):
    p = tmp_path / "s.out"; p.write_text("some historical line\n")
    rc = la.main(["--path", str(p), "--date", "2026-07-30"])
    out = capsys.readouterr()
    assert rc == la.EXIT_UNATTRIBUTABLE
    assert out.out == "", "printing lines is exactly what must not happen"
    assert "Refusing to print lines" in out.err


def test_a_bad_date_is_an_error_not_a_refusal(tmp_path):
    p = tmp_path / "x_2026-07-30.log"; p.write_text("a\n")
    assert la.main(["--path", str(p), "--date", "yesterday"]) == la.EXIT_ERROR


# --- against the live machine ---------------------------------------------------

@pytest.mark.parametrize("rel", [
    "logs/rq104/launchd_dawn_preflight.out",
    "logs/rq104_shadow_scorer_sentinel.log",
])
def test_the_real_append_only_files_are_refused(rel):
    p = UMBRELLA / rel
    if not p.exists():
        pytest.skip(f"{rel} absent")
    status, lines, _ = la.lines_for_date(p, D30)
    assert status == la.UNATTRIBUTABLE and lines == []
