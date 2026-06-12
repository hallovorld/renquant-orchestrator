"""Machine-readable engineering census for the multirepo migration.

The research docs need stable numbers, but hand grep counts drift quickly.
This module produces the counts from source/config files with explicit paths,
repo SHAs, and line-level evidence.
"""
from __future__ import annotations

import ast
import datetime as dt
import json
import subprocess
from pathlib import Path
from typing import Any, Iterable

from .runtime_paths import default_github_root


BUY_BLOCKED_WRITER_KIND = "buy_blocked_true_writers_ast"


def build_engineering_census(
    *,
    github_root: Path | None = None,
    pipeline_src: Path | None = None,
    strategy_configs: Iterable[Path] | None = None,
    expect_buy_blocked_writers: int | None = None,
) -> dict[str, Any]:
    """Return the current engineering census as a JSON-serializable dict."""
    github = (github_root or default_github_root()).expanduser().resolve()
    pipeline_src = (pipeline_src or github / "renquant-pipeline" / "src").expanduser().resolve()
    configs = list(strategy_configs or _default_strategy_configs(github))

    payload: dict[str, Any] = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "github_root": str(github),
        "repos": {
            "orchestrator": _repo_metadata(Path(__file__).resolve().parents[2]),
            "pipeline": _repo_metadata(_repo_from_src(pipeline_src)),
            "strategy": _repo_metadata(github / "renquant-strategy-104"),
            "umbrella": _repo_metadata(github / "RenQuant"),
        },
        "files": _file_census(github),
        "strategy_configs": [_strategy_config_census(path) for path in configs],
        "gate_writers": _buy_blocked_writer_census(pipeline_src),
        "expectation_failures": [],
    }

    if expect_buy_blocked_writers is not None:
        actual = payload["gate_writers"]["count"]
        if actual != expect_buy_blocked_writers:
            payload["expectation_failures"].append(
                {
                    "metric": BUY_BLOCKED_WRITER_KIND,
                    "expected": expect_buy_blocked_writers,
                    "actual": actual,
                }
            )

    missing_required = []
    if not pipeline_src.is_dir():
        missing_required.append({"kind": "pipeline_src", "path": str(pipeline_src)})
    if not any(item["exists"] for item in payload["strategy_configs"]):
        missing_required.append(
            {"kind": "strategy_config", "path": [str(path) for path in configs]}
        )
    payload["missing_required"] = missing_required
    payload["ok"] = not missing_required and not payload["expectation_failures"]
    return payload


def _default_strategy_configs(github: Path) -> tuple[Path, Path]:
    return (
        github / "renquant-strategy-104" / "configs" / "strategy_config.json",
        github / "RenQuant" / "backtesting" / "renquant_104" / "strategy_config.json",
    )


def _repo_from_src(src: Path) -> Path:
    return src.parent if src.name == "src" else src


def _repo_metadata(path: Path) -> dict[str, Any]:
    exists = (path / ".git").exists()
    meta: dict[str, Any] = {"path": str(path), "exists": exists}
    if not exists:
        return meta
    meta["head"] = _git(path, "rev-parse", "HEAD")
    meta["head_short"] = _git(path, "rev-parse", "--short", "HEAD")
    meta["dirty"] = bool(_git(path, "status", "--porcelain"))
    return meta


def _git(repo: Path, *args: str) -> str | None:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.stdout.strip() if proc.returncode == 0 else None


def _file_census(github: Path) -> list[dict[str, Any]]:
    targets = [
        (
            "pipeline_job_panel_scoring",
            github
            / "renquant-pipeline"
            / "src"
            / "renquant_pipeline"
            / "kernel"
            / "panel_pipeline"
            / "job_panel_scoring.py",
        ),
        (
            "umbrella_runner",
            github / "RenQuant" / "backtesting" / "renquant_104" / "adapters" / "runner.py",
        ),
        (
            "umbrella_wf_gate",
            github / "RenQuant" / "scripts" / "run_wf_gate.py",
        ),
    ]
    return [_line_census(name, path) for name, path in targets]


