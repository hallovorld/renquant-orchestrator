"""Tests for the vol-window activation-evidence readout (orch#1004 impl PR 2).

All fixtures are synthetic (tmp_path SQLite + JSONL); no live DB or ledger is
ever read — the module's default paths are overridden through main()'s args
or by calling the functions directly.
"""
import datetime
import importlib.util
import json
import sqlite3
from pathlib import Path

_P = Path(__file__).resolve().parents[1] / "ops" / "renquant104" / "rq104_vol_window_readout.py"
spec = importlib.util.spec_from_file_location("vwr", _P)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


# ── fixture builders ─────────────────────────────────────────────────────────

def _license_row(date, *, on=True, window_on=None, applied=None, top=None,
                 universe_n=None, tag=mod.LANE_TAG):
    if window_on is None:
        window_on = on
    if applied is None:
        applied = window_on
    return {
        "schema": "vol_window_license.v1",
        "date": date,
        "lane_tag": tag,
        "vol_window_days": 20,
        "vol20": 0.20 if on else 0.05,
        "threshold": 0.135,
        "vol_verdict_on": on,
        "regime": "BULL_VOLATILE" if window_on else "BULL_CALM",
        "hard_bear": False,
        "regime_resolved_non_bear": True,
        "bear_precedence_blocked": False,
        "kill_switch": False,
        "window_on": window_on,
        "diagnostic_only_ok": True,
        "admission_ok": False,
        "base_reason": "regime_admission:trade_monotonicity",
        "license_applied": applied,
        "top_decile": top or ["AAA", "BBB"],
        "licensed_candidates": (top or ["AAA", "BBB"]) if applied else [],
        "licensed_holdings": [],
        "n_candidates_at_admission": 5,
        "universe_n": universe_n,
        "top_decile_n": len(top or ["AAA", "BBB"]),
        "tie_break": "ticker",
    }


