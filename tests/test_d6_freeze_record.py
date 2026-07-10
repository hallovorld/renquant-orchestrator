"""Tests for scripts/d6_freeze_record.py (D6 preregistered-replay freeze record).

All fixtures are synthetic — no production DB, no umbrella artifacts.
Covers: loader-faithful session enumeration (min-rows rule, NULL handling),
a PARITY test against the ACTUAL pipeline loader
(renquant_pipeline...wf_replay_loader.load_replay_bars_from_sim_db — codex
review on PR #446: the loader is ground truth for what the replay consumes),
exclusion-window + manual-exclusion honoring, deterministic seeded-hash split
(exact floor count, nested cross-horizon consistency, seed sensitivity),
read-only DB discipline, and --verify (clean pass, DB drift, artifact drift,
tampered session lists, path-override exemption).
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "d6_freeze_record.py"
_spec = importlib.util.spec_from_file_location("d6_freeze_record", _SCRIPT)
d6 = importlib.util.module_from_spec(_spec)
sys.modules["d6_freeze_record"] = d6
_spec.loader.exec_module(d6)


# ------------------------------------------------------------------ fixtures
# Sessions before the exclusion window; both horizons populated.
CLEAN_DATES = [
    "2026-05-01", "2026-05-04", "2026-05-05", "2026-05-06", "2026-05-07",
    "2026-05-08", "2026-05-11", "2026-05-12", "2026-05-13", "2026-05-14",
    "2026-05-15", "2026-05-18", "2026-05-19", "2026-05-20", "2026-05-21",
    "2026-05-22", "2026-06-01", "2026-06-02", "2026-06-03", "2026-06-04",
]
# Inside the default exclusion window 2026-06-23 : 2026-07-09 (inclusive).
WINDOW_DATES = ["2026-06-23", "2026-06-30", "2026-07-09"]
# fwd_60d NULL on these two — sessions at fwd_1d only (nested-split check).
FWD1D_ONLY_DATES = ["2026-06-05", "2026-06-08"]
# Only one usable joined row — never a session (loader min-rows rule).
SINGLE_TICKER_DATE = "2026-06-09"
# mu is NULL for all rows — never a session.
NULL_MU_DATE = "2026-06-10"
# Exactly 2 joined rows — the >= 2 boundary; IS a session.
TWO_ROW_DATE = "2026-06-11"
# sigma is NULL for all rows — never a session.
NULL_SIGMA_DATE = "2026-06-12"
# Scored, but NO ticker_forward_returns rows at all — never a session.
NO_FWD_ROW_DATE = "2026-06-15"
# One ticker scored under TWO run_ids -> 2 joined rows for 1 distinct
# ticker. The loader counts ROWS (it emits a bar carrying the ticker
# twice), so this IS a session — the freeze tool must agree (parity edge).
DUP_RUN_DATE = "2026-06-16"

TICKERS = ["AAA", "BBB", "CCC"]
WINDOW = "2026-06-23:2026-07-09"
# Ground-truth session sets the loader yields on this fixture, per horizon.
EXPECTED_FWD1D = sorted(
    CLEAN_DATES + WINDOW_DATES + FWD1D_ONLY_DATES + [TWO_ROW_DATE, DUP_RUN_DATE])
EXPECTED_FWD60D = sorted(CLEAN_DATES + WINDOW_DATES + [TWO_ROW_DATE, DUP_RUN_DATE])
NEVER_SESSIONS = (SINGLE_TICKER_DATE, NULL_MU_DATE, NULL_SIGMA_DATE, NO_FWD_ROW_DATE)


def _make_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE score_distribution (
            run_id TEXT NOT NULL, date TEXT NOT NULL, ticker TEXT NOT NULL,
            mu REAL, sigma REAL, regime TEXT,
            PRIMARY KEY (run_id, ticker)
        );
        CREATE TABLE ticker_forward_returns (
            as_of_date DATE NOT NULL, ticker TEXT NOT NULL,
            close_price REAL, fwd_1d REAL, fwd_5d REAL, fwd_10d REAL,
            fwd_20d REAL, fwd_60d REAL,
            PRIMARY KEY (as_of_date, ticker)
        );
        """
    )
    rows_score, rows_fwd = [], []

    def add(date: str, tickers, *, mu=0.01, sigma=0.1, fwd_60d=0.02,
            fwd_rows=True, run_id=None):
        for t in tickers:
            rows_score.append((run_id or f"run-{date}", date, t, mu, sigma,
                               "BULL_CALM"))
            if fwd_rows:
                rows_fwd.append(
                    (date, t, 100.0, 0.001, 0.002, 0.003, 0.004, fwd_60d))

    for date in CLEAN_DATES + WINDOW_DATES:
        add(date, TICKERS)
    for date in FWD1D_ONLY_DATES:
        add(date, TICKERS, fwd_60d=None)
    add(SINGLE_TICKER_DATE, TICKERS[:1])
    add(NULL_MU_DATE, TICKERS, mu=None)
    add(TWO_ROW_DATE, TICKERS[:2])
    add(NULL_SIGMA_DATE, TICKERS, sigma=None)
    add(NO_FWD_ROW_DATE, TICKERS, fwd_rows=False)
    # Same ticker under two run_ids; fwd row inserted once (PK on date,ticker).
    add(DUP_RUN_DATE, TICKERS[:1], run_id=f"run-{DUP_RUN_DATE}-a")
    add(DUP_RUN_DATE, TICKERS[:1], run_id=f"run-{DUP_RUN_DATE}-b", fwd_rows=False)

    conn.executemany(
        "INSERT INTO score_distribution VALUES (?,?,?,?,?,?)", rows_score)
    conn.executemany(
        "INSERT INTO ticker_forward_returns VALUES (?,?,?,?,?,?,?,?)", rows_fwd)
    conn.commit()
    conn.close()


