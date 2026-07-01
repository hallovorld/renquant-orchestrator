"""Tests for the renquant105 OBSERVE-ONLY shadow real-time model serving.

Fixtures + a fake scorer + an injected clock. Covers shadow-vs-batch pairing +
logging, censored-quote handling, idempotent append, and the no-order /
no-mutation collector invariants.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from renquant_orchestrator.realtime_data_plane import (
    QUOTE_MISSING,
    QUOTE_OK,
    QUOTE_STALE,
    TICK_POLICY_VERSION,
    FeatureSnapshot,
    IntradaySnapshotRow,
    MarketSnapshot,
    build_realtime_snapshot,
)
from renquant_orchestrator.shadow_realtime_serving import (
    RECORD_KIND,
    ProvenanceError,
    RunProvenance,
    _ShadowLogWriter,
    default_shadow_log_path,
    run_shadow_serving,
)

AS_OF = "2026-07-01T13:00:00-04:00"
SESSION = "2026-07-01"
FIXED_CLOCK = lambda: datetime(2026, 7, 1, 17, 0, 5, tzinfo=timezone.utc)

FEATURE_DIGEST = "sha256:feat-abc"
BATCH_RUN_ID = "batch-2026-06-30-eod"
ARTIFACT_DIGEST = "sha256:artifact-xyz"

# Full provenance metadata a materialized-snapshot-backed MarketSnapshot carries.
PROV_META = {
    "feed_source": "fake",
    "tick_policy_version": TICK_POLICY_VERSION,
    "feature_cutoff": "2026-06-30",
    "feature_builder_version": "alpha158-v3",
    "feature_snapshot_digest": FEATURE_DIGEST,
}


def _row(ticker, mid, status, ref="sig-v1"):
    return IntradaySnapshotRow(
        as_of=AS_OF,
        ticker=ticker,
        intraday_mid=mid,
        quote_status=status,
        daily_feature_ref=ref,
        source_ts=AS_OF if mid is not None else None,
        age_sec=0.0 if mid is not None else None,
        source="fake" if mid is not None else None,
        session_date=SESSION,
    )


def _snapshot(rows, metadata=None):
    return MarketSnapshot(
        as_of=AS_OF,
        session_date=SESSION,
        rows=tuple(rows),
        metadata=dict(metadata if metadata is not None else PROV_META),
    )


class FakeScorer:
    """Deterministic scorer: scores priceable (OK) rows from the intraday mid,
    omitting censored (stale/missing) names — a scorer must never impute a price.
    Records the snapshots it saw so the test can assert it is read-only. Carries
    the class-A artifact fingerprint every logged row is bound to."""

    name = "fake-scorer"

    def __init__(self, *, artifact_digest=ARTIFACT_DIGEST, feature_digest=None) -> None:
        self.artifact_digest = artifact_digest
        if feature_digest is not None:
            self.feature_digest = feature_digest
        self.calls: list[MarketSnapshot] = []

    def score(self, snapshot: MarketSnapshot):
        self.calls.append(snapshot)
        return {
            row.ticker: round(row.intraday_mid / 100.0, 6)
            for row in snapshot.rows
            if row.quote_status == QUOTE_OK and row.intraday_mid is not None
        }


def _read_log(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_shadow_and_batch_scores_are_paired_and_logged(tmp_path: Path) -> None:
    out = tmp_path / "shadow.jsonl"
    scorer = FakeScorer()
    snap = _snapshot([_row("AAPL", 150.0, QUOTE_OK), _row("MSFT", 300.0, QUOTE_OK)])

    summary = run_shadow_serving(
        snapshot=snap,
        scorer=scorer,
        batch_scores={"AAPL": 1.0, "MSFT": 2.0},
        batch_run_id=BATCH_RUN_ID,
        out_path=out,
        clock=FIXED_CLOCK,
    )

    assert summary["observe_only"] is True
    assert summary["n_rows"] == 2
    assert summary["n_written"] == 2
    assert summary["n_paired"] == 2
    assert summary["coverage"] == 1.0
    assert summary["provenance"]["artifact_digest"] == ARTIFACT_DIGEST
    assert summary["provenance"]["batch_run_id"] == BATCH_RUN_ID
    assert summary["provenance"]["feature_snapshot_digest"] == FEATURE_DIGEST
    assert scorer.calls == [snap]  # scorer saw exactly the snapshot, read-only

    rows = {r["ticker"]: r for r in _read_log(out)}
    aapl = rows["AAPL"]
    assert aapl["batch_score"] == 1.0
    assert aapl["shadow_score"] == 1.5
    # Paired (comparable) ranks over the batch∩shadow intersection.
    assert aapl["in_paired_universe"] is True
    assert aapl["batch_rank_paired"] == 2  # 1.0 < 2.0 → rank 2
    assert aapl["shadow_rank_paired"] == 2  # 1.5 < 3.0 → rank 2
    assert aapl["rank_delta_paired"] == 0
    assert aapl["rank_comparability"] == "paired"
    # Full-universe ranks: diagnostic only (here identical, universe matches).
    assert aapl["batch_rank_full"] == 2
    assert aapl["shadow_rank_full"] == 2
    assert aapl["score_delta"] == 0.5
    assert aapl["quote_status"] == QUOTE_OK
    assert aapl["daily_feature_ref"] == "sig-v1"
    assert aapl["record_kind"] == RECORD_KIND
    assert aapl["observe_only"] is True
    assert aapl["logged_at"] == "2026-07-01T17:00:05+00:00"
    assert aapl["run_id"] == f"shadow-{AS_OF}"
    # Provenance stamped on every row.
    assert aapl["artifact_digest"] == ARTIFACT_DIGEST
    assert aapl["feature_cutoff"] == "2026-06-30"
    assert aapl["tick_policy_version"] == TICK_POLICY_VERSION
    assert aapl["batch_run_id"] == BATCH_RUN_ID


def test_censored_rows_logged_with_batch_but_no_shadow(tmp_path: Path) -> None:
    out = tmp_path / "shadow.jsonl"
    snap = _snapshot(
        [
            _row("AAPL", 150.0, QUOTE_OK),
            _row("MSFT", None, QUOTE_STALE),
            _row("TSLA", None, QUOTE_MISSING),
        ]
    )
    summary = run_shadow_serving(
        snapshot=snap,
        scorer=FakeScorer(),
        batch_scores={"AAPL": 1.0, "MSFT": 2.0, "TSLA": 3.0},
        batch_run_id=BATCH_RUN_ID,
        out_path=out,
        clock=FIXED_CLOCK,
    )
    assert summary["n_rows"] == 3
    assert summary["n_shadow"] == 1  # only the OK name is scored
    assert summary["n_paired"] == 1
    # Coverage / selection reported separately: 2 batch names dropped by censoring.
    assert summary["coverage"] == pytest.approx(1 / 3)
    assert summary["n_batch_only"] == 2
    assert set(summary["batch_only"]) == {"MSFT", "TSLA"}
    assert summary["n_shadow_only"] == 0

    rows = {r["ticker"]: r for r in _read_log(out)}
    assert rows["MSFT"]["shadow_score"] is None
    assert rows["MSFT"]["batch_score"] == 2.0
    assert rows["MSFT"]["quote_status"] == QUOTE_STALE
    assert rows["MSFT"]["score_delta"] is None
    assert rows["MSFT"]["in_paired_universe"] is False
    assert rows["MSFT"]["rank_delta_paired"] is None
    assert rows["MSFT"]["batch_rank_paired"] is None  # not in the comparable intersection
    assert rows["MSFT"]["batch_rank_full"] == 2  # diagnostic full-universe rank retained
    assert rows["MSFT"]["rank_comparability"] == "full-only"
    assert rows["TSLA"]["shadow_score"] is None
    assert rows["TSLA"]["quote_status"] == QUOTE_MISSING


def test_idempotent_append(tmp_path: Path) -> None:
    out = tmp_path / "shadow.jsonl"
    snap = _snapshot([_row("AAPL", 150.0, QUOTE_OK)])
    kwargs = dict(
        snapshot=snap,
        scorer=FakeScorer(),
        batch_scores={"AAPL": 1.0},
        batch_run_id=BATCH_RUN_ID,
        out_path=out,
        clock=FIXED_CLOCK,
    )

    first = run_shadow_serving(**kwargs)
    assert first["n_written"] == 1
    second = run_shadow_serving(**kwargs)
    assert second["n_written"] == 0  # same (as_of, ticker) → no duplicate

    assert len(_read_log(out)) == 1


def test_concurrent_writers_do_not_duplicate_under_lock(tmp_path: Path) -> None:
    """Two writers constructed BEFORE either appends (simulating concurrent
    collectors) still write the row once — the durable unique key is re-read
    INSIDE the single-writer lock, so read-then-append cannot race."""
    out = tmp_path / "shadow.jsonl"
    record = {
        "as_of": AS_OF,
        "ticker": "AAPL",
        "batch_score": 1.0,
        "shadow_score": 1.5,
    }
    writer_a = _ShadowLogWriter(out)
    writer_b = _ShadowLogWriter(out)  # constructed before A appends (empty view)

    assert writer_a.append([record]) == 1
    # B saw an empty file at construction, but re-reads keys under the lock.
    assert writer_b.append([record]) == 0
    assert len(_read_log(out)) == 1


def test_injected_clock_sets_logged_at(tmp_path: Path) -> None:
    out = tmp_path / "shadow.jsonl"
    stamp = datetime(2026, 7, 1, 18, 30, 0, tzinfo=timezone.utc)
    run_shadow_serving(
        snapshot=_snapshot([_row("AAPL", 150.0, QUOTE_OK)]),
        scorer=FakeScorer(),
        batch_scores={"AAPL": 1.0},
        batch_run_id=BATCH_RUN_ID,
        out_path=out,
        clock=lambda: stamp,
    )
    assert _read_log(out)[0]["logged_at"] == "2026-07-01T18:30:00+00:00"


def test_dense_rank_ties(tmp_path: Path) -> None:
    out = tmp_path / "shadow.jsonl"
    snap = _snapshot(
        [_row("AAPL", 100.0, QUOTE_OK), _row("MSFT", 100.0, QUOTE_OK), _row("TSLA", 300.0, QUOTE_OK)]
    )
    run_shadow_serving(
        snapshot=snap,
        scorer=FakeScorer(),
        batch_scores={"AAPL": 5.0, "MSFT": 5.0, "TSLA": 9.0},
        batch_run_id=BATCH_RUN_ID,
        out_path=out,
        clock=FIXED_CLOCK,
    )
    rows = {r["ticker"]: r for r in _read_log(out)}
    assert rows["TSLA"]["shadow_rank_paired"] == 1
    assert rows["AAPL"]["shadow_rank_paired"] == 2  # tie shares the rank
    assert rows["MSFT"]["shadow_rank_paired"] == 2
    assert rows["TSLA"]["batch_rank_paired"] == 1
    assert rows["AAPL"]["batch_rank_paired"] == 2


def test_no_mutation_only_the_log_file_is_written(tmp_path: Path) -> None:
    data_root = tmp_path / "dataroot"
    snap = _snapshot([_row("AAPL", 150.0, QUOTE_OK)])
    summary = run_shadow_serving(
        snapshot=snap,
        scorer=FakeScorer(),
        batch_scores={"AAPL": 1.0},
        batch_run_id=BATCH_RUN_ID,
        data_root=data_root,
        clock=FIXED_CLOCK,
    )
    expected = default_shadow_log_path(data_root)
    assert Path(summary["out"]) == expected
    pilot_dir = expected.parent
    # The collector writes the log file plus its single-writer lock — nothing else.
    assert sorted(p.name for p in pilot_dir.iterdir()) == sorted(
        [expected.name, expected.name + ".lock"]
    )

    text = expected.read_text(encoding="utf-8")
    for forbidden in ("place_order", "\"side\"", "\"pin\"", "gate_verdict", "promote"):
        assert forbidden not in text


def test_integration_build_snapshot_then_serve(tmp_path: Path) -> None:
    """End-to-end with the real assembler + a fake feed + fake scorer."""
    class FakeFeed:
        name = "fake-feed"

        def read_ticks(self):
            return [
                {"date": SESSION, "ticker": "AAPL", "mid": 150.0, "tick_time": "2026-07-01T12:59:57-04:00"},
                {"date": SESSION, "ticker": "MSFT", "mid": 300.0, "tick_time": "2026-07-01T12:58:00-04:00"},
            ]

    snap = build_realtime_snapshot(
        as_of=AS_OF,
        feature_snapshot=FeatureSnapshot.from_mapping(
            {
                "feature_cutoff": "2026-06-30",
                "feature_builder_version": "alpha158-v3",
                "features": {"AAPL": {"mom_12_1": 0.2}, "MSFT": {"mom_12_1": 0.1}},
            }
        ),
        feed_source=FakeFeed(),
        staleness_sec=15.0,
    )
    # MSFT tick is 120s old → stale/censored; AAPL is fresh.
    by = snap.by_ticker()
    assert by["AAPL"].quote_status == QUOTE_OK
    assert by["MSFT"].quote_status == QUOTE_STALE

    out = tmp_path / "shadow.jsonl"
    summary = run_shadow_serving(
        snapshot=snap,
        scorer=FakeScorer(),
        batch_scores={"AAPL": 1.0, "MSFT": 2.0},
        batch_run_id=BATCH_RUN_ID,
        out_path=out,
        clock=FIXED_CLOCK,
    )
    assert summary["n_shadow"] == 1  # only fresh AAPL scored
    rows = {r["ticker"]: r for r in _read_log(out)}
    assert rows["MSFT"]["shadow_score"] is None
    assert rows["AAPL"]["shadow_score"] == 1.5


# ---------------------------------------------------------------------------
# Provenance binding (Codex #221 blocking point 1 + 3) — reject missing/mismatched
# ---------------------------------------------------------------------------
def _feature_snapshot():
    return FeatureSnapshot.from_mapping(
        {
            "feature_cutoff": "2026-06-30",
            "feature_builder_version": "alpha158-v3",
            "features": {
                "AAPL": {"mom_12_1": 0.2},
                "MSFT": {"mom_12_1": 0.1},
                "TSLA": {"mom_12_1": 0.3},
            },
        }
    )


class _FeedAll:
    """All three watchlist names quote fresh (within the staleness bound), so the
    shadow scorer prices every one. Mids preserve the batch ordering
    (TSLA>MSFT>AAPL) so paired rank deltas are all zero."""

    name = "feed-all-fresh"

    def read_ticks(self):
        return [
            {"date": SESSION, "ticker": "AAPL", "mid": 150.0, "tick_time": "2026-07-01T12:59:55-04:00"},
            {"date": SESSION, "ticker": "MSFT", "mid": 250.0, "tick_time": "2026-07-01T12:59:55-04:00"},
            {"date": SESSION, "ticker": "TSLA", "mid": 350.0, "tick_time": "2026-07-01T12:59:55-04:00"},
        ]


class _FeedTslaStale:
    """AAPL/MSFT quote fresh; TSLA's last tick is 120s old → censored (stale), so
    the shadow scorer drops TSLA from its universe. Same mids as ``_FeedAll`` so
    the ONLY change is TSLA's censoring."""

    name = "feed-tsla-stale"

    def read_ticks(self):
        return [
            {"date": SESSION, "ticker": "AAPL", "mid": 150.0, "tick_time": "2026-07-01T12:59:55-04:00"},
            {"date": SESSION, "ticker": "MSFT", "mid": 250.0, "tick_time": "2026-07-01T12:59:55-04:00"},
            {"date": SESSION, "ticker": "TSLA", "mid": 350.0, "tick_time": "2026-07-01T12:58:00-04:00"},
        ]


