"""Every declared `evidence_glob` must be one Python's `glob` can actually expand.

`launchd_liveness_scan` calls `glob.glob(pattern)`. Python's glob does NOT expand shell
braces, so a `{a,b}_*.log` pattern matches **nothing** — and a job whose evidence glob
matches nothing is reported stale forever. I wrote exactly that pattern for
`rq105-postclose` and it matched 0 files when measured; this pins the class.

These tests deliberately assert NOTHING about what exists on disk. A test that requires
matching files passes or fails according to whose machine it runs on, which this repo has
been bitten by before.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest

MANIFEST = pathlib.Path(__file__).resolve().parent.parent / "ops" / "launchd_manifest.json"


def _globs() -> dict[str, str]:
    jobs = json.loads(MANIFEST.read_text())["jobs"]
    return {k: v["evidence_glob"] for k, v in jobs.items()
            if isinstance(v, dict) and isinstance(v.get("evidence_glob"), str)}


def test_at_least_one_job_declares_an_evidence_glob():
    """Guards against a vacuous suite: if the key were renamed, every test below would
    pass over an empty dict."""
    assert len(_globs()) >= 5


@pytest.mark.parametrize("shell_only", ["{", "}", "$", "~", "`"])  # NOT "[" — see below
def test_no_glob_uses_a_SHELL_construct_python_cannot_expand(shell_only):
    """Braces are the one that bit me; `$VAR` and `~` are the same class — expanded by a
    shell, silently literal to `glob.glob`."""
    for label, pat in _globs().items():
        assert shell_only not in pat, f"{label}: {pat!r} contains {shell_only!r}"


def test_every_glob_is_absolute():
    """`glob.glob` resolves a relative pattern against the CWD, which for a launchd job
    is not a property anyone declared."""
    for label, pat in _globs().items():
        assert pat.startswith("/"), f"{label}: {pat!r}"


def test_every_glob_contains_a_wildcard():
    """A fixed path is not a glob; declaring one would silently pin liveness to a single
    file whose name embeds a date.

    Character classes count: `daily_104/20[0-9][0-9]-...log` is a perfectly good glob, and
    my first version of this test rejected it. Enumerating `*` and `?` and forgetting `[`
    is the same enumeration-with-a-gap shape this repo keeps hitting.
    """
    for label, pat in _globs().items():
        assert any(c in pat for c in "*?["), f"{label}: {pat!r}"


def test_the_two_rq105_globs_added_2026_08_01_are_derived_from_their_scripts():
    """Both were read out of the job's own shell script rather than guessed, and the
    comment records which script and which line pattern."""
    jobs = json.loads(MANIFEST.read_text())["jobs"]
    for label, script in (
        ("com.renquant.rq105-batch-scores-export", "run_batch_scores_export.sh"),
        ("com.renquant.rq105-postclose", "run_postclose_loggers.sh"),
    ):
        c = jobs[label]["_evidence_glob_comment"]
        assert script in c, label
        assert "$TS" in c or "${MOD}" in c, label


def test_the_postclose_comment_records_WHY_only_one_module_is_declared():
    """One module, not both — and the reason (Python glob has no brace expansion, and
    the choice errs toward alarming) has to travel with the decision."""
    c = json.loads(MANIFEST.read_text())["jobs"][
        "com.renquant.rq105-postclose"]["_evidence_glob_comment"]
    assert "does NOT expand shell braces" in c
    assert "matched 0 files" in c
    assert "erring toward alarming" in c


def test_no_glob_points_outside_a_logs_directory():
    """An evidence surface is a log. A glob over an artifact or config directory would
    make liveness track something the job does not write on every run."""
    for label, pat in _globs().items():
        assert re.search(r"/logs?/", pat), f"{label}: {pat!r}"
