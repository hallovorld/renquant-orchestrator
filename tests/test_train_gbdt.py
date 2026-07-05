"""Tests for the GBDT panel-LTR training pipeline (train_gbdt).

Covers parse_args, _default_strategy_config, _production_fingerprint,
_Seq, SentimentGateTask, main, and _record_and_refresh — all without
real model training (subprocess / file I/O mocked throughout).
"""
from __future__ import annotations

import json
import sqlite3
import subprocess
import types
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from renquant_orchestrator import train_gbdt as mod


# ---------------------------------------------------------------------------
# parse_args
# ---------------------------------------------------------------------------

class TestParseArgs:
    def test_defaults(self):
        args = mod.parse_args([])
        assert args.data_dir is None
        assert args.output_path is None
        assert args.train_cutoff is None
        assert args.side_label is None
        assert args.label is None
        assert args.num_boost_round == mod.DEFAULT_N_ROUNDS
        assert args.cv_n_splits == 3
        assert args.cv_embargo_days == 60
        assert args.nthread is None
        assert args.strategy_config is None
        assert args.skip_sentiment_gate is False
        assert args.drop_sentiment is False
        assert args.exclude_features is None
        assert args.skip_cv is False
        assert args.training_window_years is None

    def test_all_flags(self):
        args = mod.parse_args([
            "--data-dir", "/d",
            "--output-path", "/o.json",
            "--train-cutoff", "2024-06-01",
            "--side-label", "wf",
            "--label", "fwd_20d",
            "--num-boost-round", "200",
            "--cv-n-splits", "5",
            "--cv-embargo-days", "30",
            "--nthread", "4",
            "--strategy-config", "/sc.json",
            "--skip-sentiment-gate",
            "--drop-sentiment",
            "--exclude-features", "a,b,c",
            "--skip-cv",
            "--training-window-years", "3.5",
        ])
        assert args.data_dir == "/d"
        assert args.output_path == "/o.json"
        assert args.train_cutoff == "2024-06-01"
        assert args.side_label == "wf"
        assert args.label == "fwd_20d"
        assert args.num_boost_round == 200
        assert args.cv_n_splits == 5
        assert args.cv_embargo_days == 30
        assert args.nthread == 4
        assert args.strategy_config == "/sc.json"
        assert args.skip_sentiment_gate is True
        assert args.drop_sentiment is True
        assert args.exclude_features == "a,b,c"
        assert args.skip_cv is True
        assert args.training_window_years == 3.5

    def test_strategy_config_none_literal(self):
        args = mod.parse_args(["--strategy-config", "none"])
        assert args.strategy_config == "none"

    def test_num_boost_round_type(self):
        args = mod.parse_args(["--num-boost-round", "50"])
        assert isinstance(args.num_boost_round, int)
        assert args.num_boost_round == 50


# ---------------------------------------------------------------------------
# _default_strategy_config
# ---------------------------------------------------------------------------

class TestDefaultStrategyConfig:
    def test_prefers_subrepo_config(self, tmp_path, monkeypatch):
        subrepo = tmp_path / "strategy_config.json"
        subrepo.write_text("{}")
        monkeypatch.setattr(mod, "DEFAULT_STRATEGY_CONFIG", subrepo)
        monkeypatch.setattr(mod, "LEGACY_STRATEGY_CONFIG", tmp_path / "legacy.json")
        assert mod._default_strategy_config() == subrepo

    def test_falls_back_to_legacy(self, tmp_path, monkeypatch):
        legacy = tmp_path / "legacy.json"
        legacy.write_text("{}")
        monkeypatch.setattr(mod, "DEFAULT_STRATEGY_CONFIG", tmp_path / "missing.json")
        monkeypatch.setattr(mod, "LEGACY_STRATEGY_CONFIG", legacy)
        assert mod._default_strategy_config() == legacy


# ---------------------------------------------------------------------------
# _production_fingerprint
# ---------------------------------------------------------------------------

