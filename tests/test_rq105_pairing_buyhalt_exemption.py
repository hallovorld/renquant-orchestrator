"""Buy-halt reclassification for the rq105 pairing collector (G-F class).

rq105 pairs ENTRY submissions; when the SERVED artifact's WF gate refuses
all new buys (P-WF-GATE, passed=False) there are no entries to pair, so an
empty pairing output is correct, not a fault. The sentinel used to page on
it (answering "did a row arrive today" not "should one have"). These
controls pin the fix AND its fail-closed scope: the page is downgraded to
a non-paging INFO ONLY on an independent buy-blocked proof (the gate
verdict); the page is NEVER flipped to a healthy "ok", and undeterminable
or gate-admits-buys both keep the page.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ops"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ops" / "renquant105"))

from rq105_liveness_check import (  # noqa: E402
    _pairing_buyhalt_reclassify,
    _wf_gate_blocks_buys,
)

STALE = "path last complete row date='2026-08-05' != today '2026-08-10' (stale)"


def test_gate_blocks_buys_downgrades_to_info_never_green():
    status, reason = _pairing_buyhalt_reclassify(False, STALE, "2026-08-05", "2026-08-10", True)
    assert status == "info_buy_halt" and status != "ok"
    assert "P-WF-GATE" in reason and "NOT paged" in reason


def test_gate_admits_buys_keeps_page():
    # gate PASSES (buys allowed) yet pairing stale -> a REAL outage -> page
    status, reason = _pairing_buyhalt_reclassify(False, STALE, "2026-08-05", "2026-08-10", False)
    assert status == "stale_or_missing" and reason == STALE


def test_undeterminable_gate_keeps_page():
    status, reason = _pairing_buyhalt_reclassify(False, STALE, "2026-08-05", "2026-08-10", None)
    assert status == "stale_or_missing" and reason == STALE


def test_healthy_row_stays_ok():
    status, _ = _pairing_buyhalt_reclassify(True, "", "2026-08-10", "2026-08-10", True)
    assert status == "ok"


def _mk_artifact(tmp: Path, passed):
    root = tmp / "backtesting" / "renquant_104" / "artifacts" / "prod"
    root.mkdir(parents=True, exist_ok=True)
    (root / "panel-ltr.alpha158_fund.json").write_text(json.dumps(
        {"wf_gate_metadata": {"passed": passed}} if passed is not None else {}))


def test_gate_reader_true_when_failing(tmp_path):
    _mk_artifact(tmp_path, False)
    assert _wf_gate_blocks_buys(tmp_path) is True


def test_gate_reader_false_when_passing(tmp_path):
    _mk_artifact(tmp_path, True)
    assert _wf_gate_blocks_buys(tmp_path) is False


def test_gate_reader_none_when_no_stamp(tmp_path):
    _mk_artifact(tmp_path, None)  # artifact exists but no wf_gate_metadata
    assert _wf_gate_blocks_buys(tmp_path) is None


def test_gate_reader_none_when_artifact_missing(tmp_path):
    assert _wf_gate_blocks_buys(tmp_path) is None
