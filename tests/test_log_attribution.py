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


def test_a_traceback_comes_back_WITH_its_header_not_dropped(tmp_path):
    """RECORD FRAMING, replacing the 50%-coverage ratio codex rejected on #648.

    The old rule accepted a 51%-stamped stream and silently discarded every
    continuation. A timestamp establishes the date of ITS OWN line and nothing else,
    so the ratio proved nothing. A record is a timestamped line plus every following
    un-timestamped line; it is returned whole or not at all."""
    p = tmp_path / "s.log"
    p.write_text("2026-07-30 12:00 Traceback (most recent call last):\n"
                 + "  File x, line 1\n" * 9)
    status, lines, why = la.lines_for_date(p, D30)
    assert status == la.ATTRIBUTED_BY_TIMESTAMP
    assert len(lines) == 10, "the body must ride with its header"
    assert "framed record" in why


def test_just_above_the_OLD_threshold_no_longer_leaks(tmp_path):
    """The regression fixture codex asked for: 51% stamped / 49% continuation. The
    old rule ACCEPTED this and returned only the 51%. Framing returns the records
    whole, and the wrong-day record does not leak."""
    body = "".join(f"2026-07-30 12:0{i} header {i}\n  detail {i}\n" for i in range(5))
    body += "2026-07-29 09:00 old header\n"
    p = tmp_path / "s.log"
    p.write_text(body)
    status, lines, _ = la.lines_for_date(p, D30)
    assert status == la.ATTRIBUTED_BY_TIMESTAMP
    assert len(lines) == 10, lines            # 5 headers + 5 details, nothing dropped
    assert not any("old header" in l for l in lines)


def test_text_BEFORE_the_first_timestamp_is_EXCLUDED_and_REPORTED(tmp_path):
    """It belongs to no record in this file — a creation banner, or the tail of a
    run whose file was rotated away. Excluded, because the guarantee is that no
    un-attributable line is returned. REPORTED, because a silent drop is the same
    defect one level down. NOT a whole-file refusal: measured on the real
    preopen_gate/stderr.log the orphan is a one-line path banner while every record
    below it is well framed."""
    p = tmp_path / "s.log"
    p.write_text("PATH_BANNER=/some/module/path\n"
                 "2026-07-30 12:00 header\n  detail\n")
    status, lines, why = la.lines_for_date(p, D30)
    assert status == la.ATTRIBUTED_BY_TIMESTAMP
    assert lines == ["2026-07-30 12:00 header", "  detail"]
    assert "EXCLUDED 1 non-blank line" in why
    assert "PATH_BANNER" not in "".join(lines)


def test_a_blank_line_before_the_first_timestamp_is_NOT_an_orphan(tmp_path):
    """Anti-vacuity on the refusal above: log files routinely start with a blank
    line, and refusing on that would make the tool useless on real input."""
    p = tmp_path / "s.log"
    p.write_text("\n\n2026-07-30 12:00 header\n  detail\n")
    status, lines, _ = la.lines_for_date(p, D30)
    assert status == la.ATTRIBUTED_BY_TIMESTAMP and len(lines) == 2


def test_a_filename_with_TWO_dates_is_refused(tmp_path):
    """Codex on #648: taking the first `search()` hit picks a winner from an
    ambiguity — a rotated range or a backfill window is not evidence that the file
    belongs to its first date."""
    p = tmp_path / "job_2026-07-29_to_2026-07-30.log"
    p.write_text("anything\n")
    status, lines, why = la.lines_for_date(p, D30)
    assert status == la.UNATTRIBUTABLE and lines == []
    assert "2 distinct dates" in why


def test_a_filename_repeating_ONE_date_is_still_attributable(tmp_path):
    """Anti-vacuity: `run_2026-07-30_2026-07-30.log` is redundant, not ambiguous."""
    p = tmp_path / "run_2026-07-30_snapshot_2026-07-30.log"
    p.write_text("a\nb\n")
    status, lines, _ = la.lines_for_date(p, D30)
    assert status == la.ATTRIBUTED_BY_FILENAME and len(lines) == 2


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


# --- the first retrofit: rq105_status._errors ------------------------------------
# It took `lines[-1]` from an append-only `launchd_*.err` and listed it under a
# header reading "rq105 status - <today>". Measured 2026-07-30, both real files were
# days stale and neither line carried a timestamp, so neither could be attributed to
# any date. A stale error is worth surfacing; calling it recent is not.

import sys as _sys

_ST = importlib.util.spec_from_file_location(
    "rq105_status", REPO / "ops" / "renquant105" / "rq105_status.py")
_st = importlib.util.module_from_spec(_ST)
_ST.loader.exec_module(_st)


def _err_fixture(tmp_path, name, body, mtime_days_ago=0):
    import os, time
    d = tmp_path / "logs" / "rq105"; d.mkdir(parents=True, exist_ok=True)
    p = d / f"launchd_{name}.err"
    p.write_text(body)
    ts = time.time() - mtime_days_ago * 86400
    os.utime(p, (ts, ts))
    return tmp_path


def test_an_err_entry_states_the_file_age_and_that_the_line_date_is_unknown(tmp_path):
    root = _err_fixture(tmp_path, "x", "some failure\n", mtime_days_ago=3)
    out = _st._errors(root, dt.date.today())
    assert len(out) == 1
    assert "line date UNKNOWN" in out[0]
    assert "3d ago" in out[0]


def test_a_file_written_today_says_today_not_a_day_count(tmp_path):
    root = _err_fixture(tmp_path, "y", "boom\n", mtime_days_ago=0)
    out = _st._errors(root, dt.date.today())
    assert "[today; line date UNKNOWN]" in out[0], out


def test_an_empty_err_file_is_not_reported(tmp_path):
    """Anti-vacuity in the other direction: launchd creates these empty, and
    reporting every job every run would drown the real ones."""
    root = _err_fixture(tmp_path, "z", "")
    assert _st._errors(root, dt.date.today()) == []


def test_the_entry_never_claims_the_failure_is_RECENT(tmp_path):
    """The word the old docstring used, and the claim the data cannot support."""
    root = _err_fixture(tmp_path, "w", "old thing\n", mtime_days_ago=30)
    out = _st._errors(root, dt.date.today())
    assert "recent" not in out[0].lower()
    assert "30d ago" in out[0]
