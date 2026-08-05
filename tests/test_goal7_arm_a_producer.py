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


def _sealed_artifact(tmp_path, params, name="a.json"):
    """A synthetic artifact whose content_sha256 actually recomputes — the
    fixture has to satisfy the same integrity contract production does, or the
    test is exercising the guard instead of the thing behind it."""
    from renquant_model_momentum.train import content_sha256_of

    body = {"kind": "momentum_residual_v0", "params": params}
    body["content_sha256"] = content_sha256_of(body)
    p = tmp_path / name
    p.write_text(json.dumps(body), encoding="utf-8")
    return p


class TestTheServedObjectIsCheckedNotAssumed:
    def test_changed_params_are_REFUSED_not_silently_used(self, tmp_path):
        """Registration §1 voids this study for a different fingerprint. A
        producer that scored history with params the served artifact does not
        carry would answer a question nobody registered."""
        art = json.loads(PAYLOAD.read_text())["provenance"]["params"]
        forged = _sealed_artifact(tmp_path, {**art, "window": 63})
        with pytest.raises(P.ServedParamsChanged) as exc:
            P.served_params(forged)
        assert "window" in str(exc.value)

    def test_the_UNCHANGED_served_params_pass(self, tmp_path):
        art = json.loads(PAYLOAD.read_text())["provenance"]["params"]
        assert P.served_params(_sealed_artifact(tmp_path, art))["params"][
            "window"] == 252


class TestTheServedObjectIsTheLEDGERSRowNotAFileOnDisk:
    """[codex on orch#825] Reading the artifact FILE and trusting its own
    `content_sha256` proves only that the file is self-consistent. The served
    object is the ledger's row; an artifact no row points at is not what the
    blend loads."""

    def _chained(self, tmp_path, *shas):
        """A ledger built by the model package's OWN appender, so the chain it
        is checked against is the one production writes."""
        from renquant_model_momentum.ledger import append_chained_row

        led = tmp_path / "ledger.jsonl"
        for sha in shas:
            append_chained_row(
                {"kind": "momentum_residual_v0", "cutoff_date": "2026-08-02",
                 "params_version": "v0", "artifact_content_sha256": sha},
                led)
        return led

    def test_a_sha_NO_row_carries_is_refused(self, tmp_path):
        led = self._chained(tmp_path, "aaa")
        with pytest.raises(P.ServedArtifactNotLedgered) as exc:
            P.ledger_row_for("bbb", led)
        assert "no ledger row carries" in str(exc.value)

    def test_a_ROW_MISSING_the_chain_fields_is_refused(self, tmp_path):
        """A hand-written line that merely declares a sha is not a ledger row."""
        led = tmp_path / "l.jsonl"
        led.write_text(json.dumps({"artifact_content_sha256": "aaa"}) + "\n",
                       encoding="utf-8")
        with pytest.raises(P.ServedArtifactNotLedgered) as exc:
            P.ledger_row_for("aaa", led)
        assert "chain contract" in str(exc.value)

    def test_a_SUPERSEDED_row_is_legal_but_must_say_so(self, tmp_path):
        led = self._chained(tmp_path, "aaa", "bbb")
        assert P.ledger_row_for("bbb", led)["is_ledger_tail"] is True
        assert P.ledger_row_for("aaa", led)["is_ledger_tail"] is False

    def test_an_ABSENT_ledger_is_refused_not_skipped(self, tmp_path):
        with pytest.raises(P.ServedArtifactNotLedgered):
            P.ledger_row_for("aaa", tmp_path / "nope.jsonl")

    def test_an_UNPARSEABLE_line_is_refused(self, tmp_path):
        p = tmp_path / "l.jsonl"
        p.write_text('{"artifact_content_sha256": "aaa"}\n{not json\n',
                     encoding="utf-8")
        with pytest.raises(P.ServedArtifactNotLedgered) as exc:
            P.ledger_row_for("aaa", p)
        assert "chain contract" in str(exc.value), (
            "'I could not check' must not read like 'it checks out'")

    def test_a_TAMPERED_CHAIN_is_refused(self, tmp_path):
        """[codex on orch#825] Matching a DECLARED sha is not verification: a
        forged-but-parseable ledger passed, and carrying prev_row_sha in the
        output made it look checked.

        SELF-CONTAINED — it builds its own chain with the model package's own
        appender. The first version read the LIVE ledger and SKIPPED when
        absent, so a clean CI checkout reported green without exercising this
        guard at all: exactly the regression the test exists to lock down.
        """
        led = self._chained(tmp_path, "aaa", "bbb")
        assert P.ledger_row_for("bbb", led)["is_ledger_tail"] is True

        rows = [json.loads(l) for l in led.read_text().splitlines() if l.strip()]
        rows[-1]["cutoff_date"] = "2099-01-01"   # edited after it was sealed
        bad = tmp_path / "bad.jsonl"
        bad.write_text("".join(json.dumps(r) + "\n" for r in rows),
                       encoding="utf-8")
        with pytest.raises(P.ServedArtifactNotLedgered) as exc:
            P.ledger_row_for("bbb", bad)
        assert "chain contract" in str(exc.value)

    def test_a_REMOVED_row_breaks_the_chain(self, tmp_path):
        """Append-only means a deletion must be detectable, not just an edit."""
        led = self._chained(tmp_path, "aaa", "bbb", "ccc")
        rows = [json.loads(l) for l in led.read_text().splitlines() if l.strip()]
        del rows[1]
        bad = tmp_path / "bad.jsonl"
        bad.write_text("".join(json.dumps(r) + "\n" for r in rows),
                       encoding="utf-8")
        with pytest.raises(P.ServedArtifactNotLedgered):
            P.ledger_row_for("ccc", bad)

    def test_a_TAMPERED_ARTIFACT_is_refused(self, tmp_path):
        """The artifact's content_sha256 is RECOMPUTED. Trusting the field it
        carries makes a corrupted artifact indistinguishable from the served
        one. Self-contained for the same reason as above."""
        params = json.loads(PAYLOAD.read_text())["provenance"]["params"]
        sealed = _sealed_artifact(tmp_path, params)
        assert P.served_params(sealed)["params"]["window"] == 252

        body = json.loads(sealed.read_text())
        body["n_scored"] = 999                   # body changed, sha left alone
        forged = tmp_path / "forged.json"
        forged.write_text(json.dumps(body), encoding="utf-8")
        with pytest.raises(P.ServedArtifactNotLedgered) as exc:
            P.served_params(forged)
        assert "does not hash to the identity it claims" in str(exc.value)

    def test_the_row_identity_is_recorded_including_its_CHAIN_position(self):
        if not P.LEDGER.is_file():
            pytest.skip("live ledger absent")
        rows = [json.loads(l) for l in P.LEDGER.read_text().splitlines() if l.strip()]
        row = P.ledger_row_for(rows[-1]["artifact_content_sha256"])
        assert row["is_ledger_tail"] is True
        assert row["row_sha"] == rows[-1]["row_sha"]
        assert row["chain_verified_by"].endswith("load_and_verify_ledger")


