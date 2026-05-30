"""Tests for ``build_patchtst_wf_manifest`` — Track D4.

Pins:
- cadence subsampling picks the right cutoffs
- DOE-tuned defaults pass through (lr / wd / seq-len / patience)
- --cross-stock-attn and --film-regime-cond + --exclude-features pass through
- subprocess success → manifest row; failure → failed_cutoffs entry
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from renquant_orchestrator import build_patchtst_wf_manifest as bp


@pytest.fixture
def source_manifest(tmp_path: Path) -> Path:
    m = tmp_path / "source.json"
    # 21-day-cadence cutoffs over ~4 years
    cuts = [
        "2022-01-01", "2022-01-22", "2022-02-12", "2022-03-05", "2022-03-26",
        "2022-04-16", "2022-05-07", "2022-05-28", "2022-06-18", "2022-07-09",
        "2023-01-14", "2023-07-22", "2024-01-22", "2024-07-29", "2025-02-03",
        "2025-08-11", "2026-02-16", "2026-03-09",
    ]
    m.write_text(json.dumps({"retrains": [{"cutoff_date": c} for c in cuts]}))
    return m


def test_cadence_subsampling_picks_semi_annual_subset(source_manifest: Path) -> None:
    out = bp.extract_cutoffs(source_manifest, cadence_days=180)
    # 21-day-cadence cuts over 4 years → semi-annual (~180d) keeps ~8-10 entries
    assert len(out) >= 6 and len(out) <= 12
    assert out[0] == "2022-01-01"
    assert out[-1] == "2026-03-09"  # last cutoff always preserved


def test_cadence_None_keeps_all(source_manifest: Path) -> None:
    cuts = bp.extract_cutoffs(source_manifest, cadence_days=None)
    assert len(cuts) == 18  # all of them


def test_main_assembles_doe_tuned_cli(
    source_manifest: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out_dir = tmp_path / "retrains"
    out_manifest = tmp_path / "manifest.json"
    captured: list[list[str]] = []

    class _RC:
        def __init__(self, rc: int) -> None: self.returncode = rc

    def fake_run(cmd, *a, **k):
        captured.append(list(cmd))
        # Pretend hf_trainer wrote the expected artifact
        for i, tok in enumerate(cmd):
            if tok == "--output-dir":
                d = Path(cmd[i + 1])
                d.mkdir(parents=True, exist_ok=True)
                # Default seed is 42
                (d / "hf_patchtst_all_seed42_model.pt").write_bytes(b"\x00")
                break
        return _RC(0)

    monkeypatch.setattr(bp.subprocess, "run", fake_run)
    rc = bp.main([
        "--source-manifest", str(source_manifest),
        "--output-dir", str(out_dir),
        "--output-manifest", str(out_manifest),
        "--cadence-days", "180",
        "--epochs", "4", "--device", "cpu",
        "--cross-stock-attn",
        "--exclude-features", "mean_sentiment,n_articles_log",
    ])
    assert rc == 0
    cmd = captured[0]
    # DOE-tuned baseline
    assert "--lr" in cmd and "1e-4" in cmd
    assert "--weight-decay" in cmd and "0.3" in cmd
    assert "--seq-len" in cmd and "24" in cmd
    assert "--early-stopping-patience" in cmd and "2" in cmd
    # Pass-through flags
    assert "--cross-stock-attn" in cmd
    assert "--exclude-features" in cmd
    assert "mean_sentiment,n_articles_log" in cmd
    assert "--epochs" in cmd and "4" in cmd
    assert "--device" in cmd and "cpu" in cmd
    assert "--save-model" in cmd  # always on (manifest needs artifacts)


def test_main_records_failed_cutoffs(
    source_manifest: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _RC:
        def __init__(self, rc: int) -> None: self.returncode = rc

    def always_fail(*a, **k):
        return _RC(1)

    monkeypatch.setattr(bp.subprocess, "run", always_fail)
    out_manifest = tmp_path / "manifest.json"
    rc = bp.main([
        "--source-manifest", str(source_manifest),
        "--output-dir", str(tmp_path / "r"),
        "--output-manifest", str(out_manifest),
        "--cadence-days", "180",
    ])
    assert rc != 0
    manifest = json.loads(out_manifest.read_text())
    assert len(manifest["failed_cutoffs"]) >= 6
    assert len(manifest["retrains"]) == 0
    assert manifest["options"]["cadence_days"] == 180


def test_main_film_regime_cond_flag_passes_through(
    source_manifest: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[list[str]] = []
    class _RC:
        def __init__(self, rc: int) -> None: self.returncode = rc
    def fake_run(cmd, *a, **k):
        captured.append(list(cmd))
        for i, tok in enumerate(cmd):
            if tok == "--output-dir":
                d = Path(cmd[i + 1]); d.mkdir(parents=True, exist_ok=True)
                (d / "hf_patchtst_all_seed42_model.pt").write_bytes(b"\x00")
        return _RC(0)
    monkeypatch.setattr(bp.subprocess, "run", fake_run)
    bp.main([
        "--source-manifest", str(source_manifest),
        "--output-dir", str(tmp_path / "r"),
        "--output-manifest", str(tmp_path / "m.json"),
        "--cadence-days", "180",
        "--film-regime-cond",
    ])
    assert "--film-regime-cond" in captured[0]
