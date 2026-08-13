"""Tests for the SessionRunner CLI (RFC #208 deferred 'LiveSessionRunner + CLI').

The load-bearing safety property: with NO §9.4 economic-authorization file
present (the normal state), ``main`` runs a FULL session that self-gates to the
Stage-1 shadow scheduler and submits NOTHING — the broker ``port_factory`` is
never invoked and no live-order artifact is ever written. The CLI mirrors the
shadow scheduler's argument surface and its fail-closed pipeline binding.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from renquant_orchestrator.intraday_live_executor import (
    default_live_actions_path,
    default_live_log_path,
)
from renquant_orchestrator.intraday_session_runner import (
    PAPER_PREREG_ID,
    main as runner_main,
)

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    from backports.zoneinfo import ZoneInfo  # type: ignore[no-redef]

from renquant_common.market_calendar import SessionBounds

ET = ZoneInfo("America/New_York")

SECTION_9_4_REL = Path("data") / "rq105" / "section_9_4_economic_authorization.json"


class _WindowAroundNowCalendar:
    """A calendar whose single session brackets the real wall-clock ``now`` by
    ±1h.

    ``main`` does not inject ``now_fn`` — ``run_session`` uses the real clock —
    so this guarantees one decision tick lands inside the entry window no
    matter when the suite runs, keeping the end-to-end shadow test
    deterministic without wall-clock assumptions.
    """

    name = "around-now"

    def __init__(self) -> None:
        self._now = datetime.now(ET)

    def session_bounds(self, date):  # noqa: ANN001 - test double
        return SessionBounds(
            open=self._now - timedelta(hours=1),
            close=self._now + timedelta(hours=1),
        )


class _NonSessionCalendar:
    name = "holiday"

    def session_bounds(self, date):  # noqa: ANN001 - test double
        return None


def _fake_signal(day: str) -> dict[str, Any]:
    # as_of must strictly predate the (real) session date; a fixed past date
    # always does (§6 class-A leak guard).
    scores = {"AAA": 0.9, "BBB": 0.4}
    return {
        "signal_version": "run-test:cafef00d",
        "as_of": "2020-01-02",
        "source_run_id": "run-test",
        "score_content_sha256": "deadbeef",
        "scores": scores,
    }


def _fake_live_state(**kwargs: Any) -> dict[str, Any]:
    return {
        "as_of": datetime.now(ET).isoformat(),
        "trading_day": str(kwargs.get("trading_day", "")),
        "account": "TEST-ACCT",
        "cash": 1000.0,
        "equity": 2000.0,
        "positions": {},
        "prices": {"AAA": 10.0, "BBB": 20.0},
        "open_buy_reservations": {},
        "unsettled_buys": 0.0,
        "pending_broker_tickers": [],
    }


def _fake_tick_runner(**kwargs: Any) -> dict[str, Any]:
    """A clean would-be BUY (no broker-submission keys). In shadow this is
    logged, never submitted — proving the decision path is exercised."""
    return {
        "enabled": True,
        "reason": "ok",
        "intents": [
            {
                "parent_intent_id": "pi-AAA-BUY-shadow",
                "account": "TEST-ACCT",
                "symbol": "AAA",
                "side": "BUY",
                "kind": "entry",
                "quantity": 1.0,
                "price": 10.0,
                "notional": 10.0,
            }
        ],
        "skipped": [],
        "blocked_by": {},
        "counters": {
            "entries_count": 1,
            "deployed_notional": 10.0,
            "turnover_notional": 10.0,
        },
    }


def _write_strategy_config(tmp_path: Path, *, enabled: bool = True) -> Path:
    cfg = tmp_path / "strategy_config.json"
    cfg.write_text(
        json.dumps(
            {
                "watchlist": ["AAA", "BBB"],
                "intraday_decisioning": {
                    "enabled": enabled,
                    "mode": "shadow",
                    "tick_seconds": 1,
                },
            }
        ),
        encoding="utf-8",
    )
    return cfg


def _read_shadow_ticks(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _patch_frozen_signal(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the class-A frozen-signal loader (which reads runs.alpaca.db) with
    a deterministic double.

    ``main`` has the scheduler CLI's exact injection surface (tick_runner /
    live_state_provider / calendar) and builds the signal loader internally
    from ``load_frozen_daily_signal``; a ticking end-to-end session therefore
    needs the class-A read stubbed, mirroring how the scheduler suite injects a
    fake signal into ``SessionScheduler`` directly. main imports the loader
    lazily by name, so patching the module attribute rebinds it at call time.
    """

    def _loader(*, db_path, session_date, calendar):  # noqa: ANN001 - test double
        return _fake_signal(session_date)

    monkeypatch.setattr(
        "renquant_orchestrator.intraday_session_inputs.load_frozen_daily_signal",
        _loader,
    )


