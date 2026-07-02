#!/usr/bin/env python3
"""r5 fix: enforce exact set-equality between a freshly-regenerated S11 manifest
and the live tree's CURRENT path set, using the same NUL-aware parser the
classifier itself uses (git_status_porcelain.py) — not a second, separately
ad hoc line/space-split parser duplicated in the sync-drill runbook.

READ-ONLY. Exits 0 (paths match exactly) or 1 (mismatch — the tree changed
between manifest generation and this check, or the manifest is stale).

Usage:
    python3 scripts/s11_verify_set_equality.py --manifest PATH [--live-tree PATH]
"""
from __future__ import annotations

import argparse
import json
import sys

from git_status_porcelain import run_git_status_porcelain_v2_nul

DEFAULT_LIVE_TREE = "/Users/renhao/git/github/RenQuant"


def live_path_set(live_tree: str) -> set[str]:
    entries = run_git_status_porcelain_v2_nul(live_tree)
    paths: set[str] = set()
    for e in entries:
        if e.kind in ("ordinary", "rename_copy", "untracked"):
            paths.add(e.path)
        elif e.kind == "unmerged":
            raise ValueError(
                f"unexpected unmerged (conflict) porcelain entry: {e.path!r} — "
                f"live tree has an active merge conflict"
            )
        # 'ignored' entries are not emitted by default and are skipped if present
    return paths


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", required=True, help="path to the freshly-regenerated S11 manifest JSON")
    ap.add_argument("--live-tree", default=DEFAULT_LIVE_TREE)
    args = ap.parse_args()

    manifest = json.loads(open(args.manifest).read())
    manifest_paths = {row["path"] for row in manifest["paths"]}
    live_paths = live_path_set(args.live_tree)

    missing_from_manifest = live_paths - manifest_paths
    extra_in_manifest = manifest_paths - live_paths

    if missing_from_manifest or extra_in_manifest:
        print(
            "ABORT: live tree path set does not match the manifest generated moments ago.\n"
            f"  paths on disk but not in manifest (tree mutated since generation): "
            f"{sorted(missing_from_manifest)[:20]}\n"
            f"  paths in manifest but not on disk (also tree mutation): "
            f"{sorted(extra_in_manifest)[:20]}\n"
            "STOP — something changed the live tree between manifest generation and this "
            "check; re-run step 2a.",
            file=sys.stderr,
        )
        return 1

    print(f"Set-equality OK: {len(live_paths)} paths match the manifest exactly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
