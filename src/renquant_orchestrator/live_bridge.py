"""Bridge scheduled live.runner invocations through pinned subrepos."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

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

    aliased: list[str] = []
    for entry in sorted(kernel_dir.iterdir()):
        stem = entry.stem if entry.suffix == ".py" else entry.name
        if stem in {"__init__", "__pycache__"} or stem.startswith("."):
            continue
        if entry.suffix not in {".py", ""}:
            continue
        modname = f"kernel.{stem}"
        try:
            mod = importlib.import_module(f"renquant_pipeline.kernel.{stem}")
        except Exception:
            continue
        sys.modules[modname] = mod
        aliased.append(modname)

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

    if _arg_value(runner_argv, "--strategy") is None:
        runner_argv = ["--strategy", "renquant_104"] + runner_argv
    runner_argv = _with_pinned_strategy_config(runner_argv, repo_root=repo_root)
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
