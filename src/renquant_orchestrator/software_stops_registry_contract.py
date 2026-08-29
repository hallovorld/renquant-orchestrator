"""Software-stop registry-file contract — the READ / validation half only.

Context: the software-stop registry file — the heartbeat/state file the
LIVE sell-only loop stamps and ``renquant_execution.software_stops_liveness``
(renquant-execution#29) reads via ``--data-root`` — is configured in
``deploy/com.renquant.stops-liveness.plist`` at the neutral runtime-state
root (``~/.renquant/runtime/software-stops``). The sell-only loop writer
must be migrated to stamp there (a separate R-PIN landing change) before
the pager can be armed.

The canonical registry DATA schema (``software_stops.py``) belongs to
renquant-pipeline; the checker belongs to renquant-execution. This repo
owns LOCATION only — the neutral path convention and classifier below.

What THIS module defines, so "consume the neutral contract" is concrete and
testable even before that follow-up lands:

1. The **neutral runtime-state root** convention — an EXACT mirror of
   :func:`renquant_orchestrator.deployment_manifest.deploy_state_root`
   (design doc's §5.2): a host-scoped root that is never inside any repo,
   resolved override-then-env-then-default, sibling to R-PIN's own
   ``~/.renquant/deploy/``. This module does not create or write to it —
   it only names the convention a migrated writer should land under
   (``~/.renquant/runtime/software-stops/<broker>.json``) and reads
   against it.
2. A **data-root classifier** (:func:`classify_data_root`) the pager
   wrapper uses to observe — not silently accept — whether its configured
   data root is the neutral root or a legacy/umbrella-anchored path,
   producing a clearly labeled message for the latter (today's honest,
   actual production configuration).

Content correction (Codex CHANGES_REQUESTED on PR #481, 2026-07-12T04:32:57Z):
an earlier revision of this module also invented a versioned "envelope"
content schema (``schema_version`` / ``kind`` keys, ``classify_registry_file``)
that this repo does not own and that never corresponded to anything the real
writer (``renquant_pipeline.software_stops``) actually produces. Codex
correctly held that the canonical registry CONTENT contract belongs to the
producing/liveness-owning subsystem — ``renquant-pipeline`` (the schema,
``software_stops.py``) and ``renquant-execution`` (the liveness checker,
``software_stops_liveness.py``) — not orchestrator, which should schedule and
consume a versioned execution CLI/record rather than define a parallel
read-side schema. That envelope machinery has been removed. Registry CONTENT
validity is now delegated entirely to
``renquant_execution.software_stops_liveness.check()`` (and, at a lower
level, ``renquant_pipeline.software_stops._validate_snapshot`` — the real,
already-existing schema owned by the producing repo). This module owns
LOCATION only (the neutral runtime-state-root convention and the
NEUTRAL-vs-LEGACY path classifier below) — it never owns or re-derives
content schema. See ``scripts/install_stops_pager.sh`` for where that real
validator is now invoked as a fail-closed pre-install guard.

Writer-migration step 1 (2026-08-29, :func:`ensure_registry_seeded`): the
registry SEEDER. The pipeline registry treats a MISSING file as "armed,
empty — created on first write" (``software_stops.py`` ``_load``), and the
execution checker's ``check()`` returns OK on a missing file, so a writer
that is running against the WRONG root (or not running at all) is
indistinguishable from "nothing armed". The seeder creates — once, only if
absent — an EMPTY, schema-valid registry at EXACTLY the path the checker
resolves, so the file's presence becomes a fact the pager can see and the
installer guard (``--validate-registry`` requires VALID, not MISSING) can
pass. It never overwrites: a corrupt existing file is reported, not
repaired — repairing is a human decision. Path tagging and schema
validation are IMPORTED from ``renquant_pipeline.software_stops``; if that
module is not importable the seeder fails closed (ImportError) rather than
re-implementing either. The seeder still owns no content schema — the
seed's shape is validated by the pipeline's own public validator before it
is published.
"""
from __future__ import annotations

