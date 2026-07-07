"""Tests for the σ-head (QuantileHead) RAW ``_rawlabel`` refresh task.

fix #1 from the training-data investigation: the derived
``alpha158_291_fundamental_dataset_rawlabel.parquet`` had no retrain cadence and
drifted behind the ranker panel (stuck at 2026-02-11 while its source panel was
already fresh). This task rebuilds it in lockstep right after the fund-panel
merge. It must:

- run AFTER the panel build and be wired into the pipeline,
- read the fresh panel + build to a staging sibling, then atomically swap in
  (non-destructive: a pre-existing ``_rawlabel`` survives a failed build),
- isolate any failure (alert + log, NEVER abort the ranker retrain),
- soft-skip a missing upstream panel without a false alert.

Per the constraints the build callable is dependency-injected so NO real
``build_raw_fwd60d_label.py`` runs and NO production ``_rawlabel`` parquet is
written here. The one test that exercises the default builder does so purely on
tmp parquet fixtures.
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
    the injected build + validate callables never read it in the mock tests."""
    p = repo / "data" / mod.DEFAULT_PANEL_FILENAME
    p.write_bytes(b"PANEL")
    return p


def _passthru_validate(report: dict | None = None):
    """A stand-in validator for wiring tests that use opaque staging bytes (the
    real validator is exercised on real parquet fixtures separately)."""

    def _v(staging, panel_in, horizon):
        return report or {"n_rows": 1, "n_tickers": 1, "finite_fraction": 1.0, "horizon": horizon}

    return _v


# ─────────────────────────── wiring / ordering ─────────────────────────────


def test_sigma_head_task_wired_after_fund_panel_merge() -> None:
    names = [type(t).__name__ for t in mod.build_pipeline().jobs[0].tasks]
    assert "RefreshSigmaHeadRawLabelTask" in names
    # runs immediately after the fund-panel merge (its fresh source) ...
    assert (
        names.index("RefreshSigmaHeadRawLabelTask")
        == names.index("MergeFundFeaturesTask") + 1
    )
    # ... and before the ranker training (it is an independent downstream step).
    assert names.index("RefreshSigmaHeadRawLabelTask") < names.index("TrainGbdtScorerTask")


# ─────────────────────────── refresh happy path ────────────────────────────


def test_refresh_builds_to_staging_then_atomically_swaps(tmp_path) -> None:
    repo = _repo(tmp_path)
    panel = _write_panel(repo)
    calls: dict = {}

    def fake_build(panel_in, panel_out, ohlcv_dir, horizon):
        calls.update(
            panel_in=panel_in, panel_out=panel_out, ohlcv_dir=ohlcv_dir, horizon=horizon
        )
        # a real builder writes ONLY to the staging path handed to it
        Path(panel_out).write_bytes(b"RAWLABEL")

    ctx = _ctx(
        repo,
        rawlabel_build_fn=fake_build,
        rawlabel_validate_fn=_passthru_validate({"n_rows": 3, "n_tickers": 2, "finite_fraction": 0.9, "horizon": 60}),
    )
    assert mod.RefreshSigmaHeadRawLabelTask().run(ctx) is True

    final = repo / "data" / mod.DEFAULT_RAWLABEL_FILENAME
    staging = final.with_name(final.name + ".staging")
    # lockstep: builder reads the fresh panel, writes the staging sibling
    assert calls["panel_in"] == ctx.panel_path == panel
    assert calls["panel_out"] == staging
    assert calls["ohlcv_dir"] == ctx.ohlcv_dir
    assert calls["horizon"] == mod.DEFAULT_RAWLABEL_HORIZON
    # non-destructive swap: staging consumed, final in place
    assert final.read_bytes() == b"RAWLABEL"
    assert not staging.exists()
    assert ctx.rawlabel_refresh_summary["status"] == "refreshed"
    # a validated swap stamps provenance and leaves NO invalidation receipt
    prov = mod.rawlabel_provenance_path(final)
    assert prov.exists()
    prov_payload = json.loads(prov.read_text())
    assert prov_payload["n_rows"] == 3
    # the provenance binds the PUBLISHED corpus to its own digest — the fix
    # for the Codex #218/#427 gap where only the INPUT (source_panel_sha256)
    # was recorded, not the OUTPUT this task actually publishes.
    assert prov_payload["rawlabel_sha256"] == mod._sha256_file(final)
    assert prov_payload["schema_version"] == mod.RAWLABEL_PROVENANCE_SCHEMA_VERSION
    assert not mod.rawlabel_receipt_path(final).exists()
    assert mod.is_rawlabel_admissible(final) is True


