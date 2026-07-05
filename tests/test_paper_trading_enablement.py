"""Tests for 105 paper trading enablement (lowered shadow-session threshold).

Paper trading carries zero capital risk. The authorization gate preserves
its full structure (authorization file, canary allowlist, loss budget, kill
switch) but relaxes the shadow-session evidence floor from 5 to 1 when
``paper=True``. Live-mode paths are unchanged.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from renquant_orchestrator.intraday_live_executor import (
    MIN_SHADOW_SESSIONS_CLEAN,
    MIN_SHADOW_SESSIONS_CLEAN_PAPER,
    Stage2Authorization,
    Stage2AuthorizationError,
    load_stage2_authorization,
    resolve_stage2_arming,
)
from renquant_orchestrator.intraday_session_runner import (
    PAPER_PREREG_ID,
    SECTION_9_4_FILENAME,
    SessionRunnerConfig,
)
from renquant_orchestrator.intraday_session_scheduler import (
    KillSwitch,
    load_intraday_config,
)

DAY = "2026-07-06"


def _base_payload(**overrides) -> dict:
    payload = {
        "authorized_by": "renhao",
        "date": "2026-07-05",
        "expiry": "2026-07-31",
        "daily_entry_notional_cap": 500.0,
        "canary_allowlist": ["AAPL", "GOOG"],
        "max_cumulative_loss_usd": 150.0,
        "evidence": {
            "shadow_sessions_clean": 1,
            "replay_audits_green": True,
            "entry_timing_report": "doc/research/entry-timing-readout.md",
        },
    }
    payload.update(overrides)
    return payload


# ---------- constant sanity ----------

def test_paper_floor_is_one():
    assert MIN_SHADOW_SESSIONS_CLEAN_PAPER == 1


def test_live_floor_unchanged():
    assert MIN_SHADOW_SESSIONS_CLEAN == 5


def test_paper_prereg_id_defined():
    assert PAPER_PREREG_ID
    assert "paper" in PAPER_PREREG_ID.lower()


# ---------- Stage2Authorization.from_payload with paper=True ----------

class TestPaperAuthorization:
    def test_paper_mode_accepts_one_session(self):
        auth = Stage2Authorization.from_payload(
            _base_payload(), today=DAY, paper=True
        )
        assert auth.shadow_sessions_clean == 1

    def test_paper_mode_accepts_five_sessions(self):
        payload = _base_payload()
        payload["evidence"]["shadow_sessions_clean"] = 5
        auth = Stage2Authorization.from_payload(
            payload, today=DAY, paper=True
        )
        assert auth.shadow_sessions_clean == 5

    def test_paper_mode_rejects_zero_sessions(self):
        payload = _base_payload()
        payload["evidence"]["shadow_sessions_clean"] = 0
        with pytest.raises(Stage2AuthorizationError, match="floor"):
            Stage2Authorization.from_payload(payload, today=DAY, paper=True)

    def test_live_mode_rejects_one_session(self):
        with pytest.raises(Stage2AuthorizationError, match="floor"):
            Stage2Authorization.from_payload(
                _base_payload(), today=DAY, paper=False
            )

    def test_live_mode_accepts_five_sessions(self):
        payload = _base_payload()
        payload["evidence"]["shadow_sessions_clean"] = 5
        auth = Stage2Authorization.from_payload(
            payload, today=DAY, paper=False
        )
        assert auth.shadow_sessions_clean == 5

    def test_paper_still_requires_allowlist(self):
        payload = _base_payload()
        del payload["canary_allowlist"]
        with pytest.raises(Stage2AuthorizationError, match="canary_allowlist"):
            Stage2Authorization.from_payload(payload, today=DAY, paper=True)

    def test_paper_still_requires_loss_budget(self):
        payload = _base_payload()
        del payload["max_cumulative_loss_usd"]
        with pytest.raises(Stage2AuthorizationError, match="max_cumulative_loss"):
            Stage2Authorization.from_payload(payload, today=DAY, paper=True)

    def test_paper_still_requires_authorized_by(self):
        payload = _base_payload()
        payload["authorized_by"] = ""
        with pytest.raises(Stage2AuthorizationError, match="authorized_by"):
            Stage2Authorization.from_payload(payload, today=DAY, paper=True)

    def test_paper_still_validates_expiry(self):
        payload = _base_payload()
        payload["expiry"] = "2026-01-01"
        with pytest.raises(Stage2AuthorizationError, match="expired"):
            Stage2Authorization.from_payload(payload, today=DAY, paper=True)

    def test_paper_still_requires_replay_green(self):
        payload = _base_payload()
        payload["evidence"]["replay_audits_green"] = False
        with pytest.raises(Stage2AuthorizationError, match="replay_audits_green"):
            Stage2Authorization.from_payload(payload, today=DAY, paper=True)


# ---------- load_stage2_authorization with paper ----------

class TestLoadAuthorizationPaper:
    def test_load_paper_auth_accepts_one_session(self, tmp_path):
        path = tmp_path / "auth.json"
        path.write_text(json.dumps(_base_payload()))
        auth = load_stage2_authorization(path, today=DAY, paper=True)
        assert auth.shadow_sessions_clean == 1

    def test_load_live_auth_rejects_one_session(self, tmp_path):
        path = tmp_path / "auth.json"
        path.write_text(json.dumps(_base_payload()))
        with pytest.raises(Stage2AuthorizationError, match="floor"):
            load_stage2_authorization(path, today=DAY, paper=False)

    def test_load_paper_default_false(self, tmp_path):
        path = tmp_path / "auth.json"
        path.write_text(json.dumps(_base_payload()))
        with pytest.raises(Stage2AuthorizationError, match="floor"):
            load_stage2_authorization(path, today=DAY)


# ---------- resolve_stage2_arming with paper ----------

class TestArmingPaper:
    def _write_auth(self, tmp_path, sessions=1):
        payload = _base_payload()
        payload["evidence"]["shadow_sessions_clean"] = sessions
        path = tmp_path / "stage2_authorization.json"
        path.write_text(json.dumps(payload))
        return path

    def _config(self):
        return load_intraday_config({
            "watchlist": ["AAPL", "GOOG"],
            "intraday_decisioning": {
                "enabled": True,
                "mode": "live",
                "tick_seconds": 1,
                "canary_allowlist": ["AAPL", "GOOG"],
            },
        })

    def test_paper_arms_with_one_session(self, tmp_path):
        auth_path = self._write_auth(tmp_path, sessions=1)
        canary_path = tmp_path / "canary.json"
        kill_path = tmp_path / "kill_file"
        decision = resolve_stage2_arming(
            config=self._config(),
            authorization_path=auth_path,
            canary_state_path=canary_path,
            kill_switch=KillSwitch(kill_path),
            environ={"RENQUANT_INTRADAY_LIVE": "1"},
            today=DAY,
            paper=True,
        )
        assert decision.gates.get("authorization_file_valid") is True

    def test_live_rejects_one_session(self, tmp_path):
        auth_path = self._write_auth(tmp_path, sessions=1)
        canary_path = tmp_path / "canary.json"
        kill_path = tmp_path / "kill_file"
        decision = resolve_stage2_arming(
            config=self._config(),
            authorization_path=auth_path,
            canary_state_path=canary_path,
            kill_switch=KillSwitch(kill_path),
            environ={"RENQUANT_INTRADAY_LIVE": "1"},
            today=DAY,
            paper=False,
        )
        assert decision.gates.get("authorization_file_valid") is False

    def test_paper_default_is_false(self, tmp_path):
        auth_path = self._write_auth(tmp_path, sessions=1)
        canary_path = tmp_path / "canary.json"
        kill_path = tmp_path / "kill_file"
        decision = resolve_stage2_arming(
            config=self._config(),
            authorization_path=auth_path,
            canary_state_path=canary_path,
            kill_switch=KillSwitch(kill_path),
            environ={"RENQUANT_INTRADAY_LIVE": "1"},
            today=DAY,
        )
        assert decision.gates.get("authorization_file_valid") is False


# ---------- SessionRunnerConfig paper field ----------

class TestSessionRunnerConfigPaper:
    def test_default_paper_false(self):
        cfg = SessionRunnerConfig(
            data_root=Path("/tmp/test"),
            strategy_config={"watchlist": []},
        )
        assert cfg.paper is False

    def test_paper_flag_set(self):
        cfg = SessionRunnerConfig(
            data_root=Path("/tmp/test"),
            strategy_config={"watchlist": []},
            paper=True,
        )
        assert cfg.paper is True


# ---------- §9.4 with paper prereg ----------

class TestSection94Paper:
    def test_paper_prereg_id_accepted(self, tmp_path):
        auth_path = tmp_path / "data" / "rq105" / SECTION_9_4_FILENAME
        auth_path.parent.mkdir(parents=True)
        auth_path.write_text(json.dumps({
            "authorized": True,
            "prereg_id": PAPER_PREREG_ID,
        }))
        from renquant_orchestrator.intraday_session_runner import SessionRunner
        runner_cfg = SessionRunnerConfig(
            data_root=tmp_path,
            strategy_config={
                "watchlist": ["AAPL"],
                "intraday_decisioning": {
                    "enabled": True,
                    "mode": "shadow",
                    "tick_seconds": 1,
                },
            },
            paper=True,
        )
        runner = SessionRunner(
            runner_config=runner_cfg,
            tick_runner=lambda **kw: {"intents": [], "scores": {}, "regime": "BULL_CALM"},
            signal_loader=lambda d: {"signal_version": "t", "as_of": d, "source_run_id": "t", "score_content_sha256": "t", "scores": {}},
            session_start_provider=lambda d, n: {"session_date": d, "watchlist": ["AAPL"]},
            live_state_provider=lambda **kw: {"prices": {"AAPL": 200.0}},
        )
        assert runner._check_section_9_4() is True

    def test_section_94_missing_fails(self, tmp_path):
        from renquant_orchestrator.intraday_session_runner import SessionRunner
        runner_cfg = SessionRunnerConfig(
            data_root=tmp_path,
            strategy_config={
                "watchlist": ["AAPL"],
                "intraday_decisioning": {
                    "enabled": True,
                    "mode": "shadow",
                    "tick_seconds": 1,
                },
            },
            paper=True,
        )
        runner = SessionRunner(
            runner_config=runner_cfg,
            tick_runner=lambda **kw: {"intents": [], "scores": {}, "regime": "BULL_CALM"},
            signal_loader=lambda d: {"signal_version": "t", "as_of": d, "source_run_id": "t", "score_content_sha256": "t", "scores": {}},
            session_start_provider=lambda d, n: {"session_date": d, "watchlist": ["AAPL"]},
            live_state_provider=lambda **kw: {"prices": {"AAPL": 200.0}},
        )
        assert runner._check_section_9_4() is False
