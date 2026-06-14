"""Execute the readonly live offboard rehearsal plan."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from .live_offboard_status import build_live_offboard_status
from .live_rehearsal_plan import build_live_rehearsal_plan


CommandRunner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]
REHEARSAL_STEPS = (
    "bridge_capture",
    "native_live_run_candidate",
    "native_live_parity",
)


def _tail(text: str, *, lines: int = 40) -> list[str]:
    return text.splitlines()[-lines:]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _default_runner(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _python_orchestrator_command(command: Sequence[str]) -> list[str]:
    if not command or command[0] != "renquant-orchestrator":
        raise ValueError(f"unsupported rehearsal command: {command!r}")
    return [sys.executable, "-m", "renquant_orchestrator", *command[1:]]


def run_live_offboard_rehearsal(
    *,
    mode: str = "live",
    output_dir: str | Path = "/tmp/renquant-live-rehearsal",
    broker: str = "readonly-alpaca",
    env_file: str | Path | None = None,
    include_execution_payload: bool = True,
    continue_on_failure: bool = False,
    runner: CommandRunner | None = None,
) -> dict[str, Any]:
    """Run the readonly bridge/native/parity evidence chain and write a manifest."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    run = runner or _default_runner

    plan = build_live_rehearsal_plan(
        mode=mode,
        output_dir=out,
        broker=broker,
        include_execution_payload=include_execution_payload,
        env_file=env_file,
    )
    _write_json(out / f"{mode}-rehearsal-plan.json", plan)

    steps: list[dict[str, Any]] = []
    ok = bool(plan["ready"])
    if ok:
        for step_name in REHEARSAL_STEPS:
            raw_command = plan["commands"][step_name]
            command = _python_orchestrator_command(raw_command)
            started = time.time()
            proc = run(command)
            elapsed = time.time() - started
            step = {
                "step": step_name,
                "command": raw_command,
                "executed_command": command,
                "returncode": proc.returncode,
                "duration_seconds": round(elapsed, 3),
                "stdout_tail": _tail(proc.stdout or ""),
                "stderr_tail": _tail(proc.stderr or ""),
                "ok": proc.returncode == 0,
            }
            steps.append(step)
            if proc.returncode != 0:
                ok = False
                if not continue_on_failure:
                    break
    final_status = build_live_offboard_status(
        mode=mode,
        output_dir=out,
        broker=broker,
        include_execution_payload=include_execution_payload,
        env_file=env_file,
    )
    _write_json(out / f"{mode}-offboard-status.json", final_status)

    payload = {
        "schema_version": 1,
        "mode": mode,
        "broker": broker,
        "output_dir": str(out),
        "plan_path": str(out / f"{mode}-rehearsal-plan.json"),
        "status_path": str(out / f"{mode}-offboard-status.json"),
        "ready_to_start": bool(plan["ready"]),
        "ok": ok and bool(final_status["stage_status"]["checks"].get("parity_ok")),
        "steps": steps,
        "final_stage_status": final_status["stage_status"],
        "blocking_reasons": final_status["blocking_reasons"],
        "ready_for_live_offboard": final_status["ready_for_live_offboard"],
        "notes": [
            "Readonly rehearsal only: native_live_commit_template is never executed.",
            "Production launchd cutover remains blocked until live-offboard-status is green and bridge jobs are explicitly replaced.",
        ],
    }
    _write_json(out / f"{mode}-offboard-rehearsal-manifest.json", payload)
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("live", "daily"), default="live")
    parser.add_argument("--broker", default="readonly-alpaca")
    parser.add_argument("--output-dir", default="/tmp/renquant-live-rehearsal")
    parser.add_argument("--env-file", default=None)
    parser.add_argument("--no-execution-payload", action="store_true")
    parser.add_argument("--continue-on-failure", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(list(argv or []))

    payload = run_live_offboard_rehearsal(
        mode=args.mode,
        output_dir=args.output_dir,
        broker=args.broker,
        env_file=args.env_file,
        include_execution_payload=not args.no_execution_payload,
        continue_on_failure=args.continue_on_failure,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["ok"] or not args.strict else 2


__all__ = ["REHEARSAL_STEPS", "run_live_offboard_rehearsal"]
