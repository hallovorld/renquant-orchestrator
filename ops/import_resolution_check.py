#!/usr/bin/env python3
"""Pin WHERE each public symbol this repo imports actually resolves. (GOAL-3, #623)

`#623` registered seven twin-implementation sites and stated the real defect
plainly: *the failure is not that duplicates exist — some duplication is
deliberate. The failure is that nothing in the repo tells you which copy
executes.* In four of the seven rows a defect was filed or a fix written against a
copy that does not run, two of them by me in one session.

This closes that gap for the surface this repo is entitled to constrain: **the
public symbols the orchestrator itself imports.** For each one it resolves the
object at import time and records the file the code actually comes from, then
compares against a committed pin. It answers "which copy runs" the only way that
cannot be fooled — **by resolution, not by grep.**

**Scope, deliberately narrow.** Only symbols this repo imports. It does NOT
enumerate other repos' internal twins: `renquant_pipeline`'s public
`VetoWeakBuysTask`-vs-kernel split is real (#623 R1) but it is not part of this
repo's dependency surface, and encoding a sibling's internals here would be the
boundary violation this programme has already paid for twice. What the orchestrator
IS entitled to pin is which implementation it gets when it imports a public name.

Three of this repo's own incidents were exactly that question:

* `renquant_common.load_scorer` decides which scorer the shadow path serves;
* `renquant_common.model_fingerprint.model_content_sha256` is why a root-level
  `training_contract` key raises and orch#620 had to nest the contract under
  `metadata` — which then made the WF gate's static sanity read the wrong panel;
* `renquant_common.validate_live_run_bundle` accepts a bundle after discarding 13
  of its 18 fields (#624), so *which* validator that name resolves to matters.

Usage:

    import_resolution_check.py                # verify against the committed pins
    import_resolution_check.py --emit         # print fresh pins for review

`--emit` prints; it never writes. The pin file is updated only through a reviewed
PR, the same rule the launchd manifest follows — a surface that can silently
re-baseline itself is not a pin.

Exit codes: ``0`` all pins hold, ``1`` drift or an unresolvable symbol, ``2``
usage/IO error, so a broken invocation cannot read as a clean check.
"""

from __future__ import annotations

import argparse
import importlib
import inspect
import json
import os
import sys
from pathlib import Path
from typing import Any

PINS = Path(__file__).resolve().parent / "import_resolution_pins.json"

#: The symbols to pin, as (module, attribute). Kept as data next to the resolver so
#: adding one is a one-line reviewed change. Each entry is a name THIS repo imports.
PINNED_SYMBOLS: tuple[tuple[str, str], ...] = (
    ("renquant_common", "load_scorer"),
    ("renquant_common", "validate_live_run_bundle"),
    ("renquant_common", "Pipeline"),
    ("renquant_common", "Task"),
    ("renquant_common.model_fingerprint", "model_content_sha256"),
    ("renquant_common.config_consistency", "fingerprint_config"),
    ("renquant_common.market_calendar", "last_completed_session"),
    ("renquant_common.notify", "send"),
    ("renquant_artifacts", "hash_jsonable"),
    ("renquant_execution", "get_broker"),
    ("renquant_execution", "BrokerExecutionPipeline"),
    ("renquant_model_gbdt", "PanelGbdtTrainingPipeline"),
    ("renquant_backtesting", "BacktestPipeline"),
    ("renquant_base_data.loaders.data", "fetch_ohlcv_incremental"),
)


def _package_relative(path: str | None) -> str | None:
    """Strip everything above the top-level package directory.

    Absolute paths differ between the dev checkout and the run checkout
    (`renquant-orchestrator` vs `renquant-orchestrator-run`), so pinning them would
    make the check fail for the wrong reason on the machine that matters. What must
    be stable is the path *inside* the package.
    """
    if not path:
        return None
    parts = Path(path).resolve().parts
    for i in range(len(parts) - 1, -1, -1):
        if parts[i] == "src" and i + 1 < len(parts):
            return "/".join(parts[i + 1:])
    # No src/ layout: fall back to the last three components, which is still more
    # stable than an absolute path and is reported as-is rather than silently.
    return "/".join(parts[-3:])


