"""Tests for ops/renquant105/rq105_liveness_check.py's row_event_time freshness
check, specifically the session-close cap (round-5 fix): the check itself runs
once daily at 14:00 PT, ~1hr after the 13:00 PT NYSE close, so evaluating the
continuously-sampled quote feed's staleness against raw wall-clock now would
fail EVERY healthy day once the sampler correctly stops at close. All ages
below are computed relative to the real `datetime.now()` at test time (not a
mocked clock) so the tests stay deterministic without patching the clock."""
from __future__ import annotations

import datetime as dt
import json
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ops"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ops" / "renquant105"))

import rq105_liveness_check as liveness  # noqa: E402
from rq105_liveness_check import _data_output_fresh, _row_timestamp_quote  # noqa: E402


def _install_fake_send(monkeypatch) -> list[dict]:
    """Replace the lazily-imported renquant_common.notify.send with a recorder,
    so a test can assert exactly what _alert forwarded (priority/tags/topic)
    without any network."""
    calls: list[dict] = []

    def fake_send(title, body, topic=None, *, priority=None, tags=None,
                  timeout=5.0, env_file=None):
        calls.append(
            {"title": title, "body": body, "topic": topic,
             "priority": priority, "tags": tags}
        )
        return True

    fake_mod = types.ModuleType("renquant_common.notify")
    fake_mod.send = fake_send
    monkeypatch.setitem(sys.modules, "renquant_common.notify", fake_mod)
    return calls


class TestUnmissableAlert:
    """GOAL-5: a 105-DOWN alert shares the 'renquant' topic with every other
    sentinel, so it must stand out — elevated priority + distinctive tags +
    an unmistakable title (the operator's 'why didn't I get an ntfy')."""

    def test_alert_forwards_elevated_priority_and_tags(self, monkeypatch):
        calls = _install_fake_send(monkeypatch)
        monkeypatch.delenv("RQ105_NTFY_TOPIC", raising=False)

        liveness._alert("🚨 rq105 DOWN — x", "body")

        assert len(calls) == 1
        assert calls[0]["priority"] == "urgent"
        assert calls[0]["tags"] == "rotating_light,rq105"
        # Unset RQ105_NTFY_TOPIC -> topic None -> sender's normal resolution
        # ($RQ/.env NTFY_TOPIC -> fleet default "renquant"): stays on the topic
        # the operator demonstrably receives.
        assert calls[0]["topic"] is None

    def test_alert_routes_dedicated_topic_when_env_set(self, monkeypatch):
        calls = _install_fake_send(monkeypatch)
        monkeypatch.setenv("RQ105_NTFY_TOPIC", "rq105-alerts")

        liveness._alert("🚨 rq105 DOWN — x", "body")

        assert calls[0]["topic"] == "rq105-alerts"

    def test_main_stale_sends_unmissable_urgent_tagged_alert(self, monkeypatch, tmp_path):
        """End-to-end on a STALE fixture: with the wrapper logs missing and a
        collector reported stale, main() must send an urgent, distinctively-
        tagged, unmistakable-titled alert (title carries the 🚨 DOWN marker)."""
        calls = _install_fake_send(monkeypatch)
        monkeypatch.delenv("RQ105_NTFY_TOPIC", raising=False)
        # Session day; empty LOGS dir -> all three wrapper logs missing (stale).
        monkeypatch.setattr(liveness, "_is_session_day", lambda day: True)
        monkeypatch.setattr(liveness, "LOGS", str(tmp_path))
        # Avoid needing the NYSE calendar / collector modules in the test env.
        monkeypatch.setattr(
            liveness, "check_collector_data_outputs", lambda data_root, as_of: {}
        )

        rc = liveness.main()

        assert rc == 1
        assert len(calls) == 1
        assert calls[0]["title"].startswith("🚨")
        assert "DOWN" in calls[0]["title"]
        assert calls[0]["priority"] == "urgent"
        assert calls[0]["tags"] == "rotating_light,rq105"