def _line_census(name: str, path: Path) -> dict[str, Any]:
    item: dict[str, Any] = {"id": name, "path": str(path), "exists": path.exists()}
    if path.exists():
        item["lines"] = len(path.read_text(encoding="utf-8", errors="replace").splitlines())
    return item


def _strategy_config_census(path: Path) -> dict[str, Any]:
    item: dict[str, Any] = {"path": str(path), "exists": path.exists()}
    if not path.exists():
        return item
    text = path.read_text(encoding="utf-8")
    item["lines"] = len(text.splitlines())
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        item.update({"valid_json": False, "error": str(exc)})
        return item
    counts = _count_json_keys(data)
    item.update({"valid_json": True, **counts})
    return item


def _count_json_keys(data: Any) -> dict[str, int]:
    counts = {
        "recursive_keys": 0,
        "underscore_keys": 0,
        "contains_reason_keys": 0,
        "contains_note_keys": 0,
    }

    def walk(obj: Any) -> None:
        if isinstance(obj, dict):
            for key, value in obj.items():
                key_s = str(key)
                counts["recursive_keys"] += 1
                if key_s.startswith("_"):
                    counts["underscore_keys"] += 1
                if "reason" in key_s:
                    counts["contains_reason_keys"] += 1
                if "note" in key_s:
                    counts["contains_note_keys"] += 1
                walk(value)
        elif isinstance(obj, list):
            for value in obj:
                walk(value)

    walk(data)
    return counts


def _buy_blocked_writer_census(pipeline_src: Path) -> dict[str, Any]:
    writers: list[dict[str, Any]] = []
    if pipeline_src.is_dir():
        for path in sorted(pipeline_src.rglob("*.py")):
            writers.extend(_buy_blocked_writers_in_file(path, pipeline_src))
    return {
        "kind": BUY_BLOCKED_WRITER_KIND,
        "pipeline_src": str(pipeline_src),
        "method": "python_ast_assign_true_or_setattr_true",
        "count": len(writers),
        "writers": writers,
    }


def _buy_blocked_writers_in_file(path: Path, root: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return [
            {
                "file": str(path.relative_to(root)),
                "line": exc.lineno,
                "kind": "syntax_error",
                "source": str(exc),
            }
        ]
    lines = text.splitlines()
    out: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        kind = _buy_blocked_write_kind(node)
        if kind is None:
            continue
        lineno = getattr(node, "lineno", 0)
        out.append(
            {
                "file": str(path.relative_to(root)),
                "line": lineno,
                "kind": kind,
                "source": lines[lineno - 1].strip() if 0 < lineno <= len(lines) else "",
            }
        )
    return sorted(out, key=lambda item: (item["file"], item["line"], item["kind"]))


def _buy_blocked_write_kind(node: ast.AST) -> str | None:
    if isinstance(node, ast.Assign):
        if _is_true_constant(node.value) and any(_is_buy_blocked_attr(t) for t in node.targets):
            return "attribute_assign_true"
    if isinstance(node, ast.AnnAssign):
        if _is_true_constant(node.value) and _is_buy_blocked_attr(node.target):
            return "attribute_assign_true"
    if isinstance(node, ast.Call):
        if (
            isinstance(node.func, ast.Name)
            and node.func.id == "setattr"
            and len(node.args) >= 3
            and _is_string_constant(node.args[1], "buy_blocked")
            and _is_true_constant(node.args[2])
        ):
            return "setattr_true"
    return None


def _is_buy_blocked_attr(node: ast.AST) -> bool:
    return isinstance(node, ast.Attribute) and node.attr == "buy_blocked"


def _is_true_constant(node: ast.AST | None) -> bool:
    return isinstance(node, ast.Constant) and node.value is True


def _is_string_constant(node: ast.AST, value: str) -> bool:
    return isinstance(node, ast.Constant) and node.value == value
