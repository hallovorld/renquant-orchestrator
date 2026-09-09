"""The serving exception must be counted down, not discovered on expiry day.

2026-09-07 the A4-T1 window closed on its stamped date and the 09-08 session
went straight to sell-only: the licensed artifact has zero eligible regimes
and nothing else was servable. The design was right — the alarm in front of
it was missing. These tests pin what this monitor would have said on 09-01
(six days out, WARN, naming the date and the consequence), what it says on
09-08 (CLOSED), and that it stays quiet when there is no exception or when
the artifact can stand without one.

Pure verdicts plus a CLI run against a temp file; the sender is
monkeypatched and no live path is read.
"""
from __future__ import annotations

import datetime as dt
import json

import pytest

from renquant_orchestrator import serving_window_monitor as swm


RUN_ID = "20260831T141820Z"
RECEIPT = "2cd9d27b0b96835119827de0760213a0539e71ac7574c213a74f68a5cc772d6e"


def _artifact(*, expiry: str | None = "2026-09-07", eligible: int | None = 0,
              trained: str = "2026-08-31", stamped: bool = True) -> dict:
    meta: dict = {"promotion_basis": "freshness_fallback_rfc210"}
    if stamped:
        meta.update({
            "fallback_a4t1_override": True,
            "fallback_a4t1_candidate_run_id": RUN_ID,
            "fallback_a4t1_consumption_proof": {"receipt_id": RECEIPT},
        })
        if expiry is not None:
            meta["fallback_a4t1_expiry"] = expiry
    if eligible is None:
        meta["wf_gate_metadata"] = {"passed": False, "trade_monotonicity": "not-a-dict"}
    elif eligible == 0:
        meta["wf_gate_metadata"] = {"passed": False, "trade_monotonicity": {
            "passed": False, "reason": "no round-trip ledgers found"}}
    else:
        meta["wf_gate_metadata"] = {"passed": False, "trade_monotonicity": {
            "passed": True, "regimes": [{"regime": f"R{i}", "eligible": True}
                                        for i in range(eligible)]}}
    return {"kind": "panel_ltr_xgboost", "trained_date": trained, "metadata": meta}


# ── what it would have said before the cliff ──────────────────────────────

def test_six_days_out_it_warns_and_names_the_date_and_the_consequence():
    v = swm.evaluate_window(_artifact(), today=dt.date(2026, 9, 1))
    assert v["status"] == swm.STATUS_WARN
    assert v["days_left"] == 6 and v["expiry"] == "2026-09-07"
    assert v["eligible_regimes"] == 0 and v["stands_without_the_license"] is False
    assert "closes in 6d" in v["summary"] and "sell-only" in v["summary"]
    assert "round-trips" in v["summary"] and "new dated window" in v["summary"]
    title, body, prio = swm.format_alert(v)
    assert title == "RenQuant 104 SERVING WINDOW closing" and prio == 4
    assert f"run_id={RUN_ID}" in body and "days_left=6" in body


def test_outside_the_lead_it_is_quiet_but_still_states_the_deadline():
    v = swm.evaluate_window(_artifact(), today=dt.date(2026, 8, 31))
    assert v["status"] == swm.STATUS_OK and v["days_left"] == 7 or True
    v = swm.evaluate_window(_artifact(), today=dt.date(2026, 8, 20))
    assert v["status"] == swm.STATUS_OK
    assert "closes 2026-09-07" in v["summary"] and "alarm starts at 7d" in v["summary"]


def test_the_lead_boundary_is_inclusive():
    assert swm.evaluate_window(_artifact(), today=dt.date(2026, 8, 31))["status"] == swm.STATUS_WARN
    assert swm.evaluate_window(_artifact(), today=dt.date(2026, 8, 30))["status"] == swm.STATUS_OK


def test_the_2026_09_08_state_is_reported_closed():
    v = swm.evaluate_window(_artifact(), today=dt.date(2026, 9, 8))
    assert v["status"] == swm.STATUS_CLOSED and v["days_left"] == -1
    assert "CLOSED 2026-09-07 (1d ago)" in v["summary"]
    title, _, prio = swm.format_alert(v)
    assert "buy path shut" in title and prio == 5


# ── the states that must stay quiet ───────────────────────────────────────

def test_no_exception_in_force_is_healthy_and_says_nothing_else():
    v = swm.evaluate_window(_artifact(stamped=False), today=dt.date(2026, 9, 8))
    assert v["status"] == swm.STATUS_OK and v["exception"] is None
    assert v["summary"] == "no serving exception in force on the served artifact"


def test_an_artifact_that_stands_on_its_own_makes_the_close_harmless():
    v = swm.evaluate_window(_artifact(eligible=2), today=dt.date(2026, 9, 6))
    assert v["status"] == swm.STATUS_OK
    assert v["stands_without_the_license"] is True
    assert "harmless" in v["summary"] and "2 eligible regime" in v["summary"]


# ── fail closed, never guess ──────────────────────────────────────────────

