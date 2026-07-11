"""Session outage monitor — the orchestrator-side consumer of the pipeline's
``funnel_integrity.v1`` + ``data_availability.v1`` run-bundle blocks.

WHY THIS LIVES HERE. On 2026-07-08/09 the buy scan ran on ~0 tickers (133/145
admission models fail-closed on staleness) and both sessions were reported
through the normal quiet "no trade" ntfy path — a two-day engineering OUTAGE
rendered as a market decision. renquant-pipeline #186/#187 made the pipeline
publish first-class, versioned verdict blocks (``ctx.funnel_integrity``,
``ctx.data_availability``) but deliberately emit NO notification: Codex closed
the umbrella alert PR (RenQuant#463) ruling that alert rendering belongs to the
repo that owns notification delivery — this one. This module reads the latest
run bundle's blocks and renders the operator-facing page.

TITLE-TAG VOCABULARY (the notification headline contract, owned here):

  ``OUTAGE``    — structural loss of buy capability (funnel
                  ``STRUCTURAL_BLOCK``) or a fail-closed data axis (data
                  ``BLOCKED``). Never reportable as a normal no-trade.
  ``DEGRADED``  — integrity invariant(s) fired but capability partially
                  survived, or a data axis alarmed under degrade_with_alarm.
  ``NO-TRADE``  — clean economic no-trade (``ECONOMIC_NO_TRADE``): zero buys
                  and NOTHING fired. The only no-buy state that may read quiet.
  ``TRADE``     — buys emitted, nothing fired.

The combined title tag is the WORST of the two blocks' contributions
(OUTAGE > DEGRADED > NO-TRADE > TRADE).

Properties (house monitor conventions, same as ``daily_trading_health``):

  * **read-only** — consumes one run-bundle JSON; never touches broker, live
    state, or production paths.
  * **fail-soft** — a missing/absent block degrades to a recorded
    ``missing_blocks`` note (with a best-effort hint from the ``counters``
    integer mirrors), never an exception. The monitor's own crash must not
    dark the session it audits.
  * **DARK by default** — this module is wire-ready for the daily flow but is
    invoked by NO scheduled job yet; wiring into daily automation is a
    separate landing (machine-landing, ask-first).

Field sources (exact schemas: pipeline ``task_funnel_integrity.py`` /
``task_data_availability.py`` docstrings, pipeline PRs #186/#187):

  * ``bundle["funnel_integrity"]`` — ``verdict``, ``verdict_reason``,
    ``structural``, ``fired[] {invariant, severity, reason, evidence}``,
    ``gate_kill_counts``, ``funnel{n_watchlist, n_admitted, ...}``, ``error``.
    Universe-collapse per-cause counts come from the
    ``universe_admission_collapse`` finding's ``evidence.top_rejection_reasons``.
  * ``bundle["data_availability"]`` — ``verdict (AVAILABLE|DEGRADED|BLOCKED)``,
    ``degraded``, ``blocked``, ``axes{name: {verdict, policy, age_days,
    coverage, violations, ...}}``, ``fired[] {axis, policy, reason, evidence}``,
    ``missing_contracts[]``, ``error``.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from renquant_common.notify import send as _send_notification

SCHEMA_VERSION = 1
OWNER_REPO = "renquant-orchestrator"

# --- Title-tag vocabulary (the notification headline contract) ---------------
TAG_OUTAGE = "OUTAGE"
TAG_DEGRADED = "DEGRADED"
TAG_NO_TRADE = "NO-TRADE"
TAG_TRADE = "TRADE"

# Worst-first severity order for combining the two blocks' contributions.
_TAG_SEVERITY = {TAG_OUTAGE: 3, TAG_DEGRADED: 2, TAG_NO_TRADE: 1, TAG_TRADE: 0}

# funnel_integrity.v1 verdict -> title tag
_FUNNEL_VERDICT_TO_TAG = {
    "STRUCTURAL_BLOCK": TAG_OUTAGE,
    "DEGRADED": TAG_DEGRADED,
    "ECONOMIC_NO_TRADE": TAG_NO_TRADE,
    "ECONOMIC_TRADE": TAG_TRADE,
}

# data_availability.v1 verdict -> title tag contribution (AVAILABLE contributes
# nothing: data availability alone never asserts a session trade verdict).
_DATA_VERDICT_TO_TAG = {
    "BLOCKED": TAG_OUTAGE,
    "DEGRADED": TAG_DEGRADED,
    "AVAILABLE": None,
}

# ntfy priority per combined tag (5 = ntfy max/page).
_TAG_PRIORITY = {TAG_OUTAGE: 5, TAG_DEGRADED: 4, TAG_NO_TRADE: 3, TAG_TRADE: 3}
_TAG_NTFY_TAGS = {
    TAG_OUTAGE: "rotating_light",
    TAG_DEGRADED: "warning",
    TAG_NO_TRADE: "zzz",
    TAG_TRADE: "chart",
}

# Integer mirrors the pipeline stamps on ctx.counters — the fallback signal
# when a bundle predates block stamping but counters_json already carries them.
_COUNTER_HINT_KEYS = (
    "funnel_integrity_fired",
    "funnel_integrity_structural",
    "funnel_integrity_errors",
    "data_availability_fired",
    "data_availability_degraded",
    "data_availability_blocked",
)


@dataclass
class OutageReport:
    """The structured result of rendering one run bundle's integrity blocks."""

    as_of: str
    run_id: str
    title_tag: str | None = None
    title: str | None = None
    body_lines: list[str] = field(default_factory=list)
    funnel_summary: dict[str, Any] = field(default_factory=dict)
    data_summary: dict[str, Any] = field(default_factory=dict)
    missing_blocks: list[str] = field(default_factory=list)
    counter_hints: dict[str, Any] = field(default_factory=dict)

    @property
    def body(self) -> str:
        return "\n".join(self.body_lines)

    @property
    def priority(self) -> int:
        return _TAG_PRIORITY.get(self.title_tag or "", 3)

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "owner_repo": OWNER_REPO,
            "as_of": self.as_of,
            "run_id": self.run_id,
            "title_tag": self.title_tag,
            "title": self.title,
            "body": self.body,
            "priority": self.priority,
            "funnel_integrity": self.funnel_summary,
            "data_availability": self.data_summary,
            "missing_blocks": self.missing_blocks,
            "counter_hints": self.counter_hints,
        }


