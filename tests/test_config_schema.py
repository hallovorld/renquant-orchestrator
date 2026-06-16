"""Tests for config_schema (#108 S1) — typed strategy-config top level.

Hermetic: a minimal valid config is built inline and mutated to exercise each
typo class the schema must catch at load.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from renquant_orchestrator.config_schema import (
    StrategyConfigTop,
    load_strategy_config,
    validate_strategy_config,
)


def _valid() -> dict:
    return {
        "model_name": "renquant_104",
        "watchlist": ["AAPL", "MSFT"],
        "benchmark": "SPY",
        "wash_sale_days": 31,
        "min_hold_days": 1,
        "max_hold_days": 500,
        "max_concurrent_positions": 12,
        "regime": {
            "bear_vol_threshold": 0.25,
            "bear_return_threshold": -0.02,
            "bear_vol_threshold_5d": 0.25,
            "bear_return_threshold_5d": -0.025,
            "transition_uncertainty_bars": 3,
            "bear_short_route_require_both": True,
        },
        # untyped extras pass through
        "some_unmodelled_block": {"a": 1},
        "another_extra": 42,
    }


def test_valid_config_passes_and_counts_extras():
    cfg = validate_strategy_config(_valid())
    assert cfg.model_name == "renquant_104"
    assert cfg.max_concurrent_positions == 12
    assert cfg.extra_key_count() == 2  # the two untyped extras


def test_wash_sale_out_of_range_caught():
    bad = _valid()
    bad["wash_sale_days"] = 3000
    with pytest.raises(ValidationError) as e:
        validate_strategy_config(bad)
    assert e.value.errors()[0]["loc"] == ("wash_sale_days",)


def test_bear_return_sign_flip_caught():
    """A POSITIVE bear_return_threshold_5d would silently disable the acute-loss
    BEAR route — the highest-value typo to catch."""
    bad = _valid()
    bad["regime"]["bear_return_threshold_5d"] = 0.04  # sign flip
    with pytest.raises(ValidationError) as e:
        validate_strategy_config(bad)
    assert e.value.errors()[0]["loc"] == ("regime", "bear_return_threshold_5d")


def test_zero_positions_caught():
    bad = _valid()
    bad["max_concurrent_positions"] = 0  # below ge=1
    with pytest.raises(ValidationError):
        validate_strategy_config(bad)


def test_wrong_type_caught():
    bad = _valid()
    bad["watchlist"] = "AAPL"  # str, not list
    with pytest.raises(ValidationError):
        validate_strategy_config(bad)


def test_missing_required_key_caught():
    bad = _valid()
    del bad["benchmark"]
    with pytest.raises(ValidationError):
        validate_strategy_config(bad)


def test_regime_extra_keys_allowed():
    cfg = _valid()
    cfg["regime"]["new_experimental_threshold"] = 0.1
    out = validate_strategy_config(cfg)
    assert out.regime.model_extra.get("new_experimental_threshold") == 0.1


def test_load_from_file(tmp_path):
    import json
    p = tmp_path / "strategy_config.json"
    p.write_text(json.dumps(_valid()))
    cfg = load_strategy_config(p)
    assert isinstance(cfg, StrategyConfigTop)
    assert cfg.benchmark == "SPY"