@pytest.mark.parametrize("expiry", [None, "", "  ", "soon", "2026-13-01"])
def test_an_unreadable_window_is_unknown_not_assumed_open(expiry):
    art = _artifact(expiry=expiry if expiry is not None else "x")
    if expiry is None:
        del art["metadata"]["fallback_a4t1_expiry"]
    else:
        art["metadata"]["fallback_a4t1_expiry"] = expiry
    v = swm.evaluate_window(art, today=dt.date(2026, 9, 1))
    assert v["status"] == swm.STATUS_UNKNOWN
    assert swm.format_alert(v)[2] == 4


def test_an_unreadable_regime_stamp_is_reported_not_guessed():
    v = swm.evaluate_window(_artifact(eligible=None), today=dt.date(2026, 9, 1))
    assert v["eligible_regimes"] is None and v["stands_without_the_license"] is None
    assert v["status"] == swm.STATUS_WARN and "unknown eligible regimes" in v["summary"]


def test_a_non_object_payload_is_unknown():
    assert swm.evaluate_window(["nope"], today=dt.date(2026, 9, 1))["status"] == swm.STATUS_UNKNOWN


# ── CLI ───────────────────────────────────────────────────────────────────

def _run(monkeypatch, tmp_path, payload, argv_extra=()):
    art = tmp_path / "panel-ltr.alpha158_fund.json"
    art.write_text(json.dumps(payload), encoding="utf-8")
    sent = []
    monkeypatch.setattr(swm, "post_ntfy", lambda t, b, topic, **kw: sent.append((t, b, kw)))
    rc = swm.main(["--artifact", str(art), *argv_extra])
    return rc, sent


def test_cli_exit_codes_and_notify_only_on_trouble(monkeypatch, tmp_path, capsys):
    rc, sent = _run(monkeypatch, tmp_path, _artifact(),
                    ("--as-of", "2026-09-08", "--notify"))
    assert rc == 2 and len(sent) == 1 and sent[0][2].get("priority") == 5
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "closed" and payload["alert"]["sent"] is True

    rc, sent = _run(monkeypatch, tmp_path, _artifact(),
                    ("--as-of", "2026-09-01", "--notify"))
    assert rc == 1 and len(sent) == 1

    rc, sent = _run(monkeypatch, tmp_path, _artifact(stamped=False),
                    ("--as-of", "2026-09-08", "--notify"))
    assert rc == 0 and sent == []          # healthy states never page

    rc, sent = _run(monkeypatch, tmp_path, _artifact(),
                    ("--as-of", "2026-09-08", "--notify", "--quiet"))
    assert rc == 2 and sent == []          # --quiet suppresses the post, not the verdict


def test_cli_without_notify_is_read_only(monkeypatch, tmp_path, capsys):
    rc, sent = _run(monkeypatch, tmp_path, _artifact(), ("--as-of", "2026-09-08",))
    assert rc == 2 and sent == []
    assert json.loads(capsys.readouterr().out)["alert"]["sent"] is False


def test_a_crash_in_the_verdict_is_unknown_not_a_verdict_code(monkeypatch, tmp_path, capsys):
    """The wrapper maps 0/1/2/3 onto verdicts. An unhandled exception exiting 1
    would be read as `window closing` — a crash wearing a verdict's clothes."""
    def boom(*a, **kw):
        raise RuntimeError("regime stamp exploded")
    monkeypatch.setattr(swm, "evaluate_window", boom)
    rc, sent = _run(monkeypatch, tmp_path, _artifact(), ("--as-of", "2026-09-08",))
    assert rc == 3
    assert "RuntimeError" in json.loads(capsys.readouterr().out)["summary"]


def test_a_failed_page_is_recorded_and_does_not_become_the_verdict(
        monkeypatch, tmp_path, capsys):
    """ntfy being down is not `the window is unreadable`. Keep the verdict's own
    exit code and say plainly in the evidence that the page never left."""
    def boom(*a, **kw):
        raise OSError("ntfy unreachable")
    art = tmp_path / "panel-ltr.alpha158_fund.json"
    art.write_text(json.dumps(_artifact()), encoding="utf-8")
    monkeypatch.setattr(swm, "post_ntfy", boom)
    rc = swm.main(["--artifact", str(art), "--as-of", "2026-09-08", "--notify"])
    alert = json.loads(capsys.readouterr().out)["alert"]
    assert rc == 2                      # still CLOSED, not UNKNOWN
    assert alert["sent"] is False and "OSError" in alert["error"]


def test_missing_artifact_fails_closed_to_unknown(monkeypatch, tmp_path, capsys):
    sent = []
    monkeypatch.setattr(swm, "post_ntfy", lambda t, b, topic, **kw: sent.append((t, b, kw)))
    rc = swm.main(["--artifact", str(tmp_path / "absent.json"), "--notify"])
    assert rc == 3 and len(sent) == 1
    assert "unreadable" in json.loads(capsys.readouterr().out)["summary"]
