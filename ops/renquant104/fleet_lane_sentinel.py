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

# The PROD lane runs FIRST in the daily wrapper; every fleet lane is a later
# step. So prod's own runs-DB row is the evidence that the SESSION happened at
# all, and it is what separates "this lane failed to record" from "nobody has
# run yet". [GOAL-1, measured 2026-08-05 03:45 PT: nine hours before the daily
# run, this sentinel reported 3 ACTIONABLE lanes on a day nothing had run.]
PROD_TAG = "alpaca"

STATE_RECORDED = "RECORDED"
STATE_FAIL_CLOSED = "FAIL_CLOSED"
STATE_MISSING = "MISSING"
STATE_DORMANT = "DORMANT"
STATE_NOT_YET_RUN = "NOT_YET_RUN"
STATE_PROFILE_DEFECT = "PROFILE_DEFECT"
ACTIONABLE = (STATE_FAIL_CLOSED, STATE_MISSING, STATE_PROFILE_DEFECT)

SESSION_STARTED = "started"
SESSION_NOT_STARTED = "not_started"
SESSION_UNKNOWN = "unknown"


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


class DbUnreadable(Exception):
    """The DB exists but could not be read. NOT the same as 'no row'."""


def _tag_record(tag: str, date: str, data_dir: Path = DATA) -> dict | None:
    """A broker tag's runs-DB row for ``date``, or None. Read-only, immutable.

    Raises ``DbUnreadable`` when the file exists but cannot be queried — folding
    that into ``None`` is what let "cannot read the evidence" masquerade as
    "there is no evidence" [codex on orch#811].
    """
    db = data_dir / f"runs.{tag}.db"
    if not db.exists():
        return None
    try:
        con = sqlite3.connect(f"file://{db}?immutable=1", uri=True)
        row = con.execute(
            "SELECT run_id, n_candidates, n_buys, n_exits FROM pipeline_runs "
            "WHERE run_date=? ORDER BY created_at DESC LIMIT 1", (date,)
        ).fetchone()
        con.close()
    except sqlite3.Error as exc:
        raise DbUnreadable(f"{db.name}: {exc}") from exc
    if not row:
        return None
    return {"run_id": row[0], "n_candidates": row[1] or 0,
            "n_buys": row[2] or 0, "n_exits": row[3] or 0}


def _lane_record(lane: FleetLane, date: str, data_dir: Path = DATA) -> dict | None:
    """A lane's row, or None. An unreadable lane DB is treated as NO record —
    the lane then falls through to the MISSING/NOT_YET_RUN decision, which is
    made on PROD evidence, never on this one."""
    try:
        return _tag_record(lane.tag, date, data_dir)
    except DbUnreadable:
        return None


def profile_defect(lane: FleetLane, configs_dir: Path | None = None) -> str | None:
    """A reason string when the lane's PINNED profile is UNUSABLE, else None.

    A CONFIG defect is true independently of whether any session ran — the daily
    wrapper will skip or fail that rail whenever it next runs. Downgrading one to
    NOT_YET_RUN erased the pre-session detection case this sentinel exists for
    [codex on orch#811].

    EXISTENCE IS NOT ENOUGH [codex on orch#812]. The wrapper gates these lanes on
    file existence alone (`daily_104.sh`) and then hands the path to the runner,
    whose loader hard-parses it with `json.loads`
    (`renquant_strategy_104/config.py`). So a malformed profile is a real
    pre-session failure, not a hypothetical one, and checking only `exists()`
    silenced it until the session ran.
    """
    path = (configs_dir or PINNED_CONFIGS) / lane.profile
    if not path.exists():
        return (f"the pinned profile {lane.profile} does not exist — the daily "
                f"wrapper will skip this rail on its next run")
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        return (f"the pinned profile {lane.profile} could not be read ({exc}) — "
                f"the runner's loader will fail on it")
    except ValueError as exc:
        return (f"the pinned profile {lane.profile} is not valid JSON ({exc}) — "
                f"the runner's loader hard-parses it and will fail on it")
    if not isinstance(cfg, dict):
        return (f"the pinned profile {lane.profile} is not a JSON object — "
                f"the runner's loader will fail on it")
    return None


