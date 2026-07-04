"""Run-over-run scorer-identity diff alarm for renquant_104 (PR #274 monitoring gap).

WHY. On 2026-06-26 prod silently rolled back from the operator-promoted
2026-06-21 XGB panel to the 2026-05-18 model (the 06-25 live-tree recovery
checkout restored the committed blob) and ran the rolled-back scorer for a
week undetected (``doc/research/2026-07-03-raw-jump-0626-diagnosis.md`` §4-ii).
The only alarm covering the surface -- the PSI raw-score drift audit -- was
SATURATED: every one of its 247 rows since birth was CRITICAL-severity and it
had minted 8 near-identical incidents in 10 days, so a genuine scorer-identity
event carried zero information. The gap the diagnosis names: identity fields
exist in every run bundle but nothing diffs them run-over-run. This monitor is
that diff.

WHAT. Reads the canonical run bundles (``pipeline_runs.run_bundle_json``, DB
opened strictly read-only via ``mode=ro``) for the recent canonical runs,
extracts a scorer-identity tuple per lane, and diffs consecutive runs:

- ``prod_panel``  -- ``artifact_hashes["panel"]`` (the stamped artifact file
  sha256) + ``panel_contract.details.trained_date`` + the booster CONTENT hash
  (sha256 of the artifact's ``booster_raw_json``, resolved by matching the
  stamped file sha against on-disk prod/staging/rollback copies). The booster
  hash is enrichment/attribution only -- fingerprint re-stamps change the file
  sha but not the booster, so it collapses the file zoo into true model
  families exactly as the diagnosis's artifact archaeology did.
- ``calibrator``  -- ``artifact_hashes["global_calibration"]``. The 06-25
  recovery swapped the calibrator at the same boundary; a silent calibrator
  swap is the same class of event (the mu transfer curve must stay bound to
  the scorer it was fit against).
- ``shadow_models[i]`` -- each stamped shadow-lane artifact hash, where stamped.

Any lane change between consecutive runs is a BOUNDARY. A boundary must be
legitimized by a recorded promote/rollback event on the boundary's calendar
window (dates from FILENAMES, never mtime -- the prod artifacts dir has been
observed bulk-touched, so mtimes are not evidence):

- prod/calibrator lanes: weekly/monthly promote-chain records under
  ``artifacts/prod`` (``<family>.weekly_<TS>.staging.json``,
  ``<family>.{weekly,monthly}_rollback_<date>.json``) and dated weekly-promote
  logs (``logs/weekly_wf_promote/<date>.log``), family-matched to the lane.
- shadow lanes: persisted promotion receipts
  (``logs/promote_shadow_patchtst/*.json``, umbrella #419), or an explained
  ``prod_panel`` change at the same boundary (a recorded promotion swaps the
  prod and shadow lanes atomically).

Unexplained boundary => CRITICAL, exit 1, ntfy (behind ``--notify``) carrying
BOTH identities. Explained boundary => INFO line, exit 0.

Separate WARN (exit 2; never masks a CRITICAL): the newest run's served
``trained_date`` is more than ``--max-trained-age-days`` (default 28) old --
the 2026-06-30 operator freshness directive
(``doc/design/2026-06-30-model-freshness-governance.md`` / RFC #210: no model
older than 28 days). Note the deliberate asymmetry with the umbrella #423
doctrine ("``trained_date`` never certifies freshness"): this check only ever
flags STALE. ``trained_date`` is an upper bound on the model's data exposure,
so a ``trained_date`` beyond the cap proves staleness, while a recent one
proves nothing and never reads healthy here. Deep freshness
(data-cutoff-keyed, per-population policies) remains
``model_freshness_monitor``'s job; this WARN covers the one thing that monitor
cannot see: the identity a RUN actually served, as stamped in its own bundle
(the 05-18 model read "normal" on disk precisely because nothing checked what
the runs were serving).

SATURATION IMMUNITY. The alarm is edge-triggered: it fires only when the
identity CHANGES between consecutive runs. A stable identity -- however wrong
or old -- never fires it (staleness is the separate WARN above), so it
definitionally cannot saturate the way the level-triggered PSI alarm did. An
unexplained boundary keeps alerting on each scheduled check until it ages out
of ``--lookback-days`` or a legitimizing record appears: bounded,
page-until-acknowledged persistence, still edge-triggered.

FAIL-CLOSED. A missing/unreadable DB, fewer than two canonical runs to diff,
or any bundle in the window without a stamped prod-panel identity fails closed
to CRITICAL: "cannot verify scorer-identity continuity" is exactly the blind
spot this monitor exists to close, never a pass.

Exit codes: 0 = ok (stable, or all boundaries explained); 1 = CRITICAL
(unexplained identity change, or fail-closed); 2 = WARN only (served
trained_date over the freshness cap).

Backfill mode: ``--backfill N`` replays the last N canonical runs' bundles and
prints the identity timeline (segments + boundary verdicts); reporting only,
always exit 0.

OBSERVE-ONLY / READ-ONLY: opens the runs DB ``mode=ro``, reads artifact bytes,
writes nothing but stdout/stderr and (behind ``--notify``) an ntfy POST. It
never trains, promotes, restores, or changes any pin.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
from typing import Any

from .runtime_paths import default_repo_root
from renquant_common.notify import send as post_ntfy  # canonical sender (campaign B6)
from .weekly_promote_monitor import (
    PROD_ARTIFACTS_SUBDIR,
    PROMOTE_LOG_SUBDIR,
    classify_promote_log,
)


SCHEMA_VERSION = 1
OWNER_REPO = "renquant-orchestrator"

DEFAULT_REPO_ROOT = default_repo_root()
DEFAULT_DB_SUBPATH = ("data", "runs.alpaca.db")
# Persisted shadow promotion receipts (umbrella #419 / RFC #212 §5), written by
# scripts/promote_shadow_patchtst.py as <UTC-TS>.json with a "promoted_at" field.
SHADOW_RECEIPT_SUBDIR = ("logs", "promote_shadow_patchtst")

DEFAULT_RUN_TYPE = "live"
DEFAULT_STRATEGY = "renquant-104"
# Boundary alert window, anchored on the NEWEST run's created_at (never wall
# clock, so a stalled pipeline does not slide the window empty). One extra run
# BEFORE the window is always kept as the diff base for the window's first run.
DEFAULT_LOOKBACK_DAYS = 5
# 2026-06-30 operator model-freshness directive (#210): no served model older
# than 28 days.
DEFAULT_MAX_TRAINED_AGE_DAYS = 28
DEFAULT_BACKFILL_RUNS = 200
DEFAULT_NTFY_TOPIC = "renquant"

LANE_PROD = "prod_panel"
LANE_CALIBRATOR = "calibrator"

# Run-bundle ``artifact_hashes`` / ``artifact_paths`` are FLAT dicts whose keys
# are dotted config paths (e.g. "ranking.panel_scoring.shadow_models[0]
# .artifact_path"), not nested objects.
_PANEL_HASH_KEYS = ("panel", "ranking.panel_scoring.artifact_path")
_CALIBRATOR_HASH_KEY = "global_calibration"
_SHADOW_KEY_RE = re.compile(r"shadow_models\[\d+\]")
_SHA_PREFIX = "sha256:"

# Which promote-record families legitimize which lane. Promote logs carry no
# family and count for both prod-chain lanes.
_LANE_FAMILY_PREFIXES = {
    LANE_PROD: ("panel-ltr",),
    LANE_CALIBRATOR: ("panel-rank-calibration",),
}

_STAGING_NAME_RE = re.compile(
    r"^(?P<family>.+)\.weekly_(?P<ts>\d{8}T\d{6}Z)\.staging\.json$"
)
_ROLLBACK_NAME_RE = re.compile(
    r"^(?P<family>.+)\.(?P<cadence>weekly|monthly)_rollback_(?P<date>\d{4}-\d{2}-\d{2})\.json$"
)
_PROMOTE_LOG_NAME_RE = re.compile(r"^(?P<date>\d{4}-\d{2}-\d{2})\.log$")
_RECEIPT_NAME_RE = re.compile(r"^(?P<date>\d{4}-\d{2}-\d{2})T\d{6}Z\.json$")

STATUS_OK = "ok"
STATUS_WARN = "warn"
STATUS_CRITICAL = "critical"
_STATUS_EXIT_CODE = {STATUS_OK: 0, STATUS_CRITICAL: 1, STATUS_WARN: 2}


def _short(sha: str | None) -> str:
    if not sha:
        return "?"
    return sha.removeprefix(_SHA_PREFIX)[:12]


def _norm_sha(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    return value.removeprefix(_SHA_PREFIX)


def _parse_created_at(value: object) -> datetime:
    """Parse the runs DB ``created_at`` (naive ``YYYY-MM-DD HH:MM:SS`` = UTC)."""
    parsed = datetime.fromisoformat(str(value).replace(" ", "T").replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _parse_iso_date(value: object) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


# --- identity extraction -----------------------------------------------------


@dataclass(frozen=True)
class LaneIdentity:
    lane: str
    artifact_sha: str | None
    trained_date: str | None = None
    booster_sha: str | None = None
    artifact_path: str | None = None

    def key(self) -> tuple:
        """Change-detection key. The booster hash is deliberately NOT part of
        it: it is derived from the artifact bytes (same file sha => same
        booster) and may be unresolvable for artifacts whose bytes are gone,
        so keying on it would turn a resolution failure into a phantom
        change."""
        return (self.artifact_sha, self.trained_date)

    def describe(self) -> str:
        parts = [_short(self.artifact_sha)]
        if self.trained_date:
            parts.append(f"trained {self.trained_date}")
        if self.booster_sha:
            parts.append(f"booster {_short(self.booster_sha)}")
        return f"{parts[0]} ({', '.join(parts[1:])})" if len(parts) > 1 else parts[0]

    def as_dict(self) -> dict[str, Any]:
        return {
            "lane": self.lane,
            "artifact_sha256": self.artifact_sha,
            "trained_date": self.trained_date,
            "booster_sha256": self.booster_sha,
            "artifact_path": self.artifact_path,
        }


# Sentinel identity for a lane that a bundle stopped (or started) stamping.
_ABSENT = "(lane not stamped)"


def _absent_lane(lane: str) -> LaneIdentity:
    return LaneIdentity(lane=lane, artifact_sha=_ABSENT)


@dataclass
class RunIdentity:
    run_id: str
    run_date: str
    created_at: datetime
    lanes: dict[str, LaneIdentity]
    usable: bool
    problem: str | None = None

    def identity_key(self) -> tuple:
        return tuple(sorted((name, lane.key()) for name, lane in self.lanes.items()))


class BoosterResolver:
    """Resolve a stamped panel-artifact file sha to its booster CONTENT hash.

    Scans the prod artifacts dir's JSON copies (current prod + weekly staging +
    rollback backups) once, hashing file bytes; a stamped sha that matches a
    copy resolves to sha256 of that copy's ``booster_raw_json``. Read-only;
    every failure resolves to ``None`` (enrichment, never a gate)."""

    def __init__(self, prod_dir: Path) -> None:
        self._prod_dir = prod_dir
        self._path_by_file_sha: dict[str, Path] | None = None
        self._booster_by_stamped: dict[str, str | None] = {}

    def _scan(self) -> dict[str, Path]:
        if self._path_by_file_sha is not None:
            return self._path_by_file_sha
        found: dict[str, Path] = {}
        try:
            candidates = sorted(self._prod_dir.glob("*.json"))
        except OSError:
            candidates = []
        for path in candidates:
            try:
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
            except OSError:
                continue
            found.setdefault(digest, path)
        self._path_by_file_sha = found
        return found

    def resolve(self, stamped_sha: str | None) -> str | None:
        stamped = _norm_sha(stamped_sha)
        if stamped is None:
            return None
        if stamped in self._booster_by_stamped:
            return self._booster_by_stamped[stamped]
        booster: str | None = None
        path = self._scan().get(stamped)
        if path is not None:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                raw = payload.get("booster_raw_json") if isinstance(payload, dict) else None
                if isinstance(raw, str) and raw:
                    booster = hashlib.sha256(raw.encode("utf-8")).hexdigest()
            except (OSError, json.JSONDecodeError, UnicodeDecodeError):
                booster = None
        self._booster_by_stamped[stamped] = booster
        return booster


def extract_identity(
    *,
    run_id: str,
    run_date: str,
    created_at: datetime,
    bundle_raw: object,
    booster_resolver: BoosterResolver | None = None,
) -> RunIdentity:
    """Extract the per-lane scorer identity from one run bundle. Fail-closed:
    a missing/unparseable bundle or a bundle without a stamped prod-panel hash
    yields ``usable=False`` (the caller escalates)."""

    def _unusable(problem: str) -> RunIdentity:
        return RunIdentity(run_id, run_date, created_at, {}, usable=False, problem=problem)

    if not bundle_raw:
        return _unusable("empty run_bundle_json")
    try:
        bundle = json.loads(bundle_raw) if isinstance(bundle_raw, (str, bytes)) else bundle_raw
    except (json.JSONDecodeError, TypeError, ValueError):
        return _unusable("unparseable run_bundle_json")
    if not isinstance(bundle, dict):
        return _unusable("run_bundle_json is not an object")

    hashes = bundle.get("artifact_hashes")
    paths = bundle.get("artifact_paths")
    hashes = hashes if isinstance(hashes, dict) else {}
    paths = paths if isinstance(paths, dict) else {}

    panel_sha = None
    panel_key = None
    for key in _PANEL_HASH_KEYS:
        panel_sha = _norm_sha(hashes.get(key))
        if panel_sha is not None:
            panel_key = key
            break
    if panel_sha is None:
        return _unusable("no stamped prod panel artifact hash in run bundle")

    contract = bundle.get("panel_contract")
    details = contract.get("details") if isinstance(contract, dict) else None
    trained = details.get("trained_date") if isinstance(details, dict) else None
    trained_date = str(trained) if trained else None

    lanes: dict[str, LaneIdentity] = {
        LANE_PROD: LaneIdentity(
            lane=LANE_PROD,
            artifact_sha=panel_sha,
            trained_date=trained_date,
            booster_sha=booster_resolver.resolve(panel_sha) if booster_resolver else None,
            artifact_path=str(paths.get(panel_key) or paths.get("panel") or "") or None,
        )
    }

    calibrator_sha = _norm_sha(hashes.get(_CALIBRATOR_HASH_KEY))
    if calibrator_sha is not None:
        lanes[LANE_CALIBRATOR] = LaneIdentity(
            lane=LANE_CALIBRATOR,
            artifact_sha=calibrator_sha,
            artifact_path=str(paths.get(_CALIBRATOR_HASH_KEY) or "") or None,
        )

    for key in sorted(hashes):
        match = _SHADOW_KEY_RE.search(key)
        if match is None:
            continue
        lane_name = match.group(0)
        lanes[lane_name] = LaneIdentity(
            lane=lane_name,
            artifact_sha=_norm_sha(hashes.get(key)),
            artifact_path=str(paths.get(key) or "") or None,
        )

    return RunIdentity(run_id, run_date, created_at, lanes, usable=True)


# --- canonical run loading ---------------------------------------------------


def load_canonical_runs(
    db_path: Path,
    *,
    run_type: str = DEFAULT_RUN_TYPE,
    strategy: str = DEFAULT_STRATEGY,
    limit: int,
) -> list[tuple[str, str, str, str | None]]:
    """Return the last ``limit`` canonical runs, CHRONOLOGICAL order, as raw
    ``(run_id, run_date, created_at, run_bundle_json)`` rows. Strictly
    read-only (URI ``mode=ro``). Raises ``FileNotFoundError``/``sqlite3.Error``
    for the caller to fail closed on."""
    if not db_path.exists():
        raise FileNotFoundError(str(db_path))
    uri = f"file:{db_path}?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        rows = conn.execute(
            """SELECT run_id, run_date, created_at, run_bundle_json
                 FROM pipeline_runs
                WHERE run_type = ? AND strategy = ?
             ORDER BY created_at DESC, run_id DESC
                LIMIT ?""",
            (run_type, strategy, int(limit)),
        ).fetchall()
    return list(reversed(rows))


def _window_runs(runs: list[RunIdentity], lookback_days: int) -> list[RunIdentity]:
    """Runs within ``lookback_days`` of the NEWEST run's created_at, plus one
    preceding run as the diff base for the window's first run."""
    if not runs:
        return []
    cutoff = runs[-1].created_at - timedelta(days=lookback_days)
    windowed = [r for r in runs if r.created_at >= cutoff]
    n_before = len(runs) - len(windowed)
    if n_before > 0:
        windowed = [runs[n_before - 1], *windowed]
    return windowed