class TestTheInputsAreFingerprintedNotJustCounted:
    """A payload recording only summary counts could be reproduced from revised
    data, or by revised feature code under unchanged params, and report
    different numbers while looking identical [codex on orch#825]."""

    def test_the_scored_table_hash_PRESERVES_duplicates(self):
        """[codex on orch#825] A (ticker, date) DICT silently overwrites
        duplicate rows, so two scored tables differing only in duplicates
        hashed identically. A canonical ordered list does not."""
        one = [("AAA", "2026-01-02", 1.0)]
        assert P._digest_of_rows(one) != P._digest_of_rows(one * 2)
        assert P._digest_of_rows(one + [("BBB", "2026-01-02", 2.0)]) == \
            P._digest_of_rows([("BBB", "2026-01-02", 2.0)] + one)

    def test_the_orchestrator_revision_comes_from_THIS_repo_not_the_cwd(self):
        """`Path.cwd()` identifies whatever checkout the caller stood in."""
        assert (P.ORCH_REPO / "ops" / "ops_audit.py").is_file(), P.ORCH_REPO
        assert P.ORCH_REPO.name == "renquant-orchestrator"

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
    """The payload is COMMITTED, so this asserts rather than skips.

    It used to skip when the file was absent or lacked the fingerprint block —
    conditions that cannot hold in a checkout of this branch, so the skip could
    only ever have hidden a regression that deleted or downgraded the record.
    """
    assert PAYLOAD.is_file(), f"the committed payload is missing: {PAYLOAD}"
    d = json.loads(PAYLOAD.read_text())
    assert "input_read_digests" in d, (
        "the committed payload lost its input fingerprints — the numbers in "
        "the result document are no longer re-derivable")
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
