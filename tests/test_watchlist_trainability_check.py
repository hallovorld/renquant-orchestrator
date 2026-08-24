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


def _tree(tmp_path: Path, *, served, trained, declared, stamp="2026-08-23",
          run_universe=None) -> Path:
    root = tmp_path / "RenQuant"
    served_p = root / C.SERVED_CONFIG
    tourn_p = root / C.TOURNAMENT_CONFIG
    wk = root / "logs" / "weekly_tournament_retrain"
    decl_p = wk / f"{stamp}.expected_non_trainable.json"
    for p in (served_p, tourn_p, decl_p):
        p.parent.mkdir(parents=True, exist_ok=True)
    served_p.write_text(json.dumps({"watchlist": served}))
    tourn_p.write_text(json.dumps({"watchlist": trained}))
    decl_p.write_text(json.dumps(declared))
    # The run-universe sibling the weekly job writes beside the declaration —
    # the binding. Defaults to the tournament universe so the happy path holds.
    (wk / f"{stamp}.expected_watchlist.json").write_text(
        json.dumps({"watchlist": run_universe if run_universe is not None else trained}))
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
    with pytest.raises(C.InputMissing, match="normalise to NOTHING"):
        C.undeclared_untrainable(root)


def test_a_missing_declaration_file_RAISES(tmp_path):
    """Without it the eight deliberate names all look undeclared — the check
    would fire loudly on correct state, which trains people to ignore it."""
    root = _tree(tmp_path, served=["AAPL"], trained=["AAPL"], declared={})
    for p in (root / "logs" / "weekly_tournament_retrain").glob("*.json"):
        p.unlink()
    with pytest.raises(C.InputMissing, match="no declaration file"):
        C.undeclared_untrainable(root)


AS_OF = __import__("datetime").date(2026, 8, 24)


# ---------------------------------------------------------------------------
# a declaration must be BOUND to the run it describes (codex on #1047)
# ---------------------------------------------------------------------------

def test_a_declaration_for_a_DIFFERENT_universe_does_not_authorise(tmp_path):
    """If the weekly job stops, an old file would go on silencing a newly
    served ticker forever — and that silence is the defect this guard exists to
    end. So the declaration has to be shown to describe the universe being
    checked."""
    root = _tree(tmp_path, served=["AAPL", "CRWV"], trained=["AAPL"],
                 declared={"CRWV": "declared under a different universe"},
                 run_universe=["AAPL", "OLDNAME"])
    with pytest.raises(C.InputMissing, match="DIFFERENT universe"):
        C.undeclared_untrainable(root)


def test_a_declaration_with_no_run_universe_sibling_is_UNVERIFIABLE(tmp_path):
    root = _tree(tmp_path, served=["AAPL"], trained=["AAPL"], declared={})
    for p in (root / "logs" / "weekly_tournament_retrain").glob("*expected_watchlist*"):
        p.unlink()
    with pytest.raises(C.InputMissing, match="cannot be bound"):
        C.undeclared_untrainable(root)


def test_a_declaration_older_than_the_producers_cadence_is_refused(tmp_path):
    """Weekly producer; three missed runs means it stopped. A declaration
    nobody refreshes must not keep authorising silence."""
    root = _tree(tmp_path, served=["AAPL"], trained=["AAPL"], declared={},
                 stamp="2026-07-01")
    with pytest.raises(C.InputMissing, match="old .limit"):
        C._declared(root, {"AAPL"}, today=AS_OF)


def test_a_recent_declaration_is_accepted(tmp_path):
    """Control — the freshness rule must not refuse everything."""
    root = _tree(tmp_path, served=["AAPL"], trained=["AAPL"], declared={},
                 stamp="2026-08-23")
    declared, path = C._declared(root, {"AAPL"}, today=AS_OF)
    assert declared == {} and path.name.startswith("2026-08-23")


def test_a_declaration_whose_name_is_not_a_date_is_refused(tmp_path):
    root = _tree(tmp_path, served=["AAPL"], trained=["AAPL"], declared={},
                 stamp="latest")
    with pytest.raises(C.InputMissing, match="does not begin with an ISO date"):
        C._declared(root, {"AAPL"}, today=AS_OF)


# ---------------------------------------------------------------------------
# normalisation, not list length, decides emptiness
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("which", ["served", "tournament"])
def test_a_watchlist_that_normalises_to_nothing_is_refused(tmp_path, which):
    """`["   "]` is a non-empty LIST that normalises to an empty SET. The set is
    what the comparison uses, so the set is what must be non-empty."""
    kw = {"served": ["AAPL"], "trained": ["AAPL"], "declared": {}}
    kw["served" if which == "served" else "trained"] = ["   ", ""]
    root = _tree(tmp_path, **kw)
    with pytest.raises(C.InputMissing, match="normalise to NOTHING"):
        C.undeclared_untrainable(root)


def test_the_newest_declaration_wins(tmp_path):
    root = _tree(tmp_path, served=["AAPL", "CRWV"], trained=["AAPL"],
                 declared={"CRWV": "declared in the OLD file"})
    wk = root / "logs" / "weekly_tournament_retrain"
    for kind in ("expected_non_trainable", "expected_watchlist"):
        (wk / f"2026-08-23.{kind}.json").rename(wk / f"2026-01-01.{kind}.json")
    (wk / "2026-08-30.expected_non_trainable.json").write_text(json.dumps({}))
    (wk / "2026-08-30.expected_watchlist.json").write_text(
        json.dumps({"watchlist": ["AAPL"]}))

    declared, path = C._declared(root, {"AAPL"},
                                 today=__import__("datetime").date(2026, 9, 1))
    assert declared == {}, "the OLD file went on silencing a name"
    assert path.name == "2026-08-30.expected_non_trainable.json"


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


def test_the_detector_is_REGISTERED_with_the_aggregator():
    """An unwired detector would have allowed the identical five-day silence it
    exists to end — this aggregator's founding finding (#723, "merged with no
    caller"), which codex pointed out I had committed again on #1047.

    Asserted against the registry, not the docstring: a comment saying it is
    wired is exactly the kind of claim that outlives the wiring.
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "ops_audit_reg", ROOT / "ops" / "ops_audit.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    entries = {name: (rel, findings)
               for name, rel, _tail, findings in mod.MEMBERS}
    assert "watchlist-trainability" in entries, sorted(entries)
    rel, findings = entries["watchlist-trainability"]
    assert rel == "watchlist_trainability_check.py"
    assert 1 in findings, "exit 1 must count as a FINDING, not a crash"
    assert 2 not in findings, (
        "exit 2 must NOT be a finding — an unreadable input or an unbindable "
        "declaration is 'could not check', which the aggregator classes as "
        "UNUSABLE rather than checked-and-clean")