# --- promote/rollback event records -------------------------------------------


@dataclass(frozen=True)
class PromoteEvent:
    kind: str  # "staging" | "rollback" | "promote_log" | "shadow_receipt"
    path: str
    event_date: date
    family: str | None = None
    detail: str | None = None

    def describe(self) -> str:
        family = f" family={self.family}" if self.family else ""
        detail = f" ({self.detail})" if self.detail else ""
        return f"{self.kind} {self.event_date}{family}{detail}: {Path(self.path).name}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "path": self.path,
            "event_date": self.event_date.isoformat(),
            "family": self.family,
            "detail": self.detail,
        }


def collect_promote_events(
    *,
    prod_artifacts_dir: Path,
    promote_log_dir: Path,
    shadow_receipt_dir: Path,
) -> list[PromoteEvent]:
    """Collect every recorded promote/rollback event. Event dates come from
    FILENAMES (the chains' own stamps), never mtime: the prod dir has been
    observed bulk-touched, so mtimes carry no evidentiary value. Fail-soft:
    missing dirs yield no events (an absent record is exactly what turns a
    change CRITICAL)."""
    events: list[PromoteEvent] = []

    try:
        prod_entries = sorted(prod_artifacts_dir.iterdir())
    except OSError:
        prod_entries = []
    for path in prod_entries:
        name = path.name
        if staging := _STAGING_NAME_RE.match(name):
            try:
                ts = datetime.strptime(staging.group("ts"), "%Y%m%dT%H%M%SZ")
            except ValueError:
                continue
            events.append(
                PromoteEvent(
                    kind="staging",
                    path=str(path),
                    event_date=ts.date(),
                    family=staging.group("family"),
                    detail=f"staged {staging.group('ts')}",
                )
            )
        elif rollback := _ROLLBACK_NAME_RE.match(name):
            event_date = _parse_iso_date(rollback.group("date"))
            if event_date is None:
                continue
            events.append(
                PromoteEvent(
                    kind="rollback",
                    path=str(path),
                    event_date=event_date,
                    family=rollback.group("family"),
                    detail=f"{rollback.group('cadence')} rollback backup",
                )
            )

    try:
        log_entries = sorted(promote_log_dir.glob("*.log"))
    except OSError:
        log_entries = []
    for path in log_entries:
        match = _PROMOTE_LOG_NAME_RE.match(path.name)
        if match is None:
            continue
        event_date = _parse_iso_date(match.group("date"))
        if event_date is None:
            continue
        status, _ = classify_promote_log(path)
        events.append(
            PromoteEvent(
                kind="promote_log",
                path=str(path),
                event_date=event_date,
                family=None,
                detail=f"weekly promote log, last run = {status}",
            )
        )

    try:
        receipt_entries = sorted(shadow_receipt_dir.glob("*.json"))
    except OSError:
        receipt_entries = []
    for path in receipt_entries:
        event_date = None
        if match := _RECEIPT_NAME_RE.match(path.name):
            event_date = _parse_iso_date(match.group("date"))
        if event_date is None:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                promoted_at = payload.get("promoted_at") if isinstance(payload, dict) else None
                event_date = _parse_iso_date(str(promoted_at)[:10]) if promoted_at else None
            except (OSError, json.JSONDecodeError, UnicodeDecodeError):
                event_date = None
        if event_date is None:
            continue
        events.append(
            PromoteEvent(
                kind="shadow_receipt",
                path=str(path),
                event_date=event_date,
                family=None,
                detail="shadow promotion receipt",
            )
        )

    return events


