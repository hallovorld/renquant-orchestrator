#!/usr/bin/env python3
"""GOAL-3: when a duplicate name is EXPORTED, which twin does the export give you?

The census (`goal3_twin_surface_audit.py`) answers "could a caller reach two
different definitions of this name". This answers the next question, and it is
the one with consequences: **for the names the package publishes, which
definition does `from <pkg> import <name>` actually resolve to?**

That is not a static question about import sites — it is resolved by the
package's own `__init__`, so this module IMPORTS the package and reads
`__module__` off the exported object. No heuristic, no guess.

MEASURED 2026-08-05 on `renquant_pipeline` `[VERIFIED — this session]`:
**19 of its 20 duplicated `__all__` exports resolve to the NON-kernel twin
while a same-named `kernel/` definition exists.** The one exception,
`InferenceContext`, has no kernel twin at all.

WHAT THAT DOES AND DOES NOT MEAN. It does NOT mean production runs the wrong
code: which definition runs depends on what each caller imports, and most
in-package callers import from `kernel.` directly. It DOES mean the published
surface systematically hands out the non-kernel copy, so a reader who follows
the package's own API lands on the twin the kernel does not use — and the two
are not thin wrappers. `validate_order_attribution` is the sharpest case: the
public copy validates a nested `attribution` dict and returns the order, the
kernel copy validates FLAT keys (`attribution_version`, `score_snapshot`,
`decision_inputs`) and returns None. An order valid under one is invalid under
the other `[VERIFIED — both bodies read]`.

Read-only. Usage:
    python scripts/goal3_public_export_resolution.py <package> [--json]
"""
from __future__ import annotations

import argparse
import importlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from scripts.goal3_twin_surface_audit import audit  # noqa: E402

#: The counterpart root the pipeline guard is configured with. A package with no
#: such root is NOT MEASURED here, rather than reported as clean — the same
#: three-valued discipline the census uses for `--kernel-root-map`.
COUNTERPART = "kernel"

STATE_NO_COUNTERPART = "NO_COUNTERPART_TWIN"
STATE_RESOLVES_TO_COUNTERPART = "RESOLVES_TO_COUNTERPART"
STATE_RESOLVES_ELSEWHERE = "RESOLVES_TO_THE_OTHER_TWIN"
STATE_UNRESOLVABLE = "EXPORT_DID_NOT_RESOLVE"


def resolve_exports(package: str) -> dict:
    result = audit(package)
    module = importlib.import_module(package)
    rows = []
    for name in sorted(result["duplicates_that_are_exported"]):
        cell = result["duplicates"][name]
        sites = [w["file"] for w in cell["sites"]]
        counterpart_sites = [s for s in sites if s.startswith(COUNTERPART + "/")]
        obj = getattr(module, name, None)
        source = getattr(obj, "__module__", None)
        if source is None:
            state = STATE_UNRESOLVABLE
        elif not counterpart_sites:
            state = STATE_NO_COUNTERPART
        else:
            rel = source[len(package) + 1:] if source.startswith(package + ".") else source
            state = (STATE_RESOLVES_TO_COUNTERPART
                     if rel.split(".")[0] == COUNTERPART else STATE_RESOLVES_ELSEWHERE)
        rows.append({
            "name": name, "state": state,
            "resolves_to": source,
            "sites": sites,
            "counterpart_sites": counterpart_sites,
            # Bodies that DIFFER mean the two are not a wrapper and its target.
            "shape": cell["shape"],
        })
    return {
        "package": package,
        "counterpart_root": COUNTERPART,
        "has_counterpart_root": result["has_kernel_counterpart_root"],
        "n_exported_duplicates": len(rows),
        "exports": rows,
        "counts": {s: sum(1 for r in rows if r["state"] == s)
                   for s in (STATE_RESOLVES_TO_COUNTERPART, STATE_RESOLVES_ELSEWHERE,
                             STATE_NO_COUNTERPART, STATE_UNRESOLVABLE)},
    }


def render(result: dict) -> str:
    out = [f"GOAL-3 public-export resolution — {result['package']}", ""]
    if not result["has_counterpart_root"]:
        out.append(f"  no {result['counterpart_root']}/ root — the guard's "
                   f"relation is UNDEFINED here, not clean")
        return "\n".join(out)
    out.append(f"  {'export':32}{'resolves to':34}{'shape':18}state")
    for r in result["exports"]:
        src = (r["resolves_to"] or "?")
        src = src[len(result["package"]) + 1:] if src.startswith(
            result["package"] + ".") else src
        out.append(f"  {r['name']:32}{src:34}{r['shape']:18}{r['state']}")
    c = result["counts"]
    out.append("")
    out.append(f"  of {result['n_exported_duplicates']} exported duplicate name(s): "
               f"{c[STATE_RESOLVES_ELSEWHERE]} resolve to the NON-{result['counterpart_root']} "
               f"twin while a {result['counterpart_root']} twin exists, "
               f"{c[STATE_RESOLVES_TO_COUNTERPART]} to the {result['counterpart_root']} one, "
               f"{c[STATE_NO_COUNTERPART]} have no twin there")
    out.append("  NOTE: this is what the PUBLISHED surface hands out. It is NOT a claim\n"
               "        about which definition production runs — that depends on what each\n"
               "        caller imports, and most in-package callers import kernel. directly.")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("package")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    result = resolve_exports(args.package)
    print(json.dumps(result, indent=2) if args.json else render(result))
    return 1 if result["counts"][STATE_RESOLVES_ELSEWHERE] else 0


if __name__ == "__main__":
    sys.exit(main())
