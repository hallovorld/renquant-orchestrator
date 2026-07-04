"""Signal pipeline configuration — 106 feature-flag-off pre-build.

Defines which feature/signal sources are available for model training pipelines
and whether each is ENABLED. New signal families (PIT revisions, analyst
estimates, regime-conditioned momentum) start OFF and flip ON only through the
standard pre-registration gate — this module provides the toggle infrastructure
so activation is a config change, not a code change.

Each SignalSource has a readiness gate: minimum accrued history (days of data)
that must exist before the source CAN be enabled. The pipeline reads the
registry at retrain time and includes only enabled + ready sources.

Usage:
    from renquant_orchestrator.signal_pipeline_config import (
        load_config, default_config, source_readiness,
    )
    config = load_config(path)
    ready = source_readiness(config, data_root)
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SignalSource:
    """A feature/signal family available to the training pipeline."""

    name: str
    kind: str  # "feature_panel" | "point_in_time" | "analyst" | "derived"
    enabled: bool = False
    min_history_days: int = 0
    data_subpath: str = ""
    description: str = ""
    prereg_gate: str = ""
    upstream_repo: str = ""


@dataclass
class PipelineConfig:
    """Full signal pipeline configuration."""

    schema_version: int = 1
    sources: list[SignalSource] = field(default_factory=list)

    def by_name(self) -> dict[str, SignalSource]:
        return {s.name: s for s in self.sources}

    def enabled_sources(self) -> list[SignalSource]:
        return [s for s in self.sources if s.enabled]

    def disabled_sources(self) -> list[SignalSource]:
        return [s for s in self.sources if not s.enabled]


def default_config() -> PipelineConfig:
    """The canonical default: current production sources ON, future sources OFF."""
    return PipelineConfig(
        schema_version=1,
        sources=[
            SignalSource(
                name="alpha158_fundamental",
                kind="feature_panel",
                enabled=True,
                data_subpath="data/alpha158_291_fundamental_dataset.parquet",
                description="Alpha158 + 13 fundamental features (production primary)",
                upstream_repo="renquant-base-data",
            ),
            SignalSource(
                name="patchtst_panel_scores",
                kind="feature_panel",
                enabled=True,
                data_subpath="models/panel/patchtst",
                description="PatchTST panel model scores (production primary)",
                upstream_repo="renquant-model",
            ),
            SignalSource(
                name="pit_estimate_revisions",
                kind="point_in_time",
                enabled=False,
                min_history_days=120,
                data_subpath="data/pit/estimate_revisions",
                description="PIT analyst estimate revision snapshots (N2, accruing)",
                prereg_gate="M-SIG signal #1 prereg required before enable",
                upstream_repo="renquant-base-data",
            ),
            SignalSource(
                name="fmp_analyst_estimates",
                kind="analyst",
                enabled=False,
                min_history_days=90,
                data_subpath="data/fmp/analyst_estimates",
                description="FMP 5y analyst estimates + key metrics (N3 substrate)",
                prereg_gate="M-SIG signal #2 prereg required before enable",
                upstream_repo="renquant-base-data",
            ),
            SignalSource(
                name="regime_conditioned_momentum",
                kind="derived",
                enabled=False,
                min_history_days=60,
                data_subpath="data/signals/regime_momentum",
                description="Regime-conditioned residual momentum (M-SIG signal #3)",
                prereg_gate="M-SIG signal #3 prereg required before enable",
                upstream_repo="renquant-model",
            ),
        ],
    )


def _count_data_days(data_root: Path, subpath: str) -> int | None:
    """Count available data days in a signal source directory.

    Returns None if the path doesn't exist or isn't inspectable.
    For parquet files: file exists = "enough" (returns 9999).
    For directories of daily snapshots: counts files matching YYYY-MM-DD pattern.
    """
    full = data_root / subpath
    if not full.exists():
        return None
    if full.is_file():
        return 9999
    import re
    date_pat = re.compile(r"\d{4}-\d{2}-\d{2}")
    count = sum(1 for f in full.iterdir() if date_pat.search(f.name))
    return count if count > 0 else None


def source_readiness(
    config: PipelineConfig,
    data_root: Path,
) -> list[dict[str, Any]]:
    """Check each source's readiness: data availability vs min_history_days.

    Returns per-source dicts with: name, enabled, ready, days_available,
    min_required, gap, prereg_gate.
    """
    results = []
    for src in config.sources:
        days = _count_data_days(data_root, src.data_subpath) if src.data_subpath else None
        ready = days is not None and days >= src.min_history_days
        gap = None
        if days is not None and src.min_history_days > 0:
            gap = max(0, src.min_history_days - days)
        results.append({
            "name": src.name,
            "kind": src.kind,
            "enabled": src.enabled,
            "ready": ready,
            "days_available": days,
            "min_required": src.min_history_days,
            "gap": gap,
            "prereg_gate": src.prereg_gate or None,
        })
    return results


def load_config(path: Path) -> PipelineConfig:
    """Load pipeline config from JSON."""
    raw = json.loads(path.read_text())
    sources = [SignalSource(**s) for s in raw.get("sources", [])]
    return PipelineConfig(
        schema_version=raw.get("schema_version", 1),
        sources=sources,
    )


def save_config(config: PipelineConfig, path: Path) -> Path:
    """Save pipeline config to JSON. Refuses canonical prod paths."""
    resolved = path.resolve()
    prod_markers = ["RenQuant/data", "RenQuant/strategy_config"]
    if any(m in str(resolved) for m in prod_markers):
        raise ValueError(f"refusing to write signal pipeline config to prod path: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": config.schema_version,
        "sources": [asdict(s) for s in config.sources],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return path


def pipeline_summary(config: PipelineConfig, data_root: Path | None = None) -> dict:
    """Summary for CLI / reporting: enabled/disabled/ready counts."""
    enabled = config.enabled_sources()
    disabled = config.disabled_sources()
    summary: dict[str, Any] = {
        "schema_version": config.schema_version,
        "total_sources": len(config.sources),
        "enabled": len(enabled),
        "disabled": len(disabled),
        "enabled_names": [s.name for s in enabled],
        "disabled_names": [s.name for s in disabled],
    }
    if data_root is not None:
        readiness = source_readiness(config, data_root)
        ready_but_off = [
            r for r in readiness if r["ready"] and not r["enabled"]
        ]
        not_ready = [r for r in readiness if not r["ready"]]
        summary["ready_but_disabled"] = [r["name"] for r in ready_but_off]
        summary["not_ready"] = [
            {"name": r["name"], "gap": r["gap"]} for r in not_ready
        ]
    return summary


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint: show signal pipeline status."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Signal pipeline configuration status",
    )
    parser.add_argument(
        "--config", default=None,
        help="path to signal pipeline config JSON (default: built-in defaults)",
    )
    parser.add_argument(
        "--data-root", default=None,
        help="data root for readiness check",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="output as JSON",
    )
    args = parser.parse_args(argv)

    if args.config:
        config = load_config(Path(args.config))
    else:
        config = default_config()

    data_root = Path(args.data_root) if args.data_root else None
    summary = pipeline_summary(config, data_root)

    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(f"Signal pipeline: {summary['enabled']}/{summary['total_sources']} sources enabled")
        print(f"  Enabled: {', '.join(summary['enabled_names'])}")
        if summary["disabled_names"]:
            print(f"  Disabled (flag-off): {', '.join(summary['disabled_names'])}")
        if data_root and summary.get("ready_but_disabled"):
            print(f"  Ready but disabled: {', '.join(summary['ready_but_disabled'])}")
        if data_root and summary.get("not_ready"):
            for nr in summary["not_ready"]:
                gap = nr["gap"]
                if gap is not None:
                    print(f"  Not ready: {nr['name']} (need {gap} more days)")
                else:
                    print(f"  Not ready: {nr['name']} (no data)")

    return 0