def _run_cli(
    tmp_path: Path,
    cfg: Path,
    *,
    calendar,
    out: Path,
    extra: list[str] | None = None,
) -> int:
    argv = [
        "--strategy-config",
        str(cfg),
        "--data-root",
        str(tmp_path),
        "--out",
        str(out),
        "--json",
        *(extra or []),
    ]
    return runner_main(
        argv,
        tick_runner=_fake_tick_runner,
        live_state_provider=_fake_live_state,
        calendar=calendar,
    )


# ─────────────── (a) full shadow session, no auth files → 0 orders ───────────
def test_cli_full_shadow_session_no_auth_submits_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
):
    monkeypatch.setenv("RENQUANT_INTRADAY_DECISIONING", "1")
    _patch_frozen_signal(monkeypatch)
    cfg = _write_strategy_config(tmp_path)
    out = tmp_path / "shadow.jsonl"

    rc = _run_cli(
        tmp_path, cfg, calendar=_WindowAroundNowCalendar(), out=out,
        extra=["--max-cycles", "1"],
    )
    assert rc == 0
    result = json.loads(capsys.readouterr().out)

    # Shadow by default; nothing armed.
    assert result["mode_effective"] == "shadow"
    assert result["armed"] is False
    assert result["status"] in ("completed", "stopped_max_cycles")

    # A decision tick actually ran (session exercised end-to-end), every
    # recorded tick is shadow — the would-be BUY was logged, never submitted.
    ticks = _read_shadow_ticks(out)
    assert ticks, "expected at least one shadow decision tick"
    assert all(t["mode"] == "shadow" for t in ticks)

    # 0 orders: no §9.4 file was present (or created), and NO live-order
    # artifact was written — the broker port_factory was never invoked.
    assert not (tmp_path / SECTION_9_4_REL).exists()
    assert not default_live_actions_path(tmp_path).exists()
    assert not default_live_log_path(tmp_path).exists()


def test_cli_shadow_even_when_mode_live_requested(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
):
    """``--mode live`` only satisfies arming gate 1; without the §9.4 file (and
    gates 2-5) the session still self-gates to shadow and submits nothing."""
    monkeypatch.setenv("RENQUANT_INTRADAY_DECISIONING", "1")
    _patch_frozen_signal(monkeypatch)
    cfg = _write_strategy_config(tmp_path)
    out = tmp_path / "shadow.jsonl"

    rc = _run_cli(
        tmp_path, cfg, calendar=_WindowAroundNowCalendar(), out=out,
        extra=["--mode", "live", "--max-cycles", "1"],
    )
    assert rc == 0
    result = json.loads(capsys.readouterr().out)
    assert result["mode_effective"] == "shadow"
    assert result["armed"] is False
    assert not default_live_actions_path(tmp_path).exists()
    assert not default_live_log_path(tmp_path).exists()


def test_cli_manifest_flag_overrides_default_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """``--manifest`` redirects the shadow session manifest to the operator
    path instead of the hard-coded ``logs/renquant105_pilot/session_manifest_*``.

    Regression guard: the flag was parsed but ``args.manifest`` was never
    threaded into the runner, so an operator-supplied manifest path was
    silently dropped and the default location was always used (codex PR #977).
    """
    monkeypatch.setenv("RENQUANT_INTRADAY_DECISIONING", "1")
    _patch_frozen_signal(monkeypatch)
    cfg = _write_strategy_config(tmp_path)
    out = tmp_path / "shadow.jsonl"
    custom_manifest = tmp_path / "custom" / "operator-manifest.json"

    rc = _run_cli(
        tmp_path, cfg, calendar=_WindowAroundNowCalendar(), out=out,
        extra=["--manifest", str(custom_manifest), "--max-cycles", "1"],
    )
    assert rc == 0

    # The override path was written (parent dir created on demand) ...
    assert custom_manifest.exists(), "operator --manifest path was ignored"
    written = json.loads(custom_manifest.read_text(encoding="utf-8"))
    assert written.get("status") in ("completed", "stopped_max_cycles")

    # ... and the hard-coded default location was NOT used.
    default_dir = tmp_path / "logs" / "renquant105_pilot"
    assert not list(default_dir.glob("session_manifest_*.json"))


# ─────────────── live-state read account follows the §9.4 gate ───────────
def _write_section_94_paper(tmp_path: Path) -> None:
    d = tmp_path / "data" / "rq105"
    d.mkdir(parents=True, exist_ok=True)
    (d / "section_9_4_economic_authorization.json").write_text(
        json.dumps({"authorized": True, "prereg_id": PAPER_PREREG_ID}),
        encoding="utf-8",
    )