class TestProductionFingerprint:
    def test_missing_config_returns_none(self, tmp_path):
        fp, fields = mod._production_fingerprint(tmp_path / "nope.json")
        assert fp is None
        assert fields is None

    def test_common_import_path(self, tmp_path, monkeypatch):
        config_path = tmp_path / "sc.json"
        cfg = {"model": {"param": 1}, "universe": ["A"]}
        config_path.write_text(json.dumps(cfg))

        fake_fp = MagicMock(return_value="sha256:abc")
        fake_mrf = MagicMock(return_value={"param": 1})

        # Patch the renquant_common import inside the function.
        fake_mod = types.ModuleType("renquant_common.config_consistency")
        fake_mod.fingerprint_config = fake_fp
        fake_mod._model_relevant_fields = fake_mrf
        monkeypatch.setitem(
            __import__("sys").modules,
            "renquant_common.config_consistency",
            fake_mod,
        )

        fp, fields = mod._production_fingerprint(config_path)
        assert fp == "sha256:abc"
        assert fields == {"param": 1}
        fake_fp.assert_called_once_with(cfg)
        fake_mrf.assert_called_once_with(cfg)

    def test_legacy_fallback_when_common_unavailable(self, tmp_path, monkeypatch):
        config_path = tmp_path / "sc.json"
        cfg = {"k": "v"}
        config_path.write_text(json.dumps(cfg))

        # Write a fake legacy module.
        legacy_path = tmp_path / "config_consistency.py"
        legacy_path.write_text(
            "def fingerprint_config(cfg): return 'sha256:legacy'\n"
            "def _model_relevant_fields(cfg): return {'legacy': True}\n"
        )
        monkeypatch.setattr(mod, "_LEGACY_CONFIG_CONSISTENCY", legacy_path)

        # Remove the common module from sys.modules so the import fails.
        import sys as _sys
        monkeypatch.delitem(_sys.modules, "renquant_common.config_consistency", raising=False)

        # Patch builtins import to fail for the common import.
        import builtins
        original_import = builtins.__import__

        def fail_import(name, *args, **kwargs):
            if name == "renquant_common.config_consistency":
                raise ImportError("no common")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fail_import)

        fp, fields = mod._production_fingerprint(config_path)
        assert fp == "sha256:legacy"
        assert fields == {"legacy": True}

    def test_no_fallback_returns_none(self, tmp_path, monkeypatch):
        config_path = tmp_path / "sc.json"
        config_path.write_text('{"x": 1}')

        import builtins
        import sys as _sys
        original_import = builtins.__import__

        def fail_import(name, *args, **kwargs):
            if name == "renquant_common.config_consistency":
                raise ImportError("no common")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fail_import)
        monkeypatch.delitem(_sys.modules, "renquant_common.config_consistency", raising=False)
        monkeypatch.setattr(mod, "_LEGACY_CONFIG_CONSISTENCY", tmp_path / "missing.py")

        fp, fields = mod._production_fingerprint(config_path)
        assert fp is None
        assert fields is None


# ---------------------------------------------------------------------------
# _Seq
# ---------------------------------------------------------------------------

class TestSeq:
    def test_tasks_property(self):
        tasks = [MagicMock(), MagicMock()]
        seq = mod._Seq(tasks)
        assert seq.tasks is tasks
        assert len(seq.tasks) == 2

    def test_empty_tasks(self):
        seq = mod._Seq([])
        assert seq.tasks == []


# ---------------------------------------------------------------------------
# _SENTIMENT_FEATURES constant
# ---------------------------------------------------------------------------

def test_sentiment_features_constant():
    assert mod._SENTIMENT_FEATURES == [
        "mean_sentiment", "n_articles_log", "sentiment_pos_share",
    ]


# ---------------------------------------------------------------------------
# main — validation guards
# ---------------------------------------------------------------------------