def resolve(module_name: str, attr: str) -> dict[str, Any]:
    """Where does `module_name.attr` actually come from? Never raises."""
    out: dict[str, Any] = {"module": module_name, "attr": attr}
    try:
        mod = importlib.import_module(module_name)
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"import failed: {type(exc).__name__}: {exc}"
        return out
    if not hasattr(mod, attr):
        out["error"] = f"{module_name} has no attribute {attr!r}"
        return out
    obj = getattr(mod, attr)
    # __module__ is where the object was DEFINED, not where it was re-exported
    # from. That difference is the entire point: a package's __init__ can map a
    # documented name onto a different implementation than the one a reader finds.
    out["defined_in"] = getattr(obj, "__module__", None)
    try:
        out["source_file"] = _package_relative(inspect.getsourcefile(obj))
    except Exception:  # noqa: BLE001
        out["source_file"] = None
    out["kind"] = type(obj).__name__
    return out


def emit() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "_comment": (
            "GOAL-3 #623: which copy of each imported public symbol actually runs. "
            "Generated by ops/import_resolution_check.py --emit and committed via a "
            "reviewed PR, never auto-written. A drift here means a public name now "
            "resolves to a different implementation than the one this repo was "
            "reviewed against."
        ),
        "symbols": {
            f"{m}.{a}": resolve(m, a) for m, a in PINNED_SYMBOLS
        },
    }


def verify(pins: dict[str, Any]) -> list[str]:
    """Compare live resolution against the pins. Returns problem lines."""
    problems: list[str] = []
    pinned = pins.get("symbols") or {}
    if not pinned:
        return ["pin file contains no symbols — cannot verify anything"]

    live = {f"{m}.{a}": resolve(m, a) for m, a in PINNED_SYMBOLS}

    # A symbol dropped from PINNED_SYMBOLS while still in the pin file, or added
    # without re-emitting, both mean the pin no longer describes the code. Neither
    # may pass silently: an unchecked symbol is indistinguishable from a clean one.
    for key in sorted(set(pinned) - set(live)):
        problems.append(
            f"{key}: pinned but no longer in PINNED_SYMBOLS — re-emit the pin file "
            f"so the record matches what is actually checked")
    for key in sorted(set(live) - set(pinned)):
        problems.append(
            f"{key}: checked but absent from the pin file — run --emit and commit, "
            f"otherwise this symbol has no baseline")

    for key in sorted(set(pinned) & set(live)):
        want, got = pinned[key], live[key]
        if got.get("error"):
            problems.append(f"{key}: unresolvable ({got['error']})")
            continue
        if want.get("error"):
            problems.append(
                f"{key}: the pin itself records an error ({want['error']}) — it was "
                f"emitted from a broken environment and is not a valid baseline")
            continue
        for field in ("defined_in", "source_file"):
            if want.get(field) != got.get(field):
                problems.append(
                    f"{key}: {field} drifted — reviewed against {want.get(field)!r}, "
                    f"now resolves to {got.get(field)!r}. Which copy runs has "
                    f"CHANGED; confirm the new one is intended before re-pinning")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--emit", action="store_true",
                    help="print fresh pins for review (never writes)")
    ap.add_argument("--pins", type=Path, default=PINS)
    args = ap.parse_args(argv)

    if args.emit:
        print(json.dumps(emit(), indent=2, sort_keys=True))
        return 0

    if not args.pins.exists():
        print(f"FATAL: pin file missing at {args.pins} — run --emit and commit it",
              file=sys.stderr)
        return 2
    try:
        pins = json.loads(args.pins.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"FATAL: pin file unreadable: {type(exc).__name__}: {exc}",
              file=sys.stderr)
        return 2

    problems = verify(pins)
    if problems:
        print("\n".join(problems))
        print(f"\nimport-resolution: {len(problems)} problem(s)")
        return 1
    print(f"import-resolution OK — {len(PINNED_SYMBOLS)} symbols resolve as reviewed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
