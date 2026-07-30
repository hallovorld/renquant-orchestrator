"""A send that fails silently is indistinguishable from one never attempted.

`undelivered_alert_scan.py` matches `ntfy send failed`, which only
`renquant_common.notify.send` emits — the PYTHON senders. This suite covers the
second population: umbrella shell scripts that post with a bare `curl` and throw
the result away. Measured 2026-07-30: 15 such scripts, all 15 blind, 12 scheduled.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
_S = importlib.util.spec_from_file_location("blind", REPO / "ops" / "blind_notifier_scan.py")
blind = importlib.util.module_from_spec(_S)
_S.loader.exec_module(blind)

SEND = 'curl -s -H "Title: $t" -d "$b" "https://ntfy.sh/$TOPIC"'


def _fixture(tmp_path, name, body, scheduled=False):
    d = tmp_path / "scripts"; d.mkdir(exist_ok=True)
    (d / name).write_text(body)
    mf = tmp_path / "m.json"
    jobs = {"com.renquant.x": {"program_args": ["/bin/bash", f"/x/scripts/{name}"]}} if scheduled else {}
    mf.write_text(json.dumps({"jobs": jobs}))
    return d, mf


def test_the_canonical_blind_line_is_caught(tmp_path):
    d, m = _fixture(tmp_path, "a.sh", SEND + " >/dev/null 2>&1 || true\n")
    r = blind.scan(d, m)
    assert r["blind"] == 1
    assert set(r["findings"][0]["silencers"]) == {
        "curl_silent", "output_discarded", "status_discarded"}


def test_a_send_that_KEEPS_its_status_is_not_a_finding(tmp_path):
    """Anti-vacuity. If every send were reported the count would carry no
    information and the tool would be ignored."""
    d, m = _fixture(tmp_path, "b.sh", 'curl -X POST -H "Title: t" "https://ntfy.sh/x"\n')
    r = blind.scan(d, m)
    assert r["blind"] == 0 and r["observable"] == 1


def test_sS_is_NOT_treated_as_silent(tmp_path):
    """`-sS` suppresses the progress meter but KEEPS errors. Matching it would
    report a sender that does report as one that does not."""
    d, m = _fixture(tmp_path, "c.sh", 'curl -sS -d "$b" "https://ntfy.sh/x"\n')
    r = blind.scan(d, m)
    assert r["blind"] == 0, r["findings"]


@pytest.mark.parametrize("line", [
    '# curl -s "https://ntfy.sh/x" >/dev/null || true',
    '   # historical: curl -s ... ntfy.sh ... || true',
])
def test_a_COMMENT_describing_a_send_is_not_a_send(tmp_path, line):
    """Counting prose is how a scan reports a number nobody can act on — the same
    error I made earlier today reading an append-only log."""
    d, m = _fixture(tmp_path, "d.sh", line + "\n")
    assert blind.scan(d, m)["scripts_with_ntfy_sends"] == 0


def test_scheduled_is_read_from_the_manifest_not_guessed(tmp_path):
    d, m = _fixture(tmp_path, "e.sh", SEND + " >/dev/null 2>&1 || true\n", scheduled=True)
    r = blind.scan(d, m)
    assert r["blind_and_scheduled"] == 1 and r["findings"][0]["scheduled"] is True


def test_a_missing_scripts_dir_is_UNUSABLE_not_clean(tmp_path):
    """An absent directory must never read as 'no blind senders'."""
    assert blind.main(["--scripts-dir", str(tmp_path / "nope"),
                       "--manifest", str(MANIFEST)]) == blind.EXIT_UNUSABLE


MANIFEST = REPO / "ops" / "launchd_manifest.json"


def test_the_live_umbrella_still_has_the_measured_population():
    """Regression pin on the real machine. If someone fixes these, this fails and
    the number gets updated deliberately rather than drifting unnoticed."""
    d = Path("/Users/renhao/git/github/RenQuant/scripts")
    if not d.is_dir():
        pytest.skip("umbrella not present")
    r = blind.scan(d, MANIFEST)
    assert r["blind"] >= 12, r["blind"]
    assert r["blind_and_scheduled"] >= 10, r["blind_and_scheduled"]
