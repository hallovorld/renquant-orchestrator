#!/usr/bin/env python3
"""Re-capture `emitter_contract.json` line pins + wrapper digests from the live wrappers.

The contract pins each watched emitter line to `<script>:<line>` so a stale citation
cannot survive a presence-only check (codex on orch#785). The cost is that ANY edit
to a wrapper above a watched line reds the local drift test — twice in two days
(RQ#568 +24 lines, RQ#580 +24 more). Hand-editing five line numbers is exactly the
kind of mechanical re-derivation that gets done wrong, so it is a tool.

What this does NOT do: change any TEMPLATE. If a template no longer appears, or the
number of emit sites stops matching the number of contract rows, it refuses — that
is real drift and needs a human to decide whether the pattern still classifies
correctly. Only positions and digests are re-derived.

Usage:  python -m ops.renquant104.recapture_emitter_contract [--check] [--note TEXT]
        --check exits 1 without writing if anything would change (CI-safe).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import subprocess
import sys
from collections import defaultdict

# A contracted line is an EMITTER line — the wrapper actually printing it. Matching
# on the template substring alone is not enough: a comment, a docstring, or a
# pattern list that quotes the same text would be silently re-pinned as if it were
# the emit site, and a template that VANISHED from every echo would then re-pin to
# its own obituary instead of refusing. [codex on orch#804]
_EMITTER_CMD = re.compile(r"\b(?:echo|printf|notify)\b")

UMBRELLA = pathlib.Path("/Users/renhao/git/github/RenQuant")
CONTRACT = pathlib.Path(__file__).resolve().parent / "emitter_contract.json"


_HEREDOC_OPEN = re.compile(r"<<(-?)\s*(['\"]?)([A-Za-z_][A-Za-z_0-9]*)\2")


def _strip_unquoted_comment(prefix: str) -> tuple[str, bool]:
    """Return (code part of `prefix`, commented_out).

    A `#` only starts a comment OUTSIDE quotes. `echo "#tag === X ==="` is a
    real emit site whose prefix contains a `#` inside a string — rejecting it
    would refuse a legitimate re-capture forever, which is worse than the
    false positive it was guarding against. [codex on orch#804]
    """
    single = double = False
    for i, ch in enumerate(prefix):
        if ch == "'" and not double:
            single = not single
        elif ch == '"' and not single:
            double = not double
        elif ch == "#" and not single and not double:
            return prefix[:i], True
    return prefix, False


def _is_emitter_line(line: str, template: str) -> bool:
    """True only if `line` is a shell statement that EMITS `template`.

    Requires an emitter command (`echo`/`printf`/`notify`) ahead of the text and
    that the occurrence is not inside a comment — so quoting the template in a
    comment or a grep pattern list is not an emit site. Quote-aware, so a `#`
    inside the emitted string does not make it look like a comment.

    Line-level only: a line inside a here-doc body never executes, and that
    cannot be seen from one line. `_emit_sites` handles it.
    """
    if template not in line:
        return False
    if line.lstrip().startswith("#"):
        return False
    prefix, commented = _strip_unquoted_comment(line[:line.index(template)])
    if commented:
        return False
    return bool(_EMITTER_CMD.search(prefix))


def _emit_sites(text: str, template: str) -> list[int]:
    """1-indexed lines of `text` that actually EMIT `template`.

    Skips here-doc bodies. `: <<'BLOCK' ... BLOCK` is the idiomatic shell block
    comment, and an `echo` inside one never runs — re-pinning to it is the same
    class of error as re-pinning to a `#` comment. [codex on orch#804]

    Conservative by design: if a real emitter ever moves INSIDE a here-doc, this
    under-counts, `recapture` refuses on the count mismatch, and a human looks.
    Refusing is the safe direction; silently re-pinning is not.
    """
    sites: list[int] = []
    delimiter: str | None = None
    tabs_ok = False
    for i, line in enumerate(text.splitlines(), start=1):
        if delimiter is not None:
            # Shell-correct close: `<<EOF` ends only on a line that is EXACTLY
            # the delimiter — `  EOF` does NOT close it. `<<-EOF` permits
            # leading TABS only, never spaces. Closing on `line.strip()` made
            # the tracker end a here-doc early and re-pin to an echo bash is
            # still swallowing as body. [codex on orch#804, verified against
            # bash 2026-08-05]
            candidate = line.lstrip("\t") if tabs_ok else line
            if candidate == delimiter:
                delimiter = None
            continue
        opened = _HEREDOC_OPEN.search(line)
        if _is_emitter_line(line, template):
            sites.append(i)
        if opened:
            tabs_ok = opened.group(1) == "-"
            delimiter = opened.group(3)
    return sites


def recapture(contract: dict, umbrella: pathlib.Path) -> list[str]:
    """Mutate `contract` in place; return a human-readable list of what moved."""
    changed: list[str] = []
    groups: dict[tuple[str, str], list] = defaultdict(list)
    for row in contract["lines"]:
        rel, line = row["source"].rsplit(":", 1)
        groups[(rel, row["template"])].append((int(line), row))

    for (rel, template), rows in groups.items():
        path = umbrella / rel
        if not path.exists():
            raise SystemExit(f"REFUSING: {rel} absent — cannot re-capture off-machine")
        text = path.read_text(errors="ignore")
        hits = _emit_sites(text, template)
        if len(hits) != len(rows):
            raise SystemExit(
                f"REFUSING: {rel} has {len(hits)} emit site(s) for {template!r} but "
                f"the contract records {len(rows)} row(s). That is a real emitter "
                f"change, not a line shift — re-verify the sentinel's pattern still "
                f"classifies this lane before touching the contract. (An emit site "
                f"is an echo/printf/notify statement; a comment or a pattern list "
                f"quoting the same text does not count.)")
        for (old, row), new in zip(sorted(rows, key=lambda r: r[0]), hits):
            if old != new:
                changed.append(f"{rel}:{old} -> :{new}")
            row["source"] = f"{rel}:{new}"

    for rel in contract["wrappers"]:
        digest = hashlib.sha256((umbrella / rel).read_bytes()).hexdigest()[:16]
        if digest != contract["wrappers"][rel]:
            changed.append(f"{rel} sha256 {contract['wrappers'][rel]} -> {digest}")
        contract["wrappers"][rel] = digest
    return changed


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="report drift and exit 1 without writing")
    ap.add_argument("--note", default="",
                    help="what changed upstream, e.g. 'after RQ#580'")
    ap.add_argument("--umbrella", type=pathlib.Path, default=UMBRELLA)
    ap.add_argument("--contract", type=pathlib.Path, default=CONTRACT)
    args = ap.parse_args(argv)

    contract = json.loads(args.contract.read_text())
    changed = recapture(contract, args.umbrella)
    if not changed:
        print("emitter contract already matches the live wrappers — nothing to do")
        return 0
    for line in changed:
        print("RECAPTURED", line)
    if args.check:
        print("--check: contract is STALE (not written)")
        return 1
    # `date` is read, never asserted (LONG ledger).
    today = subprocess.run(["date", "+%Y-%m-%d"], capture_output=True,
                           text=True, check=True).stdout.strip()
    contract["captured"] = f"{today} | re-captured {args.note}".rstrip(" |")
    args.contract.write_text(json.dumps(contract, indent=2) + "\n")
    print(f"wrote {args.contract} (captured={contract['captured']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