import argparse
import importlib
import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

# --- neutral runtime-state root (mirrors deployment_manifest.deploy_state_root) ------

#: Override env var — same naming/resolution convention as
#: ``deployment_manifest.DEPLOY_STATE_ROOT_ENV``.
RUNTIME_STATE_ROOT_ENV = "RENQUANT_RUNTIME_STATE_ROOT"
#: Sibling of R-PIN's ``~/.renquant/deploy/`` (design doc §5.2).
DEFAULT_RUNTIME_STATE_ROOT = Path("~/.renquant/runtime")

SOFTWARE_STOPS_REGISTRY_DIRNAME = "software-stops"


def runtime_state_root(override: str | Path | None = None) -> Path:
    """The neutral, host-scoped runtime-state root (never inside any repo).

    Exact mirror of ``deployment_manifest.deploy_state_root``: override,
    then ``RENQUANT_RUNTIME_STATE_ROOT``, then the default
    ``~/.renquant/runtime`` — sibling to R-PIN's own
    ``~/.renquant/deploy/``, but for state WRITTEN BY LIVE PRODUCTION
    LOOPS rather than R-PIN's own deploy/pin state.
    """
    if override is not None:
        return Path(override).expanduser()
    env = os.environ.get(RUNTIME_STATE_ROOT_ENV)
    if env:
        return Path(env).expanduser()
    return DEFAULT_RUNTIME_STATE_ROOT.expanduser()


def software_stops_registry_root(state_root: Path) -> Path:
    """Where a migrated writer should land registry files, one per broker."""
    return state_root / SOFTWARE_STOPS_REGISTRY_DIRNAME


def software_stops_registry_path(state_root: Path, *, broker: str) -> Path:
    return software_stops_registry_root(state_root) / f"{broker}.json"


# --- data-root classifier (path-level; no dependency on the writer's internal ------
#     relative-path layout, which belongs to another repo) --------------------------


@dataclass(frozen=True)
class DataRootVerdict:
    neutral: bool
    data_root: str
    message: str


def classify_data_root(
    data_root: str | Path, *, runtime_root: str | Path | None = None
) -> DataRootVerdict:
    """Classify a configured registry data root as NEUTRAL or LEGACY.

    NEUTRAL: the data root IS (or is inside) the neutral runtime-state
    root — i.e. the writer migration described in this module's docstring
    has landed.

    LEGACY: anything else, INCLUDING today's actual production
    configuration (the deprecated umbrella checkout). This is a fact
    observation, not a hard gate — the writer migration is a separately
    authorized change (out of scope here), so callers (the pager wrapper)
    should WARN, never abort, on a LEGACY verdict.
    """
    root = (
        Path(runtime_root).expanduser() if runtime_root is not None else runtime_state_root()
    ).resolve()
    candidate = Path(data_root).expanduser().resolve()
    is_neutral = candidate == root or candidate.is_relative_to(root)
    if is_neutral:
        return DataRootVerdict(
            neutral=True,
            data_root=str(candidate),
            message=f"NEUTRAL: {candidate} is under the neutral runtime-state root ({root})",
        )
    return DataRootVerdict(
        neutral=False,
        data_root=str(candidate),
        message=(
            f"LEGACY/UNVERSIONED registry root: {candidate} is NOT under the "
            f"neutral runtime-state root ({root}) — registry file is "
            "unversioned / at the legacy umbrella-anchored path — R-PIN "
            "writer migration not yet landed"
        ),
    )


def describe_data_root(
    data_root: str | Path, *, runtime_root: str | Path | None = None
) -> str:
    """One-line status string — lets a caller (the bash wrapper) do a
    single function call instead of unpacking the dataclass itself."""
    return classify_data_root(data_root, runtime_root=runtime_root).message


# --- registry seeder (writer migration, step 1) ---------------------------------------
#     Creates the registry file ONCE, only if absent, at exactly the path the
#     execution checker resolves. Tagging + schema come from the pipeline module.

