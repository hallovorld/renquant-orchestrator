#!/usr/bin/env python
"""M6 stage-2 STEP-0: pre-stamp LEGACY (0.8.1) model-content fingerprints.

Design: ``doc/design/2026-07-03-m6-stage2-fingerprint-migration.md`` §3 step 0
and §3a (the re-stamp inventory). PR #270 / design branch
``design/m6-stage2-fingerprint-migration``.

Why this exists (the armed sequence, design §1a)
------------------------------------------------
The live production scorer artifacts are UNSTAMPED: their
``model_content_fingerprint`` identity is recomputed at every read. The
scorer/calibrator binding holds today only because every reader recomputes
under the same renquant-common 0.8.1 semantics. When the fleet venv converges
on renquant-common 0.9.x, the bare ``model_content_sha256`` name becomes the
schema-v1 hasher and every recompute-route identity silently changes:

* WF path: ``walk_forward/loader.py::_scorer_fingerprints_from_payload``
  recomputes v1, fold calibrators declare legacy stamps, fold artifacts carry
  no stamped-value route -> ``_assert_calibrator_matches_entry`` (fail-CLOSED)
  raises on every fold; ``weekly_wf_promote`` breaks outright.
* Daily path: the weekly calibrator refit stamps a v1
  ``scorer_model_content_fingerprint`` while the runtime scorer identity stays
  legacy (0.9.1 ``stamp_artifact_metadata`` shim) ->
  ``_assert_calibrator_matches_scorer`` (fail-CLOSED) raises on the next daily
  run — the recurring "no trade" fail-close, scheduled in advance.

Verified acceptance semantics (measured against renquant-pipeline and
renquant-backtesting origin/main, 2026-07-03): every fail-closed verifier
PREFERS an artifact's stamped value over its own recompute —
``stamp_artifact_metadata``'s ``setdefault``, the calibrator-fit scripts'
``payload.get("model_content_fingerprint") or <recompute>`` precedence, and the
WF loader's collected-stamps list matched via the ``_any_fingerprints_match``
list-OR. Writing the legacy hash as an explicit stamp therefore makes the
whole fleet venv-version-insensitive with ZERO code change (design §2a's
mitigating pattern, exploited by §3 step 0).

What this tool does
-------------------
For every §3a step-0 scorer artifact that lacks a stamp, write

    ``model_content_fingerprint: <legacy 0.8.1 content hash>``

at the payload top level (the exact key every reader checks first), plus a
provenance record nested inside the existing ``metadata`` dict. NO
``fingerprint_schema_version`` is written: per §3's version-dispatch rule, a
versionless stamp IS the legacy-semantics declaration. The stamp keys are
classified operational under BOTH semantics (0.8.1 ``MUTABLE_ARTIFACT_KEYS``
and v1 ``OPERATIONAL_KEYS``), so writing them changes NEITHER content hash —
only the file bytes (whole-file hash), which is why the WF manifest stamper
re-run is a mandated follow-up (§3 step 0 / §5 row 5).

Hash logic is IMPORTS ONLY from ``renquant_common.model_fingerprint`` (the
triple-impl lesson, design §5 row 3): the legacy value is computed via the
0.9.1 deprecated shim ``model_content_sha256_from_path`` (verbatim 0.8.1
semantics), guarded fail-closed against the shim's silent whole-file-hash
fallback, and cross-checked against ``_legacy_model_content_sha256`` when that
private engine is importable. Nothing is re-implemented here. The tool
computes identical values under a 0.8.1 or 0.9.1 venv by construction (the
shims are verbatim); it must run BEFORE the live venv converges on 0.9.x.

Fail-closed refusals (per artifact)
-----------------------------------
* payload is not a JSON object, or carries no ``PREDICTIVE_CONTENT_HINTS``
  key (the legacy path API would silently fall back to a whole-file hash —
  not a stampable scorer artifact);
* the computed legacy hash equals the whole-file hash (fallback engaged —
  defensive; should be unreachable given the previous check);
* an existing ``model_content_fingerprint`` stamp DIFFERS from the legacy
  recompute (a foreign stamp is a real pre-existing problem, never
  overwritten here);
* a ``fingerprint_schema_version`` field is already present (the artifact is
  already on the versioned schema — step-2 territory, not step-0);
* any path outside the resolved inventory, or outside ``--root``.

An artifact whose existing stamp already equals the legacy recompute is a
no-op (idempotence: re-running the tool changes nothing).

Calibrators are NEVER written by this tool (step-0 column of §3a: "already
legacy-declared (verify only)"): active + WF fold bindings are verified and
any mismatch is a RED finding that blocks ``--apply`` (a real pre-existing
mismatch, not migration noise). Snapshot calibrators (``.staging`` /
``rollback`` / dated copies) are reported as warnings only. Regime
calibrators (``panel-calibration-*.json``) declare no scorer identity —
reported, outside step-0 scope pending the §5 row 8 decision.

LANDING REQUIREMENT
-------------------
``--apply`` writes to PRODUCTION artifact paths on the live umbrella tree.
That is a landing action: per the landing-actions rule it requires an
explicit operator grant, asked first, one grant per batch. ``--apply``
therefore also requires ``--grant "<operator grant note>"`` which is recorded
in every provenance stamp and in the JSON report (run-bundle evidence, with
``.bak`` per file + before/after hashes per design §3 step 0). The default is
a dry-run that writes nothing.

Usage
-----
    # Dry-run (default) against the live umbrella tree + JSON report
    python scripts/prestamp_legacy_fingerprints.py \
        --root /Users/renhao/git/github/RenQuant \
        --report /tmp/prestamp_step0_dryrun.json

    # Landing run (operator grant required; ask first)
    python scripts/prestamp_legacy_fingerprints.py \
        --root /Users/renhao/git/github/RenQuant \
        --report <run-bundle>/prestamp_step0.json \
        --apply --grant "operator grant YYYY-MM-DD: <note>"
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TOOL_ID = "renquant-orchestrator/scripts/prestamp_legacy_fingerprints.py"
DESIGN_REF = (
    "doc/design/2026-07-03-m6-stage2-fingerprint-migration.md §3 step 0 (PR #270)"
)
STAMP_KEY = "model_content_fingerprint"
SCHEMA_KEY = "fingerprint_schema_version"
PROVENANCE_KEY = "prestamp_legacy_fingerprint"

STRATEGY_REL = "backtesting/renquant_104"
ACTIVE_CONFIG_NAMES = ("strategy_config.json", "strategy_config.shadow.json")
PROD_DATA_GLOB = "data/panel-ltr-prod-*.json"
SHADOW_GLOB = "data/shadow_analyst/panel-ltr-shadow-*.json"
# §3a WF corpus: manifests are the reachability source; the default scope is
# the active gbdt_prod_recipe_v2 corpus (design §5 row 9: historical corpora
# stay out of scope unless explicitly passed via --manifest).
WF_MANIFEST_DEFAULT_GLOB = "artifacts/sim/walkforward_manifest_gbdt_prod_recipe_v2*.json"
WF_MANIFEST_KNOWN_GLOBS = (
    "artifacts/sim/walkforward_manifest*.json",
    "artifacts/walkforward*manifest*.json",
)
WF_FOLD_GLOB = "artifacts/walkforward_gbdt_prod_recipe_v2/*/panel-ltr.json"
WF_FOLD_CALIBRATOR_TEMPLATE = "artifacts/sim/walkforward_calibrators/{cutoff}/panel-rank-calibration.json"
PROD_CAL_SNAPSHOT_GLOB = "artifacts/prod/panel-rank-calibration*.json"
REGIME_CAL_GLOB = "artifacts/prod/panel-calibration-*.json"

APPLY_BANNER = """
================================================================================
  LANDING ACTION — OPERATOR GRANT REQUIRED
