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
    the injected build callable never reads it in the mock tests."""
    p = repo / "data" / mod.DEFAULT_PANEL_FILENAME
    p.write_bytes(b"PANEL")
    return p


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

    ctx = _ctx(repo, rawlabel_build_fn=fake_build)
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


def test_refresh_clears_a_stale_staging_before_building(tmp_path) -> None:
    repo = _repo(tmp_path)
    _write_panel(repo)
    final = repo / "data" / mod.DEFAULT_RAWLABEL_FILENAME
    staging = final.with_name(final.name + ".staging")
    staging.write_bytes(b"STALE-PARTIAL")  # leftover from a prior aborted run

    def fake_build(panel_in, panel_out, ohlcv_dir, horizon):
        assert not Path(panel_out).exists()  # stale staging was cleared first
        Path(panel_out).write_bytes(b"FRESH")

    ctx = _ctx(repo, rawlabel_build_fn=fake_build)
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
    assert not (repo / "data" / mod.DEFAULT_RAWLABEL_FILENAME).exists()


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

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    monkeypatch.setattr(mod, "post_ntfy", lambda *a, **k: None)

    def boom(*a, **k):
        raise RuntimeError("sigma head down")

    strategy_config = repo / "strategy_config.json"
    strategy_config.write_text("{}")
    ctx = mod.RetrainContext(
        repo_dir=repo,
        xgb_artifact_out=scorer,
        calibrator_out=calibrator,
        strategy_config_path=strategy_config,
        rawlabel_build_fn=boom,
    )

    result = mod.build_pipeline().run(ctx)

    # the ranker retrain still succeeds despite the σ-head failure
    assert result.ok is True
    assert ctx.rawlabel_refresh_summary["status"] == "failed"
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
