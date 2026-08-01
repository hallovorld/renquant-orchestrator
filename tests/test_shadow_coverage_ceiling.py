"""A coverage FRACTION above 1 is not a health verdict — it is an undescribable record.

Measured 2026-08-01 on the live health log: `topdecile_clf_blend_leg` reported
`coverage_frac` > 1.0 on 6 of 6 days (85 scored vs 77 candidates on 07-28, peak 1.1039)
while `hf_patchtst` was exactly 1.0000 every day. Nothing flagged it.

Two reasons it survived, and the second is the one worth remembering:
  * the only coverage check was a FLOOR — a fraction cannot be too small AND too large
    under one comparison;
  * that floor lives in the DB-fallback branch, which these records never reach. They
    carry an explicit `status`, so the producer's verdict is passed through untouched.
    My first fix added a ceiling next to the floor and CHANGED NOTHING — the branch does
    not run. The check had to move ahead of the status branch, and firing on the real
    records is what proved it.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

OPS = pathlib.Path(__file__).resolve().parent.parent / "ops" / "renquant104"
sys.path.insert(0, str(OPS))

import rq104_shadow_scorer_sentinel as S  # noqa: E402


def _rec(**over):
    """The REAL record class is `ShadowHealthRecord`, and the classifier is `classify`
    (no leading underscore). My first fixture invented `LaneDay` and `_classify` — caught
    instantly by AttributeError, which is the difference between a wrong NAME and a wrong
    KEY: the first fails loudly, the second returns None and reads as a measurement.
    """
    d = dict(run_date="2026-07-31", shadow_name="topdecile_clf_blend_leg",
             feed_present=True, loaded=True, n_scored=80, n_candidates=80,
             coverage_frac=1.0, staleness_days=1, reasons=[], state=None,
             load_error=None, status=S.STATUS_OK)
    d.update(over)
    return S.ShadowHealthRecord(
        **{k: v for k, v in d.items() if k in S.ShadowHealthRecord.__dataclass_fields__})


# --------------------------------------------------------------- the ceiling --
def test_coverage_above_one_is_MALFORMED_not_healthy():
    """The live shape: status says OK, and the number cannot be a coverage."""
    st, why = S.classify(_rec(coverage_frac=1.1039, n_scored=85, n_candidates=77))
    assert st == S.MALFORMED_RECORD
    assert "1.1039" in why[0] and "n_scored=85" in why[0] and "n_candidates=77" in why[0]


def test_exactly_one_is_HEALTHY_because_that_is_the_normal_case():
    """`hf_patchtst` reports 1.0000 every day. A `>= 1.0` ceiling would alarm on every
    fully-covered lane forever."""
    st, _ = S.classify(_rec(coverage_frac=1.0))
    assert st == S.HEALTHY


def test_the_ceiling_runs_EVEN_WHEN_the_producer_says_OK():
    """The defect's real cause: the coverage floor sits in the DB-fallback branch, which
    a record carrying `status` never reaches. A ceiling added beside the floor changes
    nothing."""
    for status in (S.STATUS_OK, S.STATUS_EXPECTED_SKIP):
        st, _ = S.classify(_rec(coverage_frac=1.05, n_scored=84, n_candidates=80,
                                 status=status))
        assert st == S.MALFORMED_RECORD, status


def test_the_ceiling_also_runs_when_the_producer_says_FAULT():
    """The clf lane was ALREADY alarming for staleness — an impossible number must not
    ride along inside a message about something else."""
    st, why = S.classify(_rec(coverage_frac=1.05, n_scored=84, n_candidates=80,
                               status=S.STATUS_FAULT, state="degraded",
                               reasons=["stale_94d_limit_28d"]))
    assert st == S.MALFORMED_RECORD
    assert "stale" not in why[0]


def test_a_MISSING_coverage_is_not_a_violation():
    """`None` is unmeasured, not out of range — the PatchTST rows carry no expected_* at
    all and must not be swept in."""
    st, _ = S.classify(_rec(coverage_frac=None))
    assert st == S.HEALTHY


def test_LOW_coverage_is_still_the_floor_case_not_malformed():
    """The two bounds answer different questions and must stay distinguishable."""
    st, why = S.classify(_rec(coverage_frac=0.10, status=None, staleness_days=1))
    assert st != S.MALFORMED_RECORD


def test_MALFORMED_is_its_own_state_not_a_synonym():
    assert S.MALFORMED_RECORD not in (S.HEALTHY, S.DEGRADED, S.LOAD_FAIL, S.FEED_DARK)


def test_the_message_states_BOTH_readings_and_picks_neither():
    """The lane may be scoring a wider universe than the candidate set — then the
    DENOMINATOR is wrong, not the lane. Deciding that needs a human."""
    _st, why = S.classify(_rec(coverage_frac=1.2, n_scored=96, n_candidates=80))
    assert "outside the day's candidate set" in why[0]
    assert "denominator is not" in why[0]
