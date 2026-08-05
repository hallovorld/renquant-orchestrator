"""orch#621 measured the wrong object; this probe measures the right one.

#621 reported four rq105 jobs "silent 28 days — roughly 17-19 missed weekday
firings each", on the evidence of a 0-byte `StandardOutPath` read from each
plist. The plist reading was careful; the OBJECT was wrong. These wrappers
redirect their own output to a DATED log, so `StandardOutPath` stays 0 bytes
forever whether or not the job runs.
"""
from __future__ import annotations

import datetime as dt
import os
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ops" / "renquant105"))
import rq105_job_liveness_probe as P  # noqa: E402

DATE = "2026-08-04"


@pytest.fixture
def tree(tmp_path, monkeypatch):
    logs, pilot, data = tmp_path / "l", tmp_path / "p", tmp_path / "d"
    for d in (logs, pilot, data):
        d.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(P, "LOGS", logs)
    monkeypatch.setattr(P, "PILOT", pilot)
    monkeypatch.setattr(P, "DATA", data)
    monkeypatch.setattr(P, "JOBS", (
        ("j-with-product", "jwp", pilot / "product.jsonl", "the product"),
        ("j-no-product", "jnp", None, "no artefact of its own"),
    ))
    return logs, pilot


def _touch(path: Path, when: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x", encoding="utf-8")
    t = dt.datetime.fromisoformat(when).timestamp()
    os.utime(path, (t, t))


class TestItAsksTheProductNotTheStdout:
    def test_a_fresh_log_and_fresh_product_is_RAN(self, tree):
        logs, pilot = tree
        _touch(logs / f"jwp_{DATE}.log", f"{DATE}T13:15")
        _touch(pilot / "product.jsonl", f"{DATE}T13:15")
        rows = {r["job"]: r for r in P.probe(DATE)}
        assert rows["j-with-product"]["state"] == P.STATE_RAN

    def test_a_fresh_log_with_a_STALE_product_is_its_own_fault(self, tree):
        """A job that ran but produced nothing new is a DIFFERENT fault from one
        that never ran, and must not be reported as the same thing."""
        logs, pilot = tree
        _touch(logs / f"jwp_{DATE}.log", f"{DATE}T13:15")
        _touch(pilot / "product.jsonl", "2026-08-03T13:15")
        r = {x["job"]: x for x in P.probe(DATE)}["j-with-product"]
        assert r["state"] == P.STATE_STALE_PRODUCT and r["state"] in P.ACTIONABLE
        assert "the job ran but its product last changed" in r["detail"]

    def test_an_ABSENT_product_is_actionable_not_silently_fine(self, tree):
        logs, _ = tree
        _touch(logs / f"jwp_{DATE}.log", f"{DATE}T13:15")
        r = {x["job"]: x for x in P.probe(DATE)}["j-with-product"]
        assert r["state"] == P.STATE_STALE_PRODUCT
        assert "ABSENT" in r["detail"]

    def test_no_dated_log_is_NO_LOG_FOR_SESSION(self, tree):
        rows = {r["job"]: r for r in P.probe(DATE)}
        assert rows["j-with-product"]["state"] == P.STATE_NO_LOG
        assert rows["j-with-product"]["state"] in P.ACTIONABLE

    def test_a_job_with_NO_product_is_judged_on_its_log_and_says_so(self, tree):
        """Absence of an artefact must be RECORDED, not treated as health."""
        logs, _ = tree
        _touch(logs / f"jnp_{DATE}.log", f"{DATE}T06:25")
        r = {x["job"]: x for x in P.probe(DATE)}["j-no-product"]
        assert r["state"] == P.STATE_RAN
        assert r["product"] is None
        assert r["product_description"] == "no artefact of its own"


class TestTheOutputSaysWhatItMeasured:
    def test_the_render_names_the_wrong_object_explicitly(self, tree):
        logs, _ = tree
        _touch(logs / f"jnp_{DATE}.log", f"{DATE}T06:25")
        text = P.render(P.probe(DATE), DATE)
        assert "StandardOutPath is NOT the object" in text
        assert "redirect to a dated log" in text

    def test_exit_code_is_1_only_when_something_is_actionable(self, tree, capsys):
        logs, pilot = tree
        _touch(logs / f"jwp_{DATE}.log", f"{DATE}T13:15")
        _touch(pilot / "product.jsonl", f"{DATE}T13:15")
        _touch(logs / f"jnp_{DATE}.log", f"{DATE}T06:25")
        assert P.main(["--date", DATE]) == 0
        _touch(pilot / "product.jsonl", "2026-08-03T13:15")
        assert P.main(["--date", DATE]) == 1


def test_the_LIVE_2026_08_04_session_refutes_the_stdout_reading():
    """Bound to reality. #621's headline was that these jobs had not fired for
    ~28 days. On the live tree the dated logs for 2026-08-04 exist for every one
    of them, and the tick feed and entry-timing shadow were both written that
    session."""
    if not P.LOGS.exists():
        pytest.skip("umbrella logs absent — the unit tests above still ran")
    rows = {r["job"]: r for r in P.probe("2026-08-04")}
    ran = [j for j, r in rows.items() if r["state"] != P.STATE_NO_LOG]
    assert len(ran) >= 5, ("the dated logs that refute #621 are gone — "
                           "re-derive before citing that correction", rows)
    assert rows["rq105-quote-logger"]["state"] == P.STATE_RAN
    assert rows["rq105-shadow-serving"]["state"] == P.STATE_RAN
