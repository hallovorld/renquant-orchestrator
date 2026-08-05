"""GOAL-7 Arm A input producer — the thing that FEEDS the frozen predicate.

The runner refuses a payload that does not name the gate's own producers.
These tests hold the producer to the other half of that contract: that it
really is those helpers' output, that the served params are checked rather
than assumed, and that a smoke run can never be mistaken for the registered
Arm A window.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from scripts import goal7_arm_a_producer as P  # noqa: E402
from scripts.goal7_arm_a_per_regime_runner import (  # noqa: E402
    ProvenanceMissing, evaluate_predicate, require_gate_provenance)

PAYLOAD = REPO / "doc" / "research" / "data" / "2026-08-05-goal7-arm-a-per-regime.json"


class TestTheServedObjectIsCheckedNotAssumed:
    def test_changed_params_are_REFUSED_not_silently_used(self, tmp_path):
        """Registration §1 voids this study for a different fingerprint. A
        producer that scored history with params the served artifact does not
        carry would answer a question nobody registered."""
        art = json.loads(PAYLOAD.read_text())["provenance"]["params"]
        forged = tmp_path / "a.json"
        forged.write_text(json.dumps(
            {"content_sha256": "x", "params": {**art, "window": 63}}),
            encoding="utf-8")
        with pytest.raises(P.ServedParamsChanged) as exc:
            P.served_params(forged)
        assert "window" in str(exc.value)

    def test_the_UNCHANGED_served_params_pass(self, tmp_path):
        art = json.loads(PAYLOAD.read_text())["provenance"]["params"]
        ok = tmp_path / "a.json"
        ok.write_text(json.dumps({"content_sha256": "x", "params": art}),
                      encoding="utf-8")
        assert P.served_params(ok)["params"]["window"] == 252


class TestTheServedObjectIsTheLEDGERSRowNotAFileOnDisk:
    """[codex on orch#825] Reading the artifact FILE and trusting its own
    `content_sha256` proves only that the file is self-consistent. The served
    object is the ledger's row; an artifact no row points at is not what the
    blend loads."""

    def _ledger(self, tmp_path, *rows):
        p = tmp_path / "ledger.jsonl"
        p.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        return p

    def test_a_sha_NO_row_carries_is_refused(self, tmp_path):
        led = self._ledger(tmp_path, {"artifact_content_sha256": "aaa"})
        with pytest.raises(P.ServedArtifactNotLedgered) as exc:
            P.ledger_row_for("bbb", led)
        assert "no ledger row carries" in str(exc.value)

    def test_an_ABSENT_ledger_is_refused_not_skipped(self, tmp_path):
        with pytest.raises(P.ServedArtifactNotLedgered):
            P.ledger_row_for("aaa", tmp_path / "nope.jsonl")

    def test_an_UNPARSEABLE_line_is_refused(self, tmp_path):
        p = tmp_path / "l.jsonl"
        p.write_text('{"artifact_content_sha256": "aaa"}\n{not json\n',
                     encoding="utf-8")
        with pytest.raises(P.ServedArtifactNotLedgered) as exc:
            P.ledger_row_for("aaa", p)
        assert "not JSON" in str(exc.value), (
            "'I could not check' must not read like 'it checks out'")

    def test_the_row_identity_is_recorded_including_its_CHAIN_position(
            self, tmp_path):
        led = self._ledger(tmp_path,
                           {"artifact_content_sha256": "aaa", "prev_row_sha": None},
                           {"artifact_content_sha256": "bbb",
                            "prev_row_sha": "sha-of-aaa", "cutoff_date": "2026-08-02"})
        row = P.ledger_row_for("bbb", led)
        assert row["is_ledger_tail"] is True
        assert row["prev_row_sha"] == "sha-of-aaa"
        older = P.ledger_row_for("aaa", led)
        assert older["is_ledger_tail"] is False, (
            "reconstructing a superseded row is legal but must SAY so")


class TestTheInputsAreFingerprintedNotJustCounted:
    """A payload recording only summary counts could be reproduced from revised
    data, or by revised feature code under unchanged params, and report
    different numbers while looking identical [codex on orch#825]."""

    def test_the_rollup_is_ORDER_independent_but_VALUE_sensitive(self):
        a = {"ohlcv/AAPL": "sha1", "ohlcv/MSFT": "sha2"}
        assert P._digest_of_mapping(a) == P._digest_of_mapping(
            {"ohlcv/MSFT": "sha2", "ohlcv/AAPL": "sha1"})
        assert P._digest_of_mapping(a) != P._digest_of_mapping(
            {"ohlcv/AAPL": "sha1", "ohlcv/MSFT": "CHANGED"})
        assert P._digest_of_mapping(a) != P._digest_of_mapping({"ohlcv/AAPL": "sha1"})

    def test_a_MUTATED_input_makes_the_result_non_comparable(self, payload_or_skip):
        """The mutation test the review asked for: flip ONE surface's digest and
        the roll-up no longer matches the record, so the two runs cannot be
        compared even though every summary count is identical."""
        recorded = payload_or_skip["input_read_digests"]
        assert recorded, "the payload must itemise what it read"
        mutated = dict(recorded)
        victim = sorted(mutated)[0]
        mutated[victim] = "sha256:" + "0" * 64
        assert (P._digest_of_mapping(mutated)
                != payload_or_skip["provenance"]["input_read_digests_sha256"])

    def test_the_payload_records_the_CODE_that_produced_it(self, payload_or_skip):
        revs = payload_or_skip["provenance"]["code_revisions"]
        assert set(revs) == {"renquant-orchestrator", "renquant-model",
                             "renquant-backtesting", "renquant-pipeline"}
        assert all(v is None or len(v) == 40 for v in revs.values()), revs

    def test_the_payload_records_the_ledger_row_it_reconstructed(
            self, payload_or_skip):
        row = payload_or_skip["provenance"]["served_ledger_row"]
        assert row["artifact_content_sha256"] == (
            payload_or_skip["provenance"]["served_artifact_content_sha256"])
        assert row["is_ledger_tail"] is True
        assert row["cutoff_date"] == "2026-08-02"


@pytest.fixture
def payload_or_skip():
    if not PAYLOAD.is_file():
        pytest.skip("payload absent")
    d = json.loads(PAYLOAD.read_text())
    if "input_read_digests" not in d:
        pytest.skip("payload predates input fingerprinting")
    return d


class TestTheShuffleIsTheRegisteredOne:
    def test_the_permutation_stays_INSIDE_each_date(self):
        """§4's placebo is a within-date label shuffle. Permuting across dates
        would also destroy the date structure the IC is computed over — a
        different, weaker null that would flatter the candidate."""
        import pandas as pd

        val = pd.DataFrame({
            "ticker": list("abcdef"),
            "date": ["d1"] * 3 + ["d2"] * 3,
            P.LABEL: [1.0, 2.0, 3.0, 10.0, 20.0, 30.0],
        })
        out = P._shuffle_within_date(val, seed=1)
        for d in ("d1", "d2"):
            before = sorted(val.loc[val["date"] == d, P.LABEL])
            after = sorted(out.loc[out["date"] == d, P.LABEL])
            assert before == after, "a date's label MULTISET must be preserved"

    def test_the_seeds_are_the_five_the_registration_fixed(self):
        assert P.SHUFFLE_SEEDS == (1, 2, 3, 4, 5)

    def test_the_shift_is_the_gates_own_2x_horizon_leg(self):
        assert P.GATE_SHIFT_DAYS == 120


class TestTheRunOnRecord:
    """Bound to the payload this session actually produced. If any of it moves,
    the GOAL-7 record must be re-derived rather than inherited."""

    @pytest.fixture(scope="class")
    def payload(self):
        return json.loads(PAYLOAD.read_text())

    def test_the_runner_ACCEPTS_it(self, payload):
        assert require_gate_provenance(payload)

    def test_it_names_all_three_gate_helpers(self, payload):
        assert set(payload["provenance"]["producers"]) == set(P.PRODUCERS)

    def test_the_window_is_the_registered_one_not_a_smoke_run(self, payload):
        prov = payload["provenance"]
        assert prov["window_rule"] == "every matured panel date — no range selected"
        assert "SMOKE" not in prov["window_rule"]
        assert prov["n_scored_dates"] == 2380
        assert prov["n_scored_rows"] == 661622

    def test_the_served_artifact_is_the_one_the_registration_names(self, payload):
        assert payload["provenance"]["served_artifact_content_sha256"] == (
            "a824c480cd9c564b8cb7276a5b8c03882d26c833fec6ee53ba234b952cb30109")

    def test_the_PRIMARY_regime_numbers(self, payload):
        c = payload["per_regime"]["BULL_CALM"]
        assert c["n_dates"] == 1684
        assert c["mean_ic"] == pytest.approx(0.02975, abs=5e-5)
        assert c["placebo_shuffle"] == pytest.approx(0.00061, abs=5e-5)
        assert c["placebo_shift"] == pytest.approx(0.02305, abs=5e-5)

    def test_all_four_conditions_hold_AND_it_still_certifies_NOTHING(self, payload):
        """The whole point of §3. Arm A is a reconstruction; passing every
        condition is not a verdict, and the outcome string must say so."""
        v = evaluate_predicate(payload["per_regime"])
        assert v["failed_conditions"] == []
        assert all(v["conditions"].values())
        assert v["outcome"] == "EXPLORATORY — NOT A CERTIFICATION"
        assert "cannot certify" in v["meaning"]

    def test_the_SECONDARY_regimes_cannot_change_the_verdict(self, payload):
        """BULL_VOLATILE is negative on both placebos. §2 pre-commits the
        primary, so this is reported and cannot be promoted to the headline —
        which is exactly the error the pooled figure already commits."""
        c = payload["per_regime"]["BULL_VOLATILE"]
        assert c["mean_ic"] < 0
        v = evaluate_predicate(payload["per_regime"])
        assert v["primary_regime"] == "BULL_CALM"
        assert v["mean_ic"] == payload["per_regime"]["BULL_CALM"]["mean_ic"]


def test_a_payload_without_provenance_is_REFUSED_by_the_runner():
    with pytest.raises(ProvenanceMissing):
        require_gate_provenance({"per_regime": {"BULL_CALM": {"mean_ic": 9.9}}})
