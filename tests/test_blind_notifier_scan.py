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
    assert r["delivery_unobservable"] == 1
    f = r["findings"][0]
    assert f["delivery_unobservable_lines"] == 1
    assert set(f["attributes"]) == {"curl_silent", "output_discarded"}


# --- NEGATIVE CONTROLS, one per individual silencer (codex BLOCKER on #646) -------
# The first predicate fired on ANY ONE of three tokens. `curl -s` still hands its
# exit status to the caller; so does a redirect. Neither alone establishes that the
# result was discarded, so neither alone may produce a finding. One test per token so
# the overbreadth cannot come back a piece at a time.

@pytest.mark.parametrize("line,why", [
    ('curl -s -d "$b" "https://ntfy.sh/x"', "-s alone: status still returned"),
    ('curl -d "$b" "https://ntfy.sh/x" >/dev/null', "redirect alone: status still returned"),
    ('curl -d "$b" "https://ntfy.sh/x" 2>&1', "stderr merge alone"),
    ('curl -s -d "$b" "https://ntfy.sh/x" >/dev/null 2>&1', "-s AND redirect, still no discard"),
])
def test_a_silencer_WITHOUT_a_status_discard_is_not_a_finding(tmp_path, line, why):
    d, m = _fixture(tmp_path, "n.sh", line + "\n")
    r = blind.scan(d, m)
    assert r["delivery_unobservable"] == 0, f"{why}: {r['findings']}"
    assert r["observable"] == 1


@pytest.mark.parametrize("tok", ["|| true", "||true", "|| :", "||:", "; true"])
def test_each_status_discarding_form_IS_recognised(tmp_path, tok):
    """Each spelling must be recognised, or the predicate is conservative in a way
    that hides real cases. CORRECTED at codex round 2 on #646: recognition alone no
    longer produces a finding -- evidence suppression is required too, so the fixture
    carries both."""
    d, m = _fixture(tmp_path, "y.sh",
                    f'curl -d "$b" "https://ntfy.sh/x" >/dev/null 2>&1 {tok}\n')
    assert blind.scan(d, m)["delivery_unobservable"] == 1, tok


@pytest.mark.parametrize("tok", ["|| true", "||true", "|| :", "||:", "; true"])
def test_each_form_WITHOUT_suppression_lands_in_status_ignored(tmp_path, tok):
    """The other half: every spelling must be seen by the weak category too, or a
    status discard could vanish from both buckets."""
    d, m = _fixture(tmp_path, "y2.sh", f'curl -d "$b" "https://ntfy.sh/x" {tok}\n')
    r = blind.scan(d, m)
    assert r["delivery_unobservable"] == 0 and r["status_ignored_only"] == 1, tok


def test_a_status_discard_ALONE_is_status_ignored_NOT_unobservable(tmp_path):
    """CORRECTED (codex round 2 on #646). The earlier version of this test asserted
    the opposite and was wrong: `|| true` discards the SHELL status, but curl still
    writes its error to stderr and that reaches the job log. An error visible in the
    log IS delivery evidence. Status discard establishes "status ignored", never
    "delivery unobservable"."""
    d, m = _fixture(tmp_path, "z.sh", 'curl -d "$b" "https://ntfy.sh/x" || true\n')
    r = blind.scan(d, m)
    assert r["delivery_unobservable"] == 0, r["findings"]
    assert r["status_ignored_only"] == 1


def test_evidence_suppression_ALONE_is_also_not_enough(tmp_path):
    """The symmetric control: output gone but status returned means a caller could
    still act on the failure."""
    d, m = _fixture(tmp_path, "q.sh", 'curl -d "$b" "https://ntfy.sh/x" >/dev/null\n')
    r = blind.scan(d, m)
    assert r["delivery_unobservable"] == 0 and r["status_ignored_only"] == 0


# --- PER-STREAM semantics (codex round 3 on #646) --------------------------------
# `>/dev/null` kills the RESPONSE BODY on stdout; curl's errors are on stderr and
# still reach the job log. `-s` kills curl's stderr output; the response body still
# lands on stdout. Either alone leaves the other stream visible, so neither alone
# can support "delivery unobservable". These are the two controls review asked for.

def test_status_discard_plus_STDOUT_ONLY_redirect_is_AMBIGUOUS(tmp_path):
    """curl errors are still on stderr and still reach the job log."""
    d, m = _fixture(tmp_path, "a1.sh",
                    'curl -d "$b" "https://ntfy.sh/x" >/dev/null || true\n')
    r = blind.scan(d, m)
    assert r["delivery_unobservable"] == 0, r["findings"]
    assert r["ambiguous_one_stream"] == 1


