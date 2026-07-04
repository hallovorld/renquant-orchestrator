"""Tests for the 106 signal pipeline configuration module."""
from __future__ import annotations

import json

import pytest

from renquant_orchestrator.signal_pipeline_config import (
    PipelineConfig,
    SignalSource,
    default_config,
    load_config,
    main,
    pipeline_summary,
    save_config,
    source_readiness,
)


def test_default_config_has_production_sources_enabled() -> None:
    config = default_config()
    by_name = config.by_name()
    assert by_name["alpha158_fundamental"].enabled is True
    assert by_name["patchtst_panel_scores"].enabled is True


def test_default_config_has_future_sources_disabled() -> None:
    config = default_config()
    by_name = config.by_name()
    assert by_name["pit_estimate_revisions"].enabled is False
    assert by_name["fmp_analyst_estimates"].enabled is False
    assert by_name["regime_conditioned_momentum"].enabled is False


def test_future_sources_have_prereg_gates() -> None:
    config = default_config()
    for src in config.disabled_sources():
        assert src.prereg_gate, f"{src.name} must have a prereg gate"


def test_future_sources_have_min_history_days() -> None:
    config = default_config()
    for src in config.disabled_sources():
        assert src.min_history_days > 0, f"{src.name} must require min history"


def test_enabled_disabled_partitions() -> None:
    config = default_config()
    assert len(config.enabled_sources()) == 2
    assert len(config.disabled_sources()) == 3
    assert len(config.sources) == 5


def test_source_readiness_no_data(tmp_path) -> None:
    config = default_config()
    results = source_readiness(config, tmp_path)
    pit = next(r for r in results if r["name"] == "pit_estimate_revisions")
    assert pit["ready"] is False
    assert pit["days_available"] is None


def test_source_readiness_parquet_file_exists(tmp_path) -> None:
    config = PipelineConfig(sources=[
        SignalSource(
            name="test_panel",
            kind="feature_panel",
            enabled=True,
            data_subpath="data/test.parquet",
        ),
    ])
    (tmp_path / "data").mkdir()
    (tmp_path / "data/test.parquet").write_bytes(b"PAR1mock")
    results = source_readiness(config, tmp_path)
    assert results[0]["ready"] is True


def test_source_readiness_directory_with_dated_snapshots(tmp_path) -> None:
    config = PipelineConfig(sources=[
        SignalSource(
            name="pit_test",
            kind="point_in_time",
            enabled=False,
            min_history_days=5,
            data_subpath="data/pit",
        ),
    ])
    pit_dir = tmp_path / "data/pit"
    pit_dir.mkdir(parents=True)
    for d in range(1, 8):
        (pit_dir / f"2026-07-{d:02d}.parquet").touch()

    results = source_readiness(config, tmp_path)
    assert results[0]["days_available"] == 7
    assert results[0]["ready"] is True
    assert results[0]["gap"] == 0


def test_source_readiness_insufficient_history(tmp_path) -> None:
    config = PipelineConfig(sources=[
        SignalSource(
            name="pit_test",
            kind="point_in_time",
            enabled=False,
            min_history_days=120,
            data_subpath="data/pit",
        ),
    ])
    pit_dir = tmp_path / "data/pit"
    pit_dir.mkdir(parents=True)
    for d in range(1, 11):
        (pit_dir / f"2026-07-{d:02d}.parquet").touch()

    results = source_readiness(config, tmp_path)
    assert results[0]["days_available"] == 10
    assert results[0]["ready"] is False
    assert results[0]["gap"] == 110


def test_save_load_roundtrip(tmp_path) -> None:
    config = default_config()
    path = tmp_path / "pipeline.json"
    save_config(config, path)
    loaded = load_config(path)
    assert len(loaded.sources) == len(config.sources)
    for orig, loaded_src in zip(config.sources, loaded.sources):
        assert orig.name == loaded_src.name
        assert orig.enabled == loaded_src.enabled
        assert orig.min_history_days == loaded_src.min_history_days


def test_save_refuses_prod_paths() -> None:
    from pathlib import Path
    config = default_config()
    with pytest.raises(ValueError, match="refusing to write"):
        save_config(config, Path.home() / "git/github/RenQuant/data/pipeline.json")


def test_pipeline_summary_basic() -> None:
    config = default_config()
    summary = pipeline_summary(config)
    assert summary["total_sources"] == 5
    assert summary["enabled"] == 2
    assert summary["disabled"] == 3
    assert "alpha158_fundamental" in summary["enabled_names"]
    assert "pit_estimate_revisions" in summary["disabled_names"]


def test_pipeline_summary_with_data_root(tmp_path) -> None:
    config = default_config()
    summary = pipeline_summary(config, data_root=tmp_path)
    assert "not_ready" in summary


def test_cli_default_json(capsys) -> None:
    rc = main(["--json"])
    assert rc == 0
    output = json.loads(capsys.readouterr().out)
    assert output["total_sources"] == 5
    assert output["enabled"] == 2


def test_cli_custom_config(tmp_path, capsys) -> None:
    config = PipelineConfig(sources=[
        SignalSource(name="only_one", kind="test", enabled=True),
    ])
    path = tmp_path / "cfg.json"
    save_config(config, path)

    rc = main(["--config", str(path), "--json"])
    assert rc == 0
    output = json.loads(capsys.readouterr().out)
    assert output["total_sources"] == 1


def test_cli_text_mode(capsys) -> None:
    rc = main([])
    assert rc == 0
    out = capsys.readouterr().out
    assert "2/5 sources enabled" in out
