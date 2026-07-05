"""S11 artifact retention policy and pruning.

The promote pipeline (kernel/model_acceptance.py) and pin-backup tooling
(scripts/promote_pin.py) write timestamped staging, rollback, and lock-backup
files that accumulate without bound.  This module defines a retention window
per artifact family and provides a ``prune_stale_artifacts`` function that
identifies (and optionally removes) files beyond the window.

Artifact families (all paths relative to the umbrella repo root):

  staging_panel_ltr
    artifacts/prod/panel-ltr.alpha158_fund.weekly_<ts>.staging.json

  staging_calibration
    artifacts/prod/panel-rank-calibration.weekly_<ts>.staging.json

  rollback_snapshots
    artifacts/prod/(panel-ltr.alpha158_fund|panel-rank-calibration)
        .(weekly|monthly)_rollback_<date>.json

  lock_backups
    subrepos.lock.json.promote-bak.<ts>

Safety: ``prune_stale_artifacts`` defaults to dry_run=True. Files are never
removed unless the caller passes ``dry_run=False`` explicitly. The function
returns the list of paths that *would* be (or *were*) removed, so callers
can audit before committing to deletion.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Retention configuration
# ---------------------------------------------------------------------------

_BT_PREFIX = "backtesting/renquant_104/"


@dataclass(frozen=True)
class ArtifactFamily:
    """One family of timestamped artifacts with a fixed retention window."""

    name: str
    glob_pattern: str
    keep: int
    description: str


#: Default families. The glob patterns are relative to the repo root.
#: ``keep`` is the number of *newest* files to retain; older ones are prunable.
DEFAULT_FAMILIES: tuple[ArtifactFamily, ...] = (
    ArtifactFamily(
        name="staging_panel_ltr",
        glob_pattern="artifacts/prod/panel-ltr.alpha158_fund.weekly_*.staging.json",
        keep=4,
        description="weekly panel-ltr staging snapshots (~1 month at weekly cadence)",
    ),
    ArtifactFamily(
        name="staging_calibration",
        glob_pattern="artifacts/prod/panel-rank-calibration.weekly_*.staging.json",
        keep=4,
        description="weekly calibration staging snapshots (~1 month at weekly cadence)",
    ),
    ArtifactFamily(
        name="rollback_snapshots",
        glob_pattern="artifacts/prod/*_rollback_*.json",
        keep=8,
        description="weekly/monthly rollback snapshots for revert safety",
    ),
    ArtifactFamily(
        name="lock_backups",
        glob_pattern="subrepos.lock.json.promote-bak.*",
        keep=5,
        description="subrepos.lock.json pre-promote backups",
    ),
)


# ---------------------------------------------------------------------------
# Pruning logic
# ---------------------------------------------------------------------------


@dataclass
class PruneResult:
    """Summary of a prune scan/execution."""

    family: str
    total_found: int
    kept: int
    prunable: list[Path]
    deleted: bool  # True only when dry_run=False and files were removed


def _scan_family(root: Path, family: ArtifactFamily) -> PruneResult:
    """Identify prunable files for one artifact family.

    Files are sorted by modification time (newest first); the ``keep`` newest
    are retained and the rest are returned as prunable.
    """
    # The glob pattern may start with a subdirectory.  We need to search
    # both the repo root and the backtesting/renquant_104/ prefix because
    # the umbrella layout nests under backtesting/.
    found: list[Path] = []
    found.extend(sorted(root.glob(family.glob_pattern)))
    bt_root = root / _BT_PREFIX
    if bt_root.is_dir():
        found.extend(sorted(bt_root.glob(family.glob_pattern)))

    # Deduplicate (in case both paths resolve to the same file via symlink).
    seen: set[Path] = set()
    unique: list[Path] = []
    for p in found:
        resolved = p.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(p)

    # Sort newest-first by mtime.
    unique.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    prunable = unique[family.keep:]
    return PruneResult(
        family=family.name,
        total_found=len(unique),
        kept=min(len(unique), family.keep),
        prunable=prunable,
        deleted=False,
    )


def prune_stale_artifacts(
    root: Path,
    *,
    dry_run: bool = True,
    families: tuple[ArtifactFamily, ...] | None = None,
) -> list[PruneResult]:
    """Scan for stale promote-pipeline artifacts and optionally delete them.

    Parameters
    ----------
    root
        Umbrella repo root (the directory containing ``subrepos.lock.json``
        and ``artifacts/``).
    dry_run
        When *True* (the default), return the list of prunable paths without
        deleting anything.  When *False*, unlink each prunable file.
    families
        Override the default family definitions (mainly for testing).

    Returns
    -------
    list[PruneResult]
        One entry per family, regardless of whether any files were found.
    """
    if families is None:
        families = DEFAULT_FAMILIES

    results: list[PruneResult] = []
    for fam in families:
        result = _scan_family(root, fam)
        if not dry_run and result.prunable:
            for p in result.prunable:
                p.unlink()
            result.deleted = True
        results.append(result)
    return results


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """CLI: ``renquant-orchestrator prune-artifacts [--execute] [--repo PATH]``."""
    ap = argparse.ArgumentParser(
        prog="renquant-orchestrator prune-artifacts",
        description="Prune stale promote-pipeline staging/rollback/backup artifacts.",
    )
    ap.add_argument(
        "--execute",
        action="store_true",
        help="actually delete files (default: dry-run, list only)",
    )
    ap.add_argument(
        "--repo",
        type=Path,
        default=None,
        help="umbrella repo root; default: /Users/renhao/git/github/RenQuant",
    )
    ap.add_argument(
        "--json",
        action="store_true",
        dest="emit_json",
        help="emit machine-readable JSON instead of human summary",
    )
    args = ap.parse_args(argv if argv is not None else sys.argv[1:])

    repo_root: Path = args.repo or Path("/Users/renhao/git/github/RenQuant")
    if not repo_root.is_dir():
        print(f"error: repo root does not exist: {repo_root}", file=sys.stderr)
        return 1

    dry_run = not args.execute
    results = prune_stale_artifacts(repo_root, dry_run=dry_run)

    if args.emit_json:
        payload = {
            "dry_run": dry_run,
            "repo_root": str(repo_root),
            "families": [
                {
                    "family": r.family,
                    "total_found": r.total_found,
                    "kept": r.kept,
                    "prunable_count": len(r.prunable),
                    "prunable_paths": [str(p) for p in r.prunable],
                    "deleted": r.deleted,
                }
                for r in results
            ],
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        mode = "EXECUTE" if not dry_run else "DRY-RUN"
        print(f"prune-artifacts [{mode}]  repo={repo_root}\n")
        total_prunable = 0
        for r in results:
            total_prunable += len(r.prunable)
            action = "deleted" if r.deleted else "would delete"
            print(
                f"  {r.family}: {r.total_found} found, keep {r.kept}, "
                f"{action} {len(r.prunable)}"
            )
            for p in r.prunable:
                print(f"    {p}")
        if not total_prunable:
            print("\n  nothing to prune")
        elif dry_run:
            print(f"\n  {total_prunable} file(s) would be deleted; pass --execute to remove")

    return 0