#: The pipeline's ``DEFAULT_REGISTRY_PATH`` — the relative default the checker
#: composes with ``--data-root`` (``software_stops_liveness.resolve_registry_path``).
#: Pinned by ``test_default_registry_rel_matches_pipeline_default``; kept as a
#: local constant only so the signature is readable without the import.
DEFAULT_REGISTRY_REL = "data/rq105/software_stops.json"

#: Seed heartbeat budget when the caller does not pass one. Mirrors the
#: pipeline's ``DEFAULT_MAX_STALENESS_MINUTES`` (30.0); an existing file's value
#: is never touched by the seeder.
DEFAULT_SEED_MAX_STALENESS_MINUTES = 30.0

#: Exit codes for ``python -m renquant_orchestrator.software_stops_registry_contract seed``.
SEED_EXIT_OK = 0          # created, or an existing VALID file (no-op)
SEED_EXIT_USAGE = 1       # bad broker / bad arguments
SEED_EXIT_CORRUPT = 2     # an existing file fails the pipeline validator (untouched)
SEED_EXIT_IMPORT = 3      # renquant_pipeline.software_stops not importable (fail closed)


class SoftwareStopRegistryCorruptOnDisk(RuntimeError):
    """An existing registry file fails the pipeline's public validator.

    Raised by :func:`ensure_registry_seeded` INSTEAD of writing. The file is
    evidence (the same stance as the pipeline registry's own
    ``SoftwareStopRegistryCorrupt``): it is never replaced or repaired here.
    """

    def __init__(self, path: Path, error: str) -> None:
        self.path = path
        self.error = error
        super().__init__(f"registry {path} exists but is CORRUPT ({error}); left untouched")


def _pipeline_stops_module():
    """Deferred import of the owning repo's registry module — fail closed.

    Tagging (``registry_path_for``) and schema (``validate_software_stop_snapshot``,
    ``REGISTRY_VERSION``, ``REGISTRY_CONTRACT``) are the pipeline's; this
    repo never re-implements them. An import failure is surfaced as an
    ImportError with a message that says WHAT is missing and WHY it is not
    worked around, so a caller (the umbrella sell wrapper) sees a non-zero
    exit rather than a seed produced from a guessed schema.
    """
    try:
        # importlib (not ``from renquant_pipeline import software_stops``): the
        # ``from`` form reads the attribute off an already-imported package
        # and so cannot observe a missing/blocked submodule.
        mod = importlib.import_module("renquant_pipeline.software_stops")
    except ImportError as exc:
        raise ImportError(
            "software-stops registry seeder: cannot import "
            "renquant_pipeline.software_stops (the owning repo's registry module) — "
            f"{type(exc).__name__}: {exc}. FAIL CLOSED: broker tagging "
            "(registry_path_for) and the snapshot schema belong to renquant-pipeline "
            "and are never re-implemented here. Put the pinned renquant-pipeline "
            "checkout's src on PYTHONPATH."
        ) from exc
    for name in (
        "registry_path_for",
        "validate_software_stop_snapshot",
        "REGISTRY_VERSION",
        "REGISTRY_CONTRACT",
    ):
        if not hasattr(mod, name):
            raise ImportError(
                "software-stops registry seeder: renquant_pipeline.software_stops "
                f"lacks the public name {name!r} this seeder depends on — the pinned "
                "pipeline checkout predates the software-stops-v1 public contract "
                "(renquant-pipeline#192). FAIL CLOSED; nothing written."
            )
    return mod


