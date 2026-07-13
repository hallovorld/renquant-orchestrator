"""Stage-0 crypto readiness workflow using renquant-common Task/Job/Pipeline.

**Paper/shadow readiness work only.** This workflow is structurally unable
to authorize live trading entries -- it verifies Alpaca crypto prerequisites
empirically on the PAPER account and persists the results as a scoped
``crypto_stage0_readiness`` record for audit.

The workflow delegates all broker-facing step checks to
``renquant_execution.crypto_stage0_checks.run_full_battery`` (the ONLY
sanctioned entry point for transactional probe orders -- see
``scripts/crypto_stage0_battery.py``'s module docstring for why). This
module owns only: run identity (``run_id``), the Task/Job/Pipeline
orchestration structure, stage trace, and the ``crypto_stage0_readiness``
persistence record.

Design reference: doc/design/2026-07-10-crypto-trading-rfc.md section 6 Stage 0.
Architecture: doc/progress/2026-07-12-crypto-stage0-battery.md.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from renquant_common import Job, Pipeline, Task

try:
    from renquant_execution.alpaca_broker import AlpacaBroker
    from renquant_execution.crypto_stage0_checks import (
        BatteryReport,
        StepResult,
        StepStatus,
        run_full_battery,
    )

    _HAS_CHECKS = True
except ImportError:
    _HAS_CHECKS = False

    from dataclasses import dataclass as _dataclass
    from dataclasses import field as _field
    from typing import Any as _Any

    @_dataclass
    class StepResult:  # type: ignore[no-redef]
        name: str
        status: str
        detail: str = ""
        data: dict[str, _Any] = _field(default_factory=dict)
        required: bool = True

    @_dataclass
    class BatteryReport:  # type: ignore[no-redef]
        timestamp: str = ""
        account_id: str = ""
        environment: str = ""
        dry_run: bool = False
        steps: list[StepResult] = _field(default_factory=list)

        @property
        def all_passed(self) -> bool:
            return all(
                getattr(s.status, "value", s.status) == "PASS"
                for s in self.steps
                if s.required
            )

    AlpacaBroker = None  # type: ignore[assignment,misc]
    StepStatus = None  # type: ignore[assignment,misc]
    run_full_battery = None  # type: ignore[assignment]


log = logging.getLogger("crypto_stage0_workflow")


# ── Context ─────────────────────────────────────────────────────────────────


@dataclass
class CryptoStage0Context:
    """Mutable context for one Stage-0 battery run.

    Follows the same context-object pattern as ``DailyRunContext`` in
    ``daily.py`` -- a single mutable object threaded through the
    Task/Job/Pipeline chain, accumulating results at each stage.

    ``run_id`` is an opaque, caller-meaningful string identifier (same
    convention as ``DailyRunContext.run_id`` in ``daily.py`` -- only
    non-empty is enforced, not a specific format), letting a caller
    propagate its own run id (e.g. to correlate with a daily run) instead
    of always minting a fresh one via :func:`new_run_id`.
    """

    run_id: str
    output_dir: Path
    paper: bool = True
    dry_run: bool = True

    # Populated by tasks during the pipeline run.
    report: BatteryReport | None = field(default=None, repr=False)
    readiness_record: dict[str, Any] = field(default_factory=dict)
    stage_trace: list[dict[str, Any]] = field(default_factory=list)
    # Authoritative pass/fail signal for this workflow run. Do NOT rely on
    # the raw Pipeline.run(ctx).ok. renquant_common.pipeline.Pipeline.run()
    # returns ok=True whenever the pipeline completes without an uncaught
    # exception -- it reflects "didn't crash", not "the battery passed" or
    # even "entries are safe". workflow_ok is populated once the run
    # completes (including safety short-circuits) and is the only field
    # callers should check for the business outcome.
    workflow_ok: bool | None = field(default=None)


def new_run_id() -> str:
    """Generate a new RFC-4122 UUID run identifier.

    This is the default when no ``run_id`` is supplied; callers may pass any
    non-empty opaque string instead (see ``CryptoStage0Context.run_id``).
    """
    return str(uuid.uuid4())


# ── Tasks ────────────────────────────────────────────────────────────────────


class ValidateStage0InputsTask(Task):
    """Validate inputs before any broker interaction.

    Checks: run_id is present, paper flag is set (live is never permitted),
    execution dependency is available. A non-paper invocation is blocked
    here before any broker object is even created.

    A validation failure populates ``ctx.report`` with the FAIL reason but
    does NOT short-circuit the Job (returns ``True``, not ``False``): the
    readiness record must still be persisted for every attempted run,
    including ones blocked before a broker was ever touched, so there is
    always an audit trail explaining why. ``RunBatteryTask`` checks for a
    pre-populated ``ctx.report`` and skips broker interaction accordingly.
    """

    def run(self, ctx: CryptoStage0Context) -> bool | None:
        if not ctx.run_id:
            raise ValueError("run_id is required")

        if not ctx.paper:
            ctx.report = BatteryReport(
                timestamp="",
                account_id="",
                environment="LIVE-BLOCKED",
                dry_run=ctx.dry_run,
                steps=[
                    StepResult(
                        name="safety",
                        status="FAIL",
                        detail="Battery requires paper=True",
                    )
                ],
            )
            ctx.stage_trace.append({
                "stage": "validate_stage0_inputs",
                "ok": False,
                "reason": "live mode blocked",
            })
            return True

        if not _HAS_CHECKS:
            ctx.report = BatteryReport(
                timestamp="",
                account_id="",
                environment="paper",
                dry_run=ctx.dry_run,
                steps=[
                    StepResult(
                        name="dependency",
                        status="FAIL",
                        detail="renquant_execution.crypto_stage0_checks not installed",
                    )
                ],
            )
            ctx.stage_trace.append({
                "stage": "validate_stage0_inputs",
                "ok": False,
                "reason": "execution dependency missing",
            })
            return True

        ctx.output_dir.mkdir(parents=True, exist_ok=True)
        ctx.stage_trace.append({"stage": "validate_stage0_inputs", "ok": True})
        return True


class RunBatteryTask(Task):
    """Construct a paper broker and delegate to execution's run_full_battery.

    All broker-adapter logic, safety gates, and step aggregation live in
    ``renquant_execution.crypto_stage0_checks.run_full_battery`` -- this
    task only handles orchestrator-side concerns: creating + connecting the
    broker, invoking the battery, and recording the result.

    If ``ctx.report`` is already populated, ``ValidateStage0InputsTask``
    blocked the run before reaching here -- skip broker interaction
    entirely. Otherwise the broker connection and battery invocation are
    wrapped so that (a) ``broker.disconnect()`` always runs, mirroring
    ``daily.ExecuteOrderIntentsTask``'s connect/try/finally pattern, and
    (b) a setup or runtime exception becomes a persisted ERROR report
    instead of an unhandled crash with no audit trail.
    """

    def run(self, ctx: CryptoStage0Context) -> bool | None:
        if ctx.report is not None:
            return True

        started = time.monotonic()
        broker = AlpacaBroker(paper=True)
        try:
            broker.connect()
            ctx.report = run_full_battery(broker, dry_run=ctx.dry_run)
        except Exception as exc:  # noqa: BLE001 -- convert to an audited ERROR report
            elapsed = time.monotonic() - started
            ctx.report = BatteryReport(
                timestamp=datetime.now(timezone.utc).isoformat(),
                account_id="",
                environment="paper",
                dry_run=ctx.dry_run,
                steps=[
                    StepResult(
                        name="run_battery",
                        status="ERROR",
                        detail=f"{type(exc).__name__}: {exc}",
                    )
                ],
            )
            ctx.stage_trace.append({
                "stage": "run_battery",
                "ok": False,
                "elapsed_sec": elapsed,
                "verdict": "ERROR",
                "error": f"{type(exc).__name__}: {exc}",
            })
            return True
        finally:
            broker.disconnect()

        elapsed = time.monotonic() - started
        ctx.stage_trace.append({
            "stage": "run_battery",
            "ok": ctx.report.all_passed,
            "elapsed_sec": elapsed,
            "n_steps": len(ctx.report.steps),
            "verdict": "PASS" if ctx.report.all_passed else "FAIL",
        })
        return True


class PersistStage0ReadinessTask(Task):
    """Persist the ``crypto_stage0_readiness`` record.

    Writes a scoped readiness artifact that daily/session bundles can
    compose without parsing ad-hoc script output. The record includes:
    run identity, battery verdict, report content hash, stage trace, and
    orchestrator provenance.

    This is a scoped readiness record, NOT a full daily run bundle --
    the battery is not a daily training-to-trading run and lacks the
    context fields (strategy_manifest, artifact_manifest, decision_trace,
    etc.) that ``PersistDailyRunBundleTask`` requires.

    Runs (and persists a record) for every attempted run, including one
    that ``ValidateStage0InputsTask`` blocked before touching a broker --
    ``ctx.report`` is already populated with the block reason in that case.
    Also sets ``ctx.workflow_ok``, the authoritative pass/fail signal for
    this run (do not use the raw ``Pipeline.run(ctx).ok``; see
    ``CryptoStage0Context.workflow_ok`` for why).
    """

    def run(self, ctx: CryptoStage0Context) -> bool | None:
        if ctx.report is None:
            raise ValueError("report is required before persistence")

        ctx.workflow_ok = bool(ctx.report.all_passed)

        report_dict = _report_to_jsonable(ctx.report)
        canonical_json = json.dumps(report_dict, indent=2, sort_keys=True, default=str)
        report_sha256 = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

        readiness = {
            "record_type": "crypto_stage0_readiness",
            "schema_version": 1,
            "run_id": ctx.run_id,
            "run_type": "crypto_stage0_battery",
            "paper": ctx.paper,
            "dry_run": ctx.dry_run,
            "orchestrator_commit": _orchestrator_commit(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "verdict": "PASS" if ctx.workflow_ok else "FAIL",
            "report_sha256": report_sha256,
            "report": report_dict,
            "stage_trace": list(ctx.stage_trace),
        }

        # Persist to output_dir.
        out_path = ctx.output_dir / "crypto_stage0_readiness.json"
        _write_json_atomic(out_path, readiness)

        ctx.readiness_record = readiness
        ctx.stage_trace.append({
            "stage": "persist_stage0_readiness",
            "ok": True,
            "output_path": str(out_path),
        })
        return True


# ── Job / Pipeline ───────────────────────────────────────────────────────────


class CryptoStage0Job(Job):
    """Sequential chain: validate -> run battery -> persist readiness."""

    @property
    def tasks(self) -> list[Task]:
        return [
            ValidateStage0InputsTask(),
            RunBatteryTask(),
            PersistStage0ReadinessTask(),
        ]


class CryptoStage0Pipeline(Pipeline):
    """Stage-0 crypto readiness battery workflow."""

    def __init__(self) -> None:
        super().__init__(
            [CryptoStage0Job()],
            name="crypto-stage0-readiness",
        )


# ── Public entry point ───────────────────────────────────────────────────────


def run_stage0_workflow(
    *,
    paper: bool,
    dry_run: bool,
    output_dir: Path,
    run_id: str | None = None,
) -> CryptoStage0Context:
    """Run the Stage-0 battery as a first-class Pipeline workflow.

    Returns the populated context with report, readiness record, and
    stage trace. The CLI is a thin wrapper around this function.
    """
    if run_id is None:
        run_id = new_run_id()

    ctx = CryptoStage0Context(
        run_id=run_id,
        output_dir=output_dir,
        paper=paper,
        dry_run=dry_run,
    )

    pipeline = CryptoStage0Pipeline()
    pipeline.run(ctx)

    return ctx


# ── Helpers (shared with CLI) ────────────────────────────────────────────────


def _step_to_jsonable(step: StepResult) -> dict[str, Any]:
    from dataclasses import asdict

    d = asdict(step)
    status = d.get("status")
    d["status"] = getattr(status, "value", status)
    return d


def _report_to_jsonable(report: BatteryReport) -> dict[str, Any]:
    return {
        "timestamp": report.timestamp,
        "account_id": report.account_id,
        "environment": report.environment,
        "dry_run": report.dry_run,
        "all_passed": report.all_passed,
        "steps": [_step_to_jsonable(s) for s in report.steps],
    }


def _orchestrator_commit() -> str:
    """Resolve the current orchestrator repo commit via git rev-parse HEAD."""
    repo_root = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        return "unknown"
    return proc.stdout.strip()


def _content_sha256(payload: str) -> str:
    """SHA-256 hex digest of a UTF-8 string (corruption detection only)."""
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    """Write JSON to path via atomic temp-file + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(
        path.suffix + f".tmp.{os.getpid()}.{int(datetime.now(timezone.utc).timestamp() * 1000)}"
    )
    tmp.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)
