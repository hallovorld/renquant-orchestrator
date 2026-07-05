"""M6 stage-2 step-2: v1 fingerprint re-stamp tool.

Walks a model artifacts directory, finds model metadata JSON files, and
re-stamps them with the unified v1 fingerprint from
renquant_common.model_fingerprint.  This is the orchestrator-owned
coordination tool for the M6 migration (design doc
doc/design/2026-07-03-m6-stage2-fingerprint-migration.md section 3 step 2).

Hash logic is IMPORTS ONLY from renquant_common.model_fingerprint -- no
re-implementation (the triple-impl lesson, three incidents 2026-05-27 /
06-22 / 07-01).  This tool never touches the live umbrella tree at
/Users/renhao/git/github/RenQuant; it operates on a specified artifacts
directory.  Defaults to dry_run=True -- never writes production artifacts
without explicit operator opt-in.

Usage::

    python -m renquant_orchestrator.m6_restamp \\
        --artifacts-dir /path/to/artifacts \\
        --dry-run          # default: preview only
        --verify           # re-read and check round-trip after write
        --output-report /path/to/report.json
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
import warnings
from pathlib import Path
from typing import Any

# Hash logic is IMPORTS ONLY from renquant_common.model_fingerprint.
# Never re-implement -- the silent-default divergence between the pipeline's
# subtractive denylist and the model repo's additive allowlist is the root
# cause of three fail-closed no-trade incidents.
from renquant_common.model_fingerprint import (
    FINGERPRINT_SCHEMA_VERSION,
    OPERATIONAL_KEYS,
    PREDICTIVE_KEYS,
    FingerprintError,
    MismatchError,
    UnclassifiedKeyError,
    model_content_sha256,
    stamp as stamp_v1,
    verify as verify_v1,
)

# The legacy 0.8.1 shim -- used ONLY to preserve the old hash as audit
# metadata (model_content_fingerprint_legacy_081).  DeprecationWarning is
# expected and silenced during controlled use.
try:
    from renquant_common.model_fingerprint import (
        _legacy_model_content_sha256,
    )
    _HAS_LEGACY = True
except ImportError:
    _HAS_LEGACY = False

# Default pattern for model metadata files within the artifacts directory.
DEFAULT_METADATA_FILENAME = "model_metadata.json"


def find_model_metadata(
    artifacts_dir: Path | str,
    filename: str = DEFAULT_METADATA_FILENAME,
) -> list[Path]:
    """Walk ``artifacts_dir`` recursively and return all model metadata files.

    Parameters
    ----------
    artifacts_dir:
        Root directory to search.
    filename:
        Filename to match (default ``model_metadata.json``).

    Returns
    -------
    Sorted list of absolute paths to matching files.
    """
    root = Path(artifacts_dir).resolve()
    if not root.is_dir():
        return []
    return sorted(root.rglob(filename))


def load_metadata(path: Path | str) -> dict[str, Any]:
    """Load and validate a model metadata JSON file.

    Raises
    ------
    FileNotFoundError
        If the file does not exist.
    json.JSONDecodeError
        If the file is not valid JSON.
    ValueError
        If the top-level value is not a JSON object.
    """
    p = Path(path)
    raw = p.read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError(
            f"expected JSON object at top level, got {type(data).__name__}: {p}"
        )
    return data


def compute_v1_fingerprint(metadata: dict[str, Any]) -> str:
    """Compute the v1 schema fingerprint hash from the canonical field set.

    Delegates to ``renquant_common.model_fingerprint.model_content_sha256``
    -- the ONE shared implementation.  The v1 contract:

    * Every top-level key MUST be classified in PREDICTIVE_KEYS or
      OPERATIONAL_KEYS (UnclassifiedKeyError on violation).
    * The hash covers the PREDICTIVE-classified subset only.
    * Canonical JSON serialization (sorted keys, exact float repr).
    * Non-finite floats in PREDICTIVE fields are rejected.

    Returns
    -------
    The ``sha256:<hex>`` digest string.
    """
    return model_content_sha256(metadata)


def restamp_metadata(
    path: Path | str,
    *,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Read metadata, compute v1 fingerprint, optionally write back.

    The re-stamp writes three fields into the payload:

    * ``model_content_fingerprint`` -- the v1 hash.
    * ``fingerprint_schema_version`` -- ``1`` (the v1 schema marker).
    * ``model_content_fingerprint_legacy_081`` -- the prior legacy hash
      preserved as audit/rollback metadata (never read by any verifier).

    When ``dry_run=True`` (the default), the file is NOT modified.

    Parameters
    ----------
    path:
        Path to the model metadata JSON file.
    dry_run:
        If True (default), compute but do not write.  Safety default per
        design: never write production artifacts without explicit opt-in.

    Returns
    -------
    Summary dict with keys: ``path``, ``status``, ``dry_run``,
    ``v1_fingerprint``, ``legacy_fingerprint`` (if available),
    ``prior_fingerprint`` (the value before re-stamp, if any),
    ``prior_schema_version``, ``error`` (if any).
    """
    p = Path(path).resolve()
    summary: dict[str, Any] = {
        "path": str(p),
        "dry_run": dry_run,
        "status": "pending",
        "v1_fingerprint": None,
        "legacy_fingerprint": None,
        "prior_fingerprint": None,
        "prior_schema_version": None,
        "error": None,
    }

    try:
        metadata = load_metadata(p)
    except Exception as exc:
        summary["status"] = "error"
        summary["error"] = f"load failed: {exc}"
        return summary

    # Record prior state.
    summary["prior_fingerprint"] = metadata.get("model_content_fingerprint")
    summary["prior_schema_version"] = metadata.get("fingerprint_schema_version")

    # Compute v1 fingerprint.
    try:
        v1_fp = compute_v1_fingerprint(metadata)
    except FingerprintError as exc:
        summary["status"] = "error"
        summary["error"] = f"v1 fingerprint computation failed: {exc}"
        return summary

    summary["v1_fingerprint"] = v1_fp

    # Compute legacy fingerprint for audit metadata.
    if _HAS_LEGACY:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                legacy_fp = _legacy_model_content_sha256(metadata)
            summary["legacy_fingerprint"] = legacy_fp
        except Exception:
            summary["legacy_fingerprint"] = None
    else:
        summary["legacy_fingerprint"] = None

    if dry_run:
        summary["status"] = "dry_run"
        return summary

    # Write the re-stamped metadata.
    # Preserve the prior legacy hash as audit/rollback metadata.
    prior_fp = metadata.get("model_content_fingerprint")
    if prior_fp and prior_fp != v1_fp:
        metadata["model_content_fingerprint_legacy_081"] = prior_fp

    metadata["model_content_fingerprint"] = v1_fp
    metadata["fingerprint_schema_version"] = FINGERPRINT_SCHEMA_VERSION

    # Provenance record for auditability.
    metadata["restamp_provenance"] = {
        "tool": "renquant_orchestrator.m6_restamp",
        "timestamp": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
        "schema_version": FINGERPRINT_SCHEMA_VERSION,
        "prior_fingerprint": prior_fp,
        "prior_schema_version": summary["prior_schema_version"],
    }

    p.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    summary["status"] = "stamped"
    return summary


