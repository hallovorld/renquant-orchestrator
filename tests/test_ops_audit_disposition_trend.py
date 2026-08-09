"""GOAL-1: an audit where nine of eleven detectors fire daily and nothing is
ever dispositioned is one the reader learns to skip.

MEASURED 2026-08-05: `com.renquant.ops-audit` runs on a schedule and exits 1
every time. Its three retained dated logs report findings 10 / 10 / 9 out of 11
detectors, and every one printed `ledger … (0 ack(s))`.

The claim is deliberately WINDOW-scoped, and these tests hold it there: the
tool reads retained logs, so it can say "no ack observed in the scanned
window" and never "never".
"""
from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ops"))
from ops_audit_disposition_trend import (  # noqa: E402
    dated_logs, read_runs, render, summarize)

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
        assert s["no_ack_observed_in_window"] is True
        assert "NO acknowledgement observed in this window" in render(
            read_runs(tmp_path), s)

    def test_the_call_out_REFUSES_to_say_never(self, tmp_path):
        """Retained logs cannot testify about pruned ones. The wording must
        stay inside the window, and say so out loud."""
        _log(tmp_path, "2026-08-03", 0, 10, acks=0)
        _log(tmp_path, "2026-08-05", 2, 9, acks=0)
        text = render(read_runs(tmp_path), summarize(read_runs(tmp_path)))
        assert "never" not in text.lower().replace("NOT a claim", "")
        assert "retention can hide an" in text

    def test_ANY_ack_stops_the_call_out(self, tmp_path):
        """Anti-false-positive: one disposition means the mechanism is in use."""
        _log(tmp_path, "2026-08-03", 0, 10, acks=0)
        _log(tmp_path, "2026-08-05", 2, 9, acks=1)
        s = summarize(read_runs(tmp_path))
        assert s["no_ack_observed_in_window"] is False
        assert "NO acknowledgement observed" not in render(read_runs(tmp_path), s)

    def test_a_log_with_NO_ledger_line_leaves_acks_unknown_not_zero(self, tmp_path):
        """Absence of the line is not evidence of zero acks."""
        _log(tmp_path, "2026-08-05", 2, 9, acks=None)
        rows = read_runs(tmp_path)
        assert rows[0]["n_acks"] is None
        assert summarize(rows)["no_ack_observed_in_window"] is False


class TestTheWindowIsStated:
    def test_the_scanned_window_is_rendered(self, tmp_path):
        _log(tmp_path, "2026-08-03", 0, 10)
        _log(tmp_path, "2026-08-05", 2, 9)
        rows = read_runs(tmp_path)
        text = render(rows, summarize(rows, n_dated_on_disk=len(dated_logs(tmp_path))))
        assert "window: 2026-08-03 … 2026-08-05 (2/2 parsed)" in text
        assert "all retained dated logs" in text

    def test_a_truncated_window_says_SUBSET(self, tmp_path):
        for d in ("2026-08-03", "2026-08-04", "2026-08-05"):
            _log(tmp_path, d, 0, 10)
        rows = read_runs(tmp_path, days=2)
        s = summarize(rows, n_dated_on_disk=len(dated_logs(tmp_path)))
        assert s["window_is_all_retained_logs"] is False
        assert "a SUBSET of the retained dated logs" in render(rows, s)

    def test_coverage_unmeasured_is_NOT_reported_as_complete(self, tmp_path):
        _log(tmp_path, "2026-08-05", 2, 9)
        s = summarize(read_runs(tmp_path))
        assert s["window_is_all_retained_logs"] is None
        assert "coverage vs disk not measured" in render(read_runs(tmp_path), s)

    def test_an_UNDATED_log_cannot_evict_a_dated_run_from_the_window(self, tmp_path):
        """REGRESSION: windowing before the date filter let `ops_audit.log`
        take a slot and silently shorten the evidence the claim rests on."""
        _log(tmp_path, "2026-08-03", 0, 10)
        _log(tmp_path, "2026-08-04", 1, 10)
        (tmp_path / "ops_audit_latest.log").write_text("noise\n", encoding="utf-8")
        rows = read_runs(tmp_path, days=2)
        assert [r["date"] for r in rows] == ["2026-08-03", "2026-08-04"]


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
    """Bound to reality — on the transition, not the count.

    The first version asserted the NO-ack state and fired when dispositioning
    began (2026-08-06, the transition it existed to catch). The count cannot
    be the durable binding in either direction: acks EXPIRE after
    ACK_MAX_AGE_DAYS=14, so a zero-ack window recurs by design. What must
    hold from now on is that the RECORD acknowledges the transition — a
    reader of the 2026-08-05 record must not inherit "the mechanism is
    unused" after it stopped being true."""
    from ops_audit_disposition_trend import LOGS

    if not LOGS.is_dir():
        pytest.skip("ops_audit logs absent — the unit tests above still ran")
    rows = read_runs()
    parsed = [r for r in rows if r.get("parsed")]
    if len(parsed) < 2:
        pytest.skip(f"only {len(parsed)} parsed runs on this box")
    s = summarize(rows, n_dated_on_disk=len(dated_logs()))
    assert s["findings_max"] >= 8, s
    record = (Path(__file__).resolve().parent.parent / "doc" / "progress" /
              "2026-08-05-goal1-ops-audit-disposition.md")
    assert "DISPOSITION-FIRST-OBSERVED 2026-08-06" in record.read_text(
        encoding="utf-8"), (
        "the GOAL-1 record no longer acknowledges that dispositioning began "
        "on 2026-08-06 — re-derive it rather than reverting it", s)
