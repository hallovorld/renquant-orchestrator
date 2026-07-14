"""Bridge scheduled live.runner invocations through pinned subrepos."""
from __future__ import annotations

import importlib
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .runtime_paths import (
    default_github_root,
    default_repo_root,
    enforce_or_warn,
    resolve_subrepo_root,
    resolve_subrepo_src_roots,
    strict_clean_enabled,
)


GITHUB = default_github_root()
DEFAULT_REPO_ROOT = default_repo_root()
DEFAULT_PIN_SRCS = [
    "renquant-common",
    "renquant-base-data",
    "renquant-artifacts",
    "renquant-strategy-104",
    "renquant-model",
    "renquant-pipeline",
    "renquant-execution",
    "renquant-backtesting",
]
BRIDGE_BUNDLE_OUTPUT_FLAG = "--bridge-bundle-output"
NATIVE_INFERENCE_PAYLOAD_OUTPUT_FLAG = "--native-inference-payload-output"
ALPACA_BROKERS = {"alpaca", "alpaca-paper", "alpaca_shadow", "readonly-alpaca"}
BRIDGE_NATIVE_INFERENCE_PRODUCER = "live_runner_bridge_hook"
CommitHook = Callable[[Any, Any], None]

# Minimum number of pipeline kernel modules that must alias successfully.
# Guards against an empty/wrong pipeline kernel directory silently producing
# zero aliases (e.g. wrong checkout, path misconfiguration).
_MIN_PIPELINE_KERNEL_MODULES = 10


def _arg_value(argv: list[str], flag: str, default: str | None = None) -> str | None:
    prefix = flag + "="
    for idx, arg in enumerate(argv):
        if arg == flag and idx + 1 < len(argv):
            return argv[idx + 1]
        if arg.startswith(prefix):
            return arg[len(prefix) :]
    return default


def _without_arg(argv: list[str], flag: str) -> list[str]:
    out: list[str] = []
    skip = False
    prefix = flag + "="
    for arg in argv:
        if skip:
            skip = False
            continue
        if arg == flag:
            skip = True
            continue
        if arg.startswith(prefix):
            continue
        out.append(arg)
    return out


def _strategy_config_name(argv: list[str]) -> str:
    explicit = _arg_value(argv, "--strategy-config-name")
    if explicit:
        return explicit
    strategy = _arg_value(argv, "--strategy", "renquant_104")
    broker = _arg_value(argv, "--broker", "paper")
    if strategy == "renquant_104" and broker == "readonly-alpaca":
        return "strategy_config.shadow.json"
    return "strategy_config.json"


def _missing_alpaca_credentials(argv: list[str]) -> list[str]:
    broker = _arg_value(argv, "--broker", "paper")
    if broker not in ALPACA_BROKERS:
        return []
    required = ("ALPACA_API_KEY", "ALPACA_SECRET_KEY")
    return [name for name in required if not os.environ.get(name)]


def _with_pinned_strategy_config(
    argv: list[str],
    *,
    repo_root: Path = DEFAULT_REPO_ROOT,
) -> list[str]:
    """Route renquant_104 config reads to the pinned strategy subrepo."""
    if _arg_value(argv, "--strategy-config-path"):
        return argv
    if _arg_value(argv, "--strategy", "renquant_104") != "renquant_104":
        return argv
    config_name = _strategy_config_name(argv)
    cfg_path = (
        resolve_subrepo_root(repo_root)
        / "renquant-strategy-104"
        / "configs"
        / config_name
    )
    return _without_arg(argv, "--strategy-config-name") + [
        "--strategy-config-path",
        str(cfg_path),
    ]


def _install_bridge_bundle_capture(
    output_path: str | Path,
    *,
    metadata: dict[str, object] | None = None,
) -> None:
    """Capture committed legacy live.runner contexts as bridge bundles."""
    from .bridge_live_bundle import write_bridge_live_bundle

    def write_bundle(_adapter: Any, ctx: Any) -> None:
        write_bridge_live_bundle(ctx, output_path, metadata=metadata)

    _install_runner_commit_hook(write_bundle, timing="after")


def _write_bridge_native_inference_payload(
    ctx: Any,
    output_path: str | Path,
    *,
    metadata: dict[str, Any],
) -> None:
    """Capture the live context after inference and before execution commit."""
    import json

    from renquant_pipeline import runtime_inference_payload_from_live_context

    payload = runtime_inference_payload_from_live_context(ctx)
    payload_metadata = dict(payload.get("metadata") or {})
    payload_metadata["native_inference_producer"] = {
        "source": BRIDGE_NATIVE_INFERENCE_PRODUCER,
        **metadata,
    }
    payload["metadata"] = payload_metadata

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _install_native_inference_payload_capture(
    output_path: str | Path,
    *,
    metadata: dict[str, Any],
) -> None:
    """Capture the live context after inference and before execution commit."""

    def write_payload(_adapter: Any, ctx: Any) -> None:
        _write_bridge_native_inference_payload(ctx, output_path, metadata=metadata)

    _install_runner_commit_hook(write_payload, timing="before")