class TestMainValidation:
    """Tests for the error-checking at the top of main()."""

    def test_cutoff_requires_side_label(self, monkeypatch, tmp_path):
        monkeypatch.setattr(mod, "DEFAULT_DATA_DIR", tmp_path)
        with pytest.raises(SystemExit, match="--side-label is required"):
            mod.main(["--train-cutoff", "2024-01-01"])

    def test_cutoff_requires_walkforward_in_output_path(self, monkeypatch, tmp_path):
        monkeypatch.setattr(mod, "DEFAULT_DATA_DIR", tmp_path)
        with pytest.raises(SystemExit, match="walkforward"):
            mod.main([
                "--train-cutoff", "2024-01-01",
                "--side-label", "wf",
                "--output-path", str(tmp_path / "prod-model.json"),
            ])

    def test_cutoff_with_walkforward_path_accepted(self, monkeypatch, tmp_path):
        """A --train-cutoff with 'walkforward' in the output-path must NOT
        be rejected by the safety guard."""
        monkeypatch.setattr(mod, "DEFAULT_DATA_DIR", tmp_path)
        out = tmp_path / "walkforward" / "model.json"

        # Patch build_training_pipeline to avoid real training.
        fake_result = MagicMock()
        fake_result.ok = True
        fake_result.name = "fake"
        fake_result.elapsed_sec = 0.1
        fake_result.steps = []
        fake_pipeline = MagicMock()
        fake_pipeline.run.return_value = fake_result

        monkeypatch.setattr(mod, "build_training_pipeline", lambda: fake_pipeline)
        monkeypatch.setattr(mod, "_production_fingerprint", lambda p: (None, None))
        monkeypatch.setattr(mod, "_record_and_refresh", lambda *a, **kw: None)

        # Provide a ctx where artifact is None (no OOS IC log path).
        def side_effect(ctx):
            ctx.artifact = None
            ctx.feat_cols = ["a", "b"]
            return fake_result

        fake_pipeline.run.side_effect = side_effect

        rc = mod.main([
            "--train-cutoff", "2024-01-01",
            "--side-label", "wf",
            "--output-path", str(out),
            "--skip-sentiment-gate",
            "--strategy-config", "none",
        ])
        assert rc == 0


# ---------------------------------------------------------------------------
# main — pipeline assembly
# ---------------------------------------------------------------------------