def seeded_registry_path(
    state_root: str | Path,
    broker_name: str | None,
    *,
    registry_rel: str = DEFAULT_REGISTRY_REL,
) -> Path:
    """The exact path the execution checker resolves for ``--data-root
    <state_root> --broker <broker_name>``:
    ``Path(state_root) / registry_rel`` broker-tagged by the pipeline's
    ``registry_path_for`` (``software_stops.json`` + ``alpaca`` ->
    ``software_stops.alpaca.json``). Mirrors
    ``software_stops_liveness.resolve_registry_path`` step for step.

    NOTE: this is deliberately NOT :func:`software_stops_registry_path`
    (``<root>/software-stops/<broker>.json``) — that older name records the
    convention this module PROPOSED for a migrated writer; the checker never
    adopted it. The checker's composition is the contract the pager runs
    against, so it is the one the seeder follows.

    Raises ``ValueError`` (from the pipeline's broker allow-list) for a
    broker name that is not on ``state_paths.ALLOWED_BROKERS``.
    """
    mod = _pipeline_stops_module()
    return mod.registry_path_for(Path(state_root).expanduser() / registry_rel, broker_name)


def _empty_seed_snapshot(mod, *, max_staleness_minutes: float) -> dict:
    return {
        "version": mod.REGISTRY_VERSION,
        "contract": mod.REGISTRY_CONTRACT,
        "max_staleness_minutes": float(max_staleness_minutes),
        "last_evaluated_at": None,
        "stops": {},
    }


def _validate_existing(mod, path: Path) -> None:
    """Validate an existing file with the pipeline's PUBLIC validator; raise
    :class:`SoftwareStopRegistryCorruptOnDisk` on any failure. Read-only."""
    try:
        mod.validate_software_stop_snapshot(json.loads(path.read_text()))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise SoftwareStopRegistryCorruptOnDisk(path, f"{type(exc).__name__}: {exc}") from exc


