"""Book-level attribution rollups + coverage report + CLI (107 sprint D3).

Consumes :func:`ledger.build_round_trips` + :func:`decompose.decompose_round_trip`
and answers "where does money actually leak": per-leg cumulative curves,
per-regime / per-month tables, the leak ranking, and — first-class, not a
footnote — the COVERAGE report: which date ranges have which legs, and why
the censored ones are censored (#253 fill-confirmation boundary etc.).

Outputs are markdown + JSON written to a research-lake directory. The writer
refuses production paths (anything under the umbrella repo's ``data/`` or the
run DB's directory) — this engine is read-only over prod by construction.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from renquant_orchestrator.attribution import decompose as dc
from renquant_orchestrator.attribution import ledger as lg

from renquant_orchestrator.runtime_paths import default_data_root

DEFAULT_OUT_DIR = Path.home() / "renquant-data/research/attribution"

_DATA_ROOT = default_data_root()
_FORBIDDEN_OUT_PREFIXES = (
    _DATA_ROOT / "data",
    _DATA_ROOT / "runtime",
)


def _leg_state(result: dict[str, Any], leg: str) -> str:
    if result["legs"].get(leg) is not None:
        return "present"
    return result["censored"].get(leg, "absent")


def coverage_report(results: list[dict[str, Any]]) -> dict[str, Any]:
    """The honesty artifact: per leg, which decision-date ranges are covered
    vs censored (and for what reason). Census over the decomposed records —
    measured from data, never asserted."""
    per_leg: dict[str, Any] = {}
    for leg in dc.LEG_NAMES:
        buckets: dict[str, list[str]] = defaultdict(list)
        for r in results:
            if r["status"] == "exit_unmatched":
                continue
            buckets[_leg_state(r, leg)].append(r["date"])
        per_leg[leg] = {
            state: {
                "n": len(dates),
                "date_min": min(dates),
                "date_max": max(dates),
            }
            for state, dates in sorted(buckets.items())
        }
    n_unmatched = sum(1 for r in results if r["status"] == "exit_unmatched")
    n_decomposable = sum(1 for r in results if r["sum_check"] is not None)
    return {
        "n_records": len(results),
        "n_fully_decomposable": n_decomposable,
        "n_open_mtm": sum(1 for r in results if r["status"] == "open_mtm"),
        "n_exit_unmatched": n_unmatched,
        "per_leg": per_leg,
        "notes": [
            "Censored legs are never imputed; a censored TIMING/SIZING/COST era "
            "means fills were not confirmed in the DB (#253), not that the leak "
            "was zero.",
            "Reference prices are decision-session CLOSES (the only persisted "
            "reference); open/VWAP benchmarks are not available in this DB.",
        ],
    }


def rollup(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Book-level per-leg aggregation over whatever is honestly computable:
    each leg is summed over the records where THAT leg is present (per-leg
    populations differ under censoring and are reported alongside)."""
    totals: dict[str, float] = {leg: 0.0 for leg in dc.LEG_NAMES}
    counts: dict[str, int] = {leg: 0 for leg in dc.LEG_NAMES}
    by_month: dict[str, dict[str, float]] = defaultdict(lambda: {leg: 0.0 for leg in dc.LEG_NAMES})
    by_regime: dict[str, dict[str, float]] = defaultdict(lambda: {leg: 0.0 for leg in dc.LEG_NAMES})
    curves: dict[str, list[tuple[str, float]]] = {leg: [] for leg in dc.LEG_NAMES}

    for r in sorted(results, key=lambda x: x["date"]):
        month = r["date"][:7]
        regime = r.get("regime") or "UNKNOWN"
        for leg in dc.LEG_NAMES:
            v = r["legs"].get(leg)
            if v is None:
                continue
            totals[leg] += v
            counts[leg] += 1
            by_month[month][leg] += v
            by_regime[regime][leg] += v
            curves[leg].append((r["date"], totals[leg]))

    leak_ranking = sorted(
        ({"leg": leg, "total": totals[leg], "n": counts[leg]} for leg in dc.LEG_NAMES),
        key=lambda x: x["total"],
    )
    total_pnl = sum(r["total_pnl"] for r in results if r["total_pnl"] is not None)
    return {
        "leg_totals": totals,
        "leg_counts": counts,
        "total_pnl_where_computable": total_pnl,
        "leak_ranking": leak_ranking,
        "by_month": {m: dict(v) for m, v in sorted(by_month.items())},
        "by_regime": {g: dict(v) for g, v in sorted(by_regime.items())},
        "cumulative_curves": curves,
    }


def build_report(
    conn,
    run_type: str = "live",
    half_spread_bps: float = 0.0,
) -> dict[str, Any]:
    """End-to-end: ledger -> decomposition (identity enforced) -> rollup +
    coverage. Read-only over the DB."""
    trips = lg.build_round_trips(conn, run_type=run_type)
    results = [dc.decompose_round_trip(t, half_spread_bps=half_spread_bps) for t in trips]
    dc.assert_identity(results)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "run_type": run_type,
        "half_spread_bps": half_spread_bps,
        "coverage": coverage_report(results),
        "rollup": rollup(results),
        "records": results,
    }


