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
    ArmDecision,
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
    SessionRunner,
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

    def _make_runner(self, tmp_path):
        return SessionRunner(
            runner_config=SessionRunnerConfig(
                data_root=tmp_path,
                strategy_config={
                    "watchlist": ["AAPL"],
                    "intraday_decisioning": {
                        "enabled": True,
                        "mode": "shadow",
                        "tick_seconds": 1,
                    },
                },
            ),
            tick_runner=lambda **kw: {"intents": [], "scores": {}, "regime": "BULL_CALM"},
            signal_loader=lambda d: {"signal_version": "t", "as_of": d, "source_run_id": "t", "score_content_sha256": "t", "scores": {}},
            session_start_provider=lambda d, n: {"session_date": d, "watchlist": ["AAPL"]},
            live_state_provider=lambda **kw: {"prices": {"AAPL": 200.0}},
        )

    def test_paper_prereg_id_returns_authorized_and_paper(self, tmp_path):
        auth_path = tmp_path / "data" / "rq105" / SECTION_9_4_FILENAME
        auth_path.parent.mkdir(parents=True)
        auth_path.write_text(json.dumps({
            "authorized": True,
            "prereg_id": PAPER_PREREG_ID,
        }))
        runner = self._make_runner(tmp_path)
        ok, is_paper = runner._check_section_9_4()
        assert ok is True
        assert is_paper is True

    def test_section_94_missing_returns_false_false(self, tmp_path):
        runner = self._make_runner(tmp_path)
        ok, is_paper = runner._check_section_9_4()
        assert ok is False
        assert is_paper is False

    def test_non_paper_prereg_returns_authorized_not_paper(self, tmp_path):
        """A non-paper prereg_id authorizes the session but does NOT
        set paper mode — the evidence floor stays at K=5."""
        auth_path = tmp_path / "data" / "rq105" / SECTION_9_4_FILENAME
        auth_path.parent.mkdir(parents=True)
        auth_path.write_text(json.dumps({
            "authorized": True,
            "prereg_id": "some-real-money-prereg",
        }))
        runner = self._make_runner(tmp_path)
        ok, is_paper = runner._check_section_9_4()
        assert ok is True
        assert is_paper is False

    def test_not_authorized_returns_false(self, tmp_path):
        auth_path = tmp_path / "data" / "rq105" / SECTION_9_4_FILENAME
        auth_path.parent.mkdir(parents=True)
        auth_path.write_text(json.dumps({
            "authorized": False,
            "prereg_id": PAPER_PREREG_ID,
        }))
        runner = self._make_runner(tmp_path)
        ok, is_paper = runner._check_section_9_4()
        assert ok is False
        assert is_paper is False

    def test_missing_prereg_id_returns_false(self, tmp_path):
        auth_path = tmp_path / "data" / "rq105" / SECTION_9_4_FILENAME
        auth_path.parent.mkdir(parents=True)
        auth_path.write_text(json.dumps({
            "authorized": True,
        }))
        runner = self._make_runner(tmp_path)
        ok, is_paper = runner._check_section_9_4()
        assert ok is False
        assert is_paper is False


# ---------- _run_live() fails closed on a paper/port-type mismatch ----------

class TestRunLivePaperPortCoupling:
    """The relaxed paper-mode evidence floor must never combine with a real
    submitting broker: _run_live() verifies the ACTUAL port_factory() output
    before any order can be submitted, independent of the declared paper flag."""

    def _armed_decision(self, tmp_path: Path, *, paper: bool) -> ArmDecision:
        payload = _base_payload(prereg_id=PAPER_PREREG_ID if paper else "some-prereg")
        auth = Stage2Authorization.from_payload(payload, today=DAY, paper=paper)
        return ArmDecision(
            armed=True,
            mode_effective="live",
            downgraded=False,
            gates={},
            reasons=(),
            authorization=auth,
        )

    def _runner(self, tmp_path: Path, *, paper: bool, port_factory):
        return SessionRunner(
            runner_config=SessionRunnerConfig(
                data_root=tmp_path,
                strategy_config={
                    "watchlist": ["AAPL"],
                    "intraday_decisioning": {
                        "enabled": True,
                        "mode": "shadow",
                        "tick_seconds": 1,
                    },
                },
                paper=paper,
            ),
            tick_runner=lambda **kw: {"intents": [], "scores": {}, "regime": "BULL_CALM"},
            signal_loader=lambda d: {"signal_version": "t", "as_of": d, "source_run_id": "t", "score_content_sha256": "t", "scores": {}},
            session_start_provider=lambda d, n: {"session_date": d, "watchlist": ["AAPL"]},
            live_state_provider=lambda **kw: {"prices": {"AAPL": 200.0}},
            port_factory=port_factory,
        )

    def test_paper_true_with_non_paper_port_fails_closed(self, tmp_path):
        """paper=True (accepted the relaxed K=1 floor) but port_factory
        constructs something that is NOT a PaperBroker — must raise, not
        silently submit live orders under a relaxed evidence bar."""
        from renquant_orchestrator.intraday_session_runner import SessionRunner

        class _NotAPaperBroker:
            """Stands in for a real live-submitting broker port."""

        runner = self._runner(
            tmp_path, paper=True, port_factory=lambda: _NotAPaperBroker(),
        )
        arming = self._armed_decision(tmp_path, paper=True)

        with pytest.raises(RuntimeError, match="not PaperBroker"):
            runner._run_live(
                arming=arming,
                kill_switch=KillSwitch(tmp_path / "KILL"),
                session_date=DAY,
                now_fn=lambda: __import__("datetime").datetime(2026, 7, 6, 10, 0),
                sleep_fn=lambda s: None,
                max_cycles=1,
            )

    def test_paper_true_with_real_paper_broker_does_not_raise_the_coupling_check(self, tmp_path):
        """paper=True with a genuine PaperBroker port must NOT trip the
        mismatch check (it may still fail/succeed later for unrelated
        reasons — this test only proves the coupling check itself passes).

        Uses a thin PaperBroker subclass adding ``open_orders()`` (aliasing
        the base class's ``get_open_orders()``) purely so this test can walk
        through ``begin_session()``'s reconciliation step — PaperBroker not
        implementing the full BrokerPort protocol is a separate, pre-existing
        gap unrelated to the paper/live coupling fix under test here."""
        from renquant_execution.paper_broker import PaperBroker
        from renquant_orchestrator.intraday_session_runner import SessionRunner

        class _ReconcilableFakePaperBroker(PaperBroker):
            def open_orders(self):
                return self.get_open_orders()

        runner = self._runner(
            tmp_path, paper=True, port_factory=lambda: _ReconcilableFakePaperBroker(),
        )
        arming = self._armed_decision(tmp_path, paper=True)

        # A non-session-day calendar short-circuits immediately after the
        # coupling check, keeping this test focused on that one invariant.
        runner.calendar = _NonSessionCalendarForCoupling()

        result = runner._run_live(
            arming=arming,
            kill_switch=KillSwitch(tmp_path / "KILL"),
            session_date=DAY,
            now_fn=lambda: __import__("datetime").datetime(2026, 7, 6, 10, 0),
            sleep_fn=lambda s: None,
            max_cycles=1,
        )
        assert result.status == "non_session_day"


class _NonSessionCalendarForCoupling:
    name = "test"

    def session_bounds(self, date):
        return None