================================================================================
  --apply WRITES model_content_fingerprint stamps into PRODUCTION artifacts
  under the live umbrella tree:

      {root}

  Per the landing-actions rule (ask first; one grant covers one batch), this
  run may proceed ONLY under an explicit operator grant for this batch. The
  --grant note below is recorded in every stamped artifact's provenance and
  in the JSON report; keep the report + the per-file .bak backups in a run
  bundle (design §3 step 0 rollback contract).

      grant: {grant}

  Follow-up in the SAME maintenance window (before any venv convergence to
  renquant-common 0.9.x): re-run scripts/stamp_walkforward_fingerprints.py on
  the affected manifests (fold file bytes changed -> calibrator
  scorer_artifact_sha256 refresh), then re-run the census and confirm every
  calibrator binding still holds.
================================================================================
"""


class PrestampRefusal(RuntimeError):
    """Raised for fail-closed refusals; message explains the remedy."""


# ---------------------------------------------------------------------------
# renquant-common import surface (IMPORTS ONLY — never re-implement hashing)
# ---------------------------------------------------------------------------

def load_fingerprint_module():
    """Import renquant_common.model_fingerprint and validate its surface."""
    try:
        from renquant_common import model_fingerprint as mf  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - environment guard
        raise PrestampRefusal(
            "renquant_common.model_fingerprint is not importable: "
            f"{exc}. This tool computes hashes via renquant-common ONLY "
            "(triple-impl lesson); run it with the RenQuant venv / "
            "PYTHONPATH that provides renquant-common >= 0.8.1."
        ) from exc
    required = (
        "model_content_sha256_from_path",
        "artifact_sha256",
        "PREDICTIVE_CONTENT_HINTS",
        "MUTABLE_ARTIFACT_KEYS",
        "model_content_sha256",
    )
    missing = [name for name in required if not hasattr(mf, name)]
    if missing:
        raise PrestampRefusal(
            f"renquant_common.model_fingerprint lacks {missing}; need the "
            "0.8.1 legacy surface (present natively in 0.8.1 and as "
            "deprecated shims in 0.9.1)."
        )
    return mf


def legacy_fingerprint(mf, path: Path, payload: dict[str, Any]) -> str:
    """Legacy 0.8.1 content hash for ``path``, fail-closed.

    Uses the public shim ``model_content_sha256_from_path`` (verbatim 0.8.1
    semantics under 0.9.1; the native implementation under 0.8.1) and refuses
    every route by which the shim could silently fall back to a whole-file
    hash. Cross-checks against the private ``_legacy_model_content_sha256``
    engine when importable.
    """
    if not isinstance(payload, dict):
        raise PrestampRefusal(
            f"{path}: payload is {type(payload).__name__}, not a JSON object "
            "— not a stampable scorer artifact."
        )
    hints = set(mf.PREDICTIVE_CONTENT_HINTS)
    if not any(key in payload for key in hints):
        raise PrestampRefusal(
            f"{path}: no PREDICTIVE_CONTENT_HINTS key present — the legacy "
            "hasher would silently fall back to a whole-file hash; refusing "
            "(not a scorer artifact, or an unknown artifact family)."
        )
    with warnings.catch_warnings():
        # The 0.9.1 shim emits DeprecationWarning by design; using the shim
        # IS this tool's contract (verbatim 0.8.1 semantics), so silence it.
        warnings.simplefilter("ignore", DeprecationWarning)
        value = mf.model_content_sha256_from_path(path)
    file_hash = mf.artifact_sha256(path)
    if value == file_hash:
        raise PrestampRefusal(
            f"{path}: legacy content hash equals the whole-file hash — the "
            "shim's silent fallback engaged; refusing to stamp a file hash "
            "as a content identity."
        )
    engine = getattr(mf, "_legacy_model_content_sha256", None)
    if callable(engine):
        cross = engine(payload)
        if cross != value:
            raise PrestampRefusal(
                f"{path}: shim path-hash {value} != payload-level legacy "
                f"engine {cross}; renquant-common shim wiring is inconsistent "
                "— refusing everything."
            )
    return value


def current_bare_fingerprint(mf, payload: dict[str, Any]) -> str | None:
    """The bare-name recompute under THIS venv (divergence telemetry only)."""
    try:
        return mf.model_content_sha256(payload)
    except Exception as exc:  # noqa: BLE001 — telemetry only, never a gate
        return f"ERROR:{type(exc).__name__}"


# ---------------------------------------------------------------------------
# Inventory resolution (glob + pinned-config + manifest reachability, §3a)
# ---------------------------------------------------------------------------

def _read_json(path: Path) -> Any:
    return json.loads(path.read_text())


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def _resolve_strategy_path(root: Path, raw: str) -> Path:
    p = Path(raw)
    return p if p.is_absolute() else (root / STRATEGY_REL / p)


def _manifest_rows(manifest_path: Path) -> list[dict[str, Any]]:
    payload = _read_json(manifest_path)
    rows = payload.get("retrains", []) if isinstance(payload, dict) else payload
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def resolve_inventory(
    root: Path,
    extra_manifests: list[str] | None = None,
) -> dict[str, Any]:
    """Enumerate the §3a step-0 inventory at run time (never from the doc).

    Returns dict with:
      stamp_targets: {resolved_path: {"path", "family", "sources"}}
      bindings: list of {"calibrator", "scorer", "severity"} to verify
      info_rows: non-actionable rows reported for census completeness
      manifests: {"in_scope": [...], "out_of_scope": [...]}
    """
    strategy_dir = root / STRATEGY_REL
    if not (strategy_dir / "strategy_config.json").exists():
        raise PrestampRefusal(
            f"--root {root} does not look like the umbrella live tree: "
            f"missing {STRATEGY_REL}/strategy_config.json. Refusing to guess."
        )

    targets: dict[Path, dict[str, Any]] = {}
    bindings: list[dict[str, Any]] = []
    info_rows: list[dict[str, Any]] = []

    def add_target(path: Path, family: str, source: str) -> None:
        if path.suffix != ".json":
            info_rows.append({
                "path": _rel(path, root),
                "family": family,
                "status": "SKIP_NON_JSON",
                "note": "whole-file-hash artifact family (design §2a site 10); "
                        "content-hash pre-stamp N/A",
                "source": source,
            })
            return
        if not _is_under(path, root):
            raise PrestampRefusal(
                f"inventory path escapes --root: {path} (from {source}). "
                "Refusing — the inventory must live under the umbrella tree."
            )
        if not path.exists():
            raise PrestampRefusal(
                f"inventory path missing on disk: {path} (from {source}). "
                "Refusing — a missing production input is never skipped "
                "silently."
            )
        entry = targets.setdefault(
            path.resolve(), {"path": path, "family": family, "sources": []}
        )
        entry["sources"].append(source)

    # -- family: prod (named data/ artifact + pinned-config resolution) ------
    for p in sorted(root.glob(PROD_DATA_GLOB)):
        add_target(p, "prod", f"glob:{PROD_DATA_GLOB}")

    for cfg_name in ACTIVE_CONFIG_NAMES:
        cfg_path = strategy_dir / cfg_name
        if not cfg_path.exists():
            continue
        cfg = _read_json(cfg_path)
        panel = ((cfg.get("ranking") or {}).get("panel_scoring") or {})
        art_raw = panel.get("artifact_path")
        if art_raw:
            add_target(
                _resolve_strategy_path(root, str(art_raw)),
                "prod",
                f"pinned-config:{cfg_name}:ranking.panel_scoring.artifact_path",
            )
        cal_raw = ((panel.get("global_calibration") or {}).get("artifact_path"))
        if cal_raw:
            cal_path = _resolve_strategy_path(root, str(cal_raw))
            declared_scorer = None
            if cal_path.exists() and cal_path.suffix == ".json":
                cal_payload = _read_json(cal_path)
                meta = cal_payload.get("metadata") or {}
                raw_scorer = meta.get("scorer_artifact")
                if raw_scorer:
                    sp = Path(str(raw_scorer))
                    if not sp.is_absolute():
                        sp = _resolve_strategy_path(root, str(raw_scorer))
                    declared_scorer = sp
                    if sp.suffix == ".json" and _is_under(sp, root) and sp.exists():
                        add_target(
                            sp, "prod",
                            f"pinned-config:{cfg_name}:global_calibration"
                            ".metadata.scorer_artifact",
                        )
            bindings.append({
                "calibrator": cal_path,
                "scorer": declared_scorer,
                "severity": "RED",
                "source": f"pinned-config:{cfg_name}",
            })

    # -- family: shadow lanes -------------------------------------------------
    for p in sorted(root.glob(SHADOW_GLOB)):
        add_target(p, "shadow", f"glob:{SHADOW_GLOB}")

    # -- family: WF folds (manifest reachability + §3a glob) -----------------
    manifest_paths: list[Path] = sorted(
        (strategy_dir).glob(WF_MANIFEST_DEFAULT_GLOB)
    )
    for raw in extra_manifests or []:
        mp = Path(raw)
        if not mp.is_absolute():
            mp = strategy_dir / mp
        if not mp.exists():
            raise PrestampRefusal(f"--manifest not found: {mp}")
        if not _is_under(mp, root):
            raise PrestampRefusal(
                f"--manifest escapes --root: {mp}. Refusing non-inventory "
                "paths."
            )
        manifest_paths.append(mp)
    manifest_paths = list(dict.fromkeys(p.resolve() for p in manifest_paths))

    known_manifests: set[Path] = set()
    for g in WF_MANIFEST_KNOWN_GLOBS:
        known_manifests.update(p.resolve() for p in strategy_dir.glob(g))
    out_of_scope = sorted(
        _rel(p, root) for p in known_manifests - set(manifest_paths)
    )

    for mp in manifest_paths:
        for row in _manifest_rows(mp):
            art_uri = row.get("artifact_uri")
            if not art_uri:
                continue
            art_path = _resolve_strategy_path(root, str(art_uri))
            add_target(art_path, "wf-fold", f"manifest:{_rel(mp, root)}")
            cal_uri = row.get("calibrator_uri") or row.get("calibration_uri")
            if cal_uri:
                bindings.append({
                    "calibrator": _resolve_strategy_path(root, str(cal_uri)),
                    "scorer": art_path,
                    "severity": "RED",
                    "source": f"manifest:{_rel(mp, root)}",
                })

    for p in sorted(strategy_dir.glob(WF_FOLD_GLOB)):
        add_target(p, "wf-fold", f"glob:{WF_FOLD_GLOB}")
        cal = strategy_dir / WF_FOLD_CALIBRATOR_TEMPLATE.format(
            cutoff=p.parent.name
        )
        if cal.exists():
            bindings.append({
                "calibrator": cal,
                "scorer": p,
                "severity": "RED",
                "source": "fold-convention",
            })

    # -- verify-only extras: snapshots (WARN) + regime calibrators (INFO) ----
    active_cals = {
        b["calibrator"].resolve() for b in bindings if b["severity"] == "RED"
    }
    for p in sorted(strategy_dir.glob(PROD_CAL_SNAPSHOT_GLOB)):
        if p.resolve() in active_cals or p.suffix != ".json":
            continue
        bindings.append({
            "calibrator": p, "scorer": None,
            "severity": "WARN", "source": f"glob:{PROD_CAL_SNAPSHOT_GLOB}",
        })
    for p in sorted(strategy_dir.glob(REGIME_CAL_GLOB)):
        info_rows.append({
            "path": _rel(p, root),
            "family": "regime-calibrator",
            "status": "OUT_OF_SCOPE",
            "note": "declares no scorer identity; §5 row 8 decision required "
                    "before any (re-)stamp — step-0 does not touch it",
            "source": f"glob:{REGIME_CAL_GLOB}",
        })

    # Deduplicate bindings on (calibrator, scorer).
    seen: set[tuple[Path, Path | None]] = set()
    deduped: list[dict[str, Any]] = []
    for b in bindings:
        key = (b["calibrator"].resolve() if b["calibrator"].exists()
               else b["calibrator"],
               b["scorer"].resolve() if b["scorer"] and b["scorer"].exists()
               else b["scorer"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(b)

    return {
        "stamp_targets": targets,
        "bindings": deduped,
        "info_rows": info_rows,
        "manifests": {
            "in_scope": sorted(_rel(p, root) for p in manifest_paths),
            "out_of_scope": out_of_scope,
        },
    }


# ---------------------------------------------------------------------------
# Per-artifact classification + write
# ---------------------------------------------------------------------------

def classify_target(mf, root: Path, path: Path, family: str) -> dict[str, Any]:
    """Decide STAMP / SKIP_ALREADY_STAMPED / REFUSE for one artifact."""
    row: dict[str, Any] = {
        "path": _rel(path, root),
        "family": family,
        "file_sha256_before": mf.artifact_sha256(path),
    }
    try:
        payload = _read_json(path)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        row.update(status="REFUSE", reason=f"invalid JSON: {exc}")
        return row
    if not isinstance(payload, dict):
        row.update(
            status="REFUSE",
            reason=f"payload is {type(payload).__name__}, not an object",
        )
        return row
    if SCHEMA_KEY in payload:
        row.update(
            status="REFUSE",
            reason=f"{SCHEMA_KEY}={payload[SCHEMA_KEY]!r} already present — "
                   "artifact is on the versioned schema; step-0 (legacy "
                   "pre-stamp) must not touch it (step-2 territory)",
        )
        return row
    try:
        legacy = legacy_fingerprint(mf, path, payload)
    except PrestampRefusal as exc:
        row.update(status="REFUSE", reason=str(exc))
        return row
    row["legacy_fingerprint"] = legacy
    row["bare_recompute_this_venv"] = current_bare_fingerprint(mf, payload)
    existing = payload.get(STAMP_KEY)
    if existing is not None:
        if str(existing) == legacy:
            row.update(status="SKIP_ALREADY_STAMPED")
        else:
            row.update(
                status="REFUSE",
                reason=f"existing stamp {existing!r} != legacy recompute "
                       f"{legacy!r} — a foreign stamp is a real pre-existing "
                       "problem; never overwritten by step-0",
            )
        return row
    row.update(status="STAMP")
    return row


def _sniff_indent(text: str) -> int | None:
    """Match the file's existing top-level JSON indentation (byte churn only)."""
    head = text[:200]
    if head.startswith("{\n") or head.startswith("{\r\n"):
        return 2
    return None