def _spy_live_state_source(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Patch the default ``AlpacaLiveStateSource`` (and its Alpaca deps) with
    light doubles, capturing the ``paper`` kwarg the CLI builds the read source
    with. Returns the capture dict."""
    captured: dict[str, Any] = {}

    class _SpySource:
        def __init__(self, *, quote_source, tickers, order_state_path, paper):  # noqa: ANN001
            captured["paper"] = paper

        def snapshot(self, **kwargs: Any) -> dict[str, Any]:
            return _fake_live_state(**kwargs)

    monkeypatch.setattr(
        "renquant_orchestrator.intraday_session_inputs.AlpacaLiveStateSource",
        _SpySource,
    )
    monkeypatch.setattr(
        "renquant_orchestrator.intraday_quote_logger.AlpacaQuoteSource",
        lambda *a, **k: object(),
    )
    monkeypatch.setattr(
        "renquant_orchestrator.intraday_quote_logger.load_watchlist",
        lambda *a, **k: ["AAA"],
    )
    return captured


def test_cli_live_state_read_account_follows_section_94_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
):
    """A §9.4-PAPER session must read the PAPER book — otherwise sizing reads
    the live account while orders route to PaperBrokerPort (split-brain).

    Non-session calendar so run_session returns before any snapshot()/class-A
    read; the quintuple gate never arms (no stage2 authorization) so nothing
    is submitted — the assertion is purely on the read-source construction.
    """
    monkeypatch.setenv("RENQUANT_INTRADAY_DECISIONING", "1")
    cfg = _write_strategy_config(tmp_path)
    out = tmp_path / "shadow.jsonl"

    _write_section_94_paper(tmp_path)
    captured = _spy_live_state_source(monkeypatch)
    rc = runner_main(
        [
            "--strategy-config", str(cfg),
            "--data-root", str(tmp_path),
            "--out", str(out),
            "--json",
        ],
        tick_runner=_fake_tick_runner,
        calendar=_NonSessionCalendar(),
    )
    assert rc == 0
    assert captured["paper"] is True  # paper book read ⇄ PaperBrokerPort
    result = json.loads(capsys.readouterr().out)
    assert result["mode_effective"] == "shadow"  # not armed: no stage2 auth
    assert not default_live_actions_path(tmp_path).exists()


def test_cli_live_state_read_account_is_live_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """No §9.4 file (the normal shadow state) → the read source is built with
    paper=False (unchanged live read)."""
    monkeypatch.setenv("RENQUANT_INTRADAY_DECISIONING", "1")
    cfg = _write_strategy_config(tmp_path)
    out = tmp_path / "shadow.jsonl"

    captured = _spy_live_state_source(monkeypatch)
    rc = runner_main(
        ["--strategy-config", str(cfg), "--data-root", str(tmp_path), "--out", str(out)],
        tick_runner=_fake_tick_runner,
        calendar=_NonSessionCalendar(),
    )
    assert rc == 0
    assert captured["paper"] is False
    assert not (tmp_path / SECTION_9_4_REL).exists()


# ─────────────── (b) fail-closed without pipeline manifests ───────────
def test_cli_fails_closed_without_pipeline_manifests(tmp_path: Path):
    """No injected tick_runner and no --data-manifest/--artifact-manifest ⇒
    refuse (rc 2), exactly like the shadow scheduler CLI — never guess a
    decision path."""
    cfg = _write_strategy_config(tmp_path)
    rc = runner_main(["--strategy-config", str(cfg), "--data-root", str(tmp_path)])
    assert rc == 2


# ─────────────── deterministic shadow-gating branches ───────────
def test_cli_disabled_config_runs_shadow_and_exits_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
):
    monkeypatch.setenv("RENQUANT_INTRADAY_DECISIONING", "1")
    cfg = _write_strategy_config(tmp_path, enabled=False)
    out = tmp_path / "shadow.jsonl"

    rc = _run_cli(tmp_path, cfg, calendar=_WindowAroundNowCalendar(), out=out)
    assert rc == 0
    result = json.loads(capsys.readouterr().out)
    assert result["mode_effective"] == "shadow"
    assert result["armed"] is False
    assert result["status"] == "disabled_config"
    assert _read_shadow_ticks(out) == []
    assert not default_live_actions_path(tmp_path).exists()


def test_cli_non_session_day_stamps_and_exits_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
):
    monkeypatch.setenv("RENQUANT_INTRADAY_DECISIONING", "1")
    cfg = _write_strategy_config(tmp_path)
    out = tmp_path / "shadow.jsonl"

    rc = _run_cli(tmp_path, cfg, calendar=_NonSessionCalendar(), out=out)
    assert rc == 0
    result = json.loads(capsys.readouterr().out)
    assert result["mode_effective"] == "shadow"
    assert result["status"] == "non_session_day"
    assert _read_shadow_ticks(out) == []
    assert not default_live_actions_path(tmp_path).exists()


def test_cli_env_flag_off_runs_shadow_and_exits_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
):
    monkeypatch.delenv("RENQUANT_INTRADAY_DECISIONING", raising=False)
    cfg = _write_strategy_config(tmp_path)
    out = tmp_path / "shadow.jsonl"

    rc = _run_cli(tmp_path, cfg, calendar=_WindowAroundNowCalendar(), out=out)
    assert rc == 0
    result = json.loads(capsys.readouterr().out)
    assert result["mode_effective"] == "shadow"
    assert result["status"] == "disabled_env_flag"
    assert _read_shadow_ticks(out) == []
    assert not default_live_actions_path(tmp_path).exists()
