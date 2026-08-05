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
        ("j-dated", "jd", "dated_{date}.json", "a dated product"),
    ))
    return logs, pilot


def _touch(path: Path, when: str, *, size: int = 1):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x" * size, encoding="utf-8")
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


class TestAnEmptyLogIsNotEvidence:
    """[codex on orch#815] `session_scheduler_2026-08-04.log` on the live tree is
    0 bytes with birth == mtime — exactly what `>> file` creates BEFORE the
    program writes anything. Calling that RAN is the same wrong-object error
    this probe exists to correct, one level in."""

    def test_a_zero_byte_dated_log_is_LOG_EMPTY_and_ACTIONABLE(self, tree):
        logs, _ = tree
        _touch(logs / f"jnp_{DATE}.log", f"{DATE}T06:25", size=0)
        r = {x["job"]: x for x in P.probe(DATE)}["j-no-product"]
        assert r["state"] == P.STATE_LOG_EMPTY and r["state"] in P.ACTIONABLE
        assert "shell redirection creates the file" in r["detail"]

    def test_a_nonempty_log_is_WROTE_OUTPUT(self, tree):
        logs, _ = tree
        _touch(logs / f"jnp_{DATE}.log", f"{DATE}T06:25", size=12)
        r = {x["job"]: x for x in P.probe(DATE)}["j-no-product"]
        assert r["state"] == P.STATE_RAN

    def test_an_empty_log_is_not_rescued_by_a_fresh_product(self, tree):
        """No evidence the job ran is no evidence, whatever else is fresh."""
        logs, pilot = tree
        _touch(logs / f"jwp_{DATE}.log", f"{DATE}T13:15", size=0)
        _touch(pilot / "product.jsonl", f"{DATE}T13:15")
        r = {x["job"]: x for x in P.probe(DATE)}["j-with-product"]
        assert r["state"] == P.STATE_LOG_EMPTY


class TestADatedProductIsActuallyChecked:
    """[codex on orch#815] batch-scores-export was configured with product=None,
    so the probe reported RAN off the log alone while the PR body cited the json
    file as evidence — a claim the probe did not encode."""

    def test_a_dated_product_template_resolves_per_session(self, tree, tmp_path):
        logs, _ = tree
        _touch(logs / f"jd_{DATE}.log", f"{DATE}T06:15", size=5)
        _touch(P.DATA / f"dated_{DATE}.json", f"{DATE}T06:15")
        r = {x["job"]: x for x in P.probe(DATE)}["j-dated"]
        assert r["state"] == P.STATE_RAN
        assert r["product"].endswith(f"dated_{DATE}.json")

    def test_a_MISSING_dated_product_is_actionable(self, tree):
        logs, _ = tree
        _touch(logs / f"jd_{DATE}.log", f"{DATE}T06:15", size=5)
        r = {x["job"]: x for x in P.probe(DATE)}["j-dated"]
        assert r["state"] == P.STATE_STALE_PRODUCT and "ABSENT" in r["detail"]


class TestTheOutputSaysWhatItMeasured:
    def test_the_render_names_the_wrong_object_explicitly(self, tree):
        logs, _ = tree
        _touch(logs / f"jnp_{DATE}.log", f"{DATE}T06:25", size=4)
        text = P.render(P.probe(DATE), DATE)
        assert "StandardOutPath is NOT the object" in text
        assert "redirect to a dated log" in text

    def test_the_render_states_it_cannot_prove_a_SCHEDULED_firing(self, tree):
        """[codex on orch#815] `shadow_serving_2026-08-04.log` was born 12:41
        against a 13:45 schedule, so a same-day manual run is indistinguishable
        here. The output must say so rather than imply otherwise."""
        logs, _ = tree
        _touch(logs / f"jnp_{DATE}.log", f"{DATE}T06:25", size=4)
        text = P.render(P.probe(DATE), DATE)
        assert "NOT establish that a SCHEDULED firing" in text

    def test_exit_code_is_1_only_when_something_is_actionable(self, tree, capsys):
        logs, pilot = tree
        _touch(logs / f"jwp_{DATE}.log", f"{DATE}T13:15", size=4)
        _touch(pilot / "product.jsonl", f"{DATE}T13:15")
        _touch(logs / f"jnp_{DATE}.log", f"{DATE}T06:25", size=4)
        _touch(logs / f"jd_{DATE}.log", f"{DATE}T06:15", size=4)
        _touch(P.DATA / f"dated_{DATE}.json", f"{DATE}T06:15")
        assert P.main(["--date", DATE]) == 0
        _touch(pilot / "product.jsonl", "2026-08-03T13:15")
        assert P.main(["--date", DATE]) == 1


def test_the_LIVE_2026_08_04_session_refutes_the_stdout_reading():
    """Bound to reality, and NARROWED after review. #621's headline was that
    these jobs had not fired for ~28 days. On the live tree FOUR of six wrote
    non-empty dated logs for 2026-08-04 and their products are fresh — enough to
    refute "silent 28 days". It does NOT claim the loop is healthy: the pairing
    product is a session stale and session-scheduler's log is EMPTY, so that one
    remains unestablished either way. [codex on orch#815]"""
    if not P.LOGS.exists():
        pytest.skip("umbrella logs absent — the unit tests above still ran")
    rows = {r["job"]: r for r in P.probe("2026-08-04")}
    wrote = [j for j, r in rows.items() if r["state"] == P.STATE_RAN]
    assert len(wrote) >= 4, ("the evidence that refutes #621 is gone — re-derive "
                             "before citing that correction", rows)
    for job in ("rq105-quote-logger", "rq105-shadow-serving",
                "rq105-batch-scores-export"):
        assert rows[job]["state"] == P.STATE_RAN, (job, rows[job])
    # and the probe must still be SAYING the two open ones are open
    assert rows["rq105-session-scheduler"]["state"] == P.STATE_LOG_EMPTY
    assert rows["rq105-postclose-pairing"]["state"] == P.STATE_STALE_PRODUCT


def test_the_live_batch_export_entry_actually_has_a_product():
    """[codex on orch#815] It was configured product=None while the write-up
    cited the json file as evidence."""
    entry = next(j for j in P.JOBS if j[0] == "rq105-batch-scores-export")
    assert entry[2] == "batch_scores_{date}.json", entry
