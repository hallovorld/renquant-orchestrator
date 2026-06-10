from __future__ import annotations

import json

from renquant_orchestrator.cli import main
from renquant_orchestrator.scheduled_jobs import inventory_payload, scheduled_jobs


def test_inventory_covers_main_scheduled_job_kinds() -> None:
    jobs = scheduled_jobs()
    kinds = {job.kind for job in jobs}
    assert {"training", "inference", "trading"}.issubset(kinds)
    assert {job.job_id for job in jobs} >= {
        "weekly_alpha158_fund_retrain",
        "daily_alpha158_linear_retrain",
        "daily_live_runner_bridge",
        "live_runner_bridge",
        "native_live_parity_fixture",
        "native_live_payload_parity_fixture",
        "native_live_execution_payload_fixture",
        "native_live_bundle_fixture",
        "native_live_run_candidate",
        "build_wf_manifest",
        "build_patchtst_wf_manifest",
    }
    assert all(job.command[:2] == ["renquant-orchestrator", "run-job"] for job in jobs)


def test_inventory_flags_remaining_umbrella_code_bridges() -> None:
    payload = inventory_payload()

    assert payload["summary"]["total"] == 15
    assert payload["summary"]["native_multirepo"] == 13
    assert payload["summary"]["umbrella_bridge"] == 2
    assert payload["summary"]["umbrella_bridge_jobs"] == [
        "daily_live_runner_bridge",
        "live_runner_bridge",
    ]
    assert payload["summary"]["remaining_umbrella_bridge_job_count"] == 2
    assert payload["summary"]["remaining_umbrella_bridge_jobs"] == [
        "daily_live_runner_bridge",
        "live_runner_bridge",
    ]
    assert payload["summary"]["native_offboard_blocker_count"] == 6
    assert payload["summary"]["native_exit_criteria_count"] == 8
    assert payload["summary"]["production_safe_umbrella_bridge_jobs"] == [
        "daily_live_runner_bridge",
        "live_runner_bridge",
    ]
    assert payload["summary"]["native_cutover_candidate_count"] == 2
    assert sorted(payload["summary"]["native_cutover_candidates"]) == [
        "daily_live_runner_bridge",
        "live_runner_bridge",
    ]
    bridge_jobs = [
        job for job in payload["jobs"]
        if job["migration_state"] == "umbrella_bridge"
    ]
    assert all(job["uses_umbrella_code"] for job in bridge_jobs)
    assert all(job["umbrella_code_dependency"] for job in bridge_jobs)
    assert all(job["native_offboard_blockers"] for job in bridge_jobs)
    assert all(job["native_exit_criteria"] for job in bridge_jobs)
    assert {
        "daily_live_runner_bridge",
        "live_runner_bridge",
    } == {job["job_id"] for job in bridge_jobs}
    assert any(
        "native_live_parity_fixture passes" in criterion
        for job in bridge_jobs
        for criterion in job["native_exit_criteria"]
    )


def test_inventory_summarizes_remaining_umbrella_state_dependencies() -> None:
    payload = inventory_payload()

    assert payload["summary"]["umbrella_state_dependency_job_count"] == 13
    assert payload["summary"]["umbrella_state_dependency_jobs"] == [
        "weekly_alpha158_fund_retrain",
        "daily_alpha158_linear_retrain",
        "native_live_parity_fixture",
        "native_live_bundle_fixture",
        "native_live_payload_parity_fixture",
        "native_live_execution_payload_fixture",
        "native_live_run_candidate",
        "daily_live_runner_bridge",
        "live_runner_bridge",
        "weekly_apy_monitor",
        "state_backup",
        "build_wf_manifest",
        "build_patchtst_wf_manifest",
    ]


def test_native_scheduled_jobs_have_no_umbrella_code_dependency() -> None:
    payload = inventory_payload()

    native_jobs = [
        job for job in payload["jobs"]
        if job["migration_state"] == "native_multirepo"
    ]

    assert native_jobs
    assert all(not job["uses_umbrella_code"] for job in native_jobs)
    assert all(job["umbrella_code_dependency"] is None for job in native_jobs)
    assert all(job["native_offboard_blockers"] == [] for job in native_jobs)


