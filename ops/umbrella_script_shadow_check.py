#!/usr/bin/env python3
"""Umbrella scripts that SHADOW a subrepo module — which copy would a reader edit?

renquant-orchestrator#623 R2 is one instance: the umbrella's
`scripts/fetch_sec_fundamentals.py` is dead, the live producer is
`renquant-base-data`'s `sec_fundamentals.py`, and `_safe_ratio` exists **only in the
dead one**. A fix was applied to the wrong file and `book_to_price` reached `1.68e19`
on 1.6% of rows for five weeks afterwards.

R2 is not a one-off. Measured 2026-07-30 over 284 umbrella `scripts/*.py`:

* **44** name-shadow a module in a subrepo's `src/`;
* **32** of those are referenced by **no** `.sh` and **no** `com.renquant.*` plist;
* of those 32, **15 are byte-identical** to their subrepo twin and **17 have
  DIVERGED** — including `fit_walkforward_calibrators` (umbrella +11,979 B),
  `train_walkforward_patchtst` (−11,488 B) and `wf_config_builder` (−8,131 B), all in
  the WF-gate area where "which copy runs" has already cost real defects.

**SCOPE LIMIT, and it excludes R2 itself.** Matching is by **identical filename stem**.
R2's pair is umbrella `fetch_sec_fundamentals.py` against base-data
`sec_fundamentals.py` — **different stems**, so this sweep does not see it. A renamed
twin is invisible here, and renaming is exactly what makes a twin hard to spot by eye.
Catching those needs content similarity rather than names, which trades a clean signal
for false positives; that is a separate tool, not a quiet widening of this one. The
registry therefore covers same-stem shadows only, and R2 stays tracked by #623.

**What this tool does NOT claim.** "Not referenced by a `.sh` or a plist" is **not**
proof a script is dead — it can be run by hand, imported by other Python, or invoked by
an agent. And a shared filename is not proof of shared purpose. So every finding is
phrased as *a reader could plausibly edit the wrong copy*, never as *this file is dead*.
The remedy for that ambiguity is a per-file disposition in the registry, not a stronger
inference from absence.

**Read-only.** Reads the umbrella tree and `git show` from sibling repos. Writes
nothing, never invokes git *inside* the umbrella, never mutates a file.

Exit codes: ``0`` every shadow pair is registered, ``1`` an unregistered pair exists or a
registered one changed class, ``2`` usage/IO error.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

REGISTRY = Path(__file__).resolve().parent / "umbrella_script_shadows.json"
UMBRELLA = Path(os.environ.get("RQ_ROOT", "/Users/renhao/git/github/RenQuant"))
GITHUB = Path(os.environ.get("RQ_GITHUB_ROOT", "/Users/renhao/git/github"))
SIBLINGS = ("renquant-base-data", "renquant-orchestrator", "renquant-pipeline",
            "renquant-model", "renquant-execution", "renquant-backtesting",
            "renquant-common", "renquant-artifacts")

IDENTICAL = "IDENTICAL"
DIVERGED = "DIVERGED"


def _sh(argv: list[str]) -> bytes:
    return subprocess.run(argv, capture_output=True).stdout


def subrepo_modules() -> dict[str, list[tuple[str, str]]]:
    """stem -> [(repo, path)] for every `src/**/*.py` on each sibling's origin/main.

    Read via `git show`/`ls-tree` on **origin/main**, not the working tree: a sibling
    checkout can sit on a feature branch, and comparing against whatever happens to be
    checked out would make the answer depend on someone else's uncommitted state.
    """
    out: dict[str, list[tuple[str, str]]] = {}
    for repo in SIBLINGS:
        listing = _sh(["git", "-C", str(GITHUB / repo), "ls-tree", "-r",
                       "--name-only", "origin/main", "--", "src"]).decode(errors="ignore")
        for line in listing.splitlines():
            if line.endswith(".py"):
                out.setdefault(Path(line).stem, []).append((repo, line))
    return out


def scheduled_reference_blob() -> str:
    """Everything a scheduled surface could name a script from."""
    blob = []
    for pat in (str(UMBRELLA / "scripts" / "*.sh"), str(UMBRELLA / "*.sh"),
                os.path.expanduser("~/Library/LaunchAgents/com.renquant.*.plist")):
        for f in glob.glob(pat):
            try:
                blob.append(Path(f).read_text(errors="ignore"))
            except Exception:  # noqa: BLE001
                continue
    return "\n".join(blob)


def survey() -> dict[str, Any]:
    mods = subrepo_modules()
    refs = scheduled_reference_blob()
    pairs: dict[str, Any] = {}
    for script in sorted(glob.glob(str(UMBRELLA / "scripts" / "*.py"))):
        p = Path(script)
        twins = mods.get(p.stem)
        if not twins:
            continue
        repo, rel = twins[0]
        blob = _sh(["git", "-C", str(GITHUB / repo), "show", f"origin/main:{rel}"])
        if not blob:
            continue
        umb = p.read_bytes()
        pairs[p.name] = {
            "subrepo": repo,
            "subrepo_path": rel,
            "class": IDENTICAL if hashlib.sha256(umb).digest() ==
                     hashlib.sha256(blob).digest() else DIVERGED,
            "umbrella_bytes": len(umb),
            "subrepo_bytes": len(blob),
            "referenced_by_a_scheduled_surface": p.name in refs,
        }
    return {
        "schema_version": 1,
        "_comment": (
            "orchestrator#623 R2 generalised. Umbrella scripts/*.py that name-shadow a "
            "sibling module. A shadow is NOT proof the umbrella copy is dead --- it is "
            "proof a reader could edit the wrong one. Each entry needs a disposition. "
            "Regenerate with ops/umbrella_script_shadow_check.py --emit."
        ),
        "pairs": pairs,
    }


def verify(reg: dict[str, Any]) -> list[str]:
    known = reg.get("pairs") or {}
    if not known:
        return ["registry lists no shadow pairs — nothing is being checked"]
    live = survey()["pairs"]
    problems: list[str] = []
    for name in sorted(set(live) - set(known)):
        e = live[name]
        problems.append(
            f"{name}: NEW shadow of {e['subrepo']}:{e['subrepo_path']} "
            f"({e['class']}) — register it with a disposition")
    for name in sorted(set(known) - set(live)):
        problems.append(f"{name}: registered but no longer shadows anything — re-emit")
    for name in sorted(set(known) & set(live)):
        if known[name].get("class") != live[name]["class"]:
            problems.append(
                f"{name}: class changed {known[name].get('class')} -> {live[name]['class']} "
                f"— the two copies just converged or diverged")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--emit", action="store_true", help="print a fresh registry (never writes)")
    ap.add_argument("--registry", type=Path, default=REGISTRY)
    args = ap.parse_args(argv)

    if args.emit:
        print(json.dumps(survey(), indent=2, sort_keys=True))
        return 0
    if not args.registry.exists():
        print(f"FATAL: registry missing at {args.registry} — run --emit and commit it",
              file=sys.stderr)
        return 2
    try:
        reg = json.loads(args.registry.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"FATAL: registry unreadable: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    problems = verify(reg)
    if problems:
        print("\n".join(problems))
        print(f"\numbrella-script-shadows: {len(problems)} problem(s)")
        return 1
    pairs = reg["pairs"]
    div = sum(1 for v in pairs.values() if v.get("class") == DIVERGED)
    print(f"umbrella-script-shadows OK — {len(pairs)} pairs registered, {div} DIVERGED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