def apply_stamp(
    mf,
    root: Path,
    path: Path,
    row: dict[str, Any],
    *,
    grant: str,
    now_iso: str,
) -> None:
    """Write the legacy stamp + provenance; verify; record before/after."""
    raw = path.read_text()
    payload = json.loads(raw)
    legacy = row["legacy_fingerprint"]
    payload[STAMP_KEY] = legacy
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
        payload["metadata"] = metadata
    metadata[PROVENANCE_KEY] = {
        "stamped_by": TOOL_ID,
        "design": DESIGN_REF,
        "semantics": "renquant-common 0.8.1 legacy (deprecated shim path)",
        "stamped_at": now_iso,
        "operator_grant": grant,
        "prior_stamp": None,
    }

    stamp_ts = now_iso.split(".")[0].replace(":", "").replace("-", "")
    backup = path.with_name(path.name + ".bak_prestamp_" + stamp_ts)
    backup.write_text(raw)
    row["backup"] = _rel(backup, root)

    indent = _sniff_indent(raw)
    if indent is None:
        blob = json.dumps(payload, separators=(",", ":"))
    else:
        blob = json.dumps(payload, indent=indent) + "\n"
    tmp = path.with_name(path.name + ".prestamp-tmp")
    tmp.write_text(blob)
    tmp.replace(path)

    # Post-write verification: the stamp is byte-identical to the legacy
    # recompute of the REWRITTEN file, and adding it changed no content hash.
    reread = _read_json(path)
    post_legacy = legacy_fingerprint(mf, path, reread)
    if reread.get(STAMP_KEY) != legacy or post_legacy != legacy:
        raise PrestampRefusal(
            f"{path}: post-write verification FAILED "
            f"(stamp={reread.get(STAMP_KEY)!r} recompute={post_legacy!r} "
            f"expected={legacy!r}); backup preserved at {backup}"
        )
    row["file_sha256_after"] = mf.artifact_sha256(path)
    row["status"] = "STAMPED"


