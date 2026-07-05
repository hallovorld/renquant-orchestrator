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
        rc = 1 if call_n["i"] == 2 else 0
        if rc == 0:
            # A successful train_gbdt run writes its --output-path artifact; the
            # manifest builder now resolves that path fail-closed before stamping
            # a row, so the success-path fake must produce the file.
            for i, tok in enumerate(cmd):
                if tok == "--output-path":
                    Path(cmd[i + 1]).parent.mkdir(parents=True, exist_ok=True)
                    Path(cmd[i + 1]).write_text("{}")
                    break
        return _RC(rc)
    monkeypatch.setattr(build_wf_manifest.subprocess, "run", fake_run)
    rc = build_wf_manifest.main([
        "--source-manifest", str(fake_source_manifest),
        "--output-dir", str(tmp_path / "r"),
        "--output-manifest", str(tmp_path / "m.json"),
    ])
    assert rc != 0
    manifest = json.loads((tmp_path / "m.json").read_text())
    assert manifest["failed_cutoffs"] == ["2022-01-22"]
    # rc=0 cutoffs that produced their artifact are appended; failed_cutoffs is
    # the authoritative skip list. (Post #108 S1: a rc=0 cutoff whose artifact is
    # missing now fails closed via resolve_artifact rather than stamping a
    # silent missing path — see test_build_wf_manifest_resolver.py.)
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


# ────────────────────────────────────────────────────────────────────────────────
# Pure helper tests — extract_cutoffs
# ────────────────────────────────────────────────────────────────────────────────


def test_extract_cutoffs_flat_list_payload(tmp_path: Path) -> None:
    """A manifest whose top-level is a bare list (no ``retrains`` key) is accepted."""
    m = tmp_path / "flat.json"
    m.write_text(json.dumps([
        {"cutoff_date": "2023-06-15T00:00:00"},
        {"cutoff_date": "2023-03-01"},
    ]))
    assert build_wf_manifest.extract_cutoffs(m) == ["2023-06-15", "2023-03-01"]


def test_extract_cutoffs_empty_retrains(tmp_path: Path) -> None:
    m = tmp_path / "empty.json"
    m.write_text(json.dumps({"retrains": []}))
    assert build_wf_manifest.extract_cutoffs(m) == []


def test_extract_cutoffs_dict_without_retrains_key(tmp_path: Path) -> None:
    """A dict with no ``retrains`` key falls back to iterating the dict itself."""
    m = tmp_path / "bare.json"
    m.write_text(json.dumps({"something_else": []}))
    # payload.get("retrains", payload) returns payload (the dict itself);
    # iterating a dict yields its keys — which are strings, not dicts — so
    # r.get("cutoff_date") will raise AttributeError.  This confirms the
    # contract: callers must supply a payload with "retrains" or a bare list.
    with pytest.raises((AttributeError, TypeError)):
        build_wf_manifest.extract_cutoffs(m)


# ────────────────────────────────────────────────────────────────────────────────
# Pure helper tests — build_train_cmd
# ────────────────────────────────────────────────────────────────────────────────


def test_build_train_cmd_minimal() -> None:
    """Minimal call: no data_dir, no strategy_config, no drop/skip flags."""
    cmd = build_wf_manifest.build_train_cmd(
        cutoff="2022-03-01",
        out_path=Path("/out/panel-ltr.json"),
        side_label="wf_test",
        cv_embargo_days=60,
        cv_n_splits=3,
        drop_sentiment=False,
        skip_cv=False,
    )
    assert cmd[0].endswith("python") or "python" in cmd[0]  # sys.executable
    assert cmd[1:3] == ["-m", "renquant_orchestrator.train_gbdt"]
    assert "--train-cutoff" in cmd
    idx = cmd.index("--train-cutoff")
    assert cmd[idx + 1] == "2022-03-01"
    assert "--side-label" in cmd
    assert cmd[cmd.index("--side-label") + 1] == "wf_test"
    assert "--cv-embargo-days" in cmd
    assert cmd[cmd.index("--cv-embargo-days") + 1] == "60"
    assert "--cv-n-splits" in cmd
    assert cmd[cmd.index("--cv-n-splits") + 1] == "3"
    assert "--output-path" in cmd
    assert cmd[cmd.index("--output-path") + 1] == "/out/panel-ltr.json"
    # Flags should NOT be present when disabled
    assert "--drop-sentiment" not in cmd
    assert "--skip-cv" not in cmd
    assert "--data-dir" not in cmd
    assert "--strategy-config" not in cmd