def _fmt(v: float | None) -> str:
    return "censored" if v is None else f"{v:+.2f}"


def render_markdown(report: dict[str, Any]) -> str:
    cov = report["coverage"]
    roll = report["rollup"]
    lines = [
        "# Decision-ledger attribution report (107 D3)",
        "",
        f"Generated: {report['generated_at']} · run_type={report['run_type']}"
        f" · half_spread_bps={report['half_spread_bps']}",
        "",
        "## Where the money leaks (per-leg totals, $; per-leg n differs under censoring)",
        "",
        "| leg | total $ | n records |",
        "|---|---:|---:|",
    ]
    for row in roll["leak_ranking"]:
        lines.append(f"| {row['leg']} | {row['total']:+.2f} | {row['n']} |")
    lines += [
        "",
        f"Total P&L where fills allow computing it: "
        f"{roll['total_pnl_where_computable']:+.2f} $ "
        f"({cov['n_fully_decomposable']}/{cov['n_records']} records fully decomposable, "
        f"{cov['n_open_mtm']} open mark-to-market, "
        f"{cov['n_exit_unmatched']} unmatched exits).",
        "",
        "## Coverage boundary (which dates have which legs — censoring is explicit)",
        "",
        "| leg | state | n | first date | last date |",
        "|---|---|---:|---|---|",
    ]
    for leg, states in cov["per_leg"].items():
        for state, info in states.items():
            lines.append(
                f"| {leg} | {state} | {info['n']} | {info['date_min']} | {info['date_max']} |"
            )
    lines += ["", "## Per-month leg totals ($)", "", "| month | " + " | ".join(dc.LEG_NAMES) + " |",
              "|---|" + "---:|" * len(dc.LEG_NAMES)]
    for month, legs in roll["by_month"].items():
        lines.append("| " + month + " | " + " | ".join(f"{legs[leg]:+.2f}" for leg in dc.LEG_NAMES) + " |")
    lines += ["", "## Per-regime leg totals ($)", "", "| regime | " + " | ".join(dc.LEG_NAMES) + " |",
              "|---|" + "---:|" * len(dc.LEG_NAMES)]
    for regime, legs in roll["by_regime"].items():
        lines.append("| " + regime + " | " + " | ".join(f"{legs[leg]:+.2f}" for leg in dc.LEG_NAMES) + " |")
    for note in cov["notes"]:
        lines += ["", f"> {note}"]
    lines.append("")
    return "\n".join(lines)


def _check_out_dir(out_dir: Path) -> Path:
    out_dir = out_dir.expanduser().resolve()
    for forbidden in _FORBIDDEN_OUT_PREFIXES:
        try:
            out_dir.relative_to(forbidden.resolve())
        except ValueError:
            continue
        raise ValueError(
            f"refusing to write attribution outputs under production path {forbidden}"
        )
    return out_dir


def write_report(report: dict[str, Any], out_dir: str | Path) -> dict[str, Path]:
    """Write markdown + JSON into the research lake (never prod paths)."""
    out = _check_out_dir(Path(out_dir))
    out.mkdir(parents=True, exist_ok=True)
    stamp = report["generated_at"].replace(":", "").replace("+0000", "Z")
    base = f"attribution_{report['run_type']}_{stamp}"
    md_path = out / f"{base}.md"
    json_path = out / f"{base}.json"
    md_path.write_text(render_markdown(report))
    json_path.write_text(json.dumps(report, indent=2, default=str))
    return {"markdown": md_path, "json": json_path}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="renquant-attribution",
        description="Decision-ledger attribution engine (read-only over the run DB).",
    )
    p.add_argument("--db", default=str(lg.DEFAULT_DB), help="run DB path (opened read-only)")
    # live only: round-trip pairing across commingled sim streams is
    # unreliable (see ledger module doc); sim class-level attribution stays
    # with decision_pnl_attribution (#145).
    p.add_argument("--run-type", default="live", choices=["live"])
    p.add_argument("--half-spread-bps", type=float, default=0.0,
                   help="optional spread-cost proxy per traded side (flagged as estimate)")
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR),
                   help="research-lake output dir (prod paths are refused)")
    args = p.parse_args(argv)

    conn = lg.connect(args.db)
    try:
        report = build_report(conn, run_type=args.run_type, half_spread_bps=args.half_spread_bps)
    finally:
        conn.close()
    paths = write_report(report, args.out_dir)
    cov = report["coverage"]
    print(
        f"attribution: {cov['n_records']} records "
        f"({cov['n_fully_decomposable']} fully decomposable, "
        f"{cov['n_open_mtm']} open mtm, {cov['n_exit_unmatched']} unmatched exits)"
    )
    for row in report["rollup"]["leak_ranking"]:
        print(f"  {row['leg']:>7}: {row['total']:+10.2f} $  (n={row['n']})")
    print(f"markdown: {paths['markdown']}")
    print(f"json:     {paths['json']}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