class TestMainPipelineAssembly:
    """Verify that main() builds the right pipeline variant and wires the
    GbdtTrainingContext correctly."""

    @pytest.fixture()
    def _patch_env(self, monkeypatch, tmp_path):
        monkeypatch.setattr(mod, "DEFAULT_DATA_DIR", tmp_path / "data")
        (tmp_path / "data").mkdir()
        monkeypatch.setattr(mod, "_production_fingerprint", lambda p: ("sha256:test", {"k": 1}))
        monkeypatch.setattr(mod, "_record_and_refresh", lambda *a, **kw: None)
        return tmp_path

    def _fake_pipeline_run(self, ctx):
        ctx.artifact = {"oos_mean_ic": 0.05, "oos_per_fold_ic": [0.04, 0.05, 0.06]}
        ctx.feat_cols = ["f1", "f2", "f3"]
        result = MagicMock()
        result.ok = True
        result.name = "panel-gbdt-training"
        result.elapsed_sec = 1.0
        result.steps = []
        return result

    def test_skip_sentiment_gate_uses_model_pipeline(self, monkeypatch, _patch_env, tmp_path):
        captured = {}

        def fake_build():
            p = MagicMock()
            p.run.side_effect = self._fake_pipeline_run
            captured["pipeline"] = p
            return p

        monkeypatch.setattr(mod, "build_training_pipeline", fake_build)

        rc = mod.main([
            "--skip-sentiment-gate",
            "--strategy-config", "none",
        ])
        assert rc == 0
        assert "pipeline" in captured
        captured["pipeline"].run.assert_called_once()

    def test_drop_sentiment_implies_skip_gate(self, monkeypatch, _patch_env, tmp_path):
        captured_ctx = []

        def fake_build():
            p = MagicMock()
            def run_fn(ctx):
                captured_ctx.append(ctx)
                return self._fake_pipeline_run(ctx)
            p.run.side_effect = run_fn
            return p

        monkeypatch.setattr(mod, "build_training_pipeline", fake_build)

        rc = mod.main(["--drop-sentiment", "--strategy-config", "none"])
        assert rc == 0
        assert len(captured_ctx) == 1
        assert captured_ctx[0].exclude_features == list(mod._SENTIMENT_FEATURES)

    def test_exclude_features_combined_with_drop_sentiment(self, monkeypatch, _patch_env, tmp_path):
        captured_ctx = []

        def fake_build():
            p = MagicMock()
            def run_fn(ctx):
                captured_ctx.append(ctx)
                return self._fake_pipeline_run(ctx)
            p.run.side_effect = run_fn
            return p

        monkeypatch.setattr(mod, "build_training_pipeline", fake_build)

        rc = mod.main([
            "--drop-sentiment",
            "--exclude-features", "extra1,extra2",
            "--strategy-config", "none",
        ])
        assert rc == 0
        expected = list(mod._SENTIMENT_FEATURES) + ["extra1", "extra2"]
        assert captured_ctx[0].exclude_features == expected

    def test_nthread_sets_params(self, monkeypatch, _patch_env, tmp_path):
        captured_ctx = []

        def fake_build():
            p = MagicMock()
            def run_fn(ctx):
                captured_ctx.append(ctx)
                return self._fake_pipeline_run(ctx)
            p.run.side_effect = run_fn
            return p

        monkeypatch.setattr(mod, "build_training_pipeline", fake_build)

        rc = mod.main([
            "--nthread", "8",
            "--skip-sentiment-gate",
            "--strategy-config", "none",
        ])
        assert rc == 0
        assert captured_ctx[0].params["nthread"] == 8

    def test_strategy_config_none_skips_fingerprint(self, monkeypatch, _patch_env, tmp_path):
        captured_ctx = []

        def fake_build():
            p = MagicMock()
            def run_fn(ctx):
                captured_ctx.append(ctx)
                return self._fake_pipeline_run(ctx)
            p.run.side_effect = run_fn
            return p

        monkeypatch.setattr(mod, "build_training_pipeline", fake_build)
        # Override to verify _production_fingerprint is NOT called.
        fp_called = []
        monkeypatch.setattr(mod, "_production_fingerprint", lambda p: fp_called.append(1) or ("x", {}))

        rc = mod.main(["--strategy-config", "none", "--skip-sentiment-gate"])
        assert rc == 0
        assert fp_called == []
        assert captured_ctx[0].config_fingerprint is None

    def test_custom_label_and_rounds(self, monkeypatch, _patch_env, tmp_path):
        captured_ctx = []

        def fake_build():
            p = MagicMock()
            def run_fn(ctx):
                captured_ctx.append(ctx)
                return self._fake_pipeline_run(ctx)
            p.run.side_effect = run_fn
            return p

        monkeypatch.setattr(mod, "build_training_pipeline", fake_build)

        rc = mod.main([
            "--label", "fwd_20d",
            "--num-boost-round", "50",
            "--skip-sentiment-gate",
            "--strategy-config", "none",
        ])
        assert rc == 0
        assert captured_ctx[0].label == "fwd_20d"
        assert captured_ctx[0].num_boost_round == 50

    def test_sentiment_gate_pipeline_structure(self, monkeypatch, _patch_env, tmp_path):
        """When NOT skipping the sentiment gate, main() builds a Pipeline with
        _Seq(LoadPanel, SentimentGate, BuildNorm) + ModelTraining + ArtifactContract."""
        pipelines_created = []

        def capture_pipeline(jobs, **kwargs):
            p = MagicMock()
            p.run.side_effect = self._fake_pipeline_run
            pipelines_created.append(jobs)
            return p

        monkeypatch.setattr(mod, "Pipeline", capture_pipeline)

        # NOT passing --skip-sentiment-gate, so the sentiment gate pipeline is built.
        rc = mod.main(["--strategy-config", "none"])
        assert rc == 0
        assert len(pipelines_created) == 1
        jobs = pipelines_created[0]
        assert len(jobs) == 3
        # First job is _Seq with 3 tasks.
        assert isinstance(jobs[0], mod._Seq)
        task_types = [type(t).__name__ for t in jobs[0].tasks]
        assert task_types == ["LoadPanelTask", "SentimentGateTask", "BuildNormalizationTask"]
        assert type(jobs[1]).__name__ == "ModelTrainingJob"
        assert type(jobs[2]).__name__ == "ArtifactContractJob"