def test_refresh_clears_a_stale_staging_before_building(tmp_path) -> None:
    repo = _repo(tmp_path)
    _write_panel(repo)
    final = repo / "data" / mod.DEFAULT_RAWLABEL_FILENAME
    staging = final.with_name(final.name + ".staging")
    staging.write_bytes(b"STALE-PARTIAL")  # leftover from a prior aborted run

    def fake_build(panel_in, panel_out, ohlcv_dir, horizon):
        assert not Path(panel_out).exists()  # stale staging was cleared first
        Path(panel_out).write_bytes(b"FRESH")

    ctx = _ctx(repo, rawlabel_build_fn=fake_build, rawlabel_validate_fn=_passthru_validate())
    assert mod.RefreshSigmaHeadRawLabelTask().run(ctx) is True
    assert final.read_bytes() == b"FRESH"


# ─────────────────────────── failure isolation ─────────────────────────────


def test_build_failure_is_isolated_and_alerts(tmp_path, monkeypatch) -> None:
    repo = _repo(tmp_path)
    _write_panel(repo)
    final = repo / "data" / mod.DEFAULT_RAWLABEL_FILENAME
    final.write_bytes(b"OLD")  # a pre-existing _rawlabel must NOT be clobbered

    alerts: list = []
    monkeypatch.setattr(
        mod, "post_ntfy", lambda title, body, topic: alerts.append((title, body, topic))
    )

    def boom(panel_in, panel_out, ohlcv_dir, horizon):
        raise RuntimeError("build blew up")

    ctx = _ctx(repo, rawlabel_build_fn=boom)
    # NEVER raises — the ranker retrain must continue
    assert mod.RefreshSigmaHeadRawLabelTask().run(ctx) is True
    assert ctx.rawlabel_refresh_summary["status"] == "failed"
    assert "build blew up" in ctx.rawlabel_refresh_summary["error"]
    # loud alert emitted
    assert alerts and alerts[0][0] == "RenQuant retrain SIGMA-HEAD-RAWLABEL"
    # non-destructive: prior artifact preserved, no half-written staging remains
    assert final.read_bytes() == b"OLD"
    assert not final.with_name(final.name + ".staging").exists()
    # a swallowed failure is NOT fail-open: a durable invalidation receipt is
    # written so downstream admission BLOCKS the stale corpus.
    receipt = mod.rawlabel_receipt_path(final)
    assert ctx.rawlabel_refresh_summary["receipt_written"] is True
    assert receipt.exists()
    assert "build blew up" in json.loads(receipt.read_text())["reason"]
    assert mod.is_rawlabel_admissible(final) is False
    with pytest.raises(mod.RawlabelStaleError):
        mod.assert_rawlabel_admissible(final)


def test_build_failure_is_silent_when_quiet(tmp_path, monkeypatch) -> None:
    repo = _repo(tmp_path)
    _write_panel(repo)
    alerts: list = []
    monkeypatch.setattr(mod, "post_ntfy", lambda *a, **k: alerts.append(a))

    def boom(*a, **k):
        raise RuntimeError("nope")

    ctx = _ctx(repo, rawlabel_build_fn=boom, quiet=True)
    assert mod.RefreshSigmaHeadRawLabelTask().run(ctx) is True
    assert ctx.rawlabel_refresh_summary["status"] == "failed"
    assert not alerts  # quiet suppresses the ntfy


def test_empty_build_output_is_treated_as_failure(tmp_path, monkeypatch) -> None:
    repo = _repo(tmp_path)
    _write_panel(repo)
    monkeypatch.setattr(mod, "post_ntfy", lambda *a, **k: None)

    # builder returns without writing the staging file → treated as a failure,
    # not silently swapped as a "success"
    ctx = _ctx(repo, rawlabel_build_fn=lambda *a, **k: None)
    assert mod.RefreshSigmaHeadRawLabelTask().run(ctx) is True
    assert ctx.rawlabel_refresh_summary["status"] == "failed"
    final = repo / "data" / mod.DEFAULT_RAWLABEL_FILENAME
    assert not final.exists()
    # no output ⇒ receipt written ⇒ downstream corpus (absent here) is inadmissible
    assert mod.rawlabel_receipt_path(final).exists()
    assert mod.is_rawlabel_admissible(final) is False


