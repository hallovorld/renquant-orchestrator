"""Canonical G4 shadow job + immutable evidence store (step 2, model#61 v4).

Write-side proofs: session-window resolution owns close(T)/open(T+1)
from the exchange calendar — with the EARLY-CLOSE adversarial case the
step-1 approval requires (reviewer requirement (b)); the L1 equal-weight
combination is frozen deterministic arithmetic; records satisfy the
step-1 contract (``renquant_pipeline.decision_schedule``, pipeline#209)
with identities minted via ``job_identity``; persistence is append-only,
digest-named, byte-identical on re-run, side-by-side on divergence, and
refuses every overwrite. SHADOW ONLY throughout — no broker anywhere.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from renquant_common.market_calendar import SessionBounds
from renquant_pipeline.decision_schedule import (
    ARM_CHAMPION,
    ARM_L1,
    FAILURE_KIND_VENUE_OUTAGE,
    REASON_WATERMARK_AFTER_CLOSE,
    job_identity,
    validate_arm_record,
    validate_session_records,
)

from renquant_orchestrator.g4_admission import recompute_watermark_from_store
from renquant_orchestrator.g4_shadow_job import (
    EXECUTION_MODE_SHADOW,
    G4ArmSpec,
    G4EvidenceIntegrityError,
    G4EvidenceStore,
    build_arm_record,
    build_failure_record,
    decision_digest_of,
    equal_weight_scores,
    input_snapshot_bytes,
    max_event_time_from_bytes,
    resolve_session_window,
    run_g4_shadow_session,
)

ET = ZoneInfo("America/New_York")
UTC = dt.timezone.utc

T = "2026-07-17"  # Friday, normal session
T_NEXT = "2026-07-20"  # Monday
EARLY = "2026-11-27"  # day after Thanksgiving — 13:00 ET early close
EARLY_NEXT = "2026-11-30"

CAL_ID = "NYSE/pmc-test"
PRICE_ID = "alpaca-iex/v1-test"


def _sha(seed: str) -> str:
    return "sha256:" + hashlib.sha256(seed.encode()).hexdigest()


class FakeCalendar:
    """Deterministic SessionCalendar covering the test sessions, including
    the early-close half day (13:00 ET close)."""

    name = "NYSE"

    _SESSIONS = {
        dt.date(2026, 7, 16): (dt.time(9, 30), dt.time(16, 0)),
        dt.date(2026, 7, 17): (dt.time(9, 30), dt.time(16, 0)),
        dt.date(2026, 7, 20): (dt.time(9, 30), dt.time(16, 0)),
        dt.date(2026, 11, 27): (dt.time(9, 30), dt.time(13, 0)),  # half day
        dt.date(2026, 11, 30): (dt.time(9, 30), dt.time(16, 0)),
    }

    def session_bounds(self, day: dt.date) -> "SessionBounds | None":
        times = self._SESSIONS.get(day)
        if times is None:
            return None
        return SessionBounds(
            open=dt.datetime.combine(day, times[0], tzinfo=ET),
            close=dt.datetime.combine(day, times[1], tzinfo=ET),
        )


def _window(session: str = T):
    return resolve_session_window(session, calendar=FakeCalendar())


def _inputs():
    """Shared information set for both arms; MUST include 'universe'."""
    return {
        "universe": {
            "event_times": [dt.datetime(2026, 7, 17, 13, 0, tzinfo=UTC)],
            "payload": {"tickers": ["AAPL", "MSFT"]},
        },
        "prices_eod": {
            "event_times": [
                dt.datetime(2026, 7, 17, 19, 0, tzinfo=UTC),
                dt.datetime(2026, 7, 17, 19, 55, tzinfo=UTC),  # 15:55 ET
            ],
            "payload": {"AAPL": 231.1, "MSFT": 508.4},
        },
    }


def _arms():
    l1_scores = equal_weight_scores(
        {
            "xgb": {"AAPL": 0.10, "MSFT": -0.20},
            "patchtst": {"AAPL": 0.30, "MSFT": -0.40},
        }
    )
    return [
        G4ArmSpec(
            arm=ARM_L1,
            artifact_digests={"xgb": _sha("xgb-a"), "patchtst": _sha("ptst-a")},
            config_digest=_sha("cfg"),
            scores=l1_scores,
            orders=[{"ticker": "AAPL", "side": "buy", "weight": 0.5}],
        ),
        G4ArmSpec(
            arm=ARM_CHAMPION,
            artifact_digests={"champion": _sha("champ-a")},
            config_digest=_sha("cfg"),
            scores={"AAPL": 0.2, "MSFT": -0.1},
            orders=[],  # declared no-trade — admissible
        ),
    ]


PRODUCED_AT = dt.datetime(2026, 7, 17, 21, 0, tzinfo=UTC)  # 17:00 ET, in-window


def _run(store: G4EvidenceStore, *, produced_at=PRODUCED_AT, arms=None, session=T):
    return run_g4_shadow_session(
        store,
        decision_session=session,
        session_window=_window(session),
        inputs=_inputs(),
        arms=arms if arms is not None else _arms(),
        calendar_id=CAL_ID,
        price_source_id=PRICE_ID,
        produced_at=produced_at,
    )


# ---------------------------------------------------------------------------
# Session-window resolution (orchestrator-owned; requirement (b))
# ---------------------------------------------------------------------------

class TestResolveSessionWindow:
    def test_normal_day_owns_close_and_next_open(self) -> None:
        window = _window(T)
        assert window.close == dt.datetime(2026, 7, 17, 16, 0, tzinfo=ET)
        assert window.next_open == dt.datetime(2026, 7, 20, 9, 30, tzinfo=ET)
        assert window.next_open_session == T_NEXT  # weekend skipped

    def test_early_close_day_resolves_the_real_close(self) -> None:
        """(b) adversarial: the half day's official close is 13:00 ET —
        a hardcoded 16:00 assumption would over-admit by three hours."""
        window = _window(EARLY)
        assert window.close == dt.datetime(2026, 11, 27, 13, 0, tzinfo=ET)
        assert window.close.time() != dt.time(16, 0)
        assert window.next_open_session == EARLY_NEXT

    def test_early_close_rejects_normal_day_watermark(self, tmp_path: Path) -> None:
        """(b) adversarial, end to end: a 14:30 ET watermark — fine on a
        normal 16:00-close day — must be REJECTED on the early-close day,
        and the canonical job fails closed rather than persisting it as
        admissible."""
        store = G4EvidenceStore(tmp_path / "g4")
        early_inputs = {
            "universe": {
                "event_times": [dt.datetime(2026, 11, 27, 14, 30, tzinfo=ET)],
                "payload": {"tickers": ["AAPL", "MSFT"]},
            },
        }
        with pytest.raises(G4EvidenceIntegrityError, match=REASON_WATERMARK_AFTER_CLOSE):
            run_g4_shadow_session(
                store,
                decision_session=EARLY,
                session_window=_window(EARLY),
                inputs=early_inputs,
                arms=_arms(),
                calendar_id=CAL_ID,
                price_source_id=PRICE_ID,
                produced_at=dt.datetime(2026, 11, 27, 14, 45, tzinfo=ET),
            )

    def test_same_watermark_admits_on_a_normal_day(self, tmp_path: Path) -> None:
        """Control for the early-close case: the identical intra-afternoon
        watermark (14:30 ET) is admissible when the close really is 16:00."""
        store = G4EvidenceStore(tmp_path / "g4")
        inputs = {
            "universe": {
                "event_times": [dt.datetime(2026, 7, 17, 14, 30, tzinfo=ET)],
                "payload": {"tickers": ["AAPL", "MSFT"]},
            },
        }
        results = run_g4_shadow_session(
            store,
            decision_session=T,
            session_window=_window(T),
            inputs=inputs,
            arms=_arms(),
            calendar_id=CAL_ID,
            price_source_id=PRICE_ID,
            produced_at=PRODUCED_AT,
        )
        assert set(results["records"]) == {ARM_L1, ARM_CHAMPION}

    def test_non_session_day_raises(self) -> None:
        with pytest.raises(ValueError, match="not a"):
            _window("2026-07-18")  # Saturday

    def test_no_next_session_in_window_raises(self) -> None:
        cal = FakeCalendar()
        with pytest.raises(ValueError, match="no .* session found"):
            resolve_session_window("2026-11-30", calendar=cal, max_lookahead_days=15)

    def test_real_nyse_early_close_thanksgiving(self) -> None:
        """(b) against the REAL calendar: 2026-11-27 (day after
        Thanksgiving) closes 13:00 ET, and the next session is Monday."""
        pytest.importorskip("pandas_market_calendars")
        window = resolve_session_window(EARLY)
        assert window.close.astimezone(ET).time() == dt.time(13, 0)
        assert window.next_open_session == EARLY_NEXT
        assert window.next_open.astimezone(ET).time() == dt.time(9, 30)

    def test_real_nyse_normal_day(self) -> None:
        pytest.importorskip("pandas_market_calendars")
        window = resolve_session_window(T)
        assert window.close.astimezone(ET).time() == dt.time(16, 0)
        assert window.next_open_session == T_NEXT


# ---------------------------------------------------------------------------
# L1 equal-weight combination (v4 §3)
# ---------------------------------------------------------------------------

class TestEqualWeightScores:
    def test_arithmetic_mean_sorted_keys(self) -> None:
        combined = equal_weight_scores(
            {"a": {"MSFT": 1.0, "AAPL": 0.5}, "b": {"AAPL": 1.5, "MSFT": -2.0}}
        )
        assert combined == {"AAPL": 1.0, "MSFT": -0.5}
        assert list(combined) == ["AAPL", "MSFT"]

    def test_single_expert_identity(self) -> None:
        assert equal_weight_scores({"a": {"X": 0.25}}) == {"X": 0.25}

    def test_mismatched_universes_fail_closed(self) -> None:
        with pytest.raises(ValueError, match="identical ticker set"):
            equal_weight_scores({"a": {"AAPL": 1.0}, "b": {"MSFT": 1.0}})

    def test_no_experts_fail_closed(self) -> None:
        with pytest.raises(ValueError, match="at least one expert"):
            equal_weight_scores({})

    def test_non_finite_fails_closed(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            equal_weight_scores({"a": {"AAPL": float("nan")}})


# ---------------------------------------------------------------------------
# The canonical shadow job — record content + contract conformance
# ---------------------------------------------------------------------------

class TestCanonicalJob:
    def test_records_satisfy_step1_contract(self, tmp_path: Path) -> None:
        """Both arms' records pass validate_arm_record AND
        validate_session_records with the byte-level watermark hook —
        the machinery consumes the pipeline#209 contract end to end."""
        store = G4EvidenceStore(tmp_path / "g4")
        results = _run(store)
        hook = recompute_watermark_from_store(store)
        window = _window()
        for record in results["records"].values():
            verdict = validate_arm_record(
                record,
                session_window=window,
                recompute_max_event_time=hook,
                expected_calendar_id=CAL_ID,
                expected_price_source_id=PRICE_ID,
            )
            assert verdict.ok, verdict.detail
            assert verdict.evidence_flags == ()  # timestamp in-window
        session_verdict = validate_session_records(
            list(results["records"].values()),
            session_window=window,
            recompute_max_event_time=hook,
            expected_calendar_id=CAL_ID,
            expected_price_source_id=PRICE_ID,
        )
        assert session_verdict.ok, session_verdict.detail

    def test_record_fields(self, tmp_path: Path) -> None:
        store = G4EvidenceStore(tmp_path / "g4")
        record = _run(store)["records"][ARM_L1]
        # v4 §2: immutable session, computed watermark, universe manifested,
        # frozen identifiers, next-open order set, deterministic identity.
        assert record["decision_session"] == T
        assert record["execution_mode"] == EXECUTION_MODE_SHADOW
        assert set(record["input_manifest"]) == {"universe", "prices_eod"}
        for entry in record["input_manifest"].values():
            assert entry["digest"].startswith("sha256:")
        assert (
            dt.datetime.fromisoformat(record["declared_input_watermark"])
            == dt.datetime(2026, 7, 17, 19, 55, tzinfo=UTC)
        )
        assert record["calendar_id"] == CAL_ID
        assert record["price_source_id"] == PRICE_ID
        assert record["orders_scheduled_for"] == T_NEXT
        assert record["job_id"] == job_identity(
            arm=ARM_L1,
            decision_session=T,
            artifact_digests=record["artifact_digests"],
            config_digest=record["config_digest"],
        )
        assert record["decision_digest"] == decision_digest_of(record)

    def test_universe_input_required(self, tmp_path: Path) -> None:
        store = G4EvidenceStore(tmp_path / "g4")
        inputs = _inputs()
        del inputs["universe"]
        with pytest.raises(ValueError, match="universe"):
            run_g4_shadow_session(
                store,
                decision_session=T,
                session_window=_window(),
                inputs=inputs,
                arms=_arms(),
                calendar_id=CAL_ID,
                price_source_id=PRICE_ID,
                produced_at=PRODUCED_AT,
            )

    def test_only_the_frozen_pair_runs(self, tmp_path: Path) -> None:
        store = G4EvidenceStore(tmp_path / "g4")
        with pytest.raises(ValueError, match="frozen registered pair"):
            _run(store, arms=[_arms()[0]])  # l1 only
        rogue = G4ArmSpec(
            arm="l2",
            artifact_digests={"x": _sha("x")},
            config_digest=_sha("cfg"),
            scores={"AAPL": 0.1},
        )
        with pytest.raises(ValueError, match="frozen registered pair"):
            _run(store, arms=[_arms()[0], rogue])

    def test_no_broker_surface(self) -> None:
        """SHADOW ONLY: the job module must not touch execution/broker
        code — the declared order set is an intent record."""
        import renquant_orchestrator.g4_shadow_job as mod

        src = Path(mod.__file__).read_text(encoding="utf-8")
        for needle in ("renquant_execution", "alpaca", "ib_insync", "Broker"):
            assert needle not in src, f"shadow job must not reference {needle!r}"