@pytest.fixture()
def env(tmp_path):
    """Synthetic sim DB + fake artifacts root + record output path."""
    db = tmp_path / "sim_runs.db"
    _make_db(db)
    art_root = tmp_path / "strategy_dir"
    (art_root / "artifacts/prod").mkdir(parents=True)
    (art_root / "artifacts/prod/model.json").write_text('{"model": 1}')
    (art_root / "artifacts/prod/calibrator.json").write_text('{"cal": 1}')
    return {
        "db": db,
        "art_root": art_root,
        "record": tmp_path / "freeze_record.json",
        "tmp": tmp_path,
    }


def _gen_args(env, seed=43, out=None, extra=()):
    return [
        "--db", str(env["db"]),
        "--exclude-window", WINDOW,
        "--tuning-frac", "0.3",
        "--seed", str(seed),
        "--artifacts-root", str(env["art_root"]),
        "--artifact", "artifacts/prod/model.json",
        "--artifact", "artifacts/prod/calibrator.json",
        "--out", str(out or env["record"]),
        *extra,
    ]


def _generate(env, seed=43, out=None, extra=()) -> dict:
    rc = d6.main(_gen_args(env, seed=seed, out=out, extra=extra))
    assert rc == 0
    return json.loads(Path(out or env["record"]).read_text())


# ---------------------------------------------------------- session census
def test_session_enumeration_matches_loader_rule(env):
    rec = _generate(env)
    fwd1 = rec["horizons"]["fwd_1d"]
    fwd60 = rec["horizons"]["fwd_60d"]
    assert fwd1["n_available"] == len(EXPECTED_FWD1D)
    assert fwd60["n_available"] == len(EXPECTED_FWD60D)
    all_ids = (fwd1["tuning"]["ids"] + fwd1["evaluation"]["ids"]
               + fwd60["tuning"]["ids"] + fwd60["evaluation"]["ids"])
    for date in NEVER_SESSIONS:
        assert date not in all_ids
    # boundary (=2 rows) and duplicate-run sessions ARE included
    assert TWO_ROW_DATE in all_ids
    assert DUP_RUN_DATE in all_ids
    # data cutoff = max kept (non-excluded) session per horizon
    assert rec["data_cutoff"]["fwd_1d_max_session"] == DUP_RUN_DATE
    assert rec["data_cutoff"]["fwd_60d_max_session"] == DUP_RUN_DATE


def test_session_parity_with_pipeline_loader(env):
    """PARITY GATE (codex review on PR #446): the freeze tool's SQL must
    enumerate EXACTLY the sessions the real replay harness will consume.
    Ground truth = the actual pipeline loader
    (renquant_pipeline...wf_replay_loader.load_replay_bars_from_sim_db),
    imported directly from the pipeline checkout on PYTHONPATH (the make-test
    env always has it; skip only in stripped envs). Covers the edge cases:
    exactly 1 vs >= 2 joined rows, NULL mu / NULL sigma, missing fwd rows,
    fwd column NULL at one horizon, and duplicate-run row counting."""
    loader = pytest.importorskip(
        "renquant_pipeline.kernel.portfolio_qp.wf_replay_loader",
        reason="renquant-pipeline not on PYTHONPATH (make test provides it)",
    )
    expected_by_horizon = {1: EXPECTED_FWD1D, 60: EXPECTED_FWD60D}
    for horizon in (1, 60):
        bars = loader.load_replay_bars_from_sim_db(
            env["db"], "2000-01-01", "2099-12-31", fwd_horizon_days=horizon)
        loader_sessions = [bar.bar_date for bar in bars]
        conn = d6.connect_readonly(env["db"])
        try:
            tool_sessions = d6.enumerate_sessions(conn, horizon)
        finally:
            conn.close()
        assert tool_sessions == loader_sessions, (
            f"fwd_{horizon}d parity broken: tool={tool_sessions} "
            f"loader={loader_sessions}")
        # and both match the hand-computed fixture ground truth
        assert loader_sessions == expected_by_horizon[horizon]
    # loader row-count semantics on the duplicate-run session: the bar
    # carries the ticker twice — that is exactly why the tool counts rows,
    # not distinct tickers.
    dup_bar = [b for b in bars if b.bar_date == DUP_RUN_DATE]
    assert dup_bar and list(dup_bar[0].snap.tickers) == ["AAA", "AAA"]