# ─────────────────────────── skip paths ────────────────────────────────────


def test_missing_panel_soft_skips_without_alert(tmp_path, monkeypatch) -> None:
    repo = _repo(tmp_path)  # no panel written
    alerts: list = []
    monkeypatch.setattr(mod, "post_ntfy", lambda *a, **k: alerts.append(a))
    called: list = []
    ctx = _ctx(repo, rawlabel_build_fn=lambda *a, **k: called.append(a))

    assert mod.RefreshSigmaHeadRawLabelTask().run(ctx) is True
    assert ctx.rawlabel_refresh_summary["status"] == "skipped-no-panel"
    assert not called  # builder never invoked
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
    called: list = []
    ctx = _ctx(repo, refresh_rawlabel=False, rawlabel_build_fn=lambda *a, **k: called.append(a))
    assert mod.RefreshSigmaHeadRawLabelTask().run(ctx) is True
    assert ctx.rawlabel_refresh_summary["status"] == "skipped"
    assert not called


def test_dry_run_does_not_build(tmp_path) -> None:
    repo = _repo(tmp_path)
    _write_panel(repo)
    called: list = []
    ctx = _ctx(repo, dry_run=True, rawlabel_build_fn=lambda *a, **k: called.append(a))
    assert mod.RefreshSigmaHeadRawLabelTask().run(ctx) is True
    assert ctx.rawlabel_refresh_summary["status"] == "dry-run"
    assert not called
    assert not (repo / "data" / mod.DEFAULT_RAWLABEL_FILENAME).exists()


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

    def boom(*a, **k):
        raise RuntimeError("sigma head down")

    # Feed the (now fail-closed, #217) OHLCV-refresh + freshness guard a passing
    # setup — explicit universe, fresh injected bars, and an independently pinned
    # expected session + gap fn — so the pipeline actually REACHES the σ-head task.
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
        rawlabel_build_fn=boom,
        panel_universe=["AAA", "BBB"],
        fetch_fn=fake_fetch,
        expected_session=frontier,
        session_gap_fn=lambda a, b: max((b - a).days, 0),
    )

    result = mod.build_pipeline().run(ctx)

    # the ranker retrain still succeeds despite the σ-head failure
    assert result.ok is True
    assert ctx.rawlabel_refresh_summary["status"] == "failed"
    assert ctx.rawlabel_refresh_summary["receipt_written"] is True
    assert scorer.exists() and calibrator.exists()


# ───────────── default builder (tmp parquet fixtures only) ──────────────────


def test_default_build_fn_computes_raw_excess_on_tmp_fixtures(tmp_path) -> None:
    """Exercise the injected default builder on TINY tmp parquet fixtures — this
    is the orchestrator's own path-parametrized port, NOT the real
    ``build_raw_fwd60d_label.py`` and it writes only under tmp_path."""
    pd = pytest.importorskip("pandas")
    import numpy as np  # noqa: PLC0415

    ohlcv_dir = tmp_path / "ohlcv"
    dates = pd.bdate_range("2026-01-01", periods=6)

    def _save(sym: str, closes: list[float]) -> None:
        d = ohlcv_dir / sym
        d.mkdir(parents=True)
        frame = pd.DataFrame({"close": closes}, index=dates)
        frame.to_parquet(d / "1d.parquet")

    _save("SPY", [100, 101, 102, 103, 104, 105])
    _save("AAA", [10, 11, 12, 13, 14, 15])
    # "ZZZ" deliberately has NO ohlcv → its raw label must be NaN

    panel = pd.DataFrame(
        {"date": [dates[0], dates[1], dates[0]], "ticker": ["AAA", "AAA", "ZZZ"]}
    )
    panel_in = tmp_path / mod.DEFAULT_PANEL_FILENAME
    panel.to_parquet(panel_in, index=False)
    panel_out = tmp_path / (mod.DEFAULT_RAWLABEL_FILENAME + ".staging")

    build = mod._default_rawlabel_build_fn()
    build(panel_in, panel_out, ohlcv_dir, horizon=2)

    assert panel_out.exists()  # writes to the exact (staging) path it was given
    out = pd.read_parquet(panel_out)
    assert "fwd_60d_excess_raw" in out.columns
    aaa_d0 = out[(out["ticker"] == "AAA") & (out["date"] == dates[0])]["fwd_60d_excess_raw"].iloc[0]
    # AAA fwd-2d 12/10-1=0.20 minus SPY 102/100-1=0.02 → 0.18
    assert aaa_d0 == pytest.approx(0.18, abs=1e-9)
    zzz = out[out["ticker"] == "ZZZ"]["fwd_60d_excess_raw"]
    assert bool(np.isnan(zzz).all())


