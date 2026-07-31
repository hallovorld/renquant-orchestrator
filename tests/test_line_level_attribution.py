"""GOAL-5 — attribution measured at the LINE, with the matching rule stated.

Codex on #676: *"the frozen CSV… never inspects log-line timestamps, run start/end
markers, or proves that a dated filename is uniquely tied to the failing invocation.
An append-only file can still contain attributable per-run records… Narrow this to
filename-level evidence coverage, or add the concrete line or marker evidence and
state the matching rule."*

Correct on every point. Rather than narrow the claim, this measures the thing.

THE MATCHING RULE, stated: a line **self-attributes** iff it begins with an ISO date,
an ISO datetime, or `HH:MM:SS`, optionally preceded by `[` or `"`. A timestamp
elsewhere in the line does not count — it cannot order two lines from different runs.

MEASURED 2026-07-31:

    layer                        lines   self-timestamped
    launchd stdout (14 jobs)      8079        0    (0.000)
    dated wrapper logs (14 files) 3682     1018    (0.276)

The retracted "7 of 14 attributable" headline is replaced by these, which are
supported rather than inferred from filenames.
"""

from __future__ import annotations

import csv
import json
import pathlib
import re

DIR = (pathlib.Path(__file__).resolve().parent.parent
       / "doc/research/evidence/2026-07-31-failing-surface-evidence")
SUMMARY = json.loads((DIR / "line_level_summary.json").read_text(encoding="utf-8"))


def _rows():
    with (DIR / "line_level_attribution.csv").open() as fh:
        return list(csv.DictReader(fh))


def test_the_matching_rule_is_stated_and_is_a_real_regex():
    """A count without its matching rule is not reproducible."""
    rx = re.compile(SUMMARY["matching_rule_regex"])
    assert rx.match("2026-07-31T02:50:24Z ok")
    assert rx.match("[2026-07-31 02:50:24] ok")
    assert rx.match("02:50:24 ok")
    assert not rx.match("ok at 2026-07-31")          # timestamp NOT at line start
    # case-insensitive: the prose writes it as SELF-ATTRIBUTES
    assert "self-attributes" in SUMMARY["matching_rule_prose"].lower()


def test_not_one_launchd_stdout_line_self_attributes():
    """THE finding, now measured at the line rather than inferred from a filename."""
    L = SUMMARY["launchd_stdout"]
    assert L["jobs"] == 14
    assert L["total_lines"] > 8000
    assert L["self_timestamped"] == 0


def test_the_dated_wrapper_layer_is_partly_attributable():
    """CONTROL. If nothing anywhere self-attributed, the rule would be suspect
    rather than the logs. Some wrapper logs are 100% timestamped."""
    W = SUMMARY["dated_wrapper_log_sample"]
    assert W["self_timestamped"] > 1000
    fracs = [float(r["frac_self_timestamped"]) for r in _rows()
             if r["layer"] == "dated_wrapper_log" and r["frac_self_timestamped"]]
    # 0.9969 (324/325), NOT 1.0 -- my first version asserted the value I had read
    # off a 2-decimal printout, which is the assert-the-display-value mistake.
    assert max(fracs) > 0.99
    assert min(fracs) == 0.0                          # and six files are at exactly 0


def test_a_dated_FILENAME_does_not_imply_attributable_LINES():
    """Codex's exact point, measured: files with a date in the name whose lines
    carry no timestamp at all."""
    dated_but_unstamped = [r for r in _rows()
                           if r["layer"] == "dated_wrapper_log"
                           and r["frac_self_timestamped"] not in ("", None)
                           and float(r["frac_self_timestamped"]) == 0.0]
    assert len(dated_but_unstamped) >= 4, dated_but_unstamped


def test_every_failing_job_is_present_in_the_launchd_layer():
    jobs = [r for r in _rows() if r["layer"] == "launchd_stdout"]
    assert len(jobs) == 14
    assert all(int(r["last_exit"]) != 0 for r in jobs)


