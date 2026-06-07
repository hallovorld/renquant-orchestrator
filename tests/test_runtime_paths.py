from __future__ import annotations

from pathlib import Path

from renquant_orchestrator import runtime_paths as mod


def test_default_roots_honor_environment(monkeypatch, tmp_path: Path) -> None:
    github = tmp_path / "github-root"
    repo = tmp_path / "runtime-root"
    monkeypatch.setenv("RENQUANT_GITHUB_ROOT", str(github))
    monkeypatch.setenv("RENQUANT_REPO_ROOT", str(repo))

    assert mod.default_github_root() == github
    assert mod.default_repo_root() == repo


def test_default_strategy_config_prefers_subrepo_when_present(monkeypatch, tmp_path: Path) -> None:
    github = tmp_path / "github-root"
    repo = tmp_path / "runtime-root"
    subrepo_cfg = github / "renquant-strategy-104" / "configs" / "strategy_config.json"
    legacy_cfg = repo / "backtesting" / "renquant_104" / "strategy_config.json"
    subrepo_cfg.parent.mkdir(parents=True)
    legacy_cfg.parent.mkdir(parents=True)
    subrepo_cfg.write_text("{}", encoding="utf-8")
    legacy_cfg.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("RENQUANT_GITHUB_ROOT", str(github))
    monkeypatch.setenv("RENQUANT_REPO_ROOT", str(repo))

    assert mod.default_strategy_config_path() == subrepo_cfg


def test_default_strategy_config_falls_back_to_repo_root(monkeypatch, tmp_path: Path) -> None:
    github = tmp_path / "github-root"
    repo = tmp_path / "runtime-root"
    legacy_cfg = repo / "backtesting" / "renquant_104" / "strategy_config.json"
    legacy_cfg.parent.mkdir(parents=True)
    legacy_cfg.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("RENQUANT_GITHUB_ROOT", str(github))
    monkeypatch.setenv("RENQUANT_REPO_ROOT", str(repo))

    assert mod.default_strategy_config_path() == legacy_cfg
