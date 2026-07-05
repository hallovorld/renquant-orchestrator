"""SEC EDGAR XBRL companyfacts harvester scheduler (N2/RS-3).

Thin orchestrator wrapper around
``renquant_base_data.sec_edgar_companyfacts_harvester``. The harvester itself
lives in renquant-base-data (PR #40); the orchestrator's role is to invoke it
against a ticker list (or watchlist file), record provenance, and expose a
CLI/scheduling surface.

Free, no API key. Never writes to canonical ``data/`` paths — the caller
picks the output path explicitly.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import logging
import subprocess
import sys
import uuid
from pathlib import Path

from .runtime_paths import default_repo_root, resolve_subrepo_root

log = logging.getLogger("renquant_orchestrator.sec_edgar_harvester")

DEFAULT_REPO_DIR = default_repo_root()
DEFAULT_PROVENANCE_DIR = "data/pit/provenance"
HARVESTER_MODULE = "renquant_base_data.sec_edgar_companyfacts_harvester"

_SUBREPO_NAMES = [
    "renquant-base-data",
    "renquant-common",
]


def _subrepo_pythonpath(repo_dir: Path) -> dict[str, str]:
    import os

    subrepo_root = resolve_subrepo_root(repo_dir)
    srcs = [subrepo_root / name / "src" for name in _SUBREPO_NAMES]
    out = dict(os.environ)
    existing = out.get("PYTHONPATH", "")
    out["PYTHONPATH"] = os.pathsep.join([*(str(s) for s in srcs), existing])
    out.setdefault("RENQUANT_REPO_ROOT", str(repo_dir))
    out.setdefault("RENQUANT_DATA_ROOT", str(repo_dir))
    return out


def harvest(
    repo_dir: Path,
    output_path: Path,
    *,
    tickers: str | None = None,
    watchlist: str | None = None,
    python: str | None = None,
    dry_run: bool = False,
) -> dict:
    """Invoke the base-data harvester and record provenance.

    Exactly one of *tickers* / *watchlist* must be given, matching the
    underlying module's mutually-exclusive CLI contract. Returns a summary
    dict with output path, record/ticker counts, and a content hash.
    """
    if bool(tickers) == bool(watchlist):
        raise ValueError("exactly one of tickers/watchlist must be given")

    py = python or sys.executable
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [py, "-m", HARVESTER_MODULE, "--output", str(output_path)]
    if tickers:
        cmd.extend(["--tickers", tickers])
    else:
        cmd.extend(["--watchlist", str(watchlist)])

    log.info("SEC EDGAR harvester: %s", " ".join(cmd))

    if dry_run:
        return {"status": "dry_run", "command": cmd, "output_path": str(output_path)}

    result = subprocess.run(
        cmd,
        cwd=str(repo_dir),
        env=_subrepo_pythonpath(repo_dir),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        log.error("SEC EDGAR harvester failed (rc=%d): %s", result.returncode, result.stderr[:500])
        raise RuntimeError(
            f"SEC EDGAR harvester failed rc={result.returncode}: {result.stderr[:200]}"
        )

    if not output_path.exists():
        raise RuntimeError(
            f"SEC EDGAR harvester returned rc=0 but produced no output at {output_path}."
        )

    lines = [ln for ln in output_path.read_text().splitlines() if ln.strip()]
    records = []
    tickers_seen: set[str] = set()
    for ln in lines:
        try:
            rec = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if "_harvest_complete" in rec:
            continue
        records.append(rec)
        if rec.get("ticker"):
            tickers_seen.add(rec["ticker"])

    provenance = {
        "collected_at": dt.datetime.utcnow().isoformat() + "Z",
        "harvester": HARVESTER_MODULE,
        "output_path": str(output_path),
        "n_records": len(records),
        "n_tickers": len(tickers_seen),
    }

    hasher = hashlib.sha256()
    hasher.update(output_path.read_bytes())
    provenance["content_sha256"] = hasher.hexdigest()

    prov_dir = repo_dir / DEFAULT_PROVENANCE_DIR
    prov_dir.mkdir(parents=True, exist_ok=True)
    # Per-invocation, not per-date: a per-date filename lets two same-day
    # harvests (reruns, or separate watchlists) silently overwrite each
    # other's provenance record, losing the earlier run's hash/count/path.
    # Timestamp (matching retrain_patchtst.py's ``weekly_%Y%m%dT%H%M%SZ``
    # run-artifact convention) for sorting/readability, plus a uuid4 suffix
    # (matching intraday_live_executor.py's ``la-{uuid.uuid4().hex[:16]}``
    # action-id pattern) so two invocations can never collide regardless of
    # timing or identical output content.
    stamp = dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    prov_file = prov_dir / f"sec_edgar_harvest_{stamp}_{uuid.uuid4().hex[:8]}.json"
    prov_file.write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    provenance["provenance_file"] = str(prov_file)

    log.info(
        "SEC EDGAR harvest: %d records, %d tickers, provenance -> %s",
        len(records), len(tickers_seen), prov_file,
    )
    return provenance


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Schedule a SEC EDGAR companyfacts harvest (N2/RS-3)"
    )
    parser.add_argument("--repo-dir", type=Path, default=DEFAULT_REPO_DIR)
    parser.add_argument("--output", required=True, help="output JSONL path")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--tickers", default=None, help="comma-separated tickers")
    group.add_argument("--watchlist", default=None, help="watchlist file path")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_dir = args.repo_dir.expanduser().resolve()

    result = harvest(
        repo_dir,
        Path(args.output),
        tickers=args.tickers,
        watchlist=args.watchlist,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
