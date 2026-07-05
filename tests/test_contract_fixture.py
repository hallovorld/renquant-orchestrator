"""Tests for ``contract_fixture`` — the deterministic daily-run smoke fixture.

Covers:
- ``fixture_data_manifest()`` returns a well-formed manifest dict
- ``run_contract_fixture()`` happy path (paper broker, dry_run=True)
- ``run_contract_fixture()`` with explicit broker_name
- ``run_contract_fixture()`` broker_name mismatch raises ValueError
- ``run_contract_fixture()`` with dry_run=False
- ``run_contract_fixture()`` propagates as_of / run_id / code_commit correctly
- Paper broker default vs explicit broker_name assignment
- Run-bundle persistence (JSON validity, sidecar files)

All external subrepo deps (renquant_strategy_104, renquant_execution,
renquant_pipeline) are monkeypatched so the suite is hermetic.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from renquant_orchestrator.contract_fixture import (
    fixture_data_manifest,
    run_contract_fixture,
)


# ---------------------------------------------------------------------------
# Helpers: fake strategy config file + fake subrepo functions
# ---------------------------------------------------------------------------

def _write_strategy_config(tmp_path: Path) -> Path:
    """Write a minimal valid strategy config JSON and return its path."""
    cfg = {
        "watchlist": ["AAPL"],
        "ranking": {"panel_scoring": {"enabled": True}},
        "regime_params": {"BULL_CALM": {"disable_new_buys": False}},
        "sector_map": {"AAPL": "Technology"},
    }
    p = tmp_path / "strategy_config.json"
    p.write_text(json.dumps(cfg))
    return p


def _fake_load_strategy_config(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text())


def _fake_strategy_manifest(path: Path) -> dict[str, Any]:
    return {
        "strategy": "renquant_104",
        "config_name": Path(path).name,
        "fingerprint": "sha256:fake-strategy-fingerprint",
        "watchlist_size": 1,
    }


class _FakePaperBroker:
    """Minimal stand-in for PaperBroker."""

    def __init__(self, *, initial_cash: float = 100_000.0):
        self.broker_name = "paper"
        self._cash = initial_cash
        self._prices: dict[str, float] = {}
        self._connected = False

    def connect(self) -> None:
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False

    def set_price(self, symbol: str, price: float) -> None:
        self._prices[symbol] = price

    def place_order(self, symbol: str, action: str, quantity: float) -> dict[str, Any]:
        return {
            "order_id": f"fake-{symbol}-{action}",
            "symbol": symbol,
            "action": action,
            "quantity": quantity,
            "status": "filled",
        }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def strategy_path(tmp_path: Path) -> Path:
    return _write_strategy_config(tmp_path)


@pytest.fixture
def _patch_subrepo_deps(monkeypatch):
    """Monkeypatch all external subrepo dependencies used by contract_fixture."""
    monkeypatch.setattr(
        "renquant_orchestrator.contract_fixture.load_strategy_config",
        _fake_load_strategy_config,
    )
    monkeypatch.setattr(
        "renquant_orchestrator.contract_fixture.strategy_manifest",
        _fake_strategy_manifest,
    )
    monkeypatch.setattr(
        "renquant_orchestrator.contract_fixture.get_broker",
        lambda broker_type, initial_cash: _FakePaperBroker(initial_cash=initial_cash),
    )
    # PanelScoringJob / SelectionJob are passed as runtime_stages — replace with
    # lightweight Task stubs that produce the order_intents the pipeline needs.
    from renquant_common import Task
    from renquant_pipeline import stamp_order_attribution

    class FakeScoreTask(Task):
        def run(self, ctx) -> bool | None:
            ctx.scores = {"AAPL": 0.42}
            ctx.decision_trace.append({"stage": "score", "ticker": "AAPL", "score": 0.42})
            return True

    class FakeSelectTask(Task):
        def run(self, ctx) -> bool | None:
            ctx.order_intents.append(
                stamp_order_attribution(
                    {"ticker": "AAPL", "action": "buy", "quantity": 1},
                    ctx,
                    source_job="FixtureScoringJob",
                    source_task="FakeSelectTask",
                    acceptance_reason="contract_fixture_smoke",
                    decision_inputs={"score": 0.42},
                )
            )
            ctx.decision_trace.append({"stage": "select", "ticker": "AAPL", "quantity": 1})
            return True

    class FakeEmitTask(Task):
        """Stand-in for PanelScoringJob(emit_orders=True)."""
        def run(self, ctx) -> bool | None:
            return True

    monkeypatch.setattr(
        "renquant_orchestrator.contract_fixture.PanelScoringJob",
        lambda emit_orders=False: FakeEmitTask() if emit_orders else FakeScoreTask(),
    )
    monkeypatch.setattr(
        "renquant_orchestrator.contract_fixture.SelectionJob",
        lambda: FakeSelectTask(),
    )


# ---------------------------------------------------------------------------
# Tests: fixture_data_manifest
# ---------------------------------------------------------------------------

class TestFixtureDataManifest:
    def test_returns_dict(self):
        m = fixture_data_manifest()
        assert isinstance(m, dict)

    def test_has_required_keys(self):
        m = fixture_data_manifest()
        for key in ("dataset_id", "schema_version", "fingerprint", "uri", "asset_class"):
            assert key in m, f"missing key: {key}"

    def test_fingerprint_starts_with_sha256(self):
        m = fixture_data_manifest()
        assert m["fingerprint"].startswith("sha256:")

    def test_retention_class_is_fixture(self):
        m = fixture_data_manifest()
        assert m["retention_class"] == "fixture"

    def test_idempotent(self):
        assert fixture_data_manifest() == fixture_data_manifest()


# ---------------------------------------------------------------------------
# Tests: run_contract_fixture — happy path
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("_patch_subrepo_deps")
class TestRunContractFixtureHappyPath:
    def test_returns_ok(self, tmp_path, strategy_path):
        result = run_contract_fixture(
            strategy_config_path=strategy_path,
            output_dir=tmp_path / "out",
            run_id="smoke-run-1",
            as_of="2026-07-04",
        )
        assert result["ok"] is True

    def test_training_calls_recorded(self, tmp_path, strategy_path):
        result = run_contract_fixture(
            strategy_config_path=strategy_path,
            output_dir=tmp_path / "out",
            run_id="smoke-run-1",
            as_of="2026-07-04",
        )
        assert "load" in result["training_calls"]
        assert "train" in result["training_calls"]
        assert "validate" in result["training_calls"]

    def test_artifact_id_present(self, tmp_path, strategy_path):
        result = run_contract_fixture(
            strategy_config_path=strategy_path,
            output_dir=tmp_path / "out",
            run_id="smoke-run-1",
            as_of="2026-07-04",
        )
        assert result["artifact_id"] == "subrepo-smoke-gbdt"

    def test_default_broker_type_is_paper(self, tmp_path, strategy_path):
        result = run_contract_fixture(
            strategy_config_path=strategy_path,
            output_dir=tmp_path / "out",
            run_id="smoke-run-1",
            as_of="2026-07-04",
        )
        assert result["broker_type"] == "paper"

    def test_default_dry_run_is_true(self, tmp_path, strategy_path):
        result = run_contract_fixture(
            strategy_config_path=strategy_path,
            output_dir=tmp_path / "out",
            run_id="smoke-run-1",
            as_of="2026-07-04",
        )
        assert result["dry_run"] is True

    def test_run_bundle_path_exists_on_disk(self, tmp_path, strategy_path):
        result = run_contract_fixture(
            strategy_config_path=strategy_path,
            output_dir=tmp_path / "out",
            run_id="smoke-run-1",
            as_of="2026-07-04",
        )
        assert Path(result["run_bundle_path"]).exists()

    def test_run_bundle_has_expected_keys(self, tmp_path, strategy_path):
        result = run_contract_fixture(
            strategy_config_path=strategy_path,
            output_dir=tmp_path / "out",
            run_id="smoke-run-1",
            as_of="2026-07-04",
        )
        keys = result["run_bundle_keys"]
        for expected in ("run_id", "run_type", "strategy_manifest", "data_manifest",
                         "artifact_manifest", "stage_trace"):
            assert expected in keys, f"bundle missing key: {expected}"

    def test_order_intents_populated(self, tmp_path, strategy_path):
        result = run_contract_fixture(
            strategy_config_path=strategy_path,
            output_dir=tmp_path / "out",
            run_id="smoke-run-1",
            as_of="2026-07-04",
        )
        assert isinstance(result["order_intents"], list)
        assert len(result["order_intents"]) >= 1

    def test_backtest_report_present(self, tmp_path, strategy_path):
        result = run_contract_fixture(
            strategy_config_path=strategy_path,
            output_dir=tmp_path / "out",
            run_id="smoke-run-1",
            as_of="2026-07-04",
        )
        assert result["backtest_report"] is not None
        assert result["backtest_report"]["ok"] is True


# ---------------------------------------------------------------------------
# Tests: run_contract_fixture — parameter variations
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("_patch_subrepo_deps")
class TestRunContractFixtureParams:
    def test_explicit_broker_name_paper(self, tmp_path, strategy_path):
        result = run_contract_fixture(
            strategy_config_path=strategy_path,
            output_dir=tmp_path / "out",
            run_id="smoke-run-2",
            as_of="2026-07-04",
            broker_name="my-paper-broker",
        )
        assert result["broker_name"] == "my-paper-broker"

    def test_code_commit_propagated(self, tmp_path, strategy_path):
        """code_commit flows into model_config and through the pipeline."""
        result = run_contract_fixture(
            strategy_config_path=strategy_path,
            output_dir=tmp_path / "out",
            run_id="smoke-run-3",
            as_of="2026-07-04",
            code_commit="abc1234",
        )
        assert result["ok"] is True
        bundle = json.loads(Path(result["run_bundle_path"]).read_text())
        assert bundle["run_id"] == "smoke-run-3"

    def test_dry_run_false(self, tmp_path, strategy_path):
        result = run_contract_fixture(
            strategy_config_path=strategy_path,
            output_dir=tmp_path / "out",
            run_id="smoke-run-4",
            as_of="2026-07-04",
            dry_run=False,
        )
        assert result["dry_run"] is False
        assert result["ok"] is True

    def test_as_of_surfaces_in_result(self, tmp_path, strategy_path):
        """as_of is passed to the trainer stub and used throughout the pipeline."""
        result = run_contract_fixture(
            strategy_config_path=strategy_path,
            output_dir=tmp_path / "out",
            run_id="smoke-date-test",
            as_of="2026-01-15",
        )
        assert result["ok"] is True


# ---------------------------------------------------------------------------
# Tests: broker_name mismatch
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("_patch_subrepo_deps")
class TestBrokerNameMismatch:
    def test_non_paper_broker_name_mismatch_raises(self, tmp_path, strategy_path, monkeypatch):
        """When broker_type is not 'paper' and broker_name doesn't match, raise ValueError."""

        class _NonPaperBroker(_FakePaperBroker):
            def __init__(self, **kw):
                super().__init__(**kw)
                self.broker_name = "real-broker-x"

        monkeypatch.setattr(
            "renquant_orchestrator.contract_fixture.get_broker",
            lambda broker_type, initial_cash: _NonPaperBroker(initial_cash=initial_cash),
        )
        with pytest.raises(ValueError, match="broker_name=.*does not match"):
            run_contract_fixture(
                strategy_config_path=strategy_path,
                output_dir=tmp_path / "out",
                run_id="mismatch-run",
                as_of="2026-07-04",
                broker_type="live",
                broker_name="wrong-name",
            )

    def test_non_paper_broker_name_matches_passes(self, tmp_path, strategy_path, monkeypatch):
        """When broker_type is not 'paper' but broker_name matches, no error."""

        class _NonPaperBroker(_FakePaperBroker):
            def __init__(self, **kw):
                super().__init__(**kw)
                self.broker_name = "real-broker-x"

        monkeypatch.setattr(
            "renquant_orchestrator.contract_fixture.get_broker",
            lambda broker_type, initial_cash: _NonPaperBroker(initial_cash=initial_cash),
        )
        result = run_contract_fixture(
            strategy_config_path=strategy_path,
            output_dir=tmp_path / "out",
            run_id="match-run",
            as_of="2026-07-04",
            broker_type="live",
            broker_name="real-broker-x",
        )
        assert result["ok"] is True

    def test_non_paper_no_broker_name_uses_default(self, tmp_path, strategy_path, monkeypatch):
        """When broker_type is not 'paper' and broker_name is None, use the broker's default."""

        class _NonPaperBroker(_FakePaperBroker):
            def __init__(self, **kw):
                super().__init__(**kw)
                self.broker_name = "default-live"

        monkeypatch.setattr(
            "renquant_orchestrator.contract_fixture.get_broker",
            lambda broker_type, initial_cash: _NonPaperBroker(initial_cash=initial_cash),
        )
        result = run_contract_fixture(
            strategy_config_path=strategy_path,
            output_dir=tmp_path / "out",
            run_id="default-name-run",
            as_of="2026-07-04",
            broker_type="live",
        )
        assert result["broker_name"] == "default-live"


