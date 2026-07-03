"""Tests for the Stage-1 replay/audit harness (RFC #208 §6/§9): decision
reproducibility on a recorded fixture session, tamper detection on the
recorded outputs, and the §6 constancy invariants at rest."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from renquant_orchestrator.intraday_replay_audit import (
    load_session_ticks,
    main as replay_main,
    replay_session,
)
from renquant_orchestrator.intraday_session_scheduler import (
    ENV_FLAG,
    IntradayDecisioningConfig,
    KillSwitch,
    SessionScheduler,
    ShadowTickWriter,
)

# Reuse the scheduler test fixtures — the fixture session must be recorded by
# the REAL scheduler so replay is exercised end-to-end, not on a synthetic log.
# (Plain-module import: this repo's tests are rootdir-inserted, not a package.)
from test_intraday_session_scheduler import (
    DAY,
    FakeCalendar,
    ManualClock,
    fake_live_state,
    fake_signal,
    fake_tick_runner,
)

ET = ZoneInfo("America/New_York")


def record_fixture_session(tmp_path: Path) -> tuple[dict, list[dict]]:
    """Record a deterministic shadow session and return (manifest, ticks)."""
    scheduler = SessionScheduler(
        config=IntradayDecisioningConfig(enabled=True, tick_seconds=600.0),
        tick_runner=fake_tick_runner,
        signal_loader=lambda day: fake_signal(),
        session_start_provider=lambda day, now: {"watchlist": ["AAA", "BBB", "CCC"]},
        live_state_provider=fake_live_state,
        writer=ShadowTickWriter(tmp_path / "shadow.jsonl"),
        manifest_path=tmp_path / "manifest.json",
        kill_switch=KillSwitch(tmp_path / "KILL"),
        calendar=FakeCalendar({DAY: ("10:00", "11:00")}),
        exit_orders_provider=lambda now: [{"ticker": "ZZZ", "quantity": 2.0}],
        environ={ENV_FLAG: "1"},
        strategy_config_fingerprint="cfg-fp",
    )
    day = datetime.fromisoformat(DAY)
    clock = ManualClock(datetime(day.year, day.month, day.day, 10, 0, tzinfo=ET))
    manifest = scheduler.run_session(now_fn=clock, sleep_fn=clock.sleep)
    ticks = load_session_ticks(tmp_path / "shadow.jsonl", DAY)
    assert manifest["status"] == "completed" and len(ticks) == 5
    return manifest, ticks


# ─────────────────────────── determinism ───────────────────────────
def test_replay_reproduces_recorded_session(tmp_path):
    manifest, ticks = record_fixture_session(tmp_path)
    report = replay_session(
        manifest=manifest, ticks=ticks, tick_runner=fake_tick_runner
    )
    assert report["ok"] is True, report["mismatches"]
    assert report["ticks_checked"] == 5
    assert report["mismatches"] == []
    assert report["signal_version"] == "run-fri:deadbeef"


def test_replay_cli_roundtrip(tmp_path):
    record_fixture_session(tmp_path)
    report_out = tmp_path / "replay_report.json"
    rc = replay_main(
        [
            "--manifest",
            str(tmp_path / "manifest.json"),
            "--shadow-log",
            str(tmp_path / "shadow.jsonl"),
            "--report-out",
            str(report_out),
        ],
        tick_runner=fake_tick_runner,
    )
    assert rc == 0
    report = json.loads(report_out.read_text(encoding="utf-8"))
    assert report["ok"] is True and report["ticks_checked"] == 5


# ─────────────────────────── tamper detection ───────────────────────────
def _tamper_line(path: Path, tick_index: int, mutate) -> None:
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if int(row.get("tick_index", -1)) == tick_index:
            mutate(row)
        lines.append(json.dumps(row, sort_keys=True))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_tampered_decision_is_caught(tmp_path):
    manifest, _ = record_fixture_session(tmp_path)

    def mutate(row):
        row["decisions"]["intents"][0]["quantity"] = 999.0

    _tamper_line(tmp_path / "shadow.jsonl", 0, mutate)
    ticks = load_session_ticks(tmp_path / "shadow.jsonl", DAY)
    report = replay_session(manifest=manifest, ticks=ticks, tick_runner=fake_tick_runner)
    assert report["ok"] is False
    kinds = {m["kind"] for m in report["mismatches"]}
    assert "decision_mismatch" in kinds


def test_tampered_live_state_is_caught(tmp_path):
    manifest, _ = record_fixture_session(tmp_path)

    def mutate(row):
        row["inputs"]["live_state"]["cash"] = 9_999_999.0

    _tamper_line(tmp_path / "shadow.jsonl", 1, mutate)
    ticks = load_session_ticks(tmp_path / "shadow.jsonl", DAY)
    report = replay_session(manifest=manifest, ticks=ticks, tick_runner=fake_tick_runner)
    assert report["ok"] is False
    kinds = {m["kind"] for m in report["mismatches"]}
    assert "live_state_integrity" in kinds


def test_signal_version_drift_is_caught(tmp_path):
    manifest, _ = record_fixture_session(tmp_path)

    def mutate(row):
        row["fingerprints"]["signal_version"] = "run-OTHER:cafebabe"

    _tamper_line(tmp_path / "shadow.jsonl", 2, mutate)
    ticks = load_session_ticks(tmp_path / "shadow.jsonl", DAY)
    report = replay_session(manifest=manifest, ticks=ticks, tick_runner=fake_tick_runner)
    assert report["ok"] is False
    kinds = {m["kind"] for m in report["mismatches"]}
    assert "signal_version_drift" in kinds


def test_mutated_class_b_manifest_is_caught(tmp_path):
    manifest, ticks = record_fixture_session(tmp_path)
    manifest["class_b"]["gate_inputs"]["watchlist"].append("EVIL")
    report = replay_session(manifest=manifest, ticks=ticks, tick_runner=fake_tick_runner)
    assert report["ok"] is False
    kinds = {m["kind"] for m in report["mismatches"]}
    assert "class_b_mutated" in kinds


def test_class_a_leak_at_rest_is_caught(tmp_path):
    manifest, ticks = record_fixture_session(tmp_path)
    manifest["class_a"]["as_of"] = DAY  # same-day signal must fail the audit
    report = replay_session(manifest=manifest, ticks=ticks, tick_runner=fake_tick_runner)
    assert report["ok"] is False
    kinds = {m["kind"] for m in report["mismatches"]}
    assert "class_a_leak" in kinds


def test_entry_recorded_after_cutoff_is_caught(tmp_path):
    """§11b at rest: an entry intent inside an exits_only tick is a finding
    even before re-running anything."""
    manifest, _ = record_fixture_session(tmp_path)

    def mutate(row):
        assert row["window_phase"] == "exits_only"
        row["decisions"]["intents"].append(
            {
                "symbol": "AAA",
                "side": "BUY",
                "kind": "entry",
                "parent_intent_id": "pi-AAA-BUY-late",
                "notional": 10.0,
            }
        )

    _tamper_line(tmp_path / "shadow.jsonl", 4, mutate)
    ticks = load_session_ticks(tmp_path / "shadow.jsonl", DAY)
    report = replay_session(manifest=manifest, ticks=ticks, tick_runner=fake_tick_runner)
    assert report["ok"] is False
    kinds = {m["kind"] for m in report["mismatches"]}
    assert "entry_after_cutoff" in kinds
    # The same tamper also breaks reproducibility, as it should.
    assert "decision_mismatch" in kinds


def test_tick_count_mismatch_is_caught(tmp_path):
    manifest, ticks = record_fixture_session(tmp_path)
    report = replay_session(
        manifest=manifest, ticks=ticks[:-1], tick_runner=fake_tick_runner
    )
    assert report["ok"] is False
    kinds = {m["kind"] for m in report["mismatches"]}
    assert "tick_count_mismatch" in kinds


def test_replay_cli_fails_closed_without_pipeline_binding(tmp_path):
    record_fixture_session(tmp_path)
    rc = replay_main(
        [
            "--manifest",
            str(tmp_path / "manifest.json"),
            "--shadow-log",
            str(tmp_path / "shadow.jsonl"),
        ]
    )
    assert rc == 2  # no injected runner + no manifests => refuse, never guess
