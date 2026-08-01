"""The live daily record cannot say which model decided — measured, with the false
finding it invites explicitly refuted.

14 live per-date records, 63 decision rows: 0/14 carry override provenance, 0/14 carry any
artifact identity, and 14 of 24 BUY rows have `active_scorer: None`. orch#713 measured that
the served artifact is admitted under an operator override; the record of what the book did
neither says so nor carries a digest by which it could be looked up.
"""

from __future__ import annotations

import json
import pathlib
import sys

import pytest

OPS = pathlib.Path(__file__).resolve().parent.parent / "ops" / "renquant104"
sys.path.insert(0, str(OPS))

import live_decision_provenance as L  # noqa: E402


def _write(tmp, name, rows):
    p = tmp / name
    p.write_text(json.dumps(rows))
    return p


# --------------------------------------------------- the false finding, refuted --
def test_SELL_rows_do_not_show_up_as_a_buy_side_scorer(tmp_path):
    """`active_scorer: hf_patchtst` on 38 rows reads as 'the stale checkpoint decides the
    book'. It does not — they are SELLs, carrying the scorer that ENTERED the position.
    The split is computed so the reader cannot make that leap."""
    _write(tmp_path, "d.json", [
        {"action": "SELL", "active_scorer": "hf_patchtst"},
        {"action": "BUY", "active_scorer": "blend"},
    ])
    rep = L.survey(str(tmp_path / "*.json"))
    assert rep["action_scorer_counts"]["SELL/hf_patchtst"] == 1
    assert rep["n_buy_rows"] == 1
    assert "SELLs" in rep["not_a_finding"] and "#569" in rep["not_a_finding"]


def test_buy_rows_with_no_scorer_are_counted_separately_from_all_buys(tmp_path):
    _write(tmp_path, "d.json", [
        {"action": "BUY", "active_scorer": None},
        {"action": "BUY", "active_scorer": "blend"},
        {"action": "SELL", "active_scorer": None},
    ])
    rep = L.survey(str(tmp_path / "*.json"))
    assert rep["n_buy_rows"] == 2
    assert rep["buy_rows_without_active_scorer"] == 1      # the SELL is not counted


# ------------------------------------------------------------- provenance itself --
def test_a_record_with_override_provenance_counts_as_covered(tmp_path):
    _write(tmp_path, "d.json", [{"action": "BUY", "active_scorer": "x",
                                 "operator_authorized_override": True}])
    rep = L.survey(str(tmp_path / "*.json"))
    assert rep["files_with_override_provenance"] == 1
    assert L.main(["--records", str(tmp_path / "*.json")]) == 0


def test_a_record_without_it_exits_1(tmp_path):
    _write(tmp_path, "d.json", [{"action": "BUY", "active_scorer": "x"}])
    assert L.main(["--records", str(tmp_path / "*.json")]) == 1


def test_artifact_identity_is_checked_separately_from_override_provenance(tmp_path):
    """A record could name the artifact without saying it was overridden — those are
    different gaps and collapsing them would hide the recoverable case."""
    _write(tmp_path, "d.json", [{"action": "BUY", "active_scorer": "x",
                                 "fingerprint": "sha256:abc"}])
    rep = L.survey(str(tmp_path / "*.json"))
    assert rep["files_with_any_artifact_identity"] == 1
    assert rep["files_with_override_provenance"] == 0


# ------------------------------------------------------------------ fail-closed --
def test_an_UNREADABLE_record_is_not_counted_as_missing_provenance(tmp_path):
    """Unreadable is unmeasured. Counting it as a finding would inflate the gap with
    files nobody read."""
    (tmp_path / "bad.json").write_text("{not json")
    _write(tmp_path, "ok.json", [{"action": "BUY", "active_scorer": "x",
                                  "override_reason": "r"}])
    rep = L.survey(str(tmp_path / "*.json"))
    assert rep["n_files_read"] == 1 and rep["n_files_unreadable"] == 1
    assert rep["files_with_override_provenance"] == 1
    assert L.main(["--records", str(tmp_path / "*.json")]) == 0


def test_NO_records_SKIPS_with_3_rather_than_reporting_clean(tmp_path):
    assert L.survey(str(tmp_path / "nope*.json"))["status"] == "no_records"
    assert L.main(["--records", str(tmp_path / "nope*.json")]) == 3


def test_a_non_list_payload_does_not_crash(tmp_path):
    (tmp_path / "d.json").write_text(json.dumps({"not": "a list"}))
    rep = L.survey(str(tmp_path / "*.json"))
    assert rep["n_files_read"] == 1 and rep["n_rows"] == 0
