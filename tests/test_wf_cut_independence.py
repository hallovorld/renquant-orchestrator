"""How independent are the WF gate's economic cuts?

A count like `n_positive_cuts: 3` is only as strong as the independence of the things
counted. These tests target the ways this measurement could overstate that independence —
a dropped cut making the rest look disjoint, an absent cut set reading as clean, and
geometry being presented as an effective sample size.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
MOD = ROOT / "ops" / "renquant104" / "wf_cut_independence.py"


def _load():
    spec = importlib.util.spec_from_file_location("wci", MOD)
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


C = _load()
D = dt.date


def _art(tmp_path, cuts, name="a.json", legacy=False, raw=None):
    block = raw if raw is not None else {"cuts": cuts}
    body = ({"wf_gate_metadata": block} if legacy
            else {"metadata": {"wf_gate_metadata": block}})
    p = tmp_path / name
    p.write_text(json.dumps(body), encoding="utf-8")
    return str(p)


# --- the geometry -----------------------------------------------------------

def test_DISJOINT_cuts_have_redundancy_one(tmp_path):
    r = C.analyse([(D(2024, 1, 1), D(2024, 6, 30)), (D(2024, 7, 1), D(2024, 12, 31))])
    assert r["disjoint"] is True and r["overlapping_pairs"] == []
    assert abs(r["redundancy"] - 1.0) < 0.02


def test_OVERLAP_is_reported_as_a_fraction_of_the_SHORTER_window(tmp_path):
    """Against the longer window a big overlap looks small — the shorter one is what
    determines how much of an observation is not new."""
    r = C.analyse([(D(2024, 1, 1), D(2025, 1, 1)), (D(2024, 10, 1), D(2025, 1, 1))])
    p = r["overlapping_pairs"][0]
    assert p["frac_of_shorter"] == 1.0


def test_redundancy_counts_REUSED_calendar(tmp_path):
    """Two identical windows: 2x the length over 1x the calendar."""
    r = C.analyse([(D(2024, 1, 1), D(2025, 1, 1)), (D(2024, 1, 1), D(2025, 1, 1))])
    assert abs(r["redundancy"] - 2.0) < 0.01


def test_the_DISJOINT_CEILING_is_arithmetic_not_a_guess(tmp_path):
    assert C.ceiling(882, 364) == 2
    assert C.ceiling(882, 252) == 3
    assert C.ceiling(882, 182) == 4


# --- ways the measurement could overstate independence ----------------------

def test_an_UNREADABLE_cut_is_REPORTED_not_dropped(tmp_path):
    """Silently shrinking the cut set makes the remainder look more independent than it
    is — the exact quantity under measurement."""
    a = _art(tmp_path, [{"start": "2024-01-01", "end": "2024-12-31"},
                        {"start": "nonsense", "end": "2025-06-30"}])
    p = json.loads(pathlib.Path(a).read_text())
    cuts, bad = C._cuts(p["metadata"]["wf_gate_metadata"])
    assert len(cuts) == 1 and len(bad) == 1
    assert C.main(["--artifact", a]) == 1          # cannot pass with a cut unread


def test_a_NON_OBJECT_cut_is_reported(tmp_path):
    a = _art(tmp_path, ["2024-01-01"])
    _, bad = C._cuts(json.loads(pathlib.Path(a).read_text())
                     ["metadata"]["wf_gate_metadata"])
    assert bad and "not an object" in bad[0]


def test_an_INVERTED_cut_is_rejected_not_counted_as_negative_length(tmp_path):
    a = _art(tmp_path, [{"start": "2025-01-01", "end": "2024-01-01"}])
    cuts, bad = C._cuts(json.loads(pathlib.Path(a).read_text())
                        ["metadata"]["wf_gate_metadata"])
    assert cuts == [] and bad and "not after" in bad[0]


def test_a_NON_LIST_cuts_field_is_reported(tmp_path):
    a = _art(tmp_path, None, raw={"cuts": "three"})
    _, bad = C._cuts(json.loads(pathlib.Path(a).read_text())
                     ["metadata"]["wf_gate_metadata"])
    assert bad and "not a list" in bad[0]


def test_NO_GATE_BLOCK_exits_1_not_0(tmp_path, capsys):
    """'No cut set' must never read as 'the cuts are independent'."""
    p = tmp_path / "n.json"
    p.write_text(json.dumps({"feature_cols": []}), encoding="utf-8")
    assert C.main(["--artifact", str(p)]) == 1
    assert "not the same as independent cuts" in capsys.readouterr().err


def test_a_MALFORMED_metadata_container_does_not_crash(tmp_path):
    p = tmp_path / "m.json"
    p.write_text(json.dumps({"metadata": "n/a"}), encoding="utf-8")
    assert C.main(["--artifact", str(p)]) == 1


def test_a_LEGACY_gate_block_is_read_and_the_source_recorded(tmp_path, capsys):
    a = _art(tmp_path, [{"start": "2024-01-01", "end": "2024-06-30"}], legacy=True)
    C.main(["--artifact", a])
    assert "legacy top-level" in capsys.readouterr().out


def test_a_MISSING_artifact_exits_2(tmp_path):
    assert C.main(["--artifact", str(tmp_path / "gone.json")]) == 2


def test_ANTI_VACUITY_disjoint_cuts_exit_ZERO(tmp_path):
    """Without this the check could flag every artifact and prove nothing."""
    a = _art(tmp_path, [{"start": "2024-01-01", "end": "2024-06-30"},
                        {"start": "2024-07-01", "end": "2024-12-31"}])
    assert C.main(["--artifact", a]) == 0


def test_the_report_REFUSES_to_call_geometry_an_effective_sample_size(tmp_path, capsys):
    """Redundancy is derivable from boundaries alone. Converting it to an effective n
    needs a correlation this tool does not measure — a standing correction here."""
    a = _art(tmp_path, [{"start": "2024-01-01", "end": "2024-12-31"},
                        {"start": "2024-07-01", "end": "2025-06-30"}])
    C.main(["--artifact", a])
    out = capsys.readouterr().out
    assert "not an effective sample size" in out


def test_the_REAL_artifact_reproduces_the_finding():
    """The numbers in the module docstring must stay derivable, or the docstring becomes
    an assertion with a citation attached."""
    import os
    p = ("/Users/renhao/git/github/RenQuant/backtesting/renquant_104/artifacts/"
         "prod/panel-ltr.alpha158_fund.previous.json")
    if not os.path.exists(p):
        import pytest
        pytest.skip("live artifact not present on this machine")
    block, _ = C._gate_block(json.loads(pathlib.Path(p).read_text()))
    cuts, bad = C._cuts(block)
    r = C.analyse(cuts)
    assert bad == [] and r["n_cuts"] == 3
    assert r["calendar_union_days"] == 816 and r["sum_of_lengths_days"] == 1089
    assert 1.33 <= r["redundancy"] <= 1.34
    assert C.ceiling(882, max(r["cut_lengths_days"])) == 2