def test_run_rejected_when_snapshot_has_no_feature_provenance(tmp_path: Path) -> None:
    """A snapshot built from a bare watchlist ref (no materialized feature
    snapshot) carries no feature digest → the run fails closed, nothing logged."""
    out = tmp_path / "shadow.jsonl"
    bare = _snapshot([_row("AAPL", 150.0, QUOTE_OK)], metadata={"feed_source": "fake"})
    with pytest.raises(ProvenanceError):
        run_shadow_serving(
            snapshot=bare,
            scorer=FakeScorer(),
            batch_scores={"AAPL": 1.0},
            batch_run_id=BATCH_RUN_ID,
            out_path=out,
            clock=FIXED_CLOCK,
        )
    assert not out.exists()  # fail-closed: no partial log


def test_run_rejected_when_batch_run_id_missing(tmp_path: Path) -> None:
    out = tmp_path / "shadow.jsonl"
    with pytest.raises(ProvenanceError):
        run_shadow_serving(
            snapshot=_snapshot([_row("AAPL", 150.0, QUOTE_OK)]),
            scorer=FakeScorer(),
            batch_scores={"AAPL": 1.0},
            batch_run_id="   ",
            out_path=out,
            clock=FIXED_CLOCK,
        )
    assert not out.exists()


def test_run_rejected_when_scorer_has_no_artifact_digest(tmp_path: Path) -> None:
    out = tmp_path / "shadow.jsonl"
    with pytest.raises(ProvenanceError):
        run_shadow_serving(
            snapshot=_snapshot([_row("AAPL", 150.0, QUOTE_OK)]),
            scorer=FakeScorer(artifact_digest=""),
            batch_scores={"AAPL": 1.0},
            batch_run_id=BATCH_RUN_ID,
            out_path=out,
            clock=FIXED_CLOCK,
        )
    assert not out.exists()


