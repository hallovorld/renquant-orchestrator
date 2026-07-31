"""The AC5 sentinel watched exactly ONE lane. A one-lane sentinel is a one-incident
sentinel.

Both regexes for the new lane were read off the real dated logs before being written
into the module. This suite pins them against the LITERAL log text, because a
refusal pattern that no longer matches its own job's output fails silent -- the same
class of defect the sentinel exists to catch, relocated into the sentinel.
"""

from __future__ import annotations

import datetime as dt
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "ops"))
sys.path.insert(0, str(REPO / "ops" / "renquant104"))

import rq104_silent_refusal_sentinel as srs  # noqa: E402

# Verbatim from logs/rq105/, 2026-07-30.
REFUSAL_LINE = ("run 2026-07-29-live-a68df3f8 fails class-A health evidence: "
                "full_buy_run(pipeline_flags) — a frozen vector must come from a "
                "contract-clean, full-buy-funnel run with training provenance; "
                "refusing to export")
ACTION_LINE = ("exported 85/85 frozen blend scores (coverage 100.0%) from "
               "2026-07-29-live-a68df3f8")


def _lane(name: str) -> srs.WatchedJob:
    return next(j for j in srs.WATCHED if j.name == name)


def test_the_sentinel_watches_more_than_one_lane():
    assert len(srs.WATCHED) >= 2
    assert {"weekly-retrain-patchtst", "rq105-batch-scores-export"} <= {
        j.name for j in srs.WATCHED}


def test_the_refusal_regex_matches_the_REAL_refusal_line():
    assert re.search(_lane("rq105-batch-scores-export").refusal_re, REFUSAL_LINE)


def test_the_action_regex_matches_the_REAL_action_line():
    assert re.search(_lane("rq105-batch-scores-export").action_re, ACTION_LINE)


def test_the_two_regexes_do_not_match_each_other():
    """If either pattern matched both outcomes the lane would report a refusal
    streak on a healthy job, or hide one on a declining job. Either way the sentinel
    would be measuring something other than what its name says."""
    lane = _lane("rq105-batch-scores-export")
    assert not re.search(lane.refusal_re, ACTION_LINE)
    assert not re.search(lane.action_re, REFUSAL_LINE)


def test_the_first_lanes_patterns_are_unchanged():
    """Anti-regression: adding a lane must not perturb the one that already works."""
    first = _lane("weekly-retrain-patchtst")
    assert first.refusal_re == r"promote:\s*refused"
    assert re.search(first.refusal_re, "promote: refused — NOT FRESH (expected)")
    assert re.search(first.action_re, "promote: promoted seed_44")


def test_every_lane_names_a_distinct_log_dir_or_a_distinct_prefix():
    """Two lanes sharing a directory would cross-read each other's dated files.
    rq105/ holds several jobs' logs, so this pins that the outcome patterns are what
    separates them -- and that no two lanes are literally identical."""
    seen = {(j.log_dir, j.refusal_re) for j in srs.WATCHED}
    assert len(seen) == len(srs.WATCHED)


def test_an_unwatchable_lane_is_RECORDED_not_silently_omitted():
    """An unwatched lane nobody wrote down is indistinguishable from one that was
    considered and cleared. weekly-wf-promote has the shape; its dated log surface
    last wrote 2026-05-24."""
    assert "weekly-wf-promote" in srs.UNWATCHABLE_LANES
    reason = srs.UNWATCHABLE_LANES["weekly-wf-promote"]
    assert "2026-05-24" in reason
    assert "dated" in reason.lower()


@pytest.mark.parametrize("line", [
    "no trade (risk_gate_vol_dropped(29))",
    "DECISION | no trade",
    "intraday sell-only: no action",
])
def test_ordinary_no_trade_prose_is_NOT_a_refusal(line):
    """Scoping control. A first sweep matched `daily_104` and `intraday_104` on
    words like 'no-op' and 'skipping' -- normal operation, not a job declining to do
    its job. Building a lane on that would alarm every session."""
    for lane in srs.WATCHED:
        assert not re.search(lane.refusal_re, line), (lane.name, line)


# --- THE HOLE IN MY OWN TESTS -----------------------------------------------------
# The first version of this suite tested only the REGEXES. The lane was configured,
# every test passed, and the lane was BLIND: `_dated_logs` required the whole stem to
# be a date (`2026-07-30.log`), while rq105 writes `batch_scores_export_2026-07-30.log`.
# It found ZERO logs. A configured-but-blind lane is worse than an absent one --- it
# reads as coverage. These are the controls that would have caught it.

