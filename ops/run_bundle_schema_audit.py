#!/usr/bin/env python3
"""Measure persisted run bundles against the shared validated schema.

GOAL-5 AC6 R4 (orchestrator issue #564) left one question open: *which* bundle
should carry the governed-override provenance field, and what would actually
validate it. The issue notes that ``renquant_common.contracts.schemas.LiveRunBundle``
is real and Pydantic-validated while the orchestrator's daily ``run_bundle.json``
(``daily.PersistDailyRunBundleTask``) is a separate ad hoc dict, and asks for a
decision.

This tool answers it by measuring instead of arguing. It reports, per bundle:

* **missing required fields** — would ``validate_live_run_bundle`` reject it;
* **silently dropped fields** — keys present in the bundle that the schema does
  not declare. This is the load-bearing number. ``LiveRunBundle`` does not set
  ``extra="forbid"``, so Pydantic's default drops unknown keys. A bundle can
  therefore *pass* validation while every provenance field it carries is thrown
  away, which is a validator that certifies a document it did not read.

That failure mode is the reason this audit exists rather than a straight "wire
the schema in" patch: adding an override-provenance field to the daily bundle and
validating it through a schema that discards unknown keys would produce a green
check over a discarded field.

**Read-only.** The tool opens bundles and writes nothing. It is safe to point at
paths under a live tree; it never mutates, never invokes git, and never follows a
path back out to write.

Exit codes: ``0`` clean, ``1`` at least one bundle would be rejected or would
lose fields, ``2`` usage/IO error (so a caller cannot mistake a broken invocation
for a clean audit).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable

try:  # pragma: no cover - exercised by the import-failure test
    from renquant_common.contracts.schemas import LiveRunBundle, validate_live_run_bundle
except Exception as exc:  # noqa: BLE001
    print(f"FATAL: cannot import the shared bundle schema: {exc}", file=sys.stderr)
    raise SystemExit(2) from exc


def schema_fields() -> tuple[frozenset[str], frozenset[str]]:
    """(required, all-declared) field names of the shared live-bundle schema.

    Read off the model rather than hardcoded, so the audit tracks the schema
    instead of a stale copy of it. A hardcoded list is how a guard ends up
    validating a shape nobody ships any more.
    """
    fields = LiveRunBundle.model_fields
    required = frozenset(name for name, f in fields.items() if f.is_required())
    return required, frozenset(fields)


def schema_drops_unknown_keys() -> bool:
    """True when the schema discards keys it does not declare.

    ``extra`` unset or ``"ignore"`` both mean silent drop. Only ``"forbid"``
    turns an undeclared key into an error, and ``"allow"`` retains it.
    """
    return LiveRunBundle.model_config.get("extra", "ignore") in (None, "ignore")


def audit_bundle(path: Path) -> dict[str, Any]:
    """Measure one bundle. Never raises for bundle-content reasons."""
    required, declared = schema_fields()
    try:
        raw = json.loads(path.read_text())
    except Exception as exc:  # noqa: BLE001
        return {"path": str(path), "readable": False, "error": f"{type(exc).__name__}: {exc}"}
    if not isinstance(raw, dict):
        return {
            "path": str(path),
            "readable": False,
            "error": f"top level is {type(raw).__name__}, not an object",
        }

    present = set(raw)
    missing = sorted(required - present)
    dropped = sorted(present - declared)

    # Run the REAL shared validator. Presence of the required keys is only a
    # necessary condition: a bundle can carry every key and still fail on a field
    # type or a cross-field rule, and reporting that as "validates" would make the
    # central measurement of this audit --- and the schema decision resting on it ---
    # unsound. This is the same mistake the audit exists to catch, so it is not
    # approximated here. (Codex BLOCKER on orch#624.)
    validation_error: str | None = None
    try:
        validate_live_run_bundle(raw)
    except Exception as exc:  # noqa: BLE001
        validation_error = f"{type(exc).__name__}: {exc}"

    return {
        "path": str(path),
        "readable": True,
        "run_type": raw.get("run_type"),
        "run_id": raw.get("run_id"),
        "key_count": len(present),
        "missing_required": missing,
        "dropped_by_schema": dropped,
        "validation_error": validation_error,
        # Measured by the validator, not inferred from key presence.
        "would_validate": validation_error is None,
        # A bundle is only "conformant" if it validates AND keeps everything it
        # carries. Validating while losing 13 of 18 fields is not conformance.
        "conformant": validation_error is None and not dropped,
    }


def audit(paths: Iterable[Path]) -> dict[str, Any]:
    results = [audit_bundle(p) for p in paths]
    readable = [r for r in results if r["readable"]]
    return {
        "schema_required": sorted(schema_fields()[0]),
        "schema_declared": sorted(schema_fields()[1]),
        "schema_drops_unknown_keys": schema_drops_unknown_keys(),
        "bundles_examined": len(results),
        "bundles_unreadable": len(results) - len(readable),
        "bundles_would_validate": sum(1 for r in readable if r["would_validate"]),
        "bundles_conformant": sum(1 for r in readable if r["conformant"]),
        "results": results,
    }


def _format(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"shared schema required fields : {report['schema_required']}")
    lines.append(f"shared schema declared fields : {len(report['schema_declared'])}")
    if report["schema_drops_unknown_keys"]:
        lines.append(
            "WARNING: the schema DISCARDS undeclared keys (extra is not 'forbid'), "
            "so a bundle can pass validation with its provenance fields dropped"
        )
    lines.append("")
    for r in report["results"]:
        if not r["readable"]:
            lines.append(f"UNREADABLE {r['path']}: {r['error']}")
            continue
        verdict = "CONFORMANT" if r["conformant"] else (
            "VALIDATES-BUT-LOSES-FIELDS" if r["would_validate"] else "REJECTED"
        )
        lines.append(f"{verdict:26} {r['path']}")
        lines.append(f"{'':26}   keys={r['key_count']} run_type={r['run_type']!r}")
        if r["missing_required"]:
            lines.append(f"{'':26}   missing required: {r['missing_required']}")
        if r.get("validation_error"):
            lines.append(f"{'':26}   validator says: {r['validation_error'][:160]}")
        if r["dropped_by_schema"]:
            lines.append(
                f"{'':26}   would be SILENTLY DROPPED "
                f"({len(r['dropped_by_schema'])}): {r['dropped_by_schema']}"
            )
    lines.append("")
    lines.append(
        f"examined={report['bundles_examined']} "
        f"unreadable={report['bundles_unreadable']} "
        f"would_validate={report['bundles_would_validate']} "
        f"conformant={report['bundles_conformant']}"
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("bundles", nargs="+", type=Path,
                    help="run_bundle.json paths, or directories to search for them")
    ap.add_argument("--json", action="store_true", help="emit the raw report")
    args = ap.parse_args(argv)

    paths: list[Path] = []
    for target in args.bundles:
        if target.is_dir():
            paths.extend(sorted(target.rglob("run_bundle.json")))
        else:
            paths.append(target)
    if not paths:
        print("FATAL: no run_bundle.json found in the given paths", file=sys.stderr)
        return 2

    report = audit(paths)
    print(json.dumps(report, indent=2) if args.json else _format(report))
    if report["bundles_unreadable"]:
        return 2
    return 0 if report["bundles_conformant"] == report["bundles_examined"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