# ---------------------------------------------------------------------------
# Binding verification (read-only, always)
# ---------------------------------------------------------------------------

def _normalize_fp(value: Any) -> str:
    return str(value or "").strip().lower().removeprefix("sha256:")


def verify_binding(mf, root: Path, binding: dict[str, Any]) -> dict[str, Any]:
    cal_path: Path = binding["calibrator"]
    row: dict[str, Any] = {
        "calibrator": _rel(cal_path, root),
        "severity": binding["severity"],
        "source": binding["source"],
    }
    if not cal_path.exists():
        row.update(verdict="MISSING", detail="calibrator file not found")
        return row
    try:
        payload = _read_json(cal_path)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        row.update(verdict="ERROR", detail=f"invalid JSON: {exc}")
        return row
    meta = payload.get("metadata") if isinstance(payload, dict) else None
    declared = (meta or {}).get("scorer_model_content_fingerprint")
    row["declared"] = declared
    if not declared:
        row.update(
            verdict="NO_DECLARATION",
            detail="calibrator declares no scorer_model_content_fingerprint",
        )
        return row
    scorer: Path | None = binding.get("scorer")
    if scorer is None:
        raw_scorer = (meta or {}).get("scorer_artifact")
        if raw_scorer:
            sp = Path(str(raw_scorer))
            if not sp.is_absolute():
                sp = _resolve_strategy_path(root, str(raw_scorer))
            scorer = sp
    if scorer is not None and scorer.suffix != ".json":
        row.update(
            verdict="FAMILY_SPLIT_NA",
            detail=f"declared scorer {scorer.name} is not a JSON payload "
                   "artifact (whole-file-hash family, design §2a site 10) — "
                   "content-hash verification N/A for step-0",
        )
        return row
    if scorer is None or not scorer.exists():
        row.update(
            verdict="UNRESOLVED_SCORER",
            detail=f"paired scorer not resolvable: {scorer}",
        )
        return row
    row["scorer"] = _rel(scorer, root)
    try:
        legacy = legacy_fingerprint(mf, scorer, _read_json(scorer))
    except PrestampRefusal as exc:
        row.update(verdict="ERROR", detail=str(exc))
        return row
    row["scorer_legacy"] = legacy
    if _normalize_fp(declared) == _normalize_fp(legacy):
        row.update(verdict="MATCH")
    else:
        row.update(
            verdict="MISMATCH",
            detail="declared scorer identity != paired scorer legacy "
                   "recompute — a REAL pre-existing mismatch (design §3 "
                   "step 2 refusal class), not migration noise",
        )
    return row


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def build_follow_ups(root: Path, inventory: dict[str, Any],
                     rows: list[dict[str, Any]]) -> list[str]:
    """The mandated §3-step-0 post-write actions (delegated, never re-done)."""
    fold_touched = any(
        r["family"] == "wf-fold" and r["status"] in ("STAMP", "STAMPED")
        for r in rows
    )
    if not fold_touched:
        return []
    ups = []
    for m in inventory["manifests"]["in_scope"]:
        rel_m = str(Path(m).relative_to(STRATEGY_REL)) if m.startswith(
            STRATEGY_REL) else m
        ups.append(
            f"cd {root} && .venv/bin/python scripts/stamp_walkforward_fingerprints.py "
            f"--manifest {rel_m} "
            "--fingerprint-config strategy_config.json "
            "--reference-artifact artifacts/prod/panel-ltr.alpha158_fund.json "
            "--dry-run   # then re-run without --dry-run under the same grant"
        )
    ups.append(
        "Run the follow-ups BEFORE any venv convergence to renquant-common "
        "0.9.x: the manifest stamper recomputes content hashes with the "
        "venv's bare model_content_sha256 (legacy today, v1 after "
        "convergence)."
    )
    return ups


