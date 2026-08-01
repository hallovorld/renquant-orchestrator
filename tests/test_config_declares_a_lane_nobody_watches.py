"""A shadow lane the CONFIG declares that the sentinel does not watch.

orch#689 made a lane VANISHING visible. Its mirror had no detector: a lane ADDED to
`shadow_models` is invisible, because `watched_lanes()` is a hardcoded tuple. Both
silences look identical from outside.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
MOD = ROOT / "ops" / "renquant104" / "rq104_shadow_scorer_sentinel.py"


def _load():
    spec = importlib.util.spec_from_file_location("sent_drift", MOD)
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


S = _load()


def _cfg(tmp_path, shadows, name="c.json", raw=None):
    body = raw if raw is not None else {
        "ranking": {"panel_scoring": {"kind": "xgb", "shadow_models": shadows}}}
    p = tmp_path / name
    p.write_text(json.dumps(body), encoding="utf-8")
    return str(p)


def _lanes(*names):
    return tuple(S.WatchedLane(name=n, runs_db=None, mlruns_dir=None, purpose=None)
                 for n in names)


# --- the gap -----------------------------------------------------------------

def test_a_config_lane_NO_watched_lane_matches_is_reported(tmp_path):
    cfg = _cfg(tmp_path, [{"name": "momentum_v1"}, {"name": "hf_patchtst"}])
    unwatched, why = S.unwatched_config_lanes(_lanes("hf_patchtst"), cfg)
    assert unwatched == ["momentum_v1"] and why == ""


def test_a_DECORATED_config_lane_counts_as_watched(tmp_path):
    """`hf_patchtst_<suffix>` is the sentinel's own matching rule; treating it as
    unwatched would alarm on a correctly-wired lane."""
    cfg = _cfg(tmp_path, [{"name": "hf_patchtst_pt07_strict_seed44_previous_primary"}])
    unwatched, _ = S.unwatched_config_lanes(_lanes("hf_patchtst"), cfg)
    assert unwatched == []


def test_ANTI_VACUITY_a_fully_wired_config_reports_nothing(tmp_path):
    cfg = _cfg(tmp_path, [{"name": "a"}, {"name": "b"}])
    assert S.unwatched_config_lanes(_lanes("a", "b"), cfg) == ([], "")


def test_a_config_with_NO_shadow_models_is_legitimate(tmp_path):
    """A lane-free config is a valid state, not a defect."""
    cfg = _cfg(tmp_path, None, raw={"ranking": {"panel_scoring": {"kind": "xgb"}}})
    assert S.unwatched_config_lanes(_lanes("a"), cfg) == ([], "")


# --- "could not check" is not "checked, found nothing" -----------------------

def test_a_MISSING_config_is_reported_not_treated_as_no_lanes(tmp_path):
    unwatched, why = S.unwatched_config_lanes(_lanes("a"), str(tmp_path / "gone.json"))
    assert unwatched == [] and "config not found" in why


def test_an_UNREADABLE_config_is_reported(tmp_path):
    p = tmp_path / "b.json"
    p.write_text("{not json", encoding="utf-8")
    _, why = S.unwatched_config_lanes(_lanes("a"), str(p))
    assert "JSONDecodeError" in why or "ValueError" in why


def test_a_STRING_ranking_container_does_not_CRASH(tmp_path):
    """`(x or {}).get(...)` is not a guard — a non-empty string is truthy. Fourth tool
    in this repo to need that sentence."""
    cfg = _cfg(tmp_path, None, raw={"ranking": "n/a"})
    _, why = S.unwatched_config_lanes(_lanes("a"), cfg)
    assert "not an object" in why


def test_a_MALFORMED_shadow_entry_is_reported_AND_the_readable_ones_still_checked(
        tmp_path):
    """A malformed entry is not 'one fewer lane'. Skipping it silently is how an
    unwatched lane stays unwatched."""
    cfg = _cfg(tmp_path, [{"name": "momentum_v1"}, {"name": 7}, "x"])
    unwatched, why = S.unwatched_config_lanes(_lanes("hf_patchtst"), cfg)
    assert unwatched == ["momentum_v1"]
    assert "unreadable shadow_models entries" in why and "entry 1" in why


def test_an_EMPTY_config_path_disables_the_check_but_says_so(tmp_path):
    _, why = S.unwatched_config_lanes(_lanes("a"), "")
    assert "config not found" in why


# --- the design decision, pinned ---------------------------------------------

def test_the_watch_list_is_NOT_derived_from_the_config():
    """The obvious fix is wrong and must stay rejected: if `watched_lanes()` came from
    the config, a lane REMOVED from the config would leave the watch list with it, and
    the sentinel would stop looking for exactly what orch#689 detects."""
    import ast
    tree = ast.parse(MOD.read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "watched_lanes")
    # AST, not a string slice: an earlier attempt sliced source between two `def`s and
    # matched a later occurrence, failing on text it was never meant to read.
    called = {n.func.id for n in ast.walk(fn)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "config_declared_lanes" not in called, (
        "watched_lanes() must not read the config; see unwatched_config_lanes()")
    consts = {c.value for c in ast.walk(fn)
              if isinstance(c, ast.Constant) and isinstance(c.value, str)}
    assert not any("shadow_models" in c for c in consts), (
        "watched_lanes() must not name the config's shadow_models key")
    assert "would stop a REMOVED lane from being noticed" in \
        MOD.read_text(encoding="utf-8")


def test_the_LIVE_config_currently_has_no_unwatched_lane():
    """Anti-vacuity against reality: the check exists for a state that does not hold
    today, and it must stay quiet until it does."""
    import os
    cfg = "/Users/renhao/git/github/renquant-strategy-104/configs/strategy_config.json"
    if not os.path.exists(cfg):
        import pytest
        pytest.skip("pinned config not present on this machine")
    unwatched, why = S.unwatched_config_lanes(S.watched_lanes(), cfg)
    assert unwatched == [] and why == "", (unwatched, why)


def test_NOT_REQUESTED_is_quiet_while_COULD_NOT_CHECK_is_not(tmp_path, monkeypatch,
                                                             capsys):
    """The split the existing suite forced. An earlier version alarmed whenever
    `--config` was absent, turning every deployment without it into a permanent alarm —
    16 failures in `test_rq104_shadow_scorer_sentinel.py`, all `assert 8 == 0`.

    A check nobody asked for must be quiet. A check that WAS asked for and could not run
    must not be.
    """
    monkeypatch.setattr(S, "alert", lambda *a, **k: None)
    monkeypatch.setattr(S, "is_session_day", lambda d: True)
    monkeypatch.setattr(S, "watched_lanes", lambda: _lanes("hf_patchtst"))
    monkeypatch.setattr(S, "_patrol_lane", lambda lane, days, today, out: 0)

    rc_absent = S.main(["--as-of", "2026-07-31"])
    out = capsys.readouterr().out
    assert rc_absent == 0
    assert "NOT REQUESTED" in out and "skipped, not passed" in out

    rc_broken = S.main(["--as-of", "2026-07-31",
                        "--config", str(tmp_path / "gone.json")])
    assert rc_broken == S.EXIT_ALARM
