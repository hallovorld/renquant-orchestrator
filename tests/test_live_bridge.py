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
    monkeypatch.setitem(
        sys.modules,
        "renquant_pipeline",
        SimpleNamespace(
            runtime_inference_payload_from_live_context=lambda ctx: {
                "schema_version": 1,
                "source": "renquant_pipeline.live_context_inference",
                "market_as_of": ctx.market_snapshot["as_of"],
                "decision_trace": list(ctx.decision_trace),
                "order_intents": list(ctx.orders),
                "scores": {"AAPL": 0.8},
            },
        ),
    )

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
    assert inference_payload["metadata"]["native_inference_producer"]["source"] == (
        "live_runner_bridge_hook"
    )
    assert inference_payload["metadata"]["native_inference_producer"]["bridge_mode"] == "live"
    assert inference_payload["market_as_of"] == "2026-06-09"
    assert inference_payload["decision_trace"] == [{"ticker": "AAPL", "stage": "score"}]
    assert inference_payload["order_intents"] == [
        {"ticker": "AAPL", "action": "buy", "quantity": 1}
    ]
    assert inference_payload["scores"] == {"AAPL": 0.8}
    bridge_payload = json.loads(bridge_output.read_text(encoding="utf-8"))
    assert bridge_payload["decision_trace"][-1]["stage"] == "commit_should_not_appear"
    assert bridge_payload["execution_audit"][0]["kind"] == "order_placed"


def test_bootstrap_fails_closed_on_declared_module_import_error(tmp_path: Path, monkeypatch) -> None:
    """A module present in the pipeline kernel dir that fails to import must raise."""
    kernel_dir = tmp_path / "pipeline_kernel"
    kernel_dir.mkdir()
    (kernel_dir / "__init__.py").touch()
    (kernel_dir / "sizing.py").write_text("raise SyntaxError('bad')", encoding="utf-8")

    original_import = mod.importlib.import_module

    def fake_import(name: str, *args, **kwargs):
        if name == "renquant_pipeline.kernel":
            return SimpleNamespace(
                __file__=str(kernel_dir / "__init__.py"),
                NON_OWNED_KERNEL_STEMS=frozenset(),
            )
        if name == "renquant_pipeline.kernel.sizing":
            raise SyntaxError("bad")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(mod.importlib, "import_module", fake_import)
    monkeypatch.setattr(mod, "_force_alias", lambda a, t, al: al.append(f"{a}<-{t}"))
    monkeypatch.setattr(mod, "resolve_subrepo_src_roots", lambda **kw: ([], []))
    monkeypatch.setattr(mod, "enforce_or_warn", lambda issues: None)
    monkeypatch.setattr(mod, "strict_clean_enabled", lambda: False)

    with pytest.raises(RuntimeError, match="fail-closed.*sizing"):
        mod.bootstrap_multirepo(repo_root=tmp_path / "RenQuant")


def test_bootstrap_umbrella_only_module_not_in_pipeline_dir(tmp_path: Path, monkeypatch) -> None:
    """Modules only in the umbrella kernel (absent from pipeline dir) are not aliased — this is OK."""
    kernel_dir = tmp_path / "pipeline_kernel"
    kernel_dir.mkdir()
    (kernel_dir / "__init__.py").touch()
    (kernel_dir / "sizing.py").write_text("x = 1", encoding="utf-8")

    original_import = mod.importlib.import_module

    def fake_import(name: str, *args, **kwargs):
        if name == "renquant_pipeline.kernel":
            return SimpleNamespace(
                __file__=str(kernel_dir / "__init__.py"),
                NON_OWNED_KERNEL_STEMS=frozenset(),
                OWNED_KERNEL_STEMS=frozenset({"sizing"}),
            )
        if name == "renquant_pipeline.kernel.sizing":
            return SimpleNamespace(x=1)
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(mod.importlib, "import_module", fake_import)
    monkeypatch.setattr(mod, "_force_alias", lambda a, t, al: al.append(f"{a}<-{t}"))
    monkeypatch.setattr(mod, "resolve_subrepo_src_roots", lambda **kw: ([], []))
    monkeypatch.setattr(mod, "enforce_or_warn", lambda issues: None)
    monkeypatch.setattr(mod, "strict_clean_enabled", lambda: False)

    aliased = mod.bootstrap_multirepo(repo_root=tmp_path / "RenQuant")
    assert "kernel.sizing" in aliased