def session_state(date: str, data_dir: Path | None = None) -> str:
    """``started`` | ``not_started`` | ``unknown`` for the daily session.

    Evidence: the PROD lane's own runs-DB row. Prod runs first in the wrapper
    and every fleet lane is a later step (verified against `daily_104.sh`), so
    no prod row means no session — and a lane never asked to run has not failed.

    THREE states, not two [codex on orch#811]. An unreadable/corrupt prod DB is
    ``unknown``, and ``unknown`` NEVER downgrades a lane: folding "cannot read
    the evidence" into "there is no evidence" is exactly the silencer this state
    was supposed to avoid becoming.

    Known weakness, stated rather than hidden: the prod row is written LATE in
    `RunnerAdapter.commit()`, after state save and order application, so a
    session that died mid-flight can leave no prod row. That is why ``unknown``
    exists and why a lane with its OWN evidence (a record, or a fail-closed
    marker) is always judged on that first.
    """
    try:
        return (SESSION_STARTED if _tag_record(PROD_TAG, date, data_dir or DATA)
                else SESSION_NOT_STARTED)
    except DbUnreadable:
        return SESSION_UNKNOWN


def session_started(date: str, data_dir: Path | None = None) -> bool:
    """Back-compat convenience: True only for a positively observed session."""
    return session_state(date, data_dir) == SESSION_STARTED


def _log_says_fail_closed(lane: FleetLane, date: str, logs_dir: Path = LOGS) -> bool:
    log = logs_dir / f"{date}_{lane.log_stem}.log"
    if not log.exists():
        return False
    try:
        text = log.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return any(m in text for m in FAIL_CLOSED_MARKERS)


def classify(lane: FleetLane, date: str, *, configs_dir: Path | None = None,
             data_dir: Path | None = None,
             logs_dir: Path | None = None) -> tuple[str, str]:
    """(state, human detail). Dormancy is checked FIRST and only from config.

    Directories resolve at CALL time, not at import: binding them as parameter
    defaults meant `main()` always read the real tree, so a redirected run (an
    env override, a test) silently measured production instead. Found while
    writing the NOT_YET_RUN test, which passed against the live data dir.
    """
    configs_dir = configs_dir or PINNED_CONFIGS
    data_dir = data_dir or DATA
    logs_dir = logs_dir or LOGS
    defect = profile_defect(lane, configs_dir)
    if defect:
        # A config defect is true whether or not anything ran today, so it is
        # checked BEFORE dormancy and BEFORE the session state, and is never
        # downgraded by either.
        return STATE_PROFILE_DEFECT, defect
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
    state = session_state(date, data_dir)
    if state == SESSION_NOT_STARTED:
        return STATE_NOT_YET_RUN, (
            "the daily session has not run yet on this date (no PROD runs-DB "
            "row either) — a lane that was never asked to run has not failed")
    if state == SESSION_UNKNOWN:
        return STATE_MISSING, (
            "no runs-DB record for this session, and the PROD runs-DB could "
            "NOT BE READ — an unreadable evidence source is not evidence of a "
            "session that never started, so this stays actionable")
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
    if session_state(args.date) == SESSION_NOT_STARTED:
        # Say it out loud. A silent all-clear on a date nothing ran is the same
        # ambiguity this state was added to remove, one level up.
        print(f"\nFLEET SENTINEL: the daily session has NOT RUN on {args.date} "
              f"(no PROD runs-DB row) — nothing to account for yet")
        return 0
    print(f"\nFLEET SENTINEL: all {len(FLEET)} lanes accounted for on {args.date}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
