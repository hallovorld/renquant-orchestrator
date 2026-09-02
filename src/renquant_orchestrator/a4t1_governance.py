"""A4-T1 candidate exception — orchestrator-side consumption governance.

Backtesting IDENTIFIES A4-T1 candidates (run-ID + digest match) but does not
enforce single-use. The orchestrator owns consumption: an atomic O_CREAT|O_EXCL
file marker in a governance ledger directory, keyed by run-ID. The proof dict
returned by ``consume()`` is passed to backtesting's ``stamp()`` as the
``a4t1_consumption_proof`` kwarg.

The governance directory defaults to ``~/.renquant/governance/`` — the
orchestrator's well-known state dir, NOT backtesting's concern. For tests,
pass an explicit ``governance_dir``.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path


_DEFAULT_GOVERNANCE_DIR = Path.home() / ".renquant" / "governance"


def consume(
    run_id: str,
    artifact_digest: str,
    staging_path: Path,
    *,
    governance_dir: Path | None = None,
) -> dict:
    """Atomically consume the A4-T1 candidate exception. Returns a proof dict.

    Raises ``FileExistsError`` if the candidate was already consumed (replay
    protection). Raises ``FileNotFoundError`` if the governance directory does
    not exist (fail-closed — never auto-create governance state).
    """
    gov = governance_dir or _DEFAULT_GOVERNANCE_DIR
    if not gov.is_dir():
        raise FileNotFoundError(
            f"A4-T1 governance directory does not exist: {gov}")
    marker_name = f"a4t1_{run_id}.consumed"
    marker_path = gov / marker_name
    proof = {
        "run_id": run_id,
        "artifact_digest": artifact_digest,
        "staging_path": str(staging_path),
        "consumed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "consumed_by": "renquant-orchestrator",
    }
    payload = json.dumps(proof, indent=2, sort_keys=True).encode("utf-8")
    fd = os.open(str(marker_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    try:
        os.write(fd, payload)
    finally:
        os.close(fd)
    return proof


def is_consumed(
    run_id: str,
    *,
    governance_dir: Path | None = None,
) -> bool:
    """Check whether the candidate was already consumed. Fail-closed: if the
    marker exists but is unreadable, returns True (consumed)."""
    gov = governance_dir or _DEFAULT_GOVERNANCE_DIR
    marker = gov / f"a4t1_{run_id}.consumed"
    return marker.exists()