def run(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    now_iso = datetime.now(timezone.utc).isoformat()
    mode = "apply" if args.apply else "dry-run"

    if args.apply:
        if not args.grant:
            print(
                "REFUSE: --apply is a landing action (writes to production "
                "artifact paths). It requires --grant \"<operator grant "
                "note>\" recorded per the landing-actions rule. Ask the "
                "operator first; one grant covers one batch.",
                file=sys.stderr,
            )
            return 2
        print(APPLY_BANNER.format(root=root, grant=args.grant))

    mf = load_fingerprint_module()
    inventory = resolve_inventory(root, extra_manifests=args.manifest)

    rows: list[dict[str, Any]] = []
    for resolved in sorted(inventory["stamp_targets"]):
        entry = inventory["stamp_targets"][resolved]
        row = classify_target(mf, root, entry["path"], entry["family"])
        row["sources"] = entry["sources"]
        rows.append(row)

    binding_rows = [
        verify_binding(mf, root, b) for b in inventory["bindings"]
    ]

    red_bindings = [
        b for b in binding_rows
        if b["severity"] == "RED"
        and b.get("verdict") not in ("MATCH", "FAMILY_SPLIT_NA")
    ]
    refusals = [r for r in rows if r["status"] == "REFUSE"]
    to_stamp = [r for r in rows if r["status"] == "STAMP"]

    blocked = bool(refusals or red_bindings)
    if args.apply and not blocked:
        for row in to_stamp:
            path = root / row["path"]
            apply_stamp(mf, root, path, row, grant=args.grant, now_iso=now_iso)
        # Re-verify every binding against the mutated tree.
        binding_rows = [
            verify_binding(mf, root, b) for b in inventory["bindings"]
        ]
        red_bindings = [
            b for b in binding_rows
            if b["severity"] == "RED"
        and b.get("verdict") not in ("MATCH", "FAMILY_SPLIT_NA")
        ]
        blocked = bool(red_bindings)

    follow_ups = build_follow_ups(root, inventory, rows)

    report = {
        "tool": TOOL_ID,
        "design": DESIGN_REF,
        "generated_at": now_iso,
        "root": str(root),
        "mode": mode,
        "operator_grant": args.grant if args.apply else None,
        "common_module": {
            "schema_v1_module": hasattr(mf, "FINGERPRINT_SCHEMA_VERSION"),
            "module_file": getattr(mf, "__file__", None),
        },
        "artifacts": rows,
        "bindings": binding_rows,
        "info": inventory["info_rows"],
        "manifests": inventory["manifests"],
        "follow_ups": follow_ups,
        "summary": {
            "n_targets": len(rows),
            "n_to_stamp": len(to_stamp),
            "n_stamped": sum(1 for r in rows if r["status"] == "STAMPED"),
            "n_already_stamped": sum(
                1 for r in rows if r["status"] == "SKIP_ALREADY_STAMPED"
            ),
            "n_refusals": len(refusals),
            "n_red_bindings": len(red_bindings),
        },
    }

    # Human-readable per-artifact before/after report.
    print(f"prestamp_legacy_fingerprints [{mode}] root={root}")
    print(f"  design: {DESIGN_REF}")
    for r in rows:
        line = f"  [{r['status']:>21}] {r['family']:<8} {r['path']}"
        if r.get("legacy_fingerprint"):
            line += f"\n{'':25}legacy={r['legacy_fingerprint']}"
        if r.get("bare_recompute_this_venv") and (
            r.get("bare_recompute_this_venv") != r.get("legacy_fingerprint")
        ):
            line += (f"\n{'':25}bare-recompute-this-venv="
                     f"{r['bare_recompute_this_venv']} (DIVERGES: this venv's "
                     "bare hasher is NOT legacy — the stamp is what keeps "
                     "verifiers stable)")
        if r.get("reason"):
            line += f"\n{'':25}reason: {r['reason']}"
        if r.get("backup"):
            line += (f"\n{'':25}backup={r['backup']}"
                     f"\n{'':25}file_sha256 {r['file_sha256_before']} -> "
                     f"{r.get('file_sha256_after')}")
        print(line)
    for b in binding_rows:
        mark = "OK " if b.get("verdict") == "MATCH" else b.get("verdict", "?")
        print(f"  [binding {b['severity']:<4} {mark:<17}] {b['calibrator']}"
              + (f" <- {b['scorer']}" if b.get("scorer") else ""))
        if b.get("detail"):
            print(f"{'':25}{b['detail']}")
    for i in inventory["info_rows"]:
        print(f"  [info {i['status']:<16}] {i['path']} — {i['note']}")
    if inventory["manifests"]["out_of_scope"]:
        print("  manifests NOT in default scope (pass --manifest to include):")
        for m in inventory["manifests"]["out_of_scope"]:
            print(f"    - {m}")
    if follow_ups:
        print("  REQUIRED follow-ups (same maintenance window):")
        for f in follow_ups:
            print(f"    - {f}")
    print(json.dumps(report["summary"], indent=2, sort_keys=True))

    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True))
        print(f"  report written: {report_path}")

    if blocked:
        print(
            "RESULT: RED — refusals/binding mismatches above; nothing may be "
            "applied until they are resolved (fail-closed).",
            file=sys.stderr,
        )
        return 2
    if args.apply:
        print("RESULT: APPLIED — record the report + .bak files in a run "
              "bundle; run the follow-ups above, then the census.")
    else:
        print("RESULT: dry-run clean — re-run with --apply --grant \"...\" "
              "under an operator grant to write.")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--root", required=True,
        help="Umbrella live-tree root (e.g. /Users/renhao/git/github/RenQuant). "
             "Must contain backtesting/renquant_104/strategy_config.json.",
    )
    p.add_argument(
        "--apply", action="store_true",
        help="Write stamps (LANDING ACTION — operator grant required; "
             "default is dry-run).",
    )
    p.add_argument(
        "--grant", default=None,
        help="Operator grant note for this batch (required with --apply; "
             "recorded in provenance + report).",
    )
    p.add_argument(
        "--manifest", action="append", default=[],
        help="Additional WF manifest (relative to backtesting/renquant_104 "
             "or absolute under --root) whose fold corpus should be included "
             "beyond the default gbdt_prod_recipe_v2 scope. Repeatable.",
    )
    p.add_argument(
        "--report", default=None,
        help="Write the full JSON report (run-bundle evidence) to this path.",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        return run(parse_args(argv))
    except PrestampRefusal as exc:
        print(f"REFUSE: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