def events_in_window(
    events: list[PromoteEvent], prev: RunIdentity, curr: RunIdentity
) -> list[PromoteEvent]:
    """Events on the boundary's calendar window [prev run date, curr run date],
    both inclusive. Calendar-day granularity is deliberate: rollback markers and
    promote logs are dated, not timestamped, and an operator promote between two
    runs on the same day must legitimize that boundary."""
    d0 = prev.created_at.date()
    d1 = curr.created_at.date()
    return [ev for ev in events if d0 <= ev.event_date <= d1]


# --- boundary detection + explanation -----------------------------------------


@dataclass
class LaneChange:
    lane: str
    prev: LaneIdentity
    curr: LaneIdentity
    explained: bool = False
    events: list[PromoteEvent] = field(default_factory=list)
    note: str | None = None

    def describe(self) -> str:
        return f"{self.lane}: {self.prev.describe()} -> {self.curr.describe()}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "lane": self.lane,
            "prev": self.prev.as_dict(),
            "curr": self.curr.as_dict(),
            "explained": self.explained,
            "events": [ev.as_dict() for ev in self.events],
            "note": self.note,
        }


@dataclass
class Boundary:
    prev_run: RunIdentity
    curr_run: RunIdentity
    changes: list[LaneChange]

    @property
    def explained(self) -> bool:
        return all(change.explained for change in self.changes)

    def as_dict(self) -> dict[str, Any]:
        return {
            "prev_run_id": self.prev_run.run_id,
            "curr_run_id": self.curr_run.run_id,
            "prev_created_at": self.prev_run.created_at.isoformat(),
            "curr_created_at": self.curr_run.created_at.isoformat(),
            "explained": self.explained,
            "changes": [change.as_dict() for change in self.changes],
        }


