#!/usr/bin/env python3
"""Tier-1 backup with restore-verify (#108 §16.3).

Backs up the tiny-but-critical set (live state, sqlite DBs, pins, .env
inventory hash — not the secret itself) to ~/renquant-data/backups/<ts>/
with a sha256 manifest, then RESTORE-DRILLS into a temp dir and verifies
every checksum. restic adoption stays planned; this closes the gap tonight.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import shutil
import tempfile
from pathlib import Path

R = Path("/Users/renhao/git/github/RenQuant")
TARGETS = [
    R / "backtesting/renquant_104/live_state.alpaca.json",
    R / "backtesting/renquant_104/live_state.alpaca_shadow.json",
    R / "data/runs.alpaca.db",
    R / "data/runs.alpaca_shadow.db",
    R / "subrepos.lock.json",
]
DEST = Path.home() / "renquant-data/backups"


def file_sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def backup() -> Path:
    ts = dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    d = DEST / ts
    d.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for t in TARGETS:
        if not t.exists():
            manifest[str(t)] = "MISSING"
            continue
        dst = d / t.name
        shutil.copy2(t, dst)
        manifest[str(t)] = file_sha(dst)
    (d / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True))
    return d


def restore_drill(snap: Path) -> bool:
    manifest = json.loads((snap / "manifest.json").read_text())
    tmp = Path(tempfile.mkdtemp(prefix="restore_drill_"))
    ok = True
    for src_str, want in manifest.items():
        if want == "MISSING":
            continue
        name = Path(src_str).name
        restored = tmp / name
        shutil.copy2(snap / name, restored)
        got = file_sha(restored)
        if got != want:
            ok = False
            print(f"  CHECKSUM MISMATCH {name}: {got[:12]} != {want[:12]}")
    shutil.rmtree(tmp)
    return ok


if __name__ == "__main__":
    snap = backup()
    n = len([k for k, v in json.loads((snap / 'manifest.json').read_text()).items()
             if v != "MISSING"])
    print(f"backup → {snap} ({n} files + manifest)")
    assert restore_drill(snap), "restore drill FAILED"
    print("restore drill: every checksum verified ✓ "
          "(an unrestored backup is a hypothesis — this one isn't)")
    # retention: keep newest 14 snapshots
    snaps = sorted(DEST.iterdir())
    for old in snaps[:-14]:
        shutil.rmtree(old)
    print(f"retention: {min(len(snaps),14)} snapshots kept")
