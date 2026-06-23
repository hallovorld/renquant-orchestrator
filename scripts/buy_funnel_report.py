#!/usr/bin/env python3
"""Read-only buy-funnel diagnostic — where does the renquant-104 daily run lose candidates?

The account sits under-deployed (the 2026-06-03 cash-drag study: "5 weeks, 4 buys, ~70-80%
cash"). The committed Phase-A question is *where in the buy funnel the candidates die* — but
the funnel is recorded only in the `logs/live_e2e/*.log` files (the structured `pipeline_runs`
table carries no funnel counters, and only sim runs). This parses those logs into a structured
per-run funnel + identifies the BINDING constraint, so the operator can decide which lever
(P-WF-GATE flicker, VetoWeakBuys floor, Kelly mu gate, ...) actually gates deployment — with
data, not a guess.

100% READ-ONLY: it parses logs only; it places no orders and changes no state. Parsing is
defensive — a missing stage is reported as None rather than crashing.

Stages (from the real run logs):
  Phase 2b (buy scan): N candidates          -> panel_candidates
  RealizedVolGateTask: dropped X/Y           -> vol_gate_dropped (Y == panel)
  VetoWeakBuysTask: dropped Z                 -> veto_weak_dropped (the rank-floor cut)
  mu_le_min_edge=K                            -> kelly_mu_below_edge
  ApplyKellySizingTask: ... cands=N non-zero  -> kelly_sized (final sized buy candidates)
  preflight ✗ P-WF-GATE                       -> wf_gate_blocked (HARD: 0 buys regardless)

Usage:
    buy_funnel_report.py [--log-dir DIR] [--last N] [--json]
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

DEFAULT_LOG_DIR = Path("/Users/renhao/git/github/RenQuant/logs/live_e2e")

_PAT = {
    "panel_candidates": re.compile(r"Phase 2b \(buy scan\): (\d+) candidates"),
    "vol_gate_dropped": re.compile(r"RealizedVolGateTask: dropped (\d+)/(\d+)"),
    "veto_weak_dropped": re.compile(r"VetoWeakBuysTask: dropped (\d+)"),
    "kelly_mu_below_edge": re.compile(r"mu_le_min_edge=(\d+)"),
    "kelly_sized": re.compile(r"ApplyKellySizingTask:.*?cands=(\d+) non-zero"),
    "wf_gate_blocked": re.compile(r"preflight .? P-WF-GATE"),
}


def _last(pattern: re.Pattern, text: str, group: int = 1):
    """Last match of `group` as int, or None. (Last = the final run if a log has retries.)"""
    matches = pattern.findall(text)
    if not matches:
        return None
    val = matches[-1]
    val = val[group - 1] if isinstance(val, tuple) else val
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def parse_funnel(text: str) -> dict:
    """Parse one run log into a structured funnel + the binding constraint."""
    panel = _last(_PAT["panel_candidates"], text)
    vol_dropped = _last(_PAT["vol_gate_dropped"], text)
    veto_dropped = _last(_PAT["veto_weak_dropped"], text)
    mu_below = _last(_PAT["kelly_mu_below_edge"], text)
    kelly_sized = _last(_PAT["kelly_sized"], text)
    wf_blocked = bool(_PAT["wf_gate_blocked"].search(text))

    after_vol = (panel - vol_dropped) if (panel is not None and vol_dropped is not None) else None
    after_veto = (after_vol - veto_dropped) if (after_vol is not None and veto_dropped is not None) else None
    actual_buys = 0 if wf_blocked else kelly_sized

    # Binding constraint: the HARD block wins; else the single stage that dropped the most.
    drops = {
        "RealizedVolGate": vol_dropped,
        "VetoWeakBuys (rank floor)": veto_dropped,
        "Kelly mu<edge": mu_below,
    }
    drops = {k: v for k, v in drops.items() if v}
    if wf_blocked:
        binding = "P-WF-GATE (HARD block -> 0 buys)"
    elif drops:
        binding = max(drops, key=drops.get)
    else:
        binding = "unknown (incomplete log)"

    return {
        "panel_candidates": panel,
        "vol_gate_dropped": vol_dropped,
        "after_vol_gate": after_vol,
        "veto_weak_dropped": veto_dropped,
        "after_veto_weak": after_veto,
        "kelly_mu_below_edge": mu_below,
        "kelly_sized": kelly_sized,
        "wf_gate_blocked": wf_blocked,
        "actual_buys": actual_buys,
        "binding_constraint": binding,
    }


def report(log_dir: Path, last: int) -> dict:
    logs = sorted(Path(log_dir).glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)[:last]
    runs = []
    for p in logs:
        try:
            f = parse_funnel(p.read_text(errors="replace"))
        except Exception as exc:  # pragma: no cover - defensive
            f = {"binding_constraint": f"parse-error: {exc}"}
        f["log"] = p.name
        runs.append(f)
    binding_counts = Counter(r.get("binding_constraint") for r in runs if r.get("panel_candidates") is not None)
    return {"log_dir": str(log_dir), "n_runs": len(runs), "runs": runs,
            "binding_constraint_frequency": dict(binding_counts)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--log-dir", default=str(DEFAULT_LOG_DIR))
    ap.add_argument("--last", type=int, default=15)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    res = report(Path(a.log_dir), a.last)
    if a.json:
        print(json.dumps(res, indent=2))
        return 0
    print(f"buy-funnel — {res['n_runs']} run(s) from {res['log_dir']}")
    print(f"{'log':40} {'panel':>6} {'>vol':>6} {'>veto':>6} {'sized':>6} {'buys':>5}  binding")
    for r in res["runs"]:
        print(f"{r.get('log','?')[:40]:40} {str(r.get('panel_candidates')):>6} "
              f"{str(r.get('after_vol_gate')):>6} {str(r.get('after_veto_weak')):>6} "
              f"{str(r.get('kelly_sized')):>6} {str(r.get('actual_buys')):>5}  {r.get('binding_constraint')}")
    print("\nbinding-constraint frequency:")
    for k, v in sorted(res["binding_constraint_frequency"].items(), key=lambda kv: -kv[1]):
        print(f"  {v:>3}x  {k}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
