#!/usr/bin/env python
"""Vol-window activation-evidence readout — orch#1004 impl PR 2 (design AC3).

Daily after the 104 run (the rq104_blend_readout.py / pipeline#213 pattern):
sweep the vol-window lane's per-session license ledger
(``backtesting/renquant_104/logs/vol_window_license.jsonl``, written by
pipeline#294 when the lane's flag is enabled), join each session with the
lane's OWN runs DB (``data/runs.alpaca_shadow_vol_window.db`` —
``RENQUANT_READONLY_TAG`` isolation, daily_104.sh Step 5f) to freeze the
lane's scored universe, append one row per session to an append-only
HASH-CHAINED ledger, and back-fill realized top-decile spreads from the
maintained ``ticker_forward_returns`` surface once rows mature.

THE ESTIMAND (design AC3, frozen):

* DECISIVE per-session readout: realized **h=60** top-decile spread —
  mean(fwd_60d over the session's licensed-construction top decile) minus
  mean(fwd_60d over the lane's own universe) — matching the certification's
  estimand (label ``fwd_60d_excess``, 60-td blocks) ``[VERIFIED — prior
  work, orch#1001 prereg §3; orch#1003 results §8 pins]``. The universe-mean
  baseline is the design's DECLARED operational deviation from the certified
  DGTW-adjusted construction (orch#1004 AC3) — the activation ask must
  restate it.
* VELOCITY diagnostic: the realized **h=20** spread, recorded in the same
  row, earlier visibility, NEVER decisive — the two horizons are measured to
  disagree in this system (orch#999; restated in orch#1004 AC3).
* ACTIVATION-EVIDENCE counter: ON-state sessions (certified vol verdict,
  SPY vol20 > 0.135 strict) whose DECISIVE realized spread is positive;
  frozen burden >= 20 ``[DERIVED — orch#1001 prereg §5 states the doubled
  PARTIAL burden (>=40), fixing the CONFIRMED-branch base at >=20;
  orch#1004 §5 AC3]``. The counter is an operational burden toward an
  operator decision, never a statistical certification (orch#1004 §6).

LEDGER CONTRACT:

* One row per session date, idempotent (re-runs and backfills never
  duplicate). Append-time payload is IMMUTABLE and hash-chained:
  ``entry_sha = sha256(canonical(immutable payload incl. prev_sha))``,
  genesis ``prev_sha = "0"*64``. Maturation later fills ONLY the mutable
  realization/telemetry fields; the chain is verified over the immutable
  payload on every run and a broken chain alarms (exit 2) before any write.
* Realization per horizon is gated on the fwd table's OWN session calendar
  (the blend readout's ``_aged_dates`` technique — ``fwd IS NOT NULL`` alone
  does not prove the horizon elapsed), requires EVERY top-decile name
  resolvable (the certified selection must be complete), and requires
  universe coverage >= UNIVERSE_COVERAGE_FLOOR (declared operational rule;
  the universe mean is then taken over the resolvable names, with the
  shortfall recorded in the row — the blend readout's telemetry lesson).
* SILENT-FEED PARITY (the GOAL-1 AC3 guard, both directions): a license
  ledger session with no full lane run in the lane DB, or a full lane run
  with no license ledger row, alarms (exit 2) — the lane's flag and its
  funnel must move together or the evidence stream is quietly broken.

READ-ONLY against every production surface (both SQLite handles open with
``mode=ro``); writes ONLY the readout ledger under
``data/rq104_vol_window_readout/`` (additive; atomic replace, only when the
rendered bytes differ — the blend readout's read-must-not-mutate fix).

NOT SCHEDULED BY THIS PR: launchd manifest entries assert deployed state
(ops/run_surface_drift_check.py alarms on a manifested job missing from
disk), so the plist + ``ops/launchd_manifest.json`` entry land together in
the operator-gated deploy batch — see the progress doc.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from pathlib import Path

SCHEMA_VERSION = "rq104_vol_window_readout.v1"
LANE_TAG = "alpaca_shadow_vol_window"

#: Frozen activation burden [DERIVED — orch#1001 prereg §5 (base of the
#: doubled PARTIAL burden); orch#1004 §5 AC3]. Echoed, never re-derived.
ACTIVATION_TARGET_ON_SESSIONS = 20

#: Horizon maturity in trading sessions: horizon + 1 session settle — the
#: blend readout's convention (61 for fwd_60d; 21 was its fwd_20d value
#: before the 2026-07-29 horizon change).
MATURITY_TDAYS_60 = 61
MATURITY_TDAYS_20 = 21

#: Declared operational rule (module docstring): a session refuses to
#: realize a horizon while fewer than this fraction of its frozen universe
#: resolves in ticker_forward_returns. Strict 100% would let ONE lane-vs-
#: backfill watchlist drift name silently zero the evidence stream forever
#: (the blend readout records exactly that failure shape in its telemetry
#: comment); the floor + per-row shortfall telemetry keeps the estimand
#: honest without that cliff. The activation ask restates coverage.
UNIVERSE_COVERAGE_FLOOR = 0.90

#: Matches the house full-run bar (rq104_blend_readout.py /
#: scripts/kpi_scorecard.py / poc_transfer_coefficient.py).
MIN_FULL_RUN_CANDIDATES = 80

GENESIS_SHA = "0" * 64

#: The append-time payload — IMMUTABLE, covered by the hash chain, in this
#: exact order. Maturation may touch NOTHING in this tuple.
IMMUTABLE_KEYS = (
    "schema",
    "run_date",
    "lane_tag",
    "lane_run_id",
    "lane_run_found",
    "vol20",
    "threshold",
    "vol_verdict_on",
    "window_on",
    "license_applied",
    "regime",
    "hard_bear",
    "kill_switch",
    "base_reason",
    "top_decile",
    "universe",
    "universe_n_ledger",
    "universe_parity",
    "prev_sha",
)


# ── hash chain ───────────────────────────────────────────────────────────────

def _canonical_immutable(row: dict) -> str:
    return json.dumps({k: row.get(k) for k in IMMUTABLE_KEYS},
                      sort_keys=True, separators=(",", ":"), default=str)


def entry_sha(row: dict) -> str:
    """sha256 over the canonical immutable payload (prev_sha included)."""
    return hashlib.sha256(_canonical_immutable(row).encode("utf-8")).hexdigest()


def verify_chain(rows: list[dict]) -> str | None:
    """None when the chain holds; else a human-readable break description."""
    prev = GENESIS_SHA
    for i, row in enumerate(rows):
        if row.get("prev_sha") != prev:
            return (f"row {i} ({row.get('run_date')}): prev_sha "
                    f"{row.get('prev_sha')!r} != expected {prev!r}")
        expect = entry_sha(row)
        if row.get("entry_sha") != expect:
            return (f"row {i} ({row.get('run_date')}): entry_sha mismatch "
                    f"(immutable payload was altered after append)")
        prev = row["entry_sha"]
    return None


# ── inputs ───────────────────────────────────────────────────────────────────

def _connect_ro(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def load_license_sessions(ledger: Path) -> tuple[dict[str, dict], int]:
    """Per-date session rows from the lane's license ledger.

    Filters to LANE_TAG (a row from another lane — or a bare run of the lane
    config outside the wrapper, lane_tag null — is counted and skipped, never
    silently attributed). LAST row per date wins: a same-day re-run appends a
    fresh evaluation and the later one describes the session the lane DB's
    latest full run also describes."""
    sessions: dict[str, dict] = {}
    skipped = 0
    if not ledger.exists():
        return sessions, skipped
    for line in ledger.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            skipped += 1
            continue
        if rec.get("lane_tag") != LANE_TAG:
            skipped += 1
            continue
        date = str(rec.get("date") or "")[:10]
        if not date:
            skipped += 1
            continue
        sessions[date] = rec
    return sessions, skipped


def lane_full_runs(db: sqlite3.Connection) -> dict[str, str]:
    """date -> run_id of the lane's latest FULL run per date (candidate count
    >= MIN_FULL_RUN_CANDIDATES, run_type='live'). Same partial-run guard as
    rq104_blend_readout.latest_live_run — an intraday/partial insert must
    never supersede the full run."""
    rows = db.execute(
        "SELECT p.run_id, p.run_date, p.created_at FROM pipeline_runs p "
        "JOIN (SELECT run_id, COUNT(*) n FROM candidate_scores "
        "      GROUP BY run_id HAVING n >= ?) c ON c.run_id = p.run_id "
        "WHERE p.run_type = 'live' "
        "ORDER BY p.created_at",
        (MIN_FULL_RUN_CANDIDATES,),
    ).fetchall()
    out: dict[str, str] = {}
    for run_id, run_date, _created in rows:   # ordered ASC: later wins
        out[str(run_date)[:10]] = run_id
    return out


def lane_universe(db: sqlite3.Connection, run_id: str) -> list[str]:
    rows = db.execute(
        "SELECT ticker FROM candidate_scores "
        "WHERE run_id = ? AND panel_score IS NOT NULL", (run_id,)).fetchall()
    return sorted({str(r[0]) for r in rows})


# ── append ───────────────────────────────────────────────────────────────────

def build_row(date: str, session: dict, run_id: str | None,
              universe: list[str], prev_sha: str) -> dict:
    universe_n_ledger = session.get("universe_n")
    row = {
        "schema": SCHEMA_VERSION,
        "run_date": date,
        "lane_tag": LANE_TAG,
        "lane_run_id": run_id,
        "lane_run_found": run_id is not None,
        "vol20": session.get("vol20"),
        "threshold": session.get("threshold"),
        "vol_verdict_on": session.get("vol_verdict_on"),
        "window_on": session.get("window_on"),
        "license_applied": session.get("license_applied"),
        "regime": session.get("regime"),
        "hard_bear": session.get("hard_bear"),
        "kill_switch": session.get("kill_switch"),
        "base_reason": session.get("base_reason"),
        "top_decile": sorted(str(t) for t in (session.get("top_decile") or [])),
        "universe": universe,
        # Cross-field parity (digests-verify-identity lesson): the ledger's
        # own count of the finite-scored cross-section vs the lane DB's.
        "universe_n_ledger": universe_n_ledger,
        "universe_parity": (len(universe) == universe_n_ledger
                            if isinstance(universe_n_ledger, int) and universe
                            else None),
        "prev_sha": prev_sha,
        # Mutable from here on (outside the chain).
        "realized_20": False,
        "realized_60": False,
    }
    row["entry_sha"] = entry_sha(row)
    return row


# ── maturation ───────────────────────────────────────────────────────────────

def _aged_dates(db: sqlite3.Connection, min_tdays: int) -> set[str]:
    """Dates whose full min_tdays-session forward window has elapsed, judged
    on the fwd table's OWN distinct-session calendar (rq104_blend_readout's
    `_aged_dates`; `fwd IS NOT NULL` alone is NOT aging evidence)."""
    sessions = sorted({str(r[0])[:10] for r in db.execute(
        "SELECT DISTINCT as_of_date FROM ticker_forward_returns")})
    if len(sessions) <= min_tdays:
        return set()
    return set(sessions[: len(sessions) - min_tdays])


def _fwd_map(db: sqlite3.Connection, col: str) -> dict[tuple[str, str], float]:
    rows = db.execute(
        f"SELECT ticker, as_of_date, {col} FROM ticker_forward_returns "  # noqa: S608 — col from the frozen pair below
        f"WHERE {col} IS NOT NULL").fetchall()
    return {(str(t), str(d)[:10]): float(v) for t, d, v in rows}


def mature_fill(rows: list[dict], fwd_db: sqlite3.Connection) -> int:
    """Fill realized spreads per horizon for aged rows, in place.

    Telemetry (resolvable counts, coverage) is recorded on EVERY pass for
    every unrealized row, so a permanently-stuck session is diagnosable
    instead of looking untouched (the blend readout's counters lesson).
    Only mutable fields are touched — the hash chain is over IMMUTABLE_KEYS.
    """
    horizons = (("20", "fwd_20d", MATURITY_TDAYS_20),
                ("60", "fwd_60d", MATURITY_TDAYS_60))
    filled = 0
    for suffix, col, min_tdays in horizons:
        fmap = _fwd_map(fwd_db, col)
        aged = _aged_dates(fwd_db, min_tdays)
        for row in rows:
            if row.get(f"realized_{suffix}"):
                continue
            date = row["run_date"]
            top = row.get("top_decile") or []
            uni = row.get("universe") or []
            top_vals = [fmap.get((t, date)) for t in top]
            uni_vals = [fmap.get((t, date)) for t in uni]
            n_top_ok = sum(v is not None for v in top_vals)
            n_uni_ok = sum(v is not None for v in uni_vals)
            coverage = (n_uni_ok / len(uni)) if uni else 0.0
            row[f"aged_{suffix}"] = date in aged
            row["n_top"] = len(top)
            row["n_universe"] = len(uni)
            row[f"n_top_resolvable_{suffix}"] = n_top_ok
            row[f"n_universe_resolvable_{suffix}"] = n_uni_ok
            row[f"universe_coverage_{suffix}"] = round(coverage, 4)
            if (row.get("lane_run_found")
                    and top and uni
                    and row[f"aged_{suffix}"]
                    and n_top_ok == len(top)
                    and coverage >= UNIVERSE_COVERAGE_FLOOR):
                top_mean = sum(v for v in top_vals if v is not None) / n_top_ok
                uni_mean = sum(v for v in uni_vals if v is not None) / n_uni_ok
                row[f"spread_{suffix}"] = top_mean - uni_mean
                row[f"realized_{suffix}"] = True
                filled += 1
    return filled


# ── the counter ──────────────────────────────────────────────────────────────

def activation_counter(rows: list[dict]) -> dict:
    """The AC3 counter. ON-state = the certified vol verdict recorded in the
    session row; DECISIVE = realized h=60 spread > 0; h=20 is velocity only
    and never enters the decisive count."""
    def _count(horizon: str, require_window: bool = False) -> int:
        n = 0
        for r in rows:
            if r.get("vol_verdict_on") is not True:
                continue
            if require_window and r.get("window_on") is not True:
                continue
            if r.get(f"realized_{horizon}") and (r.get(f"spread_{horizon}") or 0) > 0:
                n += 1
        return n
    on_total = sum(1 for r in rows if r.get("vol_verdict_on") is True)
    return {
        "target": ACTIVATION_TARGET_ON_SESSIONS,
        "on_sessions_recorded": on_total,
        "decisive_h60_positive": _count("60"),
        "decisive_h60_positive_window_only": _count("60", require_window=True),
        "velocity_h20_positive": _count("20"),
    }


def print_counter(counter: dict) -> None:
    print(
        f"ACTIVATION-EVIDENCE (decisive, certified h=60): "
        f"{counter['decisive_h60_positive']}/{counter['target']} ON-state "
        f"sessions with positive realized top-decile spread "
        f"[frozen burden >= {counter['target']}, orch#1001 §5 / orch#1004 AC3]"
    )
    print(
        f"  window-restricted (ON AND not-BEAR AND no kill): "
        f"{counter['decisive_h60_positive_window_only']}"
        f" | velocity diagnostic h=20 (never decisive): "
        f"{counter['velocity_h20_positive']}"
        f" | ON-state sessions recorded: {counter['on_sessions_recorded']}"
    )


# ── ledger io ────────────────────────────────────────────────────────────────

def load_ledger(ledger: Path) -> list[dict]:
    if not ledger.exists():
        return []
    return [json.loads(x) for x in
            ledger.read_text(encoding="utf-8").splitlines() if x.strip()]


def write_ledger(ledger: Path, rows: list[dict]) -> bool:
    """Atomic, and ONLY when the rendered bytes differ — reading the evidence
    must not mutate it (the blend readout's measured fix, verbatim intent)."""
    rendered = "".join(json.dumps(r, sort_keys=True, default=str) + "\n"
                       for r in rows)
    try:
        current = ledger.read_text(encoding="utf-8")
    except OSError:
        current = None      # unreadable/absent -> write; NOT "assume it matches"
    if current == rendered:
        return False
    ledger.parent.mkdir(parents=True, exist_ok=True)
    tmp = ledger.with_name(ledger.name + ".tmp")
    tmp.write_text(rendered, encoding="utf-8")
    os.replace(tmp, ledger)
    return True


# ── main ─────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo-dir", default="/Users/renhao/git/github/RenQuant")
    ap.add_argument("--license-ledger", default=None,
                    help="lane session ledger (default: "
                         "<repo>/backtesting/renquant_104/logs/vol_window_license.jsonl)")
    ap.add_argument("--lane-db", default=None,
                    help="lane runs DB (default: <repo>/data/runs.%s.db)" % LANE_TAG)
    ap.add_argument("--fwd-db", default=None,
                    help="ticker_forward_returns surface (default: "
                         "<repo>/data/runs.alpaca.db, opened read-only)")
    ap.add_argument("--ledger", default=None,
                    help="readout ledger (default: "
                         "<repo>/data/rq104_vol_window_readout/ledger.jsonl)")
    args = ap.parse_args(argv)
    repo = Path(args.repo_dir)
    license_ledger = Path(args.license_ledger) if args.license_ledger else \
        repo / "backtesting" / "renquant_104" / "logs" / "vol_window_license.jsonl"
    lane_db_path = Path(args.lane_db) if args.lane_db else \
        repo / "data" / f"runs.{LANE_TAG}.db"
    fwd_db_path = Path(args.fwd_db) if args.fwd_db else \
        repo / "data" / "runs.alpaca.db"
    ledger = Path(args.ledger) if args.ledger else \
        repo / "data" / "rq104_vol_window_readout" / "ledger.jsonl"

    if not license_ledger.exists() and not lane_db_path.exists():
        print(f"vol-window lane not deployed yet ({license_ledger.name} and "
              f"{lane_db_path.name} both absent) — nothing to do")
        return 0

    rows = load_ledger(ledger)
    broken = verify_chain(rows)
    if broken is not None:
        print(f"ALARM: readout ledger hash chain BROKEN — {broken}. "
              f"Refusing to write; investigate {ledger}.")
        return 2

    sessions, skipped = load_license_sessions(license_ledger)
    if skipped:
        print(f"skipped {skipped} license-ledger line(s) not attributable to "
              f"{LANE_TAG} (foreign/absent lane_tag or malformed)")

    runs_by_date: dict[str, str] = {}
    lane_db = None
    if lane_db_path.exists():
        lane_db = _connect_ro(lane_db_path)   # stays open for universe queries
        runs_by_date = lane_full_runs(lane_db)

    alarms: list[str] = []
    known_dates = {r["run_date"] for r in rows}
    prev = rows[-1]["entry_sha"] if rows else GENESIS_SHA
    appended = 0
    for date in sorted(sessions):
        if date in known_dates:
            continue
        run_id = runs_by_date.get(date)
        universe: list[str] = []
        if run_id is not None and lane_db is not None:
            universe = lane_universe(lane_db, run_id)
        if run_id is None:
            alarms.append(
                f"license session {date} has NO full lane run in "
                f"{lane_db_path.name} (>= {MIN_FULL_RUN_CANDIDATES} scored "
                f"candidates) — the lane's funnel record is missing; the row "
                f"is appended lane_run_found=false and can never realize")
        row = build_row(date, sessions[date], run_id, universe, prev)
        rows.append(row)
        prev = row["entry_sha"]
        known_dates.add(date)
        appended += 1

    # Parity, the other direction: a full lane run whose session has NO
    # license ledger row means the lane ran with the flag not evaluating —
    # the silent-feed shape this readout exists to end.
    for date in sorted(runs_by_date):
        if date not in sessions:
            alarms.append(
                f"full lane run {runs_by_date[date]} ({date}) has NO "
                f"{LANE_TAG} row in {license_ledger.name} — the vol-window "
                f"flag did not evaluate on a session the lane ran")

    if appended:
        print(f"appended {appended} session row(s)")

    filled = 0
    if fwd_db_path.exists():
        fwd_db = _connect_ro(fwd_db_path)
        filled = mature_fill(rows, fwd_db)
        if filled:
            print(f"matured: realized {filled} horizon fill(s)")
    else:
        print(f"WARN: forward-returns surface absent ({fwd_db_path}) — "
              f"no maturation this pass")

    if write_ledger(ledger, rows):
        print(f"ledger written: {ledger} ({len(rows)} row(s))")

    print_counter(activation_counter(rows))

    for a in alarms:
        print(f"ALARM: {a}")
    return 2 if alarms else 0


if __name__ == "__main__":
    sys.exit(main())
