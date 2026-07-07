"""Tests for parking_sleeve.py — S7 β-budgeted SPY/SGOV shadow allocator."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from renquant_orchestrator.parking_sleeve import (
    BookState,
    SleeveAllocation,
    SleeveConfig,
    compute_sleeve_allocation,
    main,
    write_shadow_log,
)


# --- Config tests ---


class TestSleeveConfig:
    def test_defaults(self):
        cfg = SleeveConfig()
        assert cfg.enabled is False
        assert cfg.beta_max == 0.6
        assert cfg.reserve_pct == 0.02
        assert cfg.spy_ticker == "SPY"
        assert cfg.sgov_ticker == "SGOV"
        assert cfg.beta_spy == 1.0
        assert cfg.regime_bear_override is True

    def test_from_dict_full(self):
        cfg = SleeveConfig.from_dict({
            "enabled": True,
            "beta_max": 0.5,
            "reserve_pct": 0.05,
            "spy_ticker": "VOO",
            "sgov_ticker": "BIL",
            "beta_spy": 0.98,
            "regime_bear_override": False,
        })
        assert cfg.enabled is True
        assert cfg.beta_max == 0.5
        assert cfg.reserve_pct == 0.05
        assert cfg.spy_ticker == "VOO"
        assert cfg.sgov_ticker == "BIL"
        assert cfg.beta_spy == 0.98
        assert cfg.regime_bear_override is False

    def test_from_dict_partial(self):
        cfg = SleeveConfig.from_dict({"enabled": True, "beta_max": 0.7})
        assert cfg.enabled is True
        assert cfg.beta_max == 0.7
        assert cfg.reserve_pct == 0.02  # default

    def test_from_dict_none(self):
        cfg = SleeveConfig.from_dict(None)
        assert cfg == SleeveConfig()

    def test_from_dict_empty(self):
        cfg = SleeveConfig.from_dict({})
        assert cfg == SleeveConfig()


# --- Core formula tests ---


class TestComputeSleeveAllocation:
    """Test the β-budget formula under various book states."""

    def _book(self, pv=10000, pos_val=4300, cash=5700, beta_pos=0.43, regime="BULL_CALM"):
        return BookState(
            portfolio_value=pv,
            positions_value=pos_val,
            cash_value=cash,
            beta_positions=beta_pos,
            regime=regime,
        )

    def _cfg(self, **kw):
        return SleeveConfig.from_dict({"enabled": True, **kw})

    def test_standard_case_matches_rs1(self):
        """RS-1 example: w_pos=0.43, β_pos=0.43, β_max=0.6 → spy_frac≈0.31."""
        book = self._book(pv=10000, pos_val=4300, beta_pos=0.43)
        cfg = self._cfg(beta_max=0.6, reserve_pct=0.02)
        alloc = compute_sleeve_allocation(book, cfg)

        # w_sleeve = 1 - 0.43 - 0.02 = 0.55
        assert abs(alloc.sleeve_weight - 0.55) < 1e-9
        # spy_frac = (0.6 - 0.43) / (0.55 * 1.0) = 0.17 / 0.55 ≈ 0.309
        assert abs(alloc.spy_frac - 0.17 / 0.55) < 1e-6
        assert abs(alloc.sgov_frac - (1 - alloc.spy_frac)) < 1e-9
        # β_book ≈ 0.43 + 0.55 * 0.309 * 1.0 ≈ 0.6
        assert abs(alloc.beta_book_estimate - 0.6) < 1e-6

    def test_high_beta_positions_zero_spy(self):
        """When β_positions >= β_max, sleeve gets 0% SPY."""
        book = self._book(beta_pos=0.65)
        cfg = self._cfg(beta_max=0.6)
        alloc = compute_sleeve_allocation(book, cfg)

        assert alloc.spy_frac == 0.0
        assert alloc.sgov_frac == 1.0
        assert alloc.spy_target_weight == 0.0

    def test_low_beta_positions_full_spy(self):
        """When β_positions is very low and headroom > w_sleeve, cap at 100% SPY."""
        book = self._book(pv=10000, pos_val=1000, beta_pos=0.10)
        cfg = self._cfg(beta_max=0.6, reserve_pct=0.02)
        alloc = compute_sleeve_allocation(book, cfg)

        # w_sleeve = 1 - 0.10 - 0.02 = 0.88
        # headroom = 0.6 - 0.10 = 0.50
        # spy_frac = 0.50 / (0.88 * 1.0) = 0.568 (< 1, so NOT full SPY here)
        assert alloc.spy_frac < 1.0
        assert alloc.spy_frac > 0.0

    def test_very_low_beta_caps_at_one(self):
        """When headroom / (w_sleeve * β_spy) > 1, cap spy_frac at 1.0."""
        book = self._book(pv=10000, pos_val=8000, beta_pos=0.0)
        cfg = self._cfg(beta_max=0.6, reserve_pct=0.02)
        alloc = compute_sleeve_allocation(book, cfg)

        # w_sleeve = 1 - 0.80 - 0.02 = 0.18
        # headroom = 0.6 - 0.0 = 0.6
        # spy_frac = 0.6 / (0.18 * 1.0) = 3.33 → capped to 1.0
        assert alloc.spy_frac == 1.0
        assert alloc.sgov_frac == 0.0

    def test_zero_portfolio_value(self):
        """Zero PV returns a zeroed allocation."""
        book = self._book(pv=0, pos_val=0, cash=0, beta_pos=0)
        cfg = self._cfg()
        alloc = compute_sleeve_allocation(book, cfg)

        assert alloc.spy_frac == 0.0
        assert alloc.sgov_frac == 1.0
        assert alloc.spy_target_notional == 0.0
        assert alloc.sgov_target_notional == 0.0

    def test_positions_exceed_one_minus_reserve(self):
        """When w_pos + reserve >= 1.0, sleeve_weight = 0."""
        book = self._book(pv=10000, pos_val=9900, beta_pos=0.99)
        cfg = self._cfg(reserve_pct=0.02)
        alloc = compute_sleeve_allocation(book, cfg)

        assert alloc.sleeve_weight == 0.0
        assert alloc.spy_frac == 0.0
        assert alloc.spy_target_notional == 0.0
        assert alloc.sgov_target_notional == 0.0

    def test_notional_calculation(self):
        """Target notionals match weight × PV."""
        book = self._book(pv=50000, pos_val=20000, beta_pos=0.40)
        cfg = self._cfg(beta_max=0.6, reserve_pct=0.02)
        alloc = compute_sleeve_allocation(book, cfg)

        assert abs(alloc.spy_target_notional - alloc.spy_target_weight * 50000) < 0.01
        assert abs(alloc.sgov_target_notional - alloc.sgov_target_weight * 50000) < 0.01

    def test_weights_sum_to_one(self):
        """positions_weight + sleeve_weight + reserve_weight = 1.0."""
        book = self._book(pv=10000, pos_val=4300, beta_pos=0.43)
        cfg = self._cfg(reserve_pct=0.03)
        alloc = compute_sleeve_allocation(book, cfg)

        total = alloc.positions_weight + alloc.sleeve_weight + alloc.reserve_weight
        assert abs(total - 1.0) < 1e-9

    def test_custom_beta_spy(self):
        """Non-1.0 β_spy (e.g. VOO β=0.99) changes the allocation."""
        book = self._book(pv=10000, pos_val=4000, beta_pos=0.40)
        cfg = self._cfg(beta_max=0.6, beta_spy=0.99, reserve_pct=0.02)
        alloc = compute_sleeve_allocation(book, cfg)

        # w_sleeve = 0.58, headroom = 0.20
        # spy_frac = 0.20 / (0.58 * 0.99) ≈ 0.348
        expected = 0.20 / (0.58 * 0.99)
        assert abs(alloc.spy_frac - expected) < 1e-6


# --- Regime override tests ---


class TestRegimeOverride:
    def _book(self, regime):
        return BookState(
            portfolio_value=10000,
            positions_value=4000,
            cash_value=6000,
            beta_positions=0.40,
            regime=regime,
        )

    def test_bear_override_zeros_spy(self):
        cfg = SleeveConfig.from_dict({"enabled": True, "regime_bear_override": True})
        alloc = compute_sleeve_allocation(self._book("BEAR"), cfg)

        assert alloc.spy_frac == 0.0
        assert alloc.sgov_frac == 1.0
        assert alloc.regime_override_active is True

    def test_bear_override_disabled(self):
        cfg = SleeveConfig.from_dict({"enabled": True, "regime_bear_override": False})
        alloc = compute_sleeve_allocation(self._book("BEAR"), cfg)

        assert alloc.spy_frac > 0.0
        assert alloc.regime_override_active is False

    def test_bull_calm_no_override(self):
        cfg = SleeveConfig.from_dict({"enabled": True, "regime_bear_override": True})
        alloc = compute_sleeve_allocation(self._book("BULL_CALM"), cfg)

        assert alloc.spy_frac > 0.0
        assert alloc.regime_override_active is False

    def test_bull_volatile_no_override(self):
        cfg = SleeveConfig.from_dict({"enabled": True, "regime_bear_override": True})
        alloc = compute_sleeve_allocation(self._book("BULL_VOLATILE"), cfg)

        assert alloc.spy_frac > 0.0
        assert alloc.regime_override_active is False

    def test_choppy_no_override(self):
        cfg = SleeveConfig.from_dict({"enabled": True, "regime_bear_override": True})
        alloc = compute_sleeve_allocation(self._book("CHOPPY"), cfg)

        assert alloc.spy_frac > 0.0
        assert alloc.regime_override_active is False


# --- Shadow log tests ---


class TestShadowLog:
    def test_write_creates_file(self, tmp_path):
        log_path = tmp_path / "shadow" / "sleeve.jsonl"
        book = BookState(10000, 4000, 6000, 0.40, "BULL_CALM")
        cfg = SleeveConfig.from_dict({"enabled": True})
        alloc = compute_sleeve_allocation(book, cfg)

        write_shadow_log(alloc, log_path)

        assert log_path.exists()
        lines = log_path.read_text().strip().split("\n")
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["spy_frac"] == alloc.spy_frac
        assert record["regime"] == "BULL_CALM"
        assert record["enabled"] is True

    def test_write_appends(self, tmp_path):
        log_path = tmp_path / "sleeve.jsonl"
        book1 = BookState(10000, 4000, 6000, 0.40, "BULL_CALM")
        book2 = BookState(10000, 5000, 5000, 0.50, "BEAR")
        cfg = SleeveConfig.from_dict({"enabled": True})

        alloc1 = compute_sleeve_allocation(book1, cfg)
        alloc2 = compute_sleeve_allocation(book2, cfg)
        write_shadow_log(alloc1, log_path)
        write_shadow_log(alloc2, log_path)

        lines = log_path.read_text().strip().split("\n")
        assert len(lines) == 2
        r1 = json.loads(lines[0])
        r2 = json.loads(lines[1])
        assert r1["regime"] == "BULL_CALM"
        assert r2["regime"] == "BEAR"
        assert r2["regime_override_active"] is True

    def test_log_record_fields(self, tmp_path):
        log_path = tmp_path / "sleeve.jsonl"
        book = BookState(20000, 8000, 12000, 0.40, "BULL_CALM")
        cfg = SleeveConfig.from_dict({"enabled": True, "beta_max": 0.6})
        alloc = compute_sleeve_allocation(book, cfg)
        write_shadow_log(alloc, log_path)

        record = json.loads(log_path.read_text().strip())
        expected_fields = {
            "as_of", "portfolio_value", "positions_weight", "sleeve_weight",
            "reserve_weight", "spy_frac", "sgov_frac", "spy_target_weight",
            "sgov_target_weight", "spy_target_notional", "sgov_target_notional",
            "beta_positions", "beta_book_estimate", "regime",
            "regime_override_active", "enabled", "spy_notional", "sgov_notional",
        }
        assert set(record.keys()) == expected_fields

    def test_log_alias_fields_match_target_notionals(self, tmp_path):
        log_path = tmp_path / "sleeve.jsonl"
        book = BookState(15000, 4500, 10500, 0.30, "BULL_CALM")
        cfg = SleeveConfig.from_dict({"enabled": True})
        alloc = compute_sleeve_allocation(book, cfg)

        write_shadow_log(alloc, log_path)

        record = json.loads(log_path.read_text().strip())
        assert record["spy_notional"] == pytest.approx(record["spy_target_notional"])
        assert record["sgov_notional"] == pytest.approx(record["sgov_target_notional"])


# --- Integration: allocation → log round-trip ---


class TestRoundTrip:
    def test_allocation_serializes_correctly(self, tmp_path):
        log_path = tmp_path / "sleeve.jsonl"
        book = BookState(10000, 4300, 5700, 0.43, "BULL_CALM")
        cfg = SleeveConfig.from_dict({"enabled": True, "beta_max": 0.6, "reserve_pct": 0.02})
        alloc = compute_sleeve_allocation(book, cfg)

        write_shadow_log(alloc, log_path)
        record = json.loads(log_path.read_text().strip())

        assert abs(record["spy_frac"] - alloc.spy_frac) < 1e-12
        assert abs(record["beta_book_estimate"] - 0.6) < 1e-6
        assert record["positions_weight"] == pytest.approx(0.43)
        assert record["sleeve_weight"] == pytest.approx(0.55)


class TestMain:
    def test_main_auto_runtime_mode_writes_default_shadow_log(self, tmp_path, monkeypatch, capsys):
        from renquant_orchestrator import parking_sleeve as mod

        cfg_path = tmp_path / "strategy_config.json"
        cfg_path.write_text(json.dumps({"sleeve": {"enabled": True, "beta_max": 0.6}}))

        monkeypatch.setattr(mod, "default_data_root", lambda: tmp_path)
        monkeypatch.setattr(mod, "default_strategy_config_path", lambda: cfg_path)
        monkeypatch.setattr(
            mod,
            "_build_runtime_book_state",
            lambda **_: (
                BookState(
                    portfolio_value=10_000,
                    positions_value=4_000,
                    cash_value=6_000,
                    beta_positions=0.40,
                    regime="BULL_CALM",
                ),
                {
                    "positions": {"run_id": "r1"},
                    "beta_composition": {"book_beta_measured_names": 0.40},
                    "beta_censored_names": {},
                    "db_path": str(tmp_path / "data" / "runs.alpaca.db"),
                    "ohlcv_dir": str(tmp_path / "data" / "ohlcv"),
                    "run_type": "live",
                },
            ),
        )

        rc = main([])

        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["portfolio_value"] == 10_000
        assert payload["spy_notional"] == pytest.approx(payload["spy_target_notional"])

        shadow_log = tmp_path / "backtesting" / "renquant_104" / "logs" / "parking_sleeve_shadow.jsonl"
        record = json.loads(shadow_log.read_text().strip())
        assert record["runtime"]["book_state_source"] == "latest_live_run"
        assert record["runtime"]["config_path"] == str(cfg_path)
        assert record["book_state"]["spy_notional"] == pytest.approx(record["spy_target_notional"])
        assert record["input_book_state"]["regime"] == "BULL_CALM"