# ---------------------------------------------------------------------------
# Immutable persistence: byte-identical re-run / retry / divergence / overwrite
# ---------------------------------------------------------------------------

class TestImmutablePersistence:
    def test_rerun_with_identical_inputs_is_byte_identical(self, tmp_path: Path) -> None:
        store = G4EvidenceStore(tmp_path / "g4")
        first = _run(store)
        bytes_before = {
            arm: Path(path).read_bytes() for arm, path in first["paths"].items()
        }
        second = _run(store)  # identical inputs incl. injected timestamp
        assert second["outcomes"] == {ARM_L1: "identical", ARM_CHAMPION: "identical"}
        assert first["paths"] == second["paths"]
        for arm, path in second["paths"].items():
            assert Path(path).read_bytes() == bytes_before[arm]
        # exactly ONE record file per arm — the retry was a no-op
        files = [p.name for p, _ in store.load_session_records(T)]
        assert len(files) == 2

    def test_timestamp_only_retry_keeps_first_write(self, tmp_path: Path) -> None:
        """A wall-clock retry (same decision, later run_bundle_timestamp)
        is admissible: FIRST write wins, nothing rewritten, both attempts
        logged as evidence."""
        store = G4EvidenceStore(tmp_path / "g4")
        first = _run(store)
        original = Path(first["paths"][ARM_L1]).read_bytes()
        retry = _run(store, produced_at=PRODUCED_AT + dt.timedelta(minutes=7))
        assert retry["outcomes"] == {ARM_L1: "retry", ARM_CHAMPION: "retry"}
        assert Path(first["paths"][ARM_L1]).read_bytes() == original
        attempts = [
            json.loads(line)
            for line in store.attempts_path(T).read_text().splitlines()
        ]
        assert [a["outcome"] for a in attempts].count("retry") == 2

    def test_divergent_duplicate_lands_side_by_side(self, tmp_path: Path) -> None:
        """Same job identity, different decision content: the divergent
        duplicate gets its own digest-name NEXT TO the original — never
        overwritten, never resolved by latest-commit (v4 §2)."""
        store = G4EvidenceStore(tmp_path / "g4")
        _run(store)
        diverged = [
            _arms()[0],
            G4ArmSpec(
                arm=ARM_CHAMPION,
                artifact_digests={"champion": _sha("champ-a")},
                config_digest=_sha("cfg"),
                scores={"AAPL": 0.9, "MSFT": 0.9},  # different decision
                orders=[{"ticker": "AAPL", "side": "buy", "weight": 1.0}],
            ),
        ]
        _run(store, arms=diverged)
        records = store.load_session_records(T)
        champion_files = [p for p, r in records if r.get("arm") == ARM_CHAMPION]
        assert len(champion_files) == 2  # side by side
        job_ids = {r["job_id"] for _, r in records if r.get("arm") == ARM_CHAMPION}
        digests = {r["decision_digest"] for _, r in records if r.get("arm") == ARM_CHAMPION}
        assert len(job_ids) == 1 and len(digests) == 2

    def test_overwrite_attempt_fails_and_preserves_bytes(self, tmp_path: Path) -> None:
        store = G4EvidenceStore(tmp_path / "g4")
        results = _run(store)
        path = Path(results["paths"][ARM_L1])
        original = path.read_bytes()
        with pytest.raises(G4EvidenceIntegrityError, match="refusing to overwrite"):
            store._write_once(path, b'{"tampered": true}', volatile=())
        assert path.read_bytes() == original
        assert (os.stat(path).st_mode & 0o222) == 0  # read-only on disk

    def test_precreated_conflicting_path_is_never_clobbered(self, tmp_path: Path) -> None:
        """Adversarial: junk already sits at the record's exact path —
        the write refuses and the junk survives for forensics."""
        store = G4EvidenceStore(tmp_path / "g4")
        record = build_arm_record(
            _arms()[0],
            decision_session=T,
            session_window=_window(),
            input_manifest={
                "universe": {
                    "digest": store.store_input(
                        input_snapshot_bytes(
                            "universe",
                            event_times=[dt.datetime(2026, 7, 17, 13, 0, tzinfo=UTC)],
                            payload={"tickers": ["AAPL"]},
                        )
                    ),
                    "max_event_time": "2026-07-17T13:00:00+00:00",
                }
            },
            calendar_id=CAL_ID,
            price_source_id=PRICE_ID,
            produced_at=PRODUCED_AT,
        )
        name = (
            f"{ARM_L1}-{record['job_id'][7:19]}-{record['decision_digest'][7:19]}.json"
        )
        target = store.records_dir(T) / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b'{"junk": 1}')
        with pytest.raises(G4EvidenceIntegrityError, match="refusing to overwrite"):
            store.write_record(record)
        assert target.read_bytes() == b'{"junk": 1}'

    def test_write_record_refuses_stale_decision_digest(self, tmp_path: Path) -> None:
        """Observation 2 (step-1 approval): the digest is recomputed over
        the FULL decision content, so mutated scores riding an old digest
        can never enter the store."""
        store = G4EvidenceStore(tmp_path / "g4")
        record = dict(_run(store)["records"][ARM_L1])
        record["scores"] = {"AAPL": 99.0, "MSFT": 99.0}  # digest now stale
        with pytest.raises(G4EvidenceIntegrityError, match="decision_digest"):
            store.write_record(record)

    def test_write_record_refuses_wrong_job_identity(self, tmp_path: Path) -> None:
        store = G4EvidenceStore(tmp_path / "g4")
        record = dict(_run(store)["records"][ARM_L1])
        record["config_digest"] = _sha("other-config")
        record["decision_digest"] = decision_digest_of(record)
        with pytest.raises(G4EvidenceIntegrityError, match="job_id"):
            store.write_record(record)

    def test_write_record_refuses_non_shadow_mode(self, tmp_path: Path) -> None:
        store = G4EvidenceStore(tmp_path / "g4")
        record = dict(_run(store)["records"][ARM_L1])
        record["execution_mode"] = "live"
        with pytest.raises(G4EvidenceIntegrityError, match="SHADOW"):
            store.write_record(record)

    def test_failure_records_append_side_by_side(self, tmp_path: Path) -> None:
        store = G4EvidenceStore(tmp_path / "g4")
        ts = dt.datetime(2026, 7, 17, 20, 30, tzinfo=UTC)
        for detail in ("first attempt", "second attempt"):
            record = build_failure_record(
                arm=ARM_L1,
                decision_session=T,
                kind=FAILURE_KIND_VENUE_OUTAGE,
                detail=detail,
                outage_evidence=[
                    {
                        "kind": "venue_halt",
                        "ref": "https://status.example.test/incident/1",
                        "observed_at": "2026-07-17T18:41:00+00:00",
                    }
                ],
                recorded_at=ts,
            )
            store.write_failure_record(record)
        failures = [
            r for _, r in store.load_session_records(T) if "failure" in r
        ]
        assert len(failures) == 2


