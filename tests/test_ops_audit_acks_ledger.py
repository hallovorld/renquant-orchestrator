"""GOAL-1: the FIRST entry in the ops-audit ack ledger.

orch#823 measured it: `com.renquant.ops-audit` fires 9–10 of 11 detectors every
run and `ops_audit_acks.json` did not exist — the disposition mechanism was
built and never used. These tests hold the first ack to the standard that makes
using it safe: it must be bound to a live fingerprint, carry an expiry, cover a
SITUATION rather than a magnitude, and it must not have quietly swallowed the
real defect sitting next to it.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
import sys

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "ops"))
from audit_finding_disposition import (  # noqa: E402
    ACKED, CHANGED, EXPIRED, NEW, classify, fingerprint, numbers)

LEDGER = REPO / "ops" / "ops_audit_acks.json"
ACK_FP = "e3ecdd6587cdaf4e"


#: The exact line the live detector emits — reachability included.
LIVE_TEXT = ("gate-stamp parity: 36 artifact(s) scanned — 16 carry BOTH copies "
             "(0 of them SERVED by a pinned config), 20 canonical-only, "
             "0 legacy-only, 0 no stamp, 0 malformed, 0 unreadable")


@pytest.fixture(scope="module")
def ledger():
    return json.loads(LEDGER.read_text(encoding="utf-8"))


class TestTheLedgerIsUsableAtAll:
    def test_it_exists_and_parses(self, ledger):
        """orch#823's finding was that this file did not exist."""
        assert isinstance(ledger, dict) and ledger

    def test_every_ack_carries_a_reason_and_an_expiry(self, ledger):
        for fp, ack in ledger.items():
            assert ack.get("reason"), fp
            assert ack.get("acked_at"), fp
            assert ack.get("expires_at"), (
                fp, "an ack with no explicit expiry is permanent suppression "
                    "with extra steps")
            assert dt.date.fromisoformat(ack["expires_at"]) > dt.date.fromisoformat(
                ack["acked_at"]), fp

    def test_every_ack_records_the_numbers_it_was_taken_against(self, ledger):
        """An ack covers a situation, not a magnitude — that only works if the
        magnitude at ack time is written down."""
        for fp, ack in ledger.items():
            assert isinstance(ack.get("numbers_when_acked"), list), fp
            assert ack["numbers_when_acked"], fp


class TestTheAckIsBoundToARealFinding:
    """An ack whose fingerprint matches nothing is a ledger entry that will
    never fire and never be noticed."""

    def test_the_fingerprint_is_the_one_the_live_detector_produces(self, ledger):
        ack = ledger[ACK_FP]
        text = LIVE_TEXT
        assert fingerprint(ack["member"], text) == ACK_FP
        assert numbers(text) == ack["numbers_when_acked"]

    def test_it_classifies_as_ACKED_today(self, ledger):
        d = classify("gate-stamp-parity", LIVE_TEXT, ledger, dt.date(2026, 8, 5))
        assert d["state"] == ACKED, d