def test_db_is_not_written(env):
    before = d6.sha256_file(env["db"])
    _generate(env)
    assert d6.sha256_file(env["db"]) == before


# --------------------------------------------------------------- exclusion
def test_exclusion_window_honored(env):
    rec = _generate(env)
    for horizon in ("fwd_1d", "fwd_60d"):
        h = rec["horizons"][horizon]
        kept = h["tuning"]["ids"] + h["evaluation"]["ids"]
        for date in WINDOW_DATES:
            assert date not in kept
            assert date in rec["exclusion"]["excluded_session_ids"][horizon]
        # window endpoints inclusive
        assert "2026-06-23" in rec["exclusion"]["excluded_session_ids"][horizon]
        assert "2026-07-09" in rec["exclusion"]["excluded_session_ids"][horizon]
        assert h["n_excluded"] == len(WINDOW_DATES)


def test_manual_session_exclusion_honored(env):
    inspected = CLEAN_DATES[0]
    rec = _generate(env, extra=("--exclude-session", inspected))
    for horizon in ("fwd_1d", "fwd_60d"):
        h = rec["horizons"][horizon]
        assert inspected not in h["tuning"]["ids"] + h["evaluation"]["ids"]
        assert inspected in rec["exclusion"]["excluded_session_ids"][horizon]
    assert rec["exclusion"]["manual_exclude_sessions"] == [inspected]


# ------------------------------------------------------------------- split
def test_split_deterministic_and_exact(env, tmp_path):
    rec_a = _generate(env, seed=43)
    rec_b = _generate(env, seed=43, out=tmp_path / "again.json")
    # identical apart from the generation timestamp
    assert not d6.diff_records(rec_a, rec_b, set())
    # exact floor(tuning_frac * union_n), disjoint, exhaustive
    union_n = rec_a["split"]["union_n"]
    assert rec_a["split"]["tuning_n"] == int(union_n * 0.3)
    for horizon in ("fwd_1d", "fwd_60d"):
        h = rec_a["horizons"][horizon]
        tuning, evaluation = set(h["tuning"]["ids"]), set(h["evaluation"]["ids"])
        assert not tuning & evaluation
        assert len(tuning) + len(evaluation) == h["n_kept"]


def test_split_changes_with_seed(env, tmp_path):
    rec_a = _generate(env, seed=43)
    rec_b = _generate(env, seed=44, out=tmp_path / "other-seed.json")
    assert (set(rec_a["horizons"]["fwd_1d"]["tuning"]["ids"])
            != set(rec_b["horizons"]["fwd_1d"]["tuning"]["ids"]))


def test_split_nested_across_horizons(env):
    """A date present at both horizons lands in the SAME subset (protocol §1
    nested selection) — tuning at one horizon never touches the other's
    evaluation sessions."""
    rec = _generate(env)
    t1 = set(rec["horizons"]["fwd_1d"]["tuning"]["ids"])
    e1 = set(rec["horizons"]["fwd_1d"]["evaluation"]["ids"])
    t60 = set(rec["horizons"]["fwd_60d"]["tuning"]["ids"])
    e60 = set(rec["horizons"]["fwd_60d"]["evaluation"]["ids"])
    assert not t1 & e60
    assert not t60 & e1
    # and the fwd_60d subsets are exactly the restriction of the union split
    assert t60 == t1 & (t60 | e60)


def test_assign_tuning_dates_is_pure_hash_rank():
    dates = [f"2026-01-{d:02d}" for d in range(1, 21)]
    got = d6.assign_tuning_dates(dates, seed=7, tuning_frac=0.3)
    ranked = sorted(
        dates,
        key=lambda d: (hashlib.sha256(f"7|{d}".encode()).hexdigest(), d))
    assert got == set(ranked[: int(len(dates) * 0.3)])
    # shuffling input order must not matter
    assert d6.assign_tuning_dates(list(reversed(dates)), 7, 0.3) == got