def test_bootstrap_reports_all_declared_failures(tmp_path: Path, monkeypatch) -> None:
    """When multiple owned modules fail, all are reported in the error."""
    kernel_dir = tmp_path / "pipeline_kernel"
    kernel_dir.mkdir()
    (kernel_dir / "__init__.py").touch()
    (kernel_dir / "exits.py").write_text("x = 1", encoding="utf-8")
    (kernel_dir / "sizing.py").write_text("x = 1", encoding="utf-8")

    original_import = mod.importlib.import_module

    def fake_import(name: str, *args, **kwargs):
        if name == "renquant_pipeline.kernel":
            return SimpleNamespace(
                __file__=str(kernel_dir / "__init__.py"),
                NON_OWNED_KERNEL_STEMS=frozenset(),
            )
        if name.startswith("renquant_pipeline.kernel."):
            raise ImportError(f"broken: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(mod.importlib, "import_module", fake_import)
    monkeypatch.setattr(mod, "_force_alias", lambda a, t, al: al.append(f"{a}<-{t}"))
    monkeypatch.setattr(mod, "resolve_subrepo_src_roots", lambda **kw: ([], []))
    monkeypatch.setattr(mod, "enforce_or_warn", lambda issues: None)
    monkeypatch.setattr(mod, "strict_clean_enabled", lambda: False)

    with pytest.raises(RuntimeError, match="2 pipeline-owned kernel") as exc_info:
        mod.bootstrap_multirepo(repo_root=tmp_path / "RenQuant")
    assert "exits" in str(exc_info.value)
    assert "sizing" in str(exc_info.value)


def test_bootstrap_fails_when_pipeline_missing_ownership_contract(tmp_path: Path, monkeypatch) -> None:
    """Pipeline kernel without NON_OWNED_KERNEL_STEMS must fail closed."""
    kernel_dir = tmp_path / "pipeline_kernel"
    kernel_dir.mkdir()
    (kernel_dir / "__init__.py").touch()
    (kernel_dir / "sizing.py").write_text("x = 1", encoding="utf-8")

    original_import = mod.importlib.import_module

    def fake_import(name: str, *args, **kwargs):
        if name == "renquant_pipeline.kernel":
            return SimpleNamespace(__file__=str(kernel_dir / "__init__.py"))
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(mod.importlib, "import_module", fake_import)
    monkeypatch.setattr(mod, "resolve_subrepo_src_roots", lambda **kw: ([], []))
    monkeypatch.setattr(mod, "enforce_or_warn", lambda issues: None)
    monkeypatch.setattr(mod, "strict_clean_enabled", lambda: False)

    with pytest.raises(RuntimeError, match="NON_OWNED_KERNEL_STEMS"):
        mod.bootstrap_multirepo(repo_root=tmp_path / "RenQuant")


def test_bootstrap_non_owned_stem_skips_pipeline_uses_alias(tmp_path: Path, monkeypatch) -> None:
    """A non-owned stem's pipeline import is skipped; the alias target is used instead."""
    kernel_dir = tmp_path / "pipeline_kernel"
    kernel_dir.mkdir()
    (kernel_dir / "__init__.py").touch()
    (kernel_dir / "sizing.py").write_text("x = 1", encoding="utf-8")
    meta_dir = kernel_dir / "meta_label"
    meta_dir.mkdir()
    (meta_dir / "__init__.py").write_text("raise ImportError('partial')", encoding="utf-8")

    original_import = mod.importlib.import_module
    alias_calls: list[tuple[str, str]] = []

    def fake_import(name: str, *args, **kwargs):
        if name == "renquant_pipeline.kernel":
            return SimpleNamespace(
                __file__=str(kernel_dir / "__init__.py"),
                NON_OWNED_KERNEL_STEMS=frozenset({"meta_label"}),
                OWNED_KERNEL_STEMS=frozenset({"sizing"}),
            )
        if name == "renquant_pipeline.kernel.sizing":
            return SimpleNamespace(x=1)
        if name == "renquant_pipeline.kernel.meta_label":
            raise ImportError("partial lift only")
        return original_import(name, *args, **kwargs)

    def tracking_alias(alias, target, al):
        alias_calls.append((alias, target))
        al.append(f"{alias}<-{target}")

    monkeypatch.setattr(mod.importlib, "import_module", fake_import)
    monkeypatch.setattr(mod, "_force_alias", tracking_alias)
    monkeypatch.setattr(mod, "resolve_subrepo_src_roots", lambda **kw: ([], []))
    monkeypatch.setattr(mod, "enforce_or_warn", lambda issues: None)
    monkeypatch.setattr(mod, "strict_clean_enabled", lambda: False)

    aliased = mod.bootstrap_multirepo(repo_root=tmp_path / "RenQuant")
    assert "kernel.sizing" in aliased
    assert any(a == "kernel.meta_label" and "backtesting" in t for a, t in alias_calls)
    # The pipeline's own modules import non-owned stems under the PIPELINE
    # namespace (pp_inference lazily imports renquant_pipeline.kernel.
    # meta_label.task_meta_label_veto, which exists only in the authoritative
    # backtesting copy). Regression: 2026-07-16, first post-F-8 daily died
    # mid-run because only kernel.meta_label was aliased.
    assert any(
        a == "renquant_pipeline.kernel.meta_label" and "backtesting" in t
        for a, t in alias_calls
    )


def test_bootstrap_non_owned_stem_alias_target_fails_closed(tmp_path: Path, monkeypatch) -> None:
    """If the alias target for a non-owned stem fails to import, the run fails closed."""
    kernel_dir = tmp_path / "pipeline_kernel"
    kernel_dir.mkdir()
    (kernel_dir / "__init__.py").touch()
    (kernel_dir / "sizing.py").write_text("x = 1", encoding="utf-8")
    meta_dir = kernel_dir / "meta_label"
    meta_dir.mkdir()
    (meta_dir / "__init__.py").touch()

    original_import = mod.importlib.import_module

    def fake_import(name: str, *args, **kwargs):
        if name == "renquant_pipeline.kernel":
            return SimpleNamespace(
                __file__=str(kernel_dir / "__init__.py"),
                NON_OWNED_KERNEL_STEMS=frozenset({"meta_label"}),
                OWNED_KERNEL_STEMS=frozenset({"sizing"}),
            )
        if name == "renquant_pipeline.kernel.sizing":
            return SimpleNamespace(x=1)
        if name == "renquant_backtesting.meta_label":
            raise ImportError("backtesting not available")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(mod.importlib, "import_module", fake_import)
    monkeypatch.setattr(mod, "resolve_subrepo_src_roots", lambda **kw: ([], []))
    monkeypatch.setattr(mod, "enforce_or_warn", lambda issues: None)
    monkeypatch.setattr(mod, "strict_clean_enabled", lambda: False)

    with pytest.raises(RuntimeError, match="critical multirepo module.*backtesting"):
        mod.bootstrap_multirepo(repo_root=tmp_path / "RenQuant")


def test_bootstrap_fails_when_owned_stems_missing(tmp_path: Path, monkeypatch) -> None:
    """Pipeline without OWNED_KERNEL_STEMS must fail closed immediately."""
    kernel_dir = tmp_path / "pipeline_kernel"
    kernel_dir.mkdir()
    (kernel_dir / "__init__.py").touch()

    original_import = mod.importlib.import_module

    def fake_import(name: str, *args, **kwargs):
        if name == "renquant_pipeline.kernel":
            return SimpleNamespace(
                __file__=str(kernel_dir / "__init__.py"),
                NON_OWNED_KERNEL_STEMS=frozenset(),
            )
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(mod.importlib, "import_module", fake_import)
    monkeypatch.setattr(mod, "_force_alias", lambda a, t, al: al.append(f"{a}<-{t}"))
    monkeypatch.setattr(mod, "resolve_subrepo_src_roots", lambda **kw: ([], []))
    monkeypatch.setattr(mod, "enforce_or_warn", lambda issues: None)
    monkeypatch.setattr(mod, "strict_clean_enabled", lambda: False)

    with pytest.raises(RuntimeError, match="OWNED_KERNEL_STEMS.*pin a pipeline"):
        mod.bootstrap_multirepo(repo_root=tmp_path / "RenQuant")


def test_bootstrap_fails_closed_on_missing_declared_owned_stem(
    tmp_path: Path, monkeypatch
) -> None:
    """The real path-identity/sanity check: bind the discovered module
    inventory to the pinned package's own declared OWNED_KERNEL_STEMS,
    instead of an arbitrary count (Codex, PR #514 round 2 review: "do not
    use the arbitrary _MIN_PIPELINE_KERNEL_MODULES = 10 as a path-identity
    control. It permits any wrong directory with ten importable files and
    will become stale when the package layout changes. Bind the discovered
    module inventory to the pinned package contract instead."). A kernel
    dir missing modules the pinned pipeline declares it owns must fail
    closed, naming the missing stems -- this is what actually catches a
    wrong/incomplete checkout tied to the real pinned contract, not a raw
    count that would equally miss a wrong directory with ten unrelated
    importable files or hard-fail a right directory that happens to have
    fewer than ten."""
    kernel_dir = tmp_path / "pipeline_kernel"
    kernel_dir.mkdir()
    (kernel_dir / "__init__.py").touch()
    # Wrong/incomplete checkout: only 'sizing' physically present, even
    # though the pinned pipeline declares 3 stems as owned.
    (kernel_dir / "sizing.py").write_text("x = 1", encoding="utf-8")

    original_import = mod.importlib.import_module

    def fake_import(name: str, *args, **kwargs):
        if name == "renquant_pipeline.kernel":
            return SimpleNamespace(
                __file__=str(kernel_dir / "__init__.py"),
                NON_OWNED_KERNEL_STEMS=frozenset(),
                OWNED_KERNEL_STEMS=frozenset({"sizing", "exits", "kelly"}),
            )
        if name == "renquant_pipeline.kernel.sizing":
            return SimpleNamespace(x=1)
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(mod.importlib, "import_module", fake_import)
    monkeypatch.setattr(mod, "resolve_subrepo_src_roots", lambda **kw: ([], []))
    monkeypatch.setattr(mod, "enforce_or_warn", lambda issues: None)
    monkeypatch.setattr(mod, "strict_clean_enabled", lambda: False)

    with pytest.raises(RuntimeError, match="OWNED_KERNEL_STEMS") as exc_info:
        mod.bootstrap_multirepo(repo_root=tmp_path / "RenQuant")
    message = str(exc_info.value)
    assert "exits" in message
    assert "kelly" in message
    # The stem that WAS found (sizing) must not be named as missing.
    assert "sizing" not in message


def test_bootstrap_allows_complete_declared_owned_inventory(
    tmp_path: Path, monkeypatch
) -> None:
    """The structural check passes silently when the discovered directory
    covers everything the pinned pipeline declares owned -- proving this is
    a real equivalence check, not just a stricter failure mode."""
    kernel_dir = tmp_path / "pipeline_kernel"
    kernel_dir.mkdir()
    (kernel_dir / "__init__.py").touch()
    (kernel_dir / "sizing.py").write_text("x = 1", encoding="utf-8")
    (kernel_dir / "exits.py").write_text("x = 1", encoding="utf-8")

    original_import = mod.importlib.import_module

    def fake_import(name: str, *args, **kwargs):
        if name == "renquant_pipeline.kernel":
            return SimpleNamespace(
                __file__=str(kernel_dir / "__init__.py"),
                NON_OWNED_KERNEL_STEMS=frozenset(),
                OWNED_KERNEL_STEMS=frozenset({"sizing", "exits"}),
            )
        if name in {
            "renquant_pipeline.kernel.sizing",
            "renquant_pipeline.kernel.exits",
        }:
            return SimpleNamespace(x=1)
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(mod.importlib, "import_module", fake_import)
    monkeypatch.setattr(mod, "_force_alias", lambda a, t, al: al.append(f"{a}<-{t}"))
    monkeypatch.setattr(mod, "resolve_subrepo_src_roots", lambda **kw: ([], []))
    monkeypatch.setattr(mod, "enforce_or_warn", lambda issues: None)
    monkeypatch.setattr(mod, "strict_clean_enabled", lambda: False)

    aliased = mod.bootstrap_multirepo(repo_root=tmp_path / "RenQuant")
    assert "kernel.sizing" in aliased
    assert "kernel.exits" in aliased


def test_bootstrap_fails_on_uncovered_non_owned_stem(tmp_path: Path, monkeypatch) -> None:
    """Pipeline declares a non-owned stem that orchestrator has no alias target for."""
    kernel_dir = tmp_path / "pipeline_kernel"
    kernel_dir.mkdir()
    (kernel_dir / "__init__.py").touch()
    (kernel_dir / "sizing.py").write_text("x = 1", encoding="utf-8")

    original_import = mod.importlib.import_module

    def fake_import(name: str, *args, **kwargs):
        if name == "renquant_pipeline.kernel":
            return SimpleNamespace(
                __file__=str(kernel_dir / "__init__.py"),
                NON_OWNED_KERNEL_STEMS=frozenset({"unknown_module"}),
            )
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(mod.importlib, "import_module", fake_import)
    monkeypatch.setattr(mod, "resolve_subrepo_src_roots", lambda **kw: ([], []))
    monkeypatch.setattr(mod, "enforce_or_warn", lambda issues: None)
    monkeypatch.setattr(mod, "strict_clean_enabled", lambda: False)

    with pytest.raises(RuntimeError, match="no alias target.*unknown_module|unknown_module.*no alias target"):
        mod.bootstrap_multirepo(repo_root=tmp_path / "RenQuant")


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