def diff_runs(prev: RunIdentity, curr: RunIdentity) -> list[LaneChange]:
    changes: list[LaneChange] = []
    for lane in sorted(set(prev.lanes) | set(curr.lanes)):
        before = prev.lanes.get(lane, _absent_lane(lane))
        after = curr.lanes.get(lane, _absent_lane(lane))
        if before.key() != after.key():
            changes.append(LaneChange(lane=lane, prev=before, curr=after))
    return changes


def _lane_events(lane: str, window_events: list[PromoteEvent]) -> list[PromoteEvent]:
    if lane in _LANE_FAMILY_PREFIXES:
        prefixes = _LANE_FAMILY_PREFIXES[lane]
        return [
            ev
            for ev in window_events
            if ev.kind in ("staging", "rollback", "promote_log")
            and (ev.family is None or ev.family.startswith(prefixes))
        ]
    # shadow lanes: only a persisted promotion receipt is direct evidence.
    return [ev for ev in window_events if ev.kind == "shadow_receipt"]


def explain_boundary(boundary: Boundary, events: list[PromoteEvent]) -> None:
    """Mark each lane change explained/unexplained in place."""
    window = events_in_window(events, boundary.prev_run, boundary.curr_run)
    for change in boundary.changes:
        matched = _lane_events(change.lane, window)
        if matched:
            change.explained = True
            change.events = matched
    # A recorded promotion swaps prod and shadow lanes atomically: an explained
    # prod change legitimizes same-boundary shadow (and calibrator) changes.
    prod_change = next((c for c in boundary.changes if c.lane == LANE_PROD), None)
    if prod_change is not None and prod_change.explained:
        for change in boundary.changes:
            if not change.explained:
                change.explained = True
                change.events = prod_change.events
                change.note = "legitimized by the same-boundary recorded prod promote (atomic lane swap)"


