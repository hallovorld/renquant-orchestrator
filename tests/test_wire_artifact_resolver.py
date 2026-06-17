"""#108 S1 — the artifact-existence checks in the manifest builders / retrain
are routed through the single ``resolve_artifact`` authority (fail-closed).

These tests pin that a *missing* produced artifact raises ``FileNotFoundError``
(listing the tried paths) instead of stamping a silent missing path into a
manifest row or trusting a bare exit code. They are self-contained (tmp_path)
and do not invoke any real trainer subprocess.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from renquant_orchestrator import build_patchtst_wf_manifest as bp
from renquant_orchestrator import build_wf_manifest as bm
from renquant_orchestrator import retrain_patchtst as rp


# ── GBDT build_wf_manifest.manifest_row ─────────────────────────────────────


def test_gbdt_manifest_row_resolves_existing_artifact(tmp_path):
    art = tmp_path / "2024-01-02" / "panel-ltr.json"
    art.parent.mkdir(parents=True)
    art.write_text("{}")
    row = bm.manifest_row(artifact_uri=art, cutoff="2024-01-02")
    # schema is unchanged (cross-repo WF-gate contract) and uri is resolved
    assert set(row) == {"artifact_uri", "cutoff_date", "lookahead_days", "trained_date"}
    assert row["artifact_uri"] == str(art.resolve())


def test_gbdt_manifest_row_missing_artifact_fails_closed(tmp_path):
    missing = tmp_path / "2024-01-02" / "panel-ltr.json"
    with pytest.raises(FileNotFoundError) as exc:
        bm.manifest_row(artifact_uri=missing, cutoff="2024-01-02")
    # the resolver lists the path it tried — not a silent missing stamp
    assert str(missing.resolve()) in str(exc.value)


def test_gbdt_retrain_loop_skips_cutoff_when_artifact_missing(tmp_path, monkeypatch):
    src = tmp_path / "source.json"
    src.write_text(json.dumps({"retrains": [
        {"cutoff_date": "2024-01-02"},
        {"cutoff_date": "2024-07-01"},
    ]}))
    ctx = bm.BuildWfManifestContext(
        source_manifest_path=src,
        output_dir=tmp_path / "out",
        output_manifest_path=tmp_path / "m.json",
        side_label="wf_test",
        cv_embargo_days=60,
        cv_n_splits=3,
        drop_sentiment=True,
        skip_cv=True,
    )
    bm.LoadCutoffsTask().run(ctx)
    bm.EnsureOutputDirTask().run(ctx)

    def fake_run(cmd, **kw):
        # subprocess exits 0 but ONLY the first cutoff actually writes its file
        out_path = Path(cmd[cmd.index("--output-path") + 1])
        if "2024-01-02" in str(out_path):
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text("{}")
        class R: returncode = 0
        return R()

    monkeypatch.setattr(subprocess, "run", fake_run)
    bm.RetrainAllCutoffsTask().run(ctx)
    # the rc=0-but-no-artifact cutoff is now failed closed, not silently stamped
    assert [r["cutoff_date"] for r in ctx.new_rows] == ["2024-01-02"]
    assert ctx.failed_cutoffs == ["2024-07-01"]


# ── PatchTST build_patchtst_wf_manifest.artifact_present ─────────────────────


def test_patchtst_artifact_present_true_for_existing(tmp_path):
    art = tmp_path / "model.pt"
    art.write_bytes(b"\x00")
    assert bp.artifact_present(art) is True


def test_patchtst_artifact_present_false_for_missing(tmp_path):
    # fail-closed: a missing artifact returns False (caller records a failure)
    assert bp.artifact_present(tmp_path / "nope.pt") is False


# ── retrain_patchtst resolver-routed existence guards ────────────────────────


def test_retrain_resolve_present_returns_resolved_path(tmp_path):
    art = tmp_path / "calib.json"
    art.write_text("{}")
    assert rp._resolve_present(art) == art.resolve()


def test_retrain_validate_scorer_missing_fails_closed(tmp_path):
    missing = tmp_path / "hf_patchtst_all_seed44_model.pt"
    with pytest.raises(FileNotFoundError, match="PatchTST training did not produce"):
        rp._validate_scorer_artifact(missing)


def test_retrain_read_json_object_missing_fails_closed(tmp_path):
    missing = tmp_path / "sidecar.json"
    with pytest.raises(FileNotFoundError, match="did not produce"):
        rp._read_json_object(missing, "PatchTST training")