# --- low-level helpers --------------------------------------------------------

def _today_iso(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).date().isoformat()


def _load_json(path: str | Path | None) -> Any | None:
    if path is None:
        return None
    p = Path(path)
    if not p.exists() or not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def find_latest_bundle(root: str | Path) -> Path | None:
    """Newest ``run_bundle*.json`` under ``root`` (recursive), by mtime.

    The daily flow persists one bundle per run (``daily.py`` writes
    ``<output_dir>/run_bundle.json``); "latest" = most recently written.
    """
    rootp = Path(root)
    if not rootp.exists():
        return None
    candidates = [p for p in rootp.rglob("run_bundle*.json") if p.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def worst_tag(*tags: str | None) -> str | None:
    """Combine tag contributions: the worst (highest-severity) wins."""
    present = [t for t in tags if t in _TAG_SEVERITY]
    if not present:
        return None
    return max(present, key=lambda t: _TAG_SEVERITY[t])


def _fmt_causes(causes: Mapping[str, Any]) -> str:
    """``{'stale_76d_limit_60': 133, 'no_artifact': 9}`` -> stable text."""
    items = sorted(
        ((str(k), v) for k, v in causes.items()),
        key=lambda kv: (-(kv[1] if isinstance(kv[1], (int, float)) else 0), kv[0]),
    )
    return ", ".join(f"{k}={v}" for k, v in items)


# --- funnel_integrity.v1 rendering ---------------------------------------------

def summarize_funnel(block: Mapping[str, Any]) -> dict[str, Any]:
    """Reduce a ``funnel_integrity.v1`` block to tag + lead lines.

    Returns ``{tag, lines[], verdict, fired[], collapse_causes}``; tolerant of
    partial blocks (missing keys degrade to absent lines, never raise).
    """
    verdict = str(block.get("verdict") or "")
    tag = _FUNNEL_VERDICT_TO_TAG.get(verdict)
    lines: list[str] = []
    collapse_causes: dict[str, Any] = {}

    reason = block.get("verdict_reason")
    lines.append(f"funnel: {verdict or 'unknown'}" + (f" — {reason}" if reason else ""))

    fired = [f for f in (block.get("fired") or []) if isinstance(f, Mapping)]
    for finding in fired:
        invariant = str(finding.get("invariant") or "unknown")
        severity = str(finding.get("severity") or "?")
        f_reason = str(finding.get("reason") or "")
        evidence = finding.get("evidence")
        evidence = evidence if isinstance(evidence, Mapping) else {}
        if invariant == "universe_admission_collapse":
            causes = evidence.get("top_rejection_reasons")
            if isinstance(causes, Mapping):
                collapse_causes = dict(causes)
            n_admitted = evidence.get("n_admitted")
            n_watch = evidence.get("n_watchlist")
            head = f"universe collapse: {n_admitted}/{n_watch} admitted"
            if collapse_causes:
                head += f"; causes: {_fmt_causes(collapse_causes)}"
            # Lead with the collapse so ntfy truncation can never hide it.
            lines.insert(0, head)
        else:
            lines.append(f"fired[{severity}] {invariant}: {f_reason}")

    funnel = block.get("funnel")
    if isinstance(funnel, Mapping):
        lines.append(
            "counts: watchlist={w} admitted={a} candidates={c} buys={b} exits={e}".format(
                w=funnel.get("n_watchlist"), a=funnel.get("n_admitted"),
                c=funnel.get("n_candidates_final"), b=funnel.get("n_buy_orders"),
                e=funnel.get("n_exits"),
            )
        )
    if block.get("error"):
        lines.append(f"funnel-integrity error: {block['error']}")

    return {
        "tag": tag,
        "lines": lines,
        "verdict": verdict or None,
        "fired": [str(f.get("invariant") or "unknown") for f in fired],
        "collapse_causes": collapse_causes,
    }


# --- data_availability.v1 rendering --------------------------------------------

def summarize_data_availability(block: Mapping[str, Any]) -> dict[str, Any]:
    """Reduce a ``data_availability.v1`` block to tag + axis-failure lines."""
    verdict = str(block.get("verdict") or "")
    tag = _DATA_VERDICT_TO_TAG.get(verdict)
    lines: list[str] = []
    failed_axes: list[str] = []

    if verdict and verdict != "AVAILABLE":
        lines.append(f"data: {verdict}")

    for f in block.get("fired") or []:
        if not isinstance(f, Mapping):
            continue
        axis = str(f.get("axis") or "unknown")
        failed_axes.append(axis)
        policy = str(f.get("policy") or "?")
        reason = str(f.get("reason") or "")
        detail = ""
        axes = block.get("axes")
        axis_rec = axes.get(axis) if isinstance(axes, Mapping) else None
        if isinstance(axis_rec, Mapping):
            bits = []
            if axis_rec.get("age_days") is not None:
                bits.append(f"age={axis_rec['age_days']}d")
            if axis_rec.get("coverage") is not None:
                bits.append(f"coverage={axis_rec['coverage']}")
            if bits:
                detail = f" ({', '.join(bits)})"
        lines.append(f"axis {axis} [{policy}]: {reason}{detail}")

    missing_contracts = [str(m) for m in (block.get("missing_contracts") or [])]
    if missing_contracts:
        lines.append("undeclared axes: " + ", ".join(sorted(missing_contracts)))
    if block.get("error"):
        lines.append(f"data-availability error: {block['error']}")

    return {
        "tag": tag,
        "lines": lines,
        "verdict": verdict or None,
        "failed_axes": failed_axes,
        "missing_contracts": missing_contracts,
    }


# --- top-level builder ----------------------------------------------------------

def _first_truthy(*values: Any) -> str | None:
    for value in values:
        if value:
            return str(value)
    return None


def _counter_hints(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """Best-effort integer mirrors from the bundle's counters, if present."""
    for key in ("counters", "counters_json"):
        counters = bundle.get(key)
        if isinstance(counters, str):
            try:
                counters = json.loads(counters)
            except (ValueError, TypeError):
                counters = None
        if isinstance(counters, Mapping):
            return {k: counters[k] for k in _COUNTER_HINT_KEYS if k in counters}
    return {}


def build_outage_report(
    bundle: Mapping[str, Any] | None,
    *,
    run_id: str | None = None,
    as_of: str | None = None,
    now: datetime | None = None,
) -> OutageReport:
    """Render one run bundle's integrity blocks into an :class:`OutageReport`.

    Fail-soft: ``bundle=None`` or missing blocks produce a report with
    ``missing_blocks`` populated and (when both blocks are absent) no title
    tag / no alert — the monitor never invents a session verdict.
    """
    bundle = bundle if isinstance(bundle, Mapping) else {}

    funnel_block = bundle.get("funnel_integrity")
    data_block = bundle.get("data_availability")

    funnel = (
        summarize_funnel(funnel_block)
        if isinstance(funnel_block, Mapping) else {"tag": None, "lines": []}
    )
    data = (
        summarize_data_availability(data_block)
        if isinstance(data_block, Mapping) else {"tag": None, "lines": []}
    )

    missing = []
    if not isinstance(funnel_block, Mapping):
        missing.append("funnel_integrity")
    if not isinstance(data_block, Mapping):
        missing.append("data_availability")

    resolved_as_of = _first_truthy(
        as_of,
        funnel_block.get("date") if isinstance(funnel_block, Mapping) else None,
        data_block.get("date") if isinstance(data_block, Mapping) else None,
        bundle.get("as_of"),
        bundle.get("date"),
    ) or _today_iso(now)

    report = OutageReport(
        as_of=str(resolved_as_of),
        run_id=str(run_id or bundle.get("run_id") or f"{resolved_as_of}-outage-monitor"),
        funnel_summary={k: v for k, v in funnel.items() if k != "lines"},
        data_summary={k: v for k, v in data.items() if k != "lines"},
        missing_blocks=missing,
        counter_hints=_counter_hints(bundle),
    )

    tag = worst_tag(funnel.get("tag"), data.get("tag"))
    report.title_tag = tag
    report.body_lines = list(funnel.get("lines", [])) + list(data.get("lines", []))
    for name in missing:
        report.body_lines.append(f"block missing from run bundle: {name}")
    if missing and report.counter_hints:
        report.body_lines.append(
            "counters hint: " + _fmt_causes(report.counter_hints)
        )

    if tag is not None:
        report.title = f"RENQUANT-104 {tag} SESSION-INTEGRITY {report.as_of}"
    return report


# --- alert sink -----------------------------------------------------------------

def post_ntfy(title: str, body: str, topic: str, *, priority: int = 3, tags: str = "chart") -> None:
    """This monitor's alert seam: the canonical ``renquant_common.notify`` sender
    (honors ``RENQUANT_NO_NOTIFY``), priority scaled by the title tag."""
    _send_notification(title, body, topic, priority=priority, tags=tags)


def emit_alert(
    report: OutageReport,
    *,
    topic: str,
    quiet: bool = False,
    only_alerts: bool = False,
    poster: Callable[..., None] | None = None,
) -> bool:
    """Send the session-integrity page. Returns whether a notification fired.

    ``only_alerts=True`` restricts paging to OUTAGE/DEGRADED (for an eventual
    scheduled wiring that wants silence on clean sessions).
    """
    if quiet or report.title_tag is None or report.title is None:
        return False
    if only_alerts and report.title_tag not in (TAG_OUTAGE, TAG_DEGRADED):
        return False
    sender = poster or post_ntfy
    sender(
        report.title,
        report.body,
        topic,
        priority=report.priority,
        tags=_TAG_NTFY_TAGS.get(report.title_tag, "chart"),
    )
    return True


# --- CLI --------------------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="outage-monitor", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    src = parser.add_mutually_exclusive_group()
    src.add_argument("--run-bundle", default=None, help="path to a run_bundle.json")
    src.add_argument(
        "--bundle-dir", default=None,
        help="directory to search (recursively) for the latest run_bundle*.json",
    )
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--as-of", default=None, help="YYYY-MM-DD; defaults to the block/bundle date")
    parser.add_argument("--topic", default=os.environ.get("NTFY_TOPIC", "renquant"))
    parser.add_argument("--quiet", action="store_true", help="never send the ntfy page")
    parser.add_argument(
        "--only-alerts", action="store_true",
        help="notify only on OUTAGE/DEGRADED (silence clean TRADE/NO-TRADE sessions)",
    )
    parser.add_argument(
        "--require-blocks", action="store_true",
        help="exit 3 when the bundle carries neither integrity block",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    bundle_path: Path | None = None
    if args.run_bundle:
        bundle_path = Path(args.run_bundle)
    elif args.bundle_dir:
        bundle_path = find_latest_bundle(args.bundle_dir)
        if bundle_path is None:
            print(f"outage-monitor: no run_bundle*.json under {args.bundle_dir}", file=sys.stderr)
            return 3

    bundle = _load_json(bundle_path)
    if bundle_path is not None and bundle is None:
        print(f"outage-monitor: could not read bundle at {bundle_path}", file=sys.stderr)
        return 3

    report = build_outage_report(
        bundle if isinstance(bundle, Mapping) else None,
        run_id=args.run_id,
        as_of=args.as_of,
    )
    emit_alert(report, topic=args.topic, quiet=args.quiet, only_alerts=args.only_alerts)
    print(json.dumps(report.to_payload(), indent=2, sort_keys=True))

    if len(report.missing_blocks) == 2:
        return 3 if args.require_blocks else 0
    if report.title_tag == TAG_OUTAGE:
        return 2
    if report.title_tag == TAG_DEGRADED:
        return 1
    return 0


__all__ = [
    "OWNER_REPO",
    "SCHEMA_VERSION",
    "TAG_DEGRADED",
    "TAG_NO_TRADE",
    "TAG_OUTAGE",
    "TAG_TRADE",
    "OutageReport",
    "build_outage_report",
    "emit_alert",
    "find_latest_bundle",
    "main",
    "post_ntfy",
    "summarize_data_availability",
    "summarize_funnel",
    "worst_tag",
]


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
