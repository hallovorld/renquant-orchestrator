#!/usr/bin/env python3
"""Emit the engineering census used by docs/CI."""
from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from renquant_orchestrator.engineering_census import build_engineering_census  # noqa: E402


def main() -> int:
    payload = build_engineering_census()
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
