"""A session that decided on a skeleton model fleet must not read as a no-trade.

All fixtures synthetic. Binding to the live logs would go red the day the fleet
is fixed, which is backwards for a regression test.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from ops.renquant104.model_load_coverage_scan import (  # noqa: E402
    BELOW_ABSOLUTE, BELOW_TRAILING, INSUFFICIENT, NoSessions, OK, UNREADABLE,
    dated_logs, main, read_coverage, scan,
)


def _log(d: pathlib.Path, date: str, loaded=None, universe=145, body="") -> None:
    d.mkdir(parents=True, exist_ok=True)
    t = body
    if loaded is not None:
        t += f"\n[INFO] live.runner: Loaded models for {loaded}/{universe} symbols: ['A']\n"
    (d / f"{date}.log").write_text(t or "nothing here\n", encoding="utf-8")


# --- the defect this exists for -------------------------------------------

def test_a_skeleton_fleet_is_a_finding_not_a_no_trade(tmp_path):
    for i, n in enumerate([120, 118, 122, 119, 121]):
        _log(tmp_path, f"2026-07-{10+i:02d}", n)
    _log(tmp_path, "2026-07-20", 4)          # the collapse
    r = scan(tmp_path, days=30)
    assert r["n_collapsed"] == 1
    assert r["collapsed"][0]["date"] == "2026-07-20"
    assert r["collapsed"][0]["state"] == BELOW_ABSOLUTE


def test_a_healthy_fleet_is_clean(tmp_path):
    for i, n in enumerate([120, 118, 122]):
        _log(tmp_path, f"2026-07-{10+i:02d}", n)
    assert scan(tmp_path, days=30)["n_collapsed"] == 0


# --- the two floors catch DIFFERENT shapes --------------------------------

def test_relative_floor_catches_a_decay_the_absolute_floor_sleeps_through(tmp_path):
    """A fleet decaying from a high base can stay above an absolute floor tuned
    low. The relative floor is the reason that is still a finding."""
    for i, n in enumerate([140, 140, 140, 140]):
        _log(tmp_path, f"2026-07-{10+i:02d}", n)
    _log(tmp_path, "2026-07-20", 80)         # 55% — above the 50% absolute floor
    r = scan(tmp_path, days=30, min_frac=0.50, max_drop=0.40)
    assert r["n_collapsed"] == 1
    assert r["collapsed"][0]["state"] == BELOW_TRAILING


def test_absolute_floor_catches_a_uniformly_low_fleet(tmp_path):
    """The twin: if EVERY session is low, the trailing median is low too and the
    relative test sees nothing. Only the absolute floor fires."""
    for i in range(5):
        _log(tmp_path, f"2026-07-{10+i:02d}", 10)
    r = scan(tmp_path, days=30)
    assert r["n_collapsed"] == 5
    assert all(x["state"] == BELOW_ABSOLUTE for x in r["collapsed"])


def test_either_floor_suffices_not_both(tmp_path):
    """Deliberately OR, not AND. Requiring both would let each veto the other."""
    for i in range(4):
        _log(tmp_path, f"2026-07-{10+i:02d}", 140)
    _log(tmp_path, "2026-07-20", 80)
    r = scan(tmp_path, days=30)
    row = [x for x in r["rows"] if x["date"] == "2026-07-20"][0]
    assert row["frac"] > r["min_frac"]        # passes the absolute floor
    assert row["state"] == BELOW_TRAILING     # and is STILL a finding


# --- refusals -------------------------------------------------------------

def test_a_log_with_no_loaded_line_is_UNREADABLE_not_OK(tmp_path):
    _log(tmp_path, "2026-07-10", 120)
    _log(tmp_path, "2026-07-11", None, body="ran, said nothing about models\n")
    r = scan(tmp_path, days=30)
    row = [x for x in r["rows"] if x["date"] == "2026-07-11"][0]
    assert row["state"] == UNREADABLE
    assert row["state"] != OK
    assert r["n_unreadable"] == 1


def test_unreadable_forces_exit_2_not_1(tmp_path):
    """A session that could not be checked outranks one that was checked and
    found bad — same rule the ops-audit aggregator uses."""
    _log(tmp_path, "2026-07-10", 120)
    _log(tmp_path, "2026-07-11", None)
    assert main(["--log-dir", str(tmp_path)]) == 2


def test_collapse_alone_exits_1(tmp_path):
    for i in range(4):
        _log(tmp_path, f"2026-07-{10+i:02d}", 120)
    _log(tmp_path, "2026-07-20", 4)
    assert main(["--log-dir", str(tmp_path)]) == 1


def test_all_healthy_exits_0(tmp_path):
    for i in range(3):
        _log(tmp_path, f"2026-07-{10+i:02d}", 120)
    assert main(["--log-dir", str(tmp_path)]) == 0


def test_no_sessions_refuses(tmp_path):
    with pytest.raises(NoSessions):
        scan(tmp_path / "empty", days=30)


def test_undated_logs_never_occupy_a_window_slot(tmp_path):
    """An undated log must not shorten the evidence the window rests on."""
    _log(tmp_path, "2026-07-10", 120)
    (tmp_path / "launchd_stdout.log").write_text("noise\n", encoding="utf-8")
    assert [d for d, _ in dated_logs(tmp_path)] == ["2026-07-10"]


def test_first_match_wins_so_shadow_lanes_do_not_overwrite_prod(tmp_path):
    """Shadow lanes replay the same bar and log their own counts. The prod scan
    is the first one; reading the last would report a shadow lane's fleet."""
    _log(tmp_path, "2026-07-10", 120, body="")
    p = tmp_path / "2026-07-10.log"
    p.write_text(p.read_text() + "[INFO] Loaded models for 3/145 symbols: ['X']\n",
                 encoding="utf-8")
    loaded, universe, _ = read_coverage(p)
    assert (loaded, universe) == (120, 145)


