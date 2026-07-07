#!/usr/bin/env python3
"""rq105: export the FROZEN batch score vector for today's session (N1 open
item #1 — the producer for shadow_realtime_serving --batch-scores-json).

Reads the latest daily FULL run strictly BEFORE today's session from
runs.alpaca.db (the 13:55 PT batch of the prior session is the class-A frozen
signal for today, #208 §6) and writes:

  data/rq105/batch_scores_<today>.json        flat {ticker: panel_score}
  data/rq105/batch_scores_<today>.meta.json   {run_id, score_kind, n, exported_at, ...}

Read-only against the DB; writes only the dedicated data/rq105/ path. Fails
loudly (exit 1 + ntfy via wrapper) if no qualifying run exists — the shadow
serving driver then skips the day rather than serving a stale vector silently.

Codex #236 review (round 2) — this module previously selected the
lexicographically-largest run_id with >=80 candidate_scores rows straight off
`candidate_scores`, with no check that a `pipeline_runs` row for it existed,
that it completed successfully, that it carried a strategy/artifact/config
fingerprint, or that it was actually the canonical latest run for that date
(run_id's random uuid suffix does not sort chronologically). It also wrote the
score/meta JSON as two separate direct-to-final-path writes (a crash between
them exposes a mismatched pair) and accepted as few as 40/80 non-null scores
with no visibility into which tickers were missing. Fixed: selection now joins
`pipeline_runs` and requires a real completed live run with a bound
fingerprint (config_hash + non-empty artifact_hashes), ordered by the run's
own `created_at` timestamp (not the run_id string); the score and meta files
are each written atomically (temp+fsync+rename — see
batch_scores_bundle.py's module docstring for why the PAIR is not a single
atomic transaction, and how verify_bundle compensates); coverage is measured
against the run's own persisted candidate roster (role='candidate', per the
2026-05-04 "full pre-veto candidate list" mandate — the concrete, run-bound
expected universe, not an external/driftable definition) with the missing
tickers recorded by name.

Codex #236 review (round 3) — round 2's selection accepted the latest
qualifying run from ANY date strictly before today, then stamped
session_date=today regardless of how old the source run actually was; a
multi-day pipeline outage could silently republish a stale vector as today's
"fresh" bundle, undetected because replay verification only checked the
stamp against itself. Fixed: the source run's date must now equal exactly
the immediately preceding NYSE session (via
batch_scores_bundle.expected_previous_session, the same
pandas_market_calendars primitive used elsewhere this session) — no
fallback to an older run if that exact session has no qualifying run. The
run's actual `run_date` is persisted as `source_run_date` in the meta, and
verified again on the replay side (batch_scores_bundle.verify_bundle).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from batch_scores_bundle import canonical_hash, expected_previous_session  # noqa: E402

RQ = os.environ.get("RQ_ROOT", "/Users/renhao/git/github/RenQuant")
DB = os.path.join(RQ, "data/runs.alpaca.db")
OUT_DIR = os.path.join(RQ, "data", "rq105")
MIN_ROWS = 30  # floor for a non-trivial run; coverage gate (MIN_COVERAGE_FRACTION) is the real quality check

# Fraction of the run's OWN persisted candidate roster (role='candidate', see
# module docstring) that must carry a non-null panel_score. NOT sourced from
# an established repo-wide census threshold — #227 (Stage-1 measurement-
# integrity pins / gate-input census) is still an open design doc, not yet
# shipped as code, so no canonical "expected universe" utility exists to defer
# to. 0.9 is a deliberately conservative interim floor chosen to clearly
# reject the kind of ~50% coverage collapse Codex's review flagged; replace
# with #227's real Stage-1 census requirement once it lands in code.
MIN_COVERAGE_FRACTION = 0.9


def _atomic_write_json(path: str, payload) -> None:
    """temp file in the same dir + fsync + rename: a reader sees either the
    old complete file or the new complete file, never a partial write."""
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(payload, f, sort_keys=True, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.rename(tmp, path)


def _select_source_run(con: sqlite3.Connection, expected_run_date: str):
    """Select the canonical completed live run from EXACTLY
    `expected_run_date` (the immediately preceding NYSE session — computed by
    the caller via batch_scores_bundle.expected_previous_session, NOT "any
    date before today": round 2 accepted any qualifying run strictly before
    today, so a multi-day pipeline outage would silently republish however-
    old a vector was last successfully produced. Ordered by the run's own
    created_at (pipeline_runs), not the run_id string — run_id's trailing
    uuid does not sort chronologically, so two live runs on the same date
    could previously resolve to an arbitrary one.

    Requires a `pipeline_runs` row (proves the run actually completed through
    to record_pipeline_run, not just a partial candidate_scores write) with
    run_type='live' (a real column check, not the previous run_id LIKE
    '%-live-%' string match) and a non-empty `strategy`.

    Returns (run_id, run_date, run_bundle: dict) or None.
    """
    row = con.execute(
        "select pr.run_id, pr.run_date, pr.run_bundle_json, count(cs.ticker) as n "
        "from pipeline_runs pr "
        "join candidate_scores cs "
        "  on cs.run_id = pr.run_id and cs.role = 'candidate' "
        "  and cs.panel_score is not null "
        "where pr.run_type = 'live' "
        "  and pr.run_date = ? "
        "  and pr.strategy is not null and pr.strategy != '' "
        "group by pr.run_id "
        "having n >= ? "
        "order by pr.created_at desc "
        "limit 1",
        (expected_run_date, MIN_ROWS),
    ).fetchone()
    if not row:
        return None
    run_id, run_date, run_bundle_raw, _n = row
    try:
        run_bundle = json.loads(run_bundle_raw) if run_bundle_raw else {}
    except (TypeError, ValueError):
        run_bundle = {}
    return run_id, run_date, run_bundle


# panel + global_calibration are the two "primary runtime artifacts"
# resolve_artifact_paths always aliases regardless of which underlying
# config-field variant is set (ranking.panel_scoring.artifact_path vs.
# panel_ltr.artifact_path fallback), so requiring the alias is both
# necessary and sufficient to prove the class-A signal's own inputs (panel
# score + calibration) are hashed. Everything else a config's
# artifact_paths may carry (shadow lanes, auxiliary ngboost/embedding
# heads, quality-floor thresholds, diagnostic scans, meta-label models,
# regime-conditional PATTERN strings that are never real files) is
# provably not an input to the panel score itself — see
# intraday_session_inputs.py's _REQUIRED_ARTIFACT_KEYS for the full
# reasoning (Codex #399 review; this module mirrors that fix).
_REQUIRED_ARTIFACT_KEYS = frozenset({"panel", "global_calibration"})


def _fingerprint_gaps(run_bundle: dict) -> list[str]:
    gaps = []
    if not run_bundle.get("config_hash"):
        gaps.append("config_hash")
    artifact_hashes = run_bundle.get("artifact_hashes") or {}
    if not artifact_hashes:
        gaps.append("artifact_hashes")
    else:
        missing_required = _REQUIRED_ARTIFACT_KEYS - {
            k for k, v in artifact_hashes.items() if v
        }
        if missing_required:
            gaps.append(f"artifact_hashes({','.join(sorted(missing_required))})")
    if not run_bundle.get("watchlist_hash"):
        gaps.append("watchlist_hash")
    return gaps


def main(
    *,
    db_path: str | None = None,
    out_dir: str | None = None,
    today: str | None = None,
) -> int:
    db_path = db_path or DB
    out_dir = out_dir or OUT_DIR
    today = today or dt.date.today().isoformat()
    try:
        expected_run_date = expected_previous_session(today)
    except ValueError as exc:
        print(f"cannot compute expected prior session for {today}: {exc}", file=sys.stderr)
        return 1
    con = sqlite3.connect(db_path)

    selected = _select_source_run(con, expected_run_date)
    if not selected:
        print(
            f"no qualifying completed live run for the expected prior "
            f"session {expected_run_date} (immediately preceding NYSE "
            f"session before {today}) — refusing to fall back to an older "
            "run (joined pipeline_runs: requires run_type='live', a "
            "recorded strategy, and >= %d role='candidate' rows with "
            "non-null panel_score)" % MIN_ROWS,
            file=sys.stderr,
        )
        return 1
    run_id, run_date, run_bundle = selected

    gaps = _fingerprint_gaps(run_bundle)
    if gaps:
        print(
            f"run {run_id} missing required fingerprint field(s) in its "
            f"run_bundle_json: {', '.join(gaps)} — refusing to export an "
            "unfingerprinted vector",
            file=sys.stderr,
        )
        return 1

    roster = con.execute(
        "select ticker, panel_score from candidate_scores "
        "where run_id=? and role='candidate'",
        (run_id,),
    ).fetchall()
    if not roster:
        print(f"run {run_id} has a pipeline_runs row but no role='candidate' "
              "rows — inconsistent DB state, refusing to export", file=sys.stderr)
        return 1

    scores = {t: float(s) for t, s in roster if s is not None}
    missing_tickers = sorted(t for t, s in roster if s is None)
    universe_n = len(roster)
    coverage = len(scores) / universe_n if universe_n else 0.0

    if coverage < MIN_COVERAGE_FRACTION:
        print(
            f"run {run_id} coverage {coverage:.1%} ({len(scores)}/{universe_n} "
            f"role='candidate' rows scored) is below the "
            f"{MIN_COVERAGE_FRACTION:.0%} floor — refusing to export "
            f"(missing: {', '.join(missing_tickers) or 'n/a'})",
            file=sys.stderr,
        )
        return 1

    os.makedirs(out_dir, exist_ok=True)
    score_content_hash = canonical_hash(scores)
    source_run_bundle_hash = canonical_hash(run_bundle)

    score_path = os.path.join(out_dir, f"batch_scores_{today}.json")
    meta_path = os.path.join(out_dir, f"batch_scores_{today}.meta.json")

    # Write the score payload first (temp+fsync+rename), THEN the meta bundle
    # that names its hash — a crash between the two leaves either (a) neither
    # file updated (meta write never started) or (b) a fresh score file with
    # a STALE meta pointing at the OLD score hash, which the replay-side
    # verifier (run_shadow_serving.sh) will detect and refuse, never a
    # meta claiming a hash the score file doesn't actually have.
    _atomic_write_json(score_path, scores)
    _atomic_write_json(meta_path, {
        "run_id": run_id,
        "score_kind": "panel_score",
        "n": len(scores),
        "universe_n": universe_n,
        "coverage": coverage,
        "missing_tickers": missing_tickers,
        "session_date": today,
        "source_run_date": run_date,
        "score_content_sha256": score_content_hash,
        "source_run_bundle_sha256": source_run_bundle_hash,
        "exported_at": dt.datetime.utcnow().isoformat() + "Z",
    })
    print(
        f"exported {len(scores)}/{universe_n} frozen scores "
        f"(coverage {coverage:.1%}) from {run_id} for session {today}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
