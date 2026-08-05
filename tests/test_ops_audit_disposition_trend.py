"""GOAL-1: an audit where nine of eleven detectors fire daily and nothing is
ever dispositioned is one the reader learns to skip.

MEASURED 2026-08-05: `com.renquant.ops-audit` runs on a schedule and exits 1
every time. Its three dated logs report findings 10 / 10 / 9 out of 11
detectors, and `ops_audit_acks.json` does not exist — 0 acks, ever.
"""
from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ops"))
from ops_audit_disposition_trend import read_runs, render, summarize  # noqa: E402

SUMMARY = ("ops-audit: 11 detector(s) — ok={ok} findings={f} info=0 "
           "unusable=0 crash=0 timeout=0 missing=0")
LEDGER = "  ledger /somewhere/ops_audit_acks.json ({n} ack(s)), as of 2026-08-05."


def _log(d: Path, date: str, ok: int, findings: int, acks: int | None = 0):
    body = SUMMARY.format(ok=ok, f=findings)
    if acks is not None:
        body += "\n" + LEDGER.format(n=acks)
    (d / f"ops_audit_{date}.log").write_text(body, encoding="utf-8")


class TestTheTrend:
    def test_it_reads_each_dated_log_oldest_first(self, tmp_path):
        _log(tmp_path, "2026-08-04", 1, 10)
        _log(tmp_path, "2026-08-03", 0, 10)
        rows = read_runs(tmp_path)
        assert [r["date"] for r in rows] == ["2026-08-03", "2026-08-04"]

    def test_a_falling_finding_count_reads_as_QUIETER(self, tmp_path):
        _log(tmp_path, "2026-08-03", 0, 10)
        _log(tmp_path, "2026-08-05", 2, 9)
        text = render(read_runs(tmp_path), summarize(read_runs(tmp_path)))
        assert "findings 10 → 9 over 2 runs: quieter" in text

    def test_a_rising_count_reads_as_LOUDER(self, tmp_path):
        _log(tmp_path, "2026-08-03", 5, 6)
        _log(tmp_path, "2026-08-05", 2, 9)
        assert "louder" in render(read_runs(tmp_path), summarize(read_runs(tmp_path)))

    def test_ONE_run_refuses_to_call_a_trend(self, tmp_path):
        """Two points make a line; one makes a number."""
        _log(tmp_path, "2026-08-05", 2, 9)
        text = render(read_runs(tmp_path), summarize(read_runs(tmp_path)))
        assert "no trend can be read yet" in text
        assert "quieter" not in text and "louder" not in text

    def test_the_LAST_summary_in_a_file_wins(self, tmp_path):
        """A log with two runs in it must report the later one, not the first."""
        p = tmp_path / "ops_audit_2026-08-05.log"
        p.write_text(SUMMARY.format(ok=0, f=11) + "\n" +
                     SUMMARY.format(ok=4, f=7) + "\n", encoding="utf-8")
        assert read_runs(tmp_path)[0]["findings"] == 7


class TestDispositionIsTheLoadBearingNumber:
    def test_zero_acks_everywhere_is_called_out(self, tmp_path):
        _log(tmp_path, "2026-08-03", 0, 10, acks=0)
        _log(tmp_path, "2026-08-05", 2, 9, acks=0)
        s = summarize(read_runs(tmp_path))
        assert s["never_dispositioned"] is True
        assert "NOTHING has ever been dispositioned" in render(read_runs(tmp_path), s)

    def test_ANY_ack_stops_the_call_out(self, tmp_path):
        """Anti-false-positive: one disposition means the mechanism is in use."""
        _log(tmp_path, "2026-08-03", 0, 10, acks=0)
        _log(tmp_path, "2026-08-05", 2, 9, acks=1)
        s = summarize(read_runs(tmp_path))
        assert s["never_dispositioned"] is False
        assert "NOTHING has ever been dispositioned" not in render(
            read_runs(tmp_path), s)

    def test_a_log_with_NO_ledger_line_leaves_acks_unknown_not_zero(self, tmp_path):
        """Absence of the line is not evidence of zero acks."""
        _log(tmp_path, "2026-08-05", 2, 9, acks=None)
        rows = read_runs(tmp_path)
        assert rows[0]["n_acks"] is None
        assert summarize(rows)["never_dispositioned"] is False


class TestAbsenceReadsAsAbsence:
    def test_a_log_with_no_summary_is_RECORDED_not_skipped(self, tmp_path):
        """A day the audit failed to summarise is a fact about the audit."""
        (tmp_path / "ops_audit_2026-08-05.log").write_text("crash\n", encoding="utf-8")
        rows = read_runs(tmp_path)
        assert rows and rows[0]["parsed"] is False
        assert "did not report" in rows[0]["note"]
        assert "did not report" in render(rows, summarize(rows))

    def test_a_missing_log_dir_yields_no_rows_not_a_crash(self, tmp_path):
        assert read_runs(tmp_path / "nope") == []


def test_the_LIVE_audit_is_what_the_record_describes():
    """Bound to reality: if the ops-audit starts dispositioning findings, the
    GOAL-1 record must be re-derived rather than inherited."""
    from ops_audit_disposition_trend import LOGS

    if not LOGS.is_dir():
        pytest.skip("ops_audit logs absent — the unit tests above still ran")
    rows = read_runs()
    parsed = [r for r in rows if r.get("parsed")]
    if len(parsed) < 2:
        pytest.skip(f"only {len(parsed)} parsed runs on this box")
    s = summarize(rows)
    assert s["findings_max"] >= 8, s
    assert s["never_dispositioned"] is True, (
        "the ops-audit has started dispositioning findings — re-derive the "
        "GOAL-1 alarm-fatigue record", s)