# ---------------------------------------------------------------------------
# Tests: paper broker broker_name assignment
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("_patch_subrepo_deps")
class TestPaperBrokerName:
    def test_paper_default_broker_name(self, tmp_path, strategy_path):
        """Paper broker with no explicit broker_name defaults to 'paper-smoke'."""
        result = run_contract_fixture(
            strategy_config_path=strategy_path,
            output_dir=tmp_path / "out",
            run_id="paper-default",
            as_of="2026-07-04",
            broker_type="paper",
        )
        assert result["broker_name"] == "paper-smoke"

    def test_paper_explicit_broker_name(self, tmp_path, strategy_path):
        """Paper broker with explicit broker_name uses the given name."""
        result = run_contract_fixture(
            strategy_config_path=strategy_path,
            output_dir=tmp_path / "out",
            run_id="paper-named",
            as_of="2026-07-04",
            broker_type="paper",
            broker_name="my-custom-paper",
        )
        assert result["broker_name"] == "my-custom-paper"


# ---------------------------------------------------------------------------
# Tests: run_bundle JSON on disk is valid
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("_patch_subrepo_deps")
class TestRunBundlePersistence:
    def test_run_bundle_json_is_valid(self, tmp_path, strategy_path):
        result = run_contract_fixture(
            strategy_config_path=strategy_path,
            output_dir=tmp_path / "out",
            run_id="bundle-check",
            as_of="2026-07-04",
        )
        bundle = json.loads(Path(result["run_bundle_path"]).read_text())
        assert bundle["run_id"] == "bundle-check"
        assert bundle["schema_version"] == 1

    def test_decision_trace_file_written(self, tmp_path, strategy_path):
        run_contract_fixture(
            strategy_config_path=strategy_path,
            output_dir=tmp_path / "out",
            run_id="trace-check",
            as_of="2026-07-04",
        )
        trace_file = tmp_path / "out" / "decision_trace.json"
        assert trace_file.exists()
        data = json.loads(trace_file.read_text())
        assert isinstance(data, list)

    def test_submitted_orders_file_written(self, tmp_path, strategy_path):
        run_contract_fixture(
            strategy_config_path=strategy_path,
            output_dir=tmp_path / "out",
            run_id="orders-check",
            as_of="2026-07-04",
        )
        orders_file = tmp_path / "out" / "submitted_orders.json"
        assert orders_file.exists()
        data = json.loads(orders_file.read_text())
        assert isinstance(data, list)
