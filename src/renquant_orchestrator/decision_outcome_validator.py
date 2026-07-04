"""Decision outcome validator — gate accuracy measurement.

Joins decision-ledger verdicts (allow/halve/block per gate per scope) to
realized forward returns from ``decision_outcomes`` and computes per-gate
accuracy metrics: did ALLOW decisions lead to positive returns, did BLOCK
decisions correctly avoid losers?

Detects systematic gate failures:
  - **Over-restrictive**: a gate blocks >X% of eventually-profitable trades
  - **Under-restrictive**: a gate allows >X% of eventually-losing trades
  - **Value-destructive**: blocked names outperform allowed names (gate
    actively hurts)

The validator is READ-ONLY — it never writes to any database or file.
It consumes the same ``decision_ledger`` + ``decision_outcomes`` schema
that ``ledger_attribution`` writes.

Usage::

    rq decision-validate --db ~/renquant-data/decision_ledger.db
    rq decision-validate --horizon 5 --gate ConvictionGate --json
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger("renquant_orchestrator.decision_outcome_validator")

DEFAULT_HORIZON = 20
OVER_RESTRICTIVE_THRESHOLD = 0.50
UNDER_RESTRICTIVE_THRESHOLD = 0.50
MIN_SAMPLE_SIZE = 5

JOINED_SQL = """
SELECT
  l.as_of,
  l.scope,
  l.gate,
  l.verdict,
  l.reason,
  o.ticker,
  o.fwd_{horizon}d_ret AS fwd_ret
FROM decision_ledger l
INNER JOIN decision_outcomes o
  ON l.as_of = o.as_of AND l.scope = o.scope AND l.gate = o.gate