def test_run_rejected_on_feature_digest_mismatch(tmp_path: Path) -> None:
    """A scorer declaring a feature_digest different from the served snapshot's
    digest is a genuine model/feature mismatch → rejected, never silently mixed."""
    out = tmp_path / "shadow.jsonl"
    scorer = FakeScorer(feature_digest="sha256:built-against-a-different-snapshot")
    with pytest.raises(ProvenanceError):
        run_shadow_serving(
            snapshot=_snapshot([_row("AAPL", 150.0, QUOTE_OK)]),
            scorer=scorer,
            batch_scores={"AAPL": 1.0},
            batch_run_id=BATCH_RUN_ID,
            out_path=out,
            clock=FIXED_CLOCK,
        )
    assert not out.exists()


def test_matching_feature_digest_is_accepted(tmp_path: Path) -> None:
    out = tmp_path / "shadow.jsonl"
    scorer = FakeScorer(feature_digest=FEATURE_DIGEST)  # matches PROV_META
    summary = run_shadow_serving(
        snapshot=_snapshot([_row("AAPL", 150.0, QUOTE_OK)]),
        scorer=scorer,
        batch_scores={"AAPL": 1.0},
        batch_run_id=BATCH_RUN_ID,
        out_path=out,
        clock=FIXED_CLOCK,
    )
    assert summary["n_written"] == 1