def test_live_bridge_jobs_expose_readonly_bundle_capture_rehearsal() -> None:
    payload = inventory_payload()
    bridge_jobs = [
        job for job in payload["jobs"]
        if job["job_id"] in {"daily_live_runner_bridge", "live_runner_bridge"}
    ]

    assert len(bridge_jobs) == 2
    for job in bridge_jobs:
        command = job["rehearsal_command"]
        assert command[:2] == ["renquant-orchestrator", "run-job"]
        assert job["job_id"] in command
        assert "--broker" in command
        assert "readonly-alpaca" in command
        assert "--bridge-bundle-output" in command


def test_live_bridge_jobs_expose_native_cutover_candidate_commands() -> None:
    payload = inventory_payload()
    jobs = {
        job["job_id"]: job
        for job in payload["jobs"]
        if job["job_id"] in {"daily_live_runner_bridge", "live_runner_bridge"}
    }

    assert set(jobs) == {"daily_live_runner_bridge", "live_runner_bridge"}
    for job in jobs.values():
        command = job["native_cutover_command"]
        assert job["native_replacement_job_id"] == "native_live_run_candidate"
        assert command[:3] == [
            "renquant-orchestrator",
            "run-job",
            "native_live_run_candidate",
        ]
        assert "--inference-json" in command
        assert "--execution-output-json" in command
        assert "--commit-plan-output-json" in command
        assert "--output-json" in command
        assert "--broker-name" in command
        assert "readonly-alpaca" in command

    daily_command = jobs["daily_live_runner_bridge"]["native_cutover_command"]
    live_command = jobs["live_runner_bridge"]["native_cutover_command"]
    assert "/tmp/renquant-live-rehearsal/daily-native-inference.json" in daily_command
    assert "/tmp/renquant-live-rehearsal/live-native-inference.json" in live_command


def test_scheduled_jobs_cli_emits_json(capsys) -> None:
    rc = main(["scheduled-jobs"])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == 1
    assert payload["summary"]["total"] == len(payload["jobs"])


def test_run_job_dispatches_by_inventory_id(monkeypatch) -> None:
    import renquant_orchestrator.job_runner as runner

    seen = {}

    def fake_run_module_main(module_name, argv):
        seen["module_name"] = module_name
        seen["argv"] = argv
        return 19

    monkeypatch.setattr(runner, "_run_module_main", fake_run_module_main)

    rc = main([
        "run-job",
        "weekly_alpha158_fund_retrain",
        "--",
        "--staged",
        "--repo-dir",
        "/tmp/repo",
    ])

    assert rc == 19
    assert seen == {
        "module_name": "renquant_orchestrator.retrain_alpha158_fund",
        "argv": ["--staged", "--repo-dir", "/tmp/repo"],
    }


def test_run_job_dispatches_native_live_parity_fixture(monkeypatch) -> None:
    import renquant_orchestrator.job_runner as runner

    seen = {}

    def fake_run_module_main(module_name, argv):
        seen["module_name"] = module_name
        seen["argv"] = argv
        return 0

    monkeypatch.setattr(runner, "_run_module_main", fake_run_module_main)

    rc = main([
        "run-job",
        "native_live_parity_fixture",
        "--",
        "--bridge-bundle",
        "/tmp/bridge.json",
        "--native-bundle",
        "/tmp/native.json",
        "--fail-on-diff",
    ])

    assert rc == 0
    assert seen == {
        "module_name": "renquant_orchestrator.live_parity",
        "argv": [
            "--bridge-bundle",
            "/tmp/bridge.json",
            "--native-bundle",
            "/tmp/native.json",
            "--fail-on-diff",
        ],
    }


