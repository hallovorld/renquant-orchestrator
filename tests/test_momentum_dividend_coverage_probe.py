"""ZERO_BY_ABSENCE must never be reported as a clean non-payer.

Every fixture is synthetic. The live tree currently has 31 names with no
dividend column and all 31 are genuine non-payers, so a test bound to live data
would pass for the wrong reason today and go red the day someone backfills.
"""
from __future__ import annotations

import json
import pathlib
import sys

import pandas as pd
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from ops.renquant104.momentum_dividend_coverage_probe import (  # noqa: E402
    HAS_DIVIDENDS, SOURCE_MISSING, ZERO_BY_ABSENCE, ZERO_BY_DATA,
    ArtifactUnreadable, classify, main, newest_artifact, probe,
)


def _parquet(root: pathlib.Path, ticker: str, *, dividend) -> None:
    """dividend=None writes NO dividend column — the fail-open case."""
    d = root / ticker
    d.mkdir(parents=True, exist_ok=True)
    frame = {"close": [10.0, 11.0, 12.0]}
    if dividend is not None:
        frame["dividend"] = dividend
    pd.DataFrame(frame).to_parquet(d / "1d.parquet")


def _artifact(tmp_path: pathlib.Path, tickers, *, cutoff="2026-08-02") -> pathlib.Path:
    d = tmp_path / "momentum" / cutoff
    d.mkdir(parents=True)
    f = d / "momentum_residual_v0.json"
    f.write_text(json.dumps({
        "cutoff_date": cutoff,
        "content_sha256": "deadbeef",
        "formation_return": {t: 0.1 for t in tickers},
    }), encoding="utf-8")
    return f


# --- the distinction this file exists for ---------------------------------

def test_missing_column_is_NOT_reported_as_a_non_payer(tmp_path):
    """The whole point. A payer whose column vanished and a real non-payer both
    sum to zero; only one of them is a defect."""
    o = tmp_path / "ohlcv"
    _parquet(o, "PAYER_LOST_COL", dividend=None)
    _parquet(o, "REAL_NON_PAYER", dividend=[0.0, 0.0, 0.0])
    assert classify("PAYER_LOST_COL", o)["state"] == ZERO_BY_ABSENCE
    assert classify("REAL_NON_PAYER", o)["state"] == ZERO_BY_DATA


def test_a_payer_is_recognised(tmp_path):
    o = tmp_path / "ohlcv"
    _parquet(o, "KO", dividend=[0.0, 0.5, 0.0])
    r = classify("KO", o)
    assert r["state"] == HAS_DIVIDENDS
    assert r["abs_dividend_sum"] == pytest.approx(0.5)


def test_absent_parquet_is_its_own_state(tmp_path):
    assert classify("GHOST", tmp_path / "ohlcv")["state"] == SOURCE_MISSING


def test_nan_dividends_do_not_read_as_a_payer(tmp_path):
    """NaN.abs().sum() is 0.0 only after fillna; without it the column would
    still be present and the name would be classified from a NaN total."""
    o = tmp_path / "ohlcv"
    _parquet(o, "NANNY", dividend=[float("nan")] * 3)
    assert classify("NANNY", o)["state"] == ZERO_BY_DATA


# --- aggregation ----------------------------------------------------------

def test_degraded_names_are_counted_and_named(tmp_path):
    o = tmp_path / "ohlcv"
    _parquet(o, "AAA", dividend=[0.1, 0.0, 0.0])   # payer
    _parquet(o, "BBB", dividend=[0.0, 0.0, 0.0])   # real non-payer
    _parquet(o, "CCC", dividend=None)              # SILENTLY degraded
    art = _artifact(tmp_path, ["AAA", "BBB", "CCC"])
    p = probe(art, o)
    assert p["n_names"] == 3
    assert p["n_substituted_dividend_input"] == 1
    assert p["substituted_dividend_input"] == ["CCC"]
    assert p["counts"][ZERO_BY_ABSENCE] == 1
    assert p["counts"][ZERO_BY_DATA] == 1
    assert p["counts"][HAS_DIVIDENDS] == 1


def test_source_missing_also_counts_as_substituted(tmp_path):
    o = tmp_path / "ohlcv"
    _parquet(o, "AAA", dividend=[0.1, 0.0, 0.0])
    art = _artifact(tmp_path, ["AAA", "GHOST"])
    p = probe(art, o)
    assert p["n_substituted_dividend_input"] == 1
    assert p["substituted_dividend_input"] == ["GHOST"]


def test_clean_book_exits_zero_and_degraded_exits_one(tmp_path):
    o = tmp_path / "ohlcv"
    _parquet(o, "AAA", dividend=[0.1, 0.0, 0.0])
    clean = _artifact(tmp_path, ["AAA"])
    assert main(["--artifact", str(clean), "--ohlcv-root", str(o)]) == 0
    _parquet(o, "CCC", dividend=None)
    bad = _artifact(tmp_path / "second", ["AAA", "CCC"])
    assert main(["--artifact", str(bad), "--ohlcv-root", str(o)]) == 1


# --- refusals -------------------------------------------------------------

def test_artifact_with_no_formation_return_refuses(tmp_path):
    d = tmp_path / "momentum" / "2026-08-02"
    d.mkdir(parents=True)
    f = d / "momentum_residual_v0.json"
    f.write_text(json.dumps({"cutoff_date": "2026-08-02"}), encoding="utf-8")
    with pytest.raises(ArtifactUnreadable):
        probe(f, tmp_path / "ohlcv")


def test_empty_formation_return_refuses_rather_than_reporting_full_coverage(tmp_path):
    d = tmp_path / "momentum" / "2026-08-02"
    d.mkdir(parents=True)
    f = d / "momentum_residual_v0.json"
    f.write_text(json.dumps({"formation_return": {}}), encoding="utf-8")
    with pytest.raises(ArtifactUnreadable):
        probe(f, tmp_path / "ohlcv")


def test_unparseable_artifact_refuses(tmp_path):
    f = tmp_path / "a.json"
    f.write_text("{not json", encoding="utf-8")
    with pytest.raises(ArtifactUnreadable):
        probe(f, tmp_path / "ohlcv")


# --- newest-artifact selection --------------------------------------------

def test_newest_is_chosen_by_date_name_not_mtime(tmp_path):
    """A re-copied older file gets a fresh mtime without being newer. This repo
    has already published one wrong 'newest file' from an mtime sort."""
    root = tmp_path / "momentum"
    for day in ("2026-07-26", "2026-08-02"):
        d = root / day
        d.mkdir(parents=True)
        (d / "momentum_residual_v0.json").write_text("{}", encoding="utf-8")
    # touch the OLDER one so it has the newest mtime
    old = root / "2026-07-26" / "momentum_residual_v0.json"
    old.write_text("{} ", encoding="utf-8")
    assert newest_artifact(root).parent.name == "2026-08-02"


def test_missing_artifact_root_refuses(tmp_path):
    with pytest.raises(ArtifactUnreadable):
        newest_artifact(tmp_path / "nope")
