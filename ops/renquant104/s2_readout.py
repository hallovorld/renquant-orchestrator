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
    """Per-session scores from a runs db (PROD / BLEND arms), with the
    CANONICAL run selection [codex on orch#783 item 3; measured 2026-08-04:
    the live db has 21-35 runs/session, exactly one carrying candidate-role
    rows — the daily decision run]: among the session's runs that have >=1
    role='candidate' row, pick the lexicographically-LAST run_id; scores =
    that run's role='candidate' rank_scores only; duplicate tickers within
    the selected run resolve to MAX score (deterministic). None = no run
    with candidate rows that session (missing, per the frozen tally)."""
    con = sqlite3.connect(str(db_path))
    try:
        run_row = con.execute(
            "SELECT pr.run_id FROM pipeline_runs pr "
            "JOIN candidate_scores cs ON cs.run_id = pr.run_id "
            "WHERE pr.run_date = ? AND cs.role = 'candidate' "
            "AND cs.rank_score IS NOT NULL "
            "GROUP BY pr.run_id ORDER BY pr.run_id DESC LIMIT 1",
            (session,),
        ).fetchone()
        if not run_row:
            return None
        rows = con.execute(
            "SELECT cs.ticker, MAX(cs.rank_score) FROM candidate_scores cs "
            "WHERE cs.run_id = ? AND cs.role = 'candidate' "
            "AND cs.rank_score IS NOT NULL GROUP BY cs.ticker",
            (run_row[0],),
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


# ── momentum arm: the pipeline provider loader (pipeline#262) ───────────────
# codex on orch#783: verification belongs at the pipeline provider boundary —
# pipeline imports the model-owned verifier and is the canonical artifact
# consumer. This readout does NOT reimplement chain or artifact logic; it
# calls load_momentum_artifact_as_of (single-read snapshot, chain, dated
# artifact, sha both directions, parity, golden reproduction, TIME-SAFE row
# selection) and treats None as a coverage miss.

def _default_momentum_loader(ledger_path: Path, *, session_date: str,
                             session_cutoff_utc: str):
    """The REAL provider (requires the pipeline+model distributions —
    present on the operator machine, absent on hosted CI). run_readout
    takes an injectable ``momentum_loader`` seam so the DECISION LOGIC is
    CI-tested with a fake while this real provider stays the default
    [codex on orch#783 round 3]."""
    from renquant_pipeline.kernel.panel_pipeline.momentum_residual_scorer import (
        load_momentum_artifact_as_of,
    )
    return load_momentum_artifact_as_of(
        ledger_path, session_date=session_date,
        session_cutoff_utc=session_cutoff_utc)


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
    extension_used: bool = False,
    momentum_loader=None,
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
        loader = momentum_loader or _default_momentum_loader
        mom = loader(
            momentum_ledger, session_date=session,
            session_cutoff_utc=session_cutoffs_utc[session])

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
        # Frozen two-phase rule [codex on orch#783 item 1]: the FIRST
        # 20-session coverage miss consumes the declared extension; only
        # with the extension already used does the rung close INSUFFICIENT.
        verdict = ("INSUFFICIENT RECORD — no promotion interest"
                   if extension_used else "EXTEND")
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
        "extension_used": extension_used,
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
    ap.add_argument("--extension-used", action="store_true",
                    help="the declared one-time extension window has already "
                         "run (second phase): a coverage miss now closes the "
                         "rung INSUFFICIENT instead of extending")
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args(argv)
    report = run_readout(
        sessions=[s.strip() for s in args.sessions.split(",") if s.strip()],
        prod_db=args.prod_db,
        blend_db=args.blend_db,
        momentum_ledger=args.momentum_ledger,
        fwd_db=args.fwd_db,
        session_cutoffs_utc=json.loads(args.session_cutoffs.read_text()),
        extension_used=args.extension_used,
    )
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"S2 readout: verdict={report['verdict']} -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
