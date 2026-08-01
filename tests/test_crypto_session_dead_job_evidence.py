"""The dead-job finding must be auditable from a record, not from prose.

Reviewed `[codex on orch#700]`:

> *"the asserted live state is not auditable from this PR: the 883-run count, exit code,
> stderr evidence, and 13/8 alarm counts exist only as prose, while 'today' becomes stale
> immediately… it must let a later operator distinguish the observed state from a
> narrative before acting on a live job."*

He was right before the ink dried. The first draft said **883 runs**; the capture taken a
few hours later reads **900**. A run count on a job that fires every few minutes is a
moving quantity, and a moving quantity asserted in prose is a narrative.

So the numbers live in `evidence.json` with the capture timestamp, the commands, and the
digests of everything inspected — and these tests check the RECORD's shape and the
document's agreement with it, never the live machine. A test that read `launchctl` would
have exactly the staleness problem it is here to fix, and would pass vacuously on any host
without the job.
"""

from __future__ import annotations

import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
REC = ROOT / "doc/research/evidence/2026-07-31-crypto-session-dead-job/evidence.json"
DOC = ROOT / "doc/progress/2026-07-31-the-killed-crypto-job-still-fires.md"

RECORD = json.loads(REC.read_text(encoding="utf-8"))


def test_the_record_says_WHEN_and_HOW_it_was_captured():
    """Without a timestamp and the command, a reader cannot tell whether they are
    looking at the same state — which is the whole objection."""
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", RECORD["captured_at_utc"])
    assert RECORD["schema"] == "dead_job_evidence.v1"
    cmds = " ".join(RECORD["commands"])
    assert "launchctl print" in cmds
    assert "StandardErrorPath" in cmds


def test_every_inspected_artifact_carries_a_DIGEST():
    """Paths and counts alone are not auditable: a later operator has to be able to
    tell a changed file from a changed claim."""
    for path in (("plist", "sha256"), ("stderr", "sha256"), ("manifest", "sha256")):
        value = RECORD[path[0]][path[1]]
        assert re.fullmatch(r"[0-9a-f]{64}", value), path
    for side in ("dev", "run"):
        assert re.fullmatch(r"[0-9a-f]{40}", RECORD["checkout_identities"][side]["head"])


def test_the_record_is_REDACTED():
    """The operator's home directory is not part of the finding."""
    blob = json.dumps(RECORD)
    assert "/Users/" not in blob, "an un-redacted absolute home path survived"
    assert "$HOME" in blob


def test_the_finding_itself_is_in_the_record_not_only_in_the_prose():
    """The load-bearing facts: the job runs, it always fails, and its target is gone
    from BOTH checkouts. If a future capture shows the target present, this finding is
    over and the test says so rather than the document quietly disagreeing."""
    assert RECORD["target"]["exists_in_dev_checkout"] is False
    assert RECORD["target"]["exists_in_run_checkout"] is False
    assert RECORD["manifest"]["entry_present"] is True
    assert RECORD["launchctl"]["last_exit_code"].endswith("2")
    assert RECORD["stderr"]["n_lines"] > 100


def test_every_stderr_line_is_the_SAME_line():
    """The strongest form of "this job has never done anything": N runs, one distinct
    message. Stated as a measured property of the capture, not as a count that ages."""
    assert RECORD["stderr"]["n_distinct_lines"] == 1
    only = RECORD["stderr"]["distinct_lines"][0]
    assert "can't open file" in only and "crypto_session_runner.py" in only


def test_the_DOCUMENT_quotes_the_record_rather_than_a_remembered_number():
    """The correction that prompted all this: prose and record must not drift. Any run
    count in the document has to be the captured one, and the capture timestamp has to
    appear beside it."""
    doc = DOC.read_text(encoding="utf-8")
    captured_runs = RECORD["launchctl"]["runs"].split("= ")[1]
    assert RECORD["captured_at_utc"] in doc, "the document cites no capture time"
    assert captured_runs in doc, "the document's run count is not the captured one"
    # the superseded number may survive ONLY as the retracted example it now is
    for m in re.finditer(r"\b883\b", doc):
        window = doc[max(0, m.start() - 120):m.start()]
        assert "first draft" in window or "said" in window, \
            "883 is still presented as the current count"


def test_the_alarm_surface_counts_are_MEASURED_and_this_job_is_in_them():
    """The other prose-only numbers codex named. They are now derived from
    `launchctl list` plus the ack ledger, with the ledger's digest recorded, so a
    later reader can tell a changed ledger from a changed claim.

    The load-bearing part is not the totals but the membership: this job is nonzero
    and has NO ack, which is why it occupies a permanent slot in the alarm surface.
    """
    a = RECORD["alarm_surface"]
    assert a["this_job_is_nonzero"] is True
    assert a["this_job_has_an_ack"] is False
    assert "com.renquant.crypto-session" in a["nonzero_without_an_ack"]
    assert a["n_nonzero_with_an_ack"] + a["n_nonzero_without_an_ack"] == a["n_nonzero_jobs"]
    assert re.fullmatch(r"[0-9a-f]{64}", a["ack_ledger"]["sha256"])
    doc = DOC.read_text(encoding="utf-8")
    assert str(a["n_nonzero_jobs"]) in doc and str(a["n_nonzero_without_an_ack"]) in doc
