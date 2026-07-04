"""Evidence manifests: content-hash stamping + verified re-read.

Mechanizes the S-REL §3.1 hardened evidence-JSON convention: every evidence
file stamps the content sha256 of every input it consumed, the generating
code's git SHA (+ dirty flag), the config/spec hashes, and timestamps — so a
verifier can prove *which inputs and which code* produced a given evidence
file without forensic reconstruction. The loader re-verifies input hashes on
re-read.

Provenance of the pattern: scripts/c3_residual_momentum.py (sha256_file,
canonical panel hashing, worktree-safe HEAD resolution), scripts/
msig_c2_quality.py (env-lock pip-freeze hash, dirty-tree stamp).
"""

from __future__ import annotations

import hashlib
import json
import math
import platform
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

__all__ = [
    "ManifestVerification",
    "build_manifest",
    "canonical_json",
    "json_default",
    "load_and_verify_evidence",
    "resolve_git_head",
    "resolve_git_dirty",
    "sha256_bytes",
    "sha256_file",
    "verify_manifest",
    "write_evidence",
]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path | str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def json_default(obj: Any) -> Any:
    """The house JSON encoder (c3_residual_momentum._json_default semantics)."""
    import numpy as np
    import pandas as pd

    if isinstance(obj, pd.Timestamp):
        return obj.date().isoformat()
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        v = float(obj)
        return v if math.isfinite(v) else None
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, Path):
        return str(obj)
    return str(obj)


def canonical_json(obj: Any) -> str:
    """Deterministic serialization used for content hashing (sorted keys,
    fixed separators, house encoder for numpy/pandas scalars)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=json_default)


def resolve_git_head(repo_root: Path | str) -> str | None:
    """`git rev-parse HEAD` — NOT a raw .git/HEAD read: in a linked worktree
    .git is a file, not a directory (c3_residual_momentum.resolve_worktree_head
    lesson)."""
    try:
        out = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip() or None
    except (OSError, subprocess.CalledProcessError):
        return None


def resolve_git_dirty(repo_root: Path | str) -> dict[str, int] | None:
    """Tracked-modified / untracked counts. A dirty-tree run is admissible for
    exploration, inadmissible for a verdict (S-REL §3.1)."""
    try:
        porcelain = subprocess.run(
            ["git", "-C", str(repo_root), "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    lines = porcelain.splitlines()
    tracked = [ln for ln in lines if not ln.startswith("??")]
    return {"tracked_modified": len(tracked), "untracked": len(lines) - len(tracked)}


def _env_lock_sha256() -> str | None:
    """sha256 of the sorted `pip freeze` output — pins the dependency surface
    (an xgboost minor-version change moves ICs). Failure-tolerant."""
    try:
        freeze = subprocess.run(
            [sys.executable, "-m", "pip", "freeze"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    return sha256_bytes("\n".join(sorted(freeze.splitlines())).encode())


def build_manifest(
    *,
    repo_root: Path | str,
    script: str,
    inputs: Mapping[str, Path | str] | None = None,
    input_hashes: Mapping[str, str] | None = None,
    argv: Sequence[str] | None = None,
    seeds: Sequence[int] = (),
    spec_sha256: str | None = None,
    config_sha256: str | None = None,
    env_lock: bool = False,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble the S-REL §3.1 manifest.

    `inputs` maps a stable logical name to a file path; each file is content-
    hashed here. `input_hashes` passes through hashes computed in-memory (e.g.
    a canonicalized aligned panel that never touched disk — the
    c3 `canonical_panel_sha256` pattern). `env_lock=False` by default because
    `pip freeze` is slow; verdict-producing runs should set it True.
    """
    import numpy as np
    import pandas as pd

    hashed = {str(k): sha256_file(Path(v)) for k, v in (inputs or {}).items()}
    hashed.update({str(k): str(v) for k, v in (input_hashes or {}).items()})
    manifest: dict[str, Any] = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "interpreter": sys.executable,
        "python": platform.python_version(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "code": {
            "repo_root": str(repo_root),
            "git_sha": resolve_git_head(repo_root),
            "dirty": resolve_git_dirty(repo_root),
            "script": script,
            "argv": list(argv) if argv is not None else list(sys.argv[1:]),
        },
        "inputs_sha256": hashed,
        "input_paths": {str(k): str(v) for k, v in (inputs or {}).items()},
        "seeds": [int(s) for s in seeds],
        "spec_sha256": spec_sha256,
        "config_sha256": config_sha256,
    }
    if env_lock:
        manifest["env_lock_sha256_pip_freeze"] = _env_lock_sha256()
    if extra:
        manifest.update(dict(extra))
    return manifest


def write_evidence(out_dir: Path | str, name: str, payload: Mapping[str, Any]) -> Path:
    """Write one evidence JSON (indent=2, house encoder). `payload` should
    embed its manifest under the `manifest` key."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / name
    path.write_text(json.dumps(payload, indent=2, default=json_default) + "\n")
    return path


@dataclass
class ManifestVerification:
    ok: bool
    checked: int
    mismatched: dict[str, dict[str, str]] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    unverifiable: list[str] = field(default_factory=list)

    def raise_if_failed(self) -> None:
        if not self.ok:
            raise ValueError(
                "evidence manifest verification failed: "
                f"mismatched={sorted(self.mismatched)} missing={self.missing}"
            )


def verify_manifest(
    manifest: Mapping[str, Any], *, base: Path | str | None = None
) -> ManifestVerification:
    """Recompute the content hash of every input the manifest stamped with a
    path and compare. Inputs stamped hash-only (in-memory panels) are reported
    `unverifiable`, never silently passed."""
    base = Path(base) if base is not None else Path(".")
    hashes: Mapping[str, str] = manifest.get("inputs_sha256", {}) or {}
    paths: Mapping[str, str] = manifest.get("input_paths", {}) or {}
    mismatched: dict[str, dict[str, str]] = {}
    missing: list[str] = []
    unverifiable: list[str] = []
    checked = 0
    for key, expected in hashes.items():
        raw = paths.get(key)
        if raw is None:
            unverifiable.append(key)
            continue
        p = Path(raw)
        if not p.is_absolute():
            p = base / p
        if not p.exists():
            missing.append(key)
            continue
        actual = sha256_file(p)
        checked += 1
        if actual != expected:
            mismatched[key] = {"expected": str(expected), "actual": actual}
    ok = not mismatched and not missing
    return ManifestVerification(
        ok=ok,
        checked=checked,
        mismatched=mismatched,
        missing=missing,
        unverifiable=unverifiable,
    )


def load_and_verify_evidence(
    path: Path | str, *, base: Path | str | None = None, strict: bool = True
) -> tuple[dict[str, Any], ManifestVerification]:
    """Load an evidence JSON and verify its embedded manifest. With
    strict=True (default), a failed verification raises — a verifier must
    never silently consume evidence whose inputs have drifted."""
    payload = json.loads(Path(path).read_text())
    manifest = payload.get("manifest") or {}
    verification = verify_manifest(manifest, base=base)
    if strict:
        verification.raise_if_failed()
    return payload, verification
