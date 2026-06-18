from __future__ import annotations

import json
from pathlib import Path

from renquant_orchestrator.cli import main
from renquant_orchestrator.wf_promote_triage import classify_log_text, triage_log_dir


def test_classify_manifest_and_config_failures() -> None:
    result = classify_log_text(
        "\n".join([
            "WF config parity failed: candidate config differs from prod",
            "manifest recipe mismatch: expected patchtst_wf",
            "VERDICT: FAIL",
        ]),
        name="2026-06-08-weekly.log",
    )

    assert result["date"] == "2026-06-08"
    assert result["verdict"] == "fail"
    assert result["failure_modes"] == [
        "manifest_recipe_mismatch",
        "config_parity_failed",
    ]
    assert result["evidence"][0]["line"] == 2


def test_classify_sim_zero_trade_and_benchmark_failures() -> None:
    result = classify_log_text(
        "\n".join([
            "sim cuts failed execution for 2026-06-01..2026-06-05",
            "PanelScorer.load: artifact not found: artifacts/sim/artifacts/walkforward_v2_20260602/2024-01-01/panel-ltr.json",
            "Trade contract result: missing round-trip ledger(s): cut.round_trips.csv",
            "zero trades across all WF cuts",
            "gate details absolute_ok=False benchmark_ok=False regime_ok=False",
            "Sanity result: FAIL: placebo_ic=+0.0365 (must be available and < threshold)",
            "WF result: FAIL",
        ]),
        name="2026-06-15-weekly.log",
    )

    assert result["verdict"] == "fail"
    assert result["failure_modes"] == [
        "sim_cuts_failed",
        "wf_artifact_path_missing",
        "trade_ledgers_missing",
        "zero_trades",
        "benchmark_regime_failed",
        "sanity_placebo_failed",
    ]


def test_pass_and_unknown_failure_are_explicit() -> None:
    passed = classify_log_text("WF result: PASS\n", name="2026-06-09.log")
    failed = classify_log_text("script FAILED before emitting gate details", name="2026-06-10.log")

    assert passed["verdict"] == "pass"
    assert passed["failure_modes"] == []
    assert failed["verdict"] == "fail"
    assert failed["failure_modes"] == ["unknown_failure"]


def test_triage_log_dir_summarizes_and_filters_since(tmp_path: Path) -> None:
    (tmp_path / "2026-06-01-weekly.log").write_text("VERDICT: PASS\n", encoding="utf-8")
    (tmp_path / "2026-06-08-weekly.log").write_text(
        "manifest artifacts do not match candidate recipe\nVERDICT: FAIL\n",
        encoding="utf-8",
    )
    (tmp_path / "2026-06-15-weekly.log").write_text(
        "zero trades across all WF cuts\nWF result: FAIL\n",
        encoding="utf-8",
    )
    (tmp_path / "stdout.log").write_text("not a weekly gate log\n", encoding="utf-8")

    payload = triage_log_dir(tmp_path, since="2026-06-08")

    assert payload["summary"] == {
        "total_files": 2,
        "skipped_files": 2,
        "failed_files": 2,
        "unknown_files": 0,
        "passed_files": 0,
        "by_mode": {
            "manifest_recipe_mismatch": 1,
            "zero_trades": 1,
        },
        "ok": False,
    }
    assert payload["skipped_files"] == [
        {"file": "2026-06-01-weekly.log", "reason": "before_since"},
        {"file": "stdout.log", "reason": "no_filename_date"},
    ]


def test_cli_wf_promote_triage_outputs_json_and_strict_status(tmp_path: Path, capsys) -> None:
    (tmp_path / "2026-06-15-weekly.log").write_text(
        "zero trades across all WF cuts\nVERDICT: FAIL\n",
        encoding="utf-8",
    )

    rc = main([
        "wf-promote-triage",
        "--log-dir",
        str(tmp_path),
        "--strict",
    ])

    payload = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert payload["summary"]["by_mode"] == {"zero_trades": 1}
