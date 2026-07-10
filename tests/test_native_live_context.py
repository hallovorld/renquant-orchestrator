from __future__ import annotations

import json
from pathlib import Path

from renquant_orchestrator.cli import main as cli_main
from renquant_orchestrator.native_live_context import (
    NATIVE_CONTEXT_PRODUCER,
    build_native_live_context,
)


def _write_inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    config = tmp_path / "strategy_config.json"
    market = tmp_path / "market.json"
    account = tmp_path / "account.json"
    config.write_text(json.dumps({"watchlist": ["AAPL"]}), encoding="utf-8")
    market.write_text(json.dumps({"as_of": "2026-06-15"}), encoding="utf-8")
    account.write_text(json.dumps({"positions": {}}), encoding="utf-8")
    return config, market, account


def test_build_native_live_context_writes_hydrated_context(tmp_path: Path) -> None:
    config, market, account = _write_inputs(tmp_path)
    metadata = tmp_path / "metadata.json"
    output = tmp_path / "context.json"
    metadata.write_text(json.dumps({"mode": "live"}), encoding="utf-8")

    payload = build_native_live_context(
        strategy_config_json=config,
        market_snapshot_json=market,
        account_snapshot_json=account,
        metadata_json=metadata,
        output_json=output,
    )

    assert payload["source"] == "native_live_context_fixture"
    assert payload["config"] == {"watchlist": ["AAPL"]}
    assert payload["market_snapshot"] == {"as_of": "2026-06-15"}
    assert payload["account_snapshot"] == {"positions": {}}
    assert payload["metadata"]["mode"] == "live"
    assert payload["metadata"]["native_context_producer"] == {
        "source": NATIVE_CONTEXT_PRODUCER,
        "strategy_config_json": str(config),
        "market_snapshot_json": str(market),
        "account_snapshot_json": str(account),
    }
    assert json.loads(output.read_text(encoding="utf-8")) == payload


def test_native_live_context_cli_writes_payload(tmp_path: Path, capsys) -> None:
    config, market, account = _write_inputs(tmp_path)
    output = tmp_path / "context.json"

    rc = cli_main([
        "native-live-context",
        "--strategy-config-json",
        str(config),
        "--market-snapshot-json",
        str(market),
        "--account-snapshot-json",
        str(account),
        "--output-json",
        str(output),
    ])

    assert rc == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed == json.loads(output.read_text(encoding="utf-8"))
    assert printed["metadata"]["native_context_producer"]["source"] == (
        NATIVE_CONTEXT_PRODUCER
    )


# --- §2a paired-world verification (consumption side) ---------------------------
#
# Repro: the first REAL two-arm session (2026-07-10) failed with
# "renquant-orchestrator: error: unrecognized arguments:
#  --decision-snapshot-digest ... --model-content-sha256 ... --session-date ...
#  --calibrator-content-sha256 ..." — the shadow-ab runner emitted the
# paired-world flags but the TOP-LEVEL cli.py subparser never declared them
# (the module main() did), so both arms exited 2 and the session was
# paired-invalidated. These tests drive the cli.py surface directly.

import pytest

import renquant_orchestrator.native_live_context as nlc
from renquant_orchestrator.native_live_context import (
    DecisionSnapshotMismatchError,
    decision_snapshot_identity,
    panel_artifact_refs,
    verify_config_artifact_shas,
)


def _fake_fingerprint(path: str | Path) -> str:
    return "sha256:fp-" + Path(path).read_text(encoding="utf-8").strip()


def _paired_world(tmp_path: Path) -> dict[str, Path]:
    model = tmp_path / "model.pt"
    model.write_text("model-1", encoding="utf-8")
    calibrator = tmp_path / "calibrator.json"
    calibrator.write_text("cal-1", encoding="utf-8")
    config = tmp_path / "configs" / "strategy_config.shadow.json"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(json.dumps({
        "ranking": {"panel_scoring": {
            "artifact_path": str(model),
            "global_calibration": {"enabled": True, "artifact_path": str(calibrator)},
        }},
    }), encoding="utf-8")
    market = tmp_path / "sealed_market.json"
    market.write_text(json.dumps({"as_of": "2026-07-10"}), encoding="utf-8")
    account = tmp_path / "sealed_account.json"
    account.write_text(json.dumps({"positions": {}}), encoding="utf-8")
    return {
        "config": config, "market": market, "account": account,
        "model": model, "calibrator": calibrator,
    }


