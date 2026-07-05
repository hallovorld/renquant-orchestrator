#!/usr/bin/env python3
"""Read-only diagnostic: check whether all prerequisites for rq105 paper trading
are satisfied.

This script is the pre-flight checklist an operator runs BEFORE Monday's paper
trading session. It verifies every gate the session runner will evaluate at
startup, but modifies NOTHING — no files are created, no state is written.

Every check below calls into the SAME authoritative functions the session
runner itself uses (``check_section_9_4_authorization``, ``resolve_stage2_arming``,
``load_intraday_config``, the real gate/threshold constants) rather than
maintaining a parallel copy of the gate contract. If the gate semantics move,
this script moves with them automatically — there is no second source of
truth to go stale.

Checks performed:
  1. section_9_4_economic_authorization.json exists with correct paper content
     (via ``intraday_session_runner.check_section_9_4_authorization``)
  2. PaperBrokerPort is importable from renquant_execution
  3. The full §9.3a quintuple arming gate (via
     ``intraday_live_executor.resolve_stage2_arming`` — the exact function
     ``SessionRunner._evaluate_arming`` calls)
  4. Shadow session count vs the real MIN_SHADOW_SESSIONS_CLEAN_PAPER threshold

Exit 0: all checks pass — ready for paper trading.
Exit 1: at least one check failed — see output for remediation steps.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from renquant_orchestrator.intraday_live_executor import (  # noqa: E402
    MIN_SHADOW_SESSIONS_CLEAN_PAPER,
    default_authorization_path,
    default_canary_state_path,
    resolve_stage2_arming,
)
from renquant_orchestrator.intraday_session_runner import (  # noqa: E402
    PAPER_PREREG_ID,
    SECTION_9_4_FILENAME,
    build_kill_switch,
    check_section_9_4_authorization,
)
from renquant_orchestrator.intraday_session_scheduler import (  # noqa: E402
    load_intraday_config,
)
from renquant_orchestrator.runtime_paths import default_data_root  # noqa: E402


class _Check:
    """One pass/fail check with a label and remediation hint."""

    def __init__(self, label: str) -> None:
        self.label = label
        self.passed = False
        self.detail = ""
        self.remediation = ""

    def ok(self, detail: str = "") -> None:
        self.passed = True
        self.detail = detail

    def fail(self, detail: str, remediation: str = "") -> None:
        self.passed = False
        self.detail = detail
        self.remediation = remediation


def check_rq105_data_dir(data_root: Path) -> _Check:
    """Prerequisite: the data/rq105 directory exists."""
    c = _Check("data/rq105 directory exists")
    path = data_root / "data" / "rq105"
    if path.is_dir():
        c.ok(f"Found at {path}")
    else:
        c.fail(
            f"Directory not found: {path}",
            remediation=f'Create it with:\n  mkdir -p "{path}"',
        )
    return c


def check_section_9_4(data_root: Path) -> _Check:
    """Check 1: the §9.4 economic authorization file — via the real
    ``check_section_9_4_authorization`` the session runner itself calls."""
    c = _Check("section 9.4 economic authorization file")
    path = data_root / "data" / "rq105" / SECTION_9_4_FILENAME
    authorized, is_paper = check_section_9_4_authorization(data_root)
    if not authorized:
        c.fail(
            f"Not authorized (file missing, unparseable, or content invalid): {path}",
            remediation=(
                "Create the file with:\n"
                f'  mkdir -p "{path.parent}"\n'
                f'  cat > "{path}" << \'HEREDOC\'\n'
                "  "
                + json.dumps({"authorized": True, "prereg_id": PAPER_PREREG_ID})
                + "\n"
                "  HEREDOC"
            ),
        )
    elif not is_paper:
        c.fail(
            f'Authorized, but prereg_id does not match PAPER_PREREG_ID '
            f'("{PAPER_PREREG_ID}")',
            remediation=(
                f"Fix the file at {path} — expected content:\n"
                "  "
                + json.dumps({"authorized": True, "prereg_id": PAPER_PREREG_ID})
            ),
        )
    else:
        c.ok(f"Found at {path}, authorized, paper mode confirmed")
    return c


def check_paper_broker_port() -> _Check:
    """Check 2: PaperBrokerPort importable."""
    c = _Check("PaperBrokerPort importable")
    try:
        from renquant_execution.paper_broker_port import PaperBrokerPort  # noqa: F401

        c.ok("importable from renquant_execution.paper_broker_port")
    except ImportError as exc:
        c.fail(
            f"Cannot import PaperBrokerPort: {exc}",
            remediation=(
                "Ensure renquant-execution is installed and the paper_broker_port "
                "module exists. Check that the umbrella .venv or PYTHONPATH includes "
                "the renquant-execution package."
            ),
        )
    return c


def check_quintuple_arming_gate(data_root: Path) -> _Check:
    """Check 3: the full §9.3a quintuple arming gate — via the real
    ``resolve_stage2_arming``, the exact function
    ``SessionRunner._evaluate_arming`` calls, with the same inputs
    (``load_intraday_config``, the real authorization/canary paths, a real
    ``KillSwitch``). This is READ-ONLY: no session is armed or run, we just
    ask the authoritative gate function what its verdict would be today."""
    c = _Check("§9.3a quintuple arming gate (config/auth/env/kill/envelope)")

    strategy_config_path = data_root / "strategy_config.json"
    if not strategy_config_path.exists():
        c.fail(
            f"strategy_config.json not found at {strategy_config_path}",
            remediation="Ensure the pinned strategy config exists at the data root.",
        )
        return c
    try:
        strategy_config = json.loads(strategy_config_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        c.fail(f"Cannot parse strategy_config.json: {exc}")
        return c

    intraday_config = load_intraday_config(strategy_config)
    kill_switch = build_kill_switch(intraday_config=intraday_config, data_root=data_root)
    _, is_paper = check_section_9_4_authorization(data_root)
    today = dt.date.today().isoformat()

    arming = resolve_stage2_arming(
        config=intraday_config,
        authorization_path=default_authorization_path(data_root),
        canary_state_path=default_canary_state_path(data_root),
        kill_switch=kill_switch,
        today=today,
        paper=is_paper,
    )

    if arming.armed:
        c.ok(f"ARMED — mode_effective={arming.mode_effective}")
    else:
        c.fail(
            f"NOT armed (mode_effective={arming.mode_effective}, "
            f"gates={dict(arming.gates)})",
            remediation="; ".join(arming.reasons) or "See arming.reasons for detail.",
        )
    return c


def check_shadow_sessions(data_root: Path) -> _Check:
    """Check 4: shadow session count vs the real
    MIN_SHADOW_SESSIONS_CLEAN_PAPER threshold."""
    c = _Check(
        f"Shadow session evidence >= {MIN_SHADOW_SESSIONS_CLEAN_PAPER} "
        f"clean session(s)"
    )
    log_dir = data_root / "logs" / "renquant105_pilot"
    if not log_dir.exists():
        c.fail(
            f"Shadow log directory not found: {log_dir}",
            remediation=(
                "Run at least one shadow session to create the log directory. "
                f"The paper-mode threshold is {MIN_SHADOW_SESSIONS_CLEAN_PAPER} "
                "clean shadow session(s)."
            ),
        )
        return c

    # Count session manifests (each completed session writes one).
    manifests = sorted(log_dir.glob("session_manifest_*.json")) + sorted(
        log_dir.glob("intraday_session_manifest_*.json")
    )
    count = len(manifests)

    if count >= MIN_SHADOW_SESSIONS_CLEAN_PAPER:
        c.ok(
            f"Found {count} session manifest(s) in {log_dir} "
            f"(threshold: {MIN_SHADOW_SESSIONS_CLEAN_PAPER})"
        )
    else:
        c.fail(
            f"Only {count} session manifest(s) found in {log_dir}, "
            f"need >= {MIN_SHADOW_SESSIONS_CLEAN_PAPER}",
            remediation=(
                "Run shadow sessions until the threshold is met. "
                f"Paper mode requires only {MIN_SHADOW_SESSIONS_CLEAN_PAPER} "
                "clean shadow session(s)."
            ),
        )
    return c


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv

    if argv and argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0

    data_root = default_data_root()
    print(f"[check_paper_trading_readiness] data_root = {data_root}\n")

    checks: list[_Check] = [
        check_rq105_data_dir(data_root),
        check_section_9_4(data_root),
        check_paper_broker_port(),
        check_quintuple_arming_gate(data_root),
        check_shadow_sessions(data_root),
    ]

    # Print results.
    all_ok = True
    for c in checks:
        mark = "PASS" if c.passed else "FAIL"
        print(f"  [{mark}] {c.label}")
        if c.detail:
            print(f"         {c.detail}")
        if not c.passed:
            all_ok = False

    # Print remediation for failures.
    failures = [c for c in checks if not c.passed]
    if failures:
        print(f"\n--- {len(failures)} check(s) FAILED ---\n")
        for i, c in enumerate(failures, 1):
            print(f"{i}. {c.label}")
            if c.remediation:
                for line in c.remediation.split("\n"):
                    print(f"   {line}")
            print()

    if all_ok:
        print(
            "\n[check_paper_trading_readiness] ALL CHECKS PASSED "
            "-- ready for paper trading."
        )
        return 0
    else:
        print(
            f"[check_paper_trading_readiness] {len(failures)} check(s) failed "
            "-- fix the items above before enabling paper trading.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
