"""Gate threshold calibration diagnostic (104).

Answers: are the conviction/rotation thresholds achievable given the model's
actual output distribution?  When thresholds sit ABOVE the model's max
achievable mu/er, "no trade" is a structural artifact, not a genuine signal.

Read-only: never modifies score_db, strategy config, or any artifact.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

import numpy as np

from renquant_orchestrator.runtime_paths import default_data_root

DEFAULT_DB = default_data_root() / "data" / "runs.alpaca.db"

Verdict = Literal["PASS", "STRUCTURAL_BLOCK", "MARGINAL"]

# Thresholds for the verdict classification.
STRUCTURAL_BLOCK_CEIL = 0.10  # <=10% of runs have a clearance → structural
MARGINAL_CEIL = 0.50          # <=50% → marginal


@dataclass
class GateSpec:
    """One gate to diagnose: name, the score column it gates on, and the
    threshold value. ``direction`` is ``"above"`` (candidate must be > threshold)
    or ``"below"`` (candidate must be < threshold)."""

    name: str
    column: str
    threshold: float
    direction: str = "above"


@dataclass
class GateDiagnostic:
    name: str
    column: str
    threshold: float
    direction: str
    verdict: Verdict
    runs_total: int = 0
    runs_with_clearance: int = 0
    clearance_rate: float = 0.0
    candidates_clearing_pct: float = 0.0
    score_percentiles: dict[str, float] = field(default_factory=dict)
    score_range: tuple[float | None, float | None] = (None, None)


@dataclass
class CalibrationReport:
    db_path: str
    run_type: str
    n_runs: int
    gates: list[GateDiagnostic] = field(default_factory=list)
    overall_verdict: Verdict = "PASS"


def _connect_ro(db_path: Path | None = None) -> sqlite3.Connection:
    if db_path is None:
        db_path = DEFAULT_DB
    uri = f"file:{Path(db_path)}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def _load_scores(
    conn: sqlite3.Connection,
    n_runs: int = 30,
    run_type: str = "live",
) -> list[dict[str, Any]]:
    """Load recent candidate_scores joined with pipeline_runs."""
    q = """
        SELECT cs.run_id, pr.run_date, cs.ticker,
               cs.mu, cs.sigma, cs.er, cs.raw_score, cs.rank
        FROM candidate_scores cs
        JOIN pipeline_runs pr ON pr.run_id = cs.run_id
        WHERE pr.run_type = ?
        ORDER BY pr.run_date DESC
    """
    cur = conn.execute(q, (run_type,))
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    if not rows:
        return []
    all_records = [dict(zip(cols, r)) for r in rows]
    run_ids_ordered = []
    seen = set()
    for rec in all_records:
        rid = rec["run_id"]
        if rid not in seen:
            run_ids_ordered.append(rid)
            seen.add(rid)
    keep = set(run_ids_ordered[:n_runs])
    return [r for r in all_records if r["run_id"] in keep]


def _classify(clearance_rate: float) -> Verdict:
    if clearance_rate <= STRUCTURAL_BLOCK_CEIL:
        return "STRUCTURAL_BLOCK"
    if clearance_rate <= MARGINAL_CEIL:
        return "MARGINAL"
    return "PASS"


def diagnose_gate(
    records: list[dict[str, Any]],
    gate: GateSpec,
) -> GateDiagnostic:
    """Evaluate one gate against the score distribution."""
    values_by_run: dict[str, list[float]] = {}
    all_values: list[float] = []

    for rec in records:
        val = rec.get(gate.column)
        if val is None:
            continue
        val = float(val)
        all_values.append(val)
        values_by_run.setdefault(rec["run_id"], []).append(val)

    if not all_values:
        return GateDiagnostic(
            name=gate.name,
            column=gate.column,
            threshold=gate.threshold,
            direction=gate.direction,
            verdict="STRUCTURAL_BLOCK",
            runs_total=0,
        )

    arr = np.array(all_values)
    pcts = [5, 10, 25, 50, 75, 90, 95, 99]
    percentiles = {
        f"p{p}": float(np.percentile(arr, p)) for p in pcts
    }

    if gate.direction == "above":
        clears_fn = lambda v: v > gate.threshold
    else:
        clears_fn = lambda v: v < gate.threshold

    total_candidates = len(all_values)
    candidates_clearing = sum(1 for v in all_values if clears_fn(v))

    runs_total = len(values_by_run)
    runs_with_clearance = sum(
        1 for vals in values_by_run.values()
        if any(clears_fn(v) for v in vals)
    )

    clearance_rate = runs_with_clearance / runs_total if runs_total > 0 else 0.0
    candidates_clearing_pct = candidates_clearing / total_candidates if total_candidates > 0 else 0.0

    return GateDiagnostic(
        name=gate.name,
        column=gate.column,
        threshold=gate.threshold,
        direction=gate.direction,
        verdict=_classify(clearance_rate),
        runs_total=runs_total,
        runs_with_clearance=runs_with_clearance,
        clearance_rate=clearance_rate,
        candidates_clearing_pct=candidates_clearing_pct,
        score_percentiles=percentiles,
        score_range=(float(arr.min()), float(arr.max())),
    )


def load_gates_from_config(config_path: Path) -> list[GateSpec]:
    """Extract gate thresholds from a strategy_config.json."""
    cfg = json.loads(config_path.read_text())
    gates: list[GateSpec] = []

    conviction = cfg.get("conviction_gate") or cfg.get("conviction", {})
    mu_floor = conviction.get("mu_floor")
    if mu_floor is not None:
        gates.append(GateSpec("conviction_mu_floor", "mu", float(mu_floor)))

    rotation = cfg.get("rotation") or cfg.get("rotation_gate", {})
    init_thresh = rotation.get("initiate_threshold") or rotation.get("threshold")
    if init_thresh is not None:
        gates.append(GateSpec("rotation_initiate", "er", float(init_thresh)))

    veto = cfg.get("veto_weak_buys") or cfg.get("veto", {})
    rank_floor = veto.get("rank_floor")
    if rank_floor is not None:
        gates.append(GateSpec("veto_rank_floor", "rank", float(rank_floor), direction="below"))

    return gates


def run_diagnostic(
    db_path: Path | None = None,
    config_path: Path | None = None,
    gates: list[GateSpec] | None = None,
    n_runs: int = 30,
    run_type: str = "live",
) -> CalibrationReport:
    """Run the full gate calibration diagnostic.

    Either ``config_path`` (auto-extracts gates) or ``gates`` (explicit) must
    be provided. If both, ``gates`` wins.
    """
    if gates is None and config_path is not None:
        gates = load_gates_from_config(config_path)
    if not gates:
        return CalibrationReport(
            db_path=str(db_path or DEFAULT_DB),
            run_type=run_type,
            n_runs=0,
        )

    conn = _connect_ro(db_path)
    try:
        records = _load_scores(conn, n_runs=n_runs, run_type=run_type)
    finally:
        conn.close()

    report = CalibrationReport(
        db_path=str(db_path or DEFAULT_DB),
        run_type=run_type,
        n_runs=n_runs,
    )

    worst: Verdict = "PASS"
    order = {"PASS": 0, "MARGINAL": 1, "STRUCTURAL_BLOCK": 2}

    for gate in gates:
        diag = diagnose_gate(records, gate)
        report.gates.append(diag)
        if order[diag.verdict] > order[worst]:
            worst = diag.verdict

    report.overall_verdict = worst
    return report


def render_report(report: CalibrationReport) -> str:
    lines = [
        "# Gate Calibration Diagnostic",
        "",
        f"DB:       {report.db_path}",
        f"Run type: {report.run_type}",
        f"Runs:     {report.n_runs}",
        f"Overall:  {report.overall_verdict}",
        "",
    ]
    for g in report.gates:
        lines.append(f"## {g.name} ({g.column} {'>' if g.direction == 'above' else '<'} {g.threshold})")
        lines.append("")
        lines.append(f"  Verdict:              {g.verdict}")
        lines.append(f"  Runs with clearance:  {g.runs_with_clearance}/{g.runs_total} ({g.clearance_rate:.1%})")
        lines.append(f"  Candidates clearing:  {g.candidates_clearing_pct:.1%}")
        lo, hi = g.score_range
        if lo is not None:
            lines.append(f"  Score range:          [{lo:.4f}, {hi:.4f}]")
        if g.score_percentiles:
            pct_str = "  ".join(f"{k}={v:.4f}" for k, v in g.score_percentiles.items())
            lines.append(f"  Percentiles:          {pct_str}")
        if g.verdict == "STRUCTURAL_BLOCK":
            lines.append(f"  !! STRUCTURAL: threshold {g.threshold} is above model max — no trade is ALWAYS an artifact")
        elif g.verdict == "MARGINAL":
            lines.append(f"  !! MARGINAL: threshold {g.threshold} clears <50% of runs — frequent false-no-trade")
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Gate threshold calibration diagnostic — are gates achievable?"
    )
    parser.add_argument("--db", type=Path, default=None,
                        help="score DB path (default: runs.alpaca.db)")
    parser.add_argument("--config", type=Path, default=None,
                        help="strategy_config.json to auto-extract gate thresholds")
    parser.add_argument("--n-runs", type=int, default=30,
                        help="number of recent runs to analyze")
    parser.add_argument("--run-type", default="live",
                        help="run type filter (default: live)")
    parser.add_argument("--gate", action="append", default=None,
                        metavar="NAME:COLUMN:THRESHOLD[:DIRECTION]",
                        help="explicit gate spec (repeatable); direction=above|below")
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="JSON output")
    args = parser.parse_args(argv)

    gates: list[GateSpec] | None = None
    if args.gate:
        gates = []
        for g in args.gate:
            parts = g.split(":")
            if len(parts) < 3:
                parser.error(f"gate spec needs NAME:COLUMN:THRESHOLD — got {g!r}")
            direction = parts[3] if len(parts) > 3 else "above"
            gates.append(GateSpec(parts[0], parts[1], float(parts[2]), direction))

    report = run_diagnostic(
        db_path=args.db,
        config_path=args.config,
        gates=gates,
        n_runs=args.n_runs,
        run_type=args.run_type,
    )

    if args.as_json:
        out = asdict(report)
        json.dump(out, sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
    else:
        print(render_report(report))

    if report.overall_verdict == "STRUCTURAL_BLOCK":
        return 2
    if report.overall_verdict == "MARGINAL":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