def _paired_cli_argv(world: dict[str, Path], output: Path, *, digest: str,
                     model_sha: str, calibrator_sha: str | None) -> list[str]:
    argv = [
        "native-live-context",
        "--strategy-config-json", str(world["config"]),
        "--market-snapshot-json", str(world["market"]),
        "--account-snapshot-json", str(world["account"]),
        "--output-json", str(output),
        "--decision-snapshot-digest", digest,
        "--model-content-sha256", model_sha,
        "--session-date", "2026-07-10",
    ]
    if calibrator_sha is not None:
        argv += ["--calibrator-content-sha256", calibrator_sha]
    return argv


def test_cli_accepts_paired_world_args_and_verifies(tmp_path: Path, capsys, monkeypatch) -> None:
    monkeypatch.setattr(nlc, "default_model_fingerprint_from_path", lambda: _fake_fingerprint)
    world = _paired_world(tmp_path)
    model_sha, cal_sha = "sha256:fp-model-1", "sha256:fp-cal-1"
    digest = decision_snapshot_identity(
        market_snapshot_json=world["market"],
        account_snapshot_json=world["account"],
        session_date="2026-07-10",
        model_content_sha256=model_sha,
        calibrator_content_sha256=cal_sha,
    )["digest"]
    output = tmp_path / "context.json"

    rc = cli_main(_paired_cli_argv(world, output, digest=digest,
                                   model_sha=model_sha, calibrator_sha=cal_sha))
    assert rc == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["metadata"]["decision_snapshot_verified"] is True
    assert payload["metadata"]["decision_snapshot_digest"] == digest
    assert payload["metadata"]["config_artifact_shas_verified"] is True
    assert payload["metadata"]["market_snapshot_sha256"].startswith("sha256:")
    assert payload["metadata"]["account_snapshot_sha256"].startswith("sha256:")


def test_cli_digest_mismatch_exits_nonzero_with_clear_message(tmp_path: Path, capsys, monkeypatch) -> None:
    monkeypatch.setattr(nlc, "default_model_fingerprint_from_path", lambda: _fake_fingerprint)
    world = _paired_world(tmp_path)
    output = tmp_path / "context.json"

    rc = cli_main(_paired_cli_argv(world, output, digest="beef" * 16,
                                   model_sha="sha256:fp-model-1",
                                   calibrator_sha="sha256:fp-cal-1"))
    assert rc == 2
    err = capsys.readouterr().err
    assert "PAIRED-WORLD MISMATCH" in err
    assert "digest mismatch" in err
    assert not output.exists()  # never writes a misleading context


def test_cli_model_sha_mismatch_exits_nonzero(tmp_path: Path, capsys, monkeypatch) -> None:
    """The frozen model sha disagrees with the artifact the config actually
    resolves to. The digest is computed WITH the wrong sha so the digest
    recompute alone would pass — only the artifact check catches it."""
    monkeypatch.setattr(nlc, "default_model_fingerprint_from_path", lambda: _fake_fingerprint)
    world = _paired_world(tmp_path)
    wrong_model_sha = "sha256:fp-some-other-model"
    digest = decision_snapshot_identity(
        market_snapshot_json=world["market"],
        account_snapshot_json=world["account"],
        session_date="2026-07-10",
        model_content_sha256=wrong_model_sha,
        calibrator_content_sha256="sha256:fp-cal-1",
    )["digest"]
    output = tmp_path / "context.json"

    rc = cli_main(_paired_cli_argv(world, output, digest=digest,
                                   model_sha=wrong_model_sha,
                                   calibrator_sha="sha256:fp-cal-1"))
    assert rc == 2
    err = capsys.readouterr().err
    assert "PAIRED-WORLD MISMATCH" in err
    assert "model sha mismatch" in err
    assert not output.exists()


def test_cli_calibrator_declared_but_not_frozen_exits_nonzero(tmp_path: Path, capsys, monkeypatch) -> None:
    monkeypatch.setattr(nlc, "default_model_fingerprint_from_path", lambda: _fake_fingerprint)
    world = _paired_world(tmp_path)
    digest = decision_snapshot_identity(
        market_snapshot_json=world["market"],
        account_snapshot_json=world["account"],
        session_date="2026-07-10",
        model_content_sha256="sha256:fp-model-1",
        calibrator_content_sha256=None,
    )["digest"]
    output = tmp_path / "context.json"

    rc = cli_main(_paired_cli_argv(world, output, digest=digest,
                                   model_sha="sha256:fp-model-1",
                                   calibrator_sha=None))
    assert rc == 2
    err = capsys.readouterr().err
    assert "PAIRED-WORLD MISMATCH" in err
    assert "declares an enabled calibrator" in err


