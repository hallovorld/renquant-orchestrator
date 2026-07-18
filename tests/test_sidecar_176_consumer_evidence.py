"""AC-1 executable consumer evidence: orchestrator vs the 176-col sidecar.

Companion to renquant-base-data
``doc/design/2026-07-18-rawlabel-sidecar-sentiment-reconciliation.md`` (AC-1)
and its evidence appendix. The orchestrator touches the served
``alpha158_291_fundamental_dataset_rawlabel.parquet`` on two surfaces:

1. ``build_patchtst_wf_manifest`` / ``retrain_patchtst``: pure PATH PLUMBING —
   the resolved path is handed to ``renquant_model_patchtst.fit_calibrator``
   via ``--raw-label-panel``; no parquet is opened here. Safe at 176 columns
   transitively (the calibrator's read is column-pruned to keys + er label —
   pinned in the renquant-model companion tests).

2. ``retrain_alpha158_fund`` σ-head refresh: NOT a mere reader — it is an
   ACTIVE WRITER of the served sidecar path (weekly, via
   ``weekly_wf_promote.sh`` -> ``daily_retrain_alpha158_fund.sh``). Its
   builder (``_default_rawlabel_build_fn``, a port of the ORIGINAL Track-A
   ``build_raw_fwd60d_label.py``) emits the FULL fund-panel schema + the raw
   label — sentiment columns INCLUDED (179 when the panel carries them) —
   and its pre-swap validator checks keys/label only, never column count.
   These tests pin that executably: after a one-time 179 -> 176 migration,
   the next σ-head refresh would re-emit the sentiment columns and re-arm
   the weekly PatchTST corpus-refresh deadlock unless the recipes are
   unified first. (Evidence, not a fix: the fix is a design call in the
   base-data RFC's rollout.)

Fixture provenance: ``tests/fixture_rawlabel_sidecar_columns_176.json`` is an
export of renquant-base-data ``rawlabel_sidecar.RAWLABEL_SIDECAR_COLUMNS`` at
main ``b72dd92``; base-data ``tests/test_rawlabel_sidecar_schema_export.py``
is the drift guard for every embedded copy (this file is named there).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from renquant_orchestrator import retrain_alpha158_fund as sigma_mod
from renquant_orchestrator.build_patchtst_wf_manifest import (
    DEFAULT_RAW_LABEL_PANEL_REL,
    build_calibrator_cmd,
    default_raw_label_panel_path,
)

pytest.importorskip("pyarrow")

SIDECAR_COLUMNS = json.loads(
    (Path(__file__).parent / "fixture_rawlabel_sidecar_columns_176.json").read_text()
)
SENTIMENT_COLS = ["sentiment_pos_share", "mean_sentiment", "n_articles_log"]


# ── surface 1: PatchTST WF manifest path plumbing (reader-by-proxy) ──────────


def test_manifest_builder_binds_the_exact_served_sidecar_filename(tmp_path):
    assert (
        str(DEFAULT_RAW_LABEL_PANEL_REL)
        == "data/alpha158_291_fundamental_dataset_rawlabel.parquet"
    )
    resolved = default_raw_label_panel_path(tmp_path)
    assert resolved == str(tmp_path / DEFAULT_RAW_LABEL_PANEL_REL)
    assert default_raw_label_panel_path(None) is None


def test_manifest_builder_passes_path_through_without_reading(tmp_path):
    """The path lands verbatim in the fit_calibrator argv; the manifest
    builder itself never opens the parquet (nothing to break at 176)."""
    raw = tmp_path / "data" / "alpha158_291_fundamental_dataset_rawlabel.parquet"
    cmd = build_calibrator_cmd(
        scorer_artifact=tmp_path / "model.pt",
        out_path=tmp_path / "cal.json",
        panel_path=tmp_path / "panel.parquet",
        raw_label_panel_path=raw,  # does not even exist: pass-through only
        label="fwd_60d_excess",
        data_end="2026-01-01",
        batch_size=2048,
        method="platt",
        min_rows=1000,
    )
    assert "--raw-label-panel" in cmd
    assert cmd[cmd.index("--raw-label-panel") + 1] == str(raw)
    assert "renquant_model_patchtst.fit_calibrator" in cmd


# ── surface 2: the σ-head refresh is a competing WRITER of the served path ───


def _ohlcv_fixture(tmp_path: Path, tickers, dates) -> Path:
    ohlcv_dir = tmp_path / "ohlcv"
    rng = np.random.default_rng(3)
    for ticker in [*tickers, "SPY"]:
        d = ohlcv_dir / ticker
        d.mkdir(parents=True)
        close = pd.DataFrame(
            {"close": 100.0 + rng.normal(0, 1, size=len(dates)).cumsum()},
            index=dates,
        )
        close.to_parquet(d / "1d.parquet")
    return ohlcv_dir


def _panel_with_sentiment(dates, tickers) -> pd.DataFrame:
    """A miniature fund panel in the PRODUCTION shape: features + the three
    sentiment columns (the live 178-column panel carries them)."""
    rows = [(t, d) for t in tickers for d in dates]
    rng = np.random.default_rng(5)
    panel = pd.DataFrame({
        "ticker": [t for t, _ in rows],
        "date": [d for _, d in rows],
        "KMID": rng.normal(size=len(rows)),
        "roe": rng.normal(size=len(rows)),
    })
    for col in SENTIMENT_COLS:
        panel[col] = rng.normal(size=len(rows))
    return panel


def test_sigma_head_builder_reemits_sentiment_columns_from_the_panel(tmp_path):
    """THE writer conflict: the σ-head build copies the panel schema wholesale
    and appends fwd_60d_excess_raw — a sentiment-carrying panel yields a
    sentiment-carrying sidecar (the 179-column contract), directly opposing
    the base-data builder's 176-column freeze on the SAME served path."""
    dates = pd.bdate_range("2024-01-02", periods=70)
    tickers = ["AAA", "BBB"]
    panel = _panel_with_sentiment(dates, tickers)
    panel_in = tmp_path / "panel.parquet"
    panel.to_parquet(panel_in, index=False)
    ohlcv_dir = _ohlcv_fixture(tmp_path, tickers, dates)
    out = tmp_path / "staged_rawlabel.parquet"

    sigma_mod._default_rawlabel_build_fn()(panel_in, out, ohlcv_dir, 60)

    staged = pd.read_parquet(out)
    assert set(SENTIMENT_COLS) <= set(staged.columns)
    assert sigma_mod.RAWLABEL_COLUMN in staged.columns
    assert list(staged.columns) == list(panel.columns) + [sigma_mod.RAWLABEL_COLUMN]


