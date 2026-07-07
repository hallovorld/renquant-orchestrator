"""Tests for scripts/run_rank_floor_sweep.py — rank floor calibration sweep."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.run_rank_floor_sweep import (
    FROZEN_SEEDS,
    VARIANT_SPECS,
    build_aa_variant,
    build_variant_config,
    build_variants,
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
            }
        }
    }
    p = tmp_path / "strategy_config.json"
    p.write_text(json.dumps(cfg))
    return p


class TestVariantGeneration:
    def test_grid_produces_6_variants(self, base_config: Path, tmp_path: Path) -> None:
        variants = build_variants(
            base_config_path=base_config,
            output_dir=tmp_path / "out",
            seeds=FROZEN_SEEDS,
        )
        assert len(variants) == 6

    def test_incumbent_identified(self, base_config: Path, tmp_path: Path) -> None:
        variants = build_variants(
            base_config_path=base_config,
            output_dir=tmp_path / "out",
            seeds=FROZEN_SEEDS,
        )
        incumbents = [v for v in variants if v.role == "incumbent"]
        assert len(incumbents) == 1
        assert incumbents[0].buy_floor == "adaptive_mean_std"
        assert incumbents[0].buy_floor_std_mult == 1.0

    def test_quantile_variants_set_correctly(
        self, base_config: Path, tmp_path: Path
    ) -> None:
        variants = build_variants(
            base_config_path=base_config,
            output_dir=tmp_path / "out",
            seeds=FROZEN_SEEDS,
        )
        q_variants = [v for v in variants if v.buy_floor == "adaptive_quantile"]
        assert len(q_variants) == 4
        quantiles = sorted(v.buy_floor_quantile for v in q_variants)
        assert quantiles == [0.60, 0.70, 0.80, 0.90]

    def test_config_files_written(self, base_config: Path, tmp_path: Path) -> None:
        out = tmp_path / "out"
        variants = build_variants(
            base_config_path=base_config, output_dir=out, seeds=FROZEN_SEEDS
        )
        for v in variants:
            assert v.config_path.exists()
            cfg = json.loads(v.config_path.read_text())
            panel = cfg["ranking"]["panel_scoring"]
            assert panel["buy_floor"] == v.buy_floor
            if v.buy_floor_quantile is not None:
                assert panel["buy_floor_quantile"] == v.buy_floor_quantile
            if v.buy_floor_std_mult is not None:
                assert panel["buy_floor_std_mult"] == v.buy_floor_std_mult


class TestAAControl:
    def test_aa_uses_offset_seeds(self, base_config: Path, tmp_path: Path) -> None:
        aa = build_aa_variant(
            base_config_path=base_config,
            output_dir=tmp_path / "out",
            seeds=FROZEN_SEEDS,
        )
        assert aa.role == "aa_resplit"
        assert aa.seeds == (1042, 1043, 1044)

    def test_aa_matches_incumbent_config(
        self, base_config: Path, tmp_path: Path
    ) -> None:
        aa = build_aa_variant(
            base_config_path=base_config,
            output_dir=tmp_path / "out",
            seeds=FROZEN_SEEDS,
        )
        assert aa.buy_floor == "adaptive_mean_std"
        assert aa.buy_floor_std_mult == 1.0


class TestFrozenContract:
    def test_seeds_are_frozen(self) -> None:
        assert FROZEN_SEEDS == (42, 43, 44)

    def test_variant_specs_count(self) -> None:
        assert len(VARIANT_SPECS) == 6

    def test_exactly_one_incumbent(self) -> None:
        incumbents = [s for s in VARIANT_SPECS if s[1] == "incumbent"]
        assert len(incumbents) == 1


class TestPathAuthority:
    def test_uses_default_repo_root(self) -> None:
        import scripts.run_rank_floor_sweep as mod

        with patch.object(mod, "default_repo_root") as mock:
            mock.return_value = Path("/nonexistent")
            rc = main([])
            mock.assert_called_once()
            assert rc == 1