def test_run_job_dispatches_native_live_bundle_fixture(monkeypatch) -> None:
    import renquant_orchestrator.job_runner as runner

    seen = {}

    def fake_run_module_main(module_name, argv):
        seen["module_name"] = module_name
        seen["argv"] = argv
        return 0

    monkeypatch.setattr(runner, "_run_module_main", fake_run_module_main)

    rc = main([
        "run-job",
        "native_live_bundle_fixture",
        "--",
        "--inference-json",
        "/tmp/inference.json",
        "--output-json",
        "/tmp/native.json",
    ])

    assert rc == 0
    assert seen == {
        "module_name": "renquant_orchestrator.native_live_bundle",
        "argv": [
            "--inference-json",
            "/tmp/inference.json",
            "--output-json",
            "/tmp/native.json",
        ],
    }


def test_run_job_dispatches_native_live_payload_parity_fixture(monkeypatch) -> None:
    import renquant_orchestrator.job_runner as runner

    seen = {}

    def fake_run_module_main(module_name, argv):
        seen["module_name"] = module_name
        seen["argv"] = argv
        return 0

    monkeypatch.setattr(runner, "_run_module_main", fake_run_module_main)

    rc = main([
        "run-job",
        "native_live_payload_parity_fixture",
        "--",
        "--bridge-bundle",
        "/tmp/bridge.json",
        "--inference-json",
        "/tmp/inference.json",
        "--native-bundle-output",
        "/tmp/native.json",
        "--fail-on-diff",
    ])

    assert rc == 0
    assert seen == {
        "module_name": "renquant_orchestrator.live_parity_payloads",
        "argv": [
            "--bridge-bundle",
            "/tmp/bridge.json",
            "--inference-json",
            "/tmp/inference.json",
            "--native-bundle-output",
            "/tmp/native.json",
            "--fail-on-diff",
        ],
    }


def test_run_job_dispatches_native_live_execution_payload_fixture(monkeypatch) -> None:
    import renquant_orchestrator.job_runner as runner

    seen = {}

    def fake_run_module_main(module_name, argv):
        seen["module_name"] = module_name
        seen["argv"] = argv
        return 0

    monkeypatch.setattr(runner, "_run_module_main", fake_run_module_main)

    rc = main([
        "run-job",
        "native_live_execution_payload_fixture",
        "--",
        "--inference-json",
        "/tmp/inference.json",
        "--output-json",
        "/tmp/execution.json",
    ])

    assert rc == 0
    assert seen == {
        "module_name": "renquant_orchestrator.native_execution_payload",
        "argv": [
            "--inference-json",
            "/tmp/inference.json",
            "--output-json",
            "/tmp/execution.json",
        ],
    }


def test_run_job_dispatches_native_live_run_candidate(monkeypatch) -> None:
    import renquant_orchestrator.job_runner as runner

    seen = {}

    def fake_run_module_main(module_name, argv):
        seen["module_name"] = module_name
        seen["argv"] = argv
        return 0

    monkeypatch.setattr(runner, "_run_module_main", fake_run_module_main)

    rc = main([
        "run-job",
        "native_live_run_candidate",
        "--",
        "--inference-json",
        "/tmp/inference.json",
        "--output-json",
        "/tmp/native.json",
        "--broker-name",
        "readonly-alpaca",
    ])

    assert rc == 0
    assert seen == {
        "module_name": "renquant_orchestrator.native_live_run",
        "argv": [
            "--inference-json",
            "/tmp/inference.json",
            "--output-json",
            "/tmp/native.json",
            "--broker-name",
            "readonly-alpaca",
        ],
    }


def test_scheduled_jobs_cli_can_fail_on_umbrella_bridge(capsys) -> None:
    rc = main(["scheduled-jobs", "--fail-on-umbrella-bridge"])

    assert rc == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["umbrella_bridge_jobs"] == [
        "daily_live_runner_bridge",
        "live_runner_bridge",
    ]
    assert all(
        job["native_exit_criteria"]
        for job in payload["jobs"]
        if job["migration_state"] == "umbrella_bridge"
    )
