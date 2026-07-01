"""Tests for the renquant105 OBSERVE-ONLY shadow real-time model serving.

Fixtures + a fake scorer + an injected clock. Covers shadow-vs-batch pairing +
logging, censored-quote handling, idempotent append, and the no-order /
no-mutation collector invariants.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from renquant_orchestrator.realtime_data_plane import (
    QUOTE_MISSING,
    QUOTE_OK,
    QUOTE_STALE,
    IntradaySnapshotRow,
    MarketSnapshot,
    build_realtime_snapshot,
)
from renquant_orchestrator.shadow_realtime_serving import (
    RECORD_KIND,
    default_shadow_log_path,
    run_shadow_serving,
)

AS_OF = "2026-07-01T13:00:00-04:00"
SESSION = "2026-07-01"
FIXED_CLOCK = lambda: datetime(2026, 7, 1, 17, 0, 5, tzinfo=timezone.utc)


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


def _snapshot(rows):
    return MarketSnapshot(
        as_of=AS_OF, session_date=SESSION, rows=tuple(rows), metadata={"feed_source": "fake"}
    )


class FakeScorer:
    """Deterministic scorer: scores priceable (OK) rows from the intraday mid,
    omitting censored (stale/missing) names — a scorer must never impute a price.
    Records the snapshots it saw so the test can assert it is read-only."""

    name = "fake-scorer"

    def __init__(self) -> None:
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
        out_path=out,
        clock=FIXED_CLOCK,
    )

    assert summary["observe_only"] is True
    assert summary["n_rows"] == 2
    assert summary["n_written"] == 2
    assert summary["n_paired"] == 2
    assert scorer.calls == [snap]  # scorer saw exactly the snapshot, read-only

    rows = {r["ticker"]: r for r in _read_log(out)}
    aapl = rows["AAPL"]
    assert aapl["batch_score"] == 1.0
    assert aapl["shadow_score"] == 1.5
    assert aapl["batch_rank"] == 2  # 1.0 < 2.0 → rank 2
    assert aapl["shadow_rank"] == 2  # 1.5 < 3.0 → rank 2
    assert aapl["score_delta"] == 0.5
    assert aapl["rank_delta"] == 0
    assert aapl["quote_status"] == QUOTE_OK
    assert aapl["daily_feature_ref"] == "sig-v1"
    assert aapl["record_kind"] == RECORD_KIND
    assert aapl["observe_only"] is True
    assert aapl["logged_at"] == "2026-07-01T17:00:05+00:00"
    assert aapl["run_id"] == f"shadow-{AS_OF}"


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
        out_path=out,
        clock=FIXED_CLOCK,
    )
    assert summary["n_rows"] == 3
    assert summary["n_shadow"] == 1  # only the OK name is scored
    assert summary["n_paired"] == 1

    rows = {r["ticker"]: r for r in _read_log(out)}
    assert rows["MSFT"]["shadow_score"] is None
    assert rows["MSFT"]["batch_score"] == 2.0
    assert rows["MSFT"]["quote_status"] == QUOTE_STALE
    assert rows["MSFT"]["score_delta"] is None
    assert rows["MSFT"]["rank_delta"] is None
    assert rows["TSLA"]["shadow_score"] is None
    assert rows["TSLA"]["quote_status"] == QUOTE_MISSING


def test_idempotent_append(tmp_path: Path) -> None:
    out = tmp_path / "shadow.jsonl"
    snap = _snapshot([_row("AAPL", 150.0, QUOTE_OK)])
    kwargs = dict(snapshot=snap, scorer=FakeScorer(), batch_scores={"AAPL": 1.0}, out_path=out, clock=FIXED_CLOCK)

    first = run_shadow_serving(**kwargs)
    assert first["n_written"] == 1
    second = run_shadow_serving(**kwargs)
    assert second["n_written"] == 0  # same (as_of, ticker) → no duplicate

    assert len(_read_log(out)) == 1


def test_injected_clock_sets_logged_at(tmp_path: Path) -> None:
    out = tmp_path / "shadow.jsonl"
    stamp = datetime(2026, 7, 1, 18, 30, 0, tzinfo=timezone.utc)
    run_shadow_serving(
        snapshot=_snapshot([_row("AAPL", 150.0, QUOTE_OK)]),
        scorer=FakeScorer(),
        batch_scores={"AAPL": 1.0},
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
        out_path=out,
        clock=FIXED_CLOCK,
    )
    rows = {r["ticker"]: r for r in _read_log(out)}
    assert rows["TSLA"]["shadow_rank"] == 1
    assert rows["AAPL"]["shadow_rank"] == 2  # tie shares the rank
    assert rows["MSFT"]["shadow_rank"] == 2
    assert rows["TSLA"]["batch_rank"] == 1
    assert rows["AAPL"]["batch_rank"] == 2


def test_no_mutation_only_the_log_file_is_written(tmp_path: Path) -> None:
    data_root = tmp_path / "dataroot"
    snap = _snapshot([_row("AAPL", 150.0, QUOTE_OK)])
    summary = run_shadow_serving(
        snapshot=snap,
        scorer=FakeScorer(),
        batch_scores={"AAPL": 1.0},
        data_root=data_root,
        clock=FIXED_CLOCK,
    )
    expected = default_shadow_log_path(data_root)
    assert Path(summary["out"]) == expected
    pilot_dir = expected.parent
    # The collector writes exactly one file — nothing else in the pilot dir.
    assert [p.name for p in pilot_dir.iterdir()] == [expected.name]

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
        daily_features={"AAPL": "sig", "MSFT": "sig"},
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
        out_path=out,
        clock=FIXED_CLOCK,
    )
    assert summary["n_shadow"] == 1  # only fresh AAPL scored
    rows = {r["ticker"]: r for r in _read_log(out)}
    assert rows["MSFT"]["shadow_score"] is None
    assert rows["AAPL"]["shadow_score"] == 1.5
