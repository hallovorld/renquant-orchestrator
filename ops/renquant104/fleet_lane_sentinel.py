"""GOAL-1: the fleet e2e lanes have no watcher — this is it.

WHY (measured 2026-08-04): the shadow-scorer sentinel patrols IN-PROCESS
shadow_models[] entries (clf leg, momentum v0, momentum fast). The GOAL-9
FLEET lanes are a different animal: full e2e runs with their own broker tag,
state file and runs DB, executed as daily_104.sh Step 5/5b/5c/5d/5e. Nothing
watched them — and on their first evening the RCS lane fail-closed on an
invalid component kind, clearing 83 candidates, discovered ONLY because a
human read the log. A lane that fail-closes every session looks exactly like a
lane that runs fine, from the outside.

WHAT IT ALARMS ON (per session date):
  * ``FAIL_CLOSED``  — the lane ran and its scorer refused (the RCS shape):
    a record exists with zero candidates, or the lane log carries the
    fail-closed marker. Actionable.
  * ``MISSING``      — a non-dormant lane produced NO record at all.
    Actionable (the rail did not run, or its profile vanished).

WHAT STAYS QUIET (and why, so silence is never ambiguous):
  * ``DORMANT``      — the lane's PINNED profile still carries a
    ``*_pending_first_artifact`` marker: its component genuinely does not
    exist yet (fast-momentum lanes before the Saturday genesis). Quiet BY
    DECLARATION, and the declaration is the pinned config, not this file.
  * ``RECORDED``     — the lane produced a decision record (trade or
    honest no-trade). Reported, not alarmed.

The dormancy source is deliberately the PINNED profile: a lane cannot be
silenced by editing this sentinel, only by the reviewed config that also
governs what the lane serves.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path

REPO = Path(os.environ.get("RENQUANT_REPO_ROOT",
                           "/Users/renhao/git/github/RenQuant"))
PINNED_CONFIGS = REPO / ".subrepo_runtime/repos/renquant-strategy-104/configs"
DATA = REPO / "data"
LOGS = REPO / "logs/daily_104"

FAIL_CLOSED_MARKERS = (
    "panel_scorer_load_failed",
    "panel_scoring_fail_closed",
)

STATE_RECORDED = "RECORDED"
STATE_FAIL_CLOSED = "FAIL_CLOSED"
STATE_MISSING = "MISSING"
STATE_DORMANT = "DORMANT"
ACTIONABLE = (STATE_FAIL_CLOSED, STATE_MISSING)


@dataclass(frozen=True)
class FleetLane:
    callsign: str
    tag: str
    profile: str
    log_stem: str


#: The fleet as served (callsigns per live/runner.py LANE_CALLSIGNS).
FLEET = (
    FleetLane("RC",  "alpaca_shadow_blend",           "strategy_config.shadow_blend.json",              "shadow_blend"),
    FleetLane("RSs", "alpaca_shadow_blend_mom",       "strategy_config.shadow_blend_momentum.json",     "shadow_blend_mom"),
    FleetLane("Rf",  "alpaca_shadow_blend_mom_fast",  "strategy_config.shadow_blend_momentum_fast.json","shadow_blend_mom_fast"),
    FleetLane("RCS", "alpaca_shadow_blend_rb_mom",    "strategy_config.shadow_blend_rb_mom.json",       "shadow_blend_rb_mom"),
    FleetLane("RCf", "alpaca_shadow_blend_rb_fast",   "strategy_config.shadow_blend_rb_fast.json",      "shadow_blend_rb_fast"),
)


def lane_is_dormant(lane: FleetLane, configs_dir: Path = PINNED_CONFIGS) -> bool:
    """True when the PINNED profile declares a pending-first-artifact component.

    Absent profile → NOT dormant: a lane whose rail exists but whose profile
    vanished is a real problem, and calling that 'dormant' would be exactly the
    silence this sentinel exists to remove.
    """
    path = configs_dir / lane.profile
    if not path.exists():
        return False
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    comps = (((cfg.get("ranking") or {}).get("panel_scoring") or {})
             .get("components") or [])
    for comp in comps:
        if isinstance(comp, dict) and any(
            k.endswith("_pending_first_artifact") for k in comp
        ):
            return True
    return False


def _lane_record(lane: FleetLane, date: str, data_dir: Path = DATA) -> dict | None:
    """The lane's own runs-DB row for ``date``, or None. Read-only, immutable."""
    db = data_dir / f"runs.{lane.tag}.db"
    if not db.exists():
        return None
    try:
        con = sqlite3.connect(f"file://{db}?immutable=1", uri=True)
        row = con.execute(
            "SELECT run_id, n_candidates, n_buys, n_exits FROM pipeline_runs "
            "WHERE run_date=? ORDER BY created_at DESC LIMIT 1", (date,)
        ).fetchone()
        con.close()
    except sqlite3.Error:
        return None
    if not row:
        return None
    return {"run_id": row[0], "n_candidates": row[1] or 0,
            "n_buys": row[2] or 0, "n_exits": row[3] or 0}