# --- it must not overclaim ------------------------------------------------

def test_result_refuses_to_call_a_healthy_count_correct(tmp_path):
    _log(tmp_path, "2026-07-10", 120)
    r = scan(tmp_path, days=30)
    assert "not whether any of them is fresh" in r["does_NOT_establish"]


# --- the baseline must be PRIOR sessions only (codex on orch#878) -------------

def test_a_sustained_decline_cannot_hide_by_lowering_its_own_baseline(tmp_path):
    """THE regression codex asked for. With one median over the WHOLE window, a
    sustained partial decline drags the baseline down and evades both checks:
    140,140,80,80,80 of 145 has a window median of 80, so the 80-rows show a drop
    of zero, and 55% clears a 50% absolute floor. Judged against PRIOR sessions
    only, the first 80 is a 43% fall from a 140-baseline and fires."""
    for i, n in enumerate([140, 140, 140, 140]):
        _log(tmp_path, f"2026-07-{10+i:02d}", n)
    for i, n in enumerate([80, 80, 80]):
        _log(tmp_path, f"2026-07-{20+i:02d}", n)
    r = scan(tmp_path, days=30, min_frac=0.50, max_drop=0.40, min_history=3)
    flagged = [x["date"] for x in r["rows"] if x["state"] == BELOW_TRAILING]
    assert "2026-07-20" in flagged, r["rows"]
    # and it is NOT caught by the absolute floor — 80/145 = 55% clears 50%
    row = [x for x in r["rows"] if x["date"] == "2026-07-20"][0]
    assert row["frac"] > r["min_frac"]


def test_no_row_is_judged_against_a_baseline_containing_itself(tmp_path):
    for i, n in enumerate([120, 118, 122, 119, 60]):
        _log(tmp_path, f"2026-07-{10+i:02d}", n)
    r = scan(tmp_path, days=30, min_history=3)
    last = r["rows"][-1]
    assert last["n_prior_sessions"] == 4
    # baseline is the median of the FOUR earlier rows, not of all five
    import statistics
    assert last["baseline_frac"] == statistics.median(
        [x["frac"] for x in r["rows"][:-1]])


def test_too_little_history_is_INSUFFICIENT_not_OK(tmp_path):
    """A median over one or two points is not a baseline. Such a row must not be
    reported clean on the relative test."""
    for i, n in enumerate([120, 118]):
        _log(tmp_path, f"2026-07-{10+i:02d}", n)
    r = scan(tmp_path, days=30, min_history=3)
    assert all(x["state"] == INSUFFICIENT for x in r["rows"])
    assert r["n_insufficient_history"] == 2


def test_the_absolute_floor_still_applies_without_history(tmp_path):
    """INSUFFICIENT must not become a hole: a collapse in the first session is
    still a collapse."""
    _log(tmp_path, "2026-07-10", 4)
    r = scan(tmp_path, days=30, min_history=3)
    assert r["rows"][0]["state"] == BELOW_ABSOLUTE
    assert r["n_collapsed"] == 1


def test_unreadable_sessions_do_not_enter_the_baseline(tmp_path):
    """An unreadable session contributes no frac; it must not shorten or skew the
    prior window silently."""
    for i, n in enumerate([120, 118, 122]):
        _log(tmp_path, f"2026-07-{10+i:02d}", n)
    _log(tmp_path, "2026-07-13", None)
    _log(tmp_path, "2026-07-14", 119)
    r = scan(tmp_path, days=30, min_history=3)
    last = [x for x in r["rows"] if x["date"] == "2026-07-14"][0]
    assert last["n_prior_sessions"] == 3


def test_latest_is_reported_for_the_daily_alert_surface(tmp_path):
    """The daily surface needs the newest session judged against its preceding
    baseline, not a window verdict."""
    for i, n in enumerate([120, 118, 122, 119]):
        _log(tmp_path, f"2026-07-{10+i:02d}", n)
    _log(tmp_path, "2026-07-20", 30)
    r = scan(tmp_path, days=30, min_history=3)
    assert r["latest"]["date"] == "2026-07-20"
    assert r["latest"]["state"] == BELOW_ABSOLUTE
