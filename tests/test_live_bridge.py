from __future__ import annotations

import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from renquant_orchestrator import live_bridge as mod


def test_with_pinned_strategy_config_injects_prod_path(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("RENQUANT_SUBREPO_ROOT", str(tmp_path))

    argv = mod._with_pinned_strategy_config(
        ["--strategy", "renquant_104", "--broker", "alpaca", "--once"],
        repo_root=tmp_path / "RenQuant",
    )

    assert "--strategy-config-path" in argv
    cfg = argv[argv.index("--strategy-config-path") + 1]
    assert cfg == str(tmp_path / "renquant-strategy-104" / "configs" / "strategy_config.json")


def test_with_pinned_strategy_config_injects_shadow_path(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("RENQUANT_SUBREPO_ROOT", str(tmp_path))

    argv = mod._with_pinned_strategy_config(
        ["--strategy", "renquant_104", "--broker", "readonly-alpaca", "--once"],
        repo_root=tmp_path / "RenQuant",
    )

    cfg = argv[argv.index("--strategy-config-path") + 1]
    assert cfg == str(tmp_path / "renquant-strategy-104" / "configs" / "strategy_config.shadow.json")


def test_with_pinned_strategy_config_preserves_explicit_config_path(tmp_path: Path) -> None:
    argv = ["--strategy-config-path", "/already/pinned.json", "--broker", "alpaca"]

    assert mod._with_pinned_strategy_config(argv, repo_root=tmp_path / "RenQuant") == argv


def test_subrepo_src_roots_uses_lock_local_paths(tmp_path: Path, monkeypatch) -> None:
    common = tmp_path / "renquant-common"
    pipeline = tmp_path / "renquant-pipeline"
    (common / "src").mkdir(parents=True)
    (pipeline / "src").mkdir(parents=True)
    lock = tmp_path / "subrepos.lock.json"
    lock.write_text(
        json.dumps(
            {
                "subrepos": [
                    {"name": "renquant-common", "local_path": str(common)},
                    {"name": "renquant-pipeline", "local_path": str(pipeline)},
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("RENQUANT_SUBREPO_ROOT", raising=False)

    roots, missing = mod._subrepo_src_roots(
        repo_root=tmp_path / "RenQuant",
        lock_file=lock,
        siblings=tmp_path / "unused",
        pin_srcs=["renquant-common", "renquant-pipeline"],
    )

    assert roots == [common / "src", pipeline / "src"]
    assert missing == []


def test_force_alias_fails_closed_on_critical_import(monkeypatch) -> None:
    def fake_import(name: str):
        raise ImportError(f"blocked {name}")

    monkeypatch.setattr(mod.importlib, "import_module", fake_import)
    with pytest.raises(RuntimeError, match="critical multirepo module unavailable"):
        mod._force_alias("kernel.preflight", "renquant_pipeline.kernel.preflight", [])


def test_run_bridge_preflights_alpaca_credentials(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)

    def fail_bootstrap(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("bootstrap should not run without Alpaca credentials")

    monkeypatch.setattr(mod, "bootstrap_multirepo", fail_bootstrap)

    rc = mod.run_bridge(
        ["--broker=readonly-alpaca", "--once"],
        mode="live",
        repo_root=tmp_path / "RenQuant",
    )

    assert rc == 2
    assert "missing ALPACA_API_KEY, ALPACA_SECRET_KEY" in capsys.readouterr().err


def test_run_bridge_captures_bridge_bundle_after_commit(monkeypatch, tmp_path: Path) -> None:
    output = tmp_path / "bridge.json"
    seen = {}
    monkeypatch.setenv("ALPACA_API_KEY", "key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "secret")

    class FakeRunnerAdapter:
        def commit(self, ctx):
            ctx.orders_placed = [{"ticker": "AAPL", "status": "filled"}]
            return None

    adapters_runner = SimpleNamespace(RunnerAdapter=FakeRunnerAdapter)
    original_import = mod.importlib.import_module

    def fake_import(name: str, *args, **kwargs):
        if name == "adapters.runner":
            return adapters_runner
        if name == "live.runner":
            return SimpleNamespace(main=fake_live_main)
        return original_import(name, *args, **kwargs)

    def fake_live_main():
        seen["argv"] = list(sys.argv)
        ctx = SimpleNamespace(
            decision_trace=[{"ticker": "AAPL", "stage": "score"}],
            orders=[{"ticker": "AAPL", "action": "buy", "quantity": 1}],
        )
        FakeRunnerAdapter().commit(ctx)
        return 0

    monkeypatch.setattr(mod, "bootstrap_multirepo", lambda repo_root: ["kernel.preflight"])
    monkeypatch.setattr(mod.importlib, "import_module", fake_import)

    rc = mod.run_bridge(
        [
            "--broker",
            "readonly-alpaca",
            "--once",
            "--bridge-bundle-output",
            str(output),
        ],
        mode="live",
        repo_root=tmp_path / "RenQuant",
    )

    assert rc == 0
    assert "--bridge-bundle-output" not in seen["argv"]
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["source"] == "live_runner_bridge"
    assert payload["metadata"]["bridge_mode"] == "live"
    assert payload["order_intents"][0]["ticker"] == "AAPL"
    assert payload["execution_audit"][0]["kind"] == "order_placed"


def test_run_bridge_captures_native_inference_before_commit(monkeypatch, tmp_path: Path) -> None:
    inference_output = tmp_path / "native-inference.json"
    bridge_output = tmp_path / "bridge.json"
    seen = {}
    monkeypatch.setenv("ALPACA_API_KEY", "key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "secret")

    class FakeRunnerAdapter:
        def commit(self, ctx):
            ctx.decision_trace.append({"stage": "commit_should_not_appear"})
            ctx.orders_placed = [{"ticker": "AAPL", "status": "filled"}]
            return None

    adapters_runner = SimpleNamespace(RunnerAdapter=FakeRunnerAdapter)
    original_import = mod.importlib.import_module

    def fake_import(name: str, *args, **kwargs):
        if name == "adapters.runner":
            return adapters_runner
        if name == "live.runner":
            return SimpleNamespace(main=fake_live_main)
        return original_import(name, *args, **kwargs)

    def fake_live_main():
        seen["argv"] = list(sys.argv)
        ctx = SimpleNamespace(
            config={"watchlist": ["AAPL"]},
            market_snapshot={"as_of": "2026-06-09"},
            decision_trace=[{"ticker": "AAPL", "stage": "score"}],
            orders=[{"ticker": "AAPL", "action": "buy", "quantity": 1}],
            _ticker_score_snapshot={"AAPL": {"rank_score": 0.8}},
        )
        FakeRunnerAdapter().commit(ctx)
        return 0

    monkeypatch.setattr(mod, "bootstrap_multirepo", lambda repo_root: ["kernel.preflight"])
    monkeypatch.setattr(mod.importlib, "import_module", fake_import)

    rc = mod.run_bridge(
        [
            "--broker",
            "readonly-alpaca",
            "--once",
            "--native-inference-payload-output",
            str(inference_output),
            "--bridge-bundle-output",
            str(bridge_output),
        ],
        mode="live",
        repo_root=tmp_path / "RenQuant",
    )

    assert rc == 0
    assert "--native-inference-payload-output" not in seen["argv"]
    inference_payload = json.loads(inference_output.read_text(encoding="utf-8"))
    assert inference_payload["source"] == "renquant_pipeline.live_context_inference"
    assert inference_payload["market_as_of"] == "2026-06-09"
    assert inference_payload["decision_trace"] == [{"ticker": "AAPL", "stage": "score"}]
    assert inference_payload["order_intents"] == [
        {"ticker": "AAPL", "action": "buy", "quantity": 1}
    ]
    assert inference_payload["scores"] == {"AAPL": 0.8}
    bridge_payload = json.loads(bridge_output.read_text(encoding="utf-8"))
    assert bridge_payload["decision_trace"][-1]["stage"] == "commit_should_not_appear"
    assert bridge_payload["execution_audit"][0]["kind"] == "order_placed"


def test_runner_commit_hooks_preserve_before_commit_after_order(monkeypatch) -> None:
    events = []

    class FakeRunnerAdapter:
        def commit(self, ctx):
            events.append(("commit", list(ctx.orders)))
            ctx.orders_placed = [{"ticker": "AAPL", "status": "filled"}]
            return "ok"

    adapters_runner = SimpleNamespace(RunnerAdapter=FakeRunnerAdapter)
    original_import = mod.importlib.import_module

    def fake_import(name: str, *args, **kwargs):
        if name == "adapters.runner":
            return adapters_runner
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(mod.importlib, "import_module", fake_import)
    mod._reset_runner_commit_hooks()

    def before_hook(_adapter, ctx):
        events.append(("before", list(ctx.orders)))

    def after_hook(_adapter, ctx):
        events.append(("after", list(ctx.orders_placed)))

    mod._install_runner_commit_hook(before_hook, timing="before")
    mod._install_runner_commit_hook(after_hook, timing="after")

    ctx = SimpleNamespace(orders=[{"ticker": "AAPL"}])
    result = FakeRunnerAdapter().commit(ctx)

    assert result == "ok"
    assert events == [
        ("before", [{"ticker": "AAPL"}]),
        ("commit", [{"ticker": "AAPL"}]),
        ("after", [{"ticker": "AAPL", "status": "filled"}]),
    ]