# ---------------------------------------------------------------------------
# _record_and_refresh
# ---------------------------------------------------------------------------

class TestRecordAndRefresh:

    @pytest.fixture()
    def _ctx_and_args(self, tmp_path):
        @dataclass
        class FakeCtx:
            artifact: dict = field(default_factory=lambda: {"oos_mean_ic": 0.04})
            feat_cols: list = field(default_factory=lambda: ["f1", "f2"])

        @dataclass
        class FakeArgs:
            output_path: str = str(tmp_path / "out.json")
            side_label: str = "wf"
            train_cutoff: str = "2024-06-01"
            training_window_years: float = 3.0

        return FakeCtx(), FakeArgs(), tmp_path

    def test_skips_when_db_missing(self, _ctx_and_args, monkeypatch):
        ctx, args, tmp_path = _ctx_and_args
        monkeypatch.delenv("RENQUANT_TRAINING_DB", raising=False)
        monkeypatch.delenv("RENQUANT_STRATEGY_DIR", raising=False)
        # Should complete without error when the DB does not exist.
        mod._record_and_refresh(ctx, args, elapsed_sec=1.0)

    def test_records_to_existing_db(self, _ctx_and_args, monkeypatch):
        ctx, args, tmp_path = _ctx_and_args
        db_path = tmp_path / "sim_runs.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE training_runs (id INTEGER PRIMARY KEY)")
        conn.close()

        monkeypatch.setenv("RENQUANT_TRAINING_DB", str(db_path))

        record_calls = []

        fake_persistence = types.ModuleType("renquant_pipeline.kernel.persistence")
        fake_persistence.record_training_run = lambda conn, **kw: record_calls.append(kw)
        monkeypatch.setitem(
            __import__("sys").modules,
            "renquant_pipeline.kernel.persistence",
            fake_persistence,
        )

        mod._record_and_refresh(ctx, args, elapsed_sec=2.5)

        assert len(record_calls) == 1
        assert record_calls[0]["artifact_type"] == "panel_ltr_xgboost"
        assert record_calls[0]["elapsed_sec"] == 2.5
        assert record_calls[0]["oos_mean_ic"] == 0.04
        assert record_calls[0]["n_features"] == 2

    def test_record_exception_is_non_fatal(self, _ctx_and_args, monkeypatch):
        ctx, args, tmp_path = _ctx_and_args
        db_path = tmp_path / "sim_runs.db"
        db_path.write_text("")

        monkeypatch.setenv("RENQUANT_TRAINING_DB", str(db_path))

        # Make the persistence import succeed but record_training_run raise.
        fake_persistence = types.ModuleType("renquant_pipeline.kernel.persistence")
        fake_persistence.record_training_run = MagicMock(side_effect=RuntimeError("boom"))
        monkeypatch.setitem(
            __import__("sys").modules,
            "renquant_pipeline.kernel.persistence",
            fake_persistence,
        )

        # Should NOT raise.
        mod._record_and_refresh(ctx, args, elapsed_sec=1.0)

    def test_strategy_dir_env_derives_db_path(self, _ctx_and_args, monkeypatch, tmp_path):
        ctx, args, _ = _ctx_and_args
        strat_dir = tmp_path / "umbrella" / "backtesting" / "renquant_104"
        strat_dir.mkdir(parents=True)
        data_dir = tmp_path / "umbrella" / "data"
        data_dir.mkdir(parents=True)
        db_path = data_dir / "sim_runs.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE training_runs (id INTEGER PRIMARY KEY)")
        conn.close()

        monkeypatch.setenv("RENQUANT_STRATEGY_DIR", str(strat_dir))
        monkeypatch.delenv("RENQUANT_TRAINING_DB", raising=False)

        record_calls = []
        fake_persistence = types.ModuleType("renquant_pipeline.kernel.persistence")
        fake_persistence.record_training_run = lambda conn, **kw: record_calls.append(kw)
        monkeypatch.setitem(
            __import__("sys").modules,
            "renquant_pipeline.kernel.persistence",
            fake_persistence,
        )

        mod._record_and_refresh(ctx, args, elapsed_sec=0.5)
        assert len(record_calls) == 1