def _write_license_ledger(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def _lane_db(path: Path, runs) -> None:
    """runs: list of (run_id, run_date, created_at, tickers)."""
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE pipeline_runs (run_id TEXT PRIMARY KEY, "
               "run_date TEXT, run_type TEXT, created_at TEXT)")
    db.execute("CREATE TABLE candidate_scores (run_id TEXT, ticker TEXT, "
               "panel_score REAL)")
    for run_id, run_date, created_at, tickers in runs:
        db.execute("INSERT INTO pipeline_runs VALUES (?,?,?,?)",
                   (run_id, run_date, "live", created_at))
        for t in tickers:
            db.execute("INSERT INTO candidate_scores VALUES (?,?,?)",
                       (run_id, t, 1.0))
    db.commit()
    db.close()


def _fwd_db(path: Path, rows, later_sessions_from=None, n_later=0) -> None:
    """rows: list of (ticker, as_of_date, fwd_20d, fwd_60d)."""
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE ticker_forward_returns (ticker TEXT, "
               "as_of_date TEXT, fwd_20d REAL, fwd_60d REAL)")
    db.executemany("INSERT INTO ticker_forward_returns VALUES (?,?,?,?)", rows)
    if later_sessions_from is not None:
        base = datetime.date.fromisoformat(later_sessions_from)
        for off in range(1, n_later + 1):
            db.execute("INSERT INTO ticker_forward_returns VALUES (?,?,?,?)",
                       ("ZZ", (base + datetime.timedelta(days=off)).isoformat(),
                        None, None))
    db.commit()
    db.close()


def _universe(n=90):
    return [f"T{i:03d}" for i in range(n)]


# ── hash chain ───────────────────────────────────────────────────────────────

def test_chain_appends_and_verifies():
    rows = []
    prev = mod.GENESIS_SHA
    for d in ("2026-08-18", "2026-08-19", "2026-08-20"):
        row = mod.build_row(d, _license_row(d), "r-" + d, ["A", "B"], prev)
        rows.append(row)
        prev = row["entry_sha"]
    assert mod.verify_chain(rows) is None


def test_chain_detects_tampering_of_immutable_field():
    row = mod.build_row("2026-08-18", _license_row("2026-08-18"), "r1",
                        ["A"], mod.GENESIS_SHA)
    rows = [row]
    assert mod.verify_chain(rows) is None
    row["top_decile"] = ["EVIL"]          # immutable field altered post-append
    assert mod.verify_chain(rows) is not None


def test_chain_detects_prev_sha_splice():
    r1 = mod.build_row("2026-08-18", _license_row("2026-08-18"), "r1",
                       ["A"], mod.GENESIS_SHA)
    r2 = mod.build_row("2026-08-19", _license_row("2026-08-19"), "r2",
                       ["A"], r1["entry_sha"])
    assert mod.verify_chain([r1, r2]) is None
    assert mod.verify_chain([r2]) is not None      # r1 excised -> genesis break


def test_mature_fill_mutation_does_not_break_chain(tmp_path):
    d = "2026-06-01"
    uni = _universe(20)
    row = mod.build_row(d, _license_row(d, top=uni[:2]), "r1", uni,
                        mod.GENESIS_SHA)
    rows = [row]
    fwd = tmp_path / "fwd.db"
    _fwd_db(fwd, [(t, d, 0.01, 0.02) for t in uni],
            later_sessions_from=d, n_later=mod.MATURITY_TDAYS_60)
    filled = mod.mature_fill(rows, sqlite3.connect(f"file:{fwd}?mode=ro", uri=True))
    assert filled == 2                     # both horizons realized
    assert rows[0]["realized_60"] and rows[0]["realized_20"]
    assert mod.verify_chain(rows) is None  # mutation touched only mutable fields


# ── maturity aging ───────────────────────────────────────────────────────────

def test_aging_uses_session_calendar_not_fwd_presence(tmp_path):
    """fwd_60d present on the row does NOT realize the session while fewer
    than MATURITY_TDAYS_60 later sessions exist in the table's calendar."""
    d = "2026-06-01"
    uni = _universe(10)
    row = mod.build_row(d, _license_row(d, top=uni[:1]), "r1", uni,
                        mod.GENESIS_SHA)
    fwd = tmp_path / "fwd.db"
    _fwd_db(fwd, [(t, d, 0.01, 0.02) for t in uni],
            later_sessions_from=d, n_later=mod.MATURITY_TDAYS_60 - 1)
    filled = mod.mature_fill([row], sqlite3.connect(f"file:{fwd}?mode=ro", uri=True))
    assert row["realized_60"] is False
    assert row["aged_60"] is False
    # h=20 already aged at 60 later sessions... (21 <= 59) -> realized
    assert row["realized_20"] is True
    assert filled == 1


def test_velocity_h20_matures_before_decisive_h60(tmp_path):
    d = "2026-06-01"
    uni = _universe(10)
    row = mod.build_row(d, _license_row(d, top=uni[:1]), "r1", uni,
                        mod.GENESIS_SHA)
    fwd = tmp_path / "fwd.db"
    _fwd_db(fwd, [(t, d, 0.20 if t == uni[0] else 0.00, 0.10) for t in uni],
            later_sessions_from=d, n_later=mod.MATURITY_TDAYS_20)
    mod.mature_fill([row], sqlite3.connect(f"file:{fwd}?mode=ro", uri=True))
    assert row["realized_20"] is True and row["realized_60"] is False
    # ...the velocity leg registers, but NEVER enters the decisive count —
    # h=20 is a diagnostic, the burden is pinned to the certified h=60.
    c = mod.activation_counter([row])
    assert c["velocity_h20_positive"] == 1
    assert c["decisive_h60_positive"] == 0


def test_spread_is_topdecile_minus_universe_mean(tmp_path):
    d = "2026-06-01"
    uni = ["A", "B", "C", "D"]
    row = mod.build_row(d, _license_row(d, top=["A"]), "r1", uni,
                        mod.GENESIS_SHA)
    fwd = tmp_path / "fwd.db"
    _fwd_db(fwd, [("A", d, 0.08, 0.12), ("B", d, 0.00, 0.00),
                  ("C", d, 0.02, 0.04), ("D", d, 0.02, 0.00)],
            later_sessions_from=d, n_later=mod.MATURITY_TDAYS_60)
    mod.mature_fill([row], sqlite3.connect(f"file:{fwd}?mode=ro", uri=True))
    assert row["realized_60"] is True
    assert abs(row["spread_60"] - (0.12 - (0.12 + 0.00 + 0.04 + 0.00) / 4)) < 1e-12
    assert abs(row["spread_20"] - (0.08 - (0.08 + 0.00 + 0.02 + 0.02) / 4)) < 1e-12


def test_topdecile_missing_ticker_blocks_realization_with_telemetry(tmp_path):
    d = "2026-06-01"
    uni = _universe(10)
    row = mod.build_row(d, _license_row(d, top=[uni[0], "MISSING"]), "r1", uni,
                        mod.GENESIS_SHA)
    fwd = tmp_path / "fwd.db"
    _fwd_db(fwd, [(t, d, 0.01, 0.02) for t in uni],
            later_sessions_from=d, n_later=mod.MATURITY_TDAYS_60)
    assert mod.mature_fill([row], sqlite3.connect(f"file:{fwd}?mode=ro", uri=True)) == 0
    assert row["realized_60"] is False
    assert row["n_top_resolvable_60"] == 1 and row["n_top"] == 2  # shortfall visible


def test_universe_coverage_floor_blocks_realization(tmp_path):
    d = "2026-06-01"
    uni = _universe(10)                       # only 8/10 resolvable -> 0.80 < 0.90
    row = mod.build_row(d, _license_row(d, top=uni[:1]), "r1", uni,
                        mod.GENESIS_SHA)
    fwd = tmp_path / "fwd.db"
    _fwd_db(fwd, [(t, d, 0.01, 0.02) for t in uni[:8]],
            later_sessions_from=d, n_later=mod.MATURITY_TDAYS_60)
    assert mod.mature_fill([row], sqlite3.connect(f"file:{fwd}?mode=ro", uri=True)) == 0
    assert row["realized_60"] is False
    assert row["universe_coverage_60"] == 0.8


def test_universe_coverage_above_floor_realizes_over_resolvable(tmp_path):
    d = "2026-06-01"
    uni = _universe(10)                       # 9/10 resolvable -> 0.90 passes
    row = mod.build_row(d, _license_row(d, top=uni[:1]), "r1", uni,
                        mod.GENESIS_SHA)
    fwd = tmp_path / "fwd.db"
    _fwd_db(fwd, [(t, d, 0.01, 0.02) for t in uni[:9]],
            later_sessions_from=d, n_later=mod.MATURITY_TDAYS_60)
    assert mod.mature_fill([row], sqlite3.connect(f"file:{fwd}?mode=ro", uri=True)) == 2
    assert row["realized_60"] is True
    assert row["n_universe_resolvable_60"] == 9


def test_lane_run_missing_row_never_realizes(tmp_path):
    d = "2026-06-01"
    row = mod.build_row(d, _license_row(d, top=["A"]), None, [],
                        mod.GENESIS_SHA)
    assert row["lane_run_found"] is False
    fwd = tmp_path / "fwd.db"
    _fwd_db(fwd, [("A", d, 0.01, 0.02)],
            later_sessions_from=d, n_later=mod.MATURITY_TDAYS_60)
    assert mod.mature_fill([row], sqlite3.connect(f"file:{fwd}?mode=ro", uri=True)) == 0
    assert row["realized_60"] is False


# ── the counter ──────────────────────────────────────────────────────────────

def _counted_row(*, on, spread60=None, spread20=None, window_on=None):
    row = mod.build_row("2026-06-01",
                        _license_row("2026-06-01", on=on, window_on=window_on),
                        "r1", ["A"], mod.GENESIS_SHA)
    if spread60 is not None:
        row["realized_60"] = True
        row["spread_60"] = spread60
    if spread20 is not None:
        row["realized_20"] = True
        row["spread_20"] = spread20
    return row


def test_counter_counts_only_ON_sessions_with_positive_decisive_spread():
    rows = [
        _counted_row(on=True, spread60=0.05),    # counts
        _counted_row(on=True, spread60=-0.02),   # negative -> no
        _counted_row(on=False, spread60=0.30),   # OFF session -> no
        _counted_row(on=True),                   # unrealized -> no
        _counted_row(on=True, spread20=0.10),    # velocity only -> not decisive
    ]
    c = mod.activation_counter(rows)
    assert c["decisive_h60_positive"] == 1
    assert c["velocity_h20_positive"] == 1
    assert c["on_sessions_recorded"] == 4
    assert c["target"] == 20


def test_counter_window_restricted_subset():
    rows = [
        _counted_row(on=True, spread60=0.05, window_on=True),
        _counted_row(on=True, spread60=0.05, window_on=False),  # ON but BEAR-blocked
    ]
    c = mod.activation_counter(rows)
    assert c["decisive_h60_positive"] == 2
    assert c["decisive_h60_positive_window_only"] == 1


def test_frozen_burden_is_twenty():
    """[DERIVED — orch#1001 prereg §5 base of the doubled PARTIAL burden;
    orch#1004 §5 AC3]. A drifted constant here is a drifted burden."""
    assert mod.ACTIVATION_TARGET_ON_SESSIONS == 20


# ── license ledger parsing ───────────────────────────────────────────────────

def test_lane_tag_filter_refuses_foreign_and_untagged_rows(tmp_path):
    led = tmp_path / "vol_window_license.jsonl"
    _write_license_ledger(led, [
        _license_row("2026-08-18"),
        _license_row("2026-08-19", tag="alpaca_shadow_blend"),
        _license_row("2026-08-20", tag=None),
    ])
    sessions, skipped = mod.load_license_sessions(led)
    assert set(sessions) == {"2026-08-18"}
    assert skipped == 2


def test_last_row_per_date_wins(tmp_path):
    led = tmp_path / "vol_window_license.jsonl"
    _write_license_ledger(led, [
        _license_row("2026-08-18", on=False),
        _license_row("2026-08-18", on=True),   # re-run same session
    ])
    sessions, _ = mod.load_license_sessions(led)
    assert sessions["2026-08-18"]["vol_verdict_on"] is True


def test_lane_full_runs_partial_run_never_supersedes_full(tmp_path):
    db_path = tmp_path / "lane.db"
    _lane_db(db_path, [
        ("full", "2026-08-18", "2026-08-18 14:06:00", _universe(90)),
        ("partial", "2026-08-18", "2026-08-18 18:00:00", ["X", "Y"]),
    ])
    runs = mod.lane_full_runs(sqlite3.connect(f"file:{db_path}?mode=ro", uri=True))
    assert runs == {"2026-08-18": "full"}


# ── main(): end to end on synthetic fixtures ─────────────────────────────────

def _paths(tmp_path, *, universe=None, license_rows=None, fwd_rows=None,
           n_later=0, later_from=None):
    universe = _universe(90) if universe is None else universe
    lic = tmp_path / "vol_window_license.jsonl"
    lane = tmp_path / "lane.db"
    fwd = tmp_path / "fwd.db"
    led = tmp_path / "readout" / "ledger.jsonl"
    if license_rows is not None:
        _write_license_ledger(lic, license_rows)
    _lane_db(lane, [("r-2026-08-18", "2026-08-18", "2026-08-18 14:06:00",
                     universe)])
    _fwd_db(fwd, fwd_rows or [], later_sessions_from=later_from,
            n_later=n_later)
    return lic, lane, fwd, led


def _run_main(lic, lane, fwd, led):
    return mod.main([
        "--license-ledger", str(lic), "--lane-db", str(lane),
        "--fwd-db", str(fwd), "--ledger", str(led),
    ])


def test_main_not_deployed_yet_exits_zero(tmp_path, capsys):
    rc = mod.main([
        "--license-ledger", str(tmp_path / "absent.jsonl"),
        "--lane-db", str(tmp_path / "absent.db"),
        "--fwd-db", str(tmp_path / "absent_fwd.db"),
        "--ledger", str(tmp_path / "readout" / "ledger.jsonl"),
    ])
    assert rc == 0
    assert "not deployed yet" in capsys.readouterr().out
    assert not (tmp_path / "readout" / "ledger.jsonl").exists()


def test_main_appends_idempotently_and_echoes_burden(tmp_path, capsys):
    uni = _universe(90)
    lic, lane, fwd, led = _paths(
        tmp_path, universe=uni,
        license_rows=[_license_row("2026-08-18", top=uni[:9], universe_n=90)],
        fwd_rows=[(t, "2026-08-18", 0.01, 0.02) for t in uni],
        later_from="2026-08-18", n_later=mod.MATURITY_TDAYS_60)
    assert _run_main(lic, lane, fwd, led) == 0
    rows = [json.loads(x) for x in led.read_text().splitlines()]
    assert len(rows) == 1
    assert rows[0]["universe_parity"] is True
    assert rows[0]["realized_60"] is True     # aged fixture matured same pass
    assert mod.verify_chain(rows) is None
    out1 = capsys.readouterr().out
    assert "ACTIVATION-EVIDENCE (decisive, certified h=60)" in out1
    assert "/20 ON-state" in out1
    # second pass: no duplicate, no rewrite
    before = led.read_text()
    assert _run_main(lic, lane, fwd, led) == 0
    assert led.read_text() == before
    assert len(led.read_text().splitlines()) == 1


def test_main_read_does_not_mutate_when_nothing_changes(tmp_path):
    uni = _universe(90)
    lic, lane, fwd, led = _paths(
        tmp_path, universe=uni,
        license_rows=[_license_row("2026-08-18", top=uni[:9], universe_n=90)],
        fwd_rows=[], n_later=0)
    assert _run_main(lic, lane, fwd, led) == 0
    stat1 = led.stat().st_mtime_ns, led.read_text()
    assert _run_main(lic, lane, fwd, led) == 0
    stat2 = led.stat().st_mtime_ns, led.read_text()
    assert stat1 == stat2                      # reading the evidence didn't mutate it


def test_main_alarms_on_license_session_without_lane_run(tmp_path, capsys):
    uni = _universe(90)
    lic, lane, fwd, led = _paths(
        tmp_path, universe=uni,
        license_rows=[
            _license_row("2026-08-18", top=uni[:9], universe_n=90),
            _license_row("2026-08-19", top=uni[:9], universe_n=90),  # no lane run
        ])
    rc = _run_main(lic, lane, fwd, led)
    assert rc == 2
    out = capsys.readouterr().out
    assert "ALARM" in out and "NO full lane run" in out
    rows = [json.loads(x) for x in led.read_text().splitlines()]
    assert [r["run_date"] for r in rows] == ["2026-08-18", "2026-08-19"]
    assert rows[1]["lane_run_found"] is False
    assert mod.verify_chain(rows) is None


def test_main_alarms_on_lane_run_without_license_row(tmp_path, capsys):
    lic, lane, fwd, led = _paths(tmp_path, license_rows=[])  # empty ledger file
    rc = _run_main(lic, lane, fwd, led)
    assert rc == 2
    assert "flag did not evaluate" in capsys.readouterr().out


def test_main_refuses_to_write_over_a_broken_chain(tmp_path, capsys):
    uni = _universe(90)
    lic, lane, fwd, led = _paths(
        tmp_path, universe=uni,
        license_rows=[_license_row("2026-08-18", top=uni[:9], universe_n=90)])
    assert _run_main(lic, lane, fwd, led) == 0
    # tamper with an immutable field on disk
    row = json.loads(led.read_text().splitlines()[0])
    row["top_decile"] = ["EVIL"]
    led.write_text(json.dumps(row, sort_keys=True) + "\n")
    tampered = led.read_text()
    rc = _run_main(lic, lane, fwd, led)
    assert rc == 2
    assert "hash chain BROKEN" in capsys.readouterr().out
    assert led.read_text() == tampered         # refused to write anything


def test_main_off_session_recorded_but_never_counts(tmp_path, capsys):
    uni = _universe(90)
    lic, lane, fwd, led = _paths(
        tmp_path, universe=uni,
        license_rows=[_license_row("2026-08-18", on=False, top=uni[:9],
                                   universe_n=90)],
        fwd_rows=[(t, "2026-08-18", 0.5, 0.5) for t in uni],
        later_from="2026-08-18", n_later=mod.MATURITY_TDAYS_60)
    assert _run_main(lic, lane, fwd, led) == 0
    out = capsys.readouterr().out
    assert "ACTIVATION-EVIDENCE (decisive, certified h=60): 0/20" in out
    rows = [json.loads(x) for x in led.read_text().splitlines()]
    assert rows[0]["vol_verdict_on"] is False   # the OFF session is still evidence