def _log_says_fail_closed(lane: FleetLane, date: str, logs_dir: Path = LOGS) -> bool:
    log = logs_dir / f"{date}_{lane.log_stem}.log"
    if not log.exists():
        return False
    try:
        text = log.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return any(m in text for m in FAIL_CLOSED_MARKERS)


def classify(lane: FleetLane, date: str, *, configs_dir: Path = PINNED_CONFIGS,
             data_dir: Path = DATA, logs_dir: Path = LOGS) -> tuple[str, str]:
    """(state, human detail). Dormancy is checked FIRST and only from config."""
    if lane_is_dormant(lane, configs_dir):
        return STATE_DORMANT, "pinned profile declares a pending-first-artifact component"
    rec = _lane_record(lane, date, data_dir)
    marker = _log_says_fail_closed(lane, date, logs_dir)

    # RECORD-FIRST, marker second. MEASURED 2026-08-04 while running this
    # sentinel against the very incident it was written for: the lane
    # fail-closed at 21:02, was fixed, and re-ran healthy at 22:02 — but the
    # session's log still carried the earlier run's marker, so a
    # marker-first rule kept alarming on an already-repaired lane. A watcher
    # that cannot see a repair trains its reader to ignore it.
    #
    # The DB record is per-run and latest-wins; it is the stronger evidence of
    # CURRENT state. The log marker's real job is the case the record cannot
    # express: a lane that fail-closed WITHOUT leaving a usable record.
    if rec is not None and rec["n_candidates"] > 0:
        detail = (f"{rec['run_id']}: candidates={rec['n_candidates']} "
                  f"buys={rec['n_buys']} exits={rec['n_exits']}")
        if marker:
            detail += (" — note: an EARLIER run this session left a fail-closed "
                       "marker; the latest run is healthy and supersedes it")
        return STATE_RECORDED, detail
    if rec is not None:  # record exists but scored nothing
        return STATE_FAIL_CLOSED, (
            f"record {rec['run_id']} scored ZERO candidates — the lane ran but "
            "produced no decision surface"
            + ("; lane log carries a scorer fail-closed marker" if marker else "")
        )
    if marker:
        return STATE_FAIL_CLOSED, (
            "lane log carries a scorer fail-closed marker and NO record exists "
            "— the lane refused before it could write one"
        )
    return STATE_MISSING, "no runs-DB record for this session and the lane is not dormant"


def patrol(date: str, **kw) -> tuple[list[str], list[str]]:
    """(alarm lines, info lines)."""
    alarms: list[str] = []
    info: list[str] = []
    for lane in FLEET:
        state, detail = classify(lane, date, **kw)
        line = f"[{state}] {lane.callsign} ({lane.tag}): {detail}"
        (alarms if state in ACTIONABLE else info).append(line)
    return alarms, info


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--date", default=dt.date.today().isoformat())
    args = ap.parse_args(argv)
    alarms, info = patrol(args.date)
    for line in info:
        print(line)
    for line in alarms:
        print(line)
    if alarms:
        print(f"\nFLEET SENTINEL: {len(alarms)} actionable lane state(s) on {args.date}")
        return 1
    print(f"\nFLEET SENTINEL: all {len(FLEET)} lanes accounted for on {args.date}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
