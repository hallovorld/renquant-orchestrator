"""Deployment-manifest schema v1 + loader/verifier — R-PIN Stage 1 shared module.

Design: doc/design/2026-07-11-deployment-pin-authority-migration.md (§5.1
schema, §5.2 neutral state root, §7.1 transition contract, §9 Stage 1).

This module is the SINGLE implementation of the manifest conventions proven
by the D6-§2a shadow-AB run manifest (design §2.3): the git-probe injection
point, the checkout HEAD/clean verification core, the ``artifact_store``
``{repo, path}`` schema validation, and the resolve-and-contain store-root
resolution are LIFTED here and imported back by
:mod:`~renquant_orchestrator.shadow_ab_runner` — never a third hand-copy
(the calibrator/scorer fingerprint triple-impl lesson).

Two manifest kinds share those conventions:

* the **run manifest** (shadow-AB experiment plane) — host paths + commits,
  owned by :mod:`~renquant_orchestrator.shadow_ab_runner`, unchanged;
* the **deployment manifest** (this module) — the PORTABLE pin-authority
  document (§5.1): repo IDENTITY only (remote/branch/commit/role/status),
  monotonic ``generation`` epoch, ``artifact_store`` binding, and a
  ``deployment`` record whose ``verify`` names an ALLOWLISTED profile with
  structured args and whose ``evidence_ref`` is a ``store://``
  content-addressed record — never free-form shell, never a local log path.
  ``evidence_ref`` always travels with ``evidence_repo_commit`` — the exact
  40-hex commit of the ``artifact_store`` sibling checkout the evidence was
  resolved from (Codex CHANGES_REQUESTED follow-up on orchestrator#483: an
  evidence bundle sealed by a LATER PR than the pinned artifacts commit is
  legitimate, but ``deploy-pin verify`` must resolve that EXACT revision,
  never whichever sibling checkout happens to be currently on disk).

Host-side state lives in the NEUTRAL deployed-state root (§5.2 — default
``~/.renquant/deploy/``, override ``RENQUANT_DEPLOY_STATE_ROOT``; not inside
any repo):

* ``deployment-manifest.json`` — the machine's operational copy;
* ``runtime-inventory.json``   — per-host repo-name → checkout-path map,
  verified HEAD==manifest-commit at read;
* ``expected-generation.json`` — the durable epoch record, FORWARD-ONLY
  (atomic write; any decrease refused);
* ``receipts/``                — emergency-lane receipts (Stage 3+).

Stage 1 scope: schema + loader/verifier + neutral-root support + the §7.1
transition-predicate helpers (pure functions, consumed by later stages).
NO mirror generation, NO apply, NO authority semantics — the on-disk
umbrella lock remains the authority; the manifest is an unverified shadow
record consumed by nothing (§8 stage-1 row).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import socket
import subprocess
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

# --- schema constants ------------------------------------------------------------

DEPLOYMENT_MANIFEST_SCHEMA_VERSION = 1
DEPLOYMENT_MANIFEST_KIND = "deployment-manifest"

RUNTIME_INVENTORY_SCHEMA_VERSION = 1
RUNTIME_INVENTORY_KIND = "runtime-inventory"

EXPECTED_GENERATION_SCHEMA_VERSION = 1
EXPECTED_GENERATION_KIND = "expected-generation"

#: §5.1 — repo entries carry repo IDENTITY only. Exactly these keys, all
#: required: an entry carrying anything else (``local_path``,
#: ``test_command``, …) is rejected, which is what makes portability a
#: mechanical property instead of a convention.
REPO_IDENTITY_KEYS = ("remote", "branch", "commit", "role", "status")

_MANIFEST_TOP_LEVEL_KEYS = (
    "schema_version",
    "kind",
    "generation",
    "generated_at",
    "repos",
    "artifact_store",
    "deployment",
)
_DEPLOYMENT_KEYS = (
    "deployed_at",
    "deployed_by",
    "verify",
    "state",
    "supersedes_sha256",
)
_VERIFY_KEYS = ("profile", "args", "exit", "evidence_ref", "evidence_repo_commit")

#: ``deployment.state`` values. ``deployed`` is the durable record state
#: (§5.1) and REQUIRES a sealed ``store://`` evidence_ref. ``captured`` is
#: the Stage-1 pre-seal capture state: ``deploy-pin capture`` emitted the
#: record but the verification evidence has not yet been sealed into
#: renquant-artifacts — ``evidence_ref`` may be null ONLY in this state,
#: and the record must be promoted to ``deployed`` (evidence sealed) before
#: it is committed as the durable manifest.
DEPLOYMENT_STATES = ("deployed", "captured")

EVIDENCE_REF_PREFIX = "store://"

_FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_WINDOWS_PATH_RE = re.compile(r"^[A-Za-z]:[\\/]")

MACHINE_MANIFEST_FILENAME = "deployment-manifest.json"
RUNTIME_INVENTORY_FILENAME = "runtime-inventory.json"
EXPECTED_GENERATION_FILENAME = "expected-generation.json"
RECEIPTS_DIRNAME = "receipts"

DEPLOY_STATE_ROOT_ENV = "RENQUANT_DEPLOY_STATE_ROOT"
DEFAULT_DEPLOY_STATE_ROOT = Path("~/.renquant/deploy")

#: Generation-vs-expected-record classification (§5.2): less than the
#: durable record ⇒ a stale/replayed manifest pair; greater ⇒ a torn apply
#: (crash between manifest write and record write). Both abort consumers
#: once armed (Stage 3+).
GENERATION_OK = "ok"
GENERATION_STALE_OR_REPLAYED = "stale_or_replayed"
GENERATION_TORN_APPLY = "torn_apply"


class DeploymentManifestError(RuntimeError):
    """A deployment-manifest / state-root contract was violated (fail-closed)."""


# --- shared conventions lifted from shadow_ab_runner (design §2.3) ----------------

GitProbe = Callable[[Sequence[str]], "subprocess.CompletedProcess[str]"]


def default_git_probe(args: Sequence[str]) -> "subprocess.CompletedProcess[str]":
    """The one injectable git authority shared by every manifest verifier."""
    return subprocess.run(
        ["git", *args],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def check_checkout_state(
    name: str,
    path: Path,
    expected_commit: str,
    *,
    git_probe: GitProbe | None = None,
    require_clean: bool = True,
    expected_label: str = "manifest commit",
) -> tuple[str | None, str | None]:
    """The ONE checkout-verification core behind every manifest consumer.

    Checks (i) the path exists, (ii) it is a git checkout whose HEAD matches
    ``expected_commit`` (exact, or expected prefix of >= 12 hex chars), and
    (iii) — when ``require_clean`` — the working tree is CLEAN. Returns
    ``(resolved_full_commit, None)`` on success or ``(None, problem)`` on
    the first failure; callers collect problems and fail closed. The problem
    strings are the exact fail-closed messages the shadow-AB run-manifest
    verifier has always emitted (behavior-invariant lift).
    """
    probe = git_probe or default_git_probe
    expected = str(expected_commit).strip()
    if not path.is_dir():
        return None, f"{name}: path {path} does not exist"
    head = probe(["-C", str(path), "rev-parse", "HEAD"])
    if head.returncode != 0:
        return None, f"{name}: not a git checkout ({(head.stderr or '').strip()})"
    actual = (head.stdout or "").strip()
    matches = actual == expected or (
        len(expected) >= 12 and actual.startswith(expected)
    )
    if not matches:
        return None, (
            f"{name}: checkout HEAD {actual[:12]} != {expected_label} "
            f"{expected[:12]}"
        )
    if require_clean:
        status = probe(["-C", str(path), "status", "--porcelain"])
        if status.returncode != 0:
            return None, f"{name}: git status failed"
        if (status.stdout or "").strip():
            dirty = (status.stdout or "").strip().splitlines()
            return None, (
                f"{name}: working tree DIRTY ({len(dirty)} path(s), e.g. "
                f"{dirty[0][:60]!r})"
            )
    return actual, None


def artifact_store_schema_problems(
    store: Any,
    *,
    repo_names: Sequence[str] | set[str],
) -> list[str]:
    """Schema problems for an ``artifact_store`` entry — the #464 binding.

    The store is NOT an arbitrary path: it must name a manifest repo (an
    untyped path can point straight back at the deprecated umbrella tree)
    plus a RELATIVE subdir inside it. Returns problem bodies in check order
    (callers prefix their own manifest context); an empty list means valid.
    """
    if not isinstance(store, dict) or not store.get("repo"):
        return [
            "artifact_store must be "
            "{'repo': <manifest repo name>, 'path': <relative subdir>} — "
            "a bare path is not a pinned owner"
        ]
    problems: list[str] = []
    if store["repo"] not in repo_names:
        problems.append(
            f"artifact_store.repo {store['repo']!r} is not a manifest repo — "
            "the store must live inside a pinned, verified checkout"
        )
    subdir = store.get("path") or ""
    sub_path = Path(subdir)
    if sub_path.is_absolute() or ".." in sub_path.parts:
        problems.append(
            "artifact_store.path must be a relative subdir inside the named "
            f"repo, got {subdir!r}"
        )
    return problems


def resolve_contained_subdir(
    repo_path: str | Path,
    subdir: str,
    *,
    error_cls: type[Exception],
    store_repr: str,
) -> Path:
    """resolve-and-contain: the resolved subdir must stay INSIDE the repo.

    A committed symlink at the store subdir may not point resolution outside
    the verified checkout. Escape raises ``error_cls`` (fail-closed)."""
    repo_root_resolved = Path(repo_path).resolve()
    store_root = (Path(repo_path) / (subdir or "")).resolve()
    if not store_root.is_relative_to(repo_root_resolved):
        raise error_cls(
            f"artifact_store escapes its named repo (fail-closed): "
            f"{store_repr} resolves to {store_root}, outside {repo_root_resolved}"
        )
    return store_root


# --- verification profiles (§5.1: no free-form shell in the authority doc) --------


def _readonly_e2e_args_problems(args: Any) -> list[str]:
    if not isinstance(args, dict):
        return ["deployment.verify.args must be a structured object"]
    problems: list[str] = []
    unknown = sorted(set(args) - {"min_admits"})
    if unknown:
        problems.append(
            f"deployment.verify.args carries unknown key(s) {unknown} for "
            "profile 'readonly-e2e' (allowed: ['min_admits'])"
        )
    if "min_admits" in args:
        value = args["min_admits"]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            problems.append(
                "deployment.verify.args.min_admits must be a non-negative "
                f"integer, got {value!r}"
            )
    return problems


#: The code-owned ALLOWLIST of verification profiles (§5.1). v1 contains
#: exactly the readonly-e2e profile (the promote flow's e2e verify step,
#: default args ``{"min_admits": 1}`` — the still-buys guard). A reviewed
#: manifest can never smuggle deployment-side code execution: the profile
#: NAME selects reviewed code here; args are structured data validated per
#: profile.
VERIFY_PROFILE_ALLOWLIST: dict[str, Callable[[Any], list[str]]] = {
    "readonly-e2e": _readonly_e2e_args_problems,
}

READONLY_E2E_PROFILE = "readonly-e2e"
READONLY_E2E_DEFAULT_ARGS: dict[str, int] = {"min_admits": 1}


# --- canonical content + hashing ---------------------------------------------------


def canonical_manifest_bytes(payload: Mapping[str, Any]) -> bytes:
    """The exact bytes written to disk and hashed — one canonical form."""
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def manifest_content_sha256(payload: Mapping[str, Any]) -> str:
    """Bare 64-hex sha256 of the canonical manifest content (§5.1 chaining)."""
    return hashlib.sha256(canonical_manifest_bytes(payload)).hexdigest()


def sha256_of_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def repo_identity_digest(entries: Sequence[Mapping[str, str]]) -> str:
    """sha256 binding repo IDENTITY rows to one canonical digest.

    ``entries`` is a list of ``{"name", *REPO_IDENTITY_KEYS}`` dicts — the
    shape both :func:`~renquant_orchestrator.deploy_pin.read_lock_subrepo_identity`
    (an on-disk lock reading) and :func:`manifest_repo_identity_entries` (a
    committed deployment manifest's own ``repos`` reading) produce.

    Used by ``deploy-pin verify`` (R-PIN Stage 1 evidence-binding follow-up,
    Codex CHANGES_REQUESTED on orchestrator#483) to bind a sealed evidence
    bundle's INDEPENDENTLY read source-lock digest and materialized-runtime
    -inventory digest to the manifest's own recorded commits, without
    requiring host filesystem access (the lock file, the ``.subrepo_runtime``
    clones) at verify time — only the manifest and the sealed bundle."""
    canonical = sorted(
        (
            {
                "name": str(entry["name"]),
                **{key: str(entry[key]) for key in REPO_IDENTITY_KEYS},
            }
            for entry in entries
        ),
        key=lambda entry: entry["name"],
    )
    data = (json.dumps(canonical, indent=2, sort_keys=True) + "\n").encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def manifest_repo_identity_entries(manifest: Mapping[str, Any]) -> list[dict[str, str]]:
    """A committed deployment manifest's own ``repos`` mapping, reshaped into
    :func:`repo_identity_digest` input form (name + the 5 identity fields),
    sorted by name."""
    repos = manifest.get("repos") or {}
    return [
        {
            "name": str(name),
            **{key: str(entry[key]) for key in REPO_IDENTITY_KEYS},
        }
        for name, entry in sorted(repos.items())
    ]


def _utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_json_canonical(path: Path, payload: Mapping[str, Any]) -> str:
    """Atomic canonical write (temp + ``os.replace``); returns the content sha256."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = canonical_manifest_bytes(payload)
    tmp = path.with_suffix(
        path.suffix + f".tmp.{os.getpid()}.{int(time.time() * 1000)}"
    )
    tmp.write_bytes(data)
    os.replace(tmp, path)
    return sha256_of_bytes(data)


# --- portability (§5.1: PORTABLE — no host paths) ----------------------------------


def portability_problems(payload: Any, _crumb: str = "$") -> list[str]:
    """Mechanical no-host-paths sweep over every string VALUE in the document.

    Absolute POSIX paths, ``~``-anchored paths, and Windows drive paths are
    all rejected wherever they appear — a manifest that names a host location
    anywhere is not portable and is refused, not warned about."""
    problems: list[str] = []
    if isinstance(payload, str):
        if (
            payload.startswith("/")
            or payload == "~"
            or payload.startswith("~/")
            or _WINDOWS_PATH_RE.match(payload)
        ):
            problems.append(
                f"{_crumb}: host path {payload!r} in a PORTABLE document "
                "(§5.1: repo identity only; host paths live in the runtime "
                "inventory)"
            )
    elif isinstance(payload, Mapping):
        for key in sorted(payload):
            problems.extend(portability_problems(payload[key], f"{_crumb}.{key}"))
    elif isinstance(payload, (list, tuple)):
        for idx, item in enumerate(payload):
            problems.extend(portability_problems(item, f"{_crumb}[{idx}]"))
    return problems


# --- deployment-manifest schema v1 (§5.1) ------------------------------------------


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _iso8601_problem(value: Any, field: str) -> str | None:
    if not isinstance(value, str) or not value:
        return f"{field} must be a non-empty ISO-8601 timestamp string"
    try:
        dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return f"{field} is not a parseable ISO-8601 timestamp: {value!r}"
    return None


def _repo_entry_problems(name: str, entry: Any) -> list[str]:
    if not isinstance(entry, dict):
        return [f"repos[{name!r}] must be an object"]
    problems: list[str] = []
    unknown = sorted(set(entry) - set(REPO_IDENTITY_KEYS))
    if unknown:
        problems.append(
            f"repos[{name!r}] carries non-identity key(s) {unknown} — the "
            f"portable schema allows exactly {list(REPO_IDENTITY_KEYS)} "
            "(host paths / test_command never enter the authority document)"
        )
    for key in REPO_IDENTITY_KEYS:
        value = entry.get(key)
        if not isinstance(value, str) or not value:
            problems.append(f"repos[{name!r}].{key} must be a non-empty string")
    commit = entry.get("commit")
    if isinstance(commit, str) and commit and not _FULL_SHA_RE.match(commit):
        problems.append(
            f"repos[{name!r}].commit must be a full 40-hex lowercase sha, "
            f"got {commit!r}"
        )
    return problems


def _verify_block_problems(verify: Any) -> list[str]:
    if not isinstance(verify, dict):
        return ["deployment.verify must be an object"]
    problems: list[str] = []
    unknown = sorted(set(verify) - set(_VERIFY_KEYS))
    if unknown:
        problems.append(f"deployment.verify carries unknown key(s) {unknown}")
    profile = verify.get("profile")
    validator = VERIFY_PROFILE_ALLOWLIST.get(profile) if isinstance(profile, str) else None
    if validator is None:
        problems.append(
            f"deployment.verify.profile {profile!r} is not in the code-owned "
            f"allowlist {sorted(VERIFY_PROFILE_ALLOWLIST)} — the authority "
            "document names reviewed profiles, never free-form commands"
        )
    else:
        problems.extend(validator(verify.get("args")))
    if not _is_int(verify.get("exit")):
        problems.append("deployment.verify.exit must be an integer")
    return problems


def _evidence_ref_problems(
    evidence_ref: Any, evidence_repo_commit: Any, state: Any
) -> list[str]:
    """Schema problems for the ``evidence_ref``/``evidence_repo_commit`` pair.

    Codex CHANGES_REQUESTED follow-up on orchestrator#483 (the
    checkout-identity gap): a sealed ``evidence_ref`` alone only proves the
    referenced bytes exist somewhere in the named ``artifact_store`` repo —
    ``deploy-pin verify`` used to resolve it through whatever sibling
    checkout happened to be currently on disk, which can be arbitrarily
    AHEAD of the revision the evidence was actually sealed at (exactly the
    case here: the manifest pins ``renquant-artifacts`` at one commit, but
    the evidence bundle was added later by a follow-up PR). Binding
    ``evidence_repo_commit`` — the artifact_store sibling checkout's exact
    HEAD at capture time — lets ``deploy-pin verify`` reject a sibling
    checkout that has since moved on, instead of silently trusting it.

    The two fields travel together: whenever ``evidence_ref`` is sealed
    (non-null), ``evidence_repo_commit`` MUST also be a full 40-hex commit
    naming the exact artifact_store revision it was resolved from; in the
    pre-seal ``captured`` state (``evidence_ref`` null) there is nothing to
    bind yet, so ``evidence_repo_commit`` must be null too — one may never
    be present without the other."""
    if evidence_ref is None:
        problems: list[str] = []
        if state != "captured":
            problems.append(
                "deployment.verify.evidence_ref is required for state "
                f"{state!r} — a deployed record must reference sealed "
                "store:// evidence (null is allowed only in the pre-seal "
                "'captured' state)"
            )
        if evidence_repo_commit is not None:
            problems.append(
                "deployment.verify.evidence_repo_commit must be null when "
                "evidence_ref is null — a resolved artifact_store sibling-"
                "checkout revision cannot exist without the sealed evidence "
                "it was resolved for (pre-seal 'captured' state only)"
            )
        return problems
    problems = []
    if not isinstance(evidence_ref, str) or not evidence_ref.startswith(
        EVIDENCE_REF_PREFIX
    ):
        problems.append(
            "deployment.verify.evidence_ref must be a content-addressed "
            f"{EVIDENCE_REF_PREFIX!r} record (never a local log path), "
            f"got {evidence_ref!r}"
        )
    else:
        remainder = evidence_ref[len(EVIDENCE_REF_PREFIX):]
        if not remainder or remainder.startswith("/") or ".." in Path(remainder).parts:
            problems.append(
                f"deployment.verify.evidence_ref {evidence_ref!r} has an "
                "empty or non-relative store record reference"
            )
    if (
        not isinstance(evidence_repo_commit, str)
        or not _FULL_SHA_RE.match(evidence_repo_commit)
    ):
        problems.append(
            "deployment.verify.evidence_repo_commit must be a full 40-hex "
            "lowercase sha naming the EXACT artifact_store sibling-checkout "
            "revision the sealed evidence_ref was resolved from (never null "
            f"once evidence_ref is sealed), got {evidence_repo_commit!r}"
        )
    return problems


def _deployment_block_problems(deployment: Any, generation: Any) -> list[str]:
    if not isinstance(deployment, dict):
        return ["deployment must be an object"]
    problems: list[str] = []
    unknown = sorted(set(deployment) - set(_DEPLOYMENT_KEYS))
    if unknown:
        problems.append(f"deployment carries unknown key(s) {unknown}")
    if problem := _iso8601_problem(deployment.get("deployed_at"), "deployment.deployed_at"):
        problems.append(problem)
    deployed_by = deployment.get("deployed_by")
    if not isinstance(deployed_by, str) or not deployed_by:
        problems.append("deployment.deployed_by must be a non-empty string")
    state = deployment.get("state")
    if state not in DEPLOYMENT_STATES:
        problems.append(
            f"deployment.state {state!r} not in {list(DEPLOYMENT_STATES)}"
        )
    verify = deployment.get("verify")
    problems.extend(_verify_block_problems(verify))
    if isinstance(verify, dict):
        problems.extend(
            _evidence_ref_problems(
                verify.get("evidence_ref"), verify.get("evidence_repo_commit"), state
            )
        )
    supersedes = deployment.get("supersedes_sha256")
    if supersedes is None:
        if _is_int(generation) and generation != 1:
            problems.append(
                "deployment.supersedes_sha256 may be null only for "
                f"generation 1 (the first record); generation {generation} "
                "must chain to its predecessor's content sha256"
            )
    elif not isinstance(supersedes, str) or not _SHA256_RE.match(supersedes):
        problems.append(
            "deployment.supersedes_sha256 must be a 64-hex sha256 (or null "
            f"for generation 1), got {supersedes!r}"
        )
    return problems


def deployment_manifest_problems(payload: Any) -> list[str]:
    """Every schema-v1 problem in the document (empty list == valid)."""
    if not isinstance(payload, dict):
        return ["deployment manifest must be a JSON object"]
    problems: list[str] = []
    unknown = sorted(set(payload) - set(_MANIFEST_TOP_LEVEL_KEYS))
    if unknown:
        problems.append(f"unknown top-level key(s) {unknown}")
    schema_version = payload.get("schema_version")
    if not _is_int(schema_version) or schema_version != DEPLOYMENT_MANIFEST_SCHEMA_VERSION:
        problems.append(
            f"schema_version must be {DEPLOYMENT_MANIFEST_SCHEMA_VERSION}, "
            f"got {schema_version!r}"
        )
    if payload.get("kind") != DEPLOYMENT_MANIFEST_KIND:
        problems.append(
            f"kind must be {DEPLOYMENT_MANIFEST_KIND!r}, got {payload.get('kind')!r}"
        )
    generation = payload.get("generation")
    if not _is_int(generation) or generation < 1:
        problems.append(
            f"generation must be an integer >= 1 (monotonic epoch), got "
            f"{generation!r}"
        )
    if problem := _iso8601_problem(payload.get("generated_at"), "generated_at"):
        problems.append(problem)
    repos = payload.get("repos")
    if not isinstance(repos, dict) or not repos:
        problems.append("repos must be a non-empty object of {name: identity}")
    else:
        for name in sorted(repos):
            problems.extend(_repo_entry_problems(name, repos[name]))
    store = payload.get("artifact_store")
    if store is None:
        problems.append(
            "artifact_store is required — the deployment plane declares its "
            "pinned artifact store (the #464 binding)"
        )
    else:
        repo_names = set(repos) if isinstance(repos, dict) else set()
        problems.extend(
            artifact_store_schema_problems(store, repo_names=repo_names)
        )
        if isinstance(store, dict):
            unknown_store = sorted(set(store) - {"repo", "path"})
            if unknown_store:
                problems.append(
                    f"artifact_store carries unknown key(s) {unknown_store} "
                    "— only ['repo', 'path'] are allowed in the authority "
                    "document"
                )
    problems.extend(_deployment_block_problems(payload.get("deployment"), generation))
    problems.extend(portability_problems(payload))
    return problems


def validate_deployment_manifest(
    payload: Any, *, source: str = "deployment manifest"
) -> dict[str, Any]:
    problems = deployment_manifest_problems(payload)
    if problems:
        raise DeploymentManifestError(
            f"{source}: schema validation failed: " + "; ".join(problems)
        )
    return payload


def load_deployment_manifest(path: str | Path) -> dict[str, Any]:
    """Load + fully validate the deployment manifest (fail-closed)."""
    manifest_file = Path(path)
    try:
        payload = json.loads(manifest_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DeploymentManifestError(
            f"deployment manifest {manifest_file}: unreadable ({exc})"
        ) from exc
    return validate_deployment_manifest(
        payload, source=f"deployment manifest {manifest_file}"
    )


# --- neutral host state root (§5.2) -------------------------------------------------


def deploy_state_root(override: str | Path | None = None) -> Path:
    """The neutral, host-scoped deployed-state root (never inside any repo)."""
    if override is not None:
        return Path(override).expanduser()
    env = os.environ.get(DEPLOY_STATE_ROOT_ENV)
    if env:
        return Path(env).expanduser()
    return DEFAULT_DEPLOY_STATE_ROOT.expanduser()


def state_root_paths(state_root: Path) -> dict[str, Path]:
    return {
        "manifest": state_root / MACHINE_MANIFEST_FILENAME,
        "inventory": state_root / RUNTIME_INVENTORY_FILENAME,
        "expected_generation": state_root / EXPECTED_GENERATION_FILENAME,
        "receipts": state_root / RECEIPTS_DIRNAME,
    }


def ensure_state_root_layout(state_root: Path) -> dict[str, Path]:
    """Create the §5.2 layout (root + ``receipts/``); returns the path map."""
    paths = state_root_paths(state_root)
    paths["receipts"].mkdir(parents=True, exist_ok=True)
    return paths


def build_runtime_inventory(repo_paths: Mapping[str, str | Path]) -> dict[str, Any]:
    return {
        "schema_version": RUNTIME_INVENTORY_SCHEMA_VERSION,
        "kind": RUNTIME_INVENTORY_KIND,
        "generated_at": _utc_now_iso(),
        "host": socket.gethostname(),
        "repos": {
            name: {"path": str(path)} for name, path in sorted(repo_paths.items())
        },
    }


def runtime_inventory_problems(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return ["runtime inventory must be a JSON object"]
    problems: list[str] = []
    if payload.get("schema_version") != RUNTIME_INVENTORY_SCHEMA_VERSION:
        problems.append(
            f"schema_version must be {RUNTIME_INVENTORY_SCHEMA_VERSION}"
        )
    if payload.get("kind") != RUNTIME_INVENTORY_KIND:
        problems.append(f"kind must be {RUNTIME_INVENTORY_KIND!r}")
    repos = payload.get("repos")
    if not isinstance(repos, dict) or not repos:
        problems.append("repos must be a non-empty object of {name: {path}}")
        return problems
    for name in sorted(repos):
        entry = repos[name]
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            problems.append(f"repos[{name!r}] needs a string 'path'")
            continue
        if not Path(entry["path"]).is_absolute():
            problems.append(
                f"repos[{name!r}].path must be an absolute host path, got "
                f"{entry['path']!r}"
            )
    return problems


def load_runtime_inventory(path: str | Path) -> dict[str, Any]:
    inventory_file = Path(path)
    try:
        payload = json.loads(inventory_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DeploymentManifestError(
            f"runtime inventory {inventory_file}: unreadable ({exc})"
        ) from exc
    problems = runtime_inventory_problems(payload)
    if problems:
        raise DeploymentManifestError(
            f"runtime inventory {inventory_file}: schema validation failed: "
            + "; ".join(problems)
        )
    return payload


def verify_runtime_inventory(
    manifest: Mapping[str, Any],
    inventory: Mapping[str, Any],
    *,
    git_probe: GitProbe | None = None,
    require_clean: bool = False,
) -> dict[str, str]:
    """Verify EVERY manifest repo through the host inventory (§5.2 read rule).

    For each manifest repo the inventory must name a checkout whose HEAD
    equals the manifest commit. Any failure raises (fail-closed). Returns
    the resolved ``{repo: full_commit}`` map."""
    inventory_repos = inventory.get("repos") or {}
    problems: list[str] = []
    resolved: dict[str, str] = {}
    for name, entry in sorted((manifest.get("repos") or {}).items()):
        inv_entry = inventory_repos.get(name)
        if not isinstance(inv_entry, dict) or not inv_entry.get("path"):
            problems.append(f"{name}: missing from the runtime inventory")
            continue
        commit, problem = check_checkout_state(
            name,
            Path(inv_entry["path"]),
            str(entry["commit"]),
            git_probe=git_probe,
            require_clean=require_clean,
        )
        if problem:
            problems.append(problem)
        else:
            assert commit is not None
            resolved[name] = commit
    if problems:
        raise DeploymentManifestError(
            "runtime inventory verification failed: " + "; ".join(problems)
        )
    return resolved


# --- forward-only expected-generation record (§5.2) ---------------------------------


def read_expected_generation(state_root: Path) -> dict[str, Any] | None:
    """The durable epoch record, or ``None`` when it does not exist yet."""
    record_path = state_root / EXPECTED_GENERATION_FILENAME
    if not record_path.exists():
        return None
    try:
        payload = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DeploymentManifestError(
            f"expected-generation record {record_path}: unreadable ({exc})"
        ) from exc
    problems: list[str] = []
    if not isinstance(payload, dict):
        problems.append("must be a JSON object")
    else:
        if payload.get("kind") != EXPECTED_GENERATION_KIND:
            problems.append(f"kind must be {EXPECTED_GENERATION_KIND!r}")
        if not _is_int(payload.get("generation")) or payload.get("generation") < 1:
            problems.append("generation must be an integer >= 1")
        sha = payload.get("manifest_sha256")
        if not isinstance(sha, str) or not _SHA256_RE.match(sha):
            problems.append("manifest_sha256 must be a 64-hex sha256")
    if problems:
        raise DeploymentManifestError(
            f"expected-generation record {record_path}: malformed: "
            + "; ".join(problems)
        )
    return payload


def record_expected_generation(
    state_root: Path,
    *,
    generation: int,
    manifest_sha256: str,
) -> Path:
    """FORWARD-ONLY writer for the durable epoch record (§5.2).

    Written atomically (temp + ``os.replace``) immediately AFTER a
    successful manifest write; REFUSES any decrease, and refuses rewriting
    the SAME generation with different content (that would be a silent
    history rewrite). Re-recording the identical ``(generation, sha)`` pair
    is an idempotent no-op."""
    if not _is_int(generation) or generation < 1:
        raise DeploymentManifestError(
            f"expected-generation: generation must be an integer >= 1, got "
            f"{generation!r}"
        )
    if not isinstance(manifest_sha256, str) or not _SHA256_RE.match(manifest_sha256):
        raise DeploymentManifestError(
            "expected-generation: manifest_sha256 must be a 64-hex sha256, "
            f"got {manifest_sha256!r}"
        )
    existing = read_expected_generation(state_root)
    record_path = state_root / EXPECTED_GENERATION_FILENAME
    if existing is not None:
        prior_generation = existing["generation"]
        prior_sha = existing["manifest_sha256"]
        if generation < prior_generation:
            raise DeploymentManifestError(
                f"expected-generation is FORWARD-ONLY: refusing decrease "
                f"{prior_generation} -> {generation} (a lower generation is "
                "a stale/replayed state, never a legitimate write)"
            )
        if generation == prior_generation:
            if manifest_sha256 == prior_sha:
                return record_path  # idempotent re-record
            raise DeploymentManifestError(
                f"expected-generation: refusing to rewrite generation "
                f"{generation} with different manifest content "
                f"({prior_sha[:12]} -> {manifest_sha256[:12]}) — an epoch is "
                "never reused (reverts advance the generation, §5.1)"
            )
    payload = {
        "schema_version": EXPECTED_GENERATION_SCHEMA_VERSION,
        "kind": EXPECTED_GENERATION_KIND,
        "generation": generation,
        "manifest_sha256": manifest_sha256,
        "recorded_at": _utc_now_iso(),
    }
    write_json_canonical(record_path, payload)
    return record_path


def classify_generation(
    manifest_generation: int, expected_generation: int
) -> str:
    """§5.2 consumer rule: manifest generation vs the durable record.

    ``ok`` when equal; ``stale_or_replayed`` when the manifest is BEHIND the
    record (a restored old manifest+mirror pair — hashes match internally,
    the generation betrays the replay); ``torn_apply`` when AHEAD (crash
    between manifest write and record write). Consumers abort on both once
    armed; recovery is the explicit ``deploy-pin reconcile-generation``
    flow (Stage 3)."""
    if manifest_generation == expected_generation:
        return GENERATION_OK
    if manifest_generation < expected_generation:
        return GENERATION_STALE_OR_REPLAYED
    return GENERATION_TORN_APPLY


# --- §7.1 epoch transition predicates (pure helpers; consumed by later stages) ------


def steady_state_violations(
    *,
    local_generation: int,
    local_sha256: str,
    main_generation: int,
    main_sha256: str,
) -> list[str]:
    """STEADY-STATE predicate (§5.2/§7.1): machine == origin/main recorded
    manifest, same generation. Read paths alarm on violations; the
    emergency lane refuses on them (remote steady-state equality)."""
    violations: list[str] = []
    if main_generation != local_generation:
        violations.append(
            f"generation divergence: machine at {local_generation}, "
            f"origin/main recorded manifest at {main_generation}"
        )
    if main_sha256 != local_sha256:
        violations.append(
            f"manifest content divergence: machine {local_sha256[:12]} != "
            f"origin/main {main_sha256[:12]}"
        )
    return violations


def normal_apply_violations(
    *,
    local_generation: int,
    local_sha256: str,
    main_generation: int,
    main_supersedes_sha256: str | None,
) -> list[str]:
    """NORMAL (record-first) apply predicate (§7.1): a record-first apply
    legitimately sees origin/main exactly ONE generation ahead of the
    machine, superseding exactly the machine's content — predecessor
    exactness, not literal equality."""
    violations: list[str] = []
    if main_generation != local_generation + 1:
        if main_generation > local_generation + 1:
            violations.append(
                f"generation skip: origin/main at {main_generation}, machine "
                f"at {local_generation} — someone recorded past this machine; "
                "applies halt until reconciled"
            )
        else:
            violations.append(
                f"origin/main generation {main_generation} does not extend "
                f"machine generation {local_generation} (record-first apply "
                f"requires exactly {local_generation + 1})"
            )
    if main_supersedes_sha256 != local_sha256:
        violations.append(
            "predecessor mismatch: origin/main supersedes_sha256 "
            f"{str(main_supersedes_sha256)[:12]} != machine manifest sha256 "
            f"{local_sha256[:12]} — the machine is not the state the "
            "reviewer approved a transition FROM"
        )
    return violations


def emergency_apply_violations(
    *,
    local_generation: int,
    local_sha256: str,
    main_generation: int,
    main_sha256: str,
    candidate_generation: int,
    candidate_supersedes_sha256: str | None,
) -> list[str]:
    """EMERGENCY-lane predicate (§7.1): requires remote steady-state
    EQUALITY (origin/main ahead or hash-divergent ⇒ refuse — an emergency
    candidate may only extend the epoch both sides agree on, never fork
    it), plus a locally-built candidate extending the machine epoch by
    exactly one. Token/signature checks are the Stage-3 lane's job."""
    violations = [
        f"emergency lane refused (forked-epoch guard): {violation}"
        for violation in steady_state_violations(
            local_generation=local_generation,
            local_sha256=local_sha256,
            main_generation=main_generation,
            main_sha256=main_sha256,
        )
    ]
    if candidate_generation != local_generation + 1:
        violations.append(
            f"emergency candidate generation {candidate_generation} must be "
            f"exactly machine generation + 1 ({local_generation + 1})"
        )
    if candidate_supersedes_sha256 != local_sha256:
        violations.append(
            "emergency candidate supersedes_sha256 "
            f"{str(candidate_supersedes_sha256)[:12]} != machine manifest "
            f"sha256 {local_sha256[:12]}"
        )
    return violations
