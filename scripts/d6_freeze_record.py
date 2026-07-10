#!/usr/bin/env python3
"""D6 freeze-record generator / verifier — preregistered replay protocol §1.

The D6 protocol (doc/design/2026-07-09-governor-prereg-replay-protocol.md,
orchestrator PR #443) requires that BEFORE any evaluation arm runs, the exact
replay inputs are frozen in a pushed commit: the concrete session ID lists
(tuning + evaluation, disjoint, nested selection), the sim-DB content hash,
the data cutoff, and the as-of model/calibrator artifact timestamps. This
script generates that freeze-record artifact and re-verifies it later.

THE FREEZE COMMIT FOR A VALID RUN MUST BE PUSHED BEFORE ANY ARM RUNS.
This tool only produces the artifact; committing/pushing it first is the
operator/agent discipline the protocol enforces.

Session rule (mirrors the WF-cut loader the replay harness uses —
``renquant_pipeline.kernel.portfolio_qp.wf_replay_loader.
load_replay_bars_from_sim_db``): a replay session is a ``date`` for which the
inner join of ``score_distribution`` (``mu``/``sigma`` non-NULL) and
``ticker_forward_returns`` (forward column non-NULL) yields at least
MIN_ROWS_PER_SESSION rows. The DB is opened strictly read-only
(``file:...?mode=ro``); this script never writes any production path.

Freeze rule (§1, mechanical):
  1. enumerate all sessions available in the DB, per forward horizon;
  2. EXCLUDE every session inside the hypothesis-generation window
     (default 2026-06-23 → 2026-07-09, endpoints inclusive) and any
     individually inspected session passed via --exclude-session;
  3. deterministically split the remainder into TUNING, EMBARGO, and
     EVALUATION ranges by CHRONOLOGICAL ORDER (merged D6 §2 fold-
     construction rule, codex review on PR #446 — this replaces an earlier
     seeded-hash nested-selection draft that this protocol never froze):
     sort the UNION of kept horizon session dates chronologically; the
     earliest ceil(N/2) dates are TUNING (used only for the §1 nested-
     selection hyperparameter choices); the following
     DEFAULT_EMBARGO_TRADING_DAYS (60) dates are a PURGED embargo, excluded
     from both subsets (long enough to exceed the longest forward horizon
     evaluated, so no evaluation-range forward-return window shares
     calendar days with the tuning range); the remainder is EVALUATION
     (used only for §3 estimands, §4 gates, and the §5 decision rule).
     Assignment is computed ONCE on the union and then intersected per
     horizon, so a date lands in the SAME subset for every horizon — tuning
     at one horizon can never touch evaluation sessions of another.
  4. emit a freeze-record JSON carrying exact session IDs per subset
     (tuning / embargo / evaluation, embargo IDs explicit, not just a
     count), the DB sha256, the per-horizon data cutoff, as-of artifact
     stats (path + mtime + sha256) for the live model/calibrator bundle,
     and the generator version + args (including the embargo length,
     frozen into the record so it can be reproduced later).

Verify mode (--verify RECORD.json) recomputes the record from the args
stored inside it (paths overridable with --db / --artifacts-root) and diffs
every field except the generation timestamp. Exit 0 = no drift, 1 = drift,
2 = could not evaluate.

Usage:
  d6_freeze_record.py --out doc/research/evidence/d6/freeze.json
  d6_freeze_record.py --verify doc/research/evidence/d6/freeze.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Sequence

RECORD_VERSION = "d6-freeze-v2"
GENERATOR_SCRIPT = "scripts/d6_freeze_record.py"
GENERATOR_VERSION = "2.0.0"
PROTOCOL_REF = (
    "doc/design/2026-07-09-governor-prereg-replay-protocol.md "
    "(D6 §2 fold construction; orchestrator PR #443)"
)
SPLIT_RULE_VERSION = "chronological-ceil-half-embargo-v1"

DEFAULT_DB = "/Users/renhao/git/github/RenQuant/data/sim_runs.db"
DEFAULT_EXCLUDE_WINDOW = "2026-06-23:2026-07-09"
DEFAULT_EMBARGO_TRADING_DAYS = 60
DEFAULT_HORIZONS = "1,60"
# The live model bundle the replay's mu/sigma trace was produced by — the
# umbrella strategy dir (same resolution base as
# scripts/check_model_bundle_consistency.py --strategy-dir default).
DEFAULT_ARTIFACTS_ROOT = "/Users/renhao/git/github/RenQuant/backtesting/renquant_104"
DEFAULT_ARTIFACTS = (
    "artifacts/prod/panel-ltr.alpha158_fund.json",       # panel-LTR scorer (model)
    "artifacts/prod/panel-rank-calibration.json",        # global calibrator
    "artifacts/prod/ngboost-head.alpha158_fund.json",    # sigma head
)

# Map horizon days -> ticker_forward_returns column (same contract as the
# pipeline wf_replay_loader; loud failure on unsupported horizons).
FWD_HORIZON_COLUMNS = {1: "fwd_1d", 5: "fwd_5d", 10: "fwd_10d", 20: "fwd_20d", 60: "fwd_60d"}

# The loader emits a bar only when a date has >= 2 usable joined rows.
MIN_ROWS_PER_SESSION = 2

# Fields excluded from --verify drift comparison (regeneration noise only).
VOLATILE_FIELDS = {"generated_at_utc"}

_MISSING = object()


# --------------------------------------------------------------------- utils
def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _fwd_column(horizon_days: int) -> str:
    col = FWD_HORIZON_COLUMNS.get(int(horizon_days))
    if col is None:
        raise ValueError(
            f"fwd horizon {horizon_days}d unsupported by ticker_forward_returns; "
            f"supported: {sorted(FWD_HORIZON_COLUMNS)}"
        )
    return col


def parse_window(spec: str) -> tuple[str, str]:
    """Parse 'YYYY-MM-DD:YYYY-MM-DD' (endpoints inclusive)."""
    parts = spec.split(":")
    if len(parts) != 2:
        raise ValueError(f"--exclude-window must be START:END, got {spec!r}")
    start, end = (p.strip() for p in parts)
    for p in (start, end):
        datetime.strptime(p, "%Y-%m-%d")  # loud on malformed dates
    if start > end:
        raise ValueError(f"--exclude-window start {start} > end {end}")
    return start, end


def parse_horizons(spec: str) -> list[int]:
    horizons = sorted({int(tok) for tok in spec.split(",") if tok.strip()})
    if not horizons:
        raise ValueError("--horizons is empty")
    for h in horizons:
        _fwd_column(h)  # validate early, loud
    return horizons


# ------------------------------------------------------------ session census
def connect_readonly(db_path: Path) -> sqlite3.Connection:
    """Open the sim DB strictly read-only. Never write production paths."""
    if not db_path.is_file():
        raise SystemExit(f"DB not found: {db_path}")
    return sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True)


def enumerate_sessions(conn: sqlite3.Connection, horizon_days: int) -> list[str]:
    """All session dates loadable at this horizon (loader-faithful rule).

    Mirrors load_replay_bars_from_sim_db: INNER JOIN score_distribution
    (mu, sigma non-NULL) with ticker_forward_returns (fwd col non-NULL),
    counting joined ROWS per date (the loader counts rows, not distinct
    tickers) and requiring >= MIN_ROWS_PER_SESSION.

    PARITY GATE (codex review, PR #446): this enumeration is asserted equal
    to the ACTUAL pipeline loader's output in tests/test_d6_freeze_record.py
    ::test_session_parity_with_pipeline_loader. If the loader's session
    semantics ever change, that test fails and THIS query must be updated to
    match — the loader is ground truth for what the replay consumes.
    """
    fwd_col = _fwd_column(horizon_days)
    cur = conn.execute(
        f"""
        SELECT s.date
        FROM score_distribution s
        INNER JOIN ticker_forward_returns t
            ON s.date = t.as_of_date AND s.ticker = t.ticker
        WHERE s.mu IS NOT NULL
          AND s.sigma IS NOT NULL
          AND t.{fwd_col} IS NOT NULL
        GROUP BY s.date
        HAVING COUNT(*) >= ?
        ORDER BY s.date ASC
        """,
        (MIN_ROWS_PER_SESSION,),
    )
    return [str(row[0]) for row in cur.fetchall()]


# -------------------------------------------------------- deterministic split
def assign_chronological_split(
    union_dates: Sequence[str], embargo_trading_days: int
) -> tuple[list[str], list[str], list[str]]:
    """Chronological two-range split with a purged embargo (merged D6 §2).

    ``union_dates`` MUST already be sorted chronologically (the caller
    builds it that way). The earliest ``ceil(N/2)`` dates are TUNING; the
    following ``embargo_trading_days`` dates are a PURGED embargo excluded
    from both subsets; the remainder is EVALUATION. This is a pure
    accounting split over the UNION of kept horizon dates — the same three
    date sets are then intersected per horizon, so assignment is identical
    across horizons (the protocol's nested-selection rule): tuning at one
    horizon can never touch evaluation (or embargo) sessions of another.

    Returns (tuning_ids, embargo_ids, evaluation_ids), each chronologically
    ordered and mutually disjoint; their union is exactly ``union_dates``.
    """
    if embargo_trading_days < 0:
        raise ValueError(
            f"--embargo-trading-days must be >= 0, got {embargo_trading_days}"
        )
    n = len(union_dates)
    n_tuning = math.ceil(n / 2)
    tuning = list(union_dates[:n_tuning])
    embargo = list(union_dates[n_tuning:n_tuning + embargo_trading_days])
    evaluation = list(union_dates[n_tuning + embargo_trading_days:])
    return tuning, embargo, evaluation


# ------------------------------------------------------------------ artifacts
def collect_artifact(root: Path, rel_path: str) -> dict:
    """Read-only stat + hash of one as-of artifact. Absence is recorded, not fatal."""
    path = root / rel_path
    item: dict = {
        "rel_path": rel_path,
        "abs_path": str(path),
        "present": path.is_file(),
    }
    if item["present"]:
        stat = path.stat()
        item["mtime"] = datetime.fromtimestamp(stat.st_mtime).isoformat()
        item["size_bytes"] = stat.st_size
        item["sha256"] = sha256_file(path)
    return item


# --------------------------------------------------------------- record build
def build_record(
    *,
    db_path: Path,
    exclude_window: tuple[str, str],
    exclude_sessions: Sequence[str],
    embargo_trading_days: int,
    horizons: Sequence[int],
    artifacts_root: Path,
    artifacts: Sequence[str],
) -> dict:
    """Generate the full freeze record (pure read-only)."""
    db_stat = db_path.stat() if db_path.is_file() else None
    if db_stat is None:
        raise SystemExit(f"DB not found: {db_path}")
    db_sha = sha256_file(db_path)

    conn = connect_readonly(db_path)
    try:
        sessions_by_horizon = {h: enumerate_sessions(conn, h) for h in horizons}
    finally:
        conn.close()

    win_start, win_end = exclude_window
    manual_excluded = set(exclude_sessions)

    def _is_excluded(date: str) -> bool:
        return (win_start <= date <= win_end) or date in manual_excluded

    kept_by_horizon: dict[int, list[str]] = {}
    excluded_by_horizon: dict[int, list[str]] = {}
    for h, ids in sessions_by_horizon.items():
        kept_by_horizon[h] = [d for d in ids if not _is_excluded(d)]
        excluded_by_horizon[h] = [d for d in ids if _is_excluded(d)]

    union_dates = sorted({d for ids in kept_by_horizon.values() for d in ids})
    tuning_ids_union, embargo_ids_union, eval_ids_union = assign_chronological_split(
        union_dates, embargo_trading_days
    )
    tuning_set = set(tuning_ids_union)
    embargo_set = set(embargo_ids_union)
    eval_set = set(eval_ids_union)

    horizons_out = {}
    for h in horizons:
        kept = kept_by_horizon[h]
        tuning_ids = [d for d in kept if d in tuning_set]
        embargo_ids = [d for d in kept if d in embargo_set]
        eval_ids = [d for d in kept if d in eval_set]
        horizons_out[f"fwd_{h}d"] = {
            "n_available": len(sessions_by_horizon[h]),
            "n_excluded": len(excluded_by_horizon[h]),
            "n_kept": len(kept),
            "first": kept[0] if kept else None,
            "last": kept[-1] if kept else None,
            "tuning": {"n": len(tuning_ids), "ids": tuning_ids},
            "embargo": {"n": len(embargo_ids), "ids": embargo_ids},
            "evaluation": {"n": len(eval_ids), "ids": eval_ids},
        }

    return {
        "freeze_record_version": RECORD_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "protocol": PROTOCOL_REF,
        "generator": {
            "script": GENERATOR_SCRIPT,
            "version": GENERATOR_VERSION,
            "args": {
                "db": str(db_path),
                "exclude_window": [win_start, win_end],
                "exclude_sessions": sorted(manual_excluded),
                "embargo_trading_days": embargo_trading_days,
                "horizons": list(horizons),
                "artifacts_root": str(artifacts_root),
                "artifacts": list(artifacts),
                "min_rows_per_session": MIN_ROWS_PER_SESSION,
            },
        },
        "session_rule": (
            "date with >= "
            f"{MIN_ROWS_PER_SESSION} rows in score_distribution (mu, sigma non-NULL) "
            "INNER JOIN ticker_forward_returns (fwd column non-NULL); mirrors "
            "renquant_pipeline.kernel.portfolio_qp.wf_replay_loader."
            "load_replay_bars_from_sim_db"
        ),
        "split_rule": (
            f"[{SPLIT_RULE_VERSION}] sort the union of kept session dates "
            "chronologically; earliest ceil(N/2) dates = TUNING; the following "
            f"{embargo_trading_days} trading days = PURGED EMBARGO (excluded from "
            "both subsets); remainder = EVALUATION. Assignment is computed once "
            "on the union and intersected per horizon, so it is identical across "
            "horizons (nested selection, protocol D6 §2)"
        ),
        "source_db": {
            "path": str(db_path),
            "sha256": db_sha,
            "size_bytes": db_stat.st_size,
            "mtime": datetime.fromtimestamp(db_stat.st_mtime).isoformat(),
        },
        "exclusion": {
            "window": [win_start, win_end],
            "window_endpoints_inclusive": True,
            "manual_exclude_sessions": sorted(manual_excluded),
            "excluded_session_ids": {
                f"fwd_{h}d": excluded_by_horizon[h] for h in horizons
            },
        },
        "split": {
            "rule_version": SPLIT_RULE_VERSION,
            "embargo_trading_days": embargo_trading_days,
            "union_n": len(union_dates),
            "tuning_n": len(tuning_ids_union),
            "embargo_n": len(embargo_ids_union),
            "evaluation_n": len(eval_ids_union),
            "embargo_session_ids": embargo_ids_union,
        },
        "data_cutoff": {
            f"fwd_{h}d_max_session": (
                kept_by_horizon[h][-1] if kept_by_horizon[h] else None
            )
            for h in horizons
        },
        "horizons": horizons_out,
        "artifacts": {
            "root": str(artifacts_root),
            "items": [collect_artifact(artifacts_root, rel) for rel in artifacts],
        },
    }


# ---------------------------------------------------------------------- diff
def diff_records(old: dict, new: dict, skip_paths: set[str]) -> list[tuple[str, object, object]]:
    """Structural diff; returns (dotted_path, old, new) triples. Volatile and
    caller-skipped paths are ignored. String-list diffs are summarised as
    added/removed sets so a 400-session drift prints readably."""
    out: list[tuple[str, object, object]] = []

    def walk(a: object, b: object, path: str) -> None:
        if path in skip_paths or path in VOLATILE_FIELDS:
            return
        if a is _MISSING or b is _MISSING:
            out.append((path, a if a is not _MISSING else "<missing>",
                        b if b is not _MISSING else "<missing>"))
            return
        if isinstance(a, dict) and isinstance(b, dict):
            for key in sorted(set(a) | set(b)):
                walk(a.get(key, _MISSING), b.get(key, _MISSING),
                     f"{path}.{key}" if path else str(key))
            return
        if isinstance(a, list) and isinstance(b, list):
            if a == b:
                return
            if all(isinstance(x, str) for x in a) and all(isinstance(x, str) for x in b):
                removed = sorted(set(a) - set(b))
                added = sorted(set(b) - set(a))
                if added or removed:
                    out.append((
                        path,
                        f"-{len(removed)}: {removed[:5]}{'...' if len(removed) > 5 else ''}",
                        f"+{len(added)}: {added[:5]}{'...' if len(added) > 5 else ''}",
                    ))
                else:
                    out.append((path, "<order changed>", "<order changed>"))
                return
            if len(a) == len(b):
                for i, (ai, bi) in enumerate(zip(a, b)):
                    walk(ai, bi, f"{path}.{i}")
                return
            out.append((path, f"<list len {len(a)}>", f"<list len {len(b)}>"))
            return
        if a != b:
            out.append((path, a, b))

    walk(old, new, "")
    return out


# ---------------------------------------------------------------------- main
def _record_from_args(args: argparse.Namespace, stored: Optional[dict] = None) -> dict:
    """Build a record from CLI args, or (verify mode) from a stored record's
    generator args with optional --db / --artifacts-root overrides."""
    if stored is None:
        return build_record(
            db_path=Path(args.db),
            exclude_window=parse_window(args.exclude_window),
            exclude_sessions=args.exclude_session,
            embargo_trading_days=args.embargo_trading_days,
            horizons=parse_horizons(args.horizons),
            artifacts_root=Path(args.artifacts_root),
            artifacts=args.artifact or list(DEFAULT_ARTIFACTS),
        )
    gen_args = stored.get("generator", {}).get("args", {})
    required = ("db", "exclude_window", "embargo_trading_days", "horizons",
                "artifacts_root", "artifacts")
    missing = [k for k in required if k not in gen_args]
    if missing:
        raise SystemExit(f"record is missing generator.args keys: {missing}")
    return build_record(
        db_path=Path(args.db if args.db_overridden else gen_args["db"]),
        exclude_window=tuple(gen_args["exclude_window"]),
        exclude_sessions=gen_args.get("exclude_sessions", []),
        embargo_trading_days=int(gen_args["embargo_trading_days"]),
        horizons=[int(h) for h in gen_args["horizons"]],
        artifacts_root=Path(
            args.artifacts_root if args.artifacts_root_overridden
            else gen_args["artifacts_root"]
        ),
        artifacts=list(gen_args["artifacts"]),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "The freeze COMMIT for a valid D6 run must be pushed BEFORE any "
            "arm runs (protocol §1). Run --verify against the committed record "
            "immediately before arm execution; exit 1 means the inputs drifted "
            "and the run is void."
        ),
    )
    parser.add_argument("--db", default=DEFAULT_DB,
                        help=f"sim_runs.db path, opened READ-ONLY (default: {DEFAULT_DB})")
    parser.add_argument("--exclude-window", default=DEFAULT_EXCLUDE_WINDOW,
                        help="hypothesis-generation window START:END, inclusive "
                             f"(default: {DEFAULT_EXCLUDE_WINDOW})")
    parser.add_argument("--exclude-session", action="append", default=[],
                        metavar="YYYY-MM-DD",
                        help="individually inspected session to exclude (repeatable; "
                             "protocol §1 evidence-memo rule)")
    parser.add_argument("--embargo-trading-days", type=int,
                        default=DEFAULT_EMBARGO_TRADING_DAYS,
                        help="purged-embargo length in trading days between the "
                             "tuning and evaluation ranges (default: "
                             f"{DEFAULT_EMBARGO_TRADING_DAYS}, protocol D6 §2)")
    parser.add_argument("--horizons", default=DEFAULT_HORIZONS,
                        help=f"comma-separated fwd horizons in days (default: {DEFAULT_HORIZONS})")
    parser.add_argument("--artifacts-root", default=DEFAULT_ARTIFACTS_ROOT,
                        help="umbrella strategy dir for as-of artifact stats "
                             f"(default: {DEFAULT_ARTIFACTS_ROOT})")
    parser.add_argument("--artifact", action="append", default=None, metavar="REL_PATH",
                        help="artifact rel-path under --artifacts-root (repeatable; "
                             f"default: {list(DEFAULT_ARTIFACTS)})")
    parser.add_argument("--out", default=None,
                        help="write the freeze record JSON here (default: stdout)")
    parser.add_argument("--verify", default=None, metavar="RECORD_JSON",
                        help="recompute from the record's stored args and diff; "
                             "exit 1 on any drift")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    argv_list = list(sys.argv[1:] if argv is None else argv)
    args.db_overridden = "--db" in argv_list
    args.artifacts_root_overridden = "--artifacts-root" in argv_list

    if args.verify:
        record_path = Path(args.verify)
        if not record_path.is_file():
            print(f"ERROR: record not found: {record_path}", file=sys.stderr)
            return 2
        try:
            stored = json.loads(record_path.read_text())
        except json.JSONDecodeError as exc:
            print(f"ERROR: record is not valid JSON: {exc}", file=sys.stderr)
            return 2
        try:
            recomputed = _record_from_args(args, stored=stored)
        except (SystemExit, ValueError) as exc:
            print(f"ERROR: could not recompute record: {exc}", file=sys.stderr)
            return 2
        # Path (and copy-mtime) fields are exempt ONLY when explicitly
        # overridden on the CLI — verifying a byte-identical copy at another
        # path is legitimate (sha256 still guards content); silent path or
        # timestamp drift on the recorded paths is not.
        skip: set[str] = set()
        if args.db_overridden:
            skip |= {"source_db.path", "source_db.mtime", "generator.args.db"}
        if args.artifacts_root_overridden:
            skip |= {"artifacts.root", "generator.args.artifacts_root"}

        def _overridden_artifact_field(path: str) -> bool:
            return (
                args.artifacts_root_overridden
                and path.startswith("artifacts.items.")
                and (path.endswith(".abs_path") or path.endswith(".mtime"))
            )

        drifts = [
            d for d in diff_records(stored, recomputed, skip)
            if not _overridden_artifact_field(d[0])
        ]
        if not drifts:
            print(f"VERIFY OK: {record_path} — no drift "
                  f"(db sha256 {stored['source_db']['sha256'][:12]}..., "
                  f"{stored['split']['tuning_n']} tuning / "
                  f"{stored['split']['embargo_n']} embargo / "
                  f"{stored['split']['evaluation_n']} evaluation sessions)")
            return 0
        print(f"VERIFY FAILED: {record_path} — {len(drifts)} drifted field(s):",
              file=sys.stderr)
        for path, old, new in drifts:
            print(f"  {path}:\n    record:     {old}\n    recomputed: {new}",
                  file=sys.stderr)
        print("Drift voids the freeze (protocol §1): re-freeze with a new record "
              "+ new commit before running any arm.", file=sys.stderr)
        return 1

    # ---- generation mode
    try:
        record = _record_from_args(args)
    except ValueError as exc:
        parser.error(str(exc))
    payload = json.dumps(record, indent=2, sort_keys=False) + "\n"
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(payload)
        print(f"freeze record written: {out_path}")
    else:
        sys.stdout.write(payload)
    split = record["split"]
    print(
        f"sessions: union={split['union_n']} tuning={split['tuning_n']} "
        f"embargo={split['embargo_n']} evaluation={split['evaluation_n']} "
        f"(embargo_trading_days={args.embargo_trading_days}); db sha256 "
        f"{record['source_db']['sha256'][:12]}...",
        file=sys.stderr,
    )
    print(
        "REMINDER: commit + push this record BEFORE running any arm "
        "(protocol §1 freeze discipline).",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
