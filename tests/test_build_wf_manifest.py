"""Tests for ``build_wf_manifest`` (GBDT) — Track D4.

Pins:
- cutoff extraction from source manifest (strips T-time suffix)
- subprocess command shape (--train-cutoff, --side-label, --skip-cv etc.)
- per-cutoff artifact dir + manifest row appended on success
- failed cutoffs collected into ``failed_cutoffs`` list
- options dict reflects CLI flags
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from renquant_orchestrator import build_wf_manifest


@pytest.fixture
def fake_source_manifest(tmp_path: Path) -> Path:
    m = tmp_path / "source.json"
    m.write_text(json.dumps({"retrains": [
        {"cutoff_date": "2022-01-01T00:00:00"},
        {"cutoff_date": "2022-01-22"},
        {"cutoff_date": ""},                # blank — should be filtered
        {"no_cutoff": "x"},                  # missing — should be filtered
        {"cutoff_date": "2022-02-12T00:00:00"},
    ]}))
    return m


def test_cutoffs_from_source_strips_time_and_filters_blanks(fake_source_manifest: Path) -> None:
    cuts = build_wf_manifest.extract_cutoffs(fake_source_manifest)
    assert cuts == ["2022-01-01", "2022-01-22", "2022-02-12"]


def test_main_writes_manifest_and_subprocesses_per_cutoff(
    fake_source_manifest: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Happy path: every subprocess succeeds → 3 rows + 0 failed."""
    out_dir = tmp_path / "retrains"
    out_manifest = tmp_path / "manifest.json"

    captured: list[list[str]] = []

    class _RC:
        def __init__(self, rc: int) -> None:
            self.returncode = rc

    def fake_run(cmd: list[str], *a, **k):
        captured.append(cmd)
        # Pretend train_gbdt wrote the expected artifact
        for i, tok in enumerate(cmd):
            if tok == "--output-path":
                Path(cmd[i + 1]).parent.mkdir(parents=True, exist_ok=True)
                Path(cmd[i + 1]).write_text("{}")
                break
        return _RC(0)

    monkeypatch.setattr(build_wf_manifest.subprocess, "run", fake_run)
    rc = build_wf_manifest.main([
        "--source-manifest", str(fake_source_manifest),
        "--output-dir", str(out_dir),
        "--output-manifest", str(out_manifest),
        "--data-dir", str(tmp_path / "RenQuant" / "data"),
        "--strategy-config", str(tmp_path / "renquant-strategy-104" / "configs" / "strategy_config.json"),
        "--drop-sentiment",
    ])
    assert rc == 0
    assert out_manifest.exists()
    manifest = json.loads(out_manifest.read_text())
    assert len(manifest["retrains"]) == 3
    assert manifest["failed_cutoffs"] == []
    assert manifest["built_by"] == "renquant_orchestrator.build_wf_manifest"
    # Per-cutoff subprocess assembled the right CLI
    assert len(captured) == 3
    first = captured[0]
    assert "-m" in first and "renquant_orchestrator.train_gbdt" in first
    assert "--train-cutoff" in first
    assert "--drop-sentiment" in first
    assert "--skip-cv" in first   # default ON
    assert "--cv-embargo-days" in first
    assert "--data-dir" in first
    assert str(tmp_path / "RenQuant" / "data") in first
    assert "--strategy-config" in first


def test_main_collects_failed_cutoffs_and_returns_nonzero(
    fake_source_manifest: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _RC:
        def __init__(self, rc: int) -> None: self.returncode = rc
    # Fail the middle cutoff
    call_n = {"i": 0}
    def fake_run(cmd, *a, **k):
        call_n["i"] += 1
        return _RC(1 if call_n["i"] == 2 else 0)
    monkeypatch.setattr(build_wf_manifest.subprocess, "run", fake_run)
    rc = build_wf_manifest.main([
        "--source-manifest", str(fake_source_manifest),
        "--output-dir", str(tmp_path / "r"),
        "--output-manifest", str(tmp_path / "m.json"),
    ])
    assert rc != 0
    manifest = json.loads((tmp_path / "m.json").read_text())
    assert manifest["failed_cutoffs"] == ["2022-01-22"]
    # Successful cutoffs (rc=0) are appended regardless of whether the artifact
    # file actually exists — the script trusts the trainer's exit code.
    # Behaviour anchor: failed_cutoffs is the authoritative skip list.
    assert len(manifest["retrains"]) == 2
    cutoffs_recorded = {row["cutoff_date"] for row in manifest["retrains"]}
    assert cutoffs_recorded == {"2022-01-01", "2022-02-12"}


def test_no_skip_cv_flag_drops_skip_cv_from_subprocess(
    fake_source_manifest: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[list[str]] = []
    class _RC:
        def __init__(self, rc: int) -> None: self.returncode = rc
    def fake_run(cmd, *a, **k):
        captured.append(list(cmd))
        for i, tok in enumerate(cmd):
            if tok == "--output-path":
                Path(cmd[i + 1]).parent.mkdir(parents=True, exist_ok=True)
                Path(cmd[i + 1]).write_text("{}")
        return _RC(0)
    monkeypatch.setattr(build_wf_manifest.subprocess, "run", fake_run)
    build_wf_manifest.main([
        "--source-manifest", str(fake_source_manifest),
        "--output-dir", str(tmp_path / "r"),
        "--output-manifest", str(tmp_path / "m.json"),
        "--no-skip-cv",
    ])
    assert "--skip-cv" not in captured[0]
