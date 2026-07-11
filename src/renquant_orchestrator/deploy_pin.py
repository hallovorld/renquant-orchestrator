"""deploy-pin — the R-PIN deployment-pin authority CLI (Stage 1: capture).

Design: doc/design/2026-07-11-deployment-pin-authority-migration.md (§5.1
schema, §5.2 neutral state root, §9 Stage 1).

Stage 1 ships exactly ONE subcommand:

``deploy-pin capture``
    Reads the DEPLOYED truth — the on-disk umbrella ``subrepos.lock.json``
    AND the actual materialized ``.subrepo_runtime`` clone HEADs — and
    FAILS CLOSED on ANY disagreement between them (every disagreement is
    reported, not just the first). On agreement it emits:

    * the PORTABLE deployment manifest (§5.1 — repo identity only:
      remote/branch/commit/role/status; no host path anywhere), and
    * the host runtime inventory (repo name → verified checkout path),

    to the NEUTRAL deployed-state root (§5.2 — default ``~/.renquant/deploy``,
    override ``--state-root`` / ``RENQUANT_DEPLOY_STATE_ROOT``).

    DRY-RUN by default: prints what would be written and touches NOTHING.
    ``--write`` persists (atomic writes; manifest first, then inventory,
    then the FORWARD-ONLY expected-generation record) and re-verifies the
    written pair read-only — the Stage-1 gate: capture output must match
    the on-disk lock AND the clone HEADs exactly.

READ-ONLY on the deployed trees: this command reads the lock file and runs
``git rev-parse`` in the runtime clones; it never writes the umbrella tree,
the lock, or any clone. The only mutation ``--write`` performs is creating
files under the neutral state root — which Stage 1 explicitly owns, and
which no consumer reads yet (rollback = delete a file no one consumes).

Explicit non-goals here (§9 Stages 3-4, never Stage 1): NO mirror
generation, NO apply, NO authority semantics — the on-disk lock remains
the pin authority; the emitted manifest is an unverified shadow record.

Evidence sealing: ``--evidence-ref store://<record>`` stamps the sealed
readonly-e2e verification evidence reference (the renquant-artifacts
#13/#14 mechanism). Without it the record is emitted in the pre-seal
``captured`` state; the durable commit of the first manifest (the Stage-1
follow-up PR) requires the sealed ``deployed`` state.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

from .deployment_manifest import (
    DEPLOYMENT_MANIFEST_KIND,
    DEPLOYMENT_MANIFEST_SCHEMA_VERSION,
    DeploymentManifestError,
    EVIDENCE_REF_PREFIX,
    GitProbe,
    READONLY_E2E_DEFAULT_ARGS,
    READONLY_E2E_PROFILE,
    build_runtime_inventory,
    check_checkout_state,
    default_git_probe,
    deploy_state_root,
    ensure_state_root_layout,
    load_deployment_manifest,
    load_runtime_inventory,
    manifest_content_sha256,
    read_expected_generation,
    record_expected_generation,
    sha256_of_bytes,
    state_root_paths,
    validate_deployment_manifest,
    verify_runtime_inventory,
    write_json_canonical,
)

#: Default on-disk lock = the deployed truth the 18 launchd jobs consume.
#: Single-sourced from repos.py (no second hardcode of the umbrella path).
from .repos import DEFAULT_MANIFEST as DEFAULT_LOCK_PATH

#: Materialized pinned clones live under the umbrella tree (relative to the
#: lock file's directory) until R1/R2 relocate them (design §11 non-goal).
RUNTIME_CLONES_RELATIVE = Path(".subrepo_runtime") / "repos"

DEFAULT_ARTIFACT_STORE_REPO = "renquant-artifacts"
DEFAULT_ARTIFACT_STORE_PATH = ""

#: Identity fields a lock subrepo entry must carry for the portable manifest.
_LOCK_IDENTITY_FIELDS = ("name", "remote", "branch", "commit", "role", "status")


class DeployPinError(RuntimeError):
    """A deploy-pin contract was violated (fail-closed, never best-effort)."""


def read_lock_subrepo_identity(lock_path: Path) -> list[dict[str, str]]:
    """The identity rows of the on-disk lock's ``subrepos`` list (fail-closed).

    Only IDENTITY fields are read out; the lock's host-bound fields
    (``local_path``, ``test_command``) never enter the result — they belong
    to the runtime inventory / the Stage-3 mirror compatibility table."""
    try:
        payload = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DeployPinError(
            f"on-disk lock {lock_path}: unreadable ({exc})"
        ) from exc
    subrepos = payload.get("subrepos")
    if not isinstance(subrepos, list) or not subrepos:
        raise DeployPinError(
            f"on-disk lock {lock_path}: no subrepos list — not a pin lock"
        )
    problems: list[str] = []
    entries: list[dict[str, str]] = []
    for idx, entry in enumerate(subrepos):
        if not isinstance(entry, dict):
            problems.append(f"subrepos[{idx}] is not an object")
            continue
        label = entry.get("name") or f"subrepos[{idx}]"
        missing = [
            field
            for field in _LOCK_IDENTITY_FIELDS
            if not isinstance(entry.get(field), str) or not entry.get(field)
        ]
        if missing:
            problems.append(
                f"{label}: missing/empty identity field(s) {missing} — the "
                "authority record cannot be captured without full identity"
            )
            continue
        entries.append({field: str(entry[field]) for field in _LOCK_IDENTITY_FIELDS})
    if problems:
        raise DeployPinError(
            f"on-disk lock {lock_path}: identity extraction failed "
            "(fail-closed): " + "; ".join(problems)
        )
    names = [entry["name"] for entry in entries]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise DeployPinError(
            f"on-disk lock {lock_path}: duplicate subrepo name(s) {duplicates}"
        )
    return entries


def capture_deployed_state(
    *,
    lock_path: Path,
    runtime_root: Path | None = None,
    git_probe: GitProbe | None = None,
) -> tuple[list[dict[str, str]], dict[str, Path]]:
    """Read lock + clone HEADs; FAIL CLOSED on any disagreement (all listed).

    Returns ``(lock_identity_entries, {name: verified_clone_path})`` — the
    two inputs the portable manifest and the host inventory are built from.
    """
    probe = git_probe or default_git_probe
    entries = read_lock_subrepo_identity(lock_path)
    clones_root = (
        runtime_root
        if runtime_root is not None
        else lock_path.parent / RUNTIME_CLONES_RELATIVE
    )
    disagreements: list[str] = []
    clone_paths: dict[str, Path] = {}
    for entry in entries:
        name = entry["name"]
        clone = clones_root / name
        commit, problem = check_checkout_state(
            name,
            clone,
            entry["commit"],
            git_probe=probe,
            require_clean=False,
            expected_label="on-disk lock commit",
        )
        if problem is not None:
            disagreements.append(problem)
            continue
        assert commit is not None
        if commit != entry["commit"]:
            # check_checkout_state accepts a >=12-hex prefix; the DEPLOYED
            # truth must agree on the FULL sha (a short lock commit cannot
            # anchor the authority record).
            disagreements.append(
                f"{name}: on-disk lock commit {entry['commit']!r} is not the "
                f"full clone HEAD {commit}"
            )
            continue
        clone_paths[name] = clone
    if disagreements:
        raise DeployPinError(
            "deployed truth DISAGREES (fail-closed; the capture records "
            "nothing until the on-disk lock and the materialized "
            f".subrepo_runtime clone HEADs agree) [{len(disagreements)} "
            "problem(s)]: " + "; ".join(disagreements)
        )
    return entries, clone_paths


def _next_epoch(state_root: Path) -> tuple[int, str | None]:
    """``(generation, supersedes_sha256)`` for a new capture at this root.

    First capture ⇒ ``(1, None)``. A prior machine manifest must agree with
    the expected-generation record (content hash AND generation) or the
    capture REFUSES — a torn or stale state root is never silently extended
    (recovery in Stage 1 is deleting the state root: nothing consumes it)."""
    paths = state_root_paths(state_root)
    manifest_path = paths["manifest"]
    expected = read_expected_generation(state_root)
    if not manifest_path.exists() and expected is None:
        return 1, None
    if manifest_path.exists() != (expected is not None):
        raise DeployPinError(
            f"state root {state_root} is TORN: "
            f"{'machine manifest without an expected-generation record' if manifest_path.exists() else 'expected-generation record without a machine manifest'}"
            " — refusing to extend it (Stage 1 recovery: delete the state "
            "root, which nothing consumes yet)"
        )
    assert expected is not None
    prior_bytes = manifest_path.read_bytes()
    prior_sha = sha256_of_bytes(prior_bytes)
    if prior_sha != expected["manifest_sha256"]:
        raise DeployPinError(
            f"state root {state_root} is STALE/TORN: machine manifest sha256 "
            f"{prior_sha[:12]} != expected-generation record "
            f"{expected['manifest_sha256'][:12]} — refusing to extend it"
        )
    prior = load_deployment_manifest(manifest_path)
    if prior["generation"] != expected["generation"]:
        raise DeployPinError(
            f"state root {state_root} is TORN: machine manifest generation "
            f"{prior['generation']} != expected-generation record "
            f"{expected['generation']}"
        )
    return expected["generation"] + 1, prior_sha


def build_deployment_manifest_payload(
    *,
    entries: list[dict[str, str]],
    generation: int,
    supersedes_sha256: str | None,
    deployed_by: str,
    deployed_at: str | None,
    evidence_ref: str | None,
    artifact_store_repo: str,
    artifact_store_path: str,
) -> dict[str, Any]:
    """Assemble + self-validate the PORTABLE manifest (§5.1) from lock identity."""
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload: dict[str, Any] = {
        "schema_version": DEPLOYMENT_MANIFEST_SCHEMA_VERSION,
        "kind": DEPLOYMENT_MANIFEST_KIND,
        "generation": generation,
        "generated_at": now,
        "repos": {
            entry["name"]: {
                "remote": entry["remote"],
                "branch": entry["branch"],
                "commit": entry["commit"],
                "role": entry["role"],
                "status": entry["status"],
            }
            for entry in entries
        },
        "artifact_store": {
            "repo": artifact_store_repo,
            "path": artifact_store_path,
        },
        "deployment": {
            "deployed_at": deployed_at or now,
            "deployed_by": deployed_by,
            "verify": {
                "profile": READONLY_E2E_PROFILE,
                "args": dict(READONLY_E2E_DEFAULT_ARGS),
                "exit": 0,
                "evidence_ref": evidence_ref,
            },
            "state": "deployed" if evidence_ref else "captured",
            "supersedes_sha256": supersedes_sha256,
        },
    }
    # Self-check: the capture must never emit a document its own loader
    # rejects (schema + allowlisted profile + portability sweep).
    return validate_deployment_manifest(payload, source="captured manifest")


def run_capture(
    *,
    lock_path: Path,
    runtime_root: Path | None,
    state_root: Path,
    write: bool,
    deployed_by: str,
    deployed_at: str | None,
    evidence_ref: str | None,
    artifact_store_repo: str,
    artifact_store_path: str,
    git_probe: GitProbe | None = None,
    stdout: Any = None,
) -> int:
    out = stdout or sys.stdout
    probe = git_probe or default_git_probe
    entries, clone_paths = capture_deployed_state(
        lock_path=lock_path, runtime_root=runtime_root, git_probe=probe
    )
    generation, supersedes = _next_epoch(state_root)
    manifest = build_deployment_manifest_payload(
        entries=entries,
        generation=generation,
        supersedes_sha256=supersedes,
        deployed_by=deployed_by,
        deployed_at=deployed_at,
        evidence_ref=evidence_ref,
        artifact_store_repo=artifact_store_repo,
        artifact_store_path=artifact_store_path,
    )
    inventory = build_runtime_inventory(
        {name: path.resolve() for name, path in clone_paths.items()}
    )
    # The emitted pair must verify against itself before anything is
    # reported or written: every inventory path's HEAD == manifest commit.
    verify_runtime_inventory(manifest, inventory, git_probe=probe)

    paths = state_root_paths(state_root)
    report: dict[str, Any] = {
        "mode": "write" if write else "dry-run",
        "state_root": str(state_root),
        "manifest_sha256": manifest_content_sha256(manifest),
        "manifest": manifest,
        "runtime_inventory": inventory,
        "written": [],
    }
    if not write:
        report["would_write"] = [
            str(paths["manifest"]),
            str(paths["inventory"]),
            str(paths["expected_generation"]),
            str(paths["receipts"]) + "/",
        ]
        json.dump(report, out, indent=2, sort_keys=True)
        out.write("\n")
        return 0

    ensure_state_root_layout(state_root)
    manifest_sha = write_json_canonical(paths["manifest"], manifest)
    write_json_canonical(paths["inventory"], inventory)
    # FORWARD-ONLY epoch record, written AFTER the manifest (§5.2) — a crash
    # between the two writes is a detectable torn state, never a silent one.
    record_expected_generation(
        state_root, generation=generation, manifest_sha256=manifest_sha
    )
    report["written"] = [
        str(paths["manifest"]),
        str(paths["inventory"]),
        str(paths["expected_generation"]),
    ]
    # Read-only re-verification of what actually landed on disk — the
    # Stage-1 gate evidence (capture output matches lock AND clone HEADs).
    reloaded = load_deployment_manifest(paths["manifest"])
    resolved = verify_runtime_inventory(
        reloaded, load_runtime_inventory(paths["inventory"]), git_probe=probe
    )
    report["reverified"] = {
        "manifest_sha256": manifest_sha,
        "repos": resolved,
    }
    json.dump(report, out, indent=2, sort_keys=True)
    out.write("\n")
    return 0


def _validate_evidence_ref_arg(value: str) -> str:
    if not value.startswith(EVIDENCE_REF_PREFIX) or len(value) <= len(
        EVIDENCE_REF_PREFIX
    ):
        raise argparse.ArgumentTypeError(
            f"--evidence-ref must be a content-addressed "
            f"{EVIDENCE_REF_PREFIX}<record> reference, got {value!r}"
        )
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="renquant-orchestrator deploy-pin",
        description=(
            "R-PIN deployment-pin authority CLI (Stage 1: capture only — "
            "no mirror, no apply, no authority flip)"
        ),
    )
    sub = parser.add_subparsers(dest="subcommand", required=True)
    capture = sub.add_parser(
        "capture",
        help=(
            "read the deployed truth (on-disk lock + .subrepo_runtime clone "
            "HEADs, fail-closed on disagreement) and emit the portable "
            "manifest + host inventory to the neutral state root"
        ),
    )
    capture.add_argument(
        "--lock",
        type=Path,
        default=DEFAULT_LOCK_PATH,
        help=f"on-disk umbrella lock to read (default: {DEFAULT_LOCK_PATH})",
    )
    capture.add_argument(
        "--runtime-root",
        type=Path,
        default=None,
        help=(
            "materialized clones root (default: <lock dir>/"
            f"{RUNTIME_CLONES_RELATIVE})"
        ),
    )
    capture.add_argument(
        "--state-root",
        type=Path,
        default=None,
        help=(
            "neutral deployed-state root (default: $RENQUANT_DEPLOY_STATE_ROOT "
            "or ~/.renquant/deploy)"
        ),
    )
    capture.add_argument(
        "--write",
        action="store_true",
        help="persist to the state root (default: dry-run, writes NOTHING)",
    )
    capture.add_argument(
        "--deployed-by",
        default="operator",
        help="who performed/verified the deployment being recorded",
    )
    capture.add_argument(
        "--deployed-at",
        default=None,
        help=(
            "ISO-8601 time the recorded state was actually deployed "
            "(default: capture time)"
        ),
    )
    capture.add_argument(
        "--evidence-ref",
        type=_validate_evidence_ref_arg,
        default=None,
        help=(
            "sealed store://<record> reference to the readonly-e2e "
            "verification evidence in renquant-artifacts; without it the "
            "record is emitted in the pre-seal 'captured' state"
        ),
    )
    capture.add_argument(
        "--artifact-store-repo",
        default=DEFAULT_ARTIFACT_STORE_REPO,
        help="manifest repo that owns the pinned artifact store",
    )
    capture.add_argument(
        "--artifact-store-path",
        default=DEFAULT_ARTIFACT_STORE_PATH,
        help="relative store subdir inside the artifact-store repo",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.subcommand != "capture":  # pragma: no cover — argparse enforces
        parser.error(f"unknown subcommand {args.subcommand!r}")
    state_root = deploy_state_root(args.state_root)
    try:
        return run_capture(
            lock_path=args.lock,
            runtime_root=args.runtime_root,
            state_root=state_root,
            write=args.write,
            deployed_by=args.deployed_by,
            deployed_at=args.deployed_at,
            evidence_ref=args.evidence_ref,
            artifact_store_repo=args.artifact_store_repo,
            artifact_store_path=args.artifact_store_path,
        )
    except (DeployPinError, DeploymentManifestError) as exc:
        print(f"deploy-pin capture FAILED (fail-closed): {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