def test_absent_paired_world_args_keep_legacy_behavior_identical(tmp_path: Path) -> None:
    """Byte-identical legacy pin: without the §2a args, the payload is
    EXACTLY the pre-change shape — no verification, no new metadata keys,
    no artifact resolution (no fingerprint authority is even constructed)."""
    config, market, account = _write_inputs(tmp_path)
    output = tmp_path / "context.json"

    payload = build_native_live_context(
        strategy_config_json=config,
        market_snapshot_json=market,
        account_snapshot_json=account,
        output_json=output,
    )
    assert payload == {
        "schema_version": 1,
        "source": "native_live_context_fixture",
        "config": {"watchlist": ["AAPL"]},
        "market_snapshot": {"as_of": "2026-06-15"},
        "account_snapshot": {"positions": {}},
        "metadata": {
            "native_context_producer": {
                "source": NATIVE_CONTEXT_PRODUCER,
                "strategy_config_json": str(config),
                "market_snapshot_json": str(market),
                "account_snapshot_json": str(account),
            },
        },
    }
    assert json.loads(output.read_text(encoding="utf-8")) == payload


def test_verify_config_artifact_shas_resolves_relative_to_config_dir(tmp_path: Path) -> None:
    """Anchor pin: a RELATIVE artifact ref resolves against the config
    file's own parent directory first (the pinned strategy-104 configs dir
    on the §2a path) — armed configs must be resolvable from there."""
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    (config_dir / "model.pt").write_text("model-rel", encoding="utf-8")
    config_path = config_dir / "strategy_config.shadow.json"
    config = {"ranking": {"panel_scoring": {"artifact_path": "model.pt"}}}
    config_path.write_text(json.dumps(config), encoding="utf-8")

    result = verify_config_artifact_shas(
        strategy_config_json=config_path,
        config=config,
        model_content_sha256="sha256:fp-model-rel",
        calibrator_content_sha256=None,
        fingerprint_from_path=_fake_fingerprint,
    )
    assert result["model_content_sha256"] == "sha256:fp-model-rel"

    with pytest.raises(DecisionSnapshotMismatchError, match="unresolvable"):
        verify_config_artifact_shas(
            strategy_config_json=config_path,
            config={"ranking": {"panel_scoring": {"artifact_path": "missing.pt"}}},
            model_content_sha256="sha256:whatever",
            calibrator_content_sha256=None,
            fingerprint_from_path=_fake_fingerprint,
        )


def test_panel_artifact_refs_fail_closed() -> None:
    with pytest.raises(ValueError, match="artifact_path"):
        panel_artifact_refs({"ranking": {"panel_scoring": {}}})
    with pytest.raises(ValueError, match="calibrator"):
        panel_artifact_refs({"ranking": {"panel_scoring": {
            "artifact_path": "m.pt",
            "global_calibration": {"enabled": True},
        }}})
    assert panel_artifact_refs({"ranking": {"panel_scoring": {
        "artifact_path": "m.pt",
        "global_calibration": {"enabled": False, "artifact_path": "c.json"},
    }}}) == ("m.pt", None)


def test_verify_config_artifact_shas_honors_runner_anchors(tmp_path: Path) -> None:
    """The two-arm runner threads its OWN (strategy_dir, repo_root) anchors
    into the context so both sides resolve identically — a ref resolvable
    only from the runner's strategy_dir must verify when the anchors are
    handed in, and fail closed when they are not."""
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    runner_strategy_dir = tmp_path / "strategy-root"
    (runner_strategy_dir / "artifacts").mkdir(parents=True)
    (runner_strategy_dir / "artifacts" / "model.pt").write_text("m-anchored", encoding="utf-8")
    config_path = config_dir / "strategy_config.shadow.json"
    config = {"ranking": {"panel_scoring": {"artifact_path": "artifacts/model.pt"}}}
    config_path.write_text(json.dumps(config), encoding="utf-8")

    result = verify_config_artifact_shas(
        strategy_config_json=config_path,
        config=config,
        model_content_sha256="sha256:fp-m-anchored",
        calibrator_content_sha256=None,
        strategy_dir=runner_strategy_dir,
        repo_root=tmp_path / "nonexistent-repo-root",
        fingerprint_from_path=_fake_fingerprint,
    )
    assert result["model_content_sha256"] == "sha256:fp-m-anchored"

    with pytest.raises(DecisionSnapshotMismatchError, match="unresolvable"):
        verify_config_artifact_shas(
            strategy_config_json=config_path,
            config=config,
            model_content_sha256="sha256:fp-m-anchored",
            calibrator_content_sha256=None,
            repo_root=tmp_path / "nonexistent-repo-root",
            fingerprint_from_path=_fake_fingerprint,
        )
