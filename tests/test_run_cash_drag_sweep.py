"""Tests for scripts/run_cash_drag_sweep.py — OAT parameter sweep."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.run_cash_drag_sweep import (
    FROZEN_SEEDS,
    VARIANT_SPECS,
    SweepVariant,
    _set_nested,
    build_all_variants,
    build_variant_config,
    main,
)


@pytest.fixture()
def base_config(tmp_path: Path) -> Path:
    cfg = {
        "ranking": {
            "panel_scoring": {
                "buy_floor": "adaptive_mean_std",
                "buy_floor_min": 0.20,
                "buy_floor_std_mult": 1.0,
            },
            "kelly_sizing": {
                "fractional": 0.3,
                "max_concentration": 0.12,
                "top_up_threshold": 0.05,
                "base_rate": 0.273,
            },
        },
        "regime_params": {
            "BULL_CALM": {
                "qp_turnover_max": 0.15,
                "max_position_pct": 0.12,
            },
        },
    }
    p = tmp_path / "strategy_config.json"
    p.write_text(json.dumps(cfg))
    return p


class TestSetNested:
    def test_shallow(self) -> None:
        d: dict = {"a": 1}
        _set_nested(d, "a", 2)
        assert d["a"] == 2

    def test_deep(self) -> None:
        d: dict = {"a": {"b": {"c": 1}}}
        _set_nested(d, "a.b.c", 99)
        assert d["a"]["b"]["c"] == 99

    def test_creates_intermediate(self) -> None:
        d: dict = {}
        _set_nested(d, "x.y.z", "hello")
        assert d["x"]["y"]["z"] == "hello"


class TestVariantGeneration:
    def test_total_variant_count(self, base_config: Path, tmp_path: Path) -> None:
        variants = build_all_variants(
            base_config_path=base_config,
            output_dir=tmp_path / "out",
            seeds=FROZEN_SEEDS,
        )
        assert len(variants) == len(VARIANT_SPECS) + 1  # +1 for A/A

    def test_exactly_one_incumbent(self, base_config: Path, tmp_path: Path) -> None:
        variants = build_all_variants(
            base_config_path=base_config,
            output_dir=tmp_path / "out",
            seeds=FROZEN_SEEDS,
        )
        incumbents = [v for v in variants if v.role == "incumbent"]
        assert len(incumbents) == 1

    def test_aa_has_offset_seeds(self, base_config: Path, tmp_path: Path) -> None:
        variants = build_all_variants(
            base_config_path=base_config,
            output_dir=tmp_path / "out",
            seeds=FROZEN_SEEDS,
        )
        aa = [v for v in variants if v.role == "aa_resplit"]
        assert len(aa) == 1
        assert aa[0].seeds == (1042, 1043, 1044)

    def test_overrides_applied_to_configs(
        self, base_config: Path, tmp_path: Path
    ) -> None:
        variants = build_all_variants(
            base_config_path=base_config,
            output_dir=tmp_path / "out",
            seeds=FROZEN_SEEDS,
        )
        for v in variants:
            assert v.config_path.exists()
            cfg = json.loads(v.config_path.read_text())
            for dotpath, expected in v.config_overrides.items():
                keys = dotpath.split(".")
                node = cfg
                for k in keys:
                    node = node[k]
                assert node == expected, (
                    f"{v.name}: {dotpath} expected {expected}, got {node}"
                )


class TestOATDesign:
    def test_each_variant_changes_exactly_one_dimension(self) -> None:
        dimensions = set()
        for name, role, hypothesis, overrides in VARIANT_SPECS:
            if role == "incumbent":
                assert not overrides
                continue
            dim_keys = {k.rsplit(".", 1)[0] for k in overrides}
            dimensions.add(frozenset(dim_keys))
            assert len(dim_keys) <= 2, (
                f"{name} changes {len(dim_keys)} dimensions: {dim_keys}. "
                f"OAT requires exactly 1 (or 2 for coupled params like buy_floor+quantile)."
            )

    def test_incumbent_has_no_overrides(self) -> None:
        incumbent = [s for s in VARIANT_SPECS if s[1] == "incumbent"]
        assert len(incumbent) == 1
        assert incumbent[0][3] == {}


class TestFrozenContract:
    def test_seeds_are_frozen(self) -> None:
        assert FROZEN_SEEDS == (42, 43, 44)


class TestPathAuthority:
    def test_uses_default_repo_root(self) -> None:
        import scripts.run_cash_drag_sweep as mod

        with patch.object(mod, "default_repo_root") as mock:
            mock.return_value = Path("/nonexistent")
            rc = main([])
            mock.assert_called_once()
            assert rc == 1