# --- freshness (served trained_date, #210 28-day cap) --------------------------


def check_served_freshness(
    newest: RunIdentity, *, max_trained_age_days: int
) -> dict[str, Any]:
    """WARN when the newest run SERVED a model whose trained_date is over the
    #210 cap (or is unstamped). One-directional by design: proves stale, never
    certifies fresh (umbrella #423 doctrine)."""
    lane = newest.lanes.get(LANE_PROD)
    trained = _parse_iso_date(lane.trained_date) if lane and lane.trained_date else None
    as_of = newest.created_at.date()
    if trained is None:
        return {
            "warn": True,
            "trained_date": lane.trained_date if lane else None,
            "age_days": None,
            "max_trained_age_days": max_trained_age_days,
            "summary": (
                f"served prod panel trained_date missing/unparseable in run "
                f"{newest.run_id}; cannot bound model age against the "
                f"{max_trained_age_days}d freshness directive (#210)"
            ),
        }
    age_days = (as_of - trained).days
    warn = age_days > max_trained_age_days
    summary = (
        f"served prod panel trained {trained.isoformat()} is {age_days}d old at "
        f"{as_of.isoformat()}"
        + (
            f" — over the {max_trained_age_days}d model-freshness directive "
            f"(operator 2026-06-30 / RFC #210)"
            if warn
            else f" (<= {max_trained_age_days}d cap)"
        )
    )
    return {
        "warn": warn,
        "trained_date": trained.isoformat(),
        "age_days": age_days,
        "max_trained_age_days": max_trained_age_days,
        "summary": summary,
    }