# ───────────── real fixtures: parquet builder + OHLCV helpers ───────────────


def _mk_ohlcv(ohlcv_dir: Path, sym: str, closes, dates) -> None:
    import pandas as pd  # noqa: PLC0415

    d = ohlcv_dir / sym
    d.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"close": list(closes)}, index=dates).to_parquet(d / "1d.parquet")


def _mk_real_repo_fixture(repo: Path, *, horizon: int = 2):
    """Write a real (tiny) fund panel + OHLCV under ``repo/data`` so the DEFAULT
    build + validate path runs end-to-end. Returns (panel_path, dates)."""
    import pandas as pd  # noqa: PLC0415

    data = repo / "data"
    ohlcv_dir = data / "ohlcv"
    dates = pd.bdate_range("2026-01-01", periods=8)
    _mk_ohlcv(ohlcv_dir, "SPY", [100, 101, 102, 103, 104, 105, 106, 107], dates)
    _mk_ohlcv(ohlcv_dir, "AAA", [10, 11, 12, 13, 14, 15, 16, 17], dates)
    _mk_ohlcv(ohlcv_dir, "BBB", [50, 49, 48, 47, 46, 45, 44, 43], dates)
    panel = pd.DataFrame(
        {
            "date": list(dates[:4]) * 2,
            "ticker": ["AAA"] * 4 + ["BBB"] * 4,
            "fwd_60d_excess": 0.0,  # z-scored column the ranker uses; carried through
        }
    )
    panel_path = data / mod.DEFAULT_PANEL_FILENAME
    panel.to_parquet(panel_path, index=False)
    return panel_path, dates


