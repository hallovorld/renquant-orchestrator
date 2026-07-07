"""Bundle subrepo source code for cloud container image."""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

SUBREPO_NAMES = (
    "renquant-common",
    "renquant-base-data",
    "renquant-artifacts",
    "renquant-model",
    "renquant-pipeline",
    "renquant-execution",
    "renquant-strategy-104",
    "renquant-backtesting",
    "renquant-orchestrator",
)

STRIP_DIRS = {".git", "__pycache__", "tests", "test", ".mypy_cache", ".pytest_cache"}
STRIP_EXTS = {".pyc", ".pyo"}


def bundle_subrepos(
    subrepo_root: Path,
    strategy_dir: Path,
    output_dir: Path,
) -> dict[str, str]:
    """Copy subrepo src/, kernel/, and sim/ into output_dir for container build.

    Returns a manifest: {relative_path: sha256} for every bundled file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, str] = {}

    subrepos_out = output_dir / "subrepos"
    for repo_name in SUBREPO_NAMES:
        src = subrepo_root / repo_name / "src"
        if not src.is_dir():
            continue
        dst = subrepos_out / repo_name / "src"
        _copy_tree(src, dst, manifest, f"subrepos/{repo_name}/src")

    for subdir_name in ("kernel", "sim"):
        src = strategy_dir / subdir_name
        if src.is_dir():
            dst = output_dir / subdir_name
            _copy_tree(src, dst, manifest, subdir_name)

    scripts_dir = strategy_dir.parent.parent / "scripts"
    subrepo_paths = scripts_dir / "subrepo_paths.py"
    if subrepo_paths.is_file():
        dst = output_dir / "scripts" / "subrepo_paths.py"
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(subrepo_paths, dst)
        manifest["scripts/subrepo_paths.py"] = _sha256(subrepo_paths)

    manifest_path = output_dir / "bundle_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True))
    return manifest


def _copy_tree(src: Path, dst: Path, manifest: dict[str, str], prefix: str) -> None:
    for f in sorted(src.rglob("*")):
        if f.is_dir():
            continue
        if any(p in STRIP_DIRS for p in f.parts):
            continue
        if f.suffix in STRIP_EXTS:
            continue
        rel = f.relative_to(src)
        out = dst / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, out)
        manifest[f"{prefix}/{rel}"] = _sha256(f)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compute_bundle_fingerprint(manifest: dict[str, str]) -> str:
    canonical = json.dumps(manifest, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()
