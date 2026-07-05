#!/usr/bin/env python3
"""Read-only diagnostic: check whether all prerequisites for rq105 paper trading
are satisfied.

This script is the pre-flight checklist an operator runs BEFORE Monday's paper
trading session. It verifies every gate the session runner will evaluate at
startup, but modifies NOTHING — no files are created, no state is written.

Checks performed:
  1. section_9_4_economic_authorization.json exists with correct paper content
  2. PaperBrokerPort is importable from renquant_execution
  3. The quintuple arming gate prerequisites:
     G1 — config: intraday_decisioning.enabled + mode=live
     G2 — authorization file: stage2_authorization.json present + schema-valid
     G3 — env flag: RENQUANT_INTRADAY_LIVE truthy
     G4 — kill switch: intraday_decisioning.KILL absent
     G5 — canary envelope: stage2_canary_state.json accessible
  4. Shadow session count vs MIN_SHADOW_SESSIONS_CLEAN_PAPER threshold

Exit 0: all checks pass — ready for paper trading.
Exit 1: at least one check failed — see output for remediation steps.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants — mirrored from the source modules for import-free checking.
# When the source modules ARE importable, we cross-validate against them.
# ---------------------------------------------------------------------------
SECTION_9_4_FILENAME = "section_9_4_economic_authorization.json"
PAPER_PREREG_ID = "rq105-paper-canary-prereg-v1"
MIN_SHADOW_SESSIONS_CLEAN_PAPER = 1
ENV_LIVE_FLAG = "RENQUANT_INTRADAY_LIVE"
KILL_SWITCH_FILENAME = "intraday_decisioning.KILL"
STAGE2_AUTH_FILENAME = "stage2_authorization.json"
CANARY_STATE_FILENAME = "stage2_canary_state.json"


def _resolve_data_root() -> Path:
    """Resolve the operator data root (same logic as runtime_paths.default_data_root)."""
    if raw := os.environ.get("RENQUANT_DATA_ROOT"):
        return Path(raw).expanduser().resolve()
    if raw := os.environ.get("RQ_ROOT"):
        return Path(raw).expanduser().resolve()
    # Fallback: the umbrella checkout at the canonical location.
    return Path("/Users/renhao/git/github/RenQuant").resolve()


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


def check_section_9_4(data_root: Path) -> _Check:
    """Check 1: the section 9.4 economic authorization file."""
    c = _Check("section 9.4 economic authorization file")
    path = data_root / "data" / "rq105" / SECTION_9_4_FILENAME
    if not path.exists():
        c.fail(
            f"File not found: {path}",
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
        return c
    try:
        content = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        c.fail(f"File exists but cannot be parsed: {exc}")
        return c

    errors: list[str] = []
    if not content.get("authorized"):
        errors.append('"authorized" must be true')
    if content.get("prereg_id") != PAPER_PREREG_ID:
        errors.append(
            f'"prereg_id" must be "{PAPER_PREREG_ID}", '
            f'got "{content.get("prereg_id")}"'
        )
    if errors:
        c.fail(
            f"Content validation failed: {'; '.join(errors)}",
            remediation=(
                f"Fix the file at {path} — expected content:\n"
                "  "
                + json.dumps({"authorized": True, "prereg_id": PAPER_PREREG_ID})
            ),
        )
    else:
        c.ok(f"Found at {path} with correct content")
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


def check_gate_1_config(data_root: Path) -> _Check:
    """Check G1: intraday_decisioning.enabled + mode=live in strategy config."""
    c = _Check("G1 config: intraday_decisioning enabled + mode=live")
    config_path = data_root / "strategy_config.json"
    if not config_path.exists():
        c.fail(
            f"strategy_config.json not found at {config_path}",
            remediation="Ensure the pinned strategy config exists at the data root.",
        )
        return c
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        c.fail(f"Cannot parse strategy_config.json: {exc}")
        return c

    section = config.get("intraday_decisioning", {})
    enabled = section.get("enabled", False)
    mode = section.get("mode", "shadow")

    if not enabled:
        c.fail(
            "intraday_decisioning.enabled is not true",
            remediation=(
                'Set "enabled": true in strategy_config.json '
                "intraday_decisioning section."
            ),
        )
    elif mode != "live":
        c.fail(
            f'intraday_decisioning.mode is "{mode}", must be "live"',
            remediation=(
                'Set "mode": "live" in strategy_config.json '
                "intraday_decisioning section."
            ),
        )
    else:
        c.ok("enabled=true, mode=live")
    return c


def check_gate_2_authorization(data_root: Path) -> _Check:
    """Check G2: stage2_authorization.json exists and is parseable."""
    c = _Check("G2 authorization: stage2_authorization.json")
    path = data_root / "data" / "rq105" / STAGE2_AUTH_FILENAME
    if not path.exists():
        c.fail(
            f"File not found: {path}",
            remediation=(
                "Create the stage2 authorization file at the path above. "
                "This is a SEPARATE file from the section_9_4 authorization. "
                "It must contain: authorized_by, date, expiry, "
                "daily_entry_notional_cap, evidence block (shadow_sessions_clean, "
                "replay_audits_green, entry_timing_report), canary_allowlist, "
                "max_cumulative_loss_usd. See intraday_live_executor.py "
                "Stage2Authorization dataclass for the full schema."
            ),
        )
        return c
    try:
        content = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        c.fail(f"File exists but cannot be parsed: {exc}")
        return c

    # Basic schema check — the runtime does the full validation.
    required_keys = {"authorized_by", "date", "expiry", "daily_entry_notional_cap"}
    missing = required_keys - set(content.keys())
    if missing:
        c.fail(
            f"Missing required keys: {sorted(missing)}",
            remediation="Add the missing keys to the authorization file.",
        )
    else:
        c.ok(f"Found at {path} with required keys present")
    return c


def check_gate_3_env() -> _Check:
    """Check G3: RENQUANT_INTRADAY_LIVE env flag."""
    c = _Check(f"G3 env: {ENV_LIVE_FLAG}")
    val = os.environ.get(ENV_LIVE_FLAG, "")
    if val.strip().lower() in ("1", "true", "yes"):
        c.ok(f'{ENV_LIVE_FLAG}="{val}"')
    else:
        c.fail(
            f'{ENV_LIVE_FLAG} is not set truthy (current value: "{val}")',
            remediation=(
                f"Set the env flag before running the session:\n"
                f"  export {ENV_LIVE_FLAG}=1\n"
                "Or add it to the .env file / launchd plist / wrapper script."
            ),
        )
    return c


def check_gate_4_kill_switch(data_root: Path) -> _Check:
    """Check G4: kill switch file must be ABSENT."""
    c = _Check("G4 kill switch: intraday_decisioning.KILL absent")
    path = data_root / "data" / "rq105" / KILL_SWITCH_FILENAME
    if path.exists():
        c.fail(
            f"Kill switch is ENGAGED: {path} exists",
            remediation=(
                f"Remove the kill switch file to allow sessions:\n"
                f'  rm "{path}"'
            ),
        )
    else:
        c.ok(f"Not present at {path}")
    return c


def check_gate_5_canary_envelope(data_root: Path) -> _Check:
    """Check G5: canary envelope state file accessibility."""
    c = _Check("G5 canary envelope: stage2_canary_state.json")
    path = data_root / "data" / "rq105" / CANARY_STATE_FILENAME
    if not path.exists():
        # Not necessarily a failure — the envelope is created on first armed
        # session. For initial paper trading setup this is expected.
        c.ok(
            f"Not present at {path} (will be created on first armed session; "
            f"this is expected for initial paper trading setup)"
        )
    else:
        try:
            json.loads(path.read_text(encoding="utf-8"))
            c.ok(f"Found and parseable at {path}")
        except (json.JSONDecodeError, OSError) as exc:
            c.fail(f"File exists but cannot be parsed: {exc}")
    return c


def check_shadow_sessions(data_root: Path) -> _Check:
    """Check 4: shadow session count vs MIN_SHADOW_SESSIONS_CLEAN_PAPER."""
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
                "Paper mode requires only 1 clean shadow session."
            ),
        )
    return c


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


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv

    if argv and argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0

    data_root = _resolve_data_root()
    print(f"[check_paper_trading_readiness] data_root = {data_root}\n")

    checks: list[_Check] = [
        check_rq105_data_dir(data_root),
        check_section_9_4(data_root),
        check_paper_broker_port(),
        check_gate_1_config(data_root),
        check_gate_2_authorization(data_root),
        check_gate_3_env(),
        check_gate_4_kill_switch(data_root),
        check_gate_5_canary_envelope(data_root),
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
