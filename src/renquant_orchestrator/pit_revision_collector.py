"""PIT estimate-revision snapshot collector scheduler (N2).

Thin orchestrator wrapper around ``renquant_base_data.fmp_estimate_revisions``.
The collector itself lives in renquant-base-data (PR #27, merged 2026-06-30);
the orchestrator's role is to SCHEDULE, fingerprint, and alert on freshness.

Each invocation appends one day's snapshot to the PIT revision lake. Missed days
are permanently lost (the whole point of N2: time-irreversible data accrual).
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import logging
import subprocess
import sys
from pathlib import Path

from .runtime_paths import default_repo_root, resolve_subrepo_root

log = logging.getLogger("renquant_orchestrator.pit_revision_collector")

DEFAULT_REPO_DIR = default_repo_root()
DEFAULT_OUTPUT_DIR = "data/pit/estimate_revisions"
DEFAULT_PROVENANCE_DIR = "data/pit/provenance"
COLLECTOR_MODULE = "renquant_base_data.fmp_estimate_revisions"

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


def collect_snapshot(
    repo_dir: Path,
    *,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    python: str | None = None,
    universe_file: str | None = None,
    dry_run: bool = False,
) -> dict:
    """Invoke the base-data collector and record provenance.

    Returns a summary dict with snapshot path, row count hash, and timestamp.
    """
    py = python or sys.executable
    out_path = repo_dir / output_dir
    out_path.mkdir(parents=True, exist_ok=True)

    cmd = [py, "-m", COLLECTOR_MODULE, "--output-dir", str(out_path)]
    if universe_file:
        cmd.extend(["--universe", universe_file])

    log.info("PIT revision collector: %s", " ".join(cmd))

    if dry_run:
        return {"status": "dry_run", "command": cmd, "output_dir": str(out_path)}

    result = subprocess.run(
        cmd,
        cwd=str(repo_dir),
        env=_subrepo_pythonpath(repo_dir),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        log.error("PIT revision collector failed (rc=%d): %s", result.returncode, result.stderr[:500])
        raise RuntimeError(
            f"PIT revision collector failed rc={result.returncode}: {result.stderr[:200]}"
        )

    today = dt.date.today().isoformat()
    snapshot_files = sorted(out_path.glob(f"*{today}*"))

    provenance = {
        "collected_at": dt.datetime.utcnow().isoformat() + "Z",
        "collector": COLLECTOR_MODULE,
        "output_dir": str(out_path),
        "snapshot_date": today,
        "n_files": len(snapshot_files),
        "files": [f.name for f in snapshot_files[:20]],
    }

    if snapshot_files:
        hasher = hashlib.sha256()
        for f in snapshot_files:
            hasher.update(f.read_bytes())
        provenance["content_sha256"] = hasher.hexdigest()

    prov_dir = repo_dir / DEFAULT_PROVENANCE_DIR
    prov_dir.mkdir(parents=True, exist_ok=True)
    prov_file = prov_dir / f"revision_snapshot_{today}.json"
    prov_file.write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    provenance["provenance_file"] = str(prov_file)

    log.info("PIT revision snapshot: %d files, provenance → %s", len(snapshot_files), prov_file)
    return provenance


def check_freshness(
    repo_dir: Path,
    *,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    max_gap_days: int = 2,
) -> dict:
    """Check that the PIT revision lake has a recent snapshot.

    Returns a freshness report. Raises no errors — the caller decides severity.
    """
    out_path = repo_dir / output_dir
    if not out_path.exists():
        return {"fresh": False, "reason": "output_dir_missing", "path": str(out_path)}

    files = sorted(out_path.iterdir())
    if not files:
        return {"fresh": False, "reason": "no_snapshots", "path": str(out_path)}

    latest = files[-1]
    today = dt.date.today()

    try:
        date_str = latest.stem.split("_")[-1][:10]
        latest_date = dt.date.fromisoformat(date_str)
    except (ValueError, IndexError):
        latest_date = dt.date.fromtimestamp(latest.stat().st_mtime)

    gap = (today - latest_date).days
    return {
        "fresh": gap <= max_gap_days,
        "latest_file": latest.name,
        "latest_date": latest_date.isoformat(),
        "gap_days": gap,
        "max_gap_days": max_gap_days,
        "path": str(out_path),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect PIT estimate-revision snapshot (N2)"
    )
    parser.add_argument("--repo-dir", type=Path, default=DEFAULT_REPO_DIR)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--universe", default=None, help="universe file override")
    parser.add_argument("--check-freshness", action="store_true",
                        help="check freshness instead of collecting")
    parser.add_argument("--max-gap-days", type=int, default=2)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_dir = args.repo_dir.expanduser().resolve()

    if args.check_freshness:
        report = check_freshness(
            repo_dir, output_dir=args.output_dir, max_gap_days=args.max_gap_days,
        )
        print(json.dumps(report, indent=2))
        return 0 if report["fresh"] else 1

    result = collect_snapshot(
        repo_dir,
        output_dir=args.output_dir,
        universe_file=args.universe,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