# ---------------------------------------------------------------------------
# Codex on #676: the census must be auditable and re-runnable.
# ---------------------------------------------------------------------------

def _census():
    return json.loads((DIR / "census.json").read_text(encoding="utf-8"))


def test_every_counted_row_carries_its_source_path_and_a_digest():
    """The ask, made mechanical.

    A basename and a count are not auditable: a reader cannot tell whether the file in
    front of them is the file that was counted. Path + sha256 + byte count + mtime is
    the minimum that makes a number re-derivable.
    """
    rows = [r for r in _census()["rows"] if r.get("present")]
    assert rows, "no counted rows — the census has lost its subjects"
    for r in rows:
        assert r["std_out_path"].startswith("/"), r["label"]
        assert len(r["sha256"]) == 64, r["label"]
        assert r["bytes"] > 0 or r["n_nonblank_lines"] == 0, r["label"]
        assert r["mtime"], r["label"]
        # The plist is pinned too: it decides WHICH file the job writes, so a census
        # that pins the log alone cannot tell a changed log from a redirected one.
        assert len(r["plist_sha256"]) == 64, r["label"]


def test_the_rule_is_stated_and_the_scope_note_refuses_the_wider_claim():
    s = _census()["summary"]
    assert re.compile(s["matching_rule_regex"])
    assert "begins with" in s["matching_rule_prose"]
    assert "does not establish that per-run attribution is impossible" in s["scope_note"]


def test_the_matching_rule_has_a_POSITIVE_CONTROL():
    """A count of zero is worthless if the regex never matches anything.

    Somewhere in the censused population the rule must fire, or "0 self-timestamped" is
    indistinguishable from a broken pattern. Measured 2026-07-31: it fires on 39/39
    lines of one file — 1.00 — so the zeros elsewhere are real zeros.
    """
    rows = [r for r in _census()["rows"] if r.get("present")]
    firing = [r for r in rows if r["n_self_timestamped"] > 0]
    assert firing, "the rule fires nowhere — a zero elsewhere would prove nothing"
    assert max(r["frac_self_timestamped"] for r in firing) == 1.0


def test_an_UNPARSEABLE_plist_is_not_reported_as_an_absent_file():
    """`plistlib` is expat-strict and rejects `--` inside an XML comment; two installed
    plists contain it and are LOADED AND RUNNING.

    Counting them as absent reported a parser limitation as a fact about the run
    surface. The census falls back to `plutil`, as `run_surface_drift_check._plist_load`
    already did. This asserts no row is dropped for that reason.
    """
    rows = _census()["rows"]
    bad = [r for r in rows if not r.get("present")
           and "not well-formed" in str(r.get("why", ""))]
    assert bad == [], bad
    for label in ("com.renquant.weekly-retrain-patchtst",
                  "com.renquant.weekly-tournament-retrain"):
        assert any(r["label"] == label for r in rows), f"{label} missing from the census"


def test_the_WITHDRAWN_claim_is_marked_where_it_was_MADE():
    """The review-surface defect, guarded.

    This document withdraws "attribution is impossible on this surface" in a section
    near the bottom, while the paragraph that made the claim sat 40 lines above it,
    unmarked. A reader who stops at the top comes away with the retracted claim; that
    is the same shape as a PR description outliving its correction, which this
    programme has now hit on four PRs.

    So: any sentence in the document that makes the wider claim must carry a negation
    or a withdrawal marker. Checked at sentence scope rather than by a lookbehind,
    because the negation sits several words from the phrase.
    """
    doc = (pathlib.Path(__file__).resolve().parent.parent
           / "doc/progress/2026-07-31-line-level-attribution.md").read_text("utf-8")
    wider = re.compile(r"attribution is impossible|is measured and \*\*false\*\*"
                       r"|unattributable", re.I)
    excused = re.compile(r"\bnot\b|\bnever\b|\bno\b|n't|~~|withdrawn", re.I)
    for sentence in re.split(r"(?<=[.!?])\s+", doc):
        if wider.search(sentence):
            assert excused.search(sentence), f"unmarked wider claim: {sentence!r}"
