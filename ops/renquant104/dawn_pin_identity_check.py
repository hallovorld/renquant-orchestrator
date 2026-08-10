#!/usr/bin/env python3
"""Read-only pin-identity check + runtime receipt for the dawn preflight monitor.

#968 r1 (codex P1): switching the monitor to the multirepo bridge fixes the
MODULE namespace, but the monitor must also prove it previews the SAME pinned
runtime the 13:55 order path aligns to. The order entrypoint sources
``scripts/preflight_pin_align.sh`` (``subrepo_assemble.py --sync --dry-run``)
before the bridge — it verifies/aligns ``.subrepo_runtime/repos`` to
``subrepos.lock.json`` and ABORTS on drift/dirty. A monitor that skips this can
resolve a stale-but-importable runtime and report a gate verdict from a
DIFFERENT runtime than the order path executes — recreating the monitor-vs-order
divergence at the pin level.

This is the READ-ONLY, FAIL-CLOSED equivalent: it verifies each runtime subrepo
checkout matches the lock and emits a receipt, but NEVER checks out / fetches /
mutates (a monitor must not deploy). The pin predicate is an unambiguous git
identity (runtime HEAD == the lock's ``commit``, working tree clean) — the SAME
definition ``subrepo_assemble._is_pinned`` / ``_is_dirty`` use; keep these two
one-line git reads in LOCKSTEP with that module. (Unlike a policy mirror this
carries no thresholds/age logic to drift — HEAD either equals the pin or it
does not.)

Exit 0 = every subrepo present, pinned to the lock commit, and clean.
Exit 1 = any drift / dirty / missing repo / unreadable lock (fail-closed): the
caller must NOT run the probe, because its verdict would not be trustworthy.
The receipt (entrypoint, runtime root, per-repo lock vs resolved HEAD) is printed
and optionally written, on both pass and fail, so the divergence is visible.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import subprocess
import sys
from pathlib import Path


def _git(repo: Path, *args: str) -> str:
    """One read-only git read; '' on any failure (caller treats '' as not-ok)."""
    try:
        out = subprocess.run(["git", "-C", str(repo), *args],
                             capture_output=True, text=True, check=False)
        return out.stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


def check(lock_path: Path, runtime_root: Path, repo_dir: Path | None = None) -> "tuple[bool, list[dict]]":
    """Return ``(ok_all, repos)`` — per-repo pin identity, READ-ONLY.

    Pin predicate == subrepo_assemble's: runtime ``git log -1 --format=%H``
    startswith the lock ``commit`` (``_is_pinned``) AND ``git status --porcelain``
    is empty (``_is_dirty`` is false). Any exception on a repo is captured as
    ``ok=False`` (fail-closed), never raised. ``repo_dir`` is unused (kept for
    call-site symmetry with the order path's aligner).
    """
    lock = json.loads(Path(lock_path).read_text())
    repos: list[dict] = []
    ok_all = True
    for entry in lock["subrepos"]:
        name = entry.get("name", "?")
        lock_commit = str(entry.get("commit") or "")
        row = {"name": name, "lock_commit": lock_commit,
               "runtime_head": None, "present": False, "pinned": False,
               "dirty": None, "ok": False, "error": None}
        try:
            path = Path(runtime_root) / name  # == subrepo_assemble._repo_path(runtime_root)
            row["present"] = path.exists()
            if row["present"]:
                head = _git(path, "log", "-1", "--format=%H")
                row["runtime_head"] = head or None
                # _is_pinned: expected non-empty AND head startswith expected
                row["pinned"] = bool(lock_commit) and bool(head) and head.startswith(lock_commit)
                # _is_dirty: status --porcelain non-empty; '' from a non-repo => treat dirty
                status = _git(path, "status", "--porcelain")
                is_repo = bool(_git(path, "rev-parse", "--git-dir"))
                row["dirty"] = (not is_repo) or bool(status)
                row["ok"] = bool(row["pinned"]) and not row["dirty"]
        except Exception as exc:  # noqa: BLE001 — fail-closed on any probe error
            row["error"] = f"{type(exc).__name__}: {exc}"
            row["ok"] = False
        ok_all = ok_all and row["ok"]
        repos.append(row)
    return ok_all, repos


def build_receipt(entrypoint: str, runtime_root: Path, lock_path: Path,
                  ok_all: bool, repos: list[dict], now_iso: str) -> dict:
    return {
        "receipt": "dawn_pin_identity_v1",
        "entrypoint": entrypoint,
        "runtime_root": str(runtime_root),
        "lock": str(lock_path),
        "checked_at": now_iso,
        "ok": ok_all,
        "repos": repos,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo-dir", required=True, type=Path,
                    help="umbrella repo dir (holds scripts/subrepo_assemble.py)")
    ap.add_argument("--runtime-root", required=True, type=Path,
                    help="the .subrepo_runtime/repos root to verify")
    ap.add_argument("--lock", required=True, type=Path,
                    help="subrepos.lock.json path")
    ap.add_argument("--entrypoint", default="dawn_funnel_preflight")
    ap.add_argument("--receipt-out", default=None, type=Path)
    ap.add_argument("--now", default=None,
                    help="ISO timestamp override (tests); default utcnow")
    a = ap.parse_args(argv)

    now_iso = a.now or _dt.datetime.now(_dt.timezone.utc).isoformat()
    try:
        ok_all, repos = check(a.lock, a.runtime_root, a.repo_dir)
    except Exception as exc:  # noqa: BLE001 — unreadable lock / import failure => fail-closed
        receipt = build_receipt(a.entrypoint, a.runtime_root, a.lock, False,
                                [{"error": f"{type(exc).__name__}: {exc}", "ok": False}],
                                now_iso)
        out = json.dumps(receipt, indent=2)
        print(out)
        if a.receipt_out:
            a.receipt_out.write_text(out + "\n")
        return 1

    receipt = build_receipt(a.entrypoint, a.runtime_root, a.lock, ok_all, repos, now_iso)
    out = json.dumps(receipt, indent=2)
    print(out)
    if a.receipt_out:
        a.receipt_out.write_text(out + "\n")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
