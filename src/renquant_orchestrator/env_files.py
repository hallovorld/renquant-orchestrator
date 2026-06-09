"""Small .env helpers for operator-only command preflights."""
from __future__ import annotations

import os
from pathlib import Path


def read_env_file(path: str | Path | None, *, missing_ok: bool = True) -> dict[str, str]:
    """Read simple KEY=VALUE lines without exposing values in command output."""
    if path is None:
        return {}
    env_path = Path(path)
    values: dict[str, str] = {}
    if not env_path.exists():
        if missing_ok:
            return values
        raise FileNotFoundError(f"env file not found: {env_path}")
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key:
            values[key] = value
    return values


def load_env_file(path: str | Path, *, override: bool = False) -> dict[str, str]:
    """Load a .env file into this process and return parsed keys/values."""
    values = read_env_file(path, missing_ok=False)
    for key, value in values.items():
        if override or not os.environ.get(key):
            os.environ[key] = value
    return values


__all__ = ["load_env_file", "read_env_file"]
