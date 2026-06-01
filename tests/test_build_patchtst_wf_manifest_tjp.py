"""R2 — T/J/P shape regression tests for ``build_patchtst_wf_manifest``."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from renquant_orchestrator import build_patchtst_wf_manifest as bp  # noqa: E402


def _write_model_sidecar(path: Path, *, effective_cutoff: str = "2024-01-01") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x00")
    path.with_name(path.name + ".metadata.json").write_text(json.dumps({
        "training_contract": {
            "trained_date": "2026-06-01",
            "effective_train_cutoff_date": effective_cutoff,
            "lookahead_days": 60,
        }
    }))


@pytest.fixture
def src_manifest(tmp_path):
    p = tmp_path / "source.json"
    p.write_text(json.dumps({
        "retrains": [
            {"cutoff_date": "2022-01-01"},
            {"cutoff_date": "2024-07-01"},
            {"cutoff_date": "2026-03-02"},
        ],
    }))
    return p


@pytest.fixture
def ctx(tmp_path, src_manifest):
    return bp.BuildPatchtstWfManifestContext(
        source_manifest_path=src_manifest,
        output_dir=tmp_path / "out",
        output_manifest_path=tmp_path / "manifest.json",
        cadence_days=180,
        epochs=4,
        device="cpu",
        seed=42,
        cross_stock_attn=True,
        film_regime_cond=False,
        exclude_features="mean_sentiment",
        strategy_config=None,
    )


def test_pipeline_has_three_ordered_jobs():
    p = bp.build_pipeline()
    assert p.name == "BuildPatchtstWfManifest"
    assert [type(j).__name__ for j in p.jobs] == ["PrepareJob", "RetrainJob", "EmitJob"]


def test_prepare_job_tasks_include_cwd_resolver():
    assert [type(t).__name__ for t in bp.PrepareJob().tasks] == [
        "LoadCutoffsTask", "ResolveDataRootTask", "EnsureOutputDirTask",
    ]


def test_retrain_and_emit_jobs():
    assert [type(t).__name__ for t in bp.RetrainJob().tasks] == ["RetrainAllCutoffsTask"]
    assert [type(t).__name__ for t in bp.EmitJob().tasks] == [
        "AssembleManifestPayloadTask", "WriteManifestTask",
    ]


def test_load_cutoffs_task_subsamples_by_cadence(ctx):
    bp.LoadCutoffsTask().run(ctx)
    # 180-day cadence + 3 cutoffs from 2022-01-01 to 2026-03-02 → all kept
    assert len(ctx.cutoffs) == 3
    assert ctx.cutoffs[0] == "2022-01-01"
    assert ctx.cutoffs[-1] == "2026-03-02"


def test_resolve_data_root_task_populates_explicit_trainer_inputs(ctx, monkeypatch, tmp_path):
    data_root = tmp_path / "RenQuant"
    monkeypatch.setenv("RENQUANT_DATA_ROOT", str(data_root))

    bp.ResolveDataRootTask().run(ctx)

    assert ctx.cwd == str(data_root.resolve())
    assert ctx.dataset_path == str(data_root.resolve() / bp.DEFAULT_DATASET_REL)
    assert ctx.spy_path == str(data_root.resolve() / bp.DEFAULT_SPY_REL)
    assert ctx.raw_label_panel_path == str(data_root.resolve() / bp.DEFAULT_RAW_LABEL_PANEL_REL)


def test_retrain_all_cutoffs_calls_hf_trainer_with_cwd(ctx, monkeypatch):
    bp.LoadCutoffsTask().run(ctx)
    ctx.cwd = "/fake/umbrella"
    bp.EnsureOutputDirTask().run(ctx)
    calls = []

    def fake_run(cmd, **kw):
        calls.append((cmd, kw.get("cwd")))
        if "renquant_model_patchtst.fit_calibrator" in cmd:
            Path(cmd[cmd.index("--out") + 1]).write_text("{}")
            class R: returncode = 0
            return R()
        # Pretend the artifact file gets written
        out_dir = Path(cmd[cmd.index("--output-dir") + 1])
        _write_model_sidecar(
            out_dir / f"hf_patchtst_all_seed{ctx.seed}_model.pt",
            effective_cutoff=cmd[cmd.index("--train-cutoff") + 1],
        )
        class R: returncode = 0
        return R()

    monkeypatch.setattr(subprocess, "run", fake_run)
    bp.RetrainAllCutoffsTask().run(ctx)
    train_calls = [(cmd, cwd) for cmd, cwd in calls if "renquant_model_patchtst.hf_trainer" in cmd]
    cal_calls = [(cmd, cwd) for cmd, cwd in calls if "renquant_model_patchtst.fit_calibrator" in cmd]
    assert len(train_calls) == 3
    assert len(cal_calls) == 3
    for cmd, cwd in train_calls:
        assert "renquant_model_patchtst.hf_trainer" in cmd
        assert cwd == "/fake/umbrella"
        # tuned baseline applied
        assert "--lr" in cmd and "1e-4" in cmd
    for cmd, cwd in cal_calls:
        assert cwd == "/fake/umbrella"
        assert "--scorer-artifact" in cmd
        assert "--data-end" in cmd


def test_retrain_records_missing_artifact_as_failure(ctx, monkeypatch):
    bp.LoadCutoffsTask().run(ctx)
    ctx.cwd = None
    bp.EnsureOutputDirTask().run(ctx)

    def fake_run(cmd, **kw):
        # subprocess succeeds but artifact NOT written → counted as failure
        class R: returncode = 0
        return R()

    monkeypatch.setattr(subprocess, "run", fake_run)
    bp.RetrainAllCutoffsTask().run(ctx)
    assert len(ctx.new_rows) == 0
    assert len(ctx.failed_cutoffs) == 3


def test_assemble_payload_records_options(ctx):
    bp.LoadCutoffsTask().run(ctx)
    ctx.new_rows = [{"artifact_uri": "/x.pt", "cutoff_date": "2022-01-01",
                     "lookahead_days": 60, "trained_date": "2026-05-30"}]
    bp.AssembleManifestPayloadTask().run(ctx)
    assert ctx.payload["built_by"] == "renquant_orchestrator.build_patchtst_wf_manifest"
    assert ctx.payload["trainer"] == "renquant_model_patchtst.hf_trainer"
    assert ctx.payload["options"]["cross_stock_attn"] is True
    assert ctx.payload["options"]["exclude_features"] == "mean_sentiment"


def test_full_pipeline_end_to_end(ctx, monkeypatch):
    def fake_run(cmd, **kw):
        if "renquant_model_patchtst.fit_calibrator" in cmd:
            Path(cmd[cmd.index("--out") + 1]).write_text("{}")
            class R: returncode = 0
            return R()
        out_dir = Path(cmd[cmd.index("--output-dir") + 1])
        _write_model_sidecar(
            out_dir / f"hf_patchtst_all_seed{ctx.seed}_model.pt",
            effective_cutoff=cmd[cmd.index("--train-cutoff") + 1],
        )
        class R: returncode = 0
        return R()

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = bp.build_pipeline().run(ctx)
    assert result.ok is True
    assert [s.job_name for s in result.steps] == ["PrepareJob", "RetrainJob", "EmitJob"]
    out = json.loads(ctx.output_manifest_path.read_text())
    assert len(out["retrains"]) == 3
    assert all(row.get("calibrator_uri") for row in out["retrains"])
