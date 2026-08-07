#!/usr/bin/env python3
"""Compare the broker allow-lists PROGRAMMATICALLY, not by reading the files.

WHY THIS EXISTS — and why it compares imported objects
------------------------------------------------------
`runs_db_path()` fail-closes on an unknown `broker_name`. Two copies of that
allow-list are in play: the pinned pipeline's, which the default `multirepo`
runner imports, and the umbrella's, which `RQ_DAILY_RUNNER=umbrella` imports —
a fallback `scripts/daily_104.sh:135-139` documents as the escape hatch for a
missing pinned subrepo. Measured 2026-08-07, the umbrella copy is a strict
SUBSET missing five tags, three of them live shadow-fleet lanes:

    alpaca_shadow_blend_mom_fast, alpaca_shadow_blend_rb_fast,
    alpaca_shadow_blend_rb_mom          (+ alpaca_shadow_a, alpaca_shadow_b)

So in the exact circumstance the fallback exists for — a degraded moment — three
of five shadow lanes die on a broker-name check, and it presents as
`ValueError: Unknown broker_name`, i.e. a lane crash rather than a stale list.

THE MEASUREMENT METHOD IS THE POINT. I first "measured" this by grepping each
file for `alpaca[a-z_-]*` and reported that the two PINNED copies also diverged
(15 vs 3). They do not: imported, both are 15 and identical, and
`tests/test_shadow_arm_broker_tags.py` already asserts that equality. Counting
string literals in a file is not reading the constant a module exports — the
kernel copy simply does not spell every tag as a literal. That mistake was the
seventh of its kind in one session, so this probe **imports both modules and
compares the objects**; it never reads source text. A text-based version of this
probe would reproduce the very error it exists to catch.

Exit codes:
    0  the umbrella list is a superset-or-equal of the pinned list
    1  the umbrella list is missing tags the pinned list has  (FINDING)
    2  refusal — a copy could not be imported (never silently "clean")
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

RQ = Path(os.environ.get("RQ_ROOT", "/Users/renhao/git/github/RenQuant"))
PINNED_SRC = RQ / ".subrepo_runtime" / "repos" / "renquant-pipeline" / "src"
UMBRELLA_MOD = RQ / "backtesting" / "renquant_104" / "kernel" / "state_paths.py"

EXIT_OK, EXIT_FINDING, EXIT_REFUSE = 0, 1, 2


class Unreadable(RuntimeError):
    """A copy could not be imported. Refusal, never a pass."""


def _load_umbrella(path: Path = UMBRELLA_MOD):
    if not path.is_file():
        raise Unreadable(f"umbrella copy absent: {path}")
    spec = importlib.util.spec_from_file_location("_umbrella_state_paths", path)
    if spec is None or spec.loader is None:
        raise Unreadable(f"cannot build a spec for {path}")
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as exc:  # noqa: BLE001 - any import failure is a refusal
        raise Unreadable(f"{path}: {exc}") from exc
    return mod


def _load_pinned(src: Path = PINNED_SRC):
    if not src.is_dir():
        raise Unreadable(f"pinned pipeline src absent: {src}")
    path = src / "renquant_pipeline" / "state_paths.py"
    if not path.is_file():
        raise Unreadable(f"pinned copy absent: {path}")
    spec = importlib.util.spec_from_file_location("_pinned_state_paths", path)
    if spec is None or spec.loader is None:
        raise Unreadable(f"cannot build a spec for {path}")
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as exc:  # noqa: BLE001 - any import failure is a refusal
        raise Unreadable(f"{path}: {exc}") from exc
    return mod


def _tags(mod, where: str) -> set[str]:
    v = getattr(mod, "ALLOWED_BROKERS", None)
    if v is None:
        raise Unreadable(f"{where}: no ALLOWED_BROKERS attribute")
    try:
        return {str(x) for x in v}
    except TypeError as exc:
        raise Unreadable(f"{where}: ALLOWED_BROKERS is not iterable ({exc})") from exc


def scan() -> dict:
    pinned = _tags(_load_pinned(), "pinned")
    umbrella = _tags(_load_umbrella(), "umbrella")
    missing = sorted(pinned - umbrella)
    extra = sorted(umbrella - pinned)
    return {
        "n_pinned": len(pinned),
        "n_umbrella": len(umbrella),
        "missing_from_umbrella": missing,
        "only_in_umbrella": extra,
        "identical": not missing and not extra,
    }


def render(r: dict) -> str:
    L = [f"broker allow-list parity — pinned {r['n_pinned']} vs umbrella {r['n_umbrella']}"]
    if r["identical"]:
        L.append("  identical")
        return "\n".join(L)
    if r["missing_from_umbrella"]:
        L.append(f"  MISSING from the umbrella copy ({len(r['missing_from_umbrella'])}) — "
                 "these lanes fail closed under RQ_DAILY_RUNNER=umbrella:")
        for t in r["missing_from_umbrella"]:
            L.append(f"    {t}")
    if r["only_in_umbrella"]:
        # Not a finding by itself: a tag the umbrella accepts and pinned does not
        # cannot break the default path. Reported so it is never invisible.
        L.append(f"  only in the umbrella copy ({len(r['only_in_umbrella'])}) — informational:")
        for t in r["only_in_umbrella"]:
            L.append(f"    {t}")
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        r = scan()
    except Unreadable as exc:
        print(f"REFUSING: {exc}", file=sys.stderr)
        return EXIT_REFUSE
    print(json.dumps(r, indent=2) if args.json else render(r))
    return EXIT_FINDING if r["missing_from_umbrella"] else EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
