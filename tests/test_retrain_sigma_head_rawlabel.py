"""Tests for the σ-head (QuantileHead) RAW ``_rawlabel`` CONSUME + certify task.

Single-writer amendment (base-data#48 §2.1): the served
``alpha158_291_fundamental_dataset_rawlabel.parquet`` used to have TWO weekly
writers with contradictory recipes (this orchestrator task's self-build, and the
base-data builder) — a writer war that deadlocked the weekly PatchTST corpus
refresh. The amendment makes ``renquant_base_data.rawlabel_sidecar`` the SOLE
writer. This task's self-build + column-contract-blind pre-swap validator are
RETIRED; it now CONSUMES the canonical file the sole writer published upstream:

- run AFTER the panel build/merge and be wired into the pipeline,
- VERIFY the canonical sidecar is present, in LOCKSTEP with the fresh panel
  (exact (ticker,date) coverage) and usable (unique keys, finite-label floor),
  then CERTIFY it (provenance sidecar binding its on-disk digest); it NEVER
  opens the served sidecar for write (AC-A),
- isolate any failure (alert + log, NEVER abort the ranker retrain),
- soft-skip a missing upstream panel without a false alert.

The consumer verifier is dependency-injected so wiring tests can use opaque
canonical bytes; the default verifier is exercised on real parquet fixtures.
No production ``_rawlabel`` parquet is written by this task.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
import subprocess

import pytest

from renquant_orchestrator import retrain_alpha158_fund as mod
from renquant_orchestrator import retrain_common


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "RenQuant"
    (repo / "data").mkdir(parents=True)
    return repo


def _ctx(repo: Path, **kw) -> mod.RetrainContext:
    return mod.RetrainContext(
        repo_dir=repo,
        xgb_artifact_out=repo / "x.json",
        calibrator_out=repo / "c.json",
        **kw,
    )


def _write_panel(repo: Path) -> Path:
    """Stand-in fresh fund panel so the task doesn't soft-skip. Opaque bytes:
    the injected verify callable never reads it in the mock tests."""
    p = repo / "data" / mod.DEFAULT_PANEL_FILENAME
    p.write_bytes(b"PANEL")
    return p


def _write_canonical(repo: Path, payload: bytes = b"RAWLABEL") -> Path:
    """Stand-in canonical served sidecar (written UPSTREAM by the sole base-data
    writer) so the consumer has a file to verify + certify. Opaque bytes: the
    injected verify callable never reads it in the mock tests."""
    p = repo / "data" / mod.DEFAULT_RAWLABEL_FILENAME
    p.write_bytes(payload)
    return p


def _passthru_verify(report: dict | None = None):
    """A stand-in consumer verifier for wiring tests that use opaque canonical
    bytes (the real verifier is exercised on real parquet fixtures separately)."""

    def _v(canonical, panel_in, horizon):
        return report or {"n_rows": 1, "n_tickers": 1, "finite_fraction": 1.0, "horizon": horizon}

    return _v


# ─────────────────────────── wiring / ordering ─────────────────────────────


def test_sigma_head_task_wired_after_fund_panel_merge() -> None:
    names = [type(t).__name__ for t in mod.build_pipeline().jobs[0].tasks]
    assert "RefreshSigmaHeadRawLabelTask" in names
    # runs immediately after the fund-panel merge (its lockstep source) ...
    assert (
        names.index("RefreshSigmaHeadRawLabelTask")
        == names.index("MergeFundFeaturesTask") + 1
    )
    # ... and before the ranker training (it is an independent downstream step).
    assert names.index("RefreshSigmaHeadRawLabelTask") < names.index("TrainGbdtScorerTask")


# ─────────────────── AC-A: writer cessation (no corpus write) ───────────────


def test_task_has_no_self_build_recipe_anymore() -> None:
    # base-data#48 §2.1: the self-build + column-contract-blind validator are
    # RETIRED. The symbols are gone; only the consumer verifier remains.
    assert not hasattr(mod, "_default_rawlabel_build_fn")
    assert not hasattr(mod, "_default_rawlabel_validate_fn")
    assert hasattr(mod, "_default_rawlabel_verify_fn")
    # the DI hook renamed build/validate -> a single consumer verify hook
    import dataclasses

    names = {f.name for f in dataclasses.fields(mod.RetrainContext)}
    assert "rawlabel_verify_fn" in names
    assert "rawlabel_build_fn" not in names and "rawlabel_validate_fn" not in names


def test_consume_never_opens_the_served_sidecar_for_write(tmp_path) -> None:
    """AC-A: the σ-head path CONSUMES the canonical file — it must never write
    (create, swap, or mutate) the served sidecar. We prove it two ways: the
    on-disk bytes are byte-identical before/after a successful verify+certify,
    and NO ``.staging`` sibling is ever created."""
    repo = _repo(tmp_path)
    _write_panel(repo)
    canonical = _write_canonical(repo, b"CANONICAL-BYTES-FROM-SOLE-WRITER")
    before = canonical.read_bytes()
    staging = canonical.with_name(canonical.name + ".staging")

    ctx = _ctx(repo, rawlabel_verify_fn=_passthru_verify())
    assert mod.RefreshSigmaHeadRawLabelTask().run(ctx) is True

    assert ctx.rawlabel_refresh_summary["status"] == "verified"
    # the served corpus bytes are UNCHANGED (read-only consumption) ...
    assert canonical.read_bytes() == before
    # ... and the task never created a staging file (it does not build/swap).
    assert not staging.exists()


# ─────────────────────────── consume happy path ────────────────────────────


def test_consume_verifies_present_canonical_and_certifies(tmp_path) -> None:
    repo = _repo(tmp_path)
    _write_panel(repo)
    canonical = _write_canonical(repo, b"RAWLABEL")

    ctx = _ctx(
        repo,
        rawlabel_verify_fn=_passthru_verify(
            {"n_rows": 3, "n_tickers": 2, "finite_fraction": 0.9, "horizon": 60}
        ),
    )
    assert mod.RefreshSigmaHeadRawLabelTask().run(ctx) is True

    assert ctx.rawlabel_refresh_summary["status"] == "verified"
    # a certified consume stamps provenance and leaves NO invalidation receipt
    prov = mod.rawlabel_provenance_path(canonical)
    assert prov.exists()
    prov_payload = json.loads(prov.read_text())
    assert prov_payload["n_rows"] == 3
    # the provenance binds the CONSUMED corpus to its own on-disk digest — the
    # #427 contract (source_panel_sha256 was the INPUT; rawlabel_sha256 is the
    # corpus bytes this retrain certifies).
    assert prov_payload["rawlabel_sha256"] == mod._sha256_file(canonical)
    assert prov_payload["schema_version"] == mod.RAWLABEL_PROVENANCE_SCHEMA_VERSION
    assert not mod.rawlabel_receipt_path(canonical).exists()
    assert mod.is_rawlabel_admissible(canonical) is True


def test_consume_clears_a_prior_invalidation_receipt(tmp_path) -> None:
    repo = _repo(tmp_path)
    panel = _write_panel(repo)
    canonical = _write_canonical(repo, b"FRESH-CANONICAL")
    # a stale receipt from a prior failed run must be cleared by a good consume
    mod._write_invalidation_receipt(canonical, reason="prior failure", panel_in=panel, horizon=60)
    assert mod.is_rawlabel_admissible(canonical) is False

    ctx = _ctx(repo, rawlabel_verify_fn=_passthru_verify())
    assert mod.RefreshSigmaHeadRawLabelTask().run(ctx) is True
    assert ctx.rawlabel_refresh_summary["status"] == "verified"
    assert mod.is_rawlabel_admissible(canonical) is True


# ─────────────────────────── failure isolation ─────────────────────────────


def test_absent_canonical_is_isolated_and_alerts(tmp_path, monkeypatch) -> None:
    repo = _repo(tmp_path)
    _write_panel(repo)
    # the sole base-data writer published NOTHING → the consumer cannot certify.
    final = repo / "data" / mod.DEFAULT_RAWLABEL_FILENAME
    assert not final.exists()

    alerts: list = []
    monkeypatch.setattr(
        mod, "post_ntfy", lambda title, body, topic: alerts.append((title, body, topic))
    )

    ctx = _ctx(repo)  # DEFAULT verifier; no canonical to verify
    # NEVER raises — the ranker retrain must continue
    assert mod.RefreshSigmaHeadRawLabelTask().run(ctx) is True
    assert ctx.rawlabel_refresh_summary["status"] == "failed"
    assert "absent" in ctx.rawlabel_refresh_summary["error"]
    # loud alert emitted
    assert alerts and alerts[0][0] == "RenQuant retrain SIGMA-HEAD-RAWLABEL"
    # a swallowed failure is NOT fail-open: a durable invalidation receipt blocks
    # downstream admission of the (absent/uncertified) corpus.
    receipt = mod.rawlabel_receipt_path(final)
    assert ctx.rawlabel_refresh_summary["receipt_written"] is True
    assert receipt.exists()
    assert mod.is_rawlabel_admissible(final) is False
    with pytest.raises(mod.RawlabelStaleError):
        mod.assert_rawlabel_admissible(final)


def test_verify_failure_leaves_canonical_untouched_and_alerts(tmp_path, monkeypatch) -> None:
    repo = _repo(tmp_path)
    _write_panel(repo)
    canonical = _write_canonical(repo, b"PRESENT-BUT-OUT-OF-LOCKSTEP")
    before = canonical.read_bytes()
    monkeypatch.setattr(mod, "post_ntfy", lambda *a, **k: None)

    def boom_verify(canonical_path, panel_in, horizon):
        raise mod.RawlabelValidationError("coverage != source panel")

    ctx = _ctx(repo, rawlabel_verify_fn=boom_verify)
    assert mod.RefreshSigmaHeadRawLabelTask().run(ctx) is True
    assert ctx.rawlabel_refresh_summary["status"] == "failed"
    assert "coverage" in ctx.rawlabel_refresh_summary["error"]
    # read-only: the canonical corpus the sole writer left is NOT mutated
    assert canonical.read_bytes() == before
    assert mod.rawlabel_receipt_path(canonical).exists()
    assert mod.is_rawlabel_admissible(canonical) is False


def test_consume_failure_is_silent_when_quiet(tmp_path, monkeypatch) -> None:
    repo = _repo(tmp_path)
    _write_panel(repo)
    _write_canonical(repo)
    alerts: list = []
    monkeypatch.setattr(mod, "post_ntfy", lambda *a, **k: alerts.append(a))

    def boom(*a, **k):
        raise mod.RawlabelValidationError("nope")

    ctx = _ctx(repo, rawlabel_verify_fn=boom, quiet=True)
    assert mod.RefreshSigmaHeadRawLabelTask().run(ctx) is True
    assert ctx.rawlabel_refresh_summary["status"] == "failed"
    assert not alerts  # quiet suppresses the ntfy


# ─────────────────────────── skip paths ────────────────────────────────────


def test_missing_panel_soft_skips_without_alert(tmp_path, monkeypatch) -> None:
    repo = _repo(tmp_path)  # no panel written
    _write_canonical(repo)  # a corpus may exist, but with no panel it can't be certified
    alerts: list = []
    monkeypatch.setattr(mod, "post_ntfy", lambda *a, **k: alerts.append(a))
    called: list = []
    ctx = _ctx(repo, rawlabel_verify_fn=lambda *a, **k: called.append(a) or {})

    assert mod.RefreshSigmaHeadRawLabelTask().run(ctx) is True
    assert ctx.rawlabel_refresh_summary["status"] == "skipped-no-panel"
    assert not called  # verifier never invoked
    assert not alerts  # a missing panel is the ranker path's failure, not a σ-head alert
    # ...but the corpus can't be certified in-lockstep with a missing panel, so a
    # receipt is still written (silent) to block downstream admission.
    final = repo / "data" / mod.DEFAULT_RAWLABEL_FILENAME
    assert ctx.rawlabel_refresh_summary["receipt_written"] is True
    receipt = mod.rawlabel_receipt_path(final)
    assert receipt.exists()
    assert "panel missing" in json.loads(receipt.read_text())["reason"]


def test_disabled_refresh_skips(tmp_path) -> None:
    repo = _repo(tmp_path)
    _write_panel(repo)
    _write_canonical(repo)
    called: list = []
    ctx = _ctx(repo, refresh_rawlabel=False, rawlabel_verify_fn=lambda *a, **k: called.append(a) or {})
    assert mod.RefreshSigmaHeadRawLabelTask().run(ctx) is True
    assert ctx.rawlabel_refresh_summary["status"] == "skipped"
    assert not called


def test_dry_run_does_not_consume(tmp_path) -> None:
    repo = _repo(tmp_path)
    _write_panel(repo)
    canonical = _write_canonical(repo)
    called: list = []
    ctx = _ctx(repo, dry_run=True, rawlabel_verify_fn=lambda *a, **k: called.append(a) or {})
    assert mod.RefreshSigmaHeadRawLabelTask().run(ctx) is True
    assert ctx.rawlabel_refresh_summary["status"] == "dry-run"
    assert not called
    # dry-run neither verifies nor certifies: no provenance stamped
    assert not mod.rawlabel_provenance_path(canonical).exists()


# ─────────────────────────── CLI wiring ────────────────────────────────────


def test_cli_refresh_rawlabel_defaults_true_and_opt_out(tmp_path) -> None:
    repo = _repo(tmp_path)
    assert mod.parse_args(["--repo-dir", str(repo), "--dry-run"]).refresh_rawlabel is True
    assert (
        mod.parse_args(
            ["--repo-dir", str(repo), "--no-refresh-rawlabel", "--dry-run"]
        ).refresh_rawlabel
        is False
    )


def test_main_wires_refresh_rawlabel_into_context(monkeypatch, tmp_path) -> None:
    repo = _repo(tmp_path)
    captured: list[mod.RetrainContext] = []

    class FakePipeline:
        def run(self, ctx):
            captured.append(ctx)
            return None

    monkeypatch.setattr(mod, "build_pipeline", lambda: FakePipeline())
    assert mod.main(["--repo-dir", str(repo), "--no-refresh-rawlabel", "--dry-run"]) == 0
    assert captured and captured[0].refresh_rawlabel is False


# ───────────────────── end-to-end pipeline isolation ───────────────────────


def test_pipeline_isolates_sigma_head_failure_from_ranker_retrain(tmp_path, monkeypatch) -> None:
    repo = _repo(tmp_path)
    _write_panel(repo)
    scorer = repo / "artifacts" / "panel-ltr.staging.json"
    calibrator = repo / "artifacts" / "panel-rank-calibration.staging.json"

    def fake_run(cmd, cwd=None, env=None):
        if "renquant_orchestrator.train_gbdt" in cmd:
            scorer.parent.mkdir(parents=True, exist_ok=True)
            scorer.write_text(
                json.dumps(
                    {
                        "config_fingerprint": "sha256:test",
                        "trained_date": dt.datetime.utcnow().strftime("%Y-%m-%d"),
                    }
                )
            )
        if "renquant_model_gbdt.fit_calibrator_alpha158_fund" in cmd:
            calibrator.parent.mkdir(parents=True, exist_ok=True)
            calibrator.write_text(json.dumps({"method": "isotonic"}))
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(retrain_common.subprocess, "run", fake_run)
    monkeypatch.setattr(mod, "post_ntfy", lambda *a, **k: None)
    monkeypatch.setattr(
        mod, "_stamp_calibrator_fingerprint",
        lambda scorer_path, cal_path: None,
    )

    # Feed the (now fail-closed, #217) OHLCV-refresh + freshness guard a passing
    # setup — explicit universe, fresh injected bars, and an independently pinned
    # expected session + gap fn — so the pipeline actually REACHES the σ-head task.
    # No canonical sidecar is present → the CONSUME step fails, isolated.
    pd = pytest.importorskip("pandas")
    frontier = dt.date(2026, 6, 30)

    def fake_fetch(sym, *, timeout_sec=None):
        idx = pd.bdate_range(end=pd.Timestamp(frontier), periods=5)
        return pd.DataFrame({"close": 1.0}, index=idx)

    strategy_config = repo / "strategy_config.json"
    strategy_config.write_text("{}")
    ctx = mod.RetrainContext(
        repo_dir=repo,
        xgb_artifact_out=scorer,
        calibrator_out=calibrator,
        strategy_config_path=strategy_config,
        panel_universe=["AAA", "BBB"],
        fetch_fn=fake_fetch,
        expected_session=frontier,
        session_gap_fn=lambda a, b: max((b - a).days, 0),
    )

    result = mod.build_pipeline().run(ctx)

    # the ranker retrain still succeeds despite the σ-head (consume) failure
    assert result.ok is True
    assert ctx.rawlabel_refresh_summary["status"] == "failed"
    assert ctx.rawlabel_refresh_summary["receipt_written"] is True
    assert scorer.exists() and calibrator.exists()


# ───────────── real fixtures: canonical parquet + OHLCV helpers ─────────────


# ── REAL canonical-179 fixtures built via the merged Stage-1 base-data builder ──
# The consumer verifier now binds to the EXACT ordered 179-column contract
# (renquant_base_data RAWLABEL_SIDECAR_COLUMNS, base-data#48/#49 — review
# 4729337947 P0). Fixtures are therefore the GENUINE canonical artifact the sole
# base-data writer publishes — built by running base-data's build_rawlabel_sidecar
# on a full 178-column fund panel + OHLCV — NOT a 6-column distinguishing-column
# proxy. Adversarial variants are derived by MUTATING that real 179 artifact so
# each probe differs from the canonical in exactly one contract dimension.
_FIX_HORIZON = 3
_FIX_TODAY = dt.date(2026, 7, 3)
# A representative non-sentiment feature the canonical 179-col contract carries;
# dropping it (and one more) yields a "missing-feature" file that still keeps all
# three sentiment names — the case the old 3-name heuristic wrongly certified.
_NONSENTIMENT_FEATURE = "KMID"
_SECOND_NONSENTIMENT_FEATURE = "ROC60"


def _bd_modules():
    """Import the merged Stage-1 base-data builder + corpus contract (skip the
    real-parquet tests if base-data isn't importable; it is a hard dependency)."""
    corpus = pytest.importorskip("renquant_base_data.transformer_corpus")
    rawlabel = pytest.importorskip("renquant_base_data.rawlabel_sidecar")
    return corpus, rawlabel


def _fund_panel_frame(tickers=("AAA", "BBB")):
    """A production-fund-panel-shaped frame carrying the FULL 178-column served
    schema (sentiment present, split annotated). Returns (frame, bar_dates); the
    panel covers the first 5 of 10 bar dates so every row is labeled at horizon 3."""
    import numpy as np  # noqa: PLC0415
    import pandas as pd  # noqa: PLC0415

    corpus, _ = _bd_modules()
    split_col = corpus.SPLIT_COL
    label_cols = tuple(corpus.LABEL_COLS)
    panel_cols = list(corpus.TRANSFORMER_CORPUS_COLUMNS)
    feature_cols = [
        c for c in panel_cols if c not in ("ticker", "date", split_col) + label_cols
    ]
    bar_dates = pd.bdate_range("2026-06-01", periods=10)
    panel_dates = bar_dates[:5]
    rows = []
    for t_i, ticker in enumerate(tickers):
        for d_i, date in enumerate(panel_dates):
            row = {"ticker": ticker, "date": date}
            for f_i, col in enumerate(feature_cols):
                row[col] = float(t_i + 1) + 0.01 * d_i + 0.0001 * f_i
            for label in label_cols:
                row[label] = np.nan if d_i == 0 else 0.001 * (t_i + d_i + 1)
            row[split_col] = "train" if d_i < 3 else "test"
            rows.append(row)
    frame = pd.DataFrame(rows, columns=panel_cols)
    frame["ticker"] = frame["ticker"].astype("string")
    frame[split_col] = frame[split_col].astype("string")
    return frame, bar_dates


def _mk_real_repo_fixture(repo: Path, *, tickers=("AAA", "BBB")):
    """Write a real FULL 178-column fund panel + per-ticker OHLCV (incl. SPY)
    under ``repo/data`` so the DEFAULT verifier AND the base-data builder run
    end-to-end. Returns (panel_path, ohlcv_dir, bar_dates)."""
    import pandas as pd  # noqa: PLC0415

    data = repo / "data"
    ohlcv_dir = data / "ohlcv"
    frame, bar_dates = _fund_panel_frame(tickers)
    panel_path = data / mod.DEFAULT_PANEL_FILENAME
    panel_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(panel_path, index=False)
    for t in (*tickers, "SPY"):
        base = {"AAA": 100.0, "BBB": 50.0, "SPY": 400.0}.get(t, 10.0)
        close = pd.Series(
            [base * (1.0 + 0.01 * i) for i in range(len(bar_dates))],
            index=bar_dates,
            name="close",
        )
        d = ohlcv_dir / t
        d.mkdir(parents=True, exist_ok=True)
        pd.DataFrame({"close": close}).to_parquet(d / "1d.parquet")
    return panel_path, ohlcv_dir, bar_dates


def _build_canonical(panel_path: Path, ohlcv_dir: Path, out_path: Path):
    """Build the REAL canonical-179 sidecar by running the merged Stage-1
    base-data builder (zero bar-frontier extension). In exact (ticker,date)
    lockstep with ``panel_path`` by construction. Returns (out_path, built_df)."""
    import pandas as pd  # noqa: PLC0415

    corpus, rawlabel = _bd_modules()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rawlabel.build_rawlabel_sidecar(
        panel_path,
        ohlcv_dir,
        out_path,
        horizon_trading_days=_FIX_HORIZON,
        today=_FIX_TODAY,
        extend_to_bar_frontier=False,
    )
    built = pd.read_parquet(out_path)
    # sanity: the fixture really is the genuine canonical 179-column artifact
    assert list(built.columns) == [str(c) for c in rawlabel.RAWLABEL_SIDECAR_COLUMNS]
    return out_path, built


def _write(df, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    return path


# ─────────────── default consumer verifier (real parquet) ───────────────────


def test_default_verify_accepts_a_well_formed_canonical(tmp_path) -> None:
    pytest.importorskip("pandas")
    repo = _repo(tmp_path)
    panel_path, ohlcv, _ = _mk_real_repo_fixture(repo)
    canonical = tmp_path / "canonical.parquet"
    _, built = _build_canonical(panel_path, ohlcv, canonical)

    report = mod._default_rawlabel_verify_fn()(canonical, panel_path, horizon=2)
    assert report["n_rows"] == len(built) == 10
    assert report["n_tickers"] == 2
    assert report["finite_fraction"] == pytest.approx(1.0)
    assert report["horizon"] == 2
    assert report["source_panel_sha256"].startswith("sha256:")
    assert report["source_panel_frontier"]  # ISO date string


def test_default_verify_rejects_missing_label_column(tmp_path) -> None:
    pytest.importorskip("pandas")
    repo = _repo(tmp_path)
    panel_path, ohlcv, _ = _mk_real_repo_fixture(repo)
    canonical = tmp_path / "canonical.parquet"
    _, built = _build_canonical(panel_path, ohlcv, tmp_path / "real.parquet")
    # drop the raw-label column → 178 cols → NOT the exact ordered 179 contract
    _write(built.drop(columns=[mod.RAWLABEL_COLUMN]), canonical)
    with pytest.raises(mod.RawlabelValidationError, match="not the exact ordered"):
        mod._default_rawlabel_verify_fn()(canonical, panel_path, horizon=2)


def test_default_verify_rejects_empty_canonical(tmp_path) -> None:
    pytest.importorskip("pandas")
    repo = _repo(tmp_path)
    panel_path, ohlcv, _ = _mk_real_repo_fixture(repo)
    canonical = tmp_path / "canonical.parquet"
    _, built = _build_canonical(panel_path, ohlcv, tmp_path / "real.parquet")
    # exact 179 columns, ZERO rows → structural emptiness (not a contract miss)
    _write(built.iloc[0:0], canonical)
    with pytest.raises(mod.RawlabelValidationError, match="empty"):
        mod._default_rawlabel_verify_fn()(canonical, panel_path, horizon=2)


def test_default_verify_rejects_duplicate_keys(tmp_path) -> None:
    pd = pytest.importorskip("pandas")
    repo = _repo(tmp_path)
    panel_path, ohlcv, _ = _mk_real_repo_fixture(repo)
    canonical = tmp_path / "canonical.parquet"
    _, built = _build_canonical(panel_path, ohlcv, tmp_path / "real.parquet")
    dup = pd.concat([built, built.iloc[[0]]], ignore_index=True)  # duplicate one key
    _write(dup, canonical)
    with pytest.raises(mod.RawlabelValidationError, match="duplicate"):
        mod._default_rawlabel_verify_fn()(canonical, panel_path, horizon=2)


def test_default_verify_rejects_lockstep_coverage_mismatch(tmp_path) -> None:
    pytest.importorskip("pandas")
    repo = _repo(tmp_path)
    panel_path, ohlcv, _ = _mk_real_repo_fixture(repo)
    canonical = tmp_path / "canonical.parquet"
    _, built = _build_canonical(panel_path, ohlcv, tmp_path / "real.parquet")
    _write(built.iloc[:5].copy(), canonical)  # drop panel (ticker,date) rows
    with pytest.raises(mod.RawlabelValidationError, match="coverage"):
        mod._default_rawlabel_verify_fn()(canonical, panel_path, horizon=2)


def test_default_verify_rejects_future_dated_rows(tmp_path) -> None:
    pd = pytest.importorskip("pandas")
    repo = _repo(tmp_path)
    panel_path, ohlcv, bar_dates = _mk_real_repo_fixture(repo)
    canonical = tmp_path / "canonical.parquet"
    _, built = _build_canonical(panel_path, ohlcv, tmp_path / "real.parquet")
    # a REAL-shaped (finite-feature) row BEYOND the panel frontier: a future-dated
    # key absent from the panel → caught by the lockstep coverage check (distinct
    # from the intrinsic all-NaN-feature extension check).
    future = built.iloc[[0]].copy()
    future["date"] = bar_dates[7]
    _write(pd.concat([built, future], ignore_index=True), canonical)
    with pytest.raises(mod.RawlabelValidationError, match="coverage"):
        mod._default_rawlabel_verify_fn()(canonical, panel_path, horizon=2)


# ── base-data#48/#49 EXACT-CONTRACT binding at the consumption boundary (P0) ──
# Review 4729337947: the consumer must bind to the EXACT ORDERED 179-column
# Stage-1 contract, not a distinguishing-column heuristic. The old check
# (3 sentiment names + zero-extension) WRONGLY certified a reordered schema, a
# missing-feature file, and an extra-column file. These probes exercise the full
# contract on the REAL canonical artifact: only the exact-179 zero-extension file
# is CERTIFIED; a 176-col sentiment-free file, a 177-col missing-feature file, a
# +junk-column file, a reordered-179 file, and a 179+extension-row file are ALL
# REFUSED (the reviewer's 5-probe — the 3 that wrongly certified now refuse).


def test_default_verify_certifies_canonical_179_zero_extension_file(tmp_path) -> None:
    # The genuine canonical 179-col artifact (sentiment carried, zero extension,
    # built by the sole base-data writer) is CERTIFIED.
    pytest.importorskip("pandas")
    repo = _repo(tmp_path)
    panel_path, ohlcv, _ = _mk_real_repo_fixture(repo)
    canonical = tmp_path / "canonical.parquet"
    _, built = _build_canonical(panel_path, ohlcv, canonical)
    assert list(built.columns)[-4:-1] == list(mod.SENTIMENT_COLUMNS)  # sentiment carried
    report = mod._default_rawlabel_verify_fn()(canonical, panel_path, horizon=2)
    assert report["n_rows"] == 10 and report["n_tickers"] == 2


def test_default_verify_refuses_sentiment_free_176_col_file(tmp_path) -> None:
    # Pre-amendment shape: drop the three sentiment columns → 176. In perfect
    # (ticker,date) lockstep, otherwise well-formed, yet REFUSED by the exact
    # ordered contract (certifying it would re-admit the pre-amendment recipe).
    pytest.importorskip("pandas")
    repo = _repo(tmp_path)
    panel_path, ohlcv, _ = _mk_real_repo_fixture(repo)
    canonical = tmp_path / "canonical.parquet"
    _, built = _build_canonical(panel_path, ohlcv, tmp_path / "real.parquet")
    _write(built.drop(columns=list(mod.SENTIMENT_COLUMNS)), canonical)
    with pytest.raises(mod.RawlabelValidationError, match="not the exact ordered"):
        mod._default_rawlabel_verify_fn()(canonical, panel_path, horizon=2)


def test_default_verify_refuses_177_col_missing_feature_file(tmp_path) -> None:
    # A 177-col file that KEEPS all three sentiment names but drops two other
    # required features — exactly the shape the old 3-name heuristic WRONGLY
    # certified. Refused by the exact ordered contract.
    pytest.importorskip("pandas")
    repo = _repo(tmp_path)
    panel_path, ohlcv, _ = _mk_real_repo_fixture(repo)
    canonical = tmp_path / "canonical.parquet"
    _, built = _build_canonical(panel_path, ohlcv, tmp_path / "real.parquet")
    missing_feature = built.drop(
        columns=[_NONSENTIMENT_FEATURE, _SECOND_NONSENTIMENT_FEATURE]
    )
    assert set(mod.SENTIMENT_COLUMNS) <= set(missing_feature.columns)  # sentiment kept
    assert missing_feature.shape[1] == 177
    _write(missing_feature, canonical)
    with pytest.raises(mod.RawlabelValidationError, match="not the exact ordered"):
        mod._default_rawlabel_verify_fn()(canonical, panel_path, horizon=2)


def test_default_verify_refuses_extra_junk_column_file(tmp_path) -> None:
    # An arbitrary extra column (180 cols) — the old heuristic ignored column
    # count and WRONGLY certified it. Refused by the exact ordered contract.
    pytest.importorskip("pandas")
    repo = _repo(tmp_path)
    panel_path, ohlcv, _ = _mk_real_repo_fixture(repo)
    canonical = tmp_path / "canonical.parquet"
    _, built = _build_canonical(panel_path, ohlcv, tmp_path / "real.parquet")
    junk = built.copy()
    junk["junk_extra_col"] = 1.0
    _write(junk, canonical)
    with pytest.raises(mod.RawlabelValidationError, match="not the exact ordered"):
        mod._default_rawlabel_verify_fn()(canonical, panel_path, horizon=2)


def test_default_verify_refuses_reordered_179_col_file(tmp_path) -> None:
    # Same 179 names, wrong ORDER — the old heuristic checked only membership and
    # WRONGLY certified it. Refused by the exact ordered contract (order matters).
    pytest.importorskip("pandas")
    repo = _repo(tmp_path)
    panel_path, ohlcv, _ = _mk_real_repo_fixture(repo)
    canonical = tmp_path / "canonical.parquet"
    _, built = _build_canonical(panel_path, ohlcv, tmp_path / "real.parquet")
    reordered = built[list(built.columns[::-1])]  # reverse column order
    assert set(reordered.columns) == set(built.columns)  # same names, wrong order
    _write(reordered, canonical)
    with pytest.raises(mod.RawlabelValidationError, match="reordered"):
        mod._default_rawlabel_verify_fn()(canonical, panel_path, horizon=2)


def test_default_verify_refuses_bar_frontier_extension_row(tmp_path) -> None:
    # A 179-col file carrying ONE bar-frontier extension row: a key-only row whose
    # entire feature vector is NaN. Its (ticker,date) key IS in the panel, so
    # lockstep passes — proving the extension check is INTRINSIC (row-domain
    # semantics), exactly the row-class the canonical recipe DROPS (§2.3). REFUSED.
    pytest.importorskip("pandas")
    import numpy as np  # noqa: PLC0415

    repo = _repo(tmp_path)
    panel_path, ohlcv, _ = _mk_real_repo_fixture(repo)
    canonical = tmp_path / "canonical.parquet"
    _, built = _build_canonical(panel_path, ohlcv, tmp_path / "real.parquet")
    ext = built.copy()
    feat = [c for c in ext.columns if c not in ("ticker", "date", mod.RAWLABEL_COLUMN)]
    ext.loc[ext.index[0], feat] = np.nan  # key stays in-lockstep; every feature NaN
    _write(ext, canonical)
    with pytest.raises(mod.RawlabelValidationError, match="extension row"):
        mod._default_rawlabel_verify_fn()(canonical, panel_path, horizon=2)


def test_default_verify_rejects_all_nan_label(tmp_path) -> None:
    pytest.importorskip("pandas")
    import numpy as np  # noqa: PLC0415

    repo = _repo(tmp_path)
    panel_path, ohlcv, _ = _mk_real_repo_fixture(repo)
    canonical = tmp_path / "canonical.parquet"
    _, built = _build_canonical(panel_path, ohlcv, tmp_path / "real.parquet")
    nan_label = built.copy()
    nan_label[mod.RAWLABEL_COLUMN] = np.nan  # features finite; label all NaN
    _write(nan_label, canonical)
    with pytest.raises(mod.RawlabelValidationError, match="finite-label fraction"):
        mod._default_rawlabel_verify_fn()(canonical, panel_path, horizon=2)


def test_default_verify_counts_inf_as_non_finite(tmp_path) -> None:
    pytest.importorskip("pandas")
    import numpy as np  # noqa: PLC0415

    repo = _repo(tmp_path)
    panel_path, ohlcv, _ = _mk_real_repo_fixture(repo)
    canonical = tmp_path / "canonical.parquet"
    _, built = _build_canonical(panel_path, ohlcv, tmp_path / "real.parquet")
    inf_label = built.copy()
    inf_label[mod.RAWLABEL_COLUMN] = np.inf  # all ±inf → non-finite
    _write(inf_label, canonical)
    with pytest.raises(mod.RawlabelValidationError, match="finite-label fraction"):
        mod._default_rawlabel_verify_fn()(canonical, panel_path, horizon=2)


# ──────────── task end-to-end on the DEFAULT consume + verify path ───────────


def test_task_consumes_default_verify_end_to_end(tmp_path, monkeypatch) -> None:
    """Prove the DEFAULT (non-injected) consume + verify path: a canonical file
    published upstream is verified in-lockstep and certified (provenance + digest,
    receipt cleared) WITHOUT mutating the corpus. No production write."""
    pd = pytest.importorskip("pandas")
    monkeypatch.setattr(mod, "post_ntfy", lambda *a, **k: None)
    repo = _repo(tmp_path)
    panel_path, ohlcv, _ = _mk_real_repo_fixture(repo)
    canonical = repo / "data" / mod.DEFAULT_RAWLABEL_FILENAME
    _build_canonical(panel_path, ohlcv, canonical)  # the sole writer's upstream output
    before = canonical.read_bytes()
    # a stale receipt from a prior failed run must be cleared by a good consume
    mod._write_invalidation_receipt(canonical, reason="prior failure", panel_in=panel_path, horizon=2)

    ctx = _ctx(repo, rawlabel_horizon=2)  # verify_fn DEFAULT
    assert mod.RefreshSigmaHeadRawLabelTask().run(ctx) is True

    assert ctx.rawlabel_refresh_summary["status"] == "verified"
    # read-only: the consumed corpus bytes are unchanged
    assert canonical.read_bytes() == before
    # provenance stamped, receipt cleared, corpus admissible
    prov = json.loads(mod.rawlabel_provenance_path(canonical).read_text())
    assert prov["horizon"] == 2 and prov["n_tickers"] == 2
    assert prov["source_panel_sha256"].startswith("sha256:")
    # the OUTPUT digest binds the consumed corpus (#427 contract).
    assert prov["rawlabel_sha256"] == mod._sha256_file(canonical)
    assert prov["schema_version"] == mod.RAWLABEL_PROVENANCE_SCHEMA_VERSION
    assert not mod.rawlabel_receipt_path(canonical).exists()
    assert mod.is_rawlabel_admissible(canonical) is True


def test_task_rejects_invalid_canonical_and_writes_receipt(tmp_path, monkeypatch) -> None:
    """A canonical file the sole writer left that fails verification (here: a
    2-column ticker/date file that is not the exact ordered 179 contract) must
    NOT be certified: it is left untouched, an invalidation receipt is written,
    downstream admission blocked."""
    pd = pytest.importorskip("pandas")
    monkeypatch.setattr(mod, "post_ntfy", lambda *a, **k: None)
    repo = _repo(tmp_path)
    panel_path, _ohlcv, _ = _mk_real_repo_fixture(repo)
    canonical = repo / "data" / mod.DEFAULT_RAWLABEL_FILENAME
    # a 2-column ticker/date file → NOT the exact ordered 179 contract → REFUSED
    pd.read_parquet(panel_path, columns=["ticker", "date"]).to_parquet(canonical, index=False)
    before = canonical.read_bytes()

    ctx = _ctx(repo)  # DEFAULT verifier
    assert mod.RefreshSigmaHeadRawLabelTask().run(ctx) is True
    assert ctx.rawlabel_refresh_summary["status"] == "failed"
    assert "not the exact ordered" in ctx.rawlabel_refresh_summary["error"]
    # the corpus is untouched (read-only); downstream blocked
    assert canonical.read_bytes() == before
    assert mod.rawlabel_receipt_path(canonical).exists()
    assert mod.is_rawlabel_admissible(canonical) is False


# ─────────────────── downstream admission enforcement ───────────────────────


def test_admission_helpers_gate_a_stale_corpus(tmp_path) -> None:
    repo = _repo(tmp_path)
    corpus = repo / "data" / mod.DEFAULT_RAWLABEL_FILENAME

    # missing corpus → inadmissible
    assert mod.is_rawlabel_admissible(corpus) is False
    with pytest.raises(mod.RawlabelStaleError, match="missing"):
        mod.assert_rawlabel_admissible(corpus)

    # present + no receipt → admissible
    corpus.write_bytes(b"CORPUS")
    assert mod.is_rawlabel_admissible(corpus) is True
    mod.assert_rawlabel_admissible(corpus)  # no raise

    # receipt present → inadmissible, and the reason is surfaced
    mod._write_invalidation_receipt(corpus, reason="consume failed", panel_in=repo / "p", horizon=60)
    assert mod.is_rawlabel_admissible(corpus) is False
    with pytest.raises(mod.RawlabelStaleError, match="consume failed"):
        mod.assert_rawlabel_admissible(corpus)


# ────── rawlabel_sha256 / schema_version / publication-ordering safety ──────
# Codex #218/#427 review: the success provenance must record a digest of the
# CORPUS itself (the OUTPUT #427 admits), not merely the input. Under the
# single-writer amendment the corpus is written upstream by the sole base-data
# writer; this task certifies the CONSUMED bytes — the digest still binds the
# actual on-disk corpus, so a later out-of-band edit is detectable.


def test_provenance_records_rawlabel_sha256_of_consumed_bytes(tmp_path) -> None:
    """The provenance sidecar's rawlabel_sha256 must be the digest of the ACTUAL
    on-disk CONSUMED corpus, not merely echoed from whatever the (possibly
    opaque/mocked) verifier returned."""
    repo = _repo(tmp_path)
    _write_panel(repo)
    canonical = _write_canonical(repo, b"REAL-PUBLISHED-BYTES")

    # the verifier deliberately returns NO rawlabel_sha256 — the TASK must
    # compute it itself from the consumed file, not trust an injected value.
    ctx = _ctx(repo, rawlabel_verify_fn=_passthru_verify())
    assert mod.RefreshSigmaHeadRawLabelTask().run(ctx) is True

    prov = json.loads(mod.rawlabel_provenance_path(canonical).read_text())
    assert prov["rawlabel_sha256"] == mod._sha256_file(canonical)
    # sanity: the digest genuinely reflects content, not a placeholder
    import hashlib

    assert prov["rawlabel_sha256"] == "sha256:" + hashlib.sha256(b"REAL-PUBLISHED-BYTES").hexdigest()
    assert prov["schema_version"] == mod.RAWLABEL_PROVENANCE_SCHEMA_VERSION == 1


def test_a_later_corpus_edit_is_detectable_via_digest_mismatch(tmp_path) -> None:
    """After a certified consume, if the corpus bytes are later replaced/edited
    while the sidecar is left intact, the sidecar's recorded rawlabel_sha256 no
    longer matches on-disk — exactly the signal RenQuant PR #427's consumer
    checks to fail closed."""
    repo = _repo(tmp_path)
    _write_panel(repo)
    canonical = _write_canonical(repo, b"ORIGINAL-CERTIFIED-BYTES")

    ctx = _ctx(repo, rawlabel_verify_fn=_passthru_verify())
    assert mod.RefreshSigmaHeadRawLabelTask().run(ctx) is True

    prov_path = mod.rawlabel_provenance_path(canonical)
    recorded_digest = json.loads(prov_path.read_text())["rawlabel_sha256"]
    assert recorded_digest == mod._sha256_file(canonical)

    # Simulate a later out-of-band replacement of the corpus (bytes changed),
    # sidecar left untouched — the exact tamper scenario the review flagged.
    canonical.write_bytes(b"TAMPERED-BYTES-NEVER-CERTIFIED")

    still_recorded = json.loads(prov_path.read_text())["rawlabel_sha256"]
    assert still_recorded == recorded_digest  # sidecar unchanged
    assert mod._sha256_file(canonical) != still_recorded  # but the actual bytes no longer match


def test_provenance_write_failure_after_certify_still_invalidates(tmp_path, monkeypatch) -> None:
    """If stamping the provenance sidecar fails (e.g. disk full) AFTER the corpus
    has been verified, the corpus must not be left looking silently certified —
    the exception handling writes an INVALIDATION RECEIPT so admission fails
    closed. (The consumed corpus is read-only and remains intact.)"""
    repo = _repo(tmp_path)
    _write_panel(repo)
    canonical = _write_canonical(repo, b"CANONICAL-BYTES")
    before = canonical.read_bytes()

    def boom_write_provenance(rawlabel_path, report):
        raise OSError("disk full while stamping provenance")

    monkeypatch.setattr(mod, "_write_rawlabel_provenance", boom_write_provenance)
    monkeypatch.setattr(mod, "post_ntfy", lambda *a, **k: None)

    ctx = _ctx(repo, rawlabel_verify_fn=_passthru_verify())
    assert mod.RefreshSigmaHeadRawLabelTask().run(ctx) is True

    # the consumed corpus is untouched (read-only) ...
    assert canonical.read_bytes() == before
    # ... but since its provenance could not be stamped, the task must not report
    # success and must invalidate it.
    assert ctx.rawlabel_refresh_summary["status"] == "failed"
    assert ctx.rawlabel_refresh_summary["receipt_written"] is True
    assert mod.is_rawlabel_admissible(canonical) is False
    with pytest.raises(mod.RawlabelStaleError):
        mod.assert_rawlabel_admissible(canonical)


def test_provenance_sidecar_write_is_atomic_no_torn_file(tmp_path) -> None:
    """The provenance sidecar is written via temp-file + fsync + os.replace, so a
    reader can never observe a partially-written / truncated JSON. No ``.tmp``
    sibling is left behind after a successful stamp and the final file is valid,
    complete JSON."""
    repo = _repo(tmp_path)
    final = repo / "data" / mod.DEFAULT_RAWLABEL_FILENAME
    final.parent.mkdir(parents=True, exist_ok=True)
    final.write_bytes(b"CORPUS-BYTES")

    report = {
        "n_rows": 5,
        "n_tickers": 2,
        "finite_fraction": 1.0,
        "horizon": 60,
        "source_panel_sha256": "sha256:" + "a" * 64,
        "source_panel_frontier": "2026-06-01",
        "rawlabel_sha256": mod._sha256_file(final),
    }
    prov_path = mod._write_rawlabel_provenance(final, report)

    assert prov_path.exists()
    tmp_sibling = prov_path.with_name(prov_path.name + ".tmp")
    assert not tmp_sibling.exists()
    payload = json.loads(prov_path.read_text())  # must parse cleanly (no torn write)
    assert payload["n_rows"] == 5
    assert payload["rawlabel_sha256"] == report["rawlabel_sha256"]
    assert payload["schema_version"] == mod.RAWLABEL_PROVENANCE_SCHEMA_VERSION