def ensure_registry_seeded(
    state_root: str | Path,
    broker_name: str | None,
    *,
    max_staleness_minutes: float = DEFAULT_SEED_MAX_STALENESS_MINUTES,
    registry_rel: str = DEFAULT_REGISTRY_REL,
) -> Path:
    """Create an EMPTY, schema-valid software-stop registry at the checker's
    path — only if no file exists there. Idempotent. Returns the path.

    * Absent  -> parent dirs created; the seed (``stops: {}``,
      ``last_evaluated_at: null``, the given ``max_staleness_minutes``,
      ``version``/``contract`` from the pipeline module) is validated with
      the pipeline's public ``validate_software_stop_snapshot`` BEFORE it is
      published, written to a sibling tmp file, re-validated from the bytes
      on disk, then published atomically. Publication uses ``os.link``
      (create-exclusive) rather than ``os.replace``: both are atomic, but
      ``os.link`` REFUSES to clobber, so if the real writer creates the
      file between our existence check and our publish we lose the race
      cleanly instead of overwriting its first write. One INFO log line.
    * Present and valid -> no-op (byte-identical, mtime untouched). DEBUG.
    * Present and corrupt -> :class:`SoftwareStopRegistryCorruptOnDisk`;
      the file is left exactly as found. Repairing is a human decision.
    * ``renquant_pipeline.software_stops`` not importable -> ImportError,
      nothing written (the tagging and schema are never re-implemented).

    Why the seed is inert: it is exactly what the pipeline registry would
    persist on its own first write with no stops registered — the
    registry's ``_load`` reads it as "armed, empty", ``compute_staleness``
    reports ``n_stops=0 / stale=False``, and the checker's ``check()`` says
    OK. The only thing that changes is that the file EXISTS, so
    ``--validate-registry`` reports VALID instead of MISSING and a
    heartbeat that never arrives becomes observable.
    """
    mod = _pipeline_stops_module()
    if not isinstance(max_staleness_minutes, (int, float)) or not max_staleness_minutes > 0:
        raise ValueError(f"max_staleness_minutes must be a positive number, got {max_staleness_minutes!r}")
    path = seeded_registry_path(state_root, broker_name, registry_rel=registry_rel)

    if path.exists():
        _validate_existing(mod, path)
        log.debug("software-stops registry already present and valid at %s (no-op)", path)
        return path

    seed = mod.validate_software_stop_snapshot(
        _empty_seed_snapshot(mod, max_staleness_minutes=max_staleness_minutes)
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    # Unique tmp name: two seeders (or a seeder and the writer's own
    # ``.tmp``) must never share a scratch file.
    tmp = path.with_name(f"{path.name}.seed-{os.getpid()}.tmp")
    try:
        tmp.write_text(json.dumps(seed, indent=2, sort_keys=True))
        # Re-validate the BYTES that will be published, not the dict.
        mod.validate_software_stop_snapshot(json.loads(tmp.read_text()))
        try:
            os.link(tmp, path)
        except FileExistsError:
            # Lost the race to the real writer: its file wins, unconditionally.
            _validate_existing(mod, path)
            log.debug("software-stops registry appeared at %s during seeding (no-op)", path)
            return path
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
    log.info(
        "software-stops registry SEEDED (empty, schema-valid) at %s "
        "(broker=%s, max_staleness_minutes=%s)",
        path, broker_name, float(max_staleness_minutes),
    )
    return path


# --- CLI ------------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="python -m renquant_orchestrator.software_stops_registry_contract",
        description=(
            "Software-stop registry LOCATION contract — seed the empty registry "
            "file at the path the liveness checker resolves (writer migration step 1)."
        ),
    )
    sub = ap.add_subparsers(dest="command", required=True)
    seed = sub.add_parser(
        "seed",
        help="create an empty, schema-valid registry if (and only if) none exists",
    )
    seed.add_argument(
        "--broker", required=True,
        help="broker name for the file tag (must be on the pipeline's allow-list), e.g. alpaca",
    )
    seed.add_argument(
        "--max-staleness-minutes", type=float, default=DEFAULT_SEED_MAX_STALENESS_MINUTES,
        help="heartbeat budget written into a NEW seed only (default %(default)s); "
             "an existing file is never modified",
    )
    seed.add_argument(
        "--data-root", default=None,
        help="the checker's --data-root. Default: the neutral runtime-state root's "
             f"'{SOFTWARE_STOPS_REGISTRY_DIRNAME}' dir "
             f"(RENQUANT_RUNTIME_STATE_ROOT or {DEFAULT_RUNTIME_STATE_ROOT}/"
             f"{SOFTWARE_STOPS_REGISTRY_DIRNAME}) — the value "
             "deploy/com.renquant.stops-liveness.plist arms the pager with",
    )
    seed.add_argument(
        "--registry-rel", default=DEFAULT_REGISTRY_REL,
        help="relative registry path composed under --data-root (default: the "
             "pipeline's DEFAULT_REGISTRY_PATH, %(default)s)",
    )
    return ap


def main(argv: "list[str] | None" = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command != "seed":  # pragma: no cover - argparse enforces the choice
        return SEED_EXIT_USAGE
    data_root = (
        Path(args.data_root).expanduser()
        if args.data_root
        else software_stops_registry_root(runtime_state_root())
    )
    try:
        # Compute the path first so the verdict line can name it even on failure.
        path = seeded_registry_path(data_root, args.broker, registry_rel=args.registry_rel)
        existed = path.exists()
        ensure_registry_seeded(
            data_root, args.broker,
            max_staleness_minutes=args.max_staleness_minutes,
            registry_rel=args.registry_rel,
        )
    except ImportError as exc:
        print(f"SEED IMPORT-FAIL: {exc}", file=sys.stderr)
        return SEED_EXIT_IMPORT
    except SoftwareStopRegistryCorruptOnDisk as exc:
        print(f"SEED CORRUPT: {exc}", file=sys.stderr)
        return SEED_EXIT_CORRUPT
    except ValueError as exc:
        print(f"SEED USAGE-ERROR: {exc}", file=sys.stderr)
        return SEED_EXIT_USAGE
    verdict = "EXISTS" if existed else "SEEDED"
    print(f"{verdict}: {path} (broker={args.broker})")
    return SEED_EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    raise SystemExit(main())
