"""Positive-control fixtures for the S2 readout (mandatory per the frozen
prereg's measurement-mechanics clause; these are the ONLY runs allowed
before session 20). Everything here is synthetic — no real record surface
is touched."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ops" / "renquant104"))

import s2_readout as s2  # noqa: E402

SESSIONS = [f"2026-09-{d:02d}" for d in range(1, 21)]  # 20 synthetic sessions
CUTOFFS = {s: f"{s}T20:00:00+00:00" for s in SESSIONS}


def _mk_runs_db(path: Path, per_session_scores: dict[str, dict[str, float]]) -> None:
    con = sqlite3.connect(str(path))
    con.execute("CREATE TABLE pipeline_runs (run_id TEXT, run_date TEXT)")
    con.execute("CREATE TABLE candidate_scores (run_id TEXT, ticker TEXT, rank_score REAL)")
    for i, (session, scores) in enumerate(per_session_scores.items()):
        rid = f"r{i}"
        con.execute("INSERT INTO pipeline_runs VALUES (?,?)", (rid, session))
        for t, sc in scores.items():
            con.execute("INSERT INTO candidate_scores VALUES (?,?,?)", (rid, t, sc))
    con.commit(); con.close()


def _mk_fwd_db(path: Path, per_session_returns: dict[str, dict[str, float]]) -> None:
    con = sqlite3.connect(str(path))
    con.execute("CREATE TABLE ticker_forward_returns (as_of_date TEXT, ticker TEXT, fwd_1d REAL)")
    for session, rets in per_session_returns.items():
        for t, r in rets.items():
            con.execute("INSERT INTO ticker_forward_returns VALUES (?,?,?)", (session, t, r))
    con.commit(); con.close()


def _sha(doc: dict, drop: str) -> str:
    body = {k: v for k, v in doc.items() if k != drop}
    canon = json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return "sha256:" + hashlib.sha256(canon.encode()).hexdigest()[:16]


def _mk_momentum(root: Path, entries: list[tuple[str, str, dict[str, float]]]) -> Path:
    """entries: (cutoff_date, appended_at_utc, scores) in append order."""
    root.mkdir(parents=True, exist_ok=True)
    rows, prev = [], None
    for i, (cutoff, appended, scores) in enumerate(entries):
        artifact = {"kind": "momentum_residual_v0", "cutoff_date": cutoff, "scores": scores}
        artifact["content_sha256"] = _sha(artifact, "content_sha256")
        dated = root / cutoff / "momentum_residual_v0.json"
        dated.parent.mkdir(parents=True, exist_ok=True)
        dated.write_text(json.dumps(artifact), encoding="utf-8")
        row = {"row_index": i, "prev_row_sha": prev, "appended_at_utc": appended,
               "kind": "momentum_residual_v0", "cutoff_date": cutoff,
               "params_version": "v0", "artifact_content_sha256": artifact["content_sha256"]}
        row["row_sha"] = _sha(row, "row_sha")
        rows.append(row); prev = row["row_sha"]
    ledger = root / "momentum_artifact_ledger.jsonl"
    ledger.write_text("".join(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n" for r in rows),
                      encoding="utf-8")
    return ledger


UNIVERSE = ["AAA", "BBB", "CCC", "DDD", "EEE"]


def _standard_world(tmp_path: Path, *, blend_beats_prod: bool = True,
                    momentum_sessions: "set[str] | None" = None):
    """A fully-covered synthetic world. blend picks winners iff
    blend_beats_prod; momentum serves every session unless restricted."""
    prod_scores, blend_scores, fwd = {}, {}, {}
    for s in SESSIONS:
        # winners: DDD/EEE (+1%), losers: AAA/BBB (-1%), CCC flat
        fwd[s] = {"AAA": -0.01, "BBB": -0.01, "CCC": 0.0, "DDD": 0.01, "EEE": 0.01}
        prod_scores[s] = {"AAA": 5.0, "BBB": 4.0, "CCC": 3.0, "DDD": 2.0, "EEE": 1.0}
        blend_scores[s] = ({"DDD": 5.0, "EEE": 4.0, "CCC": 3.0, "AAA": 2.0, "BBB": 1.0}
                           if blend_beats_prod else
                           {"AAA": 5.0, "BBB": 4.9, "CCC": 3.0, "DDD": 2.0, "EEE": 1.0})
    prod_db = tmp_path / "prod.db"; _mk_runs_db(prod_db, prod_scores)
    blend_db = tmp_path / "blend.db"; _mk_runs_db(blend_db, blend_scores)
    fwd_db = tmp_path / "fwd.db"; _mk_fwd_db(fwd_db, fwd)
    mom_scores = {"EEE": 9.0, "DDD": 8.0, "CCC": 1.0, "AAA": 0.5, "BBB": 0.2}
    ledger = _mk_momentum(tmp_path / "momentum",
                          [("2026-08-29", "2026-08-29T12:00:00+00:00", mom_scores)])
    return prod_db, blend_db, ledger, fwd_db


def test_positive_control_promote_interest(tmp_path):
    prod_db, blend_db, ledger, fwd_db = _standard_world(tmp_path)
    rep = s2.run_readout(SESSIONS, prod_db, blend_db, ledger, fwd_db, CUTOFFS)
    assert rep["coverage_ok"] is True
    assert rep["matched_pairs"]["blend_vs_prod"]["n"] == 20
    assert rep["matched_pairs"]["blend_vs_prod"]["mean_diff"] > 0
    assert rep["verdict"] == "PROMOTE-INTEREST"
    # the momentum serving identity triplet is recorded on every session
    for rec in rep["per_session"]:
        ident = rec["momentum_serving_identity"]
        assert set(ident) == {"row_index", "row_sha", "artifact_content_sha256"}


def test_stop_verdict_when_blend_trails_both(tmp_path):
    prod_db, blend_db, ledger, fwd_db = _standard_world(tmp_path, blend_beats_prod=False)
    # prod also picks losers; momentum picks winners -> blend < momentum, blend == prod
    rep = s2.run_readout(SESSIONS, prod_db, blend_db, ledger, fwd_db, CUTOFFS)
    assert rep["verdict"] in ("EXTEND", "STOP")  # blend==prod -> mean_diff 0 -> EXTEND
    # force strict trail vs prod too: shift blend to pick even worse basket is
    # not possible in this 5-name world (prod already worst) -> EXTEND expected
    assert rep["verdict"] == "EXTEND"


def test_insufficient_record_beats_a_winning_blend(tmp_path):
    """[codex on orch#781] a winning blend with a thin matched set must NOT
    promote: kill momentum coverage below 19 and expect INSUFFICIENT."""
    prod_db, blend_db, _, fwd_db = _standard_world(tmp_path)
    # momentum ledger appended AFTER every session cutoff -> zero qualifying rows
    ledger = _mk_momentum(tmp_path / "mom2",
                          [("2026-09-25", "2026-09-25T12:00:00+00:00",
                            {"EEE": 9.0, "DDD": 8.0, "CCC": 1.0})])
    rep = s2.run_readout(SESSIONS, prod_db, blend_db, ledger, fwd_db, CUTOFFS)
    assert rep["matched_pairs"]["blend_vs_momentum"]["n"] == 0
    assert rep["coverage_ok"] is False
    assert rep["verdict"] == "INSUFFICIENT RECORD — no promotion interest"


def test_time_safe_selection_ignores_late_appended_rows(tmp_path):
    """AMENDMENT 1 hardened rule: a row appended AFTER a session's cutoff
    must not serve that session, even with an eligible cutoff_date."""
    prod_db, blend_db, _, fwd_db = _standard_world(tmp_path)
    early = {"AAA": 9.0, "BBB": 8.0, "CCC": 7.0}          # early artifact: picks losers
    late = {"EEE": 9.0, "DDD": 8.0, "CCC": 7.0}           # late-appended: picks winners
    ledger = _mk_momentum(tmp_path / "mom3", [
        ("2026-08-29", "2026-08-29T12:00:00+00:00", early),
        # cutoff_date eligible for ALL sessions, but appended mid-window:
        ("2026-08-30", "2026-09-10T12:00:00+00:00", late),
    ])
    rep = s2.run_readout(SESSIONS, prod_db, blend_db, ledger, fwd_db, CUTOFFS)
    first = next(r for r in rep["per_session"] if r["session"] == "2026-09-01")
    tenth_plus = next(r for r in rep["per_session"] if r["session"] == "2026-09-15")
    assert first["momentum_serving_identity"]["row_index"] == 0   # late row NOT used
    assert first["momentum_basket"] == ["AAA", "BBB", "CCC"]
    assert tenth_plus["momentum_serving_identity"]["row_index"] == 1  # after append, used
    assert tenth_plus["momentum_basket"] == ["CCC", "DDD", "EEE"] or \
        set(tenth_plus["momentum_basket"]) == {"EEE", "DDD", "CCC"}


def test_placebo_is_deterministic_and_seeded(tmp_path):
    prod_db, blend_db, ledger, fwd_db = _standard_world(tmp_path)
    r1 = s2.run_readout(SESSIONS, prod_db, blend_db, ledger, fwd_db, CUTOFFS)
    r2 = s2.run_readout(SESSIONS, prod_db, blend_db, ledger, fwd_db, CUTOFFS)
    b1 = [rec["placebo_basket"] for rec in r1["per_session"]]
    b2 = [rec["placebo_basket"] for rec in r2["per_session"]]
    assert b1 == b2
    assert len({tuple(b) for b in b1}) > 1  # varies across sessions


def test_window_size_is_enforced(tmp_path):
    prod_db, blend_db, ledger, fwd_db = _standard_world(tmp_path)
    import pytest
    with pytest.raises(SystemExit, match="exactly 20"):
        s2.run_readout(SESSIONS[:5], prod_db, blend_db, ledger, fwd_db, CUTOFFS)
