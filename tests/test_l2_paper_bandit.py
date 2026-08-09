"""L2 paper bandit: the §2 contract, tested item by item. Tmp dirs only."""
from __future__ import annotations

import json
import math
import sqlite3
from pathlib import Path

import pytest

from renquant_orchestrator import l2_paper_bandit as l2


def test_floor_holds_and_renormalises():
    w = l2.apply_floor({l2.CHAMPION: 0.1, "a": 0.6, "b": 0.3})
    assert w[l2.CHAMPION] == pytest.approx(0.5)
    assert sum(w.values()) == pytest.approx(1.0)
    # proportionality among the others preserved
    assert w["a"] / w["b"] == pytest.approx(2.0)


def test_hedge_step_clips_and_records(contract_c=l2.CLIP):
    w0 = l2.apply_floor({l2.CHAMPION: 1.0, "a": 1.0})
    new, detail = l2.hedge_step(w0, {l2.CHAMPION: 0.0, "a": 0.30})  # 30% > clip
    assert "a" in detail["clipped"]
    # the update used the CLIPPED value: ratio bounded by exp(eta*C)
    assert new["a"] / new[l2.CHAMPION] <= (0.5 / 0.5) * math.exp(l2.ETA * contract_c) + 1e-9


def test_missing_mark_carries_weight_and_is_recorded():
    w0 = l2.apply_floor({l2.CHAMPION: 1.0, "a": 1.0})
    new, detail = l2.hedge_step(w0, {l2.CHAMPION: 0.01, "a": None})
    assert "a" in detail["excluded"]
    # champion rose on its positive return; the floor then dominates anyway
    assert new[l2.CHAMPION] >= 0.5 and sum(new.values()) == pytest.approx(1.0)


def _mk_lane_db(path: Path, marks: dict[str, float]) -> None:
    with sqlite3.connect(path) as con:
        con.execute("CREATE TABLE live_state_snapshots (run_date TEXT,"
                    " created_at TEXT, portfolio_value REAL)")
        for d, pv in marks.items():
            con.execute("INSERT INTO live_state_snapshots VALUES (?,?,?)",
                        (d, f"{d} 21:00:00", pv))


def _mk_all(tmp_path: Path, series: dict[str, dict[str, float]]) -> Path:
    (tmp_path / "data").mkdir()
    for arm, rel in l2.ARMS.items():
        _mk_lane_db(tmp_path / rel, series[arm])
    return tmp_path


_BASE = {"2026-08-04": 100.0, "2026-08-05": 101.0, "2026-08-06": 102.0}


def test_cli_replays_verifies_and_appends(tmp_path, capsys):
    series = {arm: dict(_BASE) for arm in l2.ARMS}
    root = _mk_all(tmp_path, series)
    log = tmp_path / "logs"
    assert l2.main(["--data-root", str(root), "--log-dir", str(log)]) == 0
    out1 = json.loads(capsys.readouterr().out)
    assert out1["rows_appended"] == 2 and out1["rows_verified"] == 0

    # second run: nothing new -> all verified, none appended (idempotent)
    assert l2.main(["--data-root", str(root), "--log-dir", str(log)]) == 0
    out2 = json.loads(capsys.readouterr().out)
    assert out2["rows_verified"] == 2 and out2["rows_appended"] == 0


def test_cli_refuses_a_tampered_log(tmp_path, capsys):
    series = {arm: dict(_BASE) for arm in l2.ARMS}
    root = _mk_all(tmp_path, series)
    log = tmp_path / "logs"
    assert l2.main(["--data-root", str(root), "--log-dir", str(log)]) == 0
    capsys.readouterr()
    f = log / "l2_paper_bandit.jsonl"
    lines = f.read_text().splitlines()
    row = json.loads(lines[0]); row["weights"][l2.CHAMPION] = 0.9
    f.write_text("\n".join([json.dumps(row, sort_keys=True)] + lines[1:]) + "\n")
    assert l2.main(["--data-root", str(root), "--log-dir", str(log)]) == 1
    assert "never appended to" in capsys.readouterr().out


def test_missing_arm_db_refuses(tmp_path, capsys):
    (tmp_path / "data").mkdir()
    _mk_lane_db(tmp_path / l2.ARMS[l2.CHAMPION], _BASE)  # champion only
    assert l2.main(["--data-root", str(tmp_path),
                    "--log-dir", str(tmp_path / "logs")]) == 1
    assert "DB missing" in capsys.readouterr().out


def test_winner_gains_weight_but_floor_binds():
    """A persistently better arm accumulates weight; the champion never sinks
    below the floor — the §2 containment in one picture."""
    marks_champ = {f"2026-08-{d:02d}": 100 * (1.001 ** i)
                   for i, d in enumerate(range(1, 21))}
    marks_star = {f"2026-08-{d:02d}": 100 * (1.02 ** i)
                  for i, d in enumerate(range(1, 21))}
    arm_marks = {a: dict(marks_champ) for a in l2.ARMS}
    arm_marks["profile_blend_mom"] = marks_star
    rows = l2.replay(arm_marks)
    final = rows[-1]["weights"]
    assert final[l2.CHAMPION] == pytest.approx(0.5)          # floor binds
    others = {a: w for a, w in final.items() if a != l2.CHAMPION}
    assert max(others, key=others.get) == "profile_blend_mom"  # winner leads