def _write_row(tmp_path: Path, ts: dt.datetime, date_iso: str) -> Path:
    path = tmp_path / "intraday_ticks.jsonl"
    row = {"date": date_iso, "ticker": "AAPL", "ts": ts.isoformat()}
    path.write_text(json.dumps(row) + "\n")
    return path


class TestRowEventTimeSessionCloseCap:
    def test_stale_vs_now_but_fresh_vs_session_close(self, tmp_path):
        """A row from 2h ago reads STALE against raw now (old behavior) but
        OK once capped at a session close that was only 5min after the row —
        the exact 'check runs 1hr after close' scenario from the live alert."""
        now = dt.datetime.now(dt.timezone.utc)
        ts_val = now - dt.timedelta(hours=2)
        session_close = now - dt.timedelta(hours=1, minutes=55)
        today = now.date().isoformat()
        path = _write_row(tmp_path, ts_val, today)

        ok_uncapped, reason_uncapped, _ = _data_output_fresh(
            str(path), today, _row_timestamp_quote, "row_event_time",
        )
        assert ok_uncapped is False
        assert "exceeds" in reason_uncapped

        ok_capped, reason_capped, _ = _data_output_fresh(
            str(path), today, _row_timestamp_quote, "row_event_time",
            session_close_utc=session_close,
        )
        assert ok_capped is True, reason_capped

    def test_during_session_cap_is_a_noop(self, tmp_path):
        """Session close far in the future (still mid-session): behavior is
        unchanged from pre-fix — freshness is judged against real now."""
        now = dt.datetime.now(dt.timezone.utc)
        ts_val = now - dt.timedelta(minutes=2)
        session_close = now + dt.timedelta(hours=3)
        today = now.date().isoformat()
        path = _write_row(tmp_path, ts_val, today)

        ok, reason, _ = _data_output_fresh(
            str(path), today, _row_timestamp_quote, "row_event_time",
            session_close_utc=session_close,
        )
        assert ok is True, reason

    def test_genuinely_stale_still_fails_with_cap(self, tmp_path):
        """A logger that stopped 3h before session close (crashed mid-day)
        must still fail even after the cap — the cap must not mask a real
        lapse, only the 'checked long after a correct close' false alarm."""
        now = dt.datetime.now(dt.timezone.utc)
        ts_val = now - dt.timedelta(hours=3)
        session_close = now - dt.timedelta(minutes=30)
        today = now.date().isoformat()
        path = _write_row(tmp_path, ts_val, today)

        ok, reason, _ = _data_output_fresh(
            str(path), today, _row_timestamp_quote, "row_event_time",
            session_close_utc=session_close,
        )
        assert ok is False
        assert "exceeds" in reason

    def test_future_clock_skew_check_unaffected_by_cap(self, tmp_path):
        """A row timestamped ahead of true now is still rejected as clock
        skew/corruption even when session_close_utc is in the past — the
        skew check must compare against real now, not the capped reference."""
        now = dt.datetime.now(dt.timezone.utc)
        ts_val = now + dt.timedelta(minutes=1)
        session_close = now - dt.timedelta(hours=1)
        today = now.date().isoformat()
        path = _write_row(tmp_path, ts_val, today)

        ok, reason, _ = _data_output_fresh(
            str(path), today, _row_timestamp_quote, "row_event_time",
            session_close_utc=session_close,
        )
        assert ok is False
        assert "FUTURE" in reason

    def test_no_session_close_arg_defaults_to_old_behavior(self, tmp_path):
        """Omitting session_close_utc (e.g. an external caller on an older
        signature) preserves the original raw-now comparison exactly."""
        now = dt.datetime.now(dt.timezone.utc)
        ts_val = now - dt.timedelta(minutes=2)
        today = now.date().isoformat()
        path = _write_row(tmp_path, ts_val, today)

        ok, reason, _ = _data_output_fresh(
            str(path), today, _row_timestamp_quote, "row_event_time",
        )
        assert ok is True, reason
