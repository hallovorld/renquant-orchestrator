"""ArtifactResolver (#108 S1) — the single artifact-resolution authority.

Every artifact lookup (primary scorer, shadow, calibrator, GMM, gate manifest
rows) must resolve through this module and nothing else. It replaces the ad-hoc
``Path(ref).resolve()`` / ``.exists()`` checks scattered across the retrain and
manifest-builder scripts — divergence between two such call sites is exactly how
incident #2 (#114) hid a dead shadow scorer for a week: the primary resolved
``strategy_dir``-first while the shadow resolved ``repo_root``-first, so the same
relative ref pointed at two different files.

Resolution contract (fail-closed):
  * an **absolute** ref is used as-is (``source="absolute"``);
  * a **store-addressed** ref — a relative ref whose first component after
    stripping any LEADING ``..`` segments is ``artifacts`` — is tried against
    an explicitly declared ``artifact_store`` FIRST when one is provided
    (``source="artifact_store"``). Prod configs author artifact refs as
    umbrella-layout parent walks (``../../artifacts/<...>``); a pinned
    checkout has no such geometry, so the run manifest declares the store
    explicitly instead of the checkout reconstructing umbrella geometry
    (2026-07-10 shadow-ab first-session precheck abort; Codex on #464).
    An interior ``..`` disqualifies (fail-safe to the geometric contract);
  * a **relative** ref is tried against ``strategy_dir`` first, then
    ``repo_root`` (``source="strategy_dir"`` / ``"repo_root"``);
  * if nothing exists, raise ``FileNotFoundError`` listing every path tried —
    never silently return a missing path.

Every resolved artifact carries a full ``sha256`` and its ``source`` so callers
can stamp provenance into walk-forward manifest rows and the DRPH run
fingerprint, letting the gate detect a wrong/stale artifact instead of scoring
it blindly.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import NamedTuple

# Artifacts range from small JSON (panel-ltr) to 100s-of-MB .pt checkpoints;
# stream the hash so we never load a whole checkpoint into memory.
_READ_CHUNK = 1 << 20  # 1 MiB

_UNHASHED = ""  # sentinel sha for resolve(..., verify_sha=False)


class ResolvedArtifact(NamedTuple):
    """A located artifact plus the provenance needed to trust it."""

    path: Path      # absolute, symlink-resolved
    sha256: str     # full 64-hex digest, or "" when verify_sha=False
    source: str     # "absolute" | "artifact_store" | "strategy_dir" | "repo_root"
    ref: str        # the original ref as requested

    @property
    def short_sha(self) -> str:
        """16-hex prefix — the form stamped into manifest rows / fingerprints."""
        return self.sha256[:16]


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(_READ_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def store_relative_ref(ref: str | Path) -> Path | None:
    """The store-relative remainder for a store-addressed ref, else ``None``.

    A relative ref is store-addressed when, after stripping any LEADING
    ``..`` segments (the umbrella-layout parent walk it was authored with),
    its first remaining component is ``artifacts`` and something follows it.
    Interior ``..`` segments disqualify — those stay on the purely geometric
    strategy_dir/repo_root contract (fail-safe).
    """
    ref_path = Path(ref)
    if ref_path.is_absolute():
        return None
    parts = ref_path.parts
    i = 0
    while i < len(parts) and parts[i] == "..":
        i += 1
    rest = parts[i:]
    if len(rest) < 2 or rest[0] != "artifacts" or ".." in rest:
        return None
    return Path(*rest[1:])


def resolve_artifact(
    ref: str | Path,
    *,
    strategy_dir: str | Path,
    repo_root: str | Path,
    artifact_store: str | Path | None = None,
    verify_sha: bool = True,
) -> ResolvedArtifact:
    """Resolve ``ref`` to a concrete, existing artifact (fail-closed).

    Args:
        ref: absolute or relative artifact reference.
        strategy_dir: the strategy root tried first for relative refs.
        repo_root: the repo root tried second for relative refs.
        artifact_store: an explicitly declared artifact-store root (e.g. from
            the run manifest). When provided, store-addressed refs (see
            :func:`store_relative_ref`) try ``artifact_store/<remainder>``
            FIRST — an explicit contract beats geometric accident. ``None``
            (the default) leaves behaviour byte-identical to before.
        verify_sha: when False, skip hashing (``sha256=""``) — use only where
            the caller needs the path but not provenance.

    Raises:
        FileNotFoundError: if no candidate exists, listing every path tried.
    """
    ref_path = Path(ref)
    strategy_dir = Path(strategy_dir)
    repo_root = Path(repo_root)

    if ref_path.is_absolute():
        candidates: list[tuple[Path, str]] = [(ref_path, "absolute")]
    else:
        store_rel = (
            store_relative_ref(ref_path) if artifact_store is not None else None
        )
        if store_rel is not None:
            # A store-addressed ref with a declared store resolves ONLY
            # inside that store (r4, Codex on #464 r3): a geometric fallback
            # would let a missing/misaddressed store object silently consume
            # an artifact from a recreated umbrella path. A miss raises.
            candidates = [(Path(artifact_store) / store_rel, "artifact_store")]
        else:
            candidates = [
                (strategy_dir / ref_path, "strategy_dir"),
                (repo_root / ref_path, "repo_root"),
            ]

    store_root_resolved = (
        Path(artifact_store).resolve() if artifact_store is not None else None
    )

    tried: list[str] = []
    for cand, source in candidates:
        cand = cand.resolve()
        tried.append(str(cand))
        if not cand.exists():
            continue
        if source == "artifact_store" and not cand.is_relative_to(
            store_root_resolved
        ):
            # resolve-and-contain (r4): a committed symlink below the store
            # may not smuggle resolution outside the verified checkout.
            raise FileNotFoundError(
                "artifact escapes the declared artifact store (fail-closed): "
                f"{str(ref)!r} resolves to {cand}, outside "
                f"{store_root_resolved}"
            )
        sha = _sha256_file(cand) if verify_sha else _UNHASHED
        return ResolvedArtifact(path=cand, sha256=sha, source=source,
                                ref=str(ref))
    raise FileNotFoundError(
        f"artifact unresolvable (fail-closed): {str(ref)!r} tried {tried}"
    )


class ArtifactResolver:
    """Bind ``strategy_dir`` / ``repo_root`` / ``artifact_store`` once;
    resolve many refs.

    Use one resolver per run so every load shares an identical resolution
    order — the invariant whose violation caused incident #2.
    """

    def __init__(
        self,
        *,
        strategy_dir: str | Path,
        repo_root: str | Path,
        artifact_store: str | Path | None = None,
    ) -> None:
        self.strategy_dir = Path(strategy_dir)
        self.repo_root = Path(repo_root)
        self.artifact_store = (
            Path(artifact_store) if artifact_store is not None else None
        )

    def resolve(self, ref: str | Path, *, verify_sha: bool = True) -> ResolvedArtifact:
        return resolve_artifact(
            ref,
            strategy_dir=self.strategy_dir,
            repo_root=self.repo_root,
            artifact_store=self.artifact_store,
            verify_sha=verify_sha,
        )