def _runner_adapter_cls() -> type:
    adapters_runner = importlib.import_module("adapters.runner")
    return getattr(adapters_runner, "RunnerAdapter")


def _reset_runner_commit_hooks() -> None:
    adapter_cls = _runner_adapter_cls()
    original = getattr(adapter_cls, "_renquant_original_commit", None)
    if original is not None:
        adapter_cls.commit = original
    setattr(adapter_cls, "_renquant_commit_hooks", {"before": [], "after": []})
    setattr(adapter_cls, "_renquant_commit_hook_wrapper_installed", False)


def _install_runner_commit_hook(
    hook: CommitHook,
    *,
    timing: str,
) -> None:
    if timing not in {"before", "after"}:
        raise ValueError("timing must be 'before' or 'after'")
    adapter_cls = _runner_adapter_cls()
    hooks = getattr(adapter_cls, "_renquant_commit_hooks", None)
    if hooks is None:
        hooks = {"before": [], "after": []}
        setattr(adapter_cls, "_renquant_commit_hooks", hooks)

    original = getattr(adapter_cls, "_renquant_original_commit", None)
    if original is None:
        original = adapter_cls.commit
        setattr(adapter_cls, "_renquant_original_commit", original)

    if not getattr(adapter_cls, "_renquant_commit_hook_wrapper_installed", False):

        def commit_with_hooks(self, ctx):  # noqa: ANN001, ANN202
            for before_hook in hooks["before"]:
                before_hook(self, ctx)
            result = original(self, ctx)
            for after_hook in hooks["after"]:
                after_hook(self, ctx)
            return result

        adapter_cls.commit = commit_with_hooks
        setattr(adapter_cls, "_renquant_commit_hook_wrapper_installed", True)
    hooks[timing].append(hook)


def _force_alias(alias: str, target: str, aliased: list[str]) -> None:
    try:
        mod = importlib.import_module(target)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"critical multirepo module unavailable: {target}") from exc
    sys.modules[alias] = mod
    aliased.append(f"{alias}<-{target}")


def _subrepo_src_roots(
    *,
    repo_root: Path = DEFAULT_REPO_ROOT,
    lock_file: Path | None = None,
    siblings: Path | None = None,
    pin_srcs: list[str] | None = None,
) -> tuple[list[Path], list[str]]:
    roots, issues = resolve_subrepo_src_roots(
        lock_file=lock_file or repo_root / "subrepos.lock.json",
        names=pin_srcs or DEFAULT_PIN_SRCS,
        siblings=siblings or repo_root.parent,
        root_override=str(resolve_subrepo_root(repo_root)),
        check_dirty=strict_clean_enabled(),
    )
    missing = [issue.repo for issue in issues if issue.reason == "missing local src root"]
    return roots, missing