def _mk_staging_parquet(path: Path, panel_path: Path, *, label_fn=None) -> None:
    """Write a staged _rawlabel parquet whose (ticker,date) coverage matches the
    panel; ``label_fn(i)`` overrides the label per row when given."""
    import pandas as pd  # noqa: PLC0415

    panel = pd.read_parquet(panel_path, columns=["ticker", "date"]).copy()
    panel[mod.RAWLABEL_COLUMN] = [
        (label_fn(i) if label_fn else 0.01) for i in range(len(panel))
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(path, index=False)


# ─────────────── default pre-swap validator (real parquet) ──────────────────


def test_default_validate_accepts_a_well_formed_staging(tmp_path) -> None:
    pytest.importorskip("pandas")
    repo = _repo(tmp_path)
    panel_path, _ = _mk_real_repo_fixture(repo)
    staging = tmp_path / "staging.parquet"
    _mk_staging_parquet(staging, panel_path)

    report = mod._default_rawlabel_validate_fn()(staging, panel_path, horizon=2)
    assert report["n_rows"] == 8
    assert report["n_tickers"] == 2
    assert report["finite_fraction"] == pytest.approx(1.0)
    assert report["horizon"] == 2
    assert report["source_panel_sha256"].startswith("sha256:")
    assert report["source_panel_frontier"]  # ISO date string


def test_default_validate_rejects_missing_label_column(tmp_path) -> None:
    pd = pytest.importorskip("pandas")
    repo = _repo(tmp_path)
    panel_path, _ = _mk_real_repo_fixture(repo)
    staging = tmp_path / "staging.parquet"
    # drop the raw-label column → schema violation
    pd.read_parquet(panel_path, columns=["ticker", "date"]).to_parquet(staging, index=False)
    with pytest.raises(mod.RawlabelValidationError, match="missing required columns"):
        mod._default_rawlabel_validate_fn()(staging, panel_path, horizon=2)


def test_default_validate_rejects_empty_staging(tmp_path) -> None:
    pd = pytest.importorskip("pandas")
    repo = _repo(tmp_path)
    panel_path, _ = _mk_real_repo_fixture(repo)
    staging = tmp_path / "staging.parquet"
    pd.DataFrame({"ticker": [], "date": [], mod.RAWLABEL_COLUMN: []}).to_parquet(staging, index=False)
    with pytest.raises(mod.RawlabelValidationError, match="empty"):
        mod._default_rawlabel_validate_fn()(staging, panel_path, horizon=2)


def test_default_validate_rejects_duplicate_keys(tmp_path) -> None:
    pd = pytest.importorskip("pandas")
    repo = _repo(tmp_path)
    panel_path, _ = _mk_real_repo_fixture(repo)
    staging = tmp_path / "staging.parquet"
    dup = pd.read_parquet(panel_path, columns=["ticker", "date"])
    dup[mod.RAWLABEL_COLUMN] = 0.01
    dup = pd.concat([dup, dup.iloc[[0]]], ignore_index=True)  # duplicate one (ticker,date)
    dup.to_parquet(staging, index=False)
    with pytest.raises(mod.RawlabelValidationError, match="duplicate"):
        mod._default_rawlabel_validate_fn()(staging, panel_path, horizon=2)


def test_default_validate_rejects_coverage_mismatch(tmp_path) -> None:
    pd = pytest.importorskip("pandas")
    repo = _repo(tmp_path)
    panel_path, _ = _mk_real_repo_fixture(repo)
    staging = tmp_path / "staging.parquet"
    short = pd.read_parquet(panel_path, columns=["ticker", "date"]).iloc[:5].copy()
    short[mod.RAWLABEL_COLUMN] = 0.01  # missing 3 of the panel's (ticker,date) rows
    short.to_parquet(staging, index=False)
    with pytest.raises(mod.RawlabelValidationError, match="coverage"):
        mod._default_rawlabel_validate_fn()(staging, panel_path, horizon=2)


def test_default_validate_rejects_future_dated_rows(tmp_path) -> None:
    pd = pytest.importorskip("pandas")
    repo = _repo(tmp_path)
    panel_path, dates = _mk_real_repo_fixture(repo)
    staging = tmp_path / "staging.parquet"
    frame = pd.read_parquet(panel_path, columns=["ticker", "date"]).copy()
    frame[mod.RAWLABEL_COLUMN] = 0.01
    # inject a row DATED BEYOND the panel frontier (a fabricated future key)
    future = pd.DataFrame({"ticker": ["AAA"], "date": [dates[7]], mod.RAWLABEL_COLUMN: [0.01]})
    pd.concat([frame, future], ignore_index=True).to_parquet(staging, index=False)
    with pytest.raises(mod.RawlabelValidationError, match="coverage"):
        mod._default_rawlabel_validate_fn()(staging, panel_path, horizon=2)


def test_default_validate_rejects_all_nan_label(tmp_path) -> None:
    pytest.importorskip("pandas")
    import numpy as np  # noqa: PLC0415

    repo = _repo(tmp_path)
    panel_path, _ = _mk_real_repo_fixture(repo)
    staging = tmp_path / "staging.parquet"
    _mk_staging_parquet(staging, panel_path, label_fn=lambda i: np.nan)
    with pytest.raises(mod.RawlabelValidationError, match="finite-label fraction"):
        mod._default_rawlabel_validate_fn()(staging, panel_path, horizon=2)


def test_default_validate_counts_inf_as_non_finite(tmp_path) -> None:
    pytest.importorskip("pandas")
    import numpy as np  # noqa: PLC0415

    repo = _repo(tmp_path)
    panel_path, _ = _mk_real_repo_fixture(repo)
    staging = tmp_path / "staging.parquet"
    _mk_staging_parquet(staging, panel_path, label_fn=lambda i: np.inf)  # all ±inf
    with pytest.raises(mod.RawlabelValidationError, match="finite-label fraction"):
        mod._default_rawlabel_validate_fn()(staging, panel_path, horizon=2)


# ──────────── task end-to-end on the DEFAULT build + validate path ───────────


def test_task_runs_default_build_and_validate_end_to_end(tmp_path, monkeypatch) -> None:
    """Prove the DEFAULT (non-injected) build + validate path: real tmp parquet
    in, validated corpus + provenance out, receipt cleared. No production write."""
    pd = pytest.importorskip("pandas")
    monkeypatch.setattr(mod, "post_ntfy", lambda *a, **k: None)
    repo = _repo(tmp_path)
    panel_path, _ = _mk_real_repo_fixture(repo, horizon=2)
    final = repo / "data" / mod.DEFAULT_RAWLABEL_FILENAME
    # a stale receipt from a prior failed run must be cleared by a good refresh
    mod._write_invalidation_receipt(final, reason="prior failure", panel_in=panel_path, horizon=2)

    ctx = _ctx(repo, rawlabel_horizon=2)  # build_fn / validate_fn both DEFAULT
    assert mod.RefreshSigmaHeadRawLabelTask().run(ctx) is True

    assert ctx.rawlabel_refresh_summary["status"] == "refreshed"
    assert final.exists()
    out = pd.read_parquet(final)
    assert mod.RAWLABEL_COLUMN in out.columns
    assert len(out) == 8
    # AAA fwd-2d 12/10-1=0.20 − SPY 102/100-1=0.02 → 0.18
    aaa0 = out[(out["ticker"] == "AAA") & (out["date"] == out["date"].min())][mod.RAWLABEL_COLUMN].iloc[0]
    assert aaa0 == pytest.approx(0.18, abs=1e-9)
    # provenance stamped, receipt cleared, corpus admissible, staging consumed
    prov = json.loads(mod.rawlabel_provenance_path(final).read_text())
    assert prov["horizon"] == 2 and prov["n_tickers"] == 2
    assert prov["source_panel_sha256"].startswith("sha256:")
    # the OUTPUT digest — closes the Codex #218/#427 gap (only the INPUT
    # digest was previously recorded).
    assert prov["rawlabel_sha256"] == mod._sha256_file(final)
    assert prov["schema_version"] == mod.RAWLABEL_PROVENANCE_SCHEMA_VERSION
    assert not mod.rawlabel_receipt_path(final).exists()
    assert mod.is_rawlabel_admissible(final) is True
    assert not final.with_name(final.name + ".staging").exists()


def test_task_rejects_invalid_build_and_keeps_prior_corpus(tmp_path, monkeypatch) -> None:
    """A build that writes a schema-invalid staging must NOT swap: prior corpus
    preserved, staging discarded, invalidation receipt written."""
    pd = pytest.importorskip("pandas")
    monkeypatch.setattr(mod, "post_ntfy", lambda *a, **k: None)
    repo = _repo(tmp_path)
    panel_path, _ = _mk_real_repo_fixture(repo)
    final = repo / "data" / mod.DEFAULT_RAWLABEL_FILENAME
    final.write_bytes(b"PRIOR-GOOD-CORPUS")

    def bad_build(panel_in, panel_out, ohlcv_dir, horizon):
        # drops the required raw-label column → real validator rejects it
        pd.read_parquet(panel_in, columns=["ticker", "date"]).to_parquet(panel_out, index=False)

    ctx = _ctx(repo, rawlabel_build_fn=bad_build)  # DEFAULT validator
    assert mod.RefreshSigmaHeadRawLabelTask().run(ctx) is True
    assert ctx.rawlabel_refresh_summary["status"] == "failed"
    assert "missing required columns" in ctx.rawlabel_refresh_summary["error"]
    # prior corpus untouched; rejected staging cleaned; downstream blocked
    assert final.read_bytes() == b"PRIOR-GOOD-CORPUS"
    assert not final.with_name(final.name + ".staging").exists()
    assert mod.rawlabel_receipt_path(final).exists()
    assert mod.is_rawlabel_admissible(final) is False


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
    mod._write_invalidation_receipt(corpus, reason="build blew up", panel_in=repo / "p", horizon=60)
    assert mod.is_rawlabel_admissible(corpus) is False
    with pytest.raises(mod.RawlabelStaleError, match="build blew up"):
        mod.assert_rawlabel_admissible(corpus)


# ────── rawlabel_sha256 / schema_version / publication-ordering safety ──────
# Codex #218/#427 review: the success provenance recorded source_panel_sha256
# (the INPUT) and horizon, but never a digest of the VALIDATED RAWLABEL
# CORPUS itself (the OUTPUT this task publishes) — so a later replacement /
# edit of the corpus with the sidecar left intact was indistinguishable from
# the originally-validated bytes, and the #427 consumer would wrongly admit
# it. These tests cover the producer half of the fix: the digest is present,
# correct, and stamped only after the corpus is durably published.


def test_provenance_records_rawlabel_sha256_of_published_bytes(tmp_path) -> None:
    """The provenance sidecar's rawlabel_sha256 must be the digest of the
    ACTUAL on-disk PUBLISHED corpus (post-swap), not merely echoed from
    whatever the (possibly opaque/mocked) validator returned."""
    repo = _repo(tmp_path)
    _write_panel(repo)

    def fake_build(panel_in, panel_out, ohlcv_dir, horizon):
        Path(panel_out).write_bytes(b"REAL-PUBLISHED-BYTES")

    # the validator deliberately returns NO rawlabel_sha256 — the TASK must
    # compute it itself from the published file, not trust an injected value.
    ctx = _ctx(repo, rawlabel_build_fn=fake_build, rawlabel_validate_fn=_passthru_validate())
    assert mod.RefreshSigmaHeadRawLabelTask().run(ctx) is True

    final = repo / "data" / mod.DEFAULT_RAWLABEL_FILENAME
    assert final.read_bytes() == b"REAL-PUBLISHED-BYTES"
    prov = json.loads(mod.rawlabel_provenance_path(final).read_text())
    assert prov["rawlabel_sha256"] == mod._sha256_file(final)
    # sanity: the digest genuinely reflects content, not a placeholder
    import hashlib

    assert prov["rawlabel_sha256"] == "sha256:" + hashlib.sha256(b"REAL-PUBLISHED-BYTES").hexdigest()
    assert prov["schema_version"] == mod.RAWLABEL_PROVENANCE_SCHEMA_VERSION == 1


def test_a_later_corpus_edit_is_detectable_via_digest_mismatch(tmp_path) -> None:
    """Prove the fix actually closes the gap: after a validated refresh, if
    the corpus bytes are later replaced/edited while the sidecar is left
    intact, the sidecar's recorded rawlabel_sha256 no longer matches the
    on-disk corpus — this is exactly the signal RenQuant PR #427's consumer
    checks to fail closed. (The #427 admission gate itself lives in the
    RenQuant repo; this proves the producer-side contract it depends on is
    load-bearing, not merely present.)"""
    repo = _repo(tmp_path)
    _write_panel(repo)

    def fake_build(panel_in, panel_out, ohlcv_dir, horizon):
        Path(panel_out).write_bytes(b"ORIGINAL-VALIDATED-BYTES")

    ctx = _ctx(repo, rawlabel_build_fn=fake_build, rawlabel_validate_fn=_passthru_validate())
    assert mod.RefreshSigmaHeadRawLabelTask().run(ctx) is True

    final = repo / "data" / mod.DEFAULT_RAWLABEL_FILENAME
    prov_path = mod.rawlabel_provenance_path(final)
    recorded_digest = json.loads(prov_path.read_text())["rawlabel_sha256"]
    assert recorded_digest == mod._sha256_file(final)

    # Simulate a later out-of-band replacement of the corpus (bytes changed),
    # sidecar left untouched — the exact tamper scenario the review flagged.
    final.write_bytes(b"TAMPERED-BYTES-NEVER-VALIDATED")

    still_recorded = json.loads(prov_path.read_text())["rawlabel_sha256"]
    assert still_recorded == recorded_digest  # sidecar unchanged (as the review posits)
    assert mod._sha256_file(final) != still_recorded  # but the actual bytes no longer match


def test_provenance_write_failure_after_swap_still_invalidates(tmp_path, monkeypatch) -> None:
    """Publication-ordering safety: the corpus swap (os.replace) and the
    provenance stamp are two separate operations. If writing the provenance
    sidecar itself fails (e.g. disk full) AFTER the corpus has already been
    durably published, the corpus must not be left looking silently valid —
    the existing exception handling must still catch it and write an
    INVALIDATION RECEIPT, so admission fails closed rather than the reader
    seeing a fresh corpus paired with a stale-or-absent sidecar."""
    repo = _repo(tmp_path)
    _write_panel(repo)
    final = repo / "data" / mod.DEFAULT_RAWLABEL_FILENAME

    def fake_build(panel_in, panel_out, ohlcv_dir, horizon):
        Path(panel_out).write_bytes(b"NEW-CORPUS-BYTES")

    def boom_write_provenance(rawlabel_path, report):
        raise OSError("disk full while stamping provenance")

    monkeypatch.setattr(mod, "_write_rawlabel_provenance", boom_write_provenance)
    monkeypatch.setattr(mod, "post_ntfy", lambda *a, **k: None)

    ctx = _ctx(repo, rawlabel_build_fn=fake_build, rawlabel_validate_fn=_passthru_validate())
    assert mod.RefreshSigmaHeadRawLabelTask().run(ctx) is True

    # the corpus WAS already swapped in (publication ordering: corpus first) ...
    assert final.read_bytes() == b"NEW-CORPUS-BYTES"
    # ... but since its provenance could not be stamped, the task must not
    # report success and must invalidate it: no reader can be misled into
    # trusting bytes that were never actually certified end-to-end.
    assert ctx.rawlabel_refresh_summary["status"] == "failed"
    assert ctx.rawlabel_refresh_summary["receipt_written"] is True
    assert mod.is_rawlabel_admissible(final) is False
    with pytest.raises(mod.RawlabelStaleError):
        mod.assert_rawlabel_admissible(final)


def test_provenance_sidecar_write_is_atomic_no_torn_file(tmp_path) -> None:
    """The provenance sidecar is written via temp-file + fsync + os.replace,
    not a direct in-place write — so a reader can never observe a
    partially-written / truncated provenance JSON. This test asserts no
    ``.tmp`` sibling is left behind after a successful stamp and the final
    file is valid, complete JSON."""
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


# ─────────── parity vs the canonical build_raw_fwd60d_label formula ──────────


def test_default_builder_parity_with_canonical_on_frozen_fixture(tmp_path) -> None:
    """The orchestrator's port must reproduce the canonical
    ``scripts/build_raw_fwd60d_label.py`` output bit-for-bit. We transcribe the
    canonical per-ticker loop (raw fwd_h return − SPY fwd_h return, trading-day
    shift, reindex on panel dates) and assert identical labels on a frozen
    fixture — data-parity, not a plumbing check."""
    pd = pytest.importorskip("pandas")
    import numpy as np  # noqa: PLC0415

    ohlcv_dir = tmp_path / "ohlcv"
    dates = pd.bdate_range("2026-01-01", periods=10)
    _mk_ohlcv(ohlcv_dir, "SPY", [100 + i for i in range(10)], dates)
    _mk_ohlcv(ohlcv_dir, "AAA", [10 + i for i in range(10)], dates)
    _mk_ohlcv(ohlcv_dir, "BBB", [80 - i for i in range(10)], dates)
    # CCC has NO ohlcv → canonical + port must both yield NaN
    panel = pd.DataFrame(
        {
            "date": list(dates[:6]) * 3,
            "ticker": ["AAA"] * 6 + ["BBB"] * 6 + ["CCC"] * 6,
        }
    )
    panel_in = tmp_path / mod.DEFAULT_PANEL_FILENAME
    panel.to_parquet(panel_in, index=False)

    HORIZON = 3

    def _canonical(panel_in: Path, ohlcv_dir: Path, horizon: int):
        # transcribed from scripts/build_raw_fwd60d_label.py:56-86
        panel = pd.read_parquet(panel_in)
        panel["date"] = pd.to_datetime(panel["date"])
        spy = pd.read_parquet(ohlcv_dir / "SPY" / "1d.parquet")
        spy.index = pd.to_datetime(spy.index)
        spy = spy["close"].sort_index()
        out_blocks = []
        for tkr, g in panel.groupby("ticker"):
            g = g.sort_values("date").reset_index(drop=True).copy()
            ohlcv_p = ohlcv_dir / tkr / "1d.parquet"
            if not ohlcv_p.exists():
                g["fwd_60d_excess_raw"] = np.nan
                out_blocks.append(g)
                continue
            ohlcv = pd.read_parquet(ohlcv_p)
            ohlcv.index = pd.to_datetime(ohlcv.index)
            close = ohlcv["close"].sort_index()
            ticker_fwd_ret = (close.shift(-horizon) / close - 1.0)
            spy_fwd_ret = (spy.shift(-horizon) / spy - 1.0)
            g_dates = g["date"].values
            excess = ticker_fwd_ret.reindex(g_dates).values - spy_fwd_ret.reindex(g_dates).values
            g["fwd_60d_excess_raw"] = excess
            out_blocks.append(g)
        return pd.concat(out_blocks, ignore_index=True)

    port_out = tmp_path / "port.parquet"
    mod._default_rawlabel_build_fn()(panel_in, port_out, ohlcv_dir, HORIZON)
    port = pd.read_parquet(port_out).sort_values(["ticker", "date"]).reset_index(drop=True)
    canon = _canonical(panel_in, ohlcv_dir, HORIZON).sort_values(["ticker", "date"]).reset_index(drop=True)

    assert list(port["ticker"]) == list(canon["ticker"])
    np.testing.assert_array_equal(
        pd.to_datetime(port["date"]).values, pd.to_datetime(canon["date"]).values
    )
    np.testing.assert_allclose(
        port[mod.RAWLABEL_COLUMN].to_numpy(dtype="float64"),
        canon[mod.RAWLABEL_COLUMN].to_numpy(dtype="float64"),
        rtol=0,
        atol=0,
        equal_nan=True,
    )
