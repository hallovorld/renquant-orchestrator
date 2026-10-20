#!/usr/bin/env python3
"""Mechanical eligibility for the small-change fast path (doc/progress/2026-10-17-small-change-fast-path-proposal.md).

Pure decision: given a PR's changed files (path + additions + deletions), its labels and the number of
fast-path merges already made in the last 24 h, say whether the PR may skip the codex APPROVE.  The
author never decides; "small" is a path/size fact.  Anything unparseable is NOT eligible (fail closed).

Eligible iff ALL hold:
  1. every path matches the ALLOW list (docs + tests only - the operator chose the conservative list);
  2. no path matches a PROTECTED pattern (this check also refuses PROD_PATH_RULES);
  3. <= MAX_FILES files and <= MAX_LINES changed lines;
  4. label ``fast-path`` is present;
  5. fewer than DAILY_LIMIT fast-path merges in the last 24 h.
Green CI and the progress doc are enforced by their own required checks and are NOT waived.

CLI:  fast_path_eligibility.py --files files.json --labels a,b --merged-24h N
      files.json = ``gh api repos/O/R/pulls/N/files --paginate`` output.  Prints one JSON verdict line;
      exit 0 = eligible, 1 = not eligible, 2 = unreadable input.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

LABEL = "fast-path"
MAX_FILES = 3
MAX_LINES = 40
DAILY_LIMIT = 3

ALLOW = (
    re.compile(r"^doc/.+"),
    re.compile(r"^[^/]+\.md$"),
    re.compile(r"^.+\.md$"),
    re.compile(r"^tests/.+\.py$"),
)

PROTECTED = (
    re.compile(r"(^|/)data/"),
    re.compile(r"(^|/)strategy_config[^/]*\.json$"),
    re.compile(r"(^|/)artifacts/"),
    re.compile(r"^subrepos\.lock\.json"),
    re.compile(r"(^|/)launchd_manifest\.json$"),
    re.compile(r"(^|/)sentinel_acks\.json$"),
    re.compile(r"^doc/memory/long-term-agreements\.md$"),
    re.compile(r"^doc/memory/fast-path"),
    re.compile(r"^doc/progress/[^/]*small-change-fast-path"),
    re.compile(r"^\.github/"),
    re.compile(r"(^|/)CODEOWNERS$"),
    re.compile(r"\.plist$"),
    re.compile(r"^scripts/fast_path_eligibility\.py$"),
    re.compile(r"^tests/test_fast_path_eligibility\.py$"),
    # mirrors agent_workflows.PROD_PATH_RULES
    re.compile(r"(^|/)live_state(?:\.[^/]+)?\.json$", re.I),
    re.compile(r"(^|/)(?:artifacts/)?(?:walkforward[^/]*|wf[^/]*)/.*\.(?:parquet|csv|db|jsonl)$", re.I),
    re.compile(r"\.parquet$", re.I),
)


def evaluate(files: list[dict], labels: list[str], merged_24h: int) -> dict:
    reasons: list[str] = []
    if LABEL not in labels:
        reasons.append(f"missing label {LABEL!r}")
    if not files:
        reasons.append("no changed files reported (fail closed)")
    lines = 0
    for f in files:
        path = str(f.get("filename") or f.get("path") or "")
        try:
            lines += int(f["additions"]) + int(f["deletions"])
        except (KeyError, TypeError, ValueError):
            reasons.append(f"unreadable size for {path!r} (fail closed)")
        if not path:
            reasons.append("file entry without a path (fail closed)")
            continue
        if any(p.search(path) for p in PROTECTED):
            reasons.append(f"protected path {path}")
        elif not any(p.match(path) for p in ALLOW):
            reasons.append(f"path outside the allow-list {path}")
        if f.get("status") in ("removed", "renamed") and any(p.search(str(f.get("previous_filename") or path)) for p in PROTECTED):
            reasons.append(f"protected path removed/renamed {path}")
    if len(files) > MAX_FILES:
        reasons.append(f"{len(files)} files > {MAX_FILES}")
    if lines > MAX_LINES:
        reasons.append(f"{lines} changed lines > {MAX_LINES}")
    if merged_24h >= DAILY_LIMIT:
        reasons.append(f"{merged_24h} fast-path merges in the last 24h >= daily limit {DAILY_LIMIT}")
    return {"eligible": not reasons, "reasons": reasons, "files": len(files), "lines": lines,
            "merged_24h": merged_24h}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--files", required=True, type=Path)
    ap.add_argument("--labels", default="")
    ap.add_argument("--merged-24h", type=int, required=True)
    a = ap.parse_args(argv)
    try:
        files = json.loads(a.files.read_text())
        if not isinstance(files, list):
            raise ValueError("files json is not a list")
    except (OSError, ValueError) as exc:
        print(json.dumps({"eligible": False, "reasons": [f"unreadable input: {exc}"]}))
        return 2
    verdict = evaluate(files, [x.strip() for x in a.labels.split(",") if x.strip()], a.merged_24h)
    print(json.dumps(verdict, sort_keys=True))
    return 0 if verdict["eligible"] else 1


if __name__ == "__main__":
    sys.exit(main())
