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


def compute_manifest_commit_id(manifest: dict[str, str]) -> str:
    """Deterministic content digest of a {path: sha256} manifest.

    Same pattern as bundle.py::compute_bundle_fingerprint — the digest
    changes iff the manifest's content changes, so it can stand in for a
    real Volume commit id (Modal's Python SDK does not return one from
    `vol.commit()`). A wall-clock timestamp proves nothing about content
    identity and cannot serve as a replay-provenance field.
    """
    canonical = json.dumps(manifest, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _prefixed(label: str, rel: str) -> str:
    """Join a sync label with a relative path. An empty label means "no
    prefix" — the file lands directly at the Volume root (needed for a
    consumer that resolves its own root via a fixed parents[N] depth rather
    than RENQUANT_DATA_ROOT, so its expected path has no extra directory
    segment beyond the Volume mount point itself)."""
    return rel if not label else f"{label}/{rel}"


def build_local_manifest(
    paths: dict[str, Path],
) -> tuple[dict[str, str], dict[str, Path]]:
    """Build {relative_path: sha256} plus {relative_path: local_file} for all
    files under the given paths.

    The second mapping is the authoritative source-file lookup for upload —
    re-deriving it by splitting the relative path on "/" is ambiguous for a
    root-level (empty-label) file, since there's no separator to split on.
    """
    manifest: dict[str, str] = {}
    sources: dict[str, Path] = {}
    for label, path in sorted(paths.items()):
        if path.is_file():
            if path.name not in SYNC_EXCLUSIONS:
                rel = _prefixed(label, path.name)
                manifest[rel] = _sha256(path)
                sources[rel] = path
        elif path.is_dir():
            for f in sorted(path.rglob("*")):
                if not f.is_file():
                    continue
                if f.name in SYNC_EXCLUSIONS:
                    continue
                if any(p in SYNC_EXCLUDE_DIRS for p in f.parts):
                    continue
                rel = _prefixed(label, str(f.relative_to(path)))
                manifest[rel] = _sha256(f)
                sources[rel] = f
    return manifest, sources


def local_data_manifest(
    local_paths: dict[str, Path],
) -> tuple[DataManifest, dict[str, Path]]:
    """Build a DataManifest from LOCAL file content only — makes NO Modal
    calls (no import of the `modal` package at all).

    `commit_id` is a deterministic content digest (`compute_manifest_commit_id`),
    not a Modal Volume commit id — it is identical whether or not the
    content is ever actually uploaded, which is exactly why
    `sync_to_modal_volume` below reuses this function rather than
    duplicating the computation: preflight/validation callers that must
    never touch Modal (see run_sweep_modal.py's --execute guardrail) can
    use this directly, and a real upload's resulting DataManifest is
    byte-identical to what this function alone would have produced.

    Returns (manifest, local_sources); local_sources is the authoritative
    {relative_path: local_file} lookup a real uploader needs — pure
    validation callers may discard it.
    """
    local_manifest, local_sources = build_local_manifest(local_paths)
    total_bytes = sum(
        p.stat().st_size
        for label, path in local_paths.items()
        for p in ([path] if path.is_file() else list(path.rglob("*")))
        if p.is_file() and p.name not in SYNC_EXCLUSIONS
    )
    manifest = DataManifest(
        commit_id=compute_manifest_commit_id(local_manifest),
        timestamp=datetime.now(timezone.utc).isoformat(),
        files=local_manifest,
        total_bytes=total_bytes,
    )
    return manifest, local_sources


def sync_to_modal_volume(
    local_paths: dict[str, Path],
    volume_name: str = "renquant-sweep-data",
) -> DataManifest:
    """Sync local data to a Modal Volume. Returns a DataManifest."""
    import modal

    manifest, local_sources = local_data_manifest(local_paths)
    local_manifest = manifest.files

    vol = modal.Volume.from_name(volume_name, create_if_missing=True)

    prev_manifest_path = Path.home() / ".renquant" / "modal_sync_manifest.json"
    prev: dict[str, str] = {}
    if prev_manifest_path.exists():
        prev = json.loads(prev_manifest_path.read_text())

    to_upload = {k: v for k, v in local_manifest.items() if prev.get(k) != v}
    if not to_upload:
        log.info("No changes to sync — reusing existing Volume state")
        return manifest

    log.info("Syncing %d files to Modal Volume '%s'", len(to_upload), volume_name)

    with vol.batch_upload(force=True) as batch:
        for rel_path, checksum in to_upload.items():
            local_file = local_sources[rel_path]
            remote_path = f"/{rel_path}"
            batch.put_file(str(local_file), remote_path)
            log.info("  uploaded %s (%s)", rel_path, checksum[:8])

    prev_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    prev_manifest_path.write_text(json.dumps(local_manifest, indent=2, sort_keys=True))

    log.info("Synced %d files (%.1f MB), commit=%s",
             len(to_upload), manifest.total_bytes / 1e6, manifest.commit_id)

    return manifest


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
