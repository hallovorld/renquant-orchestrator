#!/usr/bin/env python3
"""Fail a PR that adds/changes no durable doc/progress/<date>-<slug>.md record.

Every renquant-orchestrator PR must include a progress record — the durable
WHAT/WHY-DIR/EVIDENCE/NEXT artifact future operators audit. This is a hard repo
contract (Codex denies PRs without it). Enforcing it in CI makes it impossible to
forget instead of relying on memory.

Reads changed file paths (one per line) from a file arg or stdin; exit 0 if at least
one matches doc/progress/<YYYY-MM-DD>-<slug>.md, else exit 1 with a helpful message.
"""
from __future__ import annotations

import re
import sys

PATTERN = re.compile(r"^doc/progress/\d{4}-\d{2}-\d{2}-.+\.md$")


def has_progress_doc(paths) -> bool:
    return any(PATTERN.match(p.strip()) for p in paths if p and p.strip())


def main() -> int:
    data = open(sys.argv[1]).read() if len(sys.argv) > 1 else sys.stdin.read()
    if has_progress_doc(data.splitlines()):
        print("✓ progress record present")
        return 0
    print(
        "::error::This PR adds/changes no doc/progress/<date>-<slug>.md durable record. "
        "Every PR must include one (STATUS / WHAT / WHY-DIR / EVIDENCE / NEXT; ~12 lines; "
        "end EVIDENCE with a `[VERIFIED — ...]` tag). Format reference: "
        "doc/progress/2026-06-23-trade-review-skill-design.md. The progress doc is the SINGLE "
        "durable record — keep the PR body short and do not duplicate it.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
