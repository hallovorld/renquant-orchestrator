"""Classify weekly walk-forward promote logs into actionable failure modes."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any


DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")

FAILURE_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "manifest_recipe_mismatch": (
        re.compile(r"manifest recipe mismatch", re.IGNORECASE),
        re.compile(r"manifest artifacts do not match candidate recipe", re.IGNORECASE),
    ),
    "config_parity_failed": (
        re.compile(r"WF config parity failed", re.IGNORECASE),
    ),
    "sim_cuts_failed": (
        re.compile(r"sim cuts? failed execution", re.IGNORECASE),
        re.compile(r"sim cut .*failed", re.IGNORECASE),
    ),
    "sim_parse_failed": (
        re.compile(r"all sim cuts failed parse", re.IGNORECASE),
        re.compile(r"sim cuts? failed parse", re.IGNORECASE),
    ),
    "zero_trades": (
        re.compile(r"zero trades across all WF cuts", re.IGNORECASE),
        re.compile(r"\b0 trades\b", re.IGNORECASE),
    ),
    "benchmark_regime_failed": (
        re.compile(r"\babsolute_ok=False\b"),
        re.compile(r"\bbenchmark_ok=False\b"),
        re.compile(r"\bregime_ok=False\b"),
    ),
}

PASS_PATTERNS = (
    re.compile(r"\bVERDICT:\s*PASS\b", re.IGNORECASE),
    re.compile(r"\bWF result:\s*PASS\b", re.IGNORECASE),
)
FAIL_PATTERNS = (
    re.compile(r"\bVERDICT:\s*FAIL\b", re.IGNORECASE),
    re.compile(r"\bWF result:\s*FAIL\b", re.IGNORECASE),
    re.compile(r"\bFAILED\b", re.IGNORECASE),
)


def _extract_date(name: str) -> str | None:
    match = DATE_RE.search(name)
    return match.group(1) if match else None


def classify_log_text(text: str, *, name: str = "") -> dict[str, Any]:
    """Classify one weekly WF promote log.

    The classifier intentionally keys off stable gate phrases emitted by
    RenQuant scripts instead of trying to infer market/model state from
    surrounding prose. That keeps the output auditable and deterministic.
    """
    lines = text.splitlines()
    failure_modes: list[str] = []
    evidence: list[dict[str, str | int]] = []

    for mode, patterns in FAILURE_PATTERNS.items():
        for line_no, line in enumerate(lines, start=1):
            if any(pattern.search(line) for pattern in patterns):
                failure_modes.append(mode)
                evidence.append({
                    "mode": mode,
                    "line": line_no,
                    "text": line.strip()[:240],
                })
                break

    has_pass = any(pattern.search(text) for pattern in PASS_PATTERNS)
    has_fail = any(pattern.search(text) for pattern in FAIL_PATTERNS)
    if failure_modes or has_fail:
        verdict = "fail"
    elif has_pass:
        verdict = "pass"
    else:
        verdict = "unknown"

    if verdict == "fail" and not failure_modes:
        failure_modes.append("unknown_failure")

    return {
        "file": name,
        "date": _extract_date(name),
        "verdict": verdict,
        "failure_modes": failure_modes,
        "evidence": evidence,
    }


def triage_log_dir(log_dir: Path | str, *, since: str | None = None) -> dict[str, Any]:
    """Classify every regular file under ``log_dir`` and summarize failures."""
    root = Path(log_dir)
    if not root.exists():
        raise FileNotFoundError(f"log directory does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"log path is not a directory: {root}")

    files: list[dict[str, Any]] = []
    skipped_files: list[dict[str, str]] = []
    for path in sorted(item for item in root.iterdir() if item.is_file()):
        date = _extract_date(path.name)
        if since is not None and date is None:
            skipped_files.append({"file": path.name, "reason": "no_filename_date"})
            continue
        if since is not None and date is not None and date < since:
            skipped_files.append({"file": path.name, "reason": "before_since"})
            continue
        result = classify_log_text(path.read_text(encoding="utf-8", errors="replace"), name=path.name)
        files.append(result)

    by_mode: dict[str, int] = {}
    failed_files = 0
    unknown_files = 0
    for result in files:
        if result["verdict"] == "fail":
            failed_files += 1
        if result["verdict"] == "unknown":
            unknown_files += 1
        for mode in result["failure_modes"]:
            by_mode[mode] = by_mode.get(mode, 0) + 1

    return {
        "log_dir": str(root),
        "since": since,
        "files": files,
        "skipped_files": skipped_files,
        "summary": {
            "total_files": len(files),
            "skipped_files": len(skipped_files),
            "failed_files": failed_files,
            "unknown_files": unknown_files,
            "passed_files": sum(1 for result in files if result["verdict"] == "pass"),
            "by_mode": dict(sorted(by_mode.items())),
            "ok": failed_files == 0 and unknown_files == 0,
        },
    }
