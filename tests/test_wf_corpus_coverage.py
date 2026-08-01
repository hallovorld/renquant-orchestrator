"""Per-lane walk-forward corpus coverage.

The tool exists because a per-lane number was quoted without its lane: 43 folds
belonging to the GBDT recipe were used to retire an anchor about clf. So the tests are
mostly about the ways a coverage report can be reassuring and wrong.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
MOD = ROOT / "ops" / "renquant104" / "wf_corpus_coverage.py"


def _load():
    spec = importlib.util.spec_from_file_location("wfcc", MOD)
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


C = _load()


def _lane(root: pathlib.Path, name: str, dates: list[str]):
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    for x in dates:
        (d / x).mkdir(exist_ok=True)
    return d


def test_a_MISSING_corpus_is_distinct_from_an_EMPTY_one(tmp_path):
    """The distinction the whole tool rests on: a vanished corpus must not read as a
    present-but-empty one, or a deleted lane looks like a lane with no folds yet."""
    _lane(tmp_path, "present_empty", [])
    rep = C.survey(str(tmp_path), ["present_empty", "never_existed"])
    a, b = rep["lanes"]
    assert a["corpus_dir_exists"] is True and a["n_folds"] == 0
    assert b["corpus_dir_exists"] is False and b["n_folds"] == 0


def test_it_counts_only_DATED_directories(tmp_path):
    d = _lane(tmp_path, "lane", ["2024-01-02", "2024-02-01"])
    (d / "cache").mkdir()
    (d / "notes.txt").write_text("x")
    (d / "2024-13-99").mkdir()          # date-shaped but not a real date? still shaped
    rep = C.survey(str(tmp_path), ["lane"])
    assert rep["lanes"][0]["n_folds"] == 3   # shape-matched; files and 'cache' excluded
    assert "cache" not in str(rep)


def test_a_FILE_named_like_a_date_is_not_a_fold(tmp_path):
    d = _lane(tmp_path, "lane", ["2024-01-02"])
    (d / "2024-01-03").write_text("not a directory")
    assert C.survey(str(tmp_path), ["lane"])["lanes"][0]["n_folds"] == 1


def test_lanes_are_reported_SEPARATELY_and_never_summed(tmp_path):
    """The defect this tool was written after: one lane's folds standing in for
    another's zero. A total across lanes must not appear in the report at all."""
    _lane(tmp_path, "rich", [f"2024-01-{i:02d}" for i in range(1, 10)])
    _lane(tmp_path, "poor", [])
    rep = C.survey(str(tmp_path), ["rich", "poor"])
    assert [r["n_folds"] for r in rep["lanes"]] == [9, 0]
    assert "total" not in rep and "n_folds_total" not in rep


def test_EVERY_row_carries_its_lane_name(tmp_path):
    _lane(tmp_path, "a", ["2024-01-01"])
    _lane(tmp_path, "b", ["2024-01-01"])
    assert all(r.get("lane") for r in C.survey(str(tmp_path), ["a", "b"])["lanes"])


def test_a_MISSING_lane_makes_main_EXIT_NONZERO(tmp_path, capsys):
    _lane(tmp_path, "ok", ["2024-01-01"])
    rc = C.main(["--artifacts-root", str(tmp_path), "--lanes", "ok", "gone"])
    assert rc == 1
    assert "MISSING" in capsys.readouterr().out


def test_a_THIN_lane_makes_main_EXIT_NONZERO(tmp_path, capsys):
    _lane(tmp_path, "thin", ["2024-01-01"])
    rc = C.main(["--artifacts-root", str(tmp_path), "--lanes", "thin",
                 "--min-folds", "20"])
    assert rc == 1 and "THIN" in capsys.readouterr().out


def test_ANTI_VACUITY_a_covered_lane_exits_zero(tmp_path, capsys):
    _lane(tmp_path, "full", [f"2024-01-{i:02d}" for i in range(1, 21)])
    rc = C.main(["--artifacts-root", str(tmp_path), "--lanes", "full",
                 "--min-folds", "20"])
    assert rc == 0 and "COVERED" in capsys.readouterr().out


def test_the_report_states_what_a_fold_count_is_NOT(capsys, tmp_path):
    """A directory count reads like an evidence count unless it says otherwise."""
    _lane(tmp_path, "l", ["2024-01-01"])
    C.main(["--artifacts-root", str(tmp_path), "--lanes", "l"])
    out = capsys.readouterr().out
    assert "does not open them" in out and "never summed" in out
