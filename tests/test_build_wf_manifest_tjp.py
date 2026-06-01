"""R1 — T/J/P shape regression tests for ``build_wf_manifest`` (GBDT).

Pins the Task/Job/Pipeline architecture per §1c. Each Task is single-
responsibility and exercised through the Pipeline runner with a fake
subprocess so we never invoke the real train_gbdt.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from renquant_orchestrator import build_wf_manifest as bm  # noqa: E402


@pytest.fixture
def src_manifest(tmp_path):
    """Three-cutoff fake source manifest."""
    p = tmp_path / "source.json"
    p.write_text(json.dumps({
        "retrains": [
            {"cutoff_date": "2024-01-02"},
            {"cutoff_date": "2024-07-01"},
            {"cutoff_date": "2025-04-01"},
        ],
    }))
    return p


@pytest.fixture
def ctx(tmp_path, src_manifest):
    return bm.BuildWfManifestContext(
        source_manifest_path=src_manifest,
        output_dir=tmp_path / "out",
        output_manifest_path=tmp_path / "manifest.json",
        side_label="wf_test",
        cv_embargo_days=60,
        cv_n_splits=3,
        drop_sentiment=True,
        skip_cv=True,
    )


def test_pipeline_has_three_ordered_jobs():
    p = bm.build_pipeline()
    assert p.name == "BuildWfManifest"
    assert [type(j).__name__ for j in p.jobs] == ["PrepareJob", "RetrainJob", "EmitJob"]


def test_prepare_job_tasks():
    assert [type(t).__name__ for t in bm.PrepareJob().tasks] == [
        "LoadCutoffsTask", "ResolveTrainingInputsTask", "EnsureOutputDirTask",
    ]


def test_retrain_job_tasks():
    assert [type(t).__name__ for t in bm.RetrainJob().tasks] == ["RetrainAllCutoffsTask"]


def test_emit_job_tasks():
    assert [type(t).__name__ for t in bm.EmitJob().tasks] == [
        "AssembleManifestPayloadTask", "WriteManifestTask",
    ]


def test_load_cutoffs_task_populates_ctx(ctx):
    bm.LoadCutoffsTask().run(ctx)
    assert ctx.cutoffs == ["2024-01-02", "2024-07-01", "2025-04-01"]


def test_ensure_output_dir_task_creates_dir(ctx):
    assert not ctx.output_dir.exists()
    bm.EnsureOutputDirTask().run(ctx)
    assert ctx.output_dir.is_dir()


def test_resolve_training_inputs_task_sets_explicit_defaults(ctx, monkeypatch, tmp_path):
    data_dir = tmp_path / "RenQuant" / "data"
    strategy = tmp_path / "renquant-strategy-104" / "configs" / "strategy_config.json"
    strategy.parent.mkdir(parents=True)
    strategy.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(bm, "DEFAULT_DATA_DIR", data_dir)
    monkeypatch.setattr(bm, "DEFAULT_STRATEGY_CONFIG", strategy)

    bm.ResolveTrainingInputsTask().run(ctx)

    assert ctx.data_dir == data_dir
    assert ctx.strategy_config == str(strategy.resolve())


def test_assemble_payload_task_builds_v2_schema(ctx):
    ctx.new_rows = [{"artifact_uri": "/x", "cutoff_date": "2024-01-02",
                     "lookahead_days": 60, "trained_date": "2026-05-30"}]
    bm.AssembleManifestPayloadTask().run(ctx)
    assert ctx.payload["schema_version"] == 2
    assert ctx.payload["built_by"] == "renquant_orchestrator.build_wf_manifest"
    assert ctx.payload["trainer"] == "renquant_orchestrator.train_gbdt"
    assert ctx.payload["options"]["drop_sentiment"] is True
    assert ctx.payload["options"]["skip_cv"] is True
    assert "data_dir" in ctx.payload["options"]
    assert "strategy_config" in ctx.payload["options"]


def test_write_manifest_task_writes_file(ctx):
    ctx.payload = {"retrains": [], "schema_version": 2}
    bm.WriteManifestTask().run(ctx)
    assert ctx.output_manifest_path.exists()
    assert json.loads(ctx.output_manifest_path.read_text())["schema_version"] == 2


def test_retrain_all_cutoffs_uses_subprocess_run(ctx, monkeypatch):
    """RetrainAllCutoffsTask must subprocess.run for every cutoff and record results."""
    bm.LoadCutoffsTask().run(ctx)
    ctx.data_dir = Path("/data/root")
    ctx.strategy_config = "/cfg/strategy_config.json"
    bm.EnsureOutputDirTask().run(ctx)
    calls = []

    class FakeCompleted:
        returncode = 0

    def fake_run(cmd, **kw):
        calls.append((cmd, kw.get("env")))
        return FakeCompleted()

    monkeypatch.setattr(subprocess, "run", fake_run)
    bm.RetrainAllCutoffsTask().run(ctx)
    # one subprocess invocation per cutoff
    assert len(calls) == 3
    # all rc=0 → 3 new_rows, 0 failed
    assert len(ctx.new_rows) == 3
    assert ctx.failed_cutoffs == []
    # commands look like train_gbdt CLI invocations
    for c, env in calls:
        assert "renquant_orchestrator.train_gbdt" in c
        assert "--train-cutoff" in c
        assert "--data-dir" in c and "/data/root" in c
        assert "--strategy-config" in c and "/cfg/strategy_config.json" in c
        assert env["RENQUANT_DATA_ROOT"] == "/data/root"
        assert env["RENQUANT_STRATEGY_CONFIG"] == "/cfg/strategy_config.json"


def test_retrain_all_cutoffs_records_failures(ctx, monkeypatch):
    bm.LoadCutoffsTask().run(ctx)
    bm.EnsureOutputDirTask().run(ctx)

    def fake_run(cmd, **kw):
        class R: pass
        r = R()
        r.returncode = 1 if "2024-07-01" in cmd else 0
        return r

    monkeypatch.setattr(subprocess, "run", fake_run)
    bm.RetrainAllCutoffsTask().run(ctx)
    assert ctx.failed_cutoffs == ["2024-07-01"]
    assert len(ctx.new_rows) == 2


def test_full_pipeline_end_to_end(ctx, monkeypatch):
    """Pipeline.run() drives all 3 Jobs in order; output manifest is the result."""

    def fake_run(cmd, **kw):
        class R: returncode = 0
        return R()

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = bm.build_pipeline().run(ctx)
    assert result.ok is True
    assert [s.job_name for s in result.steps] == ["PrepareJob", "RetrainJob", "EmitJob"]
    # Final manifest written + populated
    out = json.loads(ctx.output_manifest_path.read_text())
    assert out["schema_version"] == 2
    assert len(out["retrains"]) == 3
    assert out["failed_cutoffs"] == []
