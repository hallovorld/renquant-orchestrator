#!/usr/bin/env python3
"""Which keys do the live-bundle PRODUCERS build that the shared schema never reads?

GOAL-5 AC6 R4 (orchestrator issue #564). `ops/run_bundle_schema_audit.py` measures
bundles **on disk** against `LiveRunBundle`. This measures the other half — the
**producers** — and it is the half that decides R4.

WHY THIS EXISTS. `validate_live_run_bundle` is called on both live-bundle paths, so
those paths read as *validated*. Measured 2026-07-31 by executing the validator:

    validate_live_run_bundle({... "smalln_ledger": {...}})  ->  LiveRunBundle
    "smalln_ledger" in result.model_dump()                  ->  False

`LiveRunBundle` does not set `extra="forbid"`, so Pydantic **drops** undeclared keys.
The bridge producer builds `smalln_ledger` and `metadata`; neither is declared.

**No data is lost** — and that narrowing matters. `build_bridge_live_bundle` calls the
validator for its side effect and returns *its own* dict, so both keys reach disk intact.
The defect is not loss, it is **coverage**: those keys travel a validated path while
nothing validates them. If they became malformed, vanished, or changed type, every check
in this repo would still report green.

WHY THAT IS EXACTLY R4's QUESTION. R4 asks where governed-override provenance should
live so it is *mechanically* enforced. Adding it to a bundle whose validator declares
seven keys and silently ignores the rest buys a green check over a field nobody read.
This tool turns "which keys are unread?" from an observation into a number that a
scheduled job can re-derive.

HOW IT READS THE PRODUCERS. By **AST**, not regex and not import. AST because a regex
over source text finds strings in comments and docstrings and misses computed keys —
this reports the latter as UNKNOWABLE rather than pretending; and not by import because
building a real bundle needs a live run context, which an audit must never require.

WHY IT ALSO CHECKS THE VALIDATION CALL `[codex on orch#690]`: a key census over a
function proves only that the function contains those assignments. If a refactor removed
or bypassed `validate_live_run_bundle`, this tool would still confidently report a
"validated producer path" that no longer exists. So each producer must **call the
validator on a dict it built itself** — calling it on something else is not validating
the bundle.

Read-only. Parses files, writes nothing, never invokes git.

Exit codes: ``0`` every producer validates its own bundle and every key is declared,
``1`` otherwise (unread key, unreadable producer, or a producer that no longer
validates), ``2`` usage error — so a broken invocation cannot be mistaken for a clean
audit.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent

#: (file, function) pairs that build a bundle handed to `validate_live_run_bundle`.
#: Declared rather than discovered so that a producer DISAPPEARING is a failure, not a
#: silently shrinking audit — "0 unread keys" must not be reachable by finding nothing.
PRODUCERS = (
    ("src/renquant_orchestrator/native_live_bundle.py", "build_native_live_bundle"),
    ("src/renquant_orchestrator/bridge_live_bundle.py", "build_bridge_live_bundle"),
)


def schema_declared() -> frozenset[str]:
    """The schema's declared field names, read off the model, never hardcoded."""
    from renquant_common.contracts.schemas import LiveRunBundle
    return frozenset(LiveRunBundle.model_fields)


def schema_drops_unknown_keys() -> bool:
    from renquant_common.contracts.schemas import LiveRunBundle
    return LiveRunBundle.model_config.get("extra", "ignore") in (None, "ignore")


def _assigned_keys(fn: ast.FunctionDef) -> tuple[set[str], list[str]]:
    """Literal string keys the function puts into a dict, plus what it could not read.

    Covers both shapes the producers use: a dict literal (`{"a": ...}`) and later
    subscript assignment (`bundle["metadata"] = ...`). A non-literal key is recorded in
    `unknowable` instead of being dropped — an audit that silently ignores what it
    cannot parse reports clean for the wrong reason.
    """
    keys: set[str] = set()
    unknowable: list[str] = []
    for node in ast.walk(fn):
        if isinstance(node, ast.Dict):
            for k in node.keys:
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    keys.add(k.value)
                elif k is not None:  # `**spread` has a None key; a computed key does not
                    unknowable.append(f"computed dict key at line {getattr(k, 'lineno', '?')}")
                else:
                    unknowable.append(f"dict unpacking (**) at line {node.lineno}")
        elif isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Store):
            sl = node.slice
            if isinstance(sl, ast.Constant) and isinstance(sl.value, str):
                keys.add(sl.value)
            else:
                unknowable.append(f"computed subscript key at line {node.lineno}")
    return keys, unknowable


VALIDATOR = "validate_live_run_bundle"


def _bundle_names(fn: ast.AST) -> set[str]:
    """Names assigned a dict literal inside `fn` — the candidate bundle variables."""
    out: set[str] = set()
    for node in ast.walk(fn):
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and isinstance(
                getattr(node, "value", None), ast.Dict):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                if isinstance(t, ast.Name):
                    out.add(t.id)
    return out


