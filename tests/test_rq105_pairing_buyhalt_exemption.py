"""Buy-halt reclassification for the rq105 pairing collector (G-F class).

rq105 pairs ENTRY submissions; when the SERVED artifact's WF gate refuses
all new buys (P-WF-GATE) there are no entries to pair, so an empty pairing
output is correct, not a fault. The sentinel used to page on it (answering
"did a row arrive today" not "should one have"). These controls pin the fix
AND its fail-closed scope: the page is downgraded to a non-paging INFO ONLY
on an INDEPENDENT buy-blocked proof — the AUTHORITATIVE admission verdict
(`wf_gate_admits_buys`, RFC#210 license included), NOT a raw `passed is
False` read. The page is NEVER flipped to a healthy "ok", and an
RFC#210-licensed passed=false (buys admitted) or an undeterminable read both
keep the page.
"""
from __future__ import annotations

import datetime as dt
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

# a WF stamp that ADMITS buys needs the three numerics + n_cuts_beat_spy_sharpe
_NUMERICS = {
    "wf_3cut_sharpe_mean": 0.6,
    "spy_sharpe_mean": 0.4,
    "strategy_minus_spy_sharpe_mean": 0.2,
    "n_cuts_beat_spy_sharpe": 3,
}


# ---- the pure reclassify decision table -------------------------------------

def test_gate_blocks_buys_downgrades_to_info_never_green():
    status, reason = _pairing_buyhalt_reclassify(False, STALE, "2026-08-05", "2026-08-10", True)
    assert status == "info_buy_halt" and status != "ok"
    assert "P-WF-GATE" in reason and "NOT paged" in reason


def test_gate_admits_buys_keeps_page():
    # gate ADMITS buys yet pairing stale -> a REAL outage -> page
    status, reason = _pairing_buyhalt_reclassify(False, STALE, "2026-08-05", "2026-08-10", False)
    assert status == "stale_or_missing" and reason == STALE


def test_undeterminable_gate_keeps_page():
    status, reason = _pairing_buyhalt_reclassify(False, STALE, "2026-08-05", "2026-08-10", None)
    assert status == "stale_or_missing" and reason == STALE


def test_healthy_row_stays_ok():
    status, _ = _pairing_buyhalt_reclassify(True, "", "2026-08-10", "2026-08-10", True)
    assert status == "ok"


# ---- the gate reader consumes the shared admission authority ----------------

def _mk_artifact(tmp: Path, *, canonical=..., legacy=..., promotion_basis=None,
                 trained_date=None):
    """Write the served panel artifact. ``canonical``/``legacy`` are the value
    of the ``passed`` flag (or ``None`` for a stamp present-but-without-passed,
    or ``...`` to omit that stamp entirely). Numerics are always included so a
    block is attributable to ``passed`` unless a test drops them explicitly."""
    root = tmp / "backtesting" / "renquant_104" / "artifacts" / "prod"
    root.mkdir(parents=True, exist_ok=True)
    payload: dict = {}
    if promotion_basis is not None:
        payload["promotion_basis"] = promotion_basis
    if trained_date is not None:
        payload["trained_date"] = trained_date

    def _stamp(passed):
        if passed is None:
            return dict(_NUMERICS)  # numerics present, no `passed`
        return {"passed": passed, **_NUMERICS}

    if legacy is not ...:
        payload["wf_gate_metadata"] = _stamp(legacy)
    if canonical is not ...:
        payload.setdefault("metadata", {})["wf_gate_metadata"] = _stamp(canonical)
    (root / "panel-ltr.alpha158_fund.json").write_text(json.dumps(payload))


def test_gate_reader_true_when_canonical_failing(tmp_path):
    # passed=False, NOT RFC#210-licensed -> authority BLOCKS -> buys blocked
    _mk_artifact(tmp_path, canonical=False)
    assert _wf_gate_blocks_buys(tmp_path) is True


def test_gate_reader_false_when_canonical_passing(tmp_path):
    _mk_artifact(tmp_path, canonical=True)
    assert _wf_gate_blocks_buys(tmp_path) is False


def test_rfc210_licensed_passed_false_keeps_page(tmp_path):
    # THE r7 REGRESSION: a fresh governance-served artifact serves passed=False
    # BY DESIGN and P-WF-GATE ADMITS buys -> NOT blocked -> the page stands.
    fresh = (dt.date.today() - dt.timedelta(days=5)).isoformat()
    _mk_artifact(tmp_path, canonical=False,
                 promotion_basis="freshness_fallback_rfc210", trained_date=fresh)
    assert _wf_gate_blocks_buys(tmp_path) is False


def test_rfc210_stale_passed_false_blocks(tmp_path):
    # the freshness license EXPIRES at 28d: a stale passed=False is blocked
    old = (dt.date.today() - dt.timedelta(days=40)).isoformat()
    _mk_artifact(tmp_path, canonical=False,
                 promotion_basis="freshness_fallback_rfc210", trained_date=old)
    assert _wf_gate_blocks_buys(tmp_path) is True


def test_gate_reader_missing_numerics_blocks(tmp_path):
    # passed=True but the required numerics absent -> the authority BLOCKS
    root = tmp_path / "backtesting" / "renquant_104" / "artifacts" / "prod"
    root.mkdir(parents=True, exist_ok=True)
    (root / "panel-ltr.alpha158_fund.json").write_text(
        json.dumps({"metadata": {"wf_gate_metadata": {"passed": True}}}))
    assert _wf_gate_blocks_buys(tmp_path) is True


def test_canonical_wins_over_stale_legacy(tmp_path):
    # canonical passed=True (admits) with a STALE legacy passed=False: the
    # authority reads canonical first -> admits -> NOT blocked
    _mk_artifact(tmp_path, canonical=True, legacy=False)
    assert _wf_gate_blocks_buys(tmp_path) is False


def test_agreeing_stamps_block(tmp_path):
    _mk_artifact(tmp_path, canonical=False, legacy=False)
    assert _wf_gate_blocks_buys(tmp_path) is True


def test_legacy_only_falls_back(tmp_path):
    _mk_artifact(tmp_path, legacy=False)
    assert _wf_gate_blocks_buys(tmp_path) is True


def test_gate_reader_blocks_when_no_stamp(tmp_path):
    # a valid artifact with NO wf stamp at all: the authority's verdict is
    # "absent -> buy runs blocked by P-WF-GATE" (the runtime refuses an
    # unstamped artifact) -> blocked
    root = tmp_path / "backtesting" / "renquant_104" / "artifacts" / "prod"
    root.mkdir(parents=True, exist_ok=True)
    (root / "panel-ltr.alpha158_fund.json").write_text(json.dumps({"kind": "panel"}))
    assert _wf_gate_blocks_buys(tmp_path) is True


def test_gate_reader_none_when_artifact_missing(tmp_path):
    assert _wf_gate_blocks_buys(tmp_path) is None
