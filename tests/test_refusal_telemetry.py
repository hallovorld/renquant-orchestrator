"""Tests for ops/refusal_telemetry.py (GOAL-5 AC5).

CHANGES_REQUESTED REGRESSION GUARD (PR #619, codex review 2026-07-30):
  P1 — the scanner used to count ANY line containing a check name as a
       "firing" (``if check in line``), so a non-event mention (log
       registration text, config dumps) raised a false operational alert.
       Fixed by matching only the exact line ``task_funnel_integrity.py``
       emits: ``FunnelIntegrityAlert: STRUCTURAL_BLOCK ... fired=[...]``.
  P2 — the "unknown check" fail-open path only recognized tokens ending in
       five hardcoded suffixes, so a real new refusal reason (e.g.
       ``fired=['new_refusal']``) was silently missed. Fixed by reading
       every name out of the structured ``fired=[...]`` list directly —
       anything not in KNOWN_CHECKS is UNTRACKED, no suffix heuristic.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ops"))
from refusal_telemetry import (  # noqa: E402
    FIRED_LINE,
    KNOWN_CHECKS,
    log_date,
    main,
    parse_fired_list,
    scan,
)

FIRING_LINE = (
    "2026-07-22 16:48:17,796 [WARNING] kernel.pipeline.funnel_integrity: "
    "FunnelIntegrityAlert: STRUCTURAL_BLOCK — engineering condition "
    "suppressed buy capability; do NOT report this session as a normal "
    "no-trade. fired=['single_gate_funnel_kill', 'fail_close_event']"
)

MENTION_ONLY_LINE = (
    "2026-07-15 09:00:00,000 [INFO] some.module: checks registered: "
    "single_gate_funnel_kill, fail_close_event, wash_sale_mass_block"
)

UNKNOWN_FIRING_LINE = (
    "2026-07-16 09:00:01,000 [WARNING] kernel.pipeline.funnel_integrity: "
    "FunnelIntegrityAlert: STRUCTURAL_BLOCK — engineering condition "
    "suppressed buy capability; do NOT report this session as a normal "
    "no-trade. fired=['new_refusal']"
)


def write_log(tmp_path: Path, name: str, lines: list[str]) -> Path:
    p = tmp_path / name
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


class TestFiredLineGrammar:
    """P1 regression guard: only the exact emitted grammar counts."""

    def test_known_event_parsing_counts_as_firing(self, tmp_path):
        write_log(tmp_path, "2026-07-22.log", [FIRING_LINE])
        r = scan(tmp_path, since=None)
        assert len(r["per_check"]["single_gate_funnel_kill"]) == 1
        assert len(r["per_check"]["fail_close_event"]) == 1
        hit = r["per_check"]["single_gate_funnel_kill"][0]
        assert hit["date"] == "2026-07-22"
        assert hit["file"] == "2026-07-22.log"

    def test_bare_mention_is_not_a_firing(self, tmp_path):
        """codex's exact repro: 'checks registered: <name>, ...' must not fire."""
        write_log(tmp_path, "2026-07-15.log", [MENTION_ONLY_LINE])
        r = scan(tmp_path, since=None)
        assert r["per_check"] == {}
        assert r["untracked_candidates"] == {}

    def test_info_line_bare_count_is_not_a_firing(self, tmp_path):
        write_log(tmp_path, "2026-07-17.log", [
            "2026-07-17 14:00:00,000 [INFO] kernel.pipeline.funnel_integrity: "
            "funnel integrity: verdict=DEGRADED fired=2 structural=False "
            "candidates_final=3 buys=1",
        ])
        r = scan(tmp_path, since=None)
        assert r["per_check"] == {}
        assert r["untracked_candidates"] == {}


class TestUnknownEventParsing:
    """P2 regression guard: unknown fired-names surface without a suffix rule."""

    def test_unknown_token_reported_untracked_not_dropped(self, tmp_path):
        write_log(tmp_path, "2026-07-16.log", [UNKNOWN_FIRING_LINE])
        r = scan(tmp_path, since=None)
        assert r["per_check"] == {}
        assert r["untracked_candidates"] == {"new_refusal": 1}

    def test_unknown_token_without_a_known_suffix_still_caught(self, tmp_path):
        """The old code only matched tokens ending in five hardcoded suffixes
        (_kill/_collapse/_mismatch/_event/_block); a token with none of them
        must still be surfaced now that we read the structured list."""
        line = UNKNOWN_FIRING_LINE.replace("new_refusal", "brand_new_reason")
        write_log(tmp_path, "2026-07-16.log", [line])
        r = scan(tmp_path, since=None)
        assert r["untracked_candidates"] == {"brand_new_reason": 1}

    def test_all_known_checks_recognized(self):
        for check in KNOWN_CHECKS:
            assert check in KNOWN_CHECKS