def verify_roundtrip(path: Path | str) -> bool:
    """Re-read a stamped file and verify the fingerprint matches recomputation.

    Returns True if the stored v1 fingerprint matches a fresh computation
    over the payload.  Returns False on any mismatch or error.
    """
    p = Path(path)
    try:
        metadata = load_metadata(p)
    except Exception:
        return False

    stored_fp = metadata.get("model_content_fingerprint")
    stored_version = metadata.get("fingerprint_schema_version")
    if stored_fp is None or stored_version is None:
        return False

    try:
        verify_v1(metadata, stored_fp, stored_version)
        return True
    except (FingerprintError, ValueError):
        return False


def _build_report(results: list[dict], verify_results: dict[str, bool] | None) -> dict:
    """Build a structured report from restamp results."""
    n_total = len(results)
    n_stamped = sum(1 for r in results if r["status"] == "stamped")
    n_dry_run = sum(1 for r in results if r["status"] == "dry_run")
    n_errors = sum(1 for r in results if r["status"] == "error")
    n_verified = 0
    n_verify_failed = 0
    if verify_results:
        n_verified = sum(1 for v in verify_results.values() if v)
        n_verify_failed = sum(1 for v in verify_results.values() if not v)
    return {
        "timestamp": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
        "schema_version": FINGERPRINT_SCHEMA_VERSION,
        "summary": {
            "n_total": n_total,
            "n_stamped": n_stamped,
            "n_dry_run": n_dry_run,
            "n_errors": n_errors,
            "n_verified": n_verified,
            "n_verify_failed": n_verify_failed,
        },
        "artifacts": results,
        "verify": verify_results or {},
    }


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for the M6 re-stamp tool.

    Returns
    -------
    0 on success, 1 on partial failure, 2 on fatal error.
    """
    parser = argparse.ArgumentParser(
        description="M6 stage-2 step-2: re-stamp model metadata with v1 fingerprint.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--artifacts-dir",
        required=True,
        help="Root directory to search for model_metadata.json files.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        dest="dry_run",
        help="Preview only; do not write (default: True).",
    )
    parser.add_argument(
        "--apply",
        action="store_false",
        dest="dry_run",
        help="Actually write the re-stamped metadata (overrides --dry-run).",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        default=False,
        help="After writing, re-read each file and verify round-trip.",
    )
    parser.add_argument(
        "--output-report",
        default=None,
        help="Path to write a JSON report of all operations.",
    )
    parser.add_argument(
        "--filename",
        default=DEFAULT_METADATA_FILENAME,
        help=f"Filename pattern to search for (default: {DEFAULT_METADATA_FILENAME}).",
    )
    args = parser.parse_args(argv)

    artifacts_dir = Path(args.artifacts_dir)
    if not artifacts_dir.is_dir():
        print(f"ERROR: artifacts directory does not exist: {artifacts_dir}", file=sys.stderr)
        return 2

    # Find all metadata files.
    paths = find_model_metadata(artifacts_dir, filename=args.filename)
    if not paths:
        print(f"No {args.filename} files found under {artifacts_dir}", file=sys.stderr)
        return 0

    mode = "dry-run" if args.dry_run else "apply"
    print(f"M6 v1 re-stamp ({mode}): found {len(paths)} file(s) under {artifacts_dir}")

    # Process each file.
    results: list[dict] = []
    for p in paths:
        result = restamp_metadata(p, dry_run=args.dry_run)
        results.append(result)
        status = result["status"]
        fp = result["v1_fingerprint"] or "N/A"
        print(f"  [{status:>8}] {p.relative_to(artifacts_dir)}  v1={fp}")
        if result["error"]:
            print(f"           ERROR: {result['error']}", file=sys.stderr)

    # Verify round-trip if requested and not dry-run.
    verify_results: dict[str, bool] | None = None
    if args.verify and not args.dry_run:
        verify_results = {}
        print("\nVerification:")
        for p in paths:
            ok = verify_roundtrip(p)
            verify_results[str(p)] = ok
            tag = "PASS" if ok else "FAIL"
            print(f"  [{tag}] {p.relative_to(artifacts_dir)}")

    # Write report.
    report = _build_report(results, verify_results)
    if args.output_report:
        report_path = Path(args.output_report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"\nReport written to {report_path}")

    # Summary.
    s = report["summary"]
    print(
        f"\nSummary: {s['n_total']} found, {s['n_stamped']} stamped, "
        f"{s['n_dry_run']} dry-run, {s['n_errors']} errors"
    )
    if verify_results:
        print(
            f"  Verified: {s['n_verified']} pass, {s['n_verify_failed']} fail"
        )

    if s["n_errors"] > 0:
        return 1
    if verify_results and s["n_verify_failed"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
