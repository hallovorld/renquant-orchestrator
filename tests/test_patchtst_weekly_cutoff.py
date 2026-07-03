"""Tests for ``patchtst_weekly_cutoff`` — S12 B3 corpus-frontier cutoff derivation.

Pins:
- fresh corpus ⇒ cutoff advances to the Monday-quantized labeled frontier
- stale corpus (frozen refresh) ⇒ fail-closed with a STALE message
- manifest-only (corpus missing) ⇒ refuses; the manifest can never source a cutoff
- NaN-label tail rows don't inflate the frontier
- static-manifest lower bound, future-date, and empty-corpus fail-closed paths
- CLI: stdout carries ONLY the derived cutoff; failures exit 1 via stderr
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pandas as pd
import pytest

from renquant_orchestrator import patchtst_weekly_cutoff as wc

TODAY = dt.date(2026, 7, 2)  # fixed 'today' — all derivations pass --as-of/today


def _corpus(path: Path, max_labeled: dt.date, *, periods: int = 40,
            label: str = "fwd_60d_excess", nan_tail: int = 0) -> Path:
    """A corpus-shaped parquet: business-day ``date`` ending at ``max_labeled``
    with non-null labels, plus optionally ``nan_tail`` newer unlabeled rows."""
    dates = pd.bdate_range(end=pd.Timestamp(max_labeled), periods=periods)
    frame = pd.DataFrame({"date": dates, "ticker": "AAA", label: 0.01})
    if nan_tail:
        tail_dates = pd.bdate_range(
            start=pd.Timestamp(max_labeled) + pd.offsets.BDay(1), periods=nan_tail)
        frame = pd.concat([frame, pd.DataFrame(
            {"date": tail_dates, "ticker": "AAA", label: float("nan")})],
            ignore_index=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)
    return path


def _manifest(path: Path, cutoffs: list[str]) -> Path:
    path.write_text(json.dumps({"retrains": [{"cutoff_date": c} for c in cutoffs]}))
    return path


# Fresh frontier: TODAY − 60 BDays = the achievable labeled frontier.
FRESH_FRONTIER = (pd.Timestamp(TODAY) - pd.offsets.BDay(60)).date()  # 2026-04-09 (Thu)
STATIC_TAIL = ["2026-02-16", "2026-03-09"]  # the frozen static-manifest tail


def test_fresh_corpus_advances_cutoff_past_static_tail(tmp_path: Path) -> None:
    corpus = _corpus(tmp_path / "corpus.parquet", FRESH_FRONTIER)
    manifest = _manifest(tmp_path / "static.json", STATIC_TAIL)
    cutoff = wc.derive_weekly_cutoff(
        corpus, lower_bound_manifest=manifest, today=TODAY)
    expected = wc.quantize_to_weekly_grid(FRESH_FRONTIER)
    assert cutoff == expected.isoformat()
    assert cutoff > "2026-03-09"  # advanced past the frozen static tail
    assert dt.date.fromisoformat(cutoff).weekday() == 0  # on the Monday WF grid


def test_stale_corpus_fails_closed(tmp_path: Path) -> None:
    # The real frozen corpus: labeled frontier 2026-02-10 (bar frontier
    # 2026-05-07, ~56d old at 2026-07-02) — must refuse, never train.
    corpus = _corpus(tmp_path / "corpus.parquet", dt.date(2026, 2, 10))
    with pytest.raises(wc.CutoffDerivationError, match="STALE"):
        wc.derive_weekly_cutoff(corpus, today=TODAY)


def test_manifest_only_refuses_with_message(tmp_path: Path) -> None:
    # No corpus at all — a static manifest alone must NEVER produce a cutoff.
    manifest = _manifest(tmp_path / "static.json", STATIC_TAIL)
    with pytest.raises(wc.CutoffDerivationError, match="NEVER source the cutoff"):
        wc.derive_weekly_cutoff(
            tmp_path / "missing.parquet",
            lower_bound_manifest=manifest, today=TODAY)


def test_nan_label_tail_does_not_inflate_frontier(tmp_path: Path) -> None:
    corpus = _corpus(tmp_path / "corpus.parquet", FRESH_FRONTIER, nan_tail=30)
    assert wc.corpus_labeled_frontier(corpus) == FRESH_FRONTIER
    cutoff = wc.derive_weekly_cutoff(corpus, today=TODAY)
    assert cutoff == wc.quantize_to_weekly_grid(FRESH_FRONTIER).isoformat()


def test_regressed_frontier_below_manifest_tail_fails_closed(tmp_path: Path) -> None:
    frontier = dt.date(2026, 3, 2)  # labeled but BEHIND the 2026-03-09 tail
    corpus = _corpus(tmp_path / "corpus.parquet", frontier)
    manifest = _manifest(tmp_path / "static.json", STATIC_TAIL)
    with pytest.raises(wc.CutoffDerivationError, match="regressed behind"):
        wc.derive_weekly_cutoff(
            corpus, lower_bound_manifest=manifest,
            max_staleness_days=365, today=TODAY)


def test_future_dated_corpus_fails_closed(tmp_path: Path) -> None:
    corpus = _corpus(tmp_path / "corpus.parquet", TODAY + dt.timedelta(days=30))
    with pytest.raises(wc.CutoffDerivationError, match="future"):
        wc.derive_weekly_cutoff(corpus, today=TODAY)


def test_all_nan_labels_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "corpus.parquet"
    dates = pd.bdate_range(end=pd.Timestamp(FRESH_FRONTIER), periods=5)
    pd.DataFrame({"date": dates, "fwd_60d_excess": float("nan")}).to_parquet(
        path, index=False)
    with pytest.raises(wc.CutoffDerivationError, match="no labeled rows"):
        wc.derive_weekly_cutoff(path, today=TODAY)


def test_missing_lower_bound_manifest_fails_closed(tmp_path: Path) -> None:
    corpus = _corpus(tmp_path / "corpus.parquet", FRESH_FRONTIER)
    with pytest.raises(wc.CutoffDerivationError, match="lower-bound manifest missing"):
        wc.derive_weekly_cutoff(
            corpus, lower_bound_manifest=tmp_path / "nope.json", today=TODAY)


def test_monday_frontier_is_its_own_cutoff(tmp_path: Path) -> None:
    monday = dt.date(2026, 6, 8)
    assert monday.weekday() == 0
    corpus = _corpus(tmp_path / "corpus.parquet", monday)
    cutoff = wc.derive_weekly_cutoff(corpus, max_staleness_days=365, today=TODAY)
    assert cutoff == "2026-06-08"


def test_quantize_grid_pure() -> None:
    assert wc.quantize_to_weekly_grid(dt.date(2026, 4, 9)) == dt.date(2026, 4, 6)
    assert wc.quantize_to_weekly_grid(dt.date(2026, 4, 6)) == dt.date(2026, 4, 6)
    assert wc.quantize_to_weekly_grid(dt.date(2026, 4, 12)) == dt.date(2026, 4, 6)


def test_lookahead_follows_label_horizon(tmp_path: Path) -> None:
    # fwd_20d label → only 20 BDays of structural lag; a frontier fresh for
    # fwd_60d would be STALE for fwd_20d.
    frontier_60 = FRESH_FRONTIER
    corpus = _corpus(tmp_path / "corpus.parquet", frontier_60, label="fwd_20d_excess")
    with pytest.raises(wc.CutoffDerivationError, match="STALE"):
        wc.derive_weekly_cutoff(corpus, label="fwd_20d_excess", today=TODAY)
    frontier_20 = (pd.Timestamp(TODAY) - pd.offsets.BDay(20)).date()
    corpus2 = _corpus(tmp_path / "corpus2.parquet", frontier_20, label="fwd_20d_excess")
    cutoff = wc.derive_weekly_cutoff(corpus2, label="fwd_20d_excess", today=TODAY)
    assert cutoff == wc.quantize_to_weekly_grid(frontier_20).isoformat()


# ── CLI contract: stdout is ONLY the cutoff (command-substitution safe) ──────


def test_cli_prints_only_cutoff_on_stdout(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    corpus = _corpus(tmp_path / "corpus.parquet", FRESH_FRONTIER)
    manifest = _manifest(tmp_path / "static.json", STATIC_TAIL)
    rc = wc.main([
        "--corpus", str(corpus),
        "--lower-bound-manifest", str(manifest),
        "--as-of", TODAY.isoformat(),
    ])
    captured = capsys.readouterr()
    assert rc == 0
    assert captured.out.strip() == wc.quantize_to_weekly_grid(FRESH_FRONTIER).isoformat()
    assert "\n" not in captured.out.strip()
    assert "derived cutoff" in captured.err


def test_cli_fail_closed_exit_code_and_stderr(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    rc = wc.main([
        "--corpus", str(tmp_path / "missing.parquet"),
        "--as-of", TODAY.isoformat(),
    ])
    captured = capsys.readouterr()
    assert rc == 1
    assert captured.out == ""  # nothing usable substitutes into LATEST_CUT
    assert "FAIL-CLOSED" in captured.err


def test_cli_max_staleness_override(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    corpus = _corpus(tmp_path / "corpus.parquet", dt.date(2026, 2, 10))
    rc = wc.main([
        "--corpus", str(corpus),
        "--max-staleness-days", "365",
        "--as-of", TODAY.isoformat(),
    ])
    captured = capsys.readouterr()
    assert rc == 0
    assert captured.out.strip() == "2026-02-09"  # Monday of the frontier's week