def test_sigma_head_validator_is_blind_to_the_column_contract(tmp_path):
    """The pre-swap validator would not defend EITHER recipe: it checks only
    keys + the raw label + coverage, so a 176-column (sentiment-free) staged
    file with panel-identical keys is accepted just as a 179-column one is.
    The column contract on the served path is therefore governed by whichever
    writer ran last — the deadlock's mechanical core."""
    dates = pd.bdate_range("2024-01-02", periods=10)
    tickers = ["AAA", "BBB"]
    panel = _panel_with_sentiment(dates, tickers)
    panel_in = tmp_path / "panel.parquet"
    panel.to_parquet(panel_in, index=False)

    staged_176_style = panel[["ticker", "date", "KMID", "roe"]].copy()
    staged_176_style[sigma_mod.RAWLABEL_COLUMN] = 0.01
    staged_path = tmp_path / "staged.parquet"
    staged_176_style.to_parquet(staged_path, index=False)

    report = sigma_mod._default_rawlabel_validate_fn()(staged_path, panel_in, 60)
    assert report["n_rows"] == len(panel)


def test_sigma_head_validator_rejects_bar_frontier_extension_rows(tmp_path):
    """Recipe incompatibility in the OTHER direction: the base-data builder
    extends each ticker's axis to the bar frontier (rows beyond the panel),
    which this validator refuses (staged keys must EXACTLY equal panel keys).
    A migrated, base-data-built sidecar therefore cannot be revalidated by
    the σ-head path as-is — the two recipes disagree on rows as well as
    columns."""
    dates = pd.bdate_range("2024-01-02", periods=10)
    tickers = ["AAA"]
    panel = _panel_with_sentiment(dates, tickers)
    panel_in = tmp_path / "panel.parquet"
    panel.to_parquet(panel_in, index=False)

    extension = pd.DataFrame({
        "ticker": ["AAA"],
        "date": [dates[-1] + pd.tseries.offsets.BDay(1)],
        "KMID": [np.nan], "roe": [np.nan],
        **{c: [np.nan] for c in SENTIMENT_COLS},
    })
    staged = pd.concat([panel, extension], ignore_index=True)
    staged[sigma_mod.RAWLABEL_COLUMN] = 0.01
    staged_path = tmp_path / "staged.parquet"
    staged.to_parquet(staged_path, index=False)

    with pytest.raises(sigma_mod.RawlabelValidationError, match="coverage"):
        sigma_mod._default_rawlabel_validate_fn()(staged_path, panel_in, 60)


def test_embedded_176_schema_is_sentiment_free():
    assert len(SIDECAR_COLUMNS) == 176
    assert not set(SENTIMENT_COLS) & set(SIDECAR_COLUMNS)
    assert SIDECAR_COLUMNS[-1] == sigma_mod.RAWLABEL_COLUMN
