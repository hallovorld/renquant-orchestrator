#!/usr/bin/env python3
"""S11 live-tree dirt inventory: machine-generated, mechanically reconciled.

READ-ONLY. Runs `git status --porcelain=v2` against the live umbrella tree and
classifies every reported path into exactly one class, then asserts the
classified path set equals the raw path set (no omissions, no duplicates).
Never mutates the live tree (no checkout/reset/stash/pull/clean/rm/mv).

Usage:
    python3 scripts/s11_live_tree_inventory.py [--live-tree PATH] [--out PATH]

Exits non-zero and raises if the reconciliation assertion fails — this is the
mechanism that makes "exhaustive" verifiable rather than asserted in prose.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_LIVE_TREE = "/Users/renhao/git/github/RenQuant"


@dataclass
class ClassifiedPath:
    path: str
    xy: str
    kind: str  # "tracked_modified" | "untracked"
    is_directory_entry: bool
    cls: str
    producer: str
    artifact_kind: str  # source | runtime_generated | backup | unknown
    tracked_policy: str
    disposition: str
    ticket: str
    nested_file_count: int | None = None  # supplementary only, for directory entries


# ---------------------------------------------------------------------------
# git status parsing (read-only)
# ---------------------------------------------------------------------------


def run_git_status(live_tree: str) -> list[tuple[str, str, bool]]:
    """Return [(path, xy, is_directory_entry)] from `git status --porcelain=v2`.

    Directory-entry untracked paths (an entire untracked directory reported as
    one line, because git does not recurse into a wholly-untracked directory)
    end in '/'. Tracked-modified (type '1') paths are never directory entries.
    """
    proc = subprocess.run(
        ["git", "-C", live_tree, "status", "--porcelain=v2"],
        capture_output=True, text=True, check=True,
    )
    out: list[tuple[str, str, bool]] = []
    for line in proc.stdout.splitlines():
        if not line:
            continue
        if line.startswith("1 "):
            fields = line.split(" ", 8)
            if len(fields) != 9:
                raise ValueError(f"unexpected type-1 porcelain line (renames not handled): {line!r}")
            xy, path = fields[1], fields[8]
            out.append((path, xy, False))
        elif line.startswith("2 "):
            raise ValueError(f"unexpected rename/copy (type '2') porcelain line — script does not handle renames: {line!r}")
        elif line.startswith("? "):
            path = line[2:]
            out.append((path, "??", path.endswith("/")))
        elif line.startswith("u "):
            raise ValueError(f"unexpected unmerged (type 'u') porcelain line: {line!r}")
        # ignored '!' lines are not emitted by default porcelain and are skipped if present
    return out


def count_nested_files(live_tree: str, dir_path: str) -> int:
    """Read-only supplementary count of files inside an untracked directory entry."""
    full = Path(live_tree) / dir_path
    if not full.is_dir():
        return 0
    return sum(1 for p in full.rglob("*") if p.is_file())


# ---------------------------------------------------------------------------
# Classification rules (ordered; first match wins)
# ---------------------------------------------------------------------------

_TICKER_MODEL_RE = re.compile(
    r"^(?:backtesting/renquant_104/)?models/[A-Z0-9.]+/[A-Z0-9.]+-"
    r"(policy-metadata|qtable|bin-edges|rf-trees|xgb-buy|xgb-sell|manual-rules)\.json$"
)
_TICKER_MODEL_DIR_RE = re.compile(r"^(?:backtesting/renquant_104/)?models/[A-Z0-9.]+/$")
_WF_GBDT_RE = re.compile(
    r"^(?:backtesting/renquant_104/)?artifacts/walkforward_gbdt_prod_recipe_v2/\d{4}-\d{2}-\d{2}/panel-ltr\.json$"
)
_SIM_CALIB_RE = re.compile(
    r"^(?:backtesting/renquant_104/)?artifacts/sim/walkforward_calibrators/\d{4}-\d{2}-\d{2}/panel-rank-calibration\.json$"
)
_PROD_CALIB_RESTAMP_RE = re.compile(
    r"^(?:backtesting/renquant_104/)?artifacts/prod/(panel-ltr\.alpha158_fund\.json|panel-rank-calibration\.json)$"
)
_LEAN_DATA_RE = re.compile(
    r"^backtesting/data/equity/usa/(daily|factor_files|map_files)/"
)
_RUNNER_PY_RE = re.compile(r"^(?:backtesting/renquant_104/)?adapters/runner\.py$")
_LIVE_STATE_RE = re.compile(
    r"^(?:backtesting/renquant_104/)?live_state\.(alpaca|alpaca_shadow)\.json$"
)
_STRATEGY_CONFIG_RE = re.compile(r"^(?:backtesting/renquant_104/)?strategy_config\.json$")
_DASHBOARD_RE = re.compile(r"^doc/dashboard\.md$")
_SUBREPOS_LOCK_RE = re.compile(r"^subrepos\.lock\.json$")

_WEEKLY_STAGING_RE = re.compile(
    r"^(?:backtesting/renquant_104/)?artifacts/prod/"
    r"(panel-ltr\.alpha158_fund|panel-rank-calibration)\.weekly_\d{8}T\d{6}Z\.staging\.json$"
)
_PROMOTE_ROLLBACK_RE = re.compile(
    r"^(?:backtesting/renquant_104/)?artifacts/prod/"
    r"(panel-ltr\.alpha158_fund|panel-rank-calibration)\.(weekly|monthly)_rollback_\d{4}-\d{2}-\d{2}\.json$"
)
_WF_EVAL_CONFIG_TOPLEVEL_RE = re.compile(
    r"^(?:backtesting/renquant_104/)?strategy_config\.[A-Za-z0-9_]+\.json$"
)
_WF_EVAL_PROD_SEMANTIC_RE = re.compile(
    r"^(?:backtesting/renquant_104/)?artifacts/diagnostics/wf_eval_configs/strategy_config\.[A-Za-z0-9_]+\.prod_semantic\.json$"
)
_QP_REPLAY_RE = re.compile(r"^artifacts/qp_step4_replay/$")
_PROMOTE_BAK_RE = re.compile(r"^subrepos\.lock\.json\.promote-bak\.\d{8}T\d{6}$")
_RESTAMP_BAK_RE = re.compile(
    r"^(?:backtesting/renquant_104/)?artifacts/patchtst_shadow/.*\.bak\.\d{8}-restamp$"
)
_AS_OF_RE = re.compile(r"^as_of$")

# "Other artifacts/ top-level generated outputs" — everything else directly
# under (backtesting/renquant_104/)?artifacts/ that isn't matched above, plus
# a small named set of shared-pipeline outputs. Kept as an explicit allowlist
# (not a catch-all regex) so new/unexpected paths fall through to UNCLASSIFIED
# and fail the reconciliation assertion instead of being silently absorbed.
_OTHER_ARTIFACTS_ALLOWLIST = {
    "artifacts/cache/",
    "artifacts/diagnostics/wf_trade_traces/",
    "artifacts/live-shadow/",
    "artifacts/walkforward_patchtst/",
    "artifacts/walkforward_patchtst_20d/",
    "artifacts/panel-ltr.alpha158_fund.json",
    "artifacts/panel-ltr.alpha158_linear.json",
    "artifacts/panel-ltr.alpha158_linear.previous.json",
    "artifacts/panel-rank-calibration.alpha158_linear.json",
    "artifacts/sim/walkforward_manifest_gbdt_prod_recipe_v2.json",
    "artifacts/spy-gmm-regime.json",
    "artifacts/walkforward_patchtst/",
    "artifacts/walkforward_patchtst_20d/",
    "artifacts/walkforward_patchtst_20d_manifest.json",
    "artifacts/walkforward_patchtst_manifest.json",
    "artifacts/watchlist-correlation.json",
}
_OTHER_ARTIFACTS_PREFIXED = {
    f"backtesting/renquant_104/{p}" for p in _OTHER_ARTIFACTS_ALLOWLIST
} | _OTHER_ARTIFACTS_ALLOWLIST


def classify(path: str, xy: str, is_dir: bool) -> ClassifiedPath:
    kind = "untracked" if xy == "??" else "tracked_modified"

    if _TICKER_MODEL_RE.match(path):
        return ClassifiedPath(
            path, xy, kind, is_dir,
            cls="per_ticker_model_artifact_tracked",
            producer="per-ticker training/tournament pipeline",
            artifact_kind="runtime_generated",
            tracked_policy="correctly tracked — intended durability mechanism for trained per-ticker state",
            disposition="no_action",
            ticket="",
        )
    if is_dir and _TICKER_MODEL_DIR_RE.match(path):
        return ClassifiedPath(
            path, xy, kind, is_dir,
            cls="per_ticker_model_artifact_new_ticker_dir",
            producer="per-ticker training/tournament pipeline",
            artifact_kind="runtime_generated",
            tracked_policy="should be tracked once this ticker is committed to the live watchlist/universe",
            disposition="self_resolving_no_action",
            ticket="s11-universe-expansion-model-commit (new — see roadmap-backlog.json)",
        )
    if _WF_GBDT_RE.match(path):
        return ClassifiedPath(
            path, xy, kind, is_dir,
            cls="wf_gate_gbdt_recipe_artifact",
            producer="scripts/run_wf_gate.py",
            artifact_kind="runtime_generated",
            tracked_policy="tracked — WF corpus is durable evidence per repo convention",
            disposition="no_action",
            ticket="",
        )
    if _SIM_CALIB_RE.match(path):
        return ClassifiedPath(
            path, xy, kind, is_dir,
            cls="sim_calibrator_artifact",
            producer="scripts/run_wf_gate.py (calibrator side)",
            artifact_kind="runtime_generated",
            tracked_policy="tracked",
            disposition="no_action",
            ticket="",
        )
    if _PROD_CALIB_RESTAMP_RE.match(path):
        return ClassifiedPath(
            path, xy, kind, is_dir,
            cls="prod_calibrator_restamp",
            producer="stamp_patchtst_fingerprint.py-class re-stamp tooling",
            artifact_kind="runtime_generated",
            tracked_policy="tracked",
            disposition="ticketed",
            ticket="calibrator-fingerprint-unification (existing plan item, M6/R2 — see memory: calibrator-scorer-fingerprint-triple-impl-bug)",
        )
    if _LEAN_DATA_RE.match(path):
        return ClassifiedPath(
            path, xy, kind, is_dir,
            cls="lean_backtest_data",
            producer="LEAN data-sync tooling",
            artifact_kind="runtime_generated",
            tracked_policy="tracked",
            disposition="no_action",
            ticket="",
        )
    if _RUNNER_PY_RE.match(path):
        return ClassifiedPath(
            path, xy, kind, is_dir,
            cls="runner_py_hotfix_residue",
            producer="manual hotfix",
            artifact_kind="source",
            tracked_policy="tracked",
            disposition="resolved_upstream",
            ticket="no ticket needed — origin/main already ships the fix; local diff is behind-origin residue, resolved by the sync procedure",
        )
    if _LIVE_STATE_RE.match(path):
        return ClassifiedPath(
            path, xy, kind, is_dir,
            cls="live_state_tracked",
            producer="runner.py::save_live_state_atomic",
            artifact_kind="runtime_generated",
            tracked_policy="tracked despite a .gitignore rule that does not match this filename pattern (broker-suffixed) — intent unconfirmed",
            disposition="unresolved_needs_owner",
            ticket="s11-live-state-gitignore-mismatch (new — see roadmap-backlog.json)",
        )
    if _STRATEGY_CONFIG_RE.match(path):
        return ClassifiedPath(
            path, xy, kind, is_dir,
            cls="strategy_config_pinned",
            producer="pin-align tooling / manual edit",
            artifact_kind="source",
            tracked_policy="tracked",
            disposition="no_action",
            ticket="",
        )
    if _DASHBOARD_RE.match(path):
        return ClassifiedPath(
            path, xy, kind, is_dir,
            cls="dashboard_doc",
            producer="dashboard-render tooling",
            artifact_kind="runtime_generated",
            tracked_policy="tracked",
            disposition="no_action",
            ticket="",
        )
    if _SUBREPOS_LOCK_RE.match(path):
        return ClassifiedPath(
            path, xy, kind, is_dir,
            cls="subrepos_lock",
            producer="scripts/promote_pin.py / pin-align tooling",
            artifact_kind="runtime_generated",
            tracked_policy="tracked",
            disposition="no_action",
            ticket="",
        )
    if _WEEKLY_STAGING_RE.match(path):
        return ClassifiedPath(
            path, xy, kind, is_dir,
            cls="weekly_promote_staging",
            producer="training_panel/daily_retrain_alpha158_fund.py / kernel/model_acceptance.py "
                      "(covers both panel-ltr and panel-rank-calibration staging families)",
            artifact_kind="runtime_generated",
            tracked_policy="correctly untracked — staging area, not the durable artifact",
            disposition="ticketed",
            ticket="s11-staging-backup-retention-policy (new — see roadmap-backlog.json)",
        )
    if _PROMOTE_ROLLBACK_RE.match(path):
        return ClassifiedPath(
            path, xy, kind, is_dir,
            cls="weekly_monthly_promote_rollback_snapshot",
            producer="kernel/model_acceptance.py-class promote pipeline (rollback-safety snapshot, "
                      "distinct from the pre-promote staging copy above — this is a kept revert point)",
            artifact_kind="backup",
            tracked_policy="correctly untracked — intentional rollback-safety copy, not the durable promoted artifact",
            disposition="ticketed",
            ticket="s11-staging-backup-retention-policy (new — see roadmap-backlog.json; same "
                   "unbounded-growth concern as weekly-promote staging — 20 dated rollback files "
                   "with no visible pruning, spanning the same ~2.5 week window)",
        )
    if _WF_EVAL_CONFIG_TOPLEVEL_RE.match(path):
        return ClassifiedPath(
            path, xy, kind, is_dir,
            cls="wf_eval_experiment_config",
            producer="scripts/run_wf_gate.py / kernel/model_acceptance.py",
            artifact_kind="runtime_generated",
            tracked_policy="correctly untracked — ad hoc experiment scratch state",
            disposition="no_action",
            ticket="",
        )
    if _WF_EVAL_PROD_SEMANTIC_RE.match(path):
        return ClassifiedPath(
            path, xy, kind, is_dir,
            cls="wf_eval_prod_semantic_diagnostic",
            producer="WF-eval harness semantic-diff-against-prod diagnostic dump",
            artifact_kind="runtime_generated",
            tracked_policy="correctly untracked",
            disposition="no_action",
            ticket="",
        )
    if is_dir and _QP_REPLAY_RE.match(path):
        return ClassifiedPath(
            path, xy, kind, is_dir,
            cls="qp_replay_output",
            producer="UNKNOWN — repo-wide grep for 'qp_step4_replay' found no writer",
            artifact_kind="unknown",
            tracked_policy="unknown",
            disposition="unresolved_needs_owner",
            ticket="s11-qp-replay-origin (new — see roadmap-backlog.json)",
        )
    if _PROMOTE_BAK_RE.match(path):
        return ClassifiedPath(
            path, xy, kind, is_dir,
            cls="promote_pin_backup",
            producer="scripts/promote_pin.py (backup-before-write)",
            artifact_kind="backup",
            tracked_policy="correctly untracked",
            disposition="ticketed",
            ticket="s11-staging-backup-retention-policy (new — see roadmap-backlog.json; same retention gap as weekly-promote staging)",
        )
    if _RESTAMP_BAK_RE.match(path):
        return ClassifiedPath(
            path, xy, kind, is_dir,
            cls="restamp_backup_known_event",
            producer="manual re-stamp operation, 2026-06-25 (shadow config-FP re-stamp)",
            artifact_kind="backup",
            tracked_policy="correctly untracked",
            disposition="no_action",
            ticket="",
        )
    if _AS_OF_RE.match(path):
        return ClassifiedPath(
            path, xy, kind, is_dir,
            cls="untracked_as_of_file",
            producer="UNKNOWN — repo-wide grep found no writer; file is 0 bytes",
            artifact_kind="unknown",
            tracked_policy="unknown",
            disposition="unresolved_needs_owner",
            ticket="s11-as-of-file-origin (new — see roadmap-backlog.json)",
        )
    stripped = path[len("backtesting/renquant_104/"):] if path.startswith("backtesting/renquant_104/") else path
    if path in _OTHER_ARTIFACTS_PREFIXED or stripped in _OTHER_ARTIFACTS_ALLOWLIST:
        return ClassifiedPath(
            path, xy, kind, is_dir,
            cls="other_artifacts_generated",
            producer="scripts/train_walkforward_patchtst.py / shared renquant_103/renquant_104 pipeline code (watchlist-correlation.json, spy-gmm-regime.json)",
            artifact_kind="runtime_generated",
            tracked_policy="correctly untracked — recomputable working artifacts",
            disposition="no_action",
            ticket="",
        )

    return ClassifiedPath(
        path, xy, kind, is_dir,
        cls="UNCLASSIFIED",
        producer="UNCLASSIFIED",
        artifact_kind="UNCLASSIFIED",
        tracked_policy="UNCLASSIFIED",
        disposition="UNCLASSIFIED — reconciliation will fail",
        ticket="",
    )


# ---------------------------------------------------------------------------
# Reconciliation + manifest
# ---------------------------------------------------------------------------


def build_manifest(live_tree: str) -> dict:
    raw = run_git_status(live_tree)
    raw_paths = [p for p, _, _ in raw]

    if len(raw_paths) != len(set(raw_paths)):
        seen: dict[str, int] = {}
        dupes = []
        for p in raw_paths:
            seen[p] = seen.get(p, 0) + 1
        dupes = [p for p, n in seen.items() if n > 1]
        raise AssertionError(f"git status returned duplicate paths (should be impossible): {dupes}")

    rows: list[ClassifiedPath] = []
    for path, xy, is_dir in raw:
        row = classify(path, xy, is_dir)
        if row.is_directory_entry:
            row.nested_file_count = count_nested_files(live_tree, path)
        rows.append(row)

    unclassified = [r.path for r in rows if r.cls == "UNCLASSIFIED"]
    if unclassified:
        raise AssertionError(
            f"{len(unclassified)} raw path(s) did not match any classification rule "
            f"(reconciliation FAILED — inventory is NOT exhaustive): {unclassified[:20]}"
        )

    classified_paths = [r.path for r in rows]
    if len(classified_paths) != len(set(classified_paths)):
        raise AssertionError("classification produced duplicate rows for the same path")

    raw_set, classified_set = set(raw_paths), set(classified_paths)
    if raw_set != classified_set:
        raise AssertionError(
            f"raw path set != classified path set. "
            f"missing from classification: {sorted(raw_set - classified_set)[:20]} "
            f"extra in classification: {sorted(classified_set - raw_set)[:20]}"
        )
    if len(raw_paths) != len(rows):
        raise AssertionError(f"raw count {len(raw_paths)} != classified row count {len(rows)}")

    by_class: dict[str, list[ClassifiedPath]] = {}
    for r in rows:
        by_class.setdefault(r.cls, []).append(r)

    class_summary = [
        {
            "class": cls,
            "count": len(items),
            "kind": items[0].kind,
            "artifact_kind": items[0].artifact_kind,
            "disposition": items[0].disposition,
            "ticket": items[0].ticket,
            "producer": items[0].producer,
            "representative_paths": [i.path for i in items[:3]],
            "total_nested_files_supplementary": (
                sum(i.nested_file_count or 0 for i in items)
                if any(i.is_directory_entry for i in items) else None
            ),
        }
        for cls, items in sorted(by_class.items())
    ]

    disposition_counts: dict[str, int] = {}
    for r in rows:
        disposition_counts[r.disposition] = disposition_counts.get(r.disposition, 0) + 1

    return {
        "live_tree": live_tree,
        "raw_path_count": len(raw_paths),
        "tracked_modified_count": sum(1 for r in rows if r.kind == "tracked_modified"),
        "untracked_count": sum(1 for r in rows if r.kind == "untracked"),
        "classified_row_count": len(rows),
        "reconciliation": "PASS — raw path set == classified path set, no duplicates, no omissions",
        "disposition_counts": disposition_counts,
        "class_summary": class_summary,
        "paths": [
            {
                "path": r.path,
                "xy": r.xy,
                "kind": r.kind,
                "is_directory_entry": r.is_directory_entry,
                "nested_file_count_supplementary": r.nested_file_count,
                "class": r.cls,
                "producer": r.producer,
                "artifact_kind": r.artifact_kind,
                "tracked_policy": r.tracked_policy,
                "disposition": r.disposition,
                "ticket": r.ticket,
            }
            for r in rows
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--live-tree", default=DEFAULT_LIVE_TREE)
    ap.add_argument("--out", default=None, help="write full manifest JSON here")
    args = ap.parse_args()

    manifest = build_manifest(args.live_tree)

    print(f"raw_path_count={manifest['raw_path_count']} "
          f"(tracked_modified={manifest['tracked_modified_count']}, "
          f"untracked={manifest['untracked_count']})")
    print(f"reconciliation: {manifest['reconciliation']}")
    print(f"disposition_counts: {manifest['disposition_counts']}")
    for c in manifest["class_summary"]:
        print(f"  {c['class']}: {c['count']} ({c['disposition']})")

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(manifest, indent=2, sort_keys=False) + "\n")
        print(f"\nwrote {args.out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