def test_build_train_cmd_all_flags() -> None:
    """All optional flags and paths present."""
    cmd = build_wf_manifest.build_train_cmd(
        cutoff="2023-01-15",
        out_path=Path("/retrains/2023-01-15/panel-ltr.json"),
        side_label="wf_dropsenti_v3",
        cv_embargo_days=90,
        cv_n_splits=5,
        drop_sentiment=True,
        skip_cv=True,
        data_dir=Path("/data/root"),
        strategy_config=Path("/configs/strategy_config.json"),
    )
    assert "--drop-sentiment" in cmd
    assert "--skip-cv" in cmd
    assert "--data-dir" in cmd
    assert cmd[cmd.index("--data-dir") + 1] == "/data/root"
    assert "--strategy-config" in cmd
    assert cmd[cmd.index("--strategy-config") + 1] == "/configs/strategy_config.json"


def test_build_train_cmd_returns_list_of_strings() -> None:
    """Every element of the returned command must be a string (subprocess contract)."""
    cmd = build_wf_manifest.build_train_cmd(
        cutoff="2022-01-01",
        out_path=Path("/o"),
        side_label="x",
        cv_embargo_days=30,
        cv_n_splits=2,
        drop_sentiment=False,
        skip_cv=False,
    )
    assert all(isinstance(tok, str) for tok in cmd)


# ────────────────────────────────────────────────────────────────────────────────
# Pure helper tests — manifest_row
# ────────────────────────────────────────────────────────────────────────────────


def test_manifest_row_happy_path(tmp_path: Path) -> None:
    """An existing artifact file produces a well-formed manifest row."""
    artifact = tmp_path / "2022-01-01" / "panel-ltr.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("{}")
    row = build_wf_manifest.manifest_row(
        artifact_uri=artifact,
        cutoff="2022-01-01",
        lookahead_days=60,
        repo_root=tmp_path,
    )
    assert row["cutoff_date"] == "2022-01-01"
    assert row["lookahead_days"] == 60
    assert "trained_date" in row
    assert "artifact_uri" in row
    # The resolved path should be a real absolute path
    assert Path(row["artifact_uri"]).is_absolute()


def test_manifest_row_missing_artifact_raises(tmp_path: Path) -> None:
    """A missing artifact must raise FileNotFoundError (fail-closed contract)."""
    missing = tmp_path / "nonexistent" / "panel-ltr.json"
    with pytest.raises(FileNotFoundError):
        build_wf_manifest.manifest_row(
            artifact_uri=missing,
            cutoff="2022-06-01",
            repo_root=tmp_path,
        )


def test_manifest_row_default_lookahead(tmp_path: Path) -> None:
    """Default lookahead_days is 60."""
    artifact = tmp_path / "panel-ltr.json"
    artifact.write_text("{}")
    row = build_wf_manifest.manifest_row(
        artifact_uri=artifact,
        cutoff="2022-01-01",
        repo_root=tmp_path,
    )
    assert row["lookahead_days"] == 60


# ────────────────────────────────────────────────────────────────────────────────
# Pure helper tests — build_manifest_payload
# ────────────────────────────────────────────────────────────────────────────────


def test_build_manifest_payload_structure(tmp_path: Path) -> None:
    """The v2 payload has the required schema keys."""
    source = tmp_path / "source.json"
    source.write_text("{}")
    rows = [{"artifact_uri": "/a", "cutoff_date": "2022-01-01"}]
    payload = build_wf_manifest.build_manifest_payload(
        rows=rows,
        source_manifest_path=source,
        options={"drop_sentiment": True},
        failed_cutoffs=["2022-02-01"],
    )
    assert payload["schema_version"] == 2
    assert payload["built_by"] == "renquant_orchestrator.build_wf_manifest"
    assert payload["trainer"] == "renquant_orchestrator.train_gbdt"
    assert payload["retrains"] == rows
    assert payload["failed_cutoffs"] == ["2022-02-01"]
    assert payload["options"] == {"drop_sentiment": True}
    assert payload["built_at"].endswith("Z")
    assert str(source.resolve()) == payload["source_manifest"]