# --- evaluation ----------------------------------------------------------------


def evaluate(
    runs: list[RunIdentity],
    events: list[PromoteEvent],
    *,
    max_trained_age_days: int = DEFAULT_MAX_TRAINED_AGE_DAYS,
) -> dict[str, Any]:
    """Evaluate a chronological run window into the monitor's report dict."""
    fail_closed: list[str] = []
    for run in runs:
        if not run.usable:
            fail_closed.append(f"run {run.run_id}: {run.problem}")
    usable = [r for r in runs if r.usable]
    if not runs:
        fail_closed.append("no canonical runs found in the runs DB")
    elif len(usable) < 2:
        fail_closed.append(
            f"fewer than two usable canonical run bundles to diff ({len(usable)} usable)"
        )

    boundaries: list[Boundary] = []
    for prev, curr in zip(usable, usable[1:]):
        changes = diff_runs(prev, curr)
        if not changes:
            continue
        boundary = Boundary(prev_run=prev, curr_run=curr, changes=changes)
        explain_boundary(boundary, events)
        boundaries.append(boundary)

    unexplained = [b for b in boundaries if not b.explained]
    freshness = (
        check_served_freshness(usable[-1], max_trained_age_days=max_trained_age_days)
        if usable
        else {"warn": False, "summary": "no usable run to check served freshness on"}
    )

    if fail_closed or unexplained:
        status = STATUS_CRITICAL
    elif freshness.get("warn"):
        status = STATUS_WARN
    else:
        status = STATUS_OK

    lines: list[str] = []
    for reason in fail_closed:
        lines.append(f"FAIL-CLOSED: {reason}")
    for boundary in boundaries:
        for change in boundary.changes:
            if change.explained:
                evidence = "; ".join(ev.describe() for ev in change.events)
                note = f" [{change.note}]" if change.note else ""
                lines.append(
                    f"INFO: {change.describe()} between {boundary.prev_run.run_id} and "
                    f"{boundary.curr_run.run_id} — explained by {evidence}{note}"
                )
            else:
                lines.append(
                    f"CRITICAL: {change.describe()} between {boundary.prev_run.run_id} "
                    f"and {boundary.curr_run.run_id} with NO recorded promote/rollback "
                    f"event in the boundary window — silent scorer swap"
                )
    if freshness.get("warn"):
        lines.append(f"WARN: {freshness['summary']}")

    if status == STATUS_OK:
        if usable:
            newest = usable[-1]
            prod = newest.lanes.get(LANE_PROD)
            summary = (
                f"scorer identity stable across {len(usable)} runs "
                f"({usable[0].run_id} .. {newest.run_id}); prod panel "
                f"{prod.describe() if prod else '?'}"
            )
            if boundaries:
                summary = (
                    f"{len(boundaries)} explained identity boundary(ies) across "
                    f"{len(usable)} runs; " + summary
                )
        else:
            summary = "no usable runs"
    elif status == STATUS_WARN:
        summary = freshness["summary"]
    else:
        summary = "; ".join(
            line for line in lines if line.startswith(("CRITICAL", "FAIL-CLOSED"))
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "owner_repo": OWNER_REPO,
        "as_of": usable[-1].created_at.isoformat() if usable else None,
        "n_runs": len(runs),
        "n_usable_runs": len(usable),
        "newest_run_id": usable[-1].run_id if usable else None,
        "boundaries": [b.as_dict() for b in boundaries],
        "n_unexplained_boundaries": len(unexplained),
        "fail_closed": fail_closed,
        "freshness": freshness,
        "status": status,
        "exit_code": _STATUS_EXIT_CODE[status],
        "lines": lines,
        "summary": summary,
    }


