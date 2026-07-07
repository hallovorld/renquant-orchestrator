"""Upload OHLCV + model artifacts to Modal Volume with checksums."""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from .executor import DataManifest

log = logging.getLogger(__name__)

SYNC_EXCLUSIONS = {
    ".env", "runs.alpaca.db", "live_state.json", "live_state_v2.json",
    "strategy_config.json", "rawlabel.parquet",
}

SYNC_EXCLUDE_DIRS = {"logs", ".git", "__pycache__", "tests"}


def build_local_manifest(paths: dict[str, Path]) -> dict[str, str]:
    """Build {relative_path: sha256} for all files under the given paths."""
    result: dict[str, str] = {}
    for label, path in sorted(paths.items()):
        if path.is_file():
            if path.name not in SYNC_EXCLUSIONS:
                result[f"{label}/{path.name}"] = _sha256(path)
        elif path.is_dir():
            for f in sorted(path.rglob("*")):
                if not f.is_file():
                    continue
                if f.name in SYNC_EXCLUSIONS:
                    continue
                if any(p in SYNC_EXCLUDE_DIRS for p in f.parts):
                    continue
                rel = f"{label}/{f.relative_to(path)}"
                result[rel] = _sha256(f)
    return result


def sync_to_modal_volume(
    local_paths: dict[str, Path],
    volume_name: str = "renquant-sweep-data",
) -> DataManifest:
    """Sync local data to a Modal Volume. Returns a DataManifest."""
    import modal

    local_manifest = build_local_manifest(local_paths)
    total_bytes = sum(
        p.stat().st_size
        for label, path in local_paths.items()
        for p in ([path] if path.is_file() else list(path.rglob("*")))
        if p.is_file() and p.name not in SYNC_EXCLUSIONS
    )

    vol = modal.Volume.from_name(volume_name, create_if_missing=True)

    prev_manifest_path = Path.home() / ".renquant" / "modal_sync_manifest.json"
    prev: dict[str, str] = {}
    if prev_manifest_path.exists():
        prev = json.loads(prev_manifest_path.read_text())

    to_upload = {k: v for k, v in local_manifest.items() if prev.get(k) != v}
    if not to_upload:
        log.info("No changes to sync — reusing existing Volume state")
        commit_id = prev.get("_commit_id", "unchanged")
        return DataManifest(
            commit_id=commit_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            files=local_manifest,
            total_bytes=total_bytes,
        )

    log.info("Syncing %d files to Modal Volume '%s'", len(to_upload), volume_name)

    for rel_path, checksum in to_upload.items():
        parts = rel_path.split("/", 1)
        label = parts[0]
        file_rel = parts[1] if len(parts) > 1 else ""
        local_base = local_paths[label]
        if local_base.is_file():
            local_file = local_base
        else:
            local_file = local_base / file_rel

        remote_path = f"/data/{rel_path}"
        with open(local_file, "rb") as f:
            vol.write_file(remote_path, f)
        log.info("  uploaded %s (%s)", rel_path, checksum[:8])

    vol.commit()
    commit_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    prev_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    save = dict(local_manifest)
    save["_commit_id"] = commit_id
    prev_manifest_path.write_text(json.dumps(save, indent=2, sort_keys=True))

    log.info("Synced %d files (%.1f MB), commit=%s",
             len(to_upload), total_bytes / 1e6, commit_id)

    return DataManifest(
        commit_id=commit_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        files=local_manifest,
        total_bytes=total_bytes,
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
