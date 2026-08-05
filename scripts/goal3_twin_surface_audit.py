#!/usr/bin/env python3
"""GOAL-3: an internal duplicate-definition CENSUS, and the guard's missing root.

TWO SEPARATE THINGS, kept separate on purpose [codex on orch#814].

**(a) The census this script computes.** For one package: which module-level
public names are defined in MORE THAN ONE file, and whether the bodies are
identical (a copy — divergence risk) or differ (the twin shape — which one does
a caller reach?). It also reports how many of those names are in `__all__`.

**(b) What it deliberately does NOT compute.** renquant-pipeline's guard
(`tools/twin_pairs.py`) does not use this relation. It resolves each `__all__`
export to its source object and looks for a same-named definition under one
CONFIGURED counterpart root, `kernel/`. This script's all-files, same-name scan
is broader and is NOT a stand-in for it: a collision found here is not a pair
the guard would have found, and the two counts must not be compared. An earlier
version of this file did compare them and reported a "guard subject coverage"
percentage — that number was measuring the documented API against unrelated
internal names, and it is gone.

The separately measurable fact about the guard, which needs no new machinery
`[VERIFIED — 2026-08-05]`: `renquant-pipeline` is the only repo with a `kernel/`
root at all. In every other repo the guard's relation is UNDEFINED — not
"passes", not "clean", undefined — so "install it there" is not yet a
well-formed proposal.

Read-only. Usage:  python scripts/goal3_twin_surface_audit.py <package> [--json]
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib
import json
import pathlib
import sys


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


# Where to look for callers. [codex on orch#821] Scanning only the package was
# wrong: `tests/test_entry_timing_shadow.py` imports `AdmittedName`, and several
# other names I had classified as "never imported" are imported from tests. A
# reachability figure computed over the package alone is not a reachability
# figure.
SCAN_ROOTS = ("src", "tests", "scripts", "ops")


def _scan_paths(repo: pathlib.Path, package_root: pathlib.Path) -> list[pathlib.Path]:
    """Files to search for callers.

    Falls back to the package itself when none of the SCAN_ROOTS exist beside
    it — a synthetic or vendored package has nothing else to scan, and silently
    scanning NOTHING would report every name as having no import site, which is
    the vacuous pass this whole file exists to avoid.
    """
    out: list[pathlib.Path] = []
    for rel in SCAN_ROOTS:
        d = repo / rel
        if d.is_dir():
            out.extend(sorted(d.rglob("*.py")))
    return out or sorted(package_root.rglob("*.py"))


def _module_name(package: str, site_file: str) -> str:
    """`kernel/panel_pipeline/foo.py` → `pkg.kernel.panel_pipeline.foo`."""
    rel = pathlib.PurePosixPath(site_file).with_suffix("")
    parts = [p for p in rel.parts if p != "__init__"]
    return ".".join([package, *parts])


def _importer_package(path: pathlib.Path, src_root: pathlib.Path) -> str | None:
    """The package a relative import inside ``path`` is relative TO.

    For `pkg/mod.py` that is `pkg`; for `pkg/__init__.py` it is `pkg` itself —
    a package's `__init__` is relative to the package, not to its parent.
    Getting this wrong sends every `from .x import y` in an `__init__` one level
    too high, which is how `renquant_backtesting.metrics.deflated_sharpe` was
    read as the non-existent `renquant_backtesting.deflated_sharpe` and its
    importer scored as foreign.
    """
    try:
        rel = path.relative_to(src_root)
    except ValueError:
        return None                # outside src/ — relative imports unresolvable
    parts = list(rel.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    else:
        parts = parts[:-1]
    return ".".join(parts) or None


def _resolve_module(node: ast.ImportFrom, importer_package: str | None) -> str | None:
    """The absolute module a `from … import` names, or None if unresolvable.

    Relative imports are normalised against the importing file's own package, so
    `from .b import Foo` inside `pkg/a/x.py` resolves to `pkg.a.b` and can be
    compared with a defining site. A relative import from a file with no known
    package (a test, a script) is UNRESOLVABLE and returns None rather than
    being matched on the bare name.
    """
    if not node.level:
        return node.module
    if importer_package is None:
        return None
    parts = importer_package.split(".")
    base = parts[:len(parts) - (node.level - 1)]
    if not base:
        return None
    return ".".join(base + ([node.module] if node.module else []))


def _reexport_aliases(package: str, root: pathlib.Path, names: set[str],
                      site_modules: dict[str, dict[str, str]]
                      ) -> dict[str, dict[str, str]]:
    """Modules that re-export a duplicate name FROM one of its defining sites.

    Checked, not assumed: `from pkg.a import Foo` reaches `pkg.a.b.Foo` only if
    `pkg/a/__init__.py` actually imports it. Permitting every ancestor — or
    every same-named module — would re-open the over-count this exists to close.
    Shim modules are covered too, not just `__init__.py`: a package here
    re-exports through both.

    LIMIT, stated: ONE hop. A re-export chained through two modules is not
    followed, so such a caller lands in `foreign_import_sources` rather than
    being silently credited.
    """
    aliases: dict[str, dict[str, str]] = {n: {} for n in names}
    src_root = root.parent
    for path in sorted(root.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        here = _importer_package(path, src_root)
        rel = path.relative_to(src_root).with_suffix("")
        parts = [p for p in rel.parts if p != "__init__"]
        module_here = ".".join(parts)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            target = _resolve_module(node, here)
            if target is None:
                continue
            for alias in node.names:
                site = site_modules.get(alias.name, {}).get(target)
                if site is not None and module_here != target:
                    aliases[alias.name][module_here] = site
    return aliases


def import_sources(root: pathlib.Path, duplicates: dict, package: str,
                   repo: pathlib.Path | None = None) -> dict[str, dict]:
    """Per duplicate name: which of ITS OWN defining sites a caller imports it
    from, and which same-named imports came from somewhere else entirely.

    WHY (GOAL-3, measured 2026-08-05): the census's 42 duplicate names are a
    work list, not findings. What separates a candidate from a readability risk
    is whether a caller ever refers to the name at all, and — the actual
    question — whether different callers reach DIFFERENT definitions.

    SOURCE IDENTITY, and this is the second thing the first version got wrong
    `[codex on orch#821]`: counting every `from MODULE import NAME` by NAME
    alone means an unrelated `from third_party import J` makes a duplicated `J`
    look reachable, and two such imports make it look MULTI-SOURCE. The
    permitted modules are now derived from each name's own `sites` (plus
    ancestor packages VERIFIED to re-export it), relative imports are
    normalised against the importing file's module, and anything else is
    recorded as `foreign_import_sources` — reported, never credited.

    SCOPE, stated because the first version overclaimed `[codex on orch#821]`:
    this counts `from X import NAME` sites under src/, tests/, scripts/ and
    ops/. It does **not** see `import X` + `X.NAME` attribute access, star
    imports, `importlib`, lazy `__getattr__` re-exports, or callers in OTHER
    repositories. So a name reported with no importers is "not imported BY NAME
    anywhere this scan can see" — a narrower statement than "unreachable".
    """
    repo = repo if repo is not None else pathlib.Path.cwd()
    permitted: dict[str, dict[str, str]] = {
        name: {_module_name(package, w["file"]): w["file"] for w in cell["sites"]}
        for name, cell in duplicates.items()}
    for name, extra in _reexport_aliases(
            package, root, set(duplicates), permitted).items():
        permitted[name].update(extra)

    out: dict[str, dict] = {n: {"sites_reached": set(), "modules": set(),
                                "foreign": set()} for n in duplicates}
    # The directory CONTAINING the package: module names are relative to it,
    # and for a real repo that is `<repo>/src`.
    src_root = root.parent
    for path in _scan_paths(repo, root):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        importer_package = _importer_package(path, src_root)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            module = _resolve_module(node, importer_package)
            for alias in node.names:
                if alias.name not in out:
                    continue
                site = permitted[alias.name].get(module) if module else None
                if site is None:
                    out[alias.name]["foreign"].add(module or
                                                   f"<relative level={node.level}>")
                else:
                    out[alias.name]["sites_reached"].add(site)
                    out[alias.name]["modules"].add(module)
    return {n: {"imported_from": sorted(v["modules"]),
                "sites_reached": sorted(v["sites_reached"]),
                "foreign_import_sources": sorted(v["foreign"])}
            for n, v in out.items()}


def audit(package: str) -> dict:
    module = importlib.import_module(package)
    exported = set(getattr(module, "__all__", []) or [])
    root = pathlib.Path(module.__file__).parent

    sites: dict[str, list[dict]] = {}
    public_defs: set[str] = set()
    for path in sorted(root.rglob("*.py")):
        if path.name == "__init__.py":
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        for node in tree.body:                       # MODULE level only
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                     ast.ClassDef)):
                continue
            if node.name.startswith("_"):
                continue
            public_defs.add(node.name)
            segment = ast.get_source_segment(text, node) or ""
            sites.setdefault(node.name, []).append({
                "file": str(path.relative_to(root)),
                "body_sha256": _digest(segment),
                "n_lines": len(segment.splitlines()),
            })

    duplicates = {}
    for name, where in sites.items():
        if len(where) < 2:
            continue
        digests = {w["body_sha256"] for w in where}
        duplicates[name] = {
            "exported": name in exported,
            # IDENTICAL bodies are a copy (divergence risk); DIFFERENT bodies
            # are the twin shape (which copy runs?).
            "shape": "identical-copy" if len(digests) == 1 else "differing-bodies",
            "sites": sorted(where, key=lambda w: w["file"]),
        }

    # repo root = three levels up from <repo>/src/<package>
    sources = import_sources(root, duplicates, package, repo=root.parent.parent)
    for name, cell in duplicates.items():
        found = sources.get(name, {})
        cell["imported_from"] = found.get("imported_from", [])
        cell["sites_reached"] = found.get("sites_reached", [])
        # Recorded, never credited: a same-named import from a module that is
        # NOT one of this name's definition sites says nothing about which
        # definition a caller reaches.
        cell["foreign_import_sources"] = found.get("foreign_import_sources", [])
        # Counted over SITES REACHED, not import strings. MULTI-SOURCE is the
        # question "could a reader expect one definition and get the other?",
        # and two aliases of the SAME definition do not raise it.
        cell["reachability"] = (
            "no-import-site-found" if not cell["sites_reached"] else
            "one-source" if len(cell["sites_reached"]) == 1 else
            "MULTI-SOURCE")
    return {
        "package": package,
        "all_size": len(exported),
        # UNIQUE NAMES, not sites [codex on orch#814]: `public_defs` is a
        # set, and `__all__` is also a name set, so a name-to-name
        # comparison is the coherent one — but the field must SAY name.
        "unique_public_def_names": len(public_defs),
        "n_duplicate_names": len(duplicates),
        # Whether a duplicate name is also EXPORTED is worth recording, but it
        # is NOT "visible to the guard": the guard's relation is a same-named
        # definition under `kernel/`, which this scan does not compute.
        "duplicates_that_are_exported": sorted(
            n for n, d in duplicates.items() if d["exported"]),
        "duplicates_not_exported": sorted(
            n for n, d in duplicates.items() if not d["exported"]),
        "has_kernel_counterpart_root": (root / "kernel").is_dir(),
        "duplicates": duplicates,
        "reachability_counts": {
            k: sum(1 for c in duplicates.values() if c["reachability"] == k)
            for k in ("no-import-site-found", "one-source", "MULTI-SOURCE")
        },
    }


def _root_note(result: dict) -> str:
    if result["has_kernel_counterpart_root"]:
        return "present"
    return ("ABSENT — the pipeline guard's relation (export ↔ same-named def "
            "under kernel/) is UNDEFINED here, not 'clean'")


def render(result: dict) -> str:
    lines = [
        f"GOAL-3 duplicate-definition census — {result['package']}",
        "",
        f"  __all__ ...................... {result['all_size']}",
        f"  unique public def NAMES ...... {result['unique_public_def_names']}",
        f"  duplicate-definition names ... {result['n_duplicate_names']}",
        f"    no import site found ..... "
        f"{result['reachability_counts']['no-import-site-found']}"
        f"  (no `from X import NAME` under src/tests/scripts/ops — NOT proof of "
        f"unreachability)",
        f"    one source module ........ {result['reachability_counts']['one-source']}",
        f"    MULTI-SOURCE ............. {result['reachability_counts']['MULTI-SOURCE']}"
        f"  (a reader could expect one and get the other)",
        f"    also exported ............ {len(result['duplicates_that_are_exported'])}",
        f"    not exported ............. {len(result['duplicates_not_exported'])}",
        f"  kernel/ counterpart root ..... {_root_note(result)}",
        "",
    ]
    for name in result["duplicates_not_exported"][:12]:
        d = result["duplicates"][name]
        where = ", ".join(f"{s['file']}({s['n_lines']}L)" for s in d["sites"])
        lines.append(f"  [{d['shape']}] {name}: {where}")
    if len(result["duplicates_not_exported"]) > 12:
        lines.append(f"  … and {len(result['duplicates_not_exported']) - 12} more")
    lines.append("")
    lines.append("  A duplicate is a CANDIDATE, not a verdict: confirming one means "
                 "reading both\n  bodies and deciding which the callers reach. This is "
                 "the work list, not the audit.\n  This census is NOT the pipeline "
                 "guard's relation and must not be compared to its counts.")
    return "\n".join(lines)


# The exact packages the record's table lists. A claim about "every repo" has to
# name them and be measurable over them, or it is a claim about the two I ran.
# [codex on orch#814]
SURVEYED_PACKAGES = (
    "renquant_pipeline", "renquant_orchestrator", "renquant_backtesting",
    "renquant_common", "renquant_execution", "renquant_base_data",
    "renquant_strategy_104",
)


def kernel_root_map(packages=SURVEYED_PACKAGES) -> dict:
    """{package: True | False | None} — has a `kernel/` counterpart root.

    `None` means NOT MEASURED (the package could not be imported here), never
    False: an unimportable package is not evidence of an absent root.
    """
    out = {}
    for name in packages:
        try:
            module = importlib.import_module(name)
        except Exception:                        # noqa: BLE001
            out[name] = None
            continue
        out[name] = (pathlib.Path(module.__file__).parent / "kernel").is_dir()
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("package", nargs="?", default="renquant_orchestrator")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--kernel-root-map", action="store_true",
                    help="print the has-a-kernel-root map over the surveyed "
                         "packages and exit")
    args = ap.parse_args(argv)
    if args.kernel_root_map:
        print(json.dumps(kernel_root_map(), indent=2))
        return 0
    result = audit(args.package)
    print(json.dumps(result, indent=2) if args.json else render(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