def build_report(
    *,
    db_path: Path,
    prod_artifacts_dir: Path,
    promote_log_dir: Path,
    shadow_receipt_dir: Path,
    run_type: str = DEFAULT_RUN_TYPE,
    strategy: str = DEFAULT_STRATEGY,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    max_trained_age_days: int = DEFAULT_MAX_TRAINED_AGE_DAYS,
    fetch_limit: int = 2000,
) -> dict[str, Any]:
    """Load, extract, and evaluate. DB/read errors fail closed to CRITICAL."""
    resolver = BoosterResolver(prod_artifacts_dir)
    try:
        rows = load_canonical_runs(
            db_path, run_type=run_type, strategy=strategy, limit=fetch_limit
        )
    except (FileNotFoundError, sqlite3.Error) as exc:
        return {
            "schema_version": SCHEMA_VERSION,
            "owner_repo": OWNER_REPO,
            "as_of": None,
            "n_runs": 0,
            "n_usable_runs": 0,
            "newest_run_id": None,
            "boundaries": [],
            "n_unexplained_boundaries": 0,
            "fail_closed": [f"runs DB unreadable ({db_path}): {exc}"],
            "freshness": {"warn": False, "summary": "runs DB unreadable"},
            "status": STATUS_CRITICAL,
            "exit_code": _STATUS_EXIT_CODE[STATUS_CRITICAL],
            "lines": [f"FAIL-CLOSED: runs DB unreadable ({db_path}): {exc}"],
            "summary": f"FAIL-CLOSED: runs DB unreadable ({db_path}): {exc}",
        }
    runs = [
        extract_identity(
            run_id=run_id,
            run_date=run_date,
            created_at=_parse_created_at(created_at),
            bundle_raw=bundle_raw,
            booster_resolver=resolver,
        )
        for run_id, run_date, created_at, bundle_raw in rows
    ]
    windowed = _window_runs(runs, lookback_days)
    events = collect_promote_events(
        prod_artifacts_dir=prod_artifacts_dir,
        promote_log_dir=promote_log_dir,
        shadow_receipt_dir=shadow_receipt_dir,
    )
    return evaluate(windowed, events, max_trained_age_days=max_trained_age_days)


# --- backfill timeline ----------------------------------------------------------


def format_timeline(runs: list[RunIdentity], events: list[PromoteEvent]) -> list[str]:
    """Segment N runs by identity and render the timeline with boundary
    verdicts (the backfill/replay view)."""
    lines: list[str] = []
    usable = [r for r in runs if r.usable]
    for run in runs:
        if not run.usable:
            lines.append(f"UNUSABLE {run.run_id}: {run.problem}")
    if not usable:
        lines.append("no usable runs")
        return lines

    segments: list[list[RunIdentity]] = [[usable[0]]]
    for run in usable[1:]:
        if run.identity_key() == segments[-1][-1].identity_key():
            segments[-1].append(run)
        else:
            segments.append([run])

    for index, segment in enumerate(segments):
        first, last = segment[0], segment[-1]
        lines.append(
            f"SEGMENT {first.run_id} .. {last.run_id} "
            f"({len(segment)} runs, {first.created_at.date()} .. {last.created_at.date()})"
        )
        for lane_name in sorted(first.lanes):
            lines.append(f"  {lane_name:<18} {first.lanes[lane_name].describe()}")
        if index + 1 < len(segments):
            prev, curr = segment[-1], segments[index + 1][0]
            boundary = Boundary(prev, curr, diff_runs(prev, curr))
            explain_boundary(boundary, events)
            verdict = "explained" if boundary.explained else "*** UNEXPLAINED ***"
            lines.append(f"BOUNDARY {prev.run_id} -> {curr.run_id}  {verdict}")
            for change in boundary.changes:
                lines.append(f"  {change.describe()}")
                if change.events:
                    for ev in change.events:
                        lines.append(f"    event: {ev.describe()}")
                    if change.note:
                        lines.append(f"    note: {change.note}")
                else:
                    lines.append("    event: (none in boundary window)")
    return lines


def build_backfill_lines(
    *,
    db_path: Path,
    prod_artifacts_dir: Path,
    promote_log_dir: Path,
    shadow_receipt_dir: Path,
    run_type: str = DEFAULT_RUN_TYPE,
    strategy: str = DEFAULT_STRATEGY,
    n_runs: int = DEFAULT_BACKFILL_RUNS,
) -> list[str]:
    resolver = BoosterResolver(prod_artifacts_dir)
    rows = load_canonical_runs(db_path, run_type=run_type, strategy=strategy, limit=n_runs)
    runs = [
        extract_identity(
            run_id=run_id,
            run_date=run_date,
            created_at=_parse_created_at(created_at),
            bundle_raw=bundle_raw,
            booster_resolver=resolver,
        )
        for run_id, run_date, created_at, bundle_raw in rows
    ]
    events = collect_promote_events(
        prod_artifacts_dir=prod_artifacts_dir,
        promote_log_dir=promote_log_dir,
        shadow_receipt_dir=shadow_receipt_dir,
    )
    return format_timeline(runs, events)


