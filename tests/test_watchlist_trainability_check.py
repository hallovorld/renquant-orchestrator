"""orch#1020 — a served ticker that can never be scored must not be silent.

CRWV was added to the served watchlist on the operator's request (2026-08-19) and
was inert every session after, because artifacts come from a DIFFERENT watchlist
that nobody updated. It logged `no_artifact` — the same WARNING the eight
deliberately-untrainable names log — so it read as normal.

The design has exactly two states: trained, or declared untrainable WITH a
reason. This guard refuses the third one.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MOD = ROOT / "ops" / "watchlist_trainability_check.py"


def _load():
    spec = importlib.util.spec_from_file_location("wl_trainability", MOD)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


C = _load()


def _tree(tmp_path: Path, *, served, trained, declared) -> Path:
    root = tmp_path / "RenQuant"
    served_p = root / C.SERVED_CONFIG
    tourn_p = root / C.TOURNAMENT_CONFIG
    decl_p = root / "logs" / "weekly_tournament_retrain" / "2026-08-23.expected_non_trainable.json"
    for p in (served_p, tourn_p, decl_p):
        p.parent.mkdir(parents=True, exist_ok=True)
    served_p.write_text(json.dumps({"watchlist": served}))
    tourn_p.write_text(json.dumps({"watchlist": trained}))
    decl_p.write_text(json.dumps(declared))
    return root


# ---------------------------------------------------------------------------
# the invariant
# ---------------------------------------------------------------------------

def test_a_served_ticker_that_is_neither_trained_nor_declared_FAILS(tmp_path):
    root = _tree(tmp_path, served=["AAPL", "CRWV"], trained=["AAPL"],
                 declared={"SPY": "benchmark index"})
    offenders, _ = C.undeclared_untrainable(root)
    assert offenders == ["CRWV"]


def test_a_DECLARED_untrainable_ticker_is_fine(tmp_path):
    """SPY and the sector ETFs log no_artifact by design — the guard must not
    fire on the mechanism it exists to protect."""
    root = _tree(tmp_path, served=["AAPL", "SPY"], trained=["AAPL"],
                 declared={"SPY": "benchmark index (strategy_config.benchmark)"})
    offenders, _ = C.undeclared_untrainable(root)
    assert offenders == []


def test_a_declaration_with_a_BLANK_reason_does_not_count(tmp_path):
    """The mechanism's whole value is that someone wrote down WHY. An empty
    string would let a name be silenced without anyone justifying it."""
    root = _tree(tmp_path, served=["AAPL", "CRWV"], trained=["AAPL"],
                 declared={"CRWV": "   "})
    offenders, _ = C.undeclared_untrainable(root)
    assert offenders == ["CRWV"]


def test_it_CAN_go_green(tmp_path):
    """A check that cannot pass after the documented remediation is a ratchet.
    Both remedies must work."""
    added_to_universe = _tree(tmp_path / "a", served=["AAPL", "CRWV"],
                              trained=["AAPL", "CRWV"], declared={})
    assert C.undeclared_untrainable(added_to_universe)[0] == []

    declared_instead = _tree(tmp_path / "b", served=["AAPL", "CRWV"],
                             trained=["AAPL"],
                             declared={"CRWV": "IPO 2025-06; 293 rows, far short of the cohort"})
    assert C.undeclared_untrainable(declared_instead)[0] == []


def test_a_ticker_only_in_the_tournament_is_not_an_offender(tmp_path):
    """Direction matters: trained-but-not-served is a different situation and
    this guard must not conflate them."""
    root = _tree(tmp_path, served=["AAPL"], trained=["AAPL", "OLD"], declared={})
    offenders, ev = C.undeclared_untrainable(root)
    assert offenders == []
    assert ev["served_minus_tournament"] == []


def test_case_and_whitespace_do_not_create_phantom_offenders(tmp_path):
    root = _tree(tmp_path, served=[" aapl ", "CRWV"], trained=["AAPL"],
                 declared={"crwv": "declared lowercase"})
    assert C.undeclared_untrainable(root)[0] == []


# ---------------------------------------------------------------------------
# absence must not read as agreement
# ---------------------------------------------------------------------------

def test_a_missing_served_config_RAISES_rather_than_passing(tmp_path):
    """empty-minus-empty is empty, so a moved config would make this check pass
    on a fleet it never inspected."""
    root = _tree(tmp_path, served=["AAPL"], trained=["AAPL"], declared={})
    (root / C.SERVED_CONFIG).unlink()
    with pytest.raises(C.InputMissing, match="served config"):
        C.undeclared_untrainable(root)


def test_an_EMPTY_watchlist_RAISES(tmp_path):
    root = _tree(tmp_path, served=[], trained=["AAPL"], declared={})
    with pytest.raises(C.InputMissing, match="no non-empty 'watchlist'"):
        C.undeclared_untrainable(root)


def test_a_missing_declaration_file_RAISES(tmp_path):
    """Without it the eight deliberate names all look undeclared — the check
    would fire loudly on correct state, which trains people to ignore it."""
    root = _tree(tmp_path, served=["AAPL"], trained=["AAPL"], declared={})
    for p in (root / "logs" / "weekly_tournament_retrain").glob("*.json"):
        p.unlink()
    with pytest.raises(C.InputMissing, match="no declaration file"):
        C.undeclared_untrainable(root)


def test_the_newest_declaration_wins(tmp_path):
    root = _tree(tmp_path, served=["AAPL", "CRWV"], trained=["AAPL"],
                 declared={"CRWV": "declared in the OLD file"})
    old = root / "logs" / "weekly_tournament_retrain" / "2026-08-23.expected_non_trainable.json"
    old.rename(old.with_name("2026-01-01.expected_non_trainable.json"))
    (old.with_name("2026-08-30.expected_non_trainable.json")).write_text(json.dumps({}))
    offenders, ev = C.undeclared_untrainable(root)
    assert offenders == ["CRWV"], "a stale declaration kept silencing a name"
    assert ev["declaration_file"].endswith("2026-08-30.expected_non_trainable.json")


# ---------------------------------------------------------------------------
# the exit contract
# ---------------------------------------------------------------------------

def test_exit_codes_separate_a_violation_from_an_unreadable_input(tmp_path):
    bad = _tree(tmp_path / "v", served=["AAPL", "CRWV"], trained=["AAPL"], declared={})
    assert C.main(["--rq-root", str(bad)]) == 1

    good = _tree(tmp_path / "g", served=["AAPL"], trained=["AAPL"], declared={})
    assert C.main(["--rq-root", str(good)]) == 0

    broken = _tree(tmp_path / "b", served=["AAPL"], trained=["AAPL"], declared={})
    (broken / C.TOURNAMENT_CONFIG).write_text("{not json")
    assert C.main(["--rq-root", str(broken)]) == 2, (
        "an unreadable input must not share an exit code with a real violation")
