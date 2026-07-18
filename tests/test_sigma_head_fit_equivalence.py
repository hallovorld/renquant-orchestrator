"""AC-A / AC-B for the single-writer amendment (base-data#48 §2 / §3).

Stage 2 retires the orchestrator σ-head self-build and makes it CONSUME the
canonical sidecar written by the SOLE base-data builder. Two acceptance
criteria are proven here (this file imports ``renquant_base_data`` — the
sibling checkout — so it runs in the full multirepo test job):

- **AC-A (writer cessation, base-data-side half):** the base-data builder is
  now the sole writer — it PUBLISHES the canonical served sidecar to the
  caller's path. (The orchestrator-side half — the σ-head path never opening
  the served sidecar for write — is pinned in
  ``tests/test_retrain_sigma_head_rawlabel.py``.)
- **AC-B (σ-head fit INPUT-POPULATION equivalence):** this proves INPUT
  equivalence, NOT byte-identical NGBoost σ artifacts. Concretely: over the
  IDENTICAL labeled-row population (row-set digest equality — a proper subset of
  all rows), the fit INPUT the σ-head consumes from the canonical file is
  byte-identical to what the σ-head's FORMER self-build produced. The former
  recipe (retired from src in this PR) is transcribed here verbatim as the
  baseline. A deterministic least-squares SURROGATE maps that identical input to
  identical coefficients — it demonstrates the input-identity ⇒ output-identity
  step for a fixed-seed estimator, but it is a stand-in, NOT the NGBoost σ head.
  This producer-only repo must not run real training (CLAUDE.md hard boundary),
  so the actual fixed-seed NGBoost fit comparison — proving the deployed σ
  artifacts are byte-identical — and the full Saturday integration chain are
  **AC-C umbrella-stage work against the pinned base-data revision**, NOT claimed
  here. The σ-head heads are 169-col sentiment-free (AC-1 appendix §4), so the
  fit-input comparison legitimately keys on the non-sentiment columns; that scope
  makes the INPUT proof independent of the sibling builder, but it does NOT let
  Stage 2 certify a pre-amendment file — the 179-col / sentiment / zero-extension
  CONTRACT is bound fail-closed at the CONSUMPTION boundary by the consumer
  verifier (``tests/test_retrain_sigma_head_rawlabel.py``), not by this
  fit-equivalence proof. When the amendment builder is present the 179 contract
  is additionally pinned (AC-A below).
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pytest

pd = pytest.importorskip("pandas")
pytest.importorskip("pyarrow")
rawlabel_sidecar = pytest.importorskip("renquant_base_data.rawlabel_sidecar")
transformer_corpus = pytest.importorskip("renquant_base_data.transformer_corpus")

from renquant_orchestrator.retrain_alpha158_fund import RAWLABEL_COLUMN  # noqa: E402

build_rawlabel_sidecar = rawlabel_sidecar.build_rawlabel_sidecar
RAWLABEL_SIDECAR_COLUMNS = rawlabel_sidecar.RAWLABEL_SIDECAR_COLUMNS
SENTIMENT_COLS = tuple(rawlabel_sidecar.SENTIMENT_COLS)
TRANSFORMER_CORPUS_COLUMNS = transformer_corpus.TRANSFORMER_CORPUS_COLUMNS
LABEL_COLS = transformer_corpus.LABEL_COLS
SPLIT_COL = transformer_corpus.SPLIT_COL

HORIZON = 3
TODAY = dt.date(2026, 7, 3)
BAR_DATES = pd.bdate_range("2026-06-01", periods=12)
# Panel frontier stops 2 bars short of the OHLCV frontier so the LAST panel
# date's forward window is incomplete → a genuinely UNLABELED tail row, making
# the labeled population a proper subset (the population AC-B must match).
PANEL_DATES = BAR_DATES[:10]
PANEL_FEATURE_COLS = [
    c
    for c in TRANSFORMER_CORPUS_COLUMNS
    if c not in ("ticker", "date", SPLIT_COL) + tuple(LABEL_COLS)
]


def _fund_panel(tickers=("AAA", "BBB", "CCC")) -> "pd.DataFrame":
    """A production-shaped fund panel carrying the FULL 178-column schema
    (sentiment included) so BOTH builder versions accept it."""
    rows = []
    for t_i, ticker in enumerate(tickers):
        for d_i, date in enumerate(PANEL_DATES):
            row = {"ticker": ticker, "date": date}
            for f_i, col in enumerate(PANEL_FEATURE_COLS):
                row[col] = float(t_i + 1) + 0.013 * d_i - 0.0007 * f_i
            for label in LABEL_COLS:
                row[label] = np.nan if d_i == 0 else 0.001 * (t_i + d_i + 1)
            row[SPLIT_COL] = "train" if d_i < 6 else "test"
            rows.append(row)
    frame = pd.DataFrame(rows, columns=list(TRANSFORMER_CORPUS_COLUMNS))
    frame["ticker"] = frame["ticker"].astype("string")
    frame[SPLIT_COL] = frame[SPLIT_COL].astype("string")
    return frame


def _closes(ticker: str) -> "pd.Series":
    base = {"AAA": 100.0, "BBB": 50.0, "CCC": 25.0, "SPY": 400.0}.get(ticker, 10.0)
    return pd.Series(
        [base * (1.0 + 0.013 * i - 0.0006 * i * i) for i in range(len(BAR_DATES))],
        index=BAR_DATES,
        name="close",
    )


def _write_fixture(tmp_path: Path, tickers=("AAA", "BBB", "CCC")):
    panel_path = tmp_path / "panel.parquet"
    _fund_panel(tickers).to_parquet(panel_path, index=False)
    ohlcv = tmp_path / "ohlcv"
    for t in (*tickers, "SPY"):
        p = ohlcv / t / "1d.parquet"
        p.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame({"close": _closes(t)}).to_parquet(p)
    return panel_path, ohlcv


def _former_sigma_head_build(panel_in: Path, panel_out: Path, ohlcv_dir: Path, horizon: int) -> None:
    """VERBATIM transcription of the σ-head self-builder retired from
    ``retrain_alpha158_fund._default_rawlabel_build_fn`` in this PR (a port of
    the umbrella ``scripts/build_raw_fwd60d_label.py``). Kept here as the AC-B
    baseline: the "former self-built input" the σ-head fit used to consume."""
    panel = pd.read_parquet(panel_in)
    panel["date"] = pd.to_datetime(panel["date"])

    spy = pd.read_parquet(ohlcv_dir / "SPY" / "1d.parquet")
    spy.index = pd.to_datetime(spy.index)
    spy_close = spy["close"].sort_index()
    spy_fwd_ret = spy_close.shift(-horizon) / spy_close - 1.0

    out_blocks = []
    for tkr, g in panel.groupby("ticker"):
        g = g.sort_values("date").reset_index(drop=True).copy()
        ohlcv_p = ohlcv_dir / tkr / "1d.parquet"
        if not ohlcv_p.exists():
            g[RAWLABEL_COLUMN] = np.nan
            out_blocks.append(g)
            continue
        ohlcv = pd.read_parquet(ohlcv_p)
        ohlcv.index = pd.to_datetime(ohlcv.index)
        close = ohlcv["close"].sort_index()
        ticker_fwd_ret = close.shift(-horizon) / close - 1.0
        g_dates = g["date"].values
        excess = (
            ticker_fwd_ret.reindex(g_dates).values - spy_fwd_ret.reindex(g_dates).values
        )
        g[RAWLABEL_COLUMN] = excess
        out_blocks.append(g)

    pd.concat(out_blocks, ignore_index=True).to_parquet(panel_out, index=False)


def _norm(df: "pd.DataFrame") -> "pd.DataFrame":
    d = df.copy()
    d["ticker"] = d["ticker"].astype(str)
    d["date"] = pd.to_datetime(d["date"])
    return d.sort_values(["ticker", "date"]).reset_index(drop=True)


def _fit_consumed_columns(former: "pd.DataFrame", canonical: "pd.DataFrame") -> list[str]:
    """The columns the σ-head NGBoost fit consumes: features + raw label, MINUS
    sentiment (prod/shadow heads are 169-col sentiment-free — AC-1 appendix §4)
    and keys/split. Intersection of the two outputs, so the set is the same
    whether the sibling base-data builder is 176 (drops sentiment) or 179."""
    shared = [c for c in former.columns if c in set(canonical.columns)]
    exclude = set(SENTIMENT_COLS) | {"ticker", "date", SPLIT_COL}
    return [c for c in shared if c not in exclude]


# ─────────────────────────── AC-A (base-data-side) ─────────────────────────


def test_base_data_builder_is_the_sole_writer_that_publishes_the_sidecar(tmp_path):
    panel_path, ohlcv = _write_fixture(tmp_path)
    out = tmp_path / "canonical_rawlabel.parquet"
    assert not out.exists()
    report = build_rawlabel_sidecar(
        panel_path, ohlcv, out, horizon_trading_days=HORIZON, today=TODAY,
        extend_to_bar_frontier=False,
    )
    # the SOLE writer publishes the served sidecar to the caller's path ...
    assert out.exists()
    assert report["n_rows"] > 0
    corpus = pd.read_parquet(out)
    assert RAWLABEL_COLUMN in corpus.columns
    # ... and its no-extension canonical recipe carries ONLY panel rows (§2.3):
    # the row-class the σ-head validator used to reject is gone.
    assert report["n_extension_rows"] == 0
    if len(RAWLABEL_SIDECAR_COLUMNS) == 179:  # amendment builder present
        assert set(SENTIMENT_COLS) <= set(corpus.columns)
        assert corpus.shape[1] == 179


# ─────────────────────────── AC-B (fit equivalence) ────────────────────────


def test_labeled_row_population_is_identical(tmp_path):
    panel_path, ohlcv = _write_fixture(tmp_path)
    former_out = tmp_path / "former.parquet"
    canon_out = tmp_path / "canonical.parquet"
    _former_sigma_head_build(panel_path, former_out, ohlcv, HORIZON)
    build_rawlabel_sidecar(
        panel_path, ohlcv, canon_out, horizon_trading_days=HORIZON, today=TODAY,
        extend_to_bar_frontier=False,
    )
    former = _norm(pd.read_parquet(former_out))
    canon = _norm(pd.read_parquet(canon_out))

    def labeled_keys(df):
        m = np.isfinite(pd.to_numeric(df[RAWLABEL_COLUMN], errors="coerce").to_numpy("float64"))
        return set(map(tuple, df.loc[m, ["ticker", "date"]].to_numpy()))

    fk, ck = labeled_keys(former), labeled_keys(canon)
    # row-set digest equality (AC-B): the two builders label EXACTLY the same
    # (ticker,date) rows ...
    assert fk == ck
    # ... and it is a PROPER subset of all rows (the unlabeled tail exists), so
    # the match is not vacuous.
    assert 0 < len(fk) < len(former)


def test_fit_input_is_byte_identical_over_the_labeled_population(tmp_path):
    """AC-B (input-population equivalence): the σ-head-consumed feature matrix +
    label are byte-identical between the FORMER self-build and the canonical
    build, over the identical labeled rows. This is a claim about the fit INPUT,
    not about the trained NGBoost σ artifact (see module docstring)."""
    panel_path, ohlcv = _write_fixture(tmp_path)
    former_out = tmp_path / "former.parquet"
    canon_out = tmp_path / "canonical.parquet"
    _former_sigma_head_build(panel_path, former_out, ohlcv, HORIZON)
    build_rawlabel_sidecar(
        panel_path, ohlcv, canon_out, horizon_trading_days=HORIZON, today=TODAY,
        extend_to_bar_frontier=False,
    )
    former = _norm(pd.read_parquet(former_out)).set_index(["ticker", "date"])
    canon = _norm(pd.read_parquet(canon_out)).set_index(["ticker", "date"])

    label = pd.to_numeric(former[RAWLABEL_COLUMN], errors="coerce").to_numpy("float64")
    keys = former.index[np.isfinite(label)]

    consumed = _fit_consumed_columns(former.reset_index(), canon.reset_index())
    assert RAWLABEL_COLUMN in consumed and len(consumed) > 5  # features + label

    max_abs_diff = 0.0
    for col in consumed:
        fv = former.loc[keys, col].to_numpy("float64")
        cv = canon.loc[keys, col].to_numpy("float64")
        # byte-identical (equal_nan): no fixed tolerance needed
        assert np.array_equal(fv, cv, equal_nan=True), col
        both_nan = np.isnan(fv) & np.isnan(cv)
        max_abs_diff = max(max_abs_diff, float(np.max(np.where(both_nan, 0.0, np.abs(fv - cv)))))
    assert max_abs_diff == 0.0


def test_deterministic_surrogate_fit_output_is_byte_identical(tmp_path):
    """Demonstrate the input-identity ⇒ output-identity step for a fixed-seed
    estimator: a deterministic numpy least-squares SURROGATE yields byte-identical
    coefficients from the two builders' inputs. This is a STAND-IN for the
    fixed-seed NGBoost fit — NOT the σ artifact itself. It corroborates the AC-B
    input-population equivalence; it does NOT prove byte-identical deployed σ
    heads. That real fixed-seed NGBoost comparison is AC-C umbrella-stage work
    (this producer-only repo must not run training — CLAUDE.md)."""
    panel_path, ohlcv = _write_fixture(tmp_path)
    former_out = tmp_path / "former.parquet"
    canon_out = tmp_path / "canonical.parquet"
    _former_sigma_head_build(panel_path, former_out, ohlcv, HORIZON)
    build_rawlabel_sidecar(
        panel_path, ohlcv, canon_out, horizon_trading_days=HORIZON, today=TODAY,
        extend_to_bar_frontier=False,
    )
    former = _norm(pd.read_parquet(former_out)).set_index(["ticker", "date"])
    canon = _norm(pd.read_parquet(canon_out)).set_index(["ticker", "date"])
    label = pd.to_numeric(former[RAWLABEL_COLUMN], errors="coerce").to_numpy("float64")
    keys = former.index[np.isfinite(label)]

    consumed = _fit_consumed_columns(former.reset_index(), canon.reset_index())
    feats = [c for c in consumed if c != RAWLABEL_COLUMN]

    def fit(df):
        X = np.nan_to_num(df.loc[keys, feats].to_numpy("float64"))
        y = df.loc[keys, RAWLABEL_COLUMN].to_numpy("float64")
        return np.linalg.lstsq(X, y, rcond=None)[0]

    beta_former, beta_canon = fit(former), fit(canon)
    assert np.array_equal(beta_former, beta_canon)
