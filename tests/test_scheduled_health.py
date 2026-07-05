"""Tests for renquant_orchestrator.scheduled_health — scheduled-job health surface."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from renquant_orchestrator.scheduled_health import (
    REJECT_MARKERS,
    _classify,
    _last_log_excerpt,
    _load_status_source,
    _status_by_job,
    build_scheduled_health,
)


# ---------------------------------------------------------------------------
# _load_status_source
# ---------------------------------------------------------------------------


class TestLoadStatusSource:
    def test_none_returns_empty_dict(self):
        assert _load_status_source(None) == {}

    def test_valid_json_object(self, tmp_path: Path):
        f = tmp_path / "status.json"
        f.write_text(json.dumps({"job_a": {"last_exit": 0}}))
        result = _load_status_source(f)
        assert result == {"job_a": {"last_exit": 0}}

    def test_string_path(self, tmp_path: Path):
        f = tmp_path / "status.json"
        f.write_text(json.dumps({"x": 1}))
        result = _load_status_source(str(f))
        assert result == {"x": 1}

    def test_non_dict_raises(self, tmp_path: Path):
        f = tmp_path / "status.json"
        f.write_text(json.dumps([1, 2, 3]))
        with pytest.raises(ValueError, match="must be a JSON object"):
            _load_status_source(f)

    def test_non_dict_string_raises(self, tmp_path: Path):
        f = tmp_path / "status.json"
        f.write_text(json.dumps("just a string"))
        with pytest.raises(ValueError, match="must be a JSON object"):
            _load_status_source(f)

    def test_empty_object(self, tmp_path: Path):
        f = tmp_path / "status.json"
        f.write_text("{}")
        assert _load_status_source(f) == {}

    def test_missing_file_raises(self, tmp_path: Path):
        f = tmp_path / "does_not_exist.json"
        with pytest.raises(FileNotFoundError):
            _load_status_source(f)

    def test_invalid_json_raises(self, tmp_path: Path):
        f = tmp_path / "bad.json"
        f.write_text("not json at all")
        with pytest.raises(json.JSONDecodeError):
            _load_status_source(f)


# ---------------------------------------------------------------------------
# _status_by_job
# ---------------------------------------------------------------------------


class TestStatusByJob:
    def test_top_level_dict(self):
        payload = {
            "job_a": {"last_exit": 0, "reason": "ok"},
            "job_b": {"last_exit": 1},
        }
        result = _status_by_job(payload)
        assert set(result.keys()) == {"job_a", "job_b"}
        assert result["job_a"]["last_exit"] == 0

    def test_nested_jobs_key(self):
        payload = {
            "jobs": {
                "j1": {"last_exit": 0},
                "j2": {"last_exit": 1},
            }
        }
        result = _status_by_job(payload)
        assert set(result.keys()) == {"j1", "j2"}

    def test_list_format(self):
        payload = {
            "jobs": [
                {"job_id": "j1", "last_exit": 0},
                {"job_id": "j2", "last_exit": 1},
            ]
        }
        result = _status_by_job(payload)
        assert set(result.keys()) == {"j1", "j2"}
        assert result["j1"]["last_exit"] == 0

    def test_list_skips_items_without_job_id(self):
        payload = {
            "jobs": [
                {"job_id": "j1", "last_exit": 0},
                {"no_id": True},
                {"job_id": "", "last_exit": 2},
            ]
        }
        result = _status_by_job(payload)
        assert list(result.keys()) == ["j1"]

    def test_list_skips_non_dict_items(self):
        payload = {"jobs": [{"job_id": "j1"}, "not_a_dict", 42]}
        result = _status_by_job(payload)
        assert list(result.keys()) == ["j1"]

    def test_empty_payload(self):
        assert _status_by_job({}) == {}

    def test_non_dict_values_skipped(self):
        payload = {
            "job_a": {"last_exit": 0},
            "job_b": "not a dict",
            "job_c": 42,
        }
        result = _status_by_job(payload)
        assert list(result.keys()) == ["job_a"]

    def test_integer_job_id_converted_to_str(self):
        payload = {123: {"last_exit": 0}}
        result = _status_by_job(payload)
        assert "123" in result

    def test_jobs_key_is_non_dict_non_list(self):
        payload = {"jobs": "unexpected"}
        assert _status_by_job(payload) == {}

    def test_returns_copies_not_references(self):
        inner = {"last_exit": 0}
        payload = {"j1": inner}
        result = _status_by_job(payload)
        result["j1"]["last_exit"] = 99
        assert inner["last_exit"] == 0


# ---------------------------------------------------------------------------
# _last_log_excerpt
# ---------------------------------------------------------------------------


class TestLastLogExcerpt:
    def test_no_paths(self):
        path, excerpt = _last_log_excerpt([], max_chars=100)
        assert path is None
        assert excerpt is None

    def test_all_none_paths(self):
        path, excerpt = _last_log_excerpt([None, None], max_chars=100)
        assert path is None
        assert excerpt is None

    def test_all_empty_string_paths(self):
        path, excerpt = _last_log_excerpt(["", ""], max_chars=100)
        assert path is None
        assert excerpt is None

    def test_first_existing_file_wins(self, tmp_path: Path):
        f1 = tmp_path / "log1.txt"
        f2 = tmp_path / "log2.txt"
        f1.write_text("content of first")
        f2.write_text("content of second")
        path, excerpt = _last_log_excerpt([str(f1), str(f2)], max_chars=1000)
        assert path == str(f1)
        assert excerpt == "content of first"

    def test_skips_missing_files(self, tmp_path: Path):
        f2 = tmp_path / "log2.txt"
        f2.write_text("second file content")
        path, excerpt = _last_log_excerpt(
            [str(tmp_path / "missing.txt"), str(f2)], max_chars=1000
        )
        assert path == str(f2)
        assert excerpt == "second file content"

    def test_skips_directories(self, tmp_path: Path):
        d = tmp_path / "a_dir"
        d.mkdir()
        f = tmp_path / "log.txt"
        f.write_text("hello")
        path, excerpt = _last_log_excerpt([str(d), str(f)], max_chars=1000)
        assert path == str(f)

    def test_truncation(self, tmp_path: Path):
        f = tmp_path / "big.txt"
        f.write_text("A" * 100)
        path, excerpt = _last_log_excerpt([str(f)], max_chars=10)
        assert len(excerpt) == 10
        assert excerpt == "A" * 10

    def test_no_truncation_when_short(self, tmp_path: Path):
        f = tmp_path / "short.txt"
        f.write_text("short")
        _, excerpt = _last_log_excerpt([str(f)], max_chars=1000)
        assert excerpt == "short"

    def test_skips_none_in_mixed_list(self, tmp_path: Path):
        f = tmp_path / "log.txt"
        f.write_text("found")
        path, excerpt = _last_log_excerpt([None, "", str(f)], max_chars=100)
        assert excerpt == "found"

    def test_empty_file(self, tmp_path: Path):
        f = tmp_path / "empty.txt"
        f.write_text("")
        path, excerpt = _last_log_excerpt([str(f)], max_chars=100)
        assert path == str(f)
        assert excerpt == ""


# ---------------------------------------------------------------------------
# _classify
# ---------------------------------------------------------------------------


class TestClassify:
    def test_none_exit_returns_unknown(self):
        assert _classify(None, None, None) == "unknown"

    def test_non_integer_exit_returns_unknown(self):
        assert _classify("not_a_number", None, None) == "unknown"

    def test_exit_zero_returns_ok(self):
        assert _classify(0, None, None) == "ok"

    def test_exit_zero_string_returns_ok(self):
        assert _classify("0", None, None) == "ok"

    def test_exit_nonzero_no_markers_returns_crash(self):
        assert _classify(1, None, None) == "crash"

    def test_exit_nonzero_with_unrelated_reason(self):
        assert _classify(1, "some other error", None) == "crash"

    @pytest.mark.parametrize("marker", REJECT_MARKERS)
    def test_each_reject_marker_in_reason(self, marker: str):
        assert _classify(1, f"run failed: {marker} at step 3", None) == "reject"

    @pytest.mark.parametrize("marker", REJECT_MARKERS)
    def test_each_reject_marker_in_log(self, marker: str):
        assert _classify(1, None, f"log line: {marker} detected") == "reject"

    def test_marker_case_insensitive(self):
        assert _classify(1, "GATE REJECTED", None) == "reject"

    def test_marker_mixed_case(self):
        assert _classify(1, None, "Preflight Failed here") == "reject"

    def test_exit_zero_with_marker_still_ok(self):
        assert _classify(0, "gate rejected", None) == "ok"

    def test_negative_exit_code_crash(self):
        assert _classify(-1, None, None) == "crash"

    def test_negative_exit_code_with_marker_reject(self):
        assert _classify(-9, "model rejected", None) == "reject"

    def test_float_exit_truncated(self):
        assert _classify(0.9, None, None) == "ok"

    def test_large_exit_code_crash(self):
        assert _classify(137, "killed by signal", None) == "crash"

    def test_both_reason_and_log_searched(self):
        assert _classify(1, "clean reason", "log: blocked by gate") == "reject"

    def test_none_reason_none_log(self):
        assert _classify(1, None, None) == "crash"


# ---------------------------------------------------------------------------
# build_scheduled_health  (integration, mocked inventory)
# ---------------------------------------------------------------------------


def _mock_inventory():
    return {
        "schema_version": 1,
        "jobs": [
            {
                "job_id": "daily_full",
                "kind": "daily",
                "migration_state": "native",
                "production_safe": True,
                "launchd_label": "com.renquant.daily-full",
                "launchd_stderr_path": None,
                "launchd_stdout_path": None,
            },
            {
                "job_id": "weekly_retrain",
                "kind": "weekly",
                "migration_state": "native",
                "production_safe": True,
                "launchd_label": "com.renquant.weekly-retrain",
                "launchd_stderr_path": None,
                "launchd_stdout_path": None,
            },
        ],
    }


class TestBuildScheduledHealth:
    @patch("renquant_orchestrator.scheduled_health.inventory_payload", _mock_inventory)
    def test_no_status_source(self):
        result = build_scheduled_health()
        assert result["schema_version"] == 1
        assert result["owner_repo"] == "renquant-orchestrator"
        assert result["status_source"] is None
        assert len(result["jobs"]) == 2
        for job in result["jobs"]:
            assert job["health_verdict"] == "unknown"
        s = result["summary"]
        assert s["total"] == 2
        assert s["ok"] == 0
        assert s["unknown"] == 2
        assert s["red_job_count"] == 0

    @patch("renquant_orchestrator.scheduled_health.inventory_payload", _mock_inventory)
    def test_all_ok(self, tmp_path: Path):
        status = {
            "daily_full": {"last_exit": 0},
            "weekly_retrain": {"last_exit": 0},
        }
        sf = tmp_path / "status.json"
        sf.write_text(json.dumps(status))
        result = build_scheduled_health(status_json=sf)
        assert result["status_source"] == str(sf)
        s = result["summary"]
        assert s["ok"] == 2
        assert s["unknown"] == 0
        assert s["crash"] == 0
        assert s["reject"] == 0

    @patch("renquant_orchestrator.scheduled_health.inventory_payload", _mock_inventory)
    def test_mixed_verdicts(self, tmp_path: Path):
        status = {
            "daily_full": {"last_exit": 0},
            "weekly_retrain": {"last_exit": 1, "reason": "gate rejected"},
        }
        sf = tmp_path / "status.json"
        sf.write_text(json.dumps(status))
        result = build_scheduled_health(status_json=sf)
        s = result["summary"]
        assert s["ok"] == 1
        assert s["reject"] == 1
        assert s["red_job_count"] == 1
        assert "weekly_retrain" in s["red_jobs"]

    @patch("renquant_orchestrator.scheduled_health.inventory_payload", _mock_inventory)
    def test_crash_counted_as_red(self, tmp_path: Path):
        status = {
            "daily_full": {"last_exit": 1, "reason": "segfault"},
            "weekly_retrain": {"last_exit": 0},
        }
        sf = tmp_path / "status.json"
        sf.write_text(json.dumps(status))
        result = build_scheduled_health(status_json=sf)
        s = result["summary"]
        assert s["crash"] == 1
        assert s["red_job_count"] == 1
        assert "daily_full" in s["red_jobs"]

    @patch("renquant_orchestrator.scheduled_health.inventory_payload", _mock_inventory)
    def test_log_excerpt_attached(self, tmp_path: Path):
        log_file = tmp_path / "daily.log"
        log_file.write_text("line1\nline2\ngate rejected here\n")
        status = {"daily_full": {"last_exit": 1, "last_log_path": str(log_file)}}
        sf = tmp_path / "status.json"
        sf.write_text(json.dumps(status))
        result = build_scheduled_health(status_json=sf)
        daily = next(j for j in result["jobs"] if j["job_id"] == "daily_full")
        assert daily["health_verdict"] == "reject"
        assert daily["log_excerpt"] is not None
        assert "gate rejected" in daily["log_excerpt"]

    @patch("renquant_orchestrator.scheduled_health.inventory_payload", _mock_inventory)
    def test_log_tail_chars_respected(self, tmp_path: Path):
        log_file = tmp_path / "daily.log"
        log_file.write_text("X" * 200)
        status = {"daily_full": {"last_exit": 1, "last_log_path": str(log_file)}}
        sf = tmp_path / "status.json"
        sf.write_text(json.dumps(status))
        result = build_scheduled_health(status_json=sf, log_tail_chars=50)
        daily = next(j for j in result["jobs"] if j["job_id"] == "daily_full")
        assert len(daily["log_excerpt"]) == 50

    @patch("renquant_orchestrator.scheduled_health.inventory_payload", _mock_inventory)
    def test_launchd_stderr_fallback(self, tmp_path: Path):
        """When last_log_path is absent but launchd_stderr_path exists, use it."""
        stderr_file = tmp_path / "stderr.log"
        stderr_file.write_text("error output here")

        def mock_inv():
            return {
                "schema_version": 1,
                "jobs": [
                    {
                        "job_id": "daily_full",
                        "kind": "daily",
                        "migration_state": "native",
                        "production_safe": True,
                        "launchd_label": "com.renquant.daily-full",
                        "launchd_stderr_path": str(stderr_file),
                        "launchd_stdout_path": None,
                    },
                ],
            }

        with patch(
            "renquant_orchestrator.scheduled_health.inventory_payload", mock_inv
        ):
            status = {"daily_full": {"last_exit": 1}}
            sf = tmp_path / "status.json"
            sf.write_text(json.dumps(status))
            result = build_scheduled_health(status_json=sf)
            daily = result["jobs"][0]
            assert daily["log_excerpt"] == "error output here"
            assert daily["last_log_path"] == str(stderr_file)

    @patch("renquant_orchestrator.scheduled_health.inventory_payload", _mock_inventory)
    def test_unknown_jobs_listed(self):
        result = build_scheduled_health()
        s = result["summary"]
        assert set(s["unknown_jobs"]) == {"daily_full", "weekly_retrain"}

    @patch("renquant_orchestrator.scheduled_health.inventory_payload", _mock_inventory)
    def test_status_with_nested_jobs_key(self, tmp_path: Path):
        status = {"jobs": {"daily_full": {"last_exit": 0}}}
        sf = tmp_path / "status.json"
        sf.write_text(json.dumps(status))
        result = build_scheduled_health(status_json=sf)
        daily = next(j for j in result["jobs"] if j["job_id"] == "daily_full")
        assert daily["health_verdict"] == "ok"

    @patch("renquant_orchestrator.scheduled_health.inventory_payload", _mock_inventory)
    def test_job_row_fields(self, tmp_path: Path):
        status = {
            "daily_full": {
                "last_exit": 0,
                "last_started_at": "2026-07-04T09:00:00",
                "last_finished_at": "2026-07-04T09:05:00",
                "reason": "completed normally",
            }
        }
        sf = tmp_path / "status.json"
        sf.write_text(json.dumps(status))
        result = build_scheduled_health(status_json=sf)
        daily = next(j for j in result["jobs"] if j["job_id"] == "daily_full")
        assert daily["job_id"] == "daily_full"
        assert daily["kind"] == "daily"
        assert daily["migration_state"] == "native"
        assert daily["production_safe"] is True
        assert daily["launchd_label"] == "com.renquant.daily-full"
        assert daily["last_exit"] == 0
        assert daily["last_started_at"] == "2026-07-04T09:00:00"
        assert daily["last_finished_at"] == "2026-07-04T09:05:00"
        assert daily["reason"] == "completed normally"
