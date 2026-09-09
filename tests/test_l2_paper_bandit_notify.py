"""The MoE L2 lane must SAY what it did — it ran daily with no alert path.

`com.renquant.l2-paper-bandit` has fired every weekday at 15:45 since
2026-09-03 and its only outputs were two JSONL files plus a launchd stdout
log: the operator asked repeatedly to see the MoE messages and there were
none to see (the "deployed-but-dark" class). Worse, the engine's fail-closed
path is the one that MUST be loud — the log is self-verifying and refuses
forever once any replayed row diverges, so a silent REFUSED freezes the lane
indefinitely with no signal at all.

These tests pin: both message shapes, the production-only default (a dry run
into a scratch --log-dir stays silent, which is the documented way to
exercise the engine before 14:30), and that the alert body never claims
profit for what is a paper regret number.

Hermetic: the sender is monkeypatched; nothing posts, no DB is read except
the synthetic ones built here.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from renquant_orchestrator import l2_paper_bandit as l2


LATEST = {
    "asof": "2026-09-08",
    "weights": {"champion_live_blend": 0.5045, "profile_blend": 0.1662,
                "profile_blend_mom": 0.1647, "profile_blend_rb_mom": 0.1646},
    "returns": {"champion_live_blend": 0.008396, "profile_blend": 0.008121,
                "profile_blend_mom": 0.008156, "profile_blend_rb_mom": 0.008003},
}
MIX = {"asof": "2026-09-08", "mixture_value": 1.045261, "champion_value": 1.079581,
       "best_fixed_arm": "champion_live_blend", "mixture_minus_champion": -0.03432}


def test_synced_message_names_every_arm_its_weight_and_the_mixture():
    title, body, prio = l2.format_notification(
        "SYNCED", latest=LATEST, mix_latest=MIX, appended=1)
    assert title == "RenQuant MoE L2 paper-bandit 2026-09-08"
    assert prio == 3
    assert "1 row(s) appended | arms marked: 4" in body
    for arm in LATEST["weights"]:
        assert arm in body
    # champion first (weight-sorted), with its own return rendered as a percent
    assert body.splitlines()[1].startswith("champion_live_blend")
    assert "+0.8396%" in body
    assert "mixture 1.045261 vs champion 1.079581" in body and "-0.03432" in body


def test_synced_message_refuses_to_read_as_a_profit_claim():
    _, body, _ = l2.format_notification("SYNCED", latest=LATEST, mix_latest=MIX)
    assert "PAPER" in body and "not a profitability" in body
    assert "no order is placed" in body


def test_refused_message_is_loud_and_says_the_lane_is_frozen():
    title, body, prio = l2.format_notification("REFUSED", why="arm X: DB missing at /nope")
    assert title == "RenQuant MoE L2 REFUSED"
    assert prio == 4 and prio > l2.format_notification("SYNCED", latest=LATEST)[2]
    assert "appended NOTHING" in body and "arm X: DB missing at /nope" in body
    assert "refuses" in body


def test_unmarked_arm_is_named_not_dropped():
    latest = dict(LATEST, returns={"champion_live_blend": 0.01})
    _, body, _ = l2.format_notification("SYNCED", latest=latest, mix_latest=MIX)
    assert "profile_blend" in body and "unmarked" in body


def test_partial_mixture_does_not_crash_the_message():
    _, body, _ = l2.format_notification("SYNCED", latest=LATEST, mix_latest={})
    assert "champion_live_blend" in body and "mixture " not in body


# ── the production-only default ───────────────────────────────────────────

def _book(path: Path, marks: dict[str, float]) -> None:
    """One arm book in the real schema (`live_state_snapshots`, last snapshot
    of each date wins) — same shape as tests/test_l2_paper_bandit.py builds."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as con:
        con.execute("CREATE TABLE live_state_snapshots (run_date TEXT,"
                    " created_at TEXT, portfolio_value REAL)")
        for d, pv in marks.items():
            con.execute("INSERT INTO live_state_snapshots VALUES (?,?,?)",
                        (d, f"{d} 21:00:00", pv))


@pytest.fixture
def data_root(tmp_path):
    marks = {"2026-09-04": 10000.0, "2026-09-08": 10100.0}
    for rel in l2.ARMS.values():
        _book(tmp_path / rel, marks)
    return tmp_path


def _run(monkeypatch, argv):
    sent = []
    monkeypatch.setattr(l2, "post_ntfy", lambda t, b, topic, **kw: sent.append((t, b, topic, kw)))
    rc = l2.main(argv)
    return rc, sent


def test_production_run_notifies_by_default(monkeypatch, data_root, capsys):
    rc, sent = _run(monkeypatch, ["--data-root", str(data_root)])
    assert rc == 0, capsys.readouterr().out
    assert len(sent) == 1
    title, body, topic, kw = sent[0]
    assert title.startswith("RenQuant MoE L2 paper-bandit")
    assert topic == l2.DEFAULT_NTFY_TOPIC == "renquant"
    assert kw.get("priority") == 3
    # stdout stays ONE parseable JSON object and carries the same words
    payload = json.loads(capsys.readouterr().out)
    assert payload["notification"] == {"title": title, "body": body, "sent": True}


def test_dry_run_into_a_scratch_log_dir_stays_silent(monkeypatch, data_root, tmp_path):
    rc, sent = _run(monkeypatch, ["--data-root", str(data_root),
                                  "--log-dir", str(tmp_path / "scratch")])
    assert rc == 0 and sent == []


def test_flags_override_the_default_both_ways(monkeypatch, data_root, tmp_path):
    _, sent = _run(monkeypatch, ["--data-root", str(data_root),
                                 "--log-dir", str(tmp_path / "s1"), "--notify"])
    assert len(sent) == 1
    _, sent = _run(monkeypatch, ["--data-root", str(data_root), "--no-notify"])
    assert sent == []


def test_refusal_on_the_production_run_pages(monkeypatch, tmp_path, capsys):
    rc, sent = _run(monkeypatch, ["--data-root", str(tmp_path)])   # no arm DBs
    assert rc == 1
    assert len(sent) == 1 and sent[0][0] == "RenQuant MoE L2 REFUSED"
    assert sent[0][3].get("priority") == 4
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "REFUSED" and payload["notification"]["sent"] is True
