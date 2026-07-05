"""Tests for the SEC EDGAR companyfacts harvester scheduler (N2/RS-3)."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from renquant_orchestrator import sec_edgar_harvester as mod


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "RenQuant"
    (repo / "data").mkdir(parents=True)
    return repo


def _write_output(path: Path, tickers: list[str]) -> None:
    lines = []
    for t in tickers:
        lines.append(json.dumps({"ticker": t, "field": "revenue", "value": 1}))
        lines.append(json.dumps({"ticker": t, "_harvest_complete": True}))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


def test_requires_exactly_one_of_tickers_or_watchlist(tmp_path) -> None:
    repo = _repo(tmp_path)
    with pytest.raises(ValueError, match="exactly one"):
        mod.harvest(repo, tmp_path / "out.jsonl")
    with pytest.raises(ValueError, match="exactly one"):
        mod.harvest(repo, tmp_path / "out.jsonl", tickers="AAPL", watchlist="wl.txt")


def test_dry_run_returns_command_without_subprocess(tmp_path) -> None:
    repo = _repo(tmp_path)
    output = tmp_path / "out.jsonl"
    result = mod.harvest(repo, output, tickers="AAPL,GRMN", dry_run=True)
    assert result["status"] == "dry_run"
    assert mod.HARVESTER_MODULE in " ".join(result["command"])
    assert str(output) in result["command"]


def test_harvest_invokes_base_data_module(monkeypatch, tmp_path) -> None:
    repo = _repo(tmp_path)
    output = tmp_path / "out.jsonl"

    def fake_run(cmd, cwd=None, env=None, capture_output=False, text=False):
        _write_output(output, ["AAPL", "GRMN"])
        return subprocess.CompletedProcess(cmd, 0, stdout="ok\n", stderr="")

    monkeypatch.setattr(mod.subprocess, "run", fake_run)

    result = mod.harvest(repo, output, tickers="AAPL,GRMN")
    assert result["n_records"] == 2
    assert result["n_tickers"] == 2
    assert "content_sha256" in result
    assert len(result["content_sha256"]) == 64

    prov_dir = repo / mod.DEFAULT_PROVENANCE_DIR
    assert prov_dir.exists()
    assert len(list(prov_dir.glob("*.json"))) == 1


def test_harvest_with_watchlist(monkeypatch, tmp_path) -> None:
    repo = _repo(tmp_path)
    output = tmp_path / "out.jsonl"
    watchlist = tmp_path / "watchlist.txt"
    watchlist.write_text("AAPL\nGRMN\n")

    captured_cmd = {}

    def fake_run(cmd, cwd=None, env=None, capture_output=False, text=False):
        captured_cmd["cmd"] = cmd
        _write_output(output, ["AAPL", "GRMN"])
        return subprocess.CompletedProcess(cmd, 0, stdout="ok\n", stderr="")

    monkeypatch.setattr(mod.subprocess, "run", fake_run)

    mod.harvest(repo, output, watchlist=str(watchlist))
    assert "--watchlist" in captured_cmd["cmd"]
    assert str(watchlist) in captured_cmd["cmd"]


def test_harvest_raises_on_nonzero_rc(monkeypatch, tmp_path) -> None:
    repo = _repo(tmp_path)
    output = tmp_path / "out.jsonl"

    def fail_run(cmd, cwd=None, env=None, capture_output=False, text=False):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="boom")

    monkeypatch.setattr(mod.subprocess, "run", fail_run)

    with pytest.raises(RuntimeError, match="SEC EDGAR harvester failed"):
        mod.harvest(repo, output, tickers="AAPL")


def test_harvest_raises_on_missing_output(monkeypatch, tmp_path) -> None:
    repo = _repo(tmp_path)
    output = tmp_path / "out.jsonl"

    def ok_run(cmd, cwd=None, env=None, capture_output=False, text=False):
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(mod.subprocess, "run", ok_run)

    with pytest.raises(RuntimeError, match="produced no output"):
        mod.harvest(repo, output, tickers="AAPL")


def test_harvest_provenance_unique_across_same_day_reruns(monkeypatch, tmp_path) -> None:
    """Two harvests on the same date must not overwrite each other's
    provenance record — codex review: per-date filenames lose the earlier
    run's hash/count/path on a same-day rerun or a second watchlist."""
    repo = _repo(tmp_path)
    output = tmp_path / "out.jsonl"

    def fake_run(cmd, cwd=None, env=None, capture_output=False, text=False):
        _write_output(output, ["AAPL", "GRMN"])
        return subprocess.CompletedProcess(cmd, 0, stdout="ok\n", stderr="")

    monkeypatch.setattr(mod.subprocess, "run", fake_run)

    first = mod.harvest(repo, output, tickers="AAPL,GRMN")
    second = mod.harvest(repo, output, tickers="AAPL,GRMN")

    assert first["provenance_file"] != second["provenance_file"]
    assert Path(first["provenance_file"]).exists()
    assert Path(second["provenance_file"]).exists()

    prov_dir = repo / mod.DEFAULT_PROVENANCE_DIR
    assert len(list(prov_dir.glob("*.json"))) == 2


def test_harvest_excludes_completion_markers_from_record_count(monkeypatch, tmp_path) -> None:
    """The _harvest_complete marker records (from the base-data harvester's
    resumability fix) must not be double-counted as fact records here."""
    repo = _repo(tmp_path)
    output = tmp_path / "out.jsonl"

    def fake_run(cmd, cwd=None, env=None, capture_output=False, text=False):
        _write_output(output, ["AAPL"])
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(mod.subprocess, "run", fake_run)

    result = mod.harvest(repo, output, tickers="AAPL")
    assert result["n_records"] == 1  # 1 fact record; marker line excluded
    assert result["n_tickers"] == 1
