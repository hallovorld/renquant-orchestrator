"""Modal cloud backend for the BacktestExecutor protocol.

Run guardrails (prerequisite for any run under
doc/design/2026-07-11-modal-bounded-run-experiment-plan.md):

1. ENFORCEABLE SPEND CAP — ``preflight`` REQUIRES an explicit
   ``approved_cost_cap_usd`` (no default). The effective gate is
   ``min(HARD_COST_SAFETY_GATE_USD, approved cap)`` — the tighter bound
   always governs, and a missing/unresolved cap fails closed instead of
   falling back to the fixed gate.
2. PRE-REGISTERED WORKLOAD IDENTITY — ``preflight`` REQUIRES an
   operator-approved :class:`WorkloadManifest` pinning the exact variant
   identifiers, per-variant config fingerprints, seed values, bundle /
   volume / data fingerprints, data interval, region, and image identity.
   ``execute_batch`` refuses to dispatch without a passing preflight's
   :class:`DispatchApproval` (threaded through explicitly — there is no
   honor-system flag) and re-verifies the actual requests against the
   manifest immediately before dispatch, failing on ANY mismatch.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import math
import os
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .executor import (
    BacktestRequest,
    BacktestResult,
    BatchSummary,
    DataManifest,
    PreflightReport,
)

log = logging.getLogger(__name__)

MODAL_CPU_RATE = 0.0000131  # $/physical-core-sec
MODAL_MEM_RATE = 0.00000222  # $/GiB-sec
WORKER_CORES = 4
WORKER_MEM_GIB = 16

# Hard, non-negotiable preflight spend gate. An operator-approved cap can
# only TIGHTEN this bound (effective gate = min(hard gate, approved cap));
# nothing can raise it.
HARD_COST_SAFETY_GATE_USD = 20.0

# Single source of truth for the worker image DEFINITION (build inputs).
# modal_app.py must bake exactly these inputs into _BASE_IMAGE —
# tests/test_cloud_modal.py asserts the decoration-time image was built
# from this spec, so the fingerprint recorded in a workload manifest cannot
# silently drift from what actually runs. (The resolved registry digest
# only exists after a build; each pod additionally reports MODAL_IMAGE_ID
# in its result for post-run reconciliation.)
IMAGE_SPEC: dict[str, Any] = {
    "base": "debian_slim",
    "python_version": "3.10",
    "pip_packages": [
        "pandas>=2.0",
        "numpy>=1.24",
        "scipy>=1.10",
        "scikit-learn>=1.2",
        "xgboost>=1.7",
        "pyarrow>=12.0",
        "joblib>=1.2",
        "pyyaml>=6.0",
        "cvxpy>=1.3",
        "pydantic>=2.0",
        "ngboost>=0.4",
        "lightgbm>=3.3",
    ],
    "run_commands": [
        "pip install torch --index-url https://download.pytorch.org/whl/cpu",
    ],
}


def image_spec_fingerprint() -> str:
    """Deterministic digest of the worker image definition (IMAGE_SPEC)."""
    canonical = json.dumps(IMAGE_SPEC, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()

# Conservative per-pod runtime estimate for the preflight cost gate, in
# seconds. The only real data point available is the pre-reconciliation
# smoke test's cached-run worker time (5558s / 93min) for ONE pod running
# ALL 3 seeds serially on the OLD architecture — see
# doc/progress/2026-07-08-modal-sweep-reconciled.md. Under the per-seed
# fan-out design each pod now runs exactly ONE seed, so the true per-pod
# time is very likely lower (perhaps close to 5558/3 if backtest compute
# dominates), but that has NOT been re-measured on the reconciled code, and
# fixed per-pod overhead (image pull, data load from the Volume) may not
# scale down linearly with fewer seeds. Using the full un-split figure is
# the conservative (non-optimistic) choice until a fresh bounded smoke test
# on THIS code produces a real per-seed-pod number to replace it.
DEFAULT_SECONDS_PER_POD_ESTIMATE = 5558.0


def _estimate_cost_usd(elapsed_seconds: float) -> float:
    return elapsed_seconds * (
        WORKER_CORES * MODAL_CPU_RATE + WORKER_MEM_GIB * MODAL_MEM_RATE
    )


class WorkloadManifestError(ValueError):
    """The pre-registered workload manifest is missing, malformed, or has
    unresolved required fields (unknown region, unresolved image/Volume
    identity, missing fingerprints/seeds/interval)."""


class WorkloadMismatchError(RuntimeError):
    """The actual workload deviates from the operator-approved manifest."""


class ModalExecutionDisabledError(RuntimeError):
    """Modal dispatch/sync is unconditionally disabled at the library layer.

    Codex round-3 review of orchestrator#463 (2026-07-11T04:45:20Z): the
    CLI's --execute block (run_sweep_modal.py) is UX, not a safety gate —
    any in-repo Python caller can construct a ModalExecutor directly and
    call execute_batch()/sync_data(), bypassing the CLI entirely. The
    standing operator rule (no Modal API/CLI calls at all until an
    independently verifiable, operator-signed authorization artifact and
    an enforced no-live/deploy assertion exist) must be enforced here, in
    the library both callers share, not only in one script's argument
    parsing. Neither control exists yet — see
    doc/design/2026-07-11-modal-bounded-run-experiment-plan.md's BLOCKING
    PREREQUISITE. This is deliberately NOT a self-issued authorization
    scheme; there is no bypass parameter."""


# Placeholder strings that must never pass for a REQUIRED recorded field —
# an unresolved value is an abort condition, not a post-hoc note.
_UNRESOLVED_VALUES = {"", "unknown", "none", "null", "tbd", "todo"}


def _require_resolved(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or value.strip().lower() in _UNRESOLVED_VALUES:
        raise WorkloadManifestError(
            f"workload manifest required field '{key}' is missing or "
            f"unresolved (got {value!r}) — every pre-registered field must "
            "be a concrete recorded value, not a placeholder"
        )
    return value.strip()


@dataclass(frozen=True)
class WorkloadVariant:
    """One pre-registered (variant, config fingerprint, seeds) identity."""

    name: str
    role: str
    config_sha256: str
    seeds: tuple[int, ...]


@dataclass(frozen=True)
class WorkloadManifest:
    """Operator-approved pre-registration of EXACTLY what a run may dispatch.

    ``sha256`` is the digest of the approved manifest file's raw bytes — it
    is echoed into the dispatch metadata and the run outputs so the run's
    evidence is verifiably tied to what the operator signed off on.
    """

    sha256: str
    region: str
    image_spec_sha256: str
    volume_name: str
    volume_commit_id: str
    data_manifest_sha256: str
    bundle_fingerprint: str
    artifact_manifest_sha256: str
    start: str
    end: str
    variants: tuple[WorkloadVariant, ...]

    def variant(self, name: str) -> WorkloadVariant | None:
        for v in self.variants:
            if v.name == name:
                return v
        return None

    @staticmethod
    def from_payload(payload: dict[str, Any], *, sha256: str) -> "WorkloadManifest":
        if not isinstance(payload, dict):
            raise WorkloadManifestError(
                f"workload manifest must be a JSON object, got {type(payload).__name__}"
            )
        interval = payload.get("data_interval")
        if not isinstance(interval, dict):
            raise WorkloadManifestError(
                "workload manifest required field 'data_interval' "
                "(object with 'start'/'end') is missing"
            )
        raw_variants = payload.get("variants")
        if not isinstance(raw_variants, list) or not raw_variants:
            raise WorkloadManifestError(
                "workload manifest must pre-register a non-empty 'variants' "
                "list (exact identifiers — a bare count is not a workload)"
            )
        variants: list[WorkloadVariant] = []
        seen: set[str] = set()
        for i, rv in enumerate(raw_variants):
            if not isinstance(rv, dict):
                raise WorkloadManifestError(f"variants[{i}] must be an object")
            name = _require_resolved(rv, "name")
            if name in seen:
                raise WorkloadManifestError(
                    f"variants[{i}]: duplicate variant name {name!r}"
                )
            seen.add(name)
            seeds_raw = rv.get("seeds")
            if (
                not isinstance(seeds_raw, list)
                or not seeds_raw
                or not all(isinstance(s, int) and not isinstance(s, bool) for s in seeds_raw)
            ):
                raise WorkloadManifestError(
                    f"variants[{i}] ({name}): 'seeds' must be a non-empty "
                    f"list of literal integers, got {seeds_raw!r}"
                )
            variants.append(
                WorkloadVariant(
                    name=name,
                    role=_require_resolved(rv, "role"),
                    config_sha256=_require_resolved(rv, "config_sha256"),
                    seeds=tuple(seeds_raw),
                )
            )
        return WorkloadManifest(
            sha256=sha256,
            region=_require_resolved(payload, "region"),
            image_spec_sha256=_require_resolved(payload, "image_spec_sha256"),
            volume_name=_require_resolved(payload, "volume_name"),
            volume_commit_id=_require_resolved(payload, "volume_commit_id"),
            data_manifest_sha256=_require_resolved(payload, "data_manifest_sha256"),
            bundle_fingerprint=_require_resolved(payload, "bundle_fingerprint"),
            artifact_manifest_sha256=_require_resolved(
                payload, "artifact_manifest_sha256"
            ),
            start=_require_resolved(interval, "start"),
            end=_require_resolved(interval, "end"),
            variants=tuple(variants),
        )

    @staticmethod
    def load(path: str | Path) -> "WorkloadManifest":
        raw = Path(path).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise WorkloadManifestError(
                f"workload manifest {path} is not valid JSON: {exc}"
            ) from exc
        return WorkloadManifest.from_payload(payload, sha256=digest)


def write_workload_manifest(
    path: str | Path,
    *,
    region: str,
    volume_name: str,
    volume_commit_id: str,
    data_manifest_sha256: str,
    bundle_fingerprint: str,
    artifact_manifest_sha256: str,
    start: str,
    end: str,
    variants: list[dict[str, Any]],
) -> WorkloadManifest:
    """Write a pre-registration manifest capturing the CURRENT plan.

    Validates the payload through the same loader the executor uses (so an
    unwritable/unresolved plan fails HERE, before it is ever put in front
    of the operator) and returns the parsed manifest, whose ``sha256`` is
    the digest of the exact bytes written.
    """
    payload = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "region": region,
        "image_spec_sha256": image_spec_fingerprint(),
        "volume_name": volume_name,
        "volume_commit_id": volume_commit_id,
        "data_manifest_sha256": data_manifest_sha256,
        "bundle_fingerprint": bundle_fingerprint,
        "artifact_manifest_sha256": artifact_manifest_sha256,
        "data_interval": {"start": start, "end": end},
        "variants": variants,
    }
    raw = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
    digest = hashlib.sha256(raw).hexdigest()
    manifest = WorkloadManifest.from_payload(payload, sha256=digest)
    Path(path).write_bytes(raw)
    return manifest


@dataclass(frozen=True)
class DispatchApproval:
    """Immutable evidence that preflight PASSED under an explicit
    operator-approved spend cap against a specific pre-registered workload.

    Issued only by :meth:`ModalExecutor.preflight` (and only when every
    check passes); :meth:`ModalExecutor.execute_batch` refuses to dispatch
    without one, and only honors approvals it issued itself (``nonce``)."""

    approved_cost_cap_usd: float
    effective_cost_gate_usd: float
    projected_cost_usd: float
    n_pods: int
    workload_manifest_sha256: str
    issued_at: str
    nonce: str


@dataclass
class ModalPreflightReport(PreflightReport):
    """PreflightReport plus the spend-cap/pre-registration evidence.

    ``approval`` is only present when the preflight PASSED; it is the
    dispatch token ``execute_batch`` requires."""

    approval: DispatchApproval | None = None
    workload_manifest: WorkloadManifest | None = None


class ModalExecutor:
    """Modal cloud backend — dispatches sweep variants to remote workers."""

    def __init__(
        self,
        bundle_dir: str,
        volume_name: str = "renquant-sweep-data",
        timeout: int = int(os.environ.get("MODAL_TIMEOUT", "86400")),
        retries: int = 1,
        region: str | None = None,
    ):
        self._bundle_dir = bundle_dir
        self._volume_name = volume_name
        self._timeout = timeout
        self._retries = retries
        self._region = region
        # Nonces of DispatchApprovals THIS instance issued — execute_batch
        # only honors these, so a report cannot be forged, reused from
        # another executor, or fabricated without running preflight.
        self._issued_dispatch_nonces: set[str] = set()

    def execute_batch(
        self,
        requests: list[BacktestRequest],
        *,
        on_result: Callable[[BacktestResult], None],
        on_error: Callable[[str, Exception], None],
        max_concurrent: int = 100,
        preflight: ModalPreflightReport | None = None,
    ) -> BatchSummary:
        import sys

        # Disabled at the library layer (Codex round-3, #463) — refuse
        # before ANY other guardrail logic, let alone Modal-facing work.
        # A passing `preflight` report does not bypass this: self-issued
        # authorization is exactly what round-3 rejected. A helper method
        # call (not a bare `raise` here) so re-enabling this in a future
        # PR is a one-line change and this method's body isn't read as
        # statically unreachable in the meantime.
        self._require_modal_execution_enabled()

        # Guardrails FIRST — refuse before any Modal-facing work happens.
        approval, manifest = self._require_dispatch_approval(preflight)
        self._verify_workload_matches_manifest(requests, manifest)

        module_name = "renquant_orchestrator.cloud.modal_app"
        if module_name in sys.modules:
            existing = sys.modules[module_name]
            if (
                existing.WORKER_TIMEOUT_SECONDS != self._timeout
                or existing.WORKER_RETRIES != self._retries
                or getattr(existing, "WORKER_REGION", None) != (self._region or None)
            ):
                raise RuntimeError(
                    "modal_app was already imported with timeout="
                    f"{existing.WORKER_TIMEOUT_SECONDS}, retries={existing.WORKER_RETRIES}, "
                    f"region={getattr(existing, 'WORKER_REGION', None)} "
                    f"(baked into the @app.function decorator at import time); this "
                    f"ModalExecutor requested timeout={self._timeout}, retries={self._retries}, "
                    f"region={self._region}, "
                    "which cannot be honored without a fresh process. Modal's "
                    "@app.function timeout/retries are decorator-time-only, so a "
                    "second import in the same process would silently reuse the "
                    "first import's baked-in values. Run each distinct "
                    "timeout/retries/region combination in its own process."
                )
        else:
            os.environ["RENQUANT_MODAL_TIMEOUT_SECONDS"] = str(self._timeout)
            os.environ["RENQUANT_MODAL_RETRIES"] = str(self._retries)
            if self._region:
                os.environ["RENQUANT_MODAL_REGION"] = self._region
            else:
                os.environ.pop("RENQUANT_MODAL_REGION", None)

        from .modal_app import app, run_variant_remote

        t0 = time.monotonic()
        summary = BatchSummary()

        # Echoed into every pod's request JSON so the run's own dispatch
        # records (Modal input logs) carry the approved cap + manifest sha.
        dispatch_metadata = {
            "workload_manifest_sha256": approval.workload_manifest_sha256,
            "approved_cost_cap_usd": approval.approved_cost_cap_usd,
            "effective_cost_gate_usd": approval.effective_cost_gate_usd,
            "region": manifest.region,
            "preflight_nonce": approval.nonce,
        }

        # Fan out: one Modal task per (variant, seed) for max parallelism.
        per_seed_requests = []
        for r in requests:
            for seed in r.seeds:
                d = _request_to_dict(r)
                d["seeds"] = [seed]
                d["dispatch_metadata"] = dispatch_metadata
                per_seed_requests.append(json.dumps(d))

        log.info("Starting Modal app (first run builds image ~3-5min, cached after)...")
        with app.run():
            n_tasks = len(per_seed_requests)
            n_variants = len(requests)
            log.info(
                "Dispatching %d tasks (%d variants × %d seeds)...",
                n_tasks, n_variants,
                n_tasks // n_variants if n_variants else 0,
            )

            variant_seeds: dict[str, list[dict]] = {}
            variant_meta: dict[str, dict] = {}

            n_received = 0
            for result_json in run_variant_remote.map(
                per_seed_requests,
                kwargs={},
                order_outputs=False,
                return_exceptions=True,
            ):
                n_received += 1
                if isinstance(result_json, Exception):
                    log.error(
                        "Pod %d/%d raised: %s", n_received, n_tasks, result_json
                    )
                    on_error("unknown", result_json)
                    summary.n_failed += 1
                    continue
                log.info("Pod %d/%d returned", n_received, n_tasks)
                try:
                    result_dict = json.loads(result_json)
                    vname = result_dict["variant_name"]

                    variant_seeds.setdefault(vname, []).extend(
                        result_dict.get("per_seed", [])
                    )
                    if vname not in variant_meta:
                        # Each (variant, seed) pod bills its own compute-seconds;
                        # seed the variant-level total from this pod's elapsed
                        # time rather than treating a single pod as the whole
                        # variant's cost.
                        prev = dict(result_dict)
                        prev["total_worker_seconds"] = result_dict.get(
                            "elapsed_seconds", 0.0
                        )
                        variant_meta[vname] = prev
                    else:
                        prev = variant_meta[vname]
                        # Cost is billed per pod-second across ALL dispatched
                        # pods for this variant (3 seeds = 3 separate pods
                        # under the per-seed fan-out design), so the variant's
                        # total compute-seconds is a SUM across pods, not the
                        # max of any single pod's wall-clock time. Using max()
                        # here would systematically undercount real spend by
                        # roughly (seeds_per_variant)x.
                        prev["total_worker_seconds"] = prev.get(
                            "total_worker_seconds", 0.0
                        ) + result_dict.get("elapsed_seconds", 0.0)
                        # peak_memory_mb IS legitimately a max: pods run on
                        # independent machines, so memory doesn't add across
                        # them — the worst single pod's footprint is what
                        # matters for right-sizing the resource envelope.
                        prev["peak_memory_mb"] = max(
                            prev.get("peak_memory_mb", 0),
                            result_dict.get("peak_memory_mb", 0),
                        )
                        for k in ("equity_curves", "trade_logs"):
                            if result_dict.get(k):
                                prev.setdefault(k, {}).update(result_dict[k])

                except Exception as exc:
                    vname = "unknown"
                    try:
                        vname = json.loads(result_json).get("variant_name", "unknown")
                    except Exception:
                        pass
                    on_error(vname, exc)
                    summary.n_failed += 1

            for vname, meta in variant_meta.items():
                try:
                    per_seed = variant_seeds.get(vname, [])
                    all_seeds = [s["seed"] for s in per_seed]

                    equity_curves = None
                    if meta.get("equity_curves"):
                        equity_curves = {
                            int(k): base64.b64decode(v)
                            for k, v in meta["equity_curves"].items()
                        }

                    trade_logs = None
                    if meta.get("trade_logs"):
                        trade_logs = {
                            int(k): base64.b64decode(v)
                            for k, v in meta["trade_logs"].items()
                        }

                    result = BacktestResult(
                        variant_name=vname,
                        role=meta.get("role", "candidate"),
                        config_fingerprint=meta.get("config_fingerprint", ""),
                        # worker_id/started_at/finished_at/result_checksum below
                        # are stamped from whichever pod's response happened to
                        # be aggregated first for this variant — they are NOT
                        # necessarily representative of every pod that ran a
                        # seed for this variant. Each per_seed[i] entry carries
                        # its own authoritative worker_id/started_at/
                        # finished_at/elapsed_seconds/peak_memory_mb — use those
                        # for genuine per-pod provenance.
                        worker_id=meta.get("worker_id", "modal"),
                        volume_commit_id=meta.get("volume_commit_id"),
                        code_image_id=meta.get("code_image_id"),
                        started_at=meta.get("started_at", ""),
                        finished_at=meta.get("finished_at", ""),
                        # elapsed_seconds at the variant level is the SUM of
                        # every dispatched pod's elapsed time for this variant
                        # (total billed compute-seconds), not any single pod's
                        # wall-clock duration — see the aggregation loop above.
                        elapsed_seconds=meta.get("total_worker_seconds", 0.0),
                        peak_memory_mb=meta.get("peak_memory_mb", 0.0),
                        seeds=all_seeds,
                        per_seed=per_seed,
                        equity_curves=equity_curves,
                        trade_logs=trade_logs,
                        result_checksum=meta.get("result_checksum", ""),
                        # Stamp the approved pre-registration identity into
                        # the run outputs (persisted result evidence).
                        workload_manifest_sha256=approval.workload_manifest_sha256,
                    )
                    on_result(result)
                    summary.n_completed += 1
                    summary.cost_usd += _estimate_cost_usd(result.elapsed_seconds)
                except Exception as exc:
                    on_error(vname, exc)
                    summary.n_failed += 1

        summary.total_seconds = time.monotonic() - t0
        return summary

    def preflight(
        self,
        data_manifest: DataManifest,
        *,
        n_variants: int,
        n_seeds_per_variant: int,
        approved_cost_cap_usd: float,
        workload_manifest: WorkloadManifest,
        seconds_per_pod: float = DEFAULT_SECONDS_PER_POD_ESTIMATE,
    ) -> ModalPreflightReport:
        """Deterministic pre-dispatch gate.

        ``approved_cost_cap_usd`` is REQUIRED with no default by design:
        every caller must pass the explicit operator-approved spend cap.
        The effective gate is ``min(HARD_COST_SAFETY_GATE_USD, cap)`` —
        the tighter bound always governs; a missing/invalid cap raises
        (fails closed) rather than falling back to the fixed gate.

        ``workload_manifest`` is the operator-approved pre-registration of
        the exact workload; preflight cross-checks it against the executor
        configuration and the synced data, and — only if EVERY check
        passes — issues the :class:`DispatchApproval` that
        :meth:`execute_batch` requires.
        """
        if isinstance(approved_cost_cap_usd, bool) or not isinstance(
            approved_cost_cap_usd, (int, float)
        ):
            raise TypeError(
                "approved_cost_cap_usd must be an explicit USD number "
                f"(got {approved_cost_cap_usd!r}) — there is no default and "
                "no fallback to the fixed safety gate"
            )
        cap = float(approved_cost_cap_usd)
        if not math.isfinite(cap) or cap <= 0:
            raise ValueError(
                f"approved_cost_cap_usd must be a positive finite USD amount, "
                f"got {approved_cost_cap_usd!r} — an unresolved cap fails "
                "closed; it does not fall back to the fixed "
                f"${HARD_COST_SAFETY_GATE_USD:.0f} gate"
            )
        if not isinstance(workload_manifest, WorkloadManifest):
            raise TypeError(
                "workload_manifest must be a WorkloadManifest — load the "
                "operator-approved JSON via WorkloadManifest.load(path)"
            )

        checks: dict[str, bool] = {}
        details: dict[str, str] = {}

        checks["volume_has_data"] = bool(data_manifest.files)
        if not checks["volume_has_data"]:
            details["volume_has_data"] = "No files in data manifest"

        checks["bundle_exists"] = Path(self._bundle_dir).is_dir()
        if not checks["bundle_exists"]:
            details["bundle_exists"] = f"Bundle dir not found: {self._bundle_dir}"

        try:
            import modal
            checks["modal_sdk"] = True
        except ImportError:
            checks["modal_sdk"] = False
            details["modal_sdk"] = "modal package not installed"

        # ── Pre-registration identity checks (WorkloadManifest) ──
        plan_mismatches: list[str] = []
        if len(workload_manifest.variants) != n_variants:
            plan_mismatches.append(
                f"manifest pre-registers {len(workload_manifest.variants)} "
                f"variants but the plan dispatches {n_variants}"
            )
        for v in workload_manifest.variants:
            if len(v.seeds) != n_seeds_per_variant:
                plan_mismatches.append(
                    f"variant {v.name}: {len(v.seeds)} pre-registered seeds "
                    f"vs planned {n_seeds_per_variant} per variant"
                )
        checks["manifest_matches_plan"] = not plan_mismatches
        if plan_mismatches:
            details["manifest_matches_plan"] = "; ".join(plan_mismatches)

        checks["volume_name_matches_manifest"] = (
            self._volume_name == workload_manifest.volume_name
        )
        if not checks["volume_name_matches_manifest"]:
            details["volume_name_matches_manifest"] = (
                f"executor volume {self._volume_name!r} != pre-registered "
                f"{workload_manifest.volume_name!r}"
            )

        checks["volume_commit_matches_manifest"] = (
            data_manifest.commit_id == workload_manifest.volume_commit_id
        )
        if not checks["volume_commit_matches_manifest"]:
            details["volume_commit_matches_manifest"] = (
                f"synced volume commit {data_manifest.commit_id!r} != "
                f"pre-registered {workload_manifest.volume_commit_id!r} — "
                "the data changed since the operator approved this workload"
            )

        data_sha = hashlib.sha256(
            json.dumps(data_manifest.files, sort_keys=True).encode()
        ).hexdigest()
        checks["data_manifest_matches_manifest"] = (
            data_sha == workload_manifest.data_manifest_sha256
        )
        if not checks["data_manifest_matches_manifest"]:
            details["data_manifest_matches_manifest"] = (
                f"data manifest sha {data_sha[:12]} != pre-registered "
                f"{workload_manifest.data_manifest_sha256[:12]}"
            )

        checks["image_spec_matches_manifest"] = (
            image_spec_fingerprint() == workload_manifest.image_spec_sha256
        )
        if not checks["image_spec_matches_manifest"]:
            details["image_spec_matches_manifest"] = (
                f"current image spec {image_spec_fingerprint()[:12]} != "
                f"pre-registered {workload_manifest.image_spec_sha256[:12]} — "
                "the worker image definition changed since approval"
            )

        checks["region_pinned"] = (
            bool(self._region) and self._region == workload_manifest.region
        )
        if not checks["region_pinned"]:
            details["region_pinned"] = (
                f"executor region {self._region!r} != pre-registered "
                f"{workload_manifest.region!r} — construct "
                "ModalExecutor(region=<approved region>); an unknown region "
                "is an abort, not a post-hoc note"
            )

        current_bundle_fp = self._current_bundle_fingerprint()
        checks["bundle_fingerprint_matches_manifest"] = (
            current_bundle_fp == workload_manifest.bundle_fingerprint
        )
        if not checks["bundle_fingerprint_matches_manifest"]:
            details["bundle_fingerprint_matches_manifest"] = (
                f"current bundle fingerprint {current_bundle_fp!r} != "
                f"pre-registered {workload_manifest.bundle_fingerprint!r}"
            )

        # ── Spend gate: min(hard safety gate, operator-approved cap) ──
        # Under the per-seed fan-out design, one pod is dispatched per
        # (variant, seed) pair — the cost projection must scale with the
        # ACTUAL pod count, not a stale one-pod-per-variant assumption.
        n_pods = n_variants * n_seeds_per_variant
        projected = _estimate_cost_usd(seconds_per_pod) * n_pods
        effective_gate = min(HARD_COST_SAFETY_GATE_USD, cap)
        checks["cost_within_effective_gate"] = projected < effective_gate
        # Recorded on pass AND fail — the cap is part of the run's evidence.
        details["cost_within_effective_gate"] = (
            f"projected ${projected:.2f} ({n_pods} pods = "
            f"{n_variants} variants × {n_seeds_per_variant} seeds, "
            f"{seconds_per_pod:.0f}s/pod estimate) vs effective gate "
            f"${effective_gate:.2f} = min(hard safety "
            f"${HARD_COST_SAFETY_GATE_USD:.2f}, approved cap ${cap:.2f})"
        )

        passed = all(checks.values())
        approval: DispatchApproval | None = None
        if passed:
            nonce = secrets.token_hex(16)
            self._issued_dispatch_nonces.add(nonce)
            approval = DispatchApproval(
                approved_cost_cap_usd=cap,
                effective_cost_gate_usd=effective_gate,
                projected_cost_usd=projected,
                n_pods=n_pods,
                workload_manifest_sha256=workload_manifest.sha256,
                issued_at=datetime.now(timezone.utc).isoformat(),
                nonce=nonce,
            )

        return ModalPreflightReport(
            passed=passed,
            checks=checks,
            details=details,
            approval=approval,
            workload_manifest=workload_manifest,
        )

    def _current_bundle_fingerprint(self) -> str | None:
        """Fingerprint of the bundle this executor would actually dispatch
        (recomputed from bundle_manifest.json; None if unresolvable)."""
        from .bundle import compute_bundle_fingerprint

        manifest_path = Path(self._bundle_dir) / "bundle_manifest.json"
        if not manifest_path.is_file():
            return None
        try:
            return compute_bundle_fingerprint(json.loads(manifest_path.read_text()))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return None

    def _require_modal_execution_enabled(self) -> None:
        """Unconditionally disabled (Codex round-3, #463, 2026-07-11T04:45:20Z):
        the CLI's --execute block is UX, not a safety gate — any in-repo
        Python caller can construct a ModalExecutor directly and reach
        execute_batch()/sync_data(), bypassing run_sweep_modal.py entirely.
        This is the ONE place both methods share, so it is the actual
        enforcement point. There is no parameter, flag, or self-issued
        report that bypasses this — re-enabling requires editing this
        method itself, in a dedicated PR, once an independently verifiable
        operator-signed authorization artifact and an enforced no-live/
        deploy assertion exist (doc/design/2026-07-11-modal-bounded-run-
        experiment-plan.md's BLOCKING PREREQUISITE)."""
        raise ModalExecutionDisabledError(
            "Modal execution (dispatch or data sync) is disabled: no "
            "independently verifiable, operator-signed authorization "
            "artifact and no enforced no-live/deploy assertion exist yet. "
            "See doc/design/2026-07-11-modal-bounded-run-experiment-plan.md."
        )

    def _require_dispatch_approval(
        self, preflight: ModalPreflightReport | None
    ) -> tuple[DispatchApproval, WorkloadManifest]:
        if preflight is None:
            raise RuntimeError(
                "Modal dispatch refused: no preflight report supplied. Run "
                "ModalExecutor.preflight(..., approved_cost_cap_usd=<operator-"
                "approved USD cap>, workload_manifest=<approved manifest>) and "
                "pass its report via execute_batch(..., preflight=report). "
                "There is no cap-less dispatch path."
            )
        approval = getattr(preflight, "approval", None)
        manifest = getattr(preflight, "workload_manifest", None)
        if not getattr(preflight, "passed", False) or approval is None or manifest is None:
            raise RuntimeError(
                "Modal dispatch refused: the supplied preflight report did not "
                "PASS with an approved cost cap and pre-registered workload — "
                "fix the failing checks and re-run preflight; a failed report "
                "is not a dispatch token."
            )
        if approval.nonce not in self._issued_dispatch_nonces:
            raise RuntimeError(
                "Modal dispatch refused: the preflight report was not issued "
                "by this ModalExecutor instance — re-run preflight on the "
                "executor that will dispatch."
            )
        if approval.workload_manifest_sha256 != manifest.sha256:
            raise RuntimeError(
                "Modal dispatch refused: preflight approval references a "
                "different workload manifest than the one attached to the "
                "report."
            )
        return approval, manifest

    def _verify_workload_matches_manifest(
        self, requests: list[BacktestRequest], manifest: WorkloadManifest
    ) -> None:
        """Fail-closed identity check of the ACTUAL workload against the
        operator-approved manifest, immediately before dispatch.

        A batch may be a SUBSET of the manifest (resume re-dispatches only
        incomplete variants; the incumbent runs in its own first batch),
        but every dispatched request must match its pre-registration
        exactly — any unregistered variant, changed seed set, changed
        config fingerprint, drifted bundle, or off-interval request aborts
        the whole batch before anything reaches Modal."""
        mismatches: list[str] = []

        current_bundle_fp = self._current_bundle_fingerprint()
        if current_bundle_fp != manifest.bundle_fingerprint:
            mismatches.append(
                f"bundle fingerprint {current_bundle_fp!r} != pre-registered "
                f"{manifest.bundle_fingerprint!r}"
            )

        seen: set[str] = set()
        for req in requests:
            registered = manifest.variant(req.variant_name)
            if registered is None:
                mismatches.append(
                    f"variant {req.variant_name!r} is not pre-registered in "
                    "the workload manifest"
                )
                continue
            if req.variant_name in seen:
                mismatches.append(
                    f"variant {req.variant_name!r} appears more than once in "
                    "this batch"
                )
            seen.add(req.variant_name)
            if req.role != registered.role:
                mismatches.append(
                    f"variant {req.variant_name}: role {req.role!r} != "
                    f"pre-registered {registered.role!r}"
                )
            config_sha = hashlib.sha256(req.config_json.encode()).hexdigest()
            if config_sha != registered.config_sha256:
                mismatches.append(
                    f"variant {req.variant_name}: config fingerprint "
                    f"{config_sha[:12]} != pre-registered "
                    f"{registered.config_sha256[:12]}"
                )
            if tuple(sorted(req.seeds)) != tuple(sorted(registered.seeds)):
                mismatches.append(
                    f"variant {req.variant_name}: seeds {sorted(req.seeds)} "
                    f"!= pre-registered {sorted(registered.seeds)}"
                )
            if (req.start, req.end) != (manifest.start, manifest.end):
                mismatches.append(
                    f"variant {req.variant_name}: data interval "
                    f"({req.start}, {req.end}) != pre-registered "
                    f"({manifest.start}, {manifest.end})"
                )
            if req.volume_commit_id != manifest.volume_commit_id:
                mismatches.append(
                    f"variant {req.variant_name}: volume commit "
                    f"{req.volume_commit_id!r} != pre-registered "
                    f"{manifest.volume_commit_id!r}"
                )

        if mismatches:
            raise WorkloadMismatchError(
                "Modal dispatch refused — actual workload deviates from the "
                f"operator-approved manifest (sha {manifest.sha256[:12]}):\n  - "
                + "\n  - ".join(mismatches)
            )

    def sync_data(self, local_paths: dict[str, str]) -> DataManifest:
        # Disabled at the library layer (Codex round-3, #463) — see
        # _require_modal_execution_enabled's docstring. Callers that only
        # need a DataManifest for local validation (preflight, workload
        # capture) should use renquant_orchestrator.cloud.sync_data
        # .local_data_manifest() directly instead — it makes no Modal
        # calls and is not affected by this block.
        self._require_modal_execution_enabled()

        from .sync_data import sync_to_modal_volume

        path_map = {k: Path(v) for k, v in local_paths.items()}
        return sync_to_modal_volume(path_map, volume_name=self._volume_name)


def _request_to_dict(req: BacktestRequest) -> dict[str, Any]:
    return {
        "variant_name": req.variant_name,
        "role": req.role,
        "config_json": req.config_json,
        "volume_commit_id": req.volume_commit_id,
        "seeds": req.seeds,
        "start": req.start,
        "end": req.end,
        "initial_cash": req.initial_cash,
        "incumbent_turnover": req.incumbent_turnover,
    }


