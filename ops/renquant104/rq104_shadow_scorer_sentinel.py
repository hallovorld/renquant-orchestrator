#!/usr/bin/env python3
"""rq104 shadow-scorer sentinel (GOAL-5 AC1: silence is not health).

The failure this exists for: the shadow panel scorer (PatchTST, a G4-critical
data feed) silently died — it could not load its artifact for a long stretch —
and NOTHING alarmed, because shadow-scorer failure is *fail-soft*: the pipeline
logs a warning and carries on with the legacy tournament, it does not fail a
gate. The existing liveness checkers prove the daily job *ran*; the degradation
sentinel watches the LIVE buy path. Neither one looks at whether the SHADOW
scorer actually loaded and scored. This one looks.

It alarms on the silent-degradation states of the shadow feed, each anchored to
`>= N` (default 2) consecutive session days:

  a. LOAD FAILURE — live runs happened and health signal exists, but the shadow
     scorer did not load / produced 0 scores (and the pipeline did not mark the
     non-load as by-design). This is the incident pattern.
  b. NOT ACTIONABLE / DEGRADED — the shadow loaded and scored, but its output is
     not trustworthy: the pipeline health record flags `actionable=false`
     (stale train-cutoff, low coverage, missing provenance), or — on the DB
     fallback — the derived staleness / coverage breach the same thresholds.
  c. FEED DARK — live runs happened but NO shadow health signal exists at all
     from EITHER source (no health record AND no collected scores): the whole
     feed went dark; nothing is being persisted to evaluate.

READER IS PLUGGABLE, and is now WIRED to the concrete pipeline sink:

  PRIMARY  — the structured shadow-scorer health record the renquant-pipeline
             writes (renquant-pipeline#211): an append-only JSONL sidecar at
             `<strategy_dir>/logs/shadow_scorer_health.jsonl`
             (schema `shadow_scorer_health.v1`; mirrors `admission_shadow.jsonl`),
             one object per (run_date, shadow_name). The record carries the
             pipeline's own `actionable` verdict, which is the authoritative
             false-positive guard (see below).
  FALLBACK — DERIVE the same record shape from the shadow runs DB
             (`data/runs.alpaca_shadow.db` candidate_scores). Covers dates
             BEFORE the sink exists on this machine (PR-landed != deployed), so
             the sentinel is useful the day it ships. Primary wins per-day; gaps
             fall through to the fallback.

DETECTION-BY-DESIGN vs REAL FAILURE (the naive "0-scores => alarm" lesson). A
shadow scoring 0 is not always a bug: it can fail-closed BY DESIGN (a config
fingerprint rotation clearing the scan set, or the shadow intentionally
disabled). The pipeline record's `actionable` flag encodes this — `actionable`
is TRUE when the shadow output is usable/expected and FALSE when it is degraded.
This sentinel treats `actionable=false` as the degraded signal to alarm on, and
a by-design non-load (`loaded=false` but `actionable=true`) as healthy. The DB
fallback cannot read that flag (`actionable=None`), so it judges from derived
staleness / coverage / load only, and never counts a day that had no live runs
at all — that is the liveness checker's domain, mirroring the degradation
sentinel's "missing rows are not a degradation" rule.

FEED DARK is deliberately conservative: it fires only when NEITHER the JSONL nor
the DB has any shadow signal for a day that had runs. A JSONL-only gap while the
DB score feed is alive is NOT alarmed — that is exactly the bootstrap window
before the pipeline sink is deployed here, and false-paging through it would be
the deployed-but-dark anti-pattern in reverse.

Read-only everywhere: the runs DB is opened mode=ro&immutable=1; the health
JSONL is only read. Session-day gating uses the real NYSE calendar (holidays
never alarm), and every check anchors to whole past sessions — no intraday
freshness is measured, so there is no after-hours false-positive window (the
105 stale-tick lesson).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from liveness_common import alert, is_session_day  # noqa: E402

RQ = os.environ.get("RQ_ROOT", "/Users/renhao/git/github/RenQuant")

#: Strategy root on this machine (holds strategy_config.json + the logs/ sidecar
#: dir). renquant-pipeline#211 writes the health record under <strategy_dir>/logs.
STRATEGY_DIR = os.environ.get(
    "RQ104_STRATEGY_DIR", os.path.join(RQ, "backtesting/renquant_104")
)

#: PRIMARY reader source — the pipeline's structured shadow-scorer health record
#: (renquant-pipeline#211). Append-only JSONL, one object per line; schema
#: `shadow_scorer_health.v1`. Absent until the pipeline change is DEPLOYED here,
#: at which point it supersedes the DB fallback per-day. Override with the same
#: config key the pipeline uses: config["shadow_health"]["path"].
SHADOW_HEALTH_JSONL = os.environ.get(
    "RQ104_SHADOW_HEALTH_JSONL",
    os.path.join(STRATEGY_DIR, "logs/shadow_scorer_health.jsonl"),
)

# ---------------------------------------------------------------------------
# CANONICAL CONTRACT — imported from the PRODUCER (renquant-pipeline#211) so the
# writer and this reader cannot drift. Orchestrator depends on pipeline, so the
# import is legal; it is done defensively because a minimal launchd runtime may
# not have renquant_pipeline on its path. The local fallback literals are the
# EXACT same values; `test_fallback_matches_producer` asserts they equal the
# producer's exports (that test runs wherever pipeline IS importable, i.e. CI),
# so any drift is caught mechanically. The EXACT schema version gates acceptance:
# records with any other schema (missing, a future `…v2`/`…v10`, a typo) are
# IGNORED — a schema bump is a deliberate migration that must add a parser here.
# ---------------------------------------------------------------------------
_FALLBACK_CONTRACT = {
    "SHADOW_HEALTH_SCHEMA": "shadow_scorer_health.v1",
    "STATUS_OK": "ok",
    "STATUS_EXPECTED_SKIP": "expected_skip",
    "STATUS_FAULT": "fault",
    "FAULT_STATES": frozenset({"load_failed", "unresolved_artifact", "degraded", "not_scored"}),
    "EXPECTED_SKIP_STATES": frozenset({"disabled", "no_shadow_models", "no_candidates"}),
}
try:
    from renquant_pipeline.kernel.panel_pipeline import shadow_health as _sh  # noqa: E402
    SHADOW_HEALTH_SCHEMA = _sh.SHADOW_HEALTH_SCHEMA
    STATUS_OK = _sh.STATUS_OK
    STATUS_EXPECTED_SKIP = _sh.STATUS_EXPECTED_SKIP
    STATUS_FAULT = _sh.STATUS_FAULT
    FAULT_STATES = frozenset(_sh.FAULT_STATES)
    EXPECTED_SKIP_STATES = frozenset(_sh.EXPECTED_SKIP_STATES)
    CONTRACT_SOURCE = "renquant_pipeline"
except Exception:  # noqa: BLE001 — any import failure -> use the asserted-equal literals
    SHADOW_HEALTH_SCHEMA = _FALLBACK_CONTRACT["SHADOW_HEALTH_SCHEMA"]
    STATUS_OK = _FALLBACK_CONTRACT["STATUS_OK"]
    STATUS_EXPECTED_SKIP = _FALLBACK_CONTRACT["STATUS_EXPECTED_SKIP"]
    STATUS_FAULT = _FALLBACK_CONTRACT["STATUS_FAULT"]
    FAULT_STATES = _FALLBACK_CONTRACT["FAULT_STATES"]
    EXPECTED_SKIP_STATES = _FALLBACK_CONTRACT["EXPECTED_SKIP_STATES"]
    CONTRACT_SOURCE = "local_fallback"

#: The three canonical statuses; a record must carry one of them. `actionable`
#: is redundant with status by the producer invariant `actionable == (status !=
#: "fault")`, kept only as an integrity cross-check.
VALID_STATUSES = frozenset({STATUS_OK, STATUS_EXPECTED_SKIP, STATUS_FAULT})

#: FALLBACK reader source — the shadow runs DB.
SHADOW_DB = os.environ.get("RQ104_SHADOW_DB", os.path.join(RQ, "data/runs.alpaca_shadow.db"))

#: FALLBACK reader source for MLflow-logged lanes (e.g. the top-decile clf
#: blend leg) — the mlruns tree rq104_blend_readout.py already reads daily.
MLRUNS_DIR = os.environ.get("RQ104_MLRUNS_DIR", os.path.join(RQ, "mlruns"))

#: had_runs check for MLflow-logged lanes: the PRODUCTION runs DB (not the
#: shadow DB, which this kind of lane never writes to) — the same DB
#: rq104_blend_readout.py's latest_live_run() reads.
PROD_RUNS_DB = os.environ.get("RQ104_PROD_RUNS_DB", os.path.join(RQ, "data/runs.alpaca.db"))

#: The shadow scorer's identity, as it appears in the record's shadow_name and
#: in candidate_scores.active_scorer / model_type. PatchTST is served as
#: 'hf_patchtst'. Config lane names DECORATE this key (e.g.
#: 'hf_patchtst_pt07_strict_seed44_previous_primary' after the 2026-07 clf
#: promotion demoted the lane), so the health-record match accepts the exact
#: key or any 'SHADOW_NAME_*' decorated form — see _matches_shadow_lane.
SHADOW_NAME = os.environ.get("RQ104_SHADOW_NAME", "hf_patchtst")


@dataclass(frozen=True)
class WatchedLane:
    """One shadow lane to patrol.

    A lane is not just a name: lanes differ in where their evidence LIVES.
    The PatchTST lane persists scores to the shadow runs DB, so a DB-derived
    record is a usable fallback when the structured health record is missing.
    The top-decile clf lane does NOT — it logs to MLflow — so for it the DB
    fallback would report "no scores" every single day and manufacture a
    permanent FEED DARK alarm out of a healthy lane. `runs_db` is therefore
    per-lane and may be None, meaning "structured record or nothing", UNLESS
    `mlruns_dir` is set — then the MLflow `comparison.json` locator (shared
    with rq104_blend_readout.py, the job that already reads this lane's
    evidence daily) is the fallback instead of the DB.

    `None` on the threshold fields means "use the module default", which keeps
    the existing single-lane call sites and their tests working unchanged.
    """
    name: str
    runs_db: str | None = None          # None -> no DB fallback for this lane
    mlruns_dir: str | None = None       # set -> MLflow comparison.json fallback
    staleness_max_days: int | None = None
    coverage_floor: float | None = None
    #: why this lane is watched, quoted in its alerts so an operator reading a
    #: page at 06:00 knows what it protects without opening the code
    purpose: str = ""

    def matches(self, shadow_name: str) -> bool:
        """Exact key, or the decorated config-lane form '<name>_<suffix>'."""
        return shadow_name == self.name or shadow_name.startswith(self.name + "_")

    @property
    def effective_staleness_max(self) -> int:
        return (self.staleness_max_days if self.staleness_max_days is not None
                else STALENESS_MAX_DAYS)

    @property
    def effective_coverage_floor(self) -> float:
        return (self.coverage_floor if self.coverage_floor is not None
                else COVERAGE_FLOOR)


def watched_lanes() -> tuple[WatchedLane, ...]:
    """The lanes patrolled on this machine.

    Resolved at call time, not import time, so tests and operators can retarget
    paths through the same env vars the single-lane version used.
    """
    return (
        WatchedLane(
            name=SHADOW_NAME,
            runs_db=SHADOW_DB,
            purpose="the G4-critical PatchTST feed whose silent death this "
                    "sentinel was built for",
        ),
        WatchedLane(
            name=os.environ.get("RQ104_CLF_LANE_NAME", "topdecile_clf_blend_leg"),
            runs_db=None,   # MLflow-logged: a DB fallback would alarm daily
            mlruns_dir=MLRUNS_DIR,  # its actual evidence source instead
            purpose="the certified top-decile classifier now accruing the "
                    "120-session forward ledger — the one line with a "
                    "confirmed effect, and until now unwatched",
        ),
    )


def _matches_shadow_lane(name: str) -> bool:
    """True if a health record's shadow_name is this sentinel's lane.

    Exact match, or the decorated config-lane form 'SHADOW_NAME_<suffix>'.
    A differently-keyed lane (e.g. 'topdecile_clf_blend_leg') never matches.
    If two decorated lanes of the same key ever coexist on one date,
    last-record-wins applies — acceptable while the config carries at most
    one lane per served-model key; a multi-lane sentinel is the follow-up.
    """
    return name == SHADOW_NAME or name.startswith(SHADOW_NAME + "_")

#: consecutive session days of a degraded state before alarming. 2 keeps
#: detection within one session of the incident onset while a single quiet day
#: (a one-off hiccup) never pages.
STREAK_N = int(os.environ.get("RQ104_SHADOW_STREAK_N", "2"))

#: shadow artifact staleness ceiling in calendar days — aligned with the
#: pipeline record's own default (>28d => actionable=false). Used only for the
#: DB fallback (the pipeline record's actionable verdict is authoritative when
#: present).
STALENESS_MAX_DAYS = int(os.environ.get("RQ104_SHADOW_STALENESS_MAX_DAYS", "28"))

#: minimum shadow coverage of the day's candidate set — aligned with the
#: pipeline default (<0.80 => actionable=false). DB-fallback use only.
COVERAGE_FLOOR = float(os.environ.get("RQ104_SHADOW_COVERAGE_FLOOR", "0.80"))


# ---------------------------------------------------------------------------
# the health-record contract (pipeline sink == fallback == tests all speak this)
# ---------------------------------------------------------------------------

@dataclass
class ShadowHealthRecord:
    """One (run_date, shadow_name) health verdict. Mirrors renquant-pipeline#211's
    `shadow_scorer_health.v1` record; the DB fallback DERIVES the same shape so
    the checks are source-agnostic.

    `status` is the authoritative axis (STATUS_OK / STATUS_EXPECTED_SKIP /
    STATUS_FAULT): the sentinel alarms on STATUS_FAULT and stays quiet on ok /
    expected_skip. `state` (STATE_*) refines the message. `actionable` is
    redundant with status by the producer invariant `actionable == (status !=
    "fault")` and kept only as an integrity cross-check. DB-fallback records have
    no status (None) and rely on derived load / staleness / coverage signals.

    had_runs / feed_present are derivation context (were there live runs at all;
    is there any shadow signal) that keep the liveness and feed-dark domains
    distinct.
    """
    run_date: dt.date
    shadow_name: str = SHADOW_NAME
    status: str | None = None
    state: str | None = None
    loaded: bool = False
    load_error: str | None = None
    artifact_path: str | None = None
    artifact_resolved: bool | None = None
    artifact_resolved_path: str | None = None
    effective_train_cutoff_date: str | None = None
    staleness_days: int | None = None
    config_fingerprint: str | None = None
    content_sha256: str | None = None
    n_candidates: int | None = None
    n_scored: int = 0
    coverage_frac: float | None = None
    skip_reason: str | None = None
    actionable: bool | None = None
    reasons: list[str] = field(default_factory=list)
    run_id: str | None = None
    kind: str | None = None
    source: str = "unknown"
    had_runs: bool = True
    feed_present: bool = True

    @classmethod
    def from_dict(cls, d: dict, *, source: str) -> "ShadowHealthRecord":
        rd = d.get("run_date") or d.get("date")
        run_date = dt.date.fromisoformat(rd) if isinstance(rd, str) else rd
        act = d.get("actionable")
        return cls(
            run_date=run_date,
            shadow_name=d.get("shadow_name", SHADOW_NAME),
            status=d.get("status"),
            state=d.get("state"),
            loaded=bool(d.get("loaded", False)),
            load_error=d.get("load_error"),
            artifact_path=d.get("artifact_path"),
            artifact_resolved=d.get("artifact_resolved"),
            artifact_resolved_path=d.get("artifact_resolved_path"),
            effective_train_cutoff_date=d.get("effective_train_cutoff_date"),
            staleness_days=d.get("staleness_days"),
            config_fingerprint=d.get("config_fingerprint"),
            content_sha256=d.get("content_sha256"),
            n_candidates=d.get("n_candidates"),
            n_scored=int(d.get("n_scored", 0)),
            coverage_frac=d.get("coverage_frac"),
            skip_reason=d.get("skip_reason"),
            actionable=None if act is None else bool(act),
            reasons=list(d.get("reasons", []) or []),
            run_id=d.get("run_id"),
            kind=d.get("kind"),
            source=source,
            had_runs=bool(d.get("had_runs", True)),
            feed_present=bool(d.get("feed_present", True)),
        )


# per-record classification
HEALTHY = "healthy"
LOAD_FAIL = "load_fail"
DEGRADED = "degraded"       # loaded but not actionable (stale / coverage / provenance)
FEED_DARK = "feed_dark"


def _effective_status(r: ShadowHealthRecord) -> str | None:
    """The record's canonical status. Prefer the explicit `status` field; if a
    record carried only `actionable` (defensive — #211 always emits status),
    derive it from the invariant `actionable == (status != fault)`. DB-fallback
    records have neither -> None."""
    if r.status is not None:
        return r.status
    if r.actionable is True:
        return STATUS_OK
    if r.actionable is False:
        return STATUS_FAULT
    return None


def classify(r: ShadowHealthRecord) -> tuple[str, list[str]]:
    """Map a record to (class, human reasons). Source-agnostic.

    PRODUCER/CONSUMER CONTRACT with renquant-pipeline#211: `status` is the single
    authoritative fault axis (invariant `actionable == (status != "fault")`).
      * STATUS_OK / STATUS_EXPECTED_SKIP -> QUIET. expected_skip is #211's
        explicit by-design non-fault (states: disabled / no_shadow_models /
        no_candidates) — loaded may be false, but it is NOT a fault.
      * STATUS_FAULT -> the alarm axis (states: unresolved_artifact / load_failed
        / not_scored / degraded). Alarm after >= N consecutive sessions.
    `state` / `loaded` / `n_scored` only pick the MESSAGE (LOAD_FAIL vs
    DEGRADED). The DB fallback has no status (None) and derives fault from load /
    staleness / coverage instead.
    """
    # feed dark: a day that had runs but yields no shadow signal from either feed
    if not r.feed_present:
        return FEED_DARK, ["no shadow health record and no collected scores"]

    status = _effective_status(r)
    if status is not None:
        if status != STATUS_FAULT:   # ok / expected_skip -> by design, stay quiet
            return HEALTHY, []
        reasons = list(r.reasons) or [r.state or r.load_error or "fault"]
        # a non-load / not-scored fault reads as LOAD_FAIL; a scored-but-untrusted
        # fault (degraded) reads as DEGRADED.
        if (not r.loaded) or r.n_scored == 0:
            return LOAD_FAIL, reasons
        return DEGRADED, reasons

    # status unknown (DB fallback only): derive fault from load / staleness / coverage
    if (not r.loaded) or r.n_scored == 0:
        return LOAD_FAIL, [r.load_error or "not loaded / 0 scored"]
    derived: list[str] = []
    if r.staleness_days is not None and r.staleness_days > STALENESS_MAX_DAYS:
        derived.append(f"stale train-cutoff {r.staleness_days}d > {STALENESS_MAX_DAYS}d ceiling")
    if r.coverage_frac is not None and r.coverage_frac < COVERAGE_FLOOR:
        derived.append(f"coverage {r.coverage_frac:.0%} < {COVERAGE_FLOOR:.0%} floor")
    if derived:
        return DEGRADED, derived
    return HEALTHY, []


# ---------------------------------------------------------------------------
# session-day helpers (same semantics as the degradation sentinel)
# ---------------------------------------------------------------------------

def last_session_days(as_of: dt.date, n: int, *, lookback_days: int = 21) -> list[dt.date]:
    """The n most recent NYSE session days ending at as_of (inclusive if a
    session day), OLDEST first. Bounded lookback so a calendar failure can never
    loop forever."""
    out: list[dt.date] = []
    day = as_of
    for _ in range(lookback_days):
        if is_session_day(day):
            out.append(day)
            if len(out) == n:
                break
        day -= dt.timedelta(days=1)
    return list(reversed(out))


# ---------------------------------------------------------------------------
# reader: pluggable structured sink -> DB fallback
# ---------------------------------------------------------------------------

def read_health_records(days: list[dt.date], lane: 'WatchedLane | None' = None
                        ) -> dict[dt.date, ShadowHealthRecord | None]:
    """Per-day ShadowHealthRecord (or None if the day had no live runs at all —
    the liveness checker's domain). Primary source wins per-day; days it does
    not cover fall through to the lane's fallback, so a not-yet-deployed sink
    still gets full coverage."""
    primary = _read_from_pipeline_sink(days, lane)
    missing = [d for d in days if d not in primary]
    if lane is not None and lane.mlruns_dir:
        # MLflow-logged lane: its real evidence source, not the runs DB.
        fallback = {} if not missing else _read_from_mlflow(missing, lane)
    else:
        # A lane with no runs DB and no mlruns_dir gets NO fallback: deriving
        # 'no scores' from a DB it never writes to would manufacture a
        # permanent FEED DARK alarm out of a perfectly healthy lane.
        no_db = lane is not None and lane.runs_db is None
        fallback = ({} if (no_db or not missing)
                    else _read_from_shadow_db(missing, lane))
    return {d: primary.get(d, fallback.get(d)) for d in days}


def _is_bool(v: object) -> bool:
    return isinstance(v, bool)


def _is_int(v: object) -> bool:
    # bool is a subclass of int in Python; a boolean is NOT a valid integer here.
    return isinstance(v, int) and not isinstance(v, bool)


def _opt(v: object, ok) -> bool:
    """Nullable field: pass if absent/None, else must satisfy `ok`."""
    return v is None or ok(v)


def is_valid_v1_record(obj: object) -> bool:
    """Strict acceptance for a `shadow_scorer_health.v1` record.

    Returns True only for an EXACT-version record whose core, decision-driving
    fields are present and correctly typed. Anything else — missing/unknown
    schema (`…v2`, `…v10`, a typo, or none), a malformed boolean/int, a missing
    core field, an unparseable run_date — returns False so the record is
    IGNORED and the DB fallback stays authoritative for that day. A new schema
    version is a deliberate migration: add its parser, do not best-effort it.
    """
    if not isinstance(obj, dict):
        return False
    if obj.get("schema") != SHADOW_HEALTH_SCHEMA:
        return False
    # required core fields + exact types (bool must be bool, int must not be bool)
    if not isinstance(obj.get("shadow_name"), str):
        return False
    if not isinstance(obj.get("run_date"), str):
        return False
    try:
        dt.date.fromisoformat(obj["run_date"])
    except (ValueError, TypeError):
        return False
    if not _is_bool(obj.get("loaded")):
        return False
    if not _is_bool(obj.get("actionable")):
        return False
    if not _is_int(obj.get("n_scored")):
        return False
    # status is the authoritative fault axis — required and constrained to the
    # producer's canonical set; the actionable invariant must hold or the record
    # is internally inconsistent (corrupt / wrong producer) and is rejected.
    status = obj.get("status")
    if status not in VALID_STATUSES:
        return False
    if obj["actionable"] != (status != STATUS_FAULT):
        return False
    # nullable-but-typed fields, when present
    if not _opt(obj.get("staleness_days"), _is_int):
        return False
    if not _opt(obj.get("coverage_frac"), lambda v: _is_int(v) or isinstance(v, float)):
        return False
    if not _opt(obj.get("n_candidates"), _is_int):
        return False
    if not _opt(obj.get("state"), lambda v: isinstance(v, str)):
        return False
    reasons = obj.get("reasons")
    if reasons is not None and not isinstance(reasons, list):
        return False
    return True


def _read_from_pipeline_sink(days: list[dt.date], lane: 'WatchedLane | None' = None
                             ) -> dict[dt.date, ShadowHealthRecord]:
    """Read the pipeline's structured health record (renquant-pipeline#211).

    JSONL sidecar, one object per line, schema `shadow_scorer_health.v1`.
    Absent until the pipeline change is deployed on this machine, in which case
    this returns {} and the DB fallback drives. Every line is STRICTLY validated
    (`is_valid_v1_record`); an unknown-schema or malformed record is skipped, not
    parsed. If the pipeline later ships a DB-table sink or a new schema version,
    add its parser here — the downstream checks do not change.
    """
    path = SHADOW_HEALTH_JSONL
    if not path or not os.path.exists(path):
        return {}
    wanted = set(days)
    out: dict[dt.date, ShadowHealthRecord] = {}
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not is_valid_v1_record(obj):
                    continue  # unknown/invalid -> ignore; DB fallback stays authoritative
                rec = ShadowHealthRecord.from_dict(obj, source="pipeline_health_record")
                matches = (lane.matches(rec.shadow_name) if lane is not None
                           else _matches_shadow_lane(rec.shadow_name))
                if not matches or rec.run_date not in wanted:
                    continue
                out[rec.run_date] = rec  # last record for a date wins (latest re-run)
    except OSError:
        return {}
    return out


def _open_db_readonly(path: str) -> sqlite3.Connection | None:
    try:
        return sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)
    except sqlite3.Error:
        return None


def _read_from_shadow_db(days: list[dt.date], lane: 'WatchedLane | None' = None
                         ) -> dict[dt.date, ShadowHealthRecord]:
    """Fallback: derive a ShadowHealthRecord per day from the shadow runs DB.

    Ground truth used today:
      * had_runs      — any live pipeline_runs row that day (else None: liveness)
      * feed_present  — any candidate_scores row for those runs
      * n_scored      — candidate_scores rows attributable to the shadow scorer
                        (active_scorer or model_type matching the lane via
                        _matches_shadow_lane --- the SAME function the JSONL
                        path uses, so the two cannot diverge)
      * loaded        — n_scored > 0
      * coverage_frac — distinct shadow-scored tickers / distinct candidate tickers
      * staleness_days— run_date minus the newest pipeline_runs.training_cutoff
                        seen that day (the shadow artifact's effective cutoff)
    `actionable` is left None (the pipeline's verdict is unavailable here).
    """
    if not days:
        return {}
    conn = _open_db_readonly(lane.runs_db if lane is not None else SHADOW_DB)
    if conn is None:
        return {}
    out: dict[dt.date, ShadowHealthRecord] = {}
    try:
        for day in days:
            rec = _derive_day_record(conn, day)
            if rec is not None:
                out[day] = rec
    finally:
        conn.close()
    return out


def _derive_day_record(conn: sqlite3.Connection, day: dt.date) -> ShadowHealthRecord | None:
    iso = day.isoformat()
    run_rows = conn.execute(
        "SELECT run_id, training_cutoff FROM pipeline_runs "
        "WHERE run_type='live' AND run_date=?",
        (iso,),
    ).fetchall()
    if not run_rows:
        return None  # no live runs at all => liveness checker's alarm, not ours

    run_ids = [r[0] for r in run_rows]
    cutoffs = [r[1] for r in run_rows if r[1]]
    placeholders = ",".join("?" for _ in run_ids)
    try:
        total_tickers = conn.execute(
            f"SELECT COUNT(DISTINCT ticker) FROM candidate_scores "
            f"WHERE run_id IN ({placeholders})",
            run_ids,
        ).fetchone()[0] or 0
        total_rows = conn.execute(
            f"SELECT COUNT(*) FROM candidate_scores WHERE run_id IN ({placeholders})",
            run_ids,
        ).fetchone()[0] or 0
        # LANE MATCHING MUST USE `_matches_shadow_lane`, THE SAME FUNCTION THE JSONL
        # PATH USES. Until 2026-07-30 this branch compared with SQL `=` while the
        # JSONL branch (line ~534) used the prefix matcher. The served lane is
        # `hf_patchtst_pt07_strict_seed44_previous_primary`, which the matcher
        # accepts and `=` rejects, so whenever the JSONL sink did not cover a date
        # the fallback found ZERO rows and the sentinel reported
        #   "LOAD FAILURE ... ZERO shadow scores"
        # while the pipeline's own record for the same date said
        #   loaded=True, n_scored=77 and 85, reasons=['stale_622d_limit_28d'].
        # A wrong and MORE alarming diagnosis than the truth: the lane was stale,
        # not dead, and the two send a reader to different places.
        #
        # Fixed by pulling the names and filtering in Python with the shared
        # function rather than by adding a SQL `LIKE`. A second matcher expressed in
        # SQL is a twin implementation, and the copy that runs is never the copy a
        # reader finds first.
        rows = conn.execute(
            f"SELECT ticker, active_scorer, model_type FROM candidate_scores "
            f"WHERE run_id IN ({placeholders})",
            run_ids,
        ).fetchall()
        matched = [r for r in rows
                   if _matches_shadow_lane(str(r[1] or ""))
                   or _matches_shadow_lane(str(r[2] or ""))]
        shadow_rows = len(matched)
        shadow_tickers = len({r[0] for r in matched})

        # "THE DB DOES NOT RECORD IT" IS NOT "THE SHADOW SCORED NOTHING".
        # Measured 2026-07-30: since 2026-07-22 every candidate_scores row in
        # runs.alpaca_shadow.db carries active_scorer = NULL and model_type = NULL —
        # 88/85/85/95/360/98 rows on six live dates, ZERO of them identifiable under
        # ANY matcher. Reporting loaded=False there says the shadow lane produced no
        # scores, when the truth is that this store cannot answer the question. The
        # pipeline's own JSONL for the same dates says loaded=True, n_scored=77/85.
        # Same wrong-object shape as the matcher bug above, one level down.
        # The test is on `active_scorer` ALONE, and that is not a simplification.
        # Measured on 2026-07-28 in this store, `model_type` holds the per-ticker
        # TOURNAMENT families — 'XGBoost' (104 rows), 'QLearning' (96), 'Manual' (68),
        # 'Classification' (60) — a different vocabulary that can never contain a
        # shadow lane name. So `active_scorer OR model_type` was always half inert,
        # and testing the pair for emptiness would have left this flag permanently
        # OFF: my first version did exactly that and never fired on the real data.
        # BOTH conditions, and the second is why: an existing contract
        # (test_model_type_marks_shadow_when_active_scorer_null) says `model_type`
        # MAY carry the lane when `active_scorer` is null, and my first narrowing
        # broke it. So "uninformative" means active_scorer is uniformly absent AND
        # no model_type value identifies the lane either.
        scorer_column_uninformative = (
            bool(rows)
            and not any(r[1] for r in rows)
            and not any(_matches_shadow_lane(str(r[2] or "")) for r in rows)
        )
    except sqlite3.OperationalError:
        # candidate_scores absent (minimal/legacy store): degrade, never abort.
        total_tickers = total_rows = shadow_rows = shadow_tickers = 0
        scorer_column_uninformative = True   # absent table cannot answer either

    staleness_days: int | None = None
    cutoff_str: str | None = None
    if cutoffs:
        try:
            newest = max(dt.date.fromisoformat(c[:10]) for c in cutoffs)
            staleness_days = (day - newest).days
            cutoff_str = newest.isoformat()
        except ValueError:
            staleness_days = None

    return ShadowHealthRecord(
        run_date=day,
        shadow_name=SHADOW_NAME,
        # None, not False, when the store cannot answer. False here would assert
        # the shadow lane scored nothing, which is a stronger and different claim
        # than 'this store does not record which scorer produced these rows'.
        loaded=(None if scorer_column_uninformative else shadow_rows > 0),
        effective_train_cutoff_date=cutoff_str,
        staleness_days=staleness_days,
        n_candidates=total_tickers,
        n_scored=shadow_rows,
        coverage_frac=(shadow_tickers / total_tickers) if total_tickers else None,
        actionable=None,  # fallback cannot see the pipeline's verdict
        run_id=run_ids[-1],
        source="shadow_runs_db_fallback",
        had_runs=True,
        feed_present=total_rows > 0,
    )


def _had_live_run(conn: sqlite3.Connection, day: dt.date) -> bool:
    """True if a live pipeline run happened on `day`, per the PRODUCTION runs
    DB. MLflow-logged lanes never write pipeline_runs, so this — not the
    shadow DB check `_derive_day_record` uses — is what gates a day into
    'liveness domain, skip' vs 'a real gap in this lane's evidence'."""
    row = conn.execute(
        "SELECT 1 FROM pipeline_runs WHERE run_type='live' AND run_date=? LIMIT 1",
        (day.isoformat(),),
    ).fetchone()
    return row is not None


def _run_tag(run_dir: Path, tag_name: str) -> str | None:
    """One MLflow FileStore run tag (`<run_dir>/tags/<tag_name>`), or None if
    absent/unreadable. The producer (`_log_shadow_run` in renquant-pipeline)
    writes `as_of_date` and `shadow_name` as run tags via `mlflow.set_tags`
    at log time — a content-based record, unlike file mtime, which a
    touch/copy/retry of the artifact changes without touching what date or
    lane the run actually belongs to."""
    try:
        return (run_dir / "tags" / tag_name).read_text().strip()
    except OSError:
        return None


def _mlflow_shadow_scores_for(run_date: str, mlruns: Path, shadow_name: str):
    """Locate the MLflow comparison table for `run_date`, scoped to
    `shadow_name`. Returns the shadow_score Series indexed by ticker, or None.

    Primary match: each candidate run's own `as_of_date`/`shadow_name` MLflow
    tags (see `_run_tag`) — checked across EVERY comparison.json under
    `mlruns` (tag reads are two small text files, cheap enough to not need a
    candidate cap), so an older matching record is never shadowed by a newer,
    unrelated one. A run whose tags exist but do not match this
    (run_date, shadow_name) is decisively excluded — never re-considered by
    the legacy heuristic below, which cannot tell lanes apart.

    Legacy fallback, for runs with no tags at all (pre-tag producer, or a
    different one): the SAME locator rq104_blend_readout.py uses — the
    payload's own `run_date`/`shadow_name` columns if present, else file
    mtime as the date, capped at the 20 most-recently-modified untagged
    candidates. Kept only for backward compatibility with untagged history;
    every run this producer logs today carries both tags.
    """
    import pandas as pd  # local: only lanes with mlruns_dir pay this cost

    def _load(p: Path):
        try:
            raw = json.loads(p.read_text())
            df = pd.DataFrame(raw["data"], columns=raw["columns"])
        except Exception:
            return None
        if "shadow_score" not in df.columns or "ticker" not in df.columns:
            return None
        return df

    all_candidates = list(mlruns.rglob("comparison.json"))

    tagged_matches = []
    untagged: list[Path] = []
    for p in all_candidates:
        run_dir = p.parent.parent
        tag_date = _run_tag(run_dir, "as_of_date")
        tag_lane = _run_tag(run_dir, "shadow_name")
        if tag_date is None or tag_lane is None:
            untagged.append(p)
            continue
        if tag_date[:10] == run_date and tag_lane == shadow_name:
            tagged_matches.append(p)

    if tagged_matches:
        # a rerun of the same (date, lane) -> the most recently written wins
        best = max(tagged_matches, key=lambda p: p.stat().st_mtime)
        df = _load(best)
        if df is not None:
            return df.set_index("ticker")["shadow_score"].astype(float)
        return None

    candidates = sorted(untagged, key=lambda p: p.stat().st_mtime, reverse=True)
    for p in candidates[:20]:
        df = _load(p)
        if df is None:
            continue
        if "run_date" in df.columns and str(df["run_date"].iloc[0])[:10] != run_date:
            continue
        if "run_date" not in df.columns:
            mdate = dt.date.fromtimestamp(p.stat().st_mtime).isoformat()
            if mdate != run_date:
                continue
        if "shadow_name" in df.columns and df["shadow_name"].iloc[0] != shadow_name:
            continue
        return df.set_index("ticker")["shadow_score"].astype(float)
    return None


def _read_from_mlflow(days: list[dt.date], lane: 'WatchedLane'
                      ) -> dict[dt.date, ShadowHealthRecord]:
    """Fallback for MLflow-logged lanes (e.g. the top-decile clf blend leg):
    derive a ShadowHealthRecord per day from the same comparison.json evidence
    rq104_blend_readout.py already reads daily, instead of a DB this kind of
    lane never writes to. had_runs comes from the PRODUCTION runs DB (the
    shadow DB is the wrong ground truth here — this lane never writes there).
    `actionable`/staleness/coverage are left unset, same as the DB fallback:
    this source cannot see the pipeline's verdict either.
    """
    if not days or not lane.mlruns_dir or not os.path.isdir(lane.mlruns_dir):
        return {}
    conn = _open_db_readonly(PROD_RUNS_DB)
    if conn is None:
        return {}
    out: dict[dt.date, ShadowHealthRecord] = {}
    mlruns_path = Path(lane.mlruns_dir)
    try:
        for day in days:
            if not _had_live_run(conn, day):
                continue  # no live run at all -> liveness domain, not ours
            scores = _mlflow_shadow_scores_for(day.isoformat(), mlruns_path, lane.name)
            loaded = scores is not None
            out[day] = ShadowHealthRecord(
                run_date=day,
                shadow_name=lane.name,
                loaded=loaded,
                n_scored=(int(scores.notna().sum()) if loaded else 0),
                n_candidates=(int(len(scores)) if loaded else None),
                actionable=None,
                source="mlflow_comparison_fallback",
                had_runs=True,
                feed_present=loaded,
            )
    finally:
        conn.close()
    return out


# ---------------------------------------------------------------------------
# checks — mutually exclusive by construction (at most one fires per window)
# ---------------------------------------------------------------------------

def _classify_window(records, days):
    """(date, record, class, reasons) for days that had live runs, oldest-first.
    A day with no record (None) means no runs at all — liveness's domain — and
    is omitted (so a streak is only asserted over days we can actually see)."""
    out = []
    for d in days:
        r = records.get(d)
        if r is None:
            continue
        cls, reasons = classify(r)
        out.append((d, r, cls, reasons))
    return out


def check_feed_dark_streak(records, days, lane_name=SHADOW_NAME) -> str | None:
    obs = _classify_window(records, days)
    if len(obs) < len(days) or not obs:
        return None
    if all(c == FEED_DARK for _, _, c, _ in obs):
        detail = ", ".join(f"{d.isoformat()} (src={r.source})" for d, r, _, _ in obs)
        return (
            f"shadow score feed DARK: {len(obs)} consecutive session day(s) with "
            f"live runs but NO shadow health signal at all (no record, no collected "
            f"scores) — {detail}. The whole feed for '{lane_name}' went dark; "
            f"nothing is being persisted to evaluate."
        )
    return None


def check_load_failure_streak(records, days, lane_name=SHADOW_NAME) -> str | None:
    obs = _classify_window(records, days)
    if len(obs) < len(days) or not obs:
        return None
    if all(c == LOAD_FAIL for _, _, c, _ in obs):
        detail = ", ".join(
            f"{d.isoformat()} (n_scored={r.n_scored}, src={r.source}"
            + (f", {'; '.join(rs)}" if rs else "") + ")"
            for d, r, _, rs in obs
        )
        return (
            f"shadow scorer '{lane_name}' LOAD FAILURE: {len(obs)} consecutive "
            f"session day(s) with live runs but ZERO shadow scores — {detail}. "
            f"The shadow feed silently died (fail-soft: no gate fires). This is the "
            f"'couldn't load its artifact' incident class."
        )
    return None


def check_degraded_streak(records, days, lane_name=SHADOW_NAME) -> str | None:
    """Loaded-but-unusable for >= N sessions: stale cutoff, low coverage, missing
    provenance (pipeline `actionable=false`) — or a mixed window of degradations.
    Excludes the pure all-LOAD_FAIL / all-FEED_DARK windows those checks own."""
    obs = _classify_window(records, days)
    if len(obs) < len(days) or not obs:
        return None
    classes = [c for _, _, c, _ in obs]
    if any(c == HEALTHY for c in classes):
        return None
    if all(c == LOAD_FAIL for c in classes) or all(c == FEED_DARK for c in classes):
        return None  # a more specific check owns these
    detail = "; ".join(
        f"{d.isoformat()} [{c}: {', '.join(rs) or 'degraded'}]"
        for d, r, c, rs in obs
    )
    return (
        f"shadow scorer '{lane_name}' NOT ACTIONABLE / DEGRADED: {len(obs)} "
        f"consecutive session day(s) — {detail}. It runs but its output is not "
        f"trustworthy (stale artifact / thin coverage / missing provenance)."
    )


CHECKS = (
    check_feed_dark_streak,
    check_load_failure_streak,
    check_degraded_streak,
)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", default=None, help="ISO date (default: today)")
    args = parser.parse_args(argv)

    today = dt.date.fromisoformat(args.as_of) if args.as_of else dt.date.today()

    if not is_session_day(today):
        print(f"rq104 shadow-scorer sentinel: {today.isoformat()} is not an NYSE "
              f"session day — skip")
        return 0

    lanes = watched_lanes()
    days = last_session_days(today, STREAK_N)
    all_findings: list[str] = []
    rc = 0
    for lane in lanes:
        rc |= _patrol_lane(lane, days, today, all_findings)
    if not all_findings:
        print(f"rq104 shadow-scorer sentinel: {len(lanes)} lane(s) patrolled over "
              f"{days[0].isoformat()}..{days[-1].isoformat()} — no finding")
    return rc


def _patrol_lane(lane: WatchedLane, days: list[dt.date], today: dt.date,
                 out: list[str]) -> int:
    """Patrol ONE lane. Findings are prefixed with the lane so an operator
    reading a page knows which feed degraded, and appended to `out` so main
    can tell 'every lane clean' from 'nothing was checked'."""
    records = read_health_records(days, lane)

    # If NO day in the window had live runs at all, this is a liveness lapse,
    # not a shadow-degradation signal — stay quiet (the liveness checker owns it).
    if all(records.get(d) is None for d in days):
        print(f"rq104 shadow-scorer sentinel [{lane.name}]: no signal in window "
              f"{days[0].isoformat()}..{days[-1].isoformat()} — liveness domain, skip")
        return 0

    problems: list[str] = []
    for check in CHECKS:
        err = check(records, days, lane.name)
        if err:
            problems.append(err)

    if problems:
        body = "\n".join(problems)
        if lane.purpose:
            body += f"\n\nThis lane is {lane.purpose}."
        alert(
            f"rq104 SHADOW SCORER DEGRADED [{lane.name}]: "
            f"{len(problems)} issue(s) {today.isoformat()}",
            body,
            rq_root=RQ,
        )
        print(f"[{lane.name}] " + f"\n[{lane.name}] ".join(problems))
        out.extend(problems)
        return 1

    src = next((records[d].source for d in reversed(days) if records.get(d)), "n/a")
    print(f"rq104 shadow-scorer sentinel OK {today.isoformat()} "
          f"(lane='{lane.name}', source={src})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