# ------------------------------------------------------------------ verify
def test_verify_clean_record_passes(env):
    _generate(env)
    assert d6.main(["--verify", str(env["record"])]) == 0


def test_verify_catches_db_drift(env, capsys):
    _generate(env)
    conn = sqlite3.connect(env["db"])
    conn.execute(
        "INSERT INTO score_distribution VALUES ('run-x','2026-06-18','AAA',0.01,0.1,'BULL_CALM')")
    conn.execute(
        "INSERT INTO score_distribution VALUES ('run-x2','2026-06-18','BBB',0.01,0.1,'BULL_CALM')")
    conn.execute(
        "INSERT INTO ticker_forward_returns VALUES ('2026-06-18','AAA',100,0.001,0,0,0,0.02)")
    conn.execute(
        "INSERT INTO ticker_forward_returns VALUES ('2026-06-18','BBB',100,0.001,0,0,0,0.02)")
    conn.commit()
    conn.close()
    assert d6.main(["--verify", str(env["record"])]) == 1
    err = capsys.readouterr().err
    assert "VERIFY FAILED" in err
    assert "sha256" in err  # db content hash drifted


def test_verify_catches_artifact_drift(env, capsys):
    _generate(env)
    (env["art_root"] / "artifacts/prod/model.json").write_text('{"model": 2}')
    assert d6.main(["--verify", str(env["record"])]) == 1
    assert "VERIFY FAILED" in capsys.readouterr().err


def test_verify_catches_tampered_session_list(env):
    rec = _generate(env)
    rec["horizons"]["fwd_60d"]["evaluation"]["ids"].pop()
    rec["horizons"]["fwd_60d"]["evaluation"]["n"] -= 1
    env["record"].write_text(json.dumps(rec))
    assert d6.main(["--verify", str(env["record"])]) == 1


def test_verify_db_path_override_on_identical_copy(env, tmp_path):
    """A byte-identical DB copy at another path verifies clean ONLY with an
    explicit --db override; the sha256 still guards content."""
    _generate(env)
    copy = tmp_path / "copy.db"
    copy.write_bytes(env["db"].read_bytes())
    assert d6.main(["--verify", str(env["record"]), "--db", str(copy)]) == 0
    # content drift on the copy is still caught
    conn = sqlite3.connect(copy)
    conn.execute("UPDATE ticker_forward_returns SET fwd_60d = 0.5 WHERE as_of_date = ?",
                 (CLEAN_DATES[0],))
    conn.commit()
    conn.close()
    assert d6.main(["--verify", str(env["record"]), "--db", str(copy)]) == 1


def test_verify_missing_record_is_exit_2(env):
    assert d6.main(["--verify", str(env["tmp"] / "nope.json")]) == 2


# --------------------------------------------------------------- interface
def test_seed_required_for_generation(env):
    args = _gen_args(env)
    idx = args.index("--seed")
    del args[idx:idx + 2]
    with pytest.raises(SystemExit):
        d6.main(args)


def test_record_carries_provenance(env):
    rec = _generate(env)
    assert rec["freeze_record_version"] == d6.RECORD_VERSION
    assert rec["generator"]["script"] == "scripts/d6_freeze_record.py"
    assert rec["generator"]["version"] == d6.GENERATOR_VERSION
    args = rec["generator"]["args"]
    assert args["seed"] == 43
    assert args["tuning_frac"] == 0.3
    assert args["exclude_window"] == ["2026-06-23", "2026-07-09"]
    assert rec["source_db"]["sha256"] == d6.sha256_file(env["db"])
    items = {i["rel_path"]: i for i in rec["artifacts"]["items"]}
    assert items["artifacts/prod/model.json"]["present"] is True
    assert items["artifacts/prod/model.json"]["sha256"] == d6.sha256_file(
        env["art_root"] / "artifacts/prod/model.json")
    assert "mtime" in items["artifacts/prod/calibrator.json"]


def test_missing_artifact_recorded_not_fatal(env):
    rec = _generate(env, extra=("--artifact", "artifacts/prod/absent.json"))
    items = {i["rel_path"]: i for i in rec["artifacts"]["items"]}
    assert items["artifacts/prod/absent.json"]["present"] is False


def test_bad_window_and_bad_horizon_are_loud(env):
    with pytest.raises(SystemExit):
        d6.main(_gen_args(env, extra=("--exclude-window", "2026-07-09")))
    with pytest.raises(SystemExit):
        d6.main(_gen_args(env, extra=("--horizons", "1,7")))