# ---------------------------------------------------------------------------
# SentimentGateTask
# ---------------------------------------------------------------------------

class TestSentimentGateTask:
    def test_run_applies_gate_and_updates_ctx(self, monkeypatch):
        ctx = MagicMock()
        ctx.label = "fwd_60d_excess"
        ctx.feat_cols = ["f1", "f2", "mean_sentiment"]
        ctx.train = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=5),
            "f1": range(5),
        })
        ctx.extra_artifact_fields = {}

        # Mock the umbrella imports.
        fake_train_mod = types.ModuleType("scripts.train_production_model")
        fake_train_mod.build_fingerprint_config = MagicMock(return_value={"fp": True})
        fake_train_mod.build_sentiment_training_regime_map = MagicMock(return_value={"BULL": True})
        fake_train_mod.apply_sentiment_training_gate = MagicMock(
            return_value=(ctx.train, {
                "sentiment_runtime_gate_zeroed_rows": 2,
                "sentiment_runtime_gate_disabled_regimes": ["BEAR"],
            })
        )
        monkeypatch.setitem(
            __import__("sys").modules,
            "scripts.train_production_model",
            fake_train_mod,
        )

        task = mod.SentimentGateTask()
        result = task.run(ctx)

        assert result is True
        assert ctx.extra_artifact_fields["sentiment_runtime_gate_zeroed_rows"] == 2
        fake_train_mod.build_fingerprint_config.assert_called_once()
        fake_train_mod.build_sentiment_training_regime_map.assert_called_once()
        fake_train_mod.apply_sentiment_training_gate.assert_called_once()

    def test_run_with_no_contract(self, monkeypatch):
        ctx = MagicMock()
        ctx.label = "fwd_60d_excess"
        ctx.feat_cols = ["f1"]
        ctx.train = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=3),
        })
        ctx.extra_artifact_fields = {}

        fake_train_mod = types.ModuleType("scripts.train_production_model")
        fake_train_mod.build_fingerprint_config = MagicMock(return_value={})
        fake_train_mod.build_sentiment_training_regime_map = MagicMock(return_value={})
        fake_train_mod.apply_sentiment_training_gate = MagicMock(
            return_value=(ctx.train, None)
        )
        monkeypatch.setitem(
            __import__("sys").modules,
            "scripts.train_production_model",
            fake_train_mod,
        )

        task = mod.SentimentGateTask()
        result = task.run(ctx)

        assert result is True
        assert ctx.extra_artifact_fields == {}


# ---------------------------------------------------------------------------
# main — full happy-path (end-to-end with mocks)
# ---------------------------------------------------------------------------