# ---------------------------------------------------------------------------
# Input snapshots + byte-level watermark recomputation seams
# ---------------------------------------------------------------------------

class TestInputSnapshots:
    def test_roundtrip_max_event_time(self) -> None:
        data = input_snapshot_bytes(
            "prices",
            event_times=[
                dt.datetime(2026, 7, 17, 19, 0, tzinfo=UTC),
                dt.datetime(2026, 7, 17, 15, 55, tzinfo=ET),  # 19:55 UTC
            ],
            payload={"AAPL": 1.0},
        )
        assert max_event_time_from_bytes(data) == dt.datetime(
            2026, 7, 17, 19, 55, tzinfo=UTC
        )

    def test_naive_event_time_refused_at_build(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            input_snapshot_bytes(
                "prices",
                event_times=[dt.datetime(2026, 7, 17, 19, 0)],
                payload=None,
            )

    @pytest.mark.parametrize(
        "data",
        [
            b"not json",
            b'{"kind": "other"}',
            b'{"kind": "g4_input_snapshot", "event_times": []}',
            b'{"kind": "g4_input_snapshot", "event_times": ["2026-07-17T19:00:00"]}',
        ],
    )
    def test_recompute_from_bytes_fails_closed(self, data: bytes) -> None:
        assert max_event_time_from_bytes(data) is None

    def test_read_input_verifies_hash(self, tmp_path: Path) -> None:
        store = G4EvidenceStore(tmp_path / "g4")
        data = input_snapshot_bytes(
            "universe",
            event_times=[dt.datetime(2026, 7, 17, 13, 0, tzinfo=UTC)],
            payload={"tickers": ["AAPL"]},
        )
        digest = store.store_input(data)
        assert store.read_input(digest) == data
        # a digest whose file holds OTHER bytes -> None (fail-closed)
        bogus = "sha256:" + "0" * 64
        (store.inputs_dir / f"{'0' * 64}.json").write_bytes(b"{}")
        assert store.read_input(bogus) is None
        assert store.read_input("not-a-digest") is None
        assert store.read_input(None) is None
