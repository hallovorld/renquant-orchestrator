#!/usr/bin/env python
"""M6 stage-2 step-3: read-only fingerprint census over the §3a inventory.

Design: ``doc/design/2026-07-03-m6-stage2-fingerprint-migration.md`` §3
step 3 (the "both computations agree" proof — named there as the
orchestrator census script) and §3c. Runnable at EVERY step of the
migration and wired into the daily run bundle during the window.

What it does
------------
Walks the §3a inventory (prod panel-LTR + both shadow lanes + the active
WF fold corpus + all calibrator families), enumerated at RUN time by the
same glob + pinned-config + manifest-reachability resolution the step-0
pre-stamp tool uses (IMPORTED from ``scripts/prestamp_legacy_fingerprints
.py`` — never re-derived from the design doc's table). For every scorer
artifact it computes BOTH content hashes via renquant-common IMPORTS ONLY
(the triple-impl lesson, design §5 row 3):

* the LEGACY (0.8.1) hash via the deprecated shim path (fail-closed
  against the shim's silent whole-file fallback — reusing the step-0
  tool's guarded helper);
* the schema-v1 hash via ``renquant_common.model_fingerprint``.

and grades the artifact under the ONE semantics its stamp declares
(version dispatch, design §3):

* versionless stamp (the legacy declaration): GREEN iff the stamp equals
  the legacy recompute;
* ``fingerprint_schema_version: 1``: GREEN iff the v1 recompute equals
  the stamp AND, when the step-2 audit field
  ``model_content_fingerprint_legacy_081`` is present, it equals the
  legacy recompute over the payload MINUS the migration-added top-level
  fields (proves the re-stamp didn't paper over a real drift — §3 step 3
  criterion (c); the legacy tables are frozen verbatim, so the
  migration-added fields must be stripped before the legacy engine sees
  them);
* NO stamp at all: RED (a step-0 regression — the production inventory
  is stamped 47/47 as of 2026-07-03);
* any other version value: RED (version gap — re-stamp under v1).

Calibrator bindings (§3 step 3 criterion (d)) are graded with the same
dispatch: a versionless declaration is compared against its paired
scorer's LEGACY identity, a ``scorer_fingerprint_schema_version: 1``
declaration against the scorer's v1 stamp, and a cross-schema pair is
RED by construction (never compared across schemas). Regime calibrators
(no scorer identity, §5 row 8) and snapshot calibrators (`.staging` /
rollback copies) are reported as INFO/WARN, never blocking, exactly like
the step-0 tool.

Each row also records ``v1_ready`` — whether the v1 hash is computable
at all (an ``UnclassifiedKeyError`` here is the §5 row 4 early warning
that step 2's dry-run would abort into a renquant-common table PR).

Step-3 criterion (e) (zero legacy-route acceptances over the observation
window) is NOT computed here: it comes from the pipeline's
``fingerprint-dispatch verify:`` telemetry lines in run bundles.

READ-ONLY ALWAYS: this tool never writes to any artifact; the only file
it can create is the ``--report`` JSON (run-bundle evidence).

Usage
-----
    # Census against the live umbrella tree + JSON report
    python scripts/fingerprint_census.py \
        --root /Users/renhao/git/github/RenQuant \
        --report /tmp/fingerprint_census.json

Exit codes: 0 = green (WARN/INFO rows allowed), 2 = any RED finding.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TOOL_ID = "renquant-orchestrator/scripts/fingerprint_census.py"
DESIGN_REF = (
    "doc/design/2026-07-03-m6-stage2-fingerprint-migration.md §3 step 3 / §3c"
)

STAMP_KEY = "model_content_fingerprint"
SCHEMA_KEY = "fingerprint_schema_version"
LEGACY_AUDIT_KEY = "model_content_fingerprint_legacy_081"
#: Top-level fields the stage-2 runs ADD to an artifact. The legacy 0.8.1
#: engine (frozen verbatim: they are not in MUTABLE_ARTIFACT_KEYS) would
#: hash them, so the audit-field check (c) recomputes the legacy hash over
#: the payload minus exactly this set. ``model_content_fingerprint`` itself
#: is already denylisted by the 0.8.1 tables and needs no stripping.
STAGE2_ADDED_TOP_LEVEL_FIELDS = frozenset({
    SCHEMA_KEY,
    LEGACY_AUDIT_KEY,
    "restamp_provenance",
})

CAL_DECLARED_KEY = "scorer_model_content_fingerprint"
CAL_SCHEMA_KEY = "scorer_fingerprint_schema_version"
CAL_LEGACY_AUDIT_KEY = "scorer_model_content_fingerprint_legacy_081"


# ---------------------------------------------------------------------------
# Reuse the step-0 tool's inventory + guarded legacy hashing (imports only —
# the inventory-resolution logic must never fork between the two tools).
# ---------------------------------------------------------------------------

def _load_prestamp_module():
    path = Path(__file__).resolve().parent / "prestamp_legacy_fingerprints.py"
    spec = importlib.util.spec_from_file_location(
        "prestamp_legacy_fingerprints", path,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


prestamp = _load_prestamp_module()


def _normalize_fp(value: Any) -> str:
    return str(value or "").strip().lower().removeprefix("sha256:")


def _fp_equal(a: Any, b: Any) -> bool:
    na, nb = _normalize_fp(a), _normalize_fp(b)
    return bool(na) and na == nb


def _v1_recompute(mf, payload: dict[str, Any]) -> tuple[str | None, str | None]:
    """(digest, error) under the v1 tables — never raises."""
    if not hasattr(mf, "FINGERPRINT_SCHEMA_VERSION"):
        return None, "renquant-common on this venv predates schema v1 (0.9.x)"
    try:
        return mf.model_content_sha256(payload), None
    except Exception as exc:  # noqa: BLE001 — classified + reported, never fatal
        detail = f"{type(exc).__name__}: {exc}"
        return None, (detail[:297] + "...") if len(detail) > 300 else detail


def _legacy_recompute(mf, path: Path, payload: dict[str, Any]) -> tuple[str | None, str | None]:
    """(digest, error) via the step-0 tool's fail-closed shim helper.

    Path-based: hashes the FILE's content (payload must be the file's own
    parse — the helper cross-checks the two).
    """
    try:
        return prestamp.legacy_fingerprint(mf, path, payload), None
    except prestamp.PrestampRefusal as exc:
        return None, str(exc)


def _legacy_payload_recompute(mf, payload: dict[str, Any]) -> tuple[str | None, str | None]:
    """(digest, error) of an IN-MEMORY payload under the 0.8.1 engine.

    Needed for the §3 step 3 criterion (c) audit check, where the payload
    is the file MINUS the stage-2-added top-level fields (the path-based
    shim cannot express that). Uses renquant-common's private verbatim
    engine — the exact engine the public shim routes through; still an
    import, never a re-implementation.
    """
    engine = getattr(mf, "_legacy_model_content_sha256", None)
    if not callable(engine):
        return None, (
            "renquant-common on this venv lacks the legacy payload engine "
            "(_legacy_model_content_sha256; need the 0.9.1+ shims)"
        )
    try:
        return engine(payload), None
    except ValueError as exc:
        return None, f"{type(exc).__name__}: {exc}"


# ---------------------------------------------------------------------------
# Per-artifact grading (version dispatch)
# ---------------------------------------------------------------------------

def grade_artifact(mf, root: Path, path: Path, family: str) -> dict[str, Any]:
    row: dict[str, Any] = {
        "path": prestamp._rel(path, root),
        "family": family,
        "file_sha256": mf.artifact_sha256(path),
    }
    try:
        payload = json.loads(path.read_text())
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        row.update(verdict="RED", reason=f"invalid JSON: {exc}")
        return row
    if not isinstance(payload, dict):
        row.update(
            verdict="RED",
            reason=f"payload is {type(payload).__name__}, not an object",
        )
        return row

    stamped = payload.get(STAMP_KEY)
    version = payload.get(SCHEMA_KEY)
    legacy, legacy_err = _legacy_recompute(mf, path, payload)
    v1, v1_err = _v1_recompute(mf, payload)
    row.update(
        stamped=stamped,
        stamped_schema_version=version,
        legacy_recompute=legacy,
        legacy_recompute_error=legacy_err,
        v1_recompute=v1,
        v1_recompute_error=v1_err,
        v1_ready=v1 is not None,
    )

    if stamped is None:
        row.update(
            verdict="RED",
            reason="UNSTAMPED — no model_content_fingerprint; a step-0 "
                   "regression (new/refit artifact landed without a stamp; "
                   "design §5 row 1). Re-run the step-0 pre-stamp under an "
                   "operator grant.",
        )
        return row

    if version is None:
        # Versionless stamp IS the legacy declaration.
        if legacy is None:
            row.update(
                verdict="RED",
                reason=f"legacy recompute unavailable: {legacy_err}",
            )
        elif _fp_equal(stamped, legacy):
            row.update(verdict="GREEN", reason="legacy stamp == legacy recompute")
        else:
            row.update(
                verdict="RED",
                reason="legacy stamp != legacy recompute — REAL content "
                       "drift under the stamp's own semantics, not "
                       "migration noise",
            )
        return row

    if isinstance(version, bool) or not isinstance(version, int) or version != getattr(
        mf, "FINGERPRINT_SCHEMA_VERSION", 1
    ):
        row.update(
            verdict="RED",
            reason=f"fingerprint schema version gap: stamped {version!r}; "
                   "re-stamp under the supported schema version",
        )
        return row

    # v1-stamped: criterion (b) stamp == v1 recompute.
    if v1 is None:
        row.update(
            verdict="RED",
            reason=f"v1-stamped but v1 recompute unavailable: {v1_err}",
        )
        return row
    if not _fp_equal(stamped, v1):
        row.update(
            verdict="RED",
            reason="v1 stamp != v1 recompute — REAL content drift under "
                   "the stamp's own semantics",
        )
        return row
    # Criterion (c): the legacy-081 audit field equals the legacy recompute
    # over the payload minus the migration-added top-level fields.
    audit = payload.get(LEGACY_AUDIT_KEY)
    if audit is not None:
        stripped = {
            k: v for k, v in payload.items()
            if k not in STAGE2_ADDED_TOP_LEVEL_FIELDS
        }
        audit_legacy, audit_err = _legacy_payload_recompute(mf, stripped)
        row["legacy_audit_recompute"] = audit_legacy
        if audit_legacy is None:
            row.update(
                verdict="RED",
                reason=f"legacy-081 audit recompute unavailable: {audit_err}",
            )
            return row
        if not _fp_equal(audit, audit_legacy):
            row.update(
                verdict="RED",
                reason="model_content_fingerprint_legacy_081 != legacy "
                       "recompute — the re-stamp papered over a drift "
                       "(§3 step 3 criterion (c))",
            )
            return row
    row.update(verdict="GREEN", reason="v1 stamp == v1 recompute"
               + ("" if audit is None else " and legacy-081 audit holds"))
    return row


# ---------------------------------------------------------------------------
# Binding grading (version dispatch on the calibrator's declaration)
# ---------------------------------------------------------------------------

def grade_binding(
    mf,
    root: Path,
    binding: dict[str, Any],
    artifact_rows: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    cal_path: Path = binding["calibrator"]
    row: dict[str, Any] = {
        "calibrator": prestamp._rel(cal_path, root),
        "severity": binding["severity"],
        "source": binding["source"],
    }
    if not cal_path.exists():
        row.update(verdict="MISSING", detail="calibrator file not found")
        return row
    try:
        payload = json.loads(cal_path.read_text())
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        row.update(verdict="ERROR", detail=f"invalid JSON: {exc}")
        return row
    meta = payload.get("metadata") if isinstance(payload, dict) else None
    meta = meta if isinstance(meta, dict) else {}
    declared = meta.get(CAL_DECLARED_KEY)
    declared_version = meta.get(CAL_SCHEMA_KEY)
    row["declared"] = declared
    row["declared_schema_version"] = declared_version
    if not declared:
        row.update(
            verdict="NO_DECLARATION",
            detail="calibrator declares no scorer_model_content_fingerprint",
        )
        return row

    scorer: Path | None = binding.get("scorer")
    if scorer is None:
        raw_scorer = meta.get("scorer_artifact")
        if raw_scorer:
            sp = Path(str(raw_scorer))
            if not sp.is_absolute():
                sp = prestamp._resolve_strategy_path(root, str(raw_scorer))
            scorer = sp
    if scorer is not None and scorer.suffix != ".json":
        row.update(
            verdict="FAMILY_SPLIT_NA",
            detail=f"declared scorer {scorer.name} is not a JSON payload "
                   "artifact (whole-file-hash family, design §2a site 10)",
        )
        return row
    if scorer is None or not scorer.exists():
        row.update(
            verdict="UNRESOLVED_SCORER",
            detail=f"paired scorer not resolvable: {scorer}",
        )
        return row
    row["scorer"] = prestamp._rel(scorer, root)

    scorer_row = artifact_rows.get(row["scorer"])
    if scorer_row is None:
        scorer_row = grade_artifact(mf, root, scorer, family="binding-only")
    scorer_version = scorer_row.get("stamped_schema_version")
    scorer_schema = "v1" if scorer_version is not None else "legacy"
    declared_schema = "v1" if declared_version is not None else "legacy"
    row["scorer_schema"] = scorer_schema
    row["declared_schema"] = declared_schema

    if declared_schema != scorer_schema:
        row.update(
            verdict="MISMATCH",
            detail=f"cross-schema pair (scorer={scorer_schema}-stamped, "
                   f"calibrator={declared_schema}-declared) — never compared "
                   "across schemas (design §3); re-stamp the lagging side",
        )
        return row

    if declared_schema == "v1":
        if not (isinstance(declared_version, int)
                and not isinstance(declared_version, bool)
                and declared_version == getattr(mf, "FINGERPRINT_SCHEMA_VERSION", 1)):
            row.update(
                verdict="MISMATCH",
                detail=f"declared scorer_fingerprint_schema_version="
                       f"{declared_version!r} is not the supported version",
            )
            return row
        expected = scorer_row.get("stamped")
    else:
        # Legacy route: the scorer's declared-or-recomputed legacy identity.
        expected = (
            scorer_row.get("stamped")
            if scorer_row.get("stamped_schema_version") is None
            and scorer_row.get("stamped") is not None
            else None
        ) or scorer_row.get("legacy_recompute")
    row["expected"] = expected
    if expected is None:
        row.update(
            verdict="ERROR",
            detail="paired scorer identity unavailable "
                   f"(scorer verdict: {scorer_row.get('reason')})",
        )
        return row
    if _fp_equal(declared, expected):
        row.update(verdict="MATCH")
    else:
        row.update(
            verdict="MISMATCH",
            detail="declared scorer identity != paired scorer identity "
                   "under the declared schema — a REAL binding break, "
                   "not migration noise",
        )
    return row


# ---------------------------------------------------------------------------
# Manifest stamped-field agreement (§5 row 5) — only when fields exist.
# ---------------------------------------------------------------------------

def grade_manifest_rows(mf, root: Path, manifest_rel: str) -> list[dict[str, Any]]:
    strategy_dir = root / prestamp.STRATEGY_REL
    mp = root / manifest_rel if (root / manifest_rel).exists() else strategy_dir / manifest_rel
    out: list[dict[str, Any]] = []
    for idx, row in enumerate(prestamp._manifest_rows(mp)):
        art_uri = row.get("artifact_uri")
        if not art_uri:
            continue
        checks: dict[str, Any] = {}
        art_path = prestamp._resolve_strategy_path(root, str(art_uri))
        for key in ("scorer_artifact_sha256", "artifact_sha256"):
            if row.get(key) and art_path.exists():
                checks[key] = _fp_equal(row[key], mf.artifact_sha256(art_path))
        for key in ("scorer_model_content_fingerprint", "model_content_fingerprint"):
            if row.get(key) and art_path.exists():
                try:
                    payload = json.loads(art_path.read_text())
                    stamped = payload.get(STAMP_KEY)
                except Exception:  # noqa: BLE001
                    stamped = None
                checks[key] = _fp_equal(row[key], stamped)
        if checks:
            out.append({
                "manifest": manifest_rel,
                "row": idx,
                "artifact_uri": str(art_uri),
                "checks": checks,
                "verdict": "MATCH" if all(checks.values()) else "MISMATCH",
            })
    return out


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def run_census(root: Path, extra_manifests: list[str] | None = None) -> dict[str, Any]:
    mf = prestamp.load_fingerprint_module()
    inventory = prestamp.resolve_inventory(root, extra_manifests=extra_manifests)

    artifact_rows: list[dict[str, Any]] = []
    by_rel: dict[str, dict[str, Any]] = {}
    for resolved in sorted(inventory["stamp_targets"]):
        entry = inventory["stamp_targets"][resolved]
        row = grade_artifact(mf, root, entry["path"], entry["family"])
        row["sources"] = entry["sources"]
        artifact_rows.append(row)
        by_rel[row["path"]] = row

    binding_rows = [
        grade_binding(mf, root, b, by_rel) for b in inventory["bindings"]
    ]

    manifest_rows: list[dict[str, Any]] = []
    for m in inventory["manifests"]["in_scope"]:
        manifest_rows.append({
            "manifest": m,
            "rows": grade_manifest_rows(mf, root, m),
        })

    red_artifacts = [r for r in artifact_rows if r["verdict"] == "RED"]
    red_bindings = [
        b for b in binding_rows
        if b["severity"] == "RED"
        and b.get("verdict") not in ("MATCH", "FAMILY_SPLIT_NA")
    ]
    red_manifest = [
        r for m in manifest_rows for r in m["rows"]
        if r["verdict"] == "MISMATCH"
    ]
    warn_bindings = [
        b for b in binding_rows
        if b["severity"] != "RED"
        and b.get("verdict") not in ("MATCH", "FAMILY_SPLIT_NA")
    ]

    schema_counts: dict[str, int] = {"legacy": 0, "v1": 0, "unstamped": 0}
    for r in artifact_rows:
        if r.get("stamped") is None:
            schema_counts["unstamped"] += 1
        elif r.get("stamped_schema_version") is None:
            schema_counts["legacy"] += 1
        else:
            schema_counts["v1"] += 1

    return {
        "tool": TOOL_ID,
        "design": DESIGN_REF,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "root": str(root),
        "read_only": True,
        "common_module": {
            "module_file": getattr(mf, "__file__", None),
            "schema_v1_module": hasattr(mf, "FINGERPRINT_SCHEMA_VERSION"),
        },
        "artifacts": artifact_rows,
        "bindings": binding_rows,
        "manifest_field_checks": manifest_rows,
        "info": inventory["info_rows"],
        "manifests": inventory["manifests"],
        "summary": {
            "n_artifacts": len(artifact_rows),
            "n_green": sum(1 for r in artifact_rows if r["verdict"] == "GREEN"),
            "n_red_artifacts": len(red_artifacts),
            "n_bindings": len(binding_rows),
            "n_red_bindings": len(red_bindings),
            "n_warn_bindings": len(warn_bindings),
            "n_red_manifest_rows": len(red_manifest),
            "stamped_schema_counts": schema_counts,
            "n_v1_ready": sum(1 for r in artifact_rows if r.get("v1_ready")),
            "all_green": not (red_artifacts or red_bindings or red_manifest),
        },
    }


def print_report(report: dict[str, Any]) -> None:
    print(f"fingerprint_census [read-only] root={report['root']}")
    print(f"  design: {report['design']}")
    for r in report["artifacts"]:
        schema = (
            "v1" if r.get("stamped_schema_version") is not None
            else ("legacy" if r.get("stamped") else "unstamped")
        )
        print(f"  [{r['verdict']:>5}] {r['family']:<8} {schema:<9} {r['path']}")
        print(f"{'':10}stamped={r.get('stamped')}")
        print(f"{'':10}legacy_recompute={r.get('legacy_recompute')} "
              f"v1_recompute={r.get('v1_recompute')} "
              f"v1_ready={r.get('v1_ready')}")
        if r["verdict"] != "GREEN":
            print(f"{'':10}reason: {r.get('reason')}")
    for b in report["bindings"]:
        mark = "OK " if b.get("verdict") == "MATCH" else b.get("verdict", "?")
        print(f"  [binding {b['severity']:<4} {mark:<15}] {b['calibrator']}"
              + (f" <- {b['scorer']}" if b.get("scorer") else ""))
        if b.get("detail"):
            print(f"{'':10}{b['detail']}")
    for m in report["manifest_field_checks"]:
        n = len(m["rows"])
        bad = sum(1 for r in m["rows"] if r["verdict"] == "MISMATCH")
        note = (f"{n} stamped-field rows checked, {bad} mismatched"
                if n else "no stamped fingerprint fields in rows (nothing to check)")
        print(f"  [manifest] {m['manifest']}: {note}")
    for i in report["info"]:
        print(f"  [info {i['status']:<16}] {i['path']} — {i['note']}")
    if report["manifests"]["out_of_scope"]:
        print("  manifests NOT in default scope (pass --manifest to include):")
        for m in report["manifests"]["out_of_scope"]:
            print(f"    - {m}")
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    print("RESULT: " + ("GREEN" if report["summary"]["all_green"] else "RED"))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--root", required=True,
        help="Umbrella live-tree root (e.g. /Users/renhao/git/github/RenQuant).",
    )
    p.add_argument(
        "--manifest", action="append", default=[],
        help="Additional WF manifest to include beyond the default "
             "gbdt_prod_recipe_v2 scope. Repeatable.",
    )
    p.add_argument(
        "--report", default=None,
        help="Write the full JSON report (run-bundle evidence) to this path.",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = run_census(Path(args.root).resolve(),
                            extra_manifests=args.manifest)
    except prestamp.PrestampRefusal as exc:
        print(f"REFUSE: {exc}", file=sys.stderr)
        return 2
    print_report(report)
    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True))
        print(f"  report written: {report_path}")
    return 0 if report["summary"]["all_green"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