class TestMainEndToEnd:
    def test_happy_path_returns_zero(self, monkeypatch, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        monkeypatch.setattr(mod, "DEFAULT_DATA_DIR", data_dir)
        monkeypatch.setattr(mod, "_production_fingerprint", lambda p: ("sha256:ok", {"a": 1}))
        monkeypatch.setattr(mod, "_record_and_refresh", lambda *a, **kw: None)

        def fake_run(ctx):
            ctx.artifact = {"oos_mean_ic": 0.03, "oos_per_fold_ic": [0.02, 0.03, 0.04]}
            ctx.feat_cols = ["f1", "f2"]
            result = MagicMock()
            result.ok = True
            result.name = "panel-gbdt"
            result.elapsed_sec = 5.0
            result.steps = []
            return result

        fake_pipeline = MagicMock()
        fake_pipeline.run.side_effect = fake_run
        monkeypatch.setattr(mod, "build_training_pipeline", lambda: fake_pipeline)

        rc = mod.main(["--skip-sentiment-gate", "--strategy-config", "none"])
        assert rc == 0

    def test_custom_data_dir(self, monkeypatch, tmp_path):
        data_dir = tmp_path / "custom_data"
        data_dir.mkdir()
        monkeypatch.setattr(mod, "_production_fingerprint", lambda p: (None, None))
        monkeypatch.setattr(mod, "_record_and_refresh", lambda *a, **kw: None)

        captured_ctx = []

        def fake_run(ctx):
            captured_ctx.append(ctx)
            ctx.artifact = None
            ctx.feat_cols = []
            result = MagicMock()
            result.ok = True
            result.name = "p"
            result.elapsed_sec = 0.1
            result.steps = []
            return result

        fake_pipeline = MagicMock()
        fake_pipeline.run.side_effect = fake_run
        monkeypatch.setattr(mod, "build_training_pipeline", lambda: fake_pipeline)

        rc = mod.main([
            "--data-dir", str(data_dir),
            "--skip-sentiment-gate",
            "--strategy-config", "none",
        ])
        assert rc == 0
        assert captured_ctx[0].data_dir == str(data_dir)

    def test_output_path_default(self, monkeypatch, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        monkeypatch.setattr(mod, "DEFAULT_DATA_DIR", data_dir)
        monkeypatch.setattr(mod, "_production_fingerprint", lambda p: (None, None))
        monkeypatch.setattr(mod, "_record_and_refresh", lambda *a, **kw: None)

        captured_ctx = []

        def fake_run(ctx):
            captured_ctx.append(ctx)
            ctx.artifact = None
            ctx.feat_cols = []
            result = MagicMock()
            result.ok = True
            result.name = "p"
            result.elapsed_sec = 0.1
            result.steps = []
            return result

        fake_pipeline = MagicMock()
        fake_pipeline.run.side_effect = fake_run
        monkeypatch.setattr(mod, "build_training_pipeline", lambda: fake_pipeline)

        rc = mod.main(["--skip-sentiment-gate", "--strategy-config", "none"])
        assert rc == 0
        assert captured_ctx[0].output_path == str(
            data_dir / "panel-ltr-prod-alpha158-fund-fwd60d.json"
        )

    def test_exclude_features_only(self, monkeypatch, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        monkeypatch.setattr(mod, "DEFAULT_DATA_DIR", data_dir)
        monkeypatch.setattr(mod, "_production_fingerprint", lambda p: (None, None))
        monkeypatch.setattr(mod, "_record_and_refresh", lambda *a, **kw: None)

        captured_ctx = []

        def fake_run(ctx):
            captured_ctx.append(ctx)
            ctx.artifact = None
            ctx.feat_cols = []
            result = MagicMock()
            result.ok = True
            result.name = "p"
            result.elapsed_sec = 0.1
            result.steps = []
            return result

        fake_pipeline = MagicMock()
        fake_pipeline.run.side_effect = fake_run
        monkeypatch.setattr(mod, "build_training_pipeline", lambda: fake_pipeline)

        rc = mod.main([
            "--exclude-features", "x1, x2",
            "--skip-sentiment-gate",
            "--strategy-config", "none",
        ])
        assert rc == 0
        assert captured_ctx[0].exclude_features == ["x1", "x2"]


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

class TestModuleConstants:
    def test_pin_srcs(self):
        assert mod._PIN_SRCS == [
            "renquant-common", "renquant-base-data",
            "renquant-artifacts", "renquant-model",
        ]

    def test_default_data_dir_is_under_umbrella(self):
        assert "RenQuant" in str(mod.DEFAULT_DATA_DIR)
        assert mod.DEFAULT_DATA_DIR.name == "data"

    def test_github_is_four_levels_up(self):
        # __file__ is src/renquant_orchestrator/train_gbdt.py
        # parents[3] should be the github root.
        assert mod.GITHUB == Path(mod.__file__).resolve().parents[3]