# --- alerting / CLI ---------------------------------------------------------------


def emit_alerts(
    report: dict[str, Any], *, topic: str, notify: bool, quiet: bool
) -> list[tuple[str, str]]:
    """Return (and, behind ``--notify``, post) the alert messages for a report."""
    alerts: list[tuple[str, str]] = []
    if report["status"] == STATUS_CRITICAL:
        body_lines = [
            line for line in report["lines"] if line.startswith(("CRITICAL", "FAIL-CLOSED"))
        ]
        alerts.append(
            ("RenQuant 104 scorer-identity CRITICAL", "\n".join(body_lines) or report["summary"])
        )
    if report["freshness"].get("warn"):
        alerts.append(("RenQuant 104 scorer-identity WARN", report["freshness"]["summary"]))
    if notify and not quiet:
        for title, body in alerts:
            post_ntfy(title, body, topic)
    return alerts


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=DEFAULT_REPO_ROOT)
    parser.add_argument("--db", type=Path, default=None, help="runs DB; default <repo-root>/data/runs.alpaca.db")
    parser.add_argument("--prod-artifacts-dir", type=Path, default=None)
    parser.add_argument("--promote-log-dir", type=Path, default=None)
    parser.add_argument("--shadow-receipt-dir", type=Path, default=None)
    parser.add_argument("--run-type", default=DEFAULT_RUN_TYPE)
    parser.add_argument("--strategy", default=DEFAULT_STRATEGY)
    parser.add_argument("--lookback-days", type=int, default=DEFAULT_LOOKBACK_DAYS)
    parser.add_argument("--max-trained-age-days", type=int, default=DEFAULT_MAX_TRAINED_AGE_DAYS)
    parser.add_argument(
        "--backfill",
        type=int,
        default=None,
        metavar="N",
        help="replay the last N canonical runs and print the identity timeline (report-only, exit 0)",
    )
    parser.add_argument("--topic", default=DEFAULT_NTFY_TOPIC)
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--notify", action="store_true", help="post ntfy alerts on CRITICAL/WARN")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def _resolved_paths(args: argparse.Namespace) -> dict[str, Path]:
    repo_root = args.repo_root.expanduser().resolve()
    return {
        "db_path": (args.db or repo_root.joinpath(*DEFAULT_DB_SUBPATH)).expanduser(),
        "prod_artifacts_dir": (
            args.prod_artifacts_dir or repo_root.joinpath(*PROD_ARTIFACTS_SUBDIR)
        ).expanduser(),
        "promote_log_dir": (
            args.promote_log_dir or repo_root.joinpath(*PROMOTE_LOG_SUBDIR)
        ).expanduser(),
        "shadow_receipt_dir": (
            args.shadow_receipt_dir or repo_root.joinpath(*SHADOW_RECEIPT_SUBDIR)
        ).expanduser(),
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    paths = _resolved_paths(args)

    if args.backfill is not None:
        lines = build_backfill_lines(
            **paths,
            run_type=args.run_type,
            strategy=args.strategy,
            n_runs=args.backfill,
        )
        print("\n".join(lines))
        return 0

    report = build_report(
        **paths,
        run_type=args.run_type,
        strategy=args.strategy,
        lookback_days=args.lookback_days,
        max_trained_age_days=args.max_trained_age_days,
    )
    alerts = emit_alerts(report, topic=args.topic, notify=args.notify, quiet=args.quiet)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"scorer_identity_check: {report['status']} - {report['summary']}")
        for line in report["lines"]:
            print(line)
        for title, body in alerts:
            print(f"{title}: {body}", file=sys.stderr)
    return report["exit_code"]


__all__ = [
    "Boundary",
    "BoosterResolver",
    "LaneChange",
    "LaneIdentity",
    "PromoteEvent",
    "RunIdentity",
    "build_backfill_lines",
    "build_report",
    "check_served_freshness",
    "collect_promote_events",
    "diff_runs",
    "emit_alerts",
    "evaluate",
    "events_in_window",
    "explain_boundary",
    "extract_identity",
    "format_timeline",
    "load_canonical_runs",
    "main",
    "DEFAULT_LOOKBACK_DAYS",
    "DEFAULT_MAX_TRAINED_AGE_DAYS",
    "LANE_CALIBRATOR",
    "LANE_PROD",
    "STATUS_CRITICAL",
    "STATUS_OK",
    "STATUS_WARN",
]


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
