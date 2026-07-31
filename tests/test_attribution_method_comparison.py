"""GOAL-5 — correcting orch#676's "7 of 14 attributable".

#676 classified evidence by reading each **wrapper's source** for a date-stamped log
path. That undercounts: it misses any write it cannot parse, and it never looks
outside `RenQuant/logs` — which is where `shadow-ab-daily` writes
(`~/renquant-shadow-ab/logs/2026-07-30_session.log`).

The obvious repair — count dated files in the job's stdout directory — **overcounts**
in the opposite direction: **12 of 14** of those directories are shared, so a dated
file sitting there may belong to any of the jobs writing into it.

Binding a dated file to the job **by name** gives **4 of 14**. That is the number this
file pins, and the structural finding is why the other two are wrong:
**nothing binds a job to its evidence file.**
"""

from __future__ import annotations

import csv
import pathlib

CSV = (pathlib.Path(__file__).resolve().parent.parent
       / "doc/research/evidence/2026-07-31-failing-surface-evidence"
       / "attribution_method_comparison.csv")


def _rows():
    with CSV.open() as fh:
        return list(csv.DictReader(fh))


def test_only_four_jobs_have_evidence_bound_to_them_by_name():
    rows = _rows()
    assert len(rows) == 14
    named = [r for r in rows if int(r["named_for_this_job"]) > 0]
    assert len(named) == 4, [r["job"] for r in named]


def test_the_directory_scan_overcounts_because_directories_are_shared():
    rows = _rows()
    with_dated = [r for r in rows if int(r["dated_files_in_dir"]) > 0]
    shared = [r for r in rows if r["dir_is_shared"] == "True"]
    assert len(with_dated) == 12
    assert len(shared) == 12          # every one of them is contaminated


def test_two_jobs_have_no_dated_file_anywhere_near_them():
    empty = [r for r in _rows() if int(r["dated_files_in_dir"]) == 0]
    assert sorted(r["job"] for r in empty) == [
        "com.renquant.agent-pr-loop", "com.renquant.crypto-session"]


def test_the_two_methods_disagree_which_is_the_point():
    """If both methods agreed, neither would be evidence about the other. They
    bracket the truth from opposite sides: 7 (wrapper regex) and 12 (directory
    scan), with 4 actually bound."""
    rows = _rows()
    by_dir = sum(1 for r in rows if int(r["dated_files_in_dir"]) > 0)
    by_name = sum(1 for r in rows if int(r["named_for_this_job"]) > 0)
    assert by_name < 7 < by_dir