def _lane_dirs_present() -> bool:
    """Do any watched log directories exist here?

    The discovery control below reads the real log tree, so it is a statement about
    THIS machine. On a runner no log directory exists, every lane finds nothing, and
    it reports each one "blind" — a red build whose real cause is that there was
    nothing to discover. Same shape as the umbrella, checkout-freshness and
    evidence-glob checks (#634, #637, #635).
    """
    import os
    return any(os.path.isdir(l.log_dir) for l in srs.WATCHED)


#: The log filename each lane must be able to discover, PINNED as a literal.
#:
#: These are not derived from `log_stem_prefix` — that is the whole point. My first
#: version of the test below built the fixture filename FROM the lane's own prefix, so
#: a typo'd prefix produced a typo'd file and the finder still matched it. It could
#: not fail: I verified that by corrupting the prefix and watching it pass. A control
#: whose fixture is generated from the value under test is a tautology, which is the
#: exact defect this suite exists to catch, written into the suite.
#:
#: Read off the real tree 2026-07-30 (the same logs the module's own comment cites).
EXPECTED_LOG_NAMES = {
    "weekly-retrain-patchtst": "2026-07-29.log",
    "rq105-batch-scores-export": "batch_scores_export_2026-07-29.log",
}


def test_every_lane_can_discover_the_log_it_is_supposed_to(tmp_path):
    """The anti-vacuity property, hermetically — this runs EVERYWHERE.

    A lane whose finder matches nothing passes every pattern test ever written. The
    most likely way a lane goes blind is a malformed `log_stem_prefix`, not a missing
    directory — and a prefix typo is invisible to the machine-local test on a box
    where logs happen to exist under the old name.
    """
    as_of = dt.date(2026, 7, 30)
    assert {l.name for l in srs.WATCHED} == set(EXPECTED_LOG_NAMES), (
        "a lane was added or renamed without pinning the filename it must discover; "
        "add it to EXPECTED_LOG_NAMES from the real tree, do not derive it")
    for lane in srs.WATCHED:
        d = tmp_path / lane.name
        d.mkdir()
        (d / EXPECTED_LOG_NAMES[lane.name]).write_text("x")
        found = srs._dated_logs(str(d), as_of=as_of,
                                stem_prefix=lane.log_stem_prefix)
        assert found, (
            f"{lane.name} cannot discover {EXPECTED_LOG_NAMES[lane.name]!r}, the log "
            f"its job actually writes — its log_stem_prefix "
            f"({lane.log_stem_prefix!r}) does not match reality, so the lane is blind "
            f"wherever it runs")


@pytest.mark.skipif(
    not _lane_dirs_present(),
    reason="no watched log directories on this machine — see "
           "test_every_lane_can_discover_a_log_it_is_configured_for for the property "
           "that runs in CI")
def test_every_lane_actually_DISCOVERS_logs_on_this_machine():
    """The control I was missing. A lane whose finder matches nothing passes every
    pattern test ever written.

    Machine-local by construction: it asserts the lane finds logs on the real tree,
    which only means anything where that tree exists. The hermetic test above covers
    the configuration; this one additionally catches a lane pointed at a directory
    that is empty or gone HERE.
    """
    as_of = dt.date(2026, 7, 30)
    for lane in srs.WATCHED:
        found = srs._dated_logs(lane.log_dir, as_of=as_of,
                                stem_prefix=lane.log_stem_prefix)
        assert found, f"{lane.name} discovers no dated logs — the lane is blind"


def test_the_prefix_is_what_separates_jobs_sharing_a_directory(tmp_path):
    """logs/rq105/ holds six jobs' dated logs. A finder that stripped ANY prefix
    would attribute a sibling's refusals to this lane."""
    for name in ("batch_scores_export_2026-07-29.log",
                 "quote_logger_2026-07-29.log",
                 "session_scheduler_2026-07-29.log"):
        (tmp_path / name).write_text("x")
    got = srs._dated_logs(str(tmp_path), as_of=dt.date(2026, 7, 30),
                          stem_prefix="batch_scores_export_")
    assert [p.name for _, p in got] == ["batch_scores_export_2026-07-29.log"]


def test_a_non_date_stem_after_stripping_is_skipped(tmp_path):
    (tmp_path / "batch_scores_export_latest.log").write_text("x")
    (tmp_path / "batch_scores_export_2026-07-29.log").write_text("x")
    got = srs._dated_logs(str(tmp_path), as_of=dt.date(2026, 7, 30),
                          stem_prefix="batch_scores_export_")
    assert len(got) == 1


def test_an_empty_prefix_still_behaves_exactly_as_before(tmp_path):
    """The first lane passes no prefix, so its discovery must not move."""
    (tmp_path / "2026-07-29.log").write_text("x")
    (tmp_path / "stdout.log").write_text("x")
    got = srs._dated_logs(str(tmp_path), as_of=dt.date(2026, 7, 30))
    assert [p.name for _, p in got] == ["2026-07-29.log"]
