#!/usr/bin/env python3
"""GOAL-8 S2 readout — the one-shot scorer of the frozen three-lane prereg.

Implements doc/research/2026-08-04-goal8-s2-comparison-prereg.md (+ its
pre-clock AMENDMENT 1) EXACTLY; every rule constant below cites the frozen
text. DISCIPLINE (prereg "Measurement mechanics"): this script may not run
against real records before session 20 of the window. It takes ONLY
explicit paths — there are no defaults pointing at the live surfaces — and
the fixture suite (tests/test_s2_readout.py) is the mandatory
positive-control harness.

Arms (frozen):
  PROD   — a runs db: pipeline_runs(run_date) x candidate_scores(rank_score)
  BLEND  — the S1 e2e lane's runs db, same schema
  MOMENTUM — AMENDMENT 1: the chain-verified weekly dated artifact serving
             as of each session's cutoff, selected time-safely from the
             append-only ledger; scores restricted to that session's
             prod-scored universe.

Outputs a JSON report: per-session baskets (with the momentum serving
identity triplet), per-arm means/missing counts, matched-pair coverage,
and the ordinal verdict per the frozen rule.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

BASKET_K = 3                     # frozen: top-3 per arm per session
MIN_MATCHED_PAIR_COVERAGE = 19   # frozen (codex on orch#781): of 20
MAX_BLEND_MISSING = 1            # frozen: blend missing count <= 1
WINDOW_SESSIONS = 20             # frozen: the S1 window


def _top3(scores: dict[str, float]) -> list[str]:
    """Frozen tie rule: score desc, then lexicographic ticker."""
    return [t for t, _ in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[:BASKET_K]]


def _runs_db_scores(db_path: Path, session: str) -> "dict[str, float] | None":
    """Per-session scores from a runs db (PROD / BLEND arms): the session's
    run(s) in pipeline_runs joined to candidate_scores.rank_score. None =
    the arm has NO record that session (missing, per the frozen tally)."""
    con = sqlite3.connect(str(db_path))
    try:
        rows = con.execute(
            "SELECT cs.ticker, cs.rank_score FROM candidate_scores cs "
            "JOIN pipeline_runs pr ON pr.run_id = cs.run_id "
            "WHERE pr.run_date = ? AND cs.rank_score IS NOT NULL",
            (session,),
        ).fetchall()
    finally:
        con.close()
    if not rows:
        return None
    return {str(t): float(s) for t, s in rows}


def _fwd_returns(db_path: Path, session: str) -> dict[str, float]:
    """Frozen outcome: next-session simple return = fwd_1d at the session
    date, from the shared ticker_forward_returns surface."""
    con = sqlite3.connect(str(db_path))
    try:
        rows = con.execute(
            "SELECT ticker, fwd_1d FROM ticker_forward_returns "
            "WHERE as_of_date = ? AND fwd_1d IS NOT NULL",
            (session,),
        ).fetchall()
    finally:
        con.close()
    return {str(t): float(r) for t, r in rows}


# ── momentum arm: AMENDMENT 1 time-safe ledger selection ─────────────────────

def _canon_sha(doc: dict) -> str:
    body = {k: v for k, v in doc.items() if k != "content_sha256"}
    canon = json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return "sha256:" + hashlib.sha256(canon.encode("utf-8")).hexdigest()[:16]


def _verify_chain(rows: list[dict]) -> None:
    prev = None
    for i, row in enumerate(rows):
        if row["row_index"] != i:
            raise ValueError(f"ledger row {i}: row_index {row['row_index']}")
        if row["prev_row_sha"] != prev:
            raise ValueError(f"ledger row {i}: prev_row_sha broken")
        body = {k: v for k, v in row.items() if k != "row_sha"}
        canon = json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False)
        actual = "sha256:" + hashlib.sha256(canon.encode("utf-8")).hexdigest()[:16]
        if row["row_sha"] != actual:
            raise ValueError(f"ledger row {i}: row_sha does not recompute")
        prev = row["row_sha"]


def _momentum_serving(
    ledger_path: Path, session: str, session_cutoff_utc: str
) -> "tuple[dict[str, float], dict[str, Any]] | None":
    """AMENDMENT 1 (as hardened by codex on orch#782): the serving row for
    session D is the LAST chain-verified ledger row with cutoff_date <= D
    AND appended_at_utc <= D's session cutoff. Returns (scores, identity
    triplet) or None (no qualifying/verifiable row -> no basket, counted
    against coverage)."""
    try:
        rows = [json.loads(l) for l in ledger_path.read_text(encoding="utf-8").strip().splitlines()]
        _verify_chain(rows)
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    qualifying = [
        r for r in rows
        if str(r["cutoff_date"]) <= session and str(r["appended_at_utc"]) <= session_cutoff_utc
    ]
    if not qualifying:
        return None
    row = qualifying[-1]
    dated = ledger_path.parent / str(row["cutoff_date"]) / "momentum_residual_v0.json"
    try:
        artifact = json.loads(dated.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if _canon_sha(artifact) != artifact.get("content_sha256"):
        return None
    if artifact.get("content_sha256") != row["artifact_content_sha256"]:
        return None
    scores = {
        str(t): float(v)
        for t, v in (artifact.get("scores") or {}).items()
        if isinstance(v, (int, float)) and not isinstance(v, bool)
    }
    identity = {
        "row_index": row["row_index"],
        "row_sha": row["row_sha"],
        "artifact_content_sha256": row["artifact_content_sha256"],
    }
    return scores, identity


# ── placebo (frozen seed recipe) ─────────────────────────────────────────────

def _placebo_basket(session: str, universe: list[str]) -> list[str]:
    """Frozen: 3 names drawn uniformly, seeded by sha256(ISO date)[:8] as int."""
    import random
    seed = int(hashlib.sha256(session.encode("utf-8")).hexdigest()[:8], 16)
    rng = random.Random(seed)
    pool = sorted(universe)
    if len(pool) <= BASKET_K:
        return pool
    return sorted(rng.sample(pool, BASKET_K))


# ── the readout ──────────────────────────────────────────────────────────────

def run_readout(
    sessions: list[str],
    prod_db: Path,
    blend_db: Path,
    momentum_ledger: Path,
    fwd_db: Path,
    session_cutoffs_utc: dict[str, str],
) -> dict[str, Any]:
    if len(sessions) != WINDOW_SESSIONS:
        raise SystemExit(
            f"the frozen window is exactly {WINDOW_SESSIONS} scheduled sessions; got {len(sessions)}")
    per_session: list[dict[str, Any]] = []
    arm_returns: dict[str, dict[str, float]] = {"prod": {}, "blend": {}, "momentum": {}, "placebo": {}}
    missing: dict[str, int] = {"prod": 0, "blend": 0, "momentum": 0}

    for session in sessions:
        fwd = _fwd_returns(fwd_db, session)
        rec: dict[str, Any] = {"session": session}
        prod_scores = _runs_db_scores(prod_db, session)
        blend_scores = _runs_db_scores(blend_db, session)
        mom = _momentum_serving(
            momentum_ledger, session, session_cutoffs_utc[session])

        universe = sorted(prod_scores) if prod_scores else []
        arms: dict[str, "list[str] | None"] = {
            "prod": _top3(prod_scores) if prod_scores else None,
            "blend": _top3(blend_scores) if blend_scores else None,
            "momentum": None,
            "placebo": _placebo_basket(session, universe) if universe else None,
        }
        if mom is not None and universe:
            mom_scores, identity = mom
            in_universe = {t: s for t, s in mom_scores.items() if t in set(universe)}
            arms["momentum"] = _top3(in_universe) if in_universe else None
            rec["momentum_serving_identity"] = identity

        for arm, basket in arms.items():
            if basket is None:
                if arm != "placebo":
                    missing[arm] += 1
                rec[f"{arm}_basket"] = None
                continue
            # frozen: names with no forward return are EXCLUDED for every arm
            returns = [fwd[t] for t in basket if t in fwd]
            rec[f"{arm}_basket"] = basket
            rec[f"{arm}_n_priced"] = len(returns)
            if returns:
                val = sum(returns) / len(returns)
                arm_returns[arm][session] = val
                rec[f"{arm}_return"] = val
        per_session.append(rec)

    def _matched_mean(a: str, b: str) -> "tuple[float | None, int]":
        common = sorted(set(arm_returns[a]) & set(arm_returns[b]))
        if not common:
            return None, 0
        diffs = [arm_returns[a][s] - arm_returns[b][s] for s in common]
        return sum(diffs) / len(diffs), len(common)

    bp_mean, bp_n = _matched_mean("blend", "prod")
    bm_mean, bm_n = _matched_mean("blend", "momentum")
    mp_mean, mp_n = _matched_mean("momentum", "prod")

    coverage_ok = bp_n >= MIN_MATCHED_PAIR_COVERAGE and bm_n >= MIN_MATCHED_PAIR_COVERAGE
    if not coverage_ok:
        verdict = "INSUFFICIENT RECORD — no promotion interest"
    elif bp_mean is not None and bp_mean > 0 and missing["blend"] <= MAX_BLEND_MISSING:
        verdict = "PROMOTE-INTEREST"
    elif (bp_mean is not None and bp_mean < 0) and (bm_mean is not None and bm_mean < 0):
        verdict = "STOP"
    else:
        verdict = "EXTEND"

    return {
        "sessions": sessions,
        "per_session": per_session,
        "arm_mean": {a: (sum(v.values()) / len(v) if v else None) for a, v in arm_returns.items()},
        "missing": missing,
        "matched_pairs": {
            "blend_vs_prod": {"mean_diff": bp_mean, "n": bp_n},
            "blend_vs_momentum": {"mean_diff": bm_mean, "n": bm_n},
            "momentum_vs_prod": {"mean_diff": mp_mean, "n": mp_n},
        },
        "coverage_ok": coverage_ok,
        "verdict": verdict,
    }


def main(argv: "list[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sessions", required=True,
                    help="comma-separated ISO dates: the exact 20 scheduled sessions")
    ap.add_argument("--session-cutoffs", required=True, type=Path,
                    help="JSON file: {session: cutoff ISO-UTC} for the time-safe momentum rule")
    ap.add_argument("--prod-db", required=True, type=Path)
    ap.add_argument("--blend-db", required=True, type=Path)
    ap.add_argument("--momentum-ledger", required=True, type=Path)
    ap.add_argument("--fwd-db", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args(argv)
    report = run_readout(
        sessions=[s.strip() for s in args.sessions.split(",") if s.strip()],
        prod_db=args.prod_db,
        blend_db=args.blend_db,
        momentum_ledger=args.momentum_ledger,
        fwd_db=args.fwd_db,
        session_cutoffs_utc=json.loads(args.session_cutoffs.read_text()),
    )
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"S2 readout: verdict={report['verdict']} -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