WHERE 1=1 {where_clause}
ORDER BY l.as_of, l.gate
"""


@dataclass
class GateAccuracy:
    gate: str
    allow_n: int = 0
    allow_profitable: int = 0
    allow_avg_ret: float | None = None
    block_n: int = 0
    block_profitable: int = 0
    block_avg_ret: float | None = None
    precision: float | None = None
    recall: float | None = None
    accuracy: float | None = None
    value_of_gate: float | None = None
    verdict: str = "INSUFFICIENT_DATA"
    detail: str = ""


@dataclass
class ValidationReport:
    horizon: int
    gate_filter: str | None
    start_date: str | None
    end_date: str | None
    total_joined_rows: int
    gates: list[GateAccuracy] = field(default_factory=list)
    overall_verdict: str = "INSUFFICIENT_DATA"
    detail: str = ""


def _safe_div(numerator: float, denominator: float) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def load_joined_data(
    conn: sqlite3.Connection,
    *,
    horizon: int = DEFAULT_HORIZON,
    gate: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict[str, Any]]:
    if horizon not in (5, 20, 60):
        raise ValueError(f"horizon must be 5, 20, or 60; got {horizon}")

    where_parts: list[str] = []
    params: list[str] = []
    if gate:
        where_parts.append("AND l.gate = ?")
        params.append(gate)
    if start_date:
        where_parts.append("AND l.as_of >= ?")
        params.append(start_date)
    if end_date:
        where_parts.append("AND l.as_of <= ?")
        params.append(end_date)

    where_clause = " ".join(where_parts)
    sql = JOINED_SQL.format(horizon=horizon, where_clause=where_clause)
    cur = conn.execute(sql, params)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def compute_gate_accuracy(
    rows: list[dict[str, Any]],
    gate_name: str,
    *,
    over_restrictive_threshold: float = OVER_RESTRICTIVE_THRESHOLD,
    under_restrictive_threshold: float = UNDER_RESTRICTIVE_THRESHOLD,
    min_sample: int = MIN_SAMPLE_SIZE,
) -> GateAccuracy:
    ga = GateAccuracy(gate=gate_name)

    allow_rets: list[float] = []
    block_rets: list[float] = []

    for r in rows:
        if r["gate"] != gate_name:
            continue
        ret = r["fwd_ret"]
        if ret is None:
            continue
        if r["verdict"] == "allow":
            allow_rets.append(ret)
        elif r["verdict"] == "block":
            block_rets.append(ret)

    ga.allow_n = len(allow_rets)
    ga.block_n = len(block_rets)

    if ga.allow_n > 0:
        ga.allow_profitable = sum(1 for r in allow_rets if r > 0)
        ga.allow_avg_ret = sum(allow_rets) / len(allow_rets)

    if ga.block_n > 0:
        ga.block_profitable = sum(1 for r in block_rets if r > 0)
        ga.block_avg_ret = sum(block_rets) / len(block_rets)

    total = ga.allow_n + ga.block_n
    if total < min_sample:
        ga.verdict = "INSUFFICIENT_DATA"
        ga.detail = f"{total} rows < {min_sample} minimum"
        return ga

    true_pos = ga.allow_profitable
    true_neg = ga.block_n - ga.block_profitable
    false_pos = ga.allow_n - ga.allow_profitable
    false_neg = ga.block_profitable

    ga.precision = _safe_div(true_pos, true_pos + false_pos)
    ga.recall = _safe_div(true_pos, true_pos + false_neg)
    ga.accuracy = _safe_div(true_pos + true_neg, total)

    if ga.allow_avg_ret is not None and ga.block_avg_ret is not None:
        ga.value_of_gate = ga.allow_avg_ret - ga.block_avg_ret

    block_profitable_rate = _safe_div(ga.block_profitable, ga.block_n) if ga.block_n > 0 else None
    allow_losing_rate = _safe_div(ga.allow_n - ga.allow_profitable, ga.allow_n) if ga.allow_n > 0 else None

    if ga.value_of_gate is not None and ga.value_of_gate < 0:
        ga.verdict = "VALUE_DESTRUCTIVE"
        ga.detail = (
            f"blocked names outperform allowed "
            f"(allow={ga.allow_avg_ret:+.4f}, block={ga.block_avg_ret:+.4f}, "
            f"VoG={ga.value_of_gate:+.4f})"
        )
    elif block_profitable_rate is not None and block_profitable_rate > over_restrictive_threshold:
        ga.verdict = "OVER_RESTRICTIVE"
        ga.detail = (
            f"{ga.block_profitable}/{ga.block_n} blocked trades were profitable "
            f"({block_profitable_rate:.1%} > {over_restrictive_threshold:.0%})"
        )
    elif allow_losing_rate is not None and allow_losing_rate > under_restrictive_threshold:
        ga.verdict = "UNDER_RESTRICTIVE"
        ga.detail = (
            f"{ga.allow_n - ga.allow_profitable}/{ga.allow_n} allowed trades lost money "
            f"({allow_losing_rate:.1%} > {under_restrictive_threshold:.0%})"
        )
    else:
        ga.verdict = "PASS"
        ga.detail = (
            f"accuracy={ga.accuracy:.1%}" if ga.accuracy is not None else "ok"
        )

    return ga


def validate(
    conn: sqlite3.Connection,
    *,
    horizon: int = DEFAULT_HORIZON,
    gate: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    min_sample: int = MIN_SAMPLE_SIZE,
) -> ValidationReport:
    rows = load_joined_data(
        conn,
        horizon=horizon,
        gate=gate,
        start_date=start_date,
        end_date=end_date,
    )

    report = ValidationReport(
        horizon=horizon,
        gate_filter=gate,
        start_date=start_date,
        end_date=end_date,
        total_joined_rows=len(rows),
    )

    if not rows:
        report.overall_verdict = "INSUFFICIENT_DATA"
        report.detail = "no joined ledger+outcome rows found"
        return report

    gate_names = sorted({r["gate"] for r in rows})

    for gn in gate_names:
        ga = compute_gate_accuracy(rows, gn, min_sample=min_sample)
        report.gates.append(ga)

    verdicts = [g.verdict for g in report.gates]
    if any(v == "VALUE_DESTRUCTIVE" for v in verdicts):
        report.overall_verdict = "FAIL"
        destructive = [g.gate for g in report.gates if g.verdict == "VALUE_DESTRUCTIVE"]
        report.detail = f"value-destructive gates: {', '.join(destructive)}"
    elif any(v == "OVER_RESTRICTIVE" for v in verdicts):
        report.overall_verdict = "WARNING"
        over = [g.gate for g in report.gates if g.verdict == "OVER_RESTRICTIVE"]
        report.detail = f"over-restrictive gates: {', '.join(over)}"
    elif all(v == "INSUFFICIENT_DATA" for v in verdicts):
        report.overall_verdict = "INSUFFICIENT_DATA"
        report.detail = "all gates below minimum sample size"
    elif all(v in ("PASS", "INSUFFICIENT_DATA") for v in verdicts):
        report.overall_verdict = "PASS"
        passing = [g.gate for g in report.gates if g.verdict == "PASS"]
        report.detail = f"{len(passing)}/{len(report.gates)} gates pass"
    else:
        report.overall_verdict = "WARNING"
        issues = [g.gate for g in report.gates if g.verdict not in ("PASS", "INSUFFICIENT_DATA")]
        report.detail = f"issues in: {', '.join(issues)}"

    return report


def render_text(report: ValidationReport) -> str:
    lines: list[str] = []
    lines.append(f"Decision Outcome Validation (fwd_{report.horizon}d)")
    lines.append(f"Overall: {report.overall_verdict} — {report.detail}")
    lines.append(f"Rows: {report.total_joined_rows}")
    if report.gate_filter:
        lines.append(f"Gate filter: {report.gate_filter}")
    if report.start_date or report.end_date:
        lines.append(f"Date range: {report.start_date or '...'} → {report.end_date or '...'}")
    lines.append("")

    for g in report.gates:
        lines.append(f"  {g.gate}: {g.verdict}")
        lines.append(f"    allow: n={g.allow_n}, profitable={g.allow_profitable}, "
                     f"avg_ret={g.allow_avg_ret:+.4f}" if g.allow_avg_ret is not None
                     else f"    allow: n={g.allow_n}")
        lines.append(f"    block: n={g.block_n}, profitable={g.block_profitable}, "
                     f"avg_ret={g.block_avg_ret:+.4f}" if g.block_avg_ret is not None
                     else f"    block: n={g.block_n}")
        if g.accuracy is not None:
            lines.append(f"    accuracy={g.accuracy:.1%}, precision={g.precision:.1%}, "
                        f"recall={g.recall:.1%}")
        if g.value_of_gate is not None:
            lines.append(f"    value_of_gate={g.value_of_gate:+.4f}")
        lines.append(f"    {g.detail}")
        lines.append("")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate decision gate accuracy against realized outcomes"
    )
    parser.add_argument(
        "--db", default=None,
        help="decision ledger DB path (default: ~/renquant-data/decision_ledger.db)",
    )
    parser.add_argument(
        "--horizon", type=int, default=DEFAULT_HORIZON, choices=[5, 20, 60],
        help="forward return horizon in days (default: 20)",
    )
    parser.add_argument("--gate", default=None, help="filter to a specific gate")
    parser.add_argument("--start-date", default=None, help="start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", default=None, help="end date (YYYY-MM-DD)")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument(
        "--min-sample", type=int, default=MIN_SAMPLE_SIZE,
        help=f"minimum sample size per gate (default: {MIN_SAMPLE_SIZE})",
    )
    parser.add_argument(
        "--strict", action="store_true",
        help="return non-zero on WARNING or FAIL",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    from .decision_ledger import DEFAULT_DB
    from .ledger_attribution import OUTCOMES_DDL

    db_path = Path(args.db) if args.db else DEFAULT_DB
    if not db_path.exists():
        print(f"error: DB not found at {db_path}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        if "decision_ledger" not in tables:
            print("error: decision_ledger table not found", file=sys.stderr)
            return 1
        if "decision_outcomes" not in tables:
            print("error: decision_outcomes table not found "
                  "(no forward returns recorded yet)", file=sys.stderr)
            return 1

        report = validate(
            conn,
            horizon=args.horizon,
            gate=args.gate,
            start_date=args.start_date,
            end_date=args.end_date,
            min_sample=args.min_sample,
        )
    finally:
        conn.close()

    if args.json:
        print(json.dumps(asdict(report), indent=2))
    else:
        print(render_text(report))

    if args.strict and report.overall_verdict in ("FAIL", "WARNING"):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
