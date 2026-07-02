#!/usr/bin/env python3
"""Shared NUL-aware `git status --porcelain=v2 -z` parser.

Text-mode (non-`-z`) porcelain output delimits records with newlines and, for
rename/copy entries, separates the new path from the original path with an
internal tab — both are ambiguous for paths containing spaces, tabs, or
literal newlines (git C-quotes such paths in text mode instead, which
requires a *separate* un-quoting pass that ad hoc line/space-split parsers,
including an earlier version of this repo's own classifier, skip entirely).

`-z` mode is unambiguous: git disables path quoting and NUL-terminates every
field. Ordinary (`1`), unmerged (`u`), and untracked (`?`)/ignored (`!`)
entries are each one NUL-terminated token. Rename/copy (`2`) entries are TWO
consecutive NUL-terminated tokens for the SAME logical record: the
fields+newPath token, then a second token holding origPath alone —
consuming only one token per record misparses the following record as the
origPath for every rename/copy entry encountered.

Read-only: this module only ever invokes `git status`.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class PorcelainEntry:
    kind: str  # "ordinary" | "rename_copy" | "unmerged" | "untracked" | "ignored"
    xy: str
    path: str
    orig_path: str | None = None  # only set for kind == "rename_copy"


def run_git_status_porcelain_v2_nul(live_tree: str) -> list[PorcelainEntry]:
    """Read-only. Parses `git status --porcelain=v2 -z` into structured entries.

    No assumption is made about paths not containing spaces/tabs/newlines —
    the NUL terminator is the only delimiter relied on.
    """
    proc = subprocess.run(
        ["git", "-C", live_tree, "status", "--porcelain=v2", "-z"],
        capture_output=True, check=True,
    )
    tokens = proc.stdout.split(b"\0")
    if tokens and tokens[-1] == b"":
        tokens = tokens[:-1]  # trailing NUL produces one empty token at the end

    entries: list[PorcelainEntry] = []
    i = 0
    n = len(tokens)
    while i < n:
        raw = tokens[i].decode("utf-8", errors="surrogateescape")
        if raw.startswith("1 "):
            fields = raw.split(" ", 8)
            if len(fields) != 9:
                raise ValueError(f"malformed type-1 porcelain record: {raw!r}")
            entries.append(PorcelainEntry("ordinary", fields[1], fields[8]))
            i += 1
        elif raw.startswith("2 "):
            fields = raw.split(" ", 9)
            if len(fields) != 10:
                raise ValueError(f"malformed type-2 porcelain record: {raw!r}")
            if i + 1 >= n:
                raise ValueError(
                    f"type-2 (rename/copy) porcelain record missing its origPath "
                    f"token (truncated stream?): {raw!r}"
                )
            orig_path = tokens[i + 1].decode("utf-8", errors="surrogateescape")
            entries.append(PorcelainEntry("rename_copy", fields[1], fields[9], orig_path))
            i += 2  # consume both tokens of this one logical record
        elif raw.startswith("u "):
            fields = raw.split(" ", 10)
            if len(fields) != 11:
                raise ValueError(f"malformed type-u (unmerged) porcelain record: {raw!r}")
            entries.append(PorcelainEntry("unmerged", fields[1], fields[10]))
            i += 1
        elif raw.startswith("? "):
            entries.append(PorcelainEntry("untracked", "??", raw[2:]))
            i += 1
        elif raw.startswith("! "):
            entries.append(PorcelainEntry("ignored", "!!", raw[2:]))
            i += 1
        elif raw == "":
            i += 1  # stray empty token (defensive; observed harmless in some git versions)
        else:
            raise ValueError(f"unrecognized porcelain v2 record type: {raw!r}")
    return entries