def test_build_manifest_payload_empty_rows(tmp_path: Path) -> None:
    """An empty rows list is valid (all cutoffs may have failed)."""
    source = tmp_path / "source.json"
    source.write_text("{}")
    payload = build_wf_manifest.build_manifest_payload(
        rows=[],
        source_manifest_path=source,
        options={},
        failed_cutoffs=["2022-01-01", "2022-02-01"],
    )
    assert payload["retrains"] == []
    assert len(payload["failed_cutoffs"]) == 2


def test_build_manifest_payload_copies_inputs(tmp_path: Path) -> None:
    """Payload must copy mutable inputs so later mutations don't leak back."""
    source = tmp_path / "s.json"
    source.write_text("{}")
    rows = [{"cutoff_date": "2022-01-01"}]
    failed = ["2022-02-01"]
    options = {"k": "v"}
    payload = build_wf_manifest.build_manifest_payload(
        rows=rows,
        source_manifest_path=source,
        options=options,
        failed_cutoffs=failed,
    )
    # Mutate originals — payload must be independent
    rows.append({"cutoff_date": "extra"})
    failed.append("extra")
    options["k2"] = "v2"
    assert len(payload["retrains"]) == 1
    assert len(payload["failed_cutoffs"]) == 1
    assert "k2" not in payload["options"]


# ────────────────────────────────────────────────────────────────────────────────
# Pure helper tests — training_env
# ────────────────────────────────────────────────────────────────────────────────


def test_training_env_data_dir_named_data(tmp_path: Path) -> None:
    """When data_dir ends in 'data', its parent becomes RENQUANT_DATA_ROOT."""
    data_dir = tmp_path / "RenQuant" / "data"
    env = build_wf_manifest.training_env(data_dir, strategy_config=None)
    assert env["RENQUANT_DATA_ROOT"] == str(tmp_path / "RenQuant")
    assert env["RENQUANT_STRATEGY_DIR"] == str(
        tmp_path / "RenQuant" / "backtesting" / "renquant_104"
    )


def test_training_env_data_dir_not_named_data(tmp_path: Path) -> None:
    """When data_dir does NOT end in 'data', it is used directly as data root."""
    data_dir = tmp_path / "custom_root"
    env = build_wf_manifest.training_env(data_dir, strategy_config=None)
    assert env["RENQUANT_DATA_ROOT"] == str(tmp_path / "custom_root")


def test_training_env_strategy_config(tmp_path: Path) -> None:
    env = build_wf_manifest.training_env(
        data_dir=None, strategy_config="/configs/strategy_config.json"
    )
    assert env["RENQUANT_STRATEGY_CONFIG"] == "/configs/strategy_config.json"


def test_training_env_no_args() -> None:
    """With both args None, the env is a copy of os.environ with no extras set."""
    import os
    env = build_wf_manifest.training_env(data_dir=None, strategy_config=None)
    # Should be a dict (not os.environ itself) containing PATH at minimum
    assert isinstance(env, dict)
    assert "PATH" in env
    # Should not inject RENQUANT keys when args are None
    # (unless they were already in os.environ)
    if "RENQUANT_DATA_ROOT" not in os.environ:
        assert "RENQUANT_DATA_ROOT" not in env


def test_training_env_setdefault_does_not_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pre-existing env vars are NOT overwritten (setdefault contract)."""
    monkeypatch.setenv("RENQUANT_DATA_ROOT", "/existing")
    data_dir = tmp_path / "data"
    env = build_wf_manifest.training_env(data_dir, strategy_config=None)
    assert env["RENQUANT_DATA_ROOT"] == "/existing"