def test_status_discard_plus_s_WITHOUT_stdout_redirect_is_AMBIGUOUS(tmp_path):
    """The response body is still on stdout and still reaches the job log."""
    d, m = _fixture(tmp_path, "a2.sh",
                    'curl -s -d "$b" "https://ntfy.sh/x" || true\n')
    r = blind.scan(d, m)
    assert r["delivery_unobservable"] == 0, r["findings"]
    assert r["ambiguous_one_stream"] == 1


@pytest.mark.parametrize("both", [
    '>/dev/null 2>&1 || true',
    '-s >/dev/null || true',
    '-o /dev/null 2>/dev/null || true',
])
def test_BOTH_streams_silenced_IS_the_strong_finding(tmp_path, both):
    """Anti-vacuity for the per-stream rule: a predicate strict enough to accept
    nothing would erase the population it exists to count."""
    d, m = _fixture(tmp_path, "b1.sh", f'curl -d "$b" "https://ntfy.sh/x" {both}\n')
    assert blind.scan(d, m)["delivery_unobservable"] == 1, both


def test_BOTH_together_are_unobservable(tmp_path):
    d, m = _fixture(tmp_path, "r.sh",
                    'curl -d "$b" "https://ntfy.sh/x" >/dev/null 2>&1 || true\n')
    assert blind.scan(d, m)["delivery_unobservable"] == 1


# --- the send recogniser must establish an actual POST ---------------------------

@pytest.mark.parametrize("line", [
    'echo "would curl https://ntfy.sh/x"',
    'URL="https://ntfy.sh/$TOPIC"   # curl target',
    'curl -I "https://ntfy.sh/x" >/dev/null 2>&1 || true',
    'curl "https://ntfy.sh/x" >/dev/null 2>&1 || true',
])
def test_a_line_that_is_not_a_POST_is_not_counted(tmp_path, line):
    """A line merely containing `curl` and `ntfy.sh` can be an echo, a comment
    fragment, a variable, or a GET. Counting them inflates a population whose whole
    value is that every member really sends."""
    d, m = _fixture(tmp_path, "p.sh", line + "\n")
    r = blind.scan(d, m)
    assert r["scripts_with_ntfy_sends"] == 0, r


@pytest.mark.parametrize("flag", ["-d ", "--data", "-X POST", "-T ", "--upload-file"])
def test_each_POST_form_IS_recognised(tmp_path, flag):
    """Anti-vacuity for the recogniser: a rule strict enough to see nothing would
    make the whole measurement vanish."""
    d, m = _fixture(tmp_path, "s.sh",
                    f'curl {flag} "$b" "https://ntfy.sh/x" >/dev/null 2>&1 || true\n')
    assert blind.scan(d, m)["delivery_unobservable"] == 1, flag


def test_a_send_that_KEEPS_its_status_is_not_a_finding(tmp_path):
    """Anti-vacuity. If every send were reported the count would carry no
    information and the tool would be ignored."""
    d, m = _fixture(tmp_path, "b.sh", 'curl -X POST -H "Title: t" "https://ntfy.sh/x"\n')
    r = blind.scan(d, m)
    assert r["delivery_unobservable"] == 0 and r["observable"] == 1


def test_sS_is_NOT_treated_as_silent(tmp_path):
    """`-sS` suppresses the progress meter but KEEPS errors. Matching it would
    report a sender that does report as one that does not."""
    d, m = _fixture(tmp_path, "c.sh", 'curl -sS -d "$b" "https://ntfy.sh/x"\n')
    r = blind.scan(d, m)
    assert r["delivery_unobservable"] == 0, r["findings"]


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
    assert r["delivery_unobservable_and_scheduled"] == 1 and r["findings"][0]["scheduled"] is True


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
    assert r["delivery_unobservable"] >= 12, r["delivery_unobservable"]
    assert r["delivery_unobservable_and_scheduled"] >= 10, r["delivery_unobservable_and_scheduled"]
    # Measured 2026-07-30 under the strict recogniser AND the two-condition
    # predicate: 15 / 12 / 0 — identical to the loose version, so nothing was being
    # counted that should not have been. The number was right; the definition was not.
    assert r["status_ignored_only"] == 0
    # Per-stream re-measure, codex round 3: all 16 POST lines silence BOTH streams,
    # so the ambiguous bucket is empty. If a future edit drops one stream's
    # redirect, that line moves here instead of silently keeping the strong claim.
    assert r["ambiguous_one_stream"] == 0
