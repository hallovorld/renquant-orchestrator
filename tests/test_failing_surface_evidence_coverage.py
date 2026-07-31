"""GOAL-5 — half the currently-failing scheduled surface cannot be dated from its own output.

Measured 2026-07-31 over every `com.renquant.*` job whose launchctl last exit is
nonzero (n=14): **7 produce dated evidence, 7 produce only append-only undated
evidence**, and **0 of 14** plists give their `StandardOutPath` a dated filename.

That matters because `launchctl` retains a job's last exit **until its next run**, so
the exit code alone dates nothing. When the only other artefact is a flat append-only
file, no line in it can be attributed to a run — the trap this session has paid for
repeatedly, here measured across the whole failing surface rather than one job.

Read from a frozen CSV: re-deriving it at test time would measure the operator's
machine, which is the other recurring shape in this repo.
"""

from __future__ import annotations

import csv
import pathlib

CSV = (pathlib.Path(__file__).resolve().parent.parent
       / "doc/research/evidence/2026-07-31-failing-surface-evidence"
       / "evidence_coverage.csv")


def _rows():
    with CSV.open() as fh:
        return list(csv.DictReader(fh))


def test_half_the_failing_surface_is_not_attributable():
    rows = _rows()
    assert len(rows) == 14
    yes = [r for r in rows if r["attributable"] == "yes"]
    no = [r for r in rows if r["attributable"] == "no"]
    assert len(yes) == 7 and len(no) == 7


def test_no_plist_gives_its_stdout_a_dated_name():
    """THE structural finding. Every StandardOutPath is a flat file, so the launchd
    stream layer is undated across the ENTIRE failing surface — which is why seven
    jobs relying on it alone cannot be dated."""
    rows = _rows()
    assert all(r["std_out_dated"] == "False" for r in rows)


def test_every_job_has_a_nonzero_exit_recorded():
    """Anti-vacuity: the population is the FAILING surface, not all jobs."""
    assert all(int(r["last_exit"]) != 0 for r in _rows())


def test_the_dated_ones_really_are_dated_in_the_wrapper():
    """Control on the classifier: 'attributable' must trace to a concrete mechanism,
    not be assigned by default."""
    for r in _rows():
        if r["attributable"] == "yes":
            assert r["wrapper_writes"] == "dated" or r["std_out_dated"] == "True", r


def test_one_wrapper_could_not_be_classified_and_is_reported_as_such():
    """A wrapper the classifier cannot read is recorded `unresolvable`, never
    silently counted as fine — the fail-open default this repo keeps re-learning."""
    unresolvable = [r for r in _rows() if r["wrapper_writes"] == "unresolvable"]
    assert len(unresolvable) == 1
    assert unresolvable[0]["attributable"] == "no"