class TestDateFiltering:
    def test_since_skips_older_files(self, tmp_path):
        write_log(tmp_path, "2026-07-01.log", [FIRING_LINE])
        write_log(tmp_path, "2026-07-22.log", [FIRING_LINE])
        r = scan(tmp_path, since=__import__("datetime").date(2026, 7, 10))
        assert r["files_skipped_by_since"] == 1
        assert r["files_scanned"] == 1
        assert len(r["per_check"]["single_gate_funnel_kill"]) == 1
        assert r["per_check"]["single_gate_funnel_kill"][0]["file"] == "2026-07-22.log"

    def test_log_date_parses_iso_prefix(self):
        assert log_date(Path("2026-07-22.log")) == __import__("datetime").date(2026, 7, 22)

    def test_log_date_none_for_undated_filename(self):
        assert log_date(Path("junk.log")) is None


class TestMalformedInput:
    def test_undated_file_still_scanned_but_excluded_from_dated_recent(self, tmp_path):
        write_log(tmp_path, "junk.log", [FIRING_LINE])
        r = scan(tmp_path, since=None)
        assert r["files_scanned"] == 1
        hit = r["per_check"]["single_gate_funnel_kill"][0]
        assert hit["date"] is None

    def test_malformed_fired_payload_does_not_crash(self, tmp_path):
        bad = (
            "2026-07-18 00:00:00,000 [WARNING] kernel.pipeline.funnel_integrity: "
            "FunnelIntegrityAlert: STRUCTURAL_BLOCK — ... fired=[not, valid, python"
        )
        write_log(tmp_path, "2026-07-18.log", [bad])
        r = scan(tmp_path, since=None)
        assert r["per_check"] == {}
        assert r["untracked_candidates"] == {}

    def test_parse_fired_list_rejects_non_list_and_non_string_items(self):
        assert parse_fired_list("42") is None
        assert parse_fired_list("['ok', 1]") is None
        assert parse_fired_list("['a', 'b']") == ["a", "b"]

    def test_fired_line_regex_requires_structural_block(self):
        degraded = FIRING_LINE.replace("STRUCTURAL_BLOCK", "DEGRADED")
        assert FIRED_LINE.search(degraded) is None
        assert FIRED_LINE.search(FIRING_LINE) is not None


class TestAlertWindowExitCodes:
    def test_recent_firing_inside_window_exits_1(self, tmp_path, capsys):
        write_log(tmp_path, "2026-07-22.log", [FIRING_LINE])
        rc = main([
            "--log-dir", str(tmp_path),
            "--today", "2026-07-25",
            "--alert-window-days", "7",
        ])
        assert rc == 1
        assert "ALERT" in capsys.readouterr().out

    def test_firing_outside_window_exits_0(self, tmp_path, capsys):
        write_log(tmp_path, "2026-07-01.log", [FIRING_LINE])
        rc = main([
            "--log-dir", str(tmp_path),
            "--today", "2026-07-25",
            "--alert-window-days", "7",
        ])
        assert rc == 0
        assert "OK" in capsys.readouterr().out

    def test_no_log_dir_aborts_with_exit_2(self, tmp_path, capsys):
        rc = main(["--log-dir", str(tmp_path / "does-not-exist")])
        assert rc == 2
        assert "ABORT" in capsys.readouterr().out


class TestJsonModeIsPureJson:
    """MED regression guard (PR #619, codex review 2026-07-30): --json stdout
    must be parseable as JSON with nothing else on it — no summary/CAVEAT
    prose before or after the blob."""

    def test_json_stdout_parses_with_a_firing(self, tmp_path, capsys):
        write_log(tmp_path, "2026-07-22.log", [FIRING_LINE])
        rc = main([
            "--log-dir", str(tmp_path),
            "--today", "2026-07-25",
            "--alert-window-days", "7",
            "--json",
        ])
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert rc == 1
        assert parsed["summary"]["single_gate_funnel_kill"] == 1
        assert len(parsed["recent"]) == 2

    def test_json_stdout_parses_when_clean(self, tmp_path, capsys):
        write_log(tmp_path, "2026-07-01.log", [FIRING_LINE])
        rc = main([
            "--log-dir", str(tmp_path),
            "--today", "2026-07-25",
            "--alert-window-days", "7",
            "--json",
        ])
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert rc == 0
        assert parsed["recent"] == []
