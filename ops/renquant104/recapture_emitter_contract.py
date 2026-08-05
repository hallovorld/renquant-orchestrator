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
import subprocess
import sys
from collections import defaultdict

UMBRELLA = pathlib.Path("/Users/renhao/git/github/RenQuant")
CONTRACT = pathlib.Path(__file__).resolve().parent / "emitter_contract.json"


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
        lines = path.read_text(errors="ignore").splitlines()
        hits = sorted(i + 1 for i, ln in enumerate(lines) if template in ln)
        if len(hits) != len(rows):
            raise SystemExit(
                f"REFUSING: {rel} has {len(hits)} emit site(s) for {template!r} but "
                f"the contract records {len(rows)} row(s). That is a real emitter "
                f"change, not a line shift — re-verify the sentinel's pattern still "
                f"classifies this lane before touching the contract.")
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
