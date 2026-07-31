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

MEASURED 2026-08-01:

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