def bootstrap_multirepo(
    *,
    repo_root: Path = DEFAULT_REPO_ROOT,
    lock_file: Path | None = None,
    siblings: Path | None = None,
    pin_srcs: list[str] | None = None,
) -> list[str]:
    """Put pinned subrepos on sys.path and alias lifted runtime modules."""
    strategy_dir = repo_root / "backtesting" / "renquant_104"
    for path in (str(repo_root), str(strategy_dir)):
        if path not in sys.path:
            sys.path.insert(0, path)

    src_roots, pin_issues = resolve_subrepo_src_roots(
        lock_file=lock_file or repo_root / "subrepos.lock.json",
        names=pin_srcs or DEFAULT_PIN_SRCS,
        siblings=siblings or repo_root.parent,
        root_override=str(resolve_subrepo_root(repo_root)),
        check_dirty=strict_clean_enabled(),
    )
    enforce_or_warn(pin_issues)
    for src in src_roots:
        if str(src) not in sys.path:
            sys.path.append(str(src))

    pipeline_kernel = importlib.import_module("renquant_pipeline.kernel")
    kernel_dir = Path(pipeline_kernel.__file__).resolve().parent

    # The pipeline kernel directory IS the manifest: every .py file and
    # sub-package present there is a declared module that MUST import
    # successfully.  Modules that exist only in the umbrella kernel (never
    # lifted) simply don't appear in this directory, so no allowlist is needed.
    # If a declared module fails to import (syntax error, missing dep, etc.),
    # the run fails closed — the umbrella copy must never silently substitute.
    declared_stems: list[str] = []
    for entry in sorted(kernel_dir.iterdir()):
        stem = entry.stem if entry.suffix == ".py" else entry.name
        if stem in {"__init__", "__pycache__"} or stem.startswith("."):
            continue
        if entry.suffix not in {".py", ""}:
            continue
        declared_stems.append(stem)

    aliased: list[str] = []
    failed: list[tuple[str, Exception]] = []
    for stem in declared_stems:
        modname = f"kernel.{stem}"
        try:
            pipeline_mod = importlib.import_module(f"renquant_pipeline.kernel.{stem}")
        except Exception as exc:  # noqa: BLE001
            failed.append((stem, exc))
            continue
        sys.modules[modname] = pipeline_mod
        aliased.append(modname)

    if failed:
        details = "; ".join(f"{s}: {e}" for s, e in failed)
        raise RuntimeError(
            f"[multirepo] fail-closed: {len(failed)} pipeline kernel module(s) "
            f"declared in {kernel_dir} failed to import: {details}"
        )

    if len(aliased) < _MIN_PIPELINE_KERNEL_MODULES:
        raise RuntimeError(
            f"[multirepo] fail-closed: only {len(aliased)} pipeline kernel modules "
            f"aliased (minimum {_MIN_PIPELINE_KERNEL_MODULES}); possible pipeline "
            f"checkout/path misconfiguration"
        )

    # Critical production modules must not silently fall back to umbrella. If
    # one import fails, the scheduled multirepo run is not actually using the
    # pinned production path and should fail closed.
    _force_alias("kernel.preflight", "renquant_pipeline.kernel.preflight", aliased)
    _force_alias("kernel.panel_pipeline", "renquant_pipeline.kernel.panel_pipeline", aliased)
    _force_alias(
        "renquant_pipeline.kernel.meta_label",
        "renquant_backtesting.meta_label",
        aliased,
    )
    _force_alias(
        "renquant_pipeline.panel_scoring",
        "renquant_pipeline.kernel.panel_pipeline.job_panel_scoring",
        aliased,
    )
    return aliased


def run_bridge(
    argv: list[str] | None = None,
    *,
    mode: str = "live",
    repo_root: Path = DEFAULT_REPO_ROOT,
) -> int:
    """Bootstrap multirepo runtime, then hand off to umbrella live.runner."""
    runner_argv = list(sys.argv[1:] if argv is None else argv)
    missing_creds = _missing_alpaca_credentials(runner_argv)
    if missing_creds:
        sys.stderr.write(
            "live bridge preflight failed: broker requires Alpaca credentials; "
            f"missing {', '.join(missing_creds)}.\n"
        )
        return 2
    bridge_bundle_output = _arg_value(runner_argv, BRIDGE_BUNDLE_OUTPUT_FLAG)
    if bridge_bundle_output:
        runner_argv = _without_arg(runner_argv, BRIDGE_BUNDLE_OUTPUT_FLAG)
    native_inference_output = _arg_value(runner_argv, NATIVE_INFERENCE_PAYLOAD_OUTPUT_FLAG)
    if native_inference_output:
        runner_argv = _without_arg(runner_argv, NATIVE_INFERENCE_PAYLOAD_OUTPUT_FLAG)
    aliased = bootstrap_multirepo(repo_root=repo_root)
    if mode == "daily":
        sys.stderr.write(
            f"[multirepo] routed {len(aliased)} kernel modules to renquant-pipeline; "
            "preflight/panel_pipeline/panel_scoring resolve from pinned subrepos; "
            "meta_label resolves from renquant-backtesting when available.\n"
        )
    else:
        sys.stderr.write(
            f"[multirepo] routed {len(aliased)} lifted modules through sibling subrepos; "
            "live.runner remains the execution handoff.\n"
        )
    _reset_runner_commit_hooks()

    if _arg_value(runner_argv, "--strategy") is None:
        runner_argv = ["--strategy", "renquant_104"] + runner_argv
    runner_argv = _with_pinned_strategy_config(runner_argv, repo_root=repo_root)
    if native_inference_output:
        _install_native_inference_payload_capture(
            native_inference_output,
            metadata={
                "bridge_mode": mode,
                "repo_root": str(repo_root),
                "runner_args": list(runner_argv),
            },
        )
    if bridge_bundle_output:
        _install_bridge_bundle_capture(
            bridge_bundle_output,
            metadata={
                "bridge_mode": mode,
                "repo_root": str(repo_root),
                "runner_args": list(runner_argv),
            },
        )
    sys.argv = [sys.argv[0]] + runner_argv
    runner = importlib.import_module("live.runner")
    return int(runner.main() or 0)


def main(
    argv: list[str] | None = None,
    *,
    mode: str = "live",
    repo_root: Path = DEFAULT_REPO_ROOT,
) -> int:
    return run_bridge(argv, mode=mode, repo_root=repo_root)


if __name__ == "__main__":
    raise SystemExit(main())
