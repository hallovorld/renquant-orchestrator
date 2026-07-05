"""Tests for ops/renquant105/check_paper_trading_readiness.py (Codex round 4 —
the checker's §9.3a arming-gate check unconditionally read
``data_root / "strategy_config.json"`` while the real launch entrypoints in
this repo (``intraday_session_scheduler.py``, ``intraday_quote_logger.py``,
``train_gbdt.py``) all resolve the strategy config via an explicit
``--strategy-config`` override falling back to
``runtime_paths.default_strategy_config_path()``. That meant the checker
could report readiness against a different config than the one production
would actually launch with. This file proves: (1) an explicit
``--strategy-config`` path is genuinely used, not ignored; (2) absent that,
the checker calls the SAME ``default_strategy_config_path()`` function the
real entrypoints use — not a hardcoded ``data_root``-relative guess."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import mock

import pytest

REPO = Path(__file__).resolve().parent.parent
OPS_DIR = REPO / "ops" / "renquant105"
sys.path.insert(0, str(OPS_DIR))

import check_paper_trading_readiness as checker  # noqa: E402


def _write_strategy_config(path: Path, *, watchlist=None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"watchlist": watchlist or ["AAPL"]}))


class TestExplicitStrategyConfigOverride:
    def test_explicit_strategy_config_path_is_used_over_default(self, tmp_path, monkeypatch):
        """An explicit --strategy-config path must be the one actually read —
        not silently replaced by a data-root-relative guess or the repo default."""
        data_root = tmp_path / "data_root"
        data_root.mkdir()
        explicit_config = tmp_path / "explicit" / "strategy_config.json"
        _write_strategy_config(explicit_config, watchlist=["EXPLICIT_TICKER"])

        # A decoy at the data-root-relative location the pre-fix code hardcoded —
        # if the fix regressed, this is what would get read instead.
        decoy_config = data_root / "strategy_config.json"
        _write_strategy_config(decoy_config, watchlist=["DECOY_TICKER"])

        seen_paths = []
        real_check = checker.check_quintuple_arming_gate

        def _spy(data_root_arg, strategy_config_path_arg):
            seen_paths.append(strategy_config_path_arg)
            return real_check(data_root_arg, strategy_config_path_arg)

        monkeypatch.setattr(checker, "default_data_root", lambda: data_root)
        monkeypatch.setattr(checker, "check_quintuple_arming_gate", _spy)

        checker.main(["--strategy-config", str(explicit_config)])

        assert seen_paths == [explicit_config]
        assert decoy_config not in seen_paths

    def test_no_override_falls_back_to_default_strategy_config_path(self, tmp_path, monkeypatch):
        """Without --strategy-config, main() must call the SAME
        default_strategy_config_path() the real launch entrypoints use — not
        a hardcoded data_root / "strategy_config.json" guess. Proven by making
        the canonical resolver return a sentinel path and asserting the
        checker's gate function is invoked with that exact sentinel, even
        though a decoy file sits at the old hardcoded location."""
        data_root = tmp_path / "data_root"
        data_root.mkdir()
        decoy_config = data_root / "strategy_config.json"
        _write_strategy_config(decoy_config, watchlist=["DECOY_TICKER"])

        sentinel_config = tmp_path / "canonical" / "strategy_config.json"
        _write_strategy_config(sentinel_config, watchlist=["CANONICAL_TICKER"])

        seen_paths = []
        real_check = checker.check_quintuple_arming_gate

        def _spy(data_root_arg, strategy_config_path_arg):
            seen_paths.append(strategy_config_path_arg)
            return real_check(data_root_arg, strategy_config_path_arg)

        monkeypatch.setattr(checker, "default_data_root", lambda: data_root)
        monkeypatch.setattr(checker, "default_strategy_config_path", lambda: sentinel_config)
        monkeypatch.setattr(checker, "check_quintuple_arming_gate", _spy)

        checker.main([])

        assert seen_paths == [sentinel_config]
        assert decoy_config not in seen_paths


class TestCheckQuintupleArmingGateRequiresExplicitPath:
    def test_missing_strategy_config_at_explicit_path_fails_with_remediation(self, tmp_path):
        """check_quintuple_arming_gate no longer derives any path itself —
        it must fail closed (not guess an alternate path) when the passed-in
        path doesn't exist, and the remediation must mention --strategy-config."""
        data_root = tmp_path / "data_root"
        data_root.mkdir()
        missing_path = tmp_path / "does" / "not" / "exist.json"

        result = checker.check_quintuple_arming_gate(data_root, missing_path)

        assert not result.passed
        assert str(missing_path) in result.detail
        assert "--strategy-config" in result.remediation