class TestTheAckCoversASituationNotAMagnitude:
    def _classify(self, ledger, text, day=dt.date(2026, 8, 5)):
        return classify("gate-stamp-parity", text, ledger, day)["state"]

    def test_a_CONFIG_CHANGE_ALONE_breaks_the_ack(self, ledger):
        """[codex on orch#829] THE blocker. The ack says it clears when a
        both-copy artifact becomes SERVED — but if the fingerprint carried only
        census counts, pointing a pinned config at one of the existing 16 would
        leave 36/16/20/0/0/0/0 unchanged and the ack would keep holding over a
        now-reachable conflicting verdict. The served count is IN the summary,
        so this alone breaks it."""
        s = self._classify(ledger, LIVE_TEXT.replace(
            "(0 of them SERVED", "(1 of them SERVED"))
        assert s == CHANGED, s

    def test_reachability_becoming_UNKNOWN_breaks_the_ack(self, ledger):
        """'I could not read the configs' must not inherit an ack taken when
        the answer was known."""
        s = self._classify(ledger, LIVE_TEXT.replace(
            "(0 of them SERVED by a pinned config)",
            "(reachability UNKNOWN (pinned configs unreadable))"))
        assert s in (CHANGED, NEW), s

    def test_a_LEGACY_ONLY_artifact_appearing_breaks_the_ack(self, ledger):
        """A legacy-only stamp means a reader can get a verdict the canonical
        copy never gave."""
        s = self._classify(ledger, LIVE_TEXT.replace(
            "20 canonical-only, 0 legacy-only", "19 canonical-only, 1 legacy-only"))
        assert s == CHANGED, s

    def test_MORE_both_copy_artifacts_breaks_the_ack(self, ledger):
        s = self._classify(ledger, LIVE_TEXT.replace(
            "36 artifact(s) scanned — 16 carry", "40 artifact(s) scanned — 20 carry"))
        assert s == CHANGED, s

    def test_it_EXPIRES_on_its_own(self, ledger):
        """'No config points at it' is a fact about today's configs."""
        assert self._classify(ledger, LIVE_TEXT, day=dt.date(2026, 9, 6)) == EXPIRED


class TestWhatWasDELIBERATELYNotAcked:
    """The value of an ack ledger is destroyed by one dishonest entry."""

    def test_booster_identity_is_NOT_acked(self, ledger):
        """36 artifacts → 15 distinct boosters under ONE identity is a real open
        defect: the WF gate admits on the recipe hash and never scores the
        candidate's booster. Acking it is the failure this ledger exists to
        avoid, and the omission is asserted rather than merely intended."""
        assert not any(a.get("member") == "booster-identity"
                       for a in ledger.values())

    def test_only_ONE_detector_is_acked_at_all(self, ledger):
        members = {a.get("member") for a in ledger.values()}
        assert members == {"gate-stamp-parity"}, (
            "eight other findings stay loud — this ledger's first entry is a "
            "disposition, not a cleanup", members)

    def test_the_ack_says_out_loud_what_it_does_not_cover(self, ledger):
        assert "booster-identity" in ledger[ACK_FP]["not_acked_note"]


def test_the_LIVE_audit_reports_it_as_INFO_not_as_a_finding():
    """End-to-end: the mechanism has to actually change the report, or this is
    a ledger nobody reads either."""
    import subprocess

    ops = REPO / "ops" / "ops_audit.py"
    if not ops.is_file():
        pytest.skip("ops_audit absent")
    proc = subprocess.run([sys.executable, str(ops), "--json"],
                          capture_output=True, text=True, timeout=900)
    if proc.returncode not in (0, 1):
        pytest.skip(f"ops_audit unusable here (rc={proc.returncode})")
    out = json.loads(proc.stdout)
    row = next(r for r in out["results"] if r["member"] == "gate-stamp-parity")
    assert row["disposition"] == ACKED, row
    assert out["counts"]["info"] >= 1, out["counts"]
    others = [r for r in out["results"]
              if r["status"] == "findings" and r["disposition"] == NEW]
    assert others, "if everything went quiet at once, something is wrong"


def test_the_reachability_check_compares_PATHS_not_basenames(tmp_path):
    """A basename match reaches outside its subject: a synthetic fixture named
    `panel-ltr.alpha158_fund.json` in a scratch directory is not the served
    artifact. The first version of this check flagged one, i.e. it answered a
    question about the operator's disk instead of about the root it was asked
    to scan — caught by the parity suite, and pinned here."""
    sys.path.insert(0, str(REPO / "ops" / "renquant104"))
    import gate_stamp_parity as G

    stamp = {"metadata": {"wf_gate_metadata": {"passed": True}},
             "wf_gate_metadata": {"passed": False}}
    (tmp_path / "panel-ltr.alpha158_fund.json").write_text(json.dumps(stamp),
                                                           encoding="utf-8")
    problems, infos = G.scan(str(tmp_path), "panel-ltr.alpha158_fund*.json")
    assert "0 of them SERVED by a pinned config" in infos[0], infos
    assert not any("SELECTED BY A PINNED CONFIG" in p for p in problems), problems