def _validates(fn: ast.AST) -> tuple[bool, list[str]]:
    """Does this function pass its CONSTRUCTED bundle to the shared validator?

    Reviewed `[codex on orch#690]`: *"it does not verify that each function actually
    passes its constructed bundle to validate_live_run_bundle, so a refactor that removes
    or bypasses that call can still yield a confident report about a validated producer
    path."*

    Exactly the defect this audit was written to expose, one level up: it was measuring
    key names and calling the result a statement about a *validated* boundary. A key
    census over a function that no longer validates anything describes a boundary that
    does not exist.

    So both halves are required: the call must be present, AND its first positional
    argument must be a name that was assigned a dict literal in the same function.
    Calling the validator on something else is not validating the bundle you built.
    """
    names = _bundle_names(fn)
    called = validated_arg = False
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        target = (f.id if isinstance(f, ast.Name)
                  else f.attr if isinstance(f, ast.Attribute) else None)
        if target != VALIDATOR:
            continue
        called = True
        if node.args and isinstance(node.args[0], ast.Name) and \
                node.args[0].id in names:
            validated_arg = True
    why = []
    if not called:
        why.append(f"{VALIDATOR} is never called in this function — the 'validated "
                   f"producer path' this audit reports on does not exist here")
    elif not validated_arg:
        why.append(f"{VALIDATOR} is called, but not on a dict built in this function "
                   f"(built: {sorted(names) or 'none'}) — validating something else is "
                   f"not validating the bundle")
    return (called and validated_arg), why


def audit_producer(rel: str, func: str) -> dict[str, Any]:
    path = REPO / rel
    if not path.exists():
        return {"producer": rel, "function": func, "readable": False,
                "why": "file not found — a declared producer vanished"}
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError) as exc:
        return {"producer": rel, "function": func, "readable": False,
                "why": f"{type(exc).__name__}: {exc}"}
    fn = next((n for n in ast.walk(tree)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
               and n.name == func), None)
    if fn is None:
        return {"producer": rel, "function": func, "readable": False,
                "why": f"function {func!r} not found — the audit's target moved"}
    keys, unknowable = _assigned_keys(fn)
    declared = schema_declared()
    validates, why = _validates(fn)
    return {"producer": rel, "function": func, "readable": True,
            "keys_built": sorted(keys),
            "unread_by_schema": sorted(keys - declared),
            "validates_its_bundle": validates,
            "validation_findings": why,
            "unknowable": unknowable}


def audit() -> dict[str, Any]:
    rows = [audit_producer(rel, fn) for rel, fn in PRODUCERS]
    unread = sorted({k for r in rows for k in r.get("unread_by_schema", [])})
    unvalidated = [r["producer"] for r in rows
                   if r["readable"] and not r["validates_its_bundle"]]
    return {
        "producers_not_validating_their_bundle": unvalidated,
        "n_producers_declared": len(PRODUCERS),
        "n_producers_read": sum(1 for r in rows if r["readable"]),
        "schema_drops_unknown_keys": schema_drops_unknown_keys(),
        "schema_declared_fields": sorted(schema_declared()),
        "unread_keys_across_producers": unread,
        "producers": rows,
        "scope_note": (
            "Unread does not mean lost: a producer that returns its own dict still "
            "writes these keys to disk. It means nothing validates them — they travel "
            "a validated path uncovered, and a malformed or missing value would not "
            "be caught by any check in this repo."),
    }


def _format(rep: dict[str, Any]) -> str:
    out = [f"shared schema declares : {rep['schema_declared_fields']}",
           f"schema drops undeclared keys : {rep['schema_drops_unknown_keys']}"]
    for r in rep["producers"]:
        if not r["readable"]:
            out.append(f"UNREADABLE  {r['producer']}::{r['function']} — {r['why']}")
            continue
        if not r["validates_its_bundle"]:
            mark = "NOT VALIDATED"
        elif r["unread_by_schema"]:
            mark = "UNREAD KEYS"
        else:
            mark = "all declared"
        out.append(f"{mark:13s} {r['producer']}::{r['function']}")
        for w in r["validation_findings"]:
            out.append(f"               {w}")
        out.append(f"               builds {len(r['keys_built'])}: {r['keys_built']}")
        if r["unread_by_schema"]:
            out.append(f"               NOT read by the schema: {r['unread_by_schema']}")
        for u in r["unknowable"]:
            out.append(f"               UNKNOWABLE: {u}")
    out.append(f"\nproducers declared={rep['n_producers_declared']} "
               f"read={rep['n_producers_read']} "
               f"unread_keys={len(rep['unread_keys_across_producers'])} "
               f"{rep['unread_keys_across_producers']}")
    out.append(rep["scope_note"])
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="emit the raw report")
    args = ap.parse_args(argv)
    try:
        rep = audit()
    except Exception as exc:  # noqa: BLE001
        print(f"bundle-producer audit: could not run: {type(exc).__name__}: {exc}",
              file=sys.stderr)
        return 2
    print(json.dumps(rep, indent=2, sort_keys=True) if args.json else _format(rep))
    # A producer that could not be read is a failure, not a pass: otherwise deleting a
    # producer is the cheapest way to make this audit green.
    unread = rep["unread_keys_across_producers"]
    unreadable = rep["n_producers_declared"] - rep["n_producers_read"]
    # A producer that no longer validates its own bundle is the WORST outcome here, not
    # the mildest: the whole report is a statement about a validated boundary.
    unvalidated = rep["producers_not_validating_their_bundle"]
    return 1 if (unread or unreadable or unvalidated) else 0


if __name__ == "__main__":
    raise SystemExit(main())