def test_provenance_validate_lists_all_missing_fields() -> None:
    with pytest.raises(ProvenanceError) as exc:
        RunProvenance(
            artifact_digest="",
            feature_builder_version="v1",
            feature_cutoff="",
            feature_snapshot_digest="d",
            tick_policy_version="1",
            batch_run_id="",
        ).validate()
    msg = str(exc.value)
    assert "artifact_digest" in msg and "feature_cutoff" in msg and "batch_run_id" in msg


def test_paired_ranks_stable_under_censoring_but_full_ranks_shift(tmp_path: Path) -> None:
    """The PRIMARY endpoint (paired rank delta) must not move when quote
    censoring drops a name from the shadow universe; only the NON-comparable
    full-universe shadow rank shifts. This is exactly the confound Codex flagged."""
    out_all = tmp_path / "all.jsonl"
    out_censored = tmp_path / "censored.jsonl"
    batch = {"AAPL": 1.0, "MSFT": 2.0, "TSLA": 3.0}

    # Case 1: all three priceable.
    snap_all = build_realtime_snapshot(
        as_of=AS_OF,
        feature_snapshot=_feature_snapshot(),
        feed_source=_FeedAll(),
        staleness_sec=15.0,
    )
    # Case 2: TSLA quote censored (stale) → not scored by the shadow scorer.
    snap_censored = build_realtime_snapshot(
        as_of=AS_OF,
        feature_snapshot=_feature_snapshot(),
        feed_source=_FeedTslaStale(),
        staleness_sec=15.0,
    )

    run_shadow_serving(
        snapshot=snap_all, scorer=FakeScorer(), batch_scores=batch,
        batch_run_id=BATCH_RUN_ID, out_path=out_all, clock=FIXED_CLOCK,
    )
    run_shadow_serving(
        snapshot=snap_censored, scorer=FakeScorer(), batch_scores=batch,
        batch_run_id=BATCH_RUN_ID, out_path=out_censored, clock=FIXED_CLOCK,
    )
    a_all = {r["ticker"]: r for r in _read_log(out_all)}["AAPL"]
    a_cens = {r["ticker"]: r for r in _read_log(out_censored)}["AAPL"]

    # AAPL's PAIRED rank delta is identical across the two universes.
    assert a_all["rank_delta_paired"] == a_cens["rank_delta_paired"]
    # But its NON-comparable full shadow rank changed because TSLA dropped out.
    assert a_all["shadow_rank_full"] != a_cens["shadow_rank_full"]
