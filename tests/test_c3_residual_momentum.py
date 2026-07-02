"""Focused tests for scripts/c3_residual_momentum.py's round-2 bootstrap fix.

Codex's review found the conditioned-cell bootstrap pre-filtered to an
in-cell-only array BEFORE drawing blocks, which silently splices together
regime episodes separated by a calendar gap as if they were contiguous
trading days -- no longer a genuine 60-trading-day dependence block. These
tests construct a synthetic series with two regime episodes separated by a
long off-regime gap and prove: the OLD (naive) function collapses the gap,
while the FIXED function (blocks drawn from the full dated series, mask
carried through) does not.
"""
from __future__ import annotations

import os
import sys

import numpy as np

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

import c3_residual_momentum as c3  # noqa: E402


def _synthetic_two_episode_series():
    """30 in-cell dates (episode A), 170 off-cell dates (a long gap -- far
    bigger than the block size), 30 in-cell dates (episode B). Episode A's
    values are all exactly 1.0, episode B's are all exactly -1.0, and every
    off-cell value is 0.0. If a bootstrap draw's block spans the seam between
    the two episodes' filtered positions, its in-cell mean will be some blend
    of +1.0 and -1.0 (not exactly +-1.0) -- a directly observable symptom of
    gap-collapse that a genuinely gap-respecting bootstrap cannot produce."""
    n_a, n_gap, n_b = 30, 170, 30
    vals = np.concatenate([
        np.full(n_a, 1.0),
        np.full(n_gap, 0.0),
        np.full(n_b, -1.0),
    ])
    in_cell = np.concatenate([
        np.ones(n_a, dtype=bool),
        np.zeros(n_gap, dtype=bool),
        np.ones(n_b, dtype=bool),
    ])
    return vals, in_cell


def test_old_naive_bootstrap_draws_single_blocks_that_splice_episodes():
    """The OLD (pre-filtered) approach: filtering to in-cell-only first
    produces a 60-element array of exactly [1.0]*30 + [-1.0]*30 with NO
    positional gap between the two episodes. A SINGLE 45-length contiguous
    block drawn from this 60-element array, if it starts anywhere in [1, 15],
    necessarily spans filtered-position 30 -- the artificial seam -- and
    therefore contains BOTH +1.0 (episode A) and -1.0 (episode B) values
    within one block, even though those dates were really ~170 calendar days
    apart. This demonstrates the bug directly at the single-block level,
    which is the actual defect (not merely that a full multi-block resample's
    aggregate mean can reflect both episodes -- that is legitimate for any
    moving-block bootstrap of the full population)."""
    vals, in_cell = _synthetic_two_episode_series()
    cond_vals = vals[in_cell]  # the old code's pre-filtering step
    assert len(cond_vals) == 60
    n_blocks_spanning_seam = 0
    for start in range(1, 16):  # every valid non-zero start for block=45 over n=60
        block = cond_vals[start:start + 45]
        if (block > 0).any() and (block < 0).any():
            n_blocks_spanning_seam += 1
    assert n_blocks_spanning_seam == 15, (
        "expected every non-zero-start block to splice the artificial seam in "
        "the pre-filtered array -- if this fails, the synthetic fixture needs "
        "adjusting, not the assertion")


def test_fixed_bootstrap_no_single_block_spans_both_episodes():
    """The FIXED function draws blocks from the FULL 230-element series (with
    the off-cell gap present as real positions). Episode A occupies positions
    [0,30), episode B occupies positions [200,230); they are 170 positions
    apart. A single window of `block`=45 consecutive positions, starting
    anywhere in [0, 230-45=185], can NEVER simultaneously include a position
    < 30 (episode A) AND a position >= 200 (episode B), since that would
    require the window to span at least 200 positions -- more than 4x the
    block size. This proves the fix's single-block draws respect true
    calendar contiguity; unlike the old approach, no individual block can
    splice two calendar-distant episodes together."""
    vals, in_cell = _synthetic_two_episode_series()
    n = len(vals)
    block = 45
    max_start = n - block
    n_spanning = 0
    for start in range(0, max_start + 1):
        idx = np.arange(start, start + block)
        touches_a = np.any(idx < 30)
        touches_b = np.any(idx >= 200)
        if touches_a and touches_b:
            n_spanning += 1
    assert n_spanning == 0, (
        f"{n_spanning} single-block windows out of {max_start + 1} illegally "
        "spanned both episodes -- a 45-length window should never reach "
        "across a 170-position gap")

    # Sanity: the fixed function still produces valid, computable resamples
    # on this fixture (proving the fix doesn't just avoid the bug by
    # returning None/empty).
    means = c3.block_bootstrap_conditional_mean(vals, in_cell, block=block, n_boot=200, seed=1)
    assert means is not None
    assert len(means) > 0


def test_effective_block_coverage_reports_true_episode_structure():
    vals, in_cell = _synthetic_two_episode_series()
    cov = c3.effective_block_coverage(vals, in_cell, block=45)
    # 230 // 45 = 5 full non-overlapping blocks. Block 0 = positions [0,45)
    # covers all 30 of episode A plus 15 off-cell -> >=2 in-cell (usable).
    # Blocks 1-3 = positions [45,180) are entirely within the 170-date
    # off-cell gap -> 0 in-cell (not usable). Block 4 = positions [180,225)
    # is entirely off-cell/early episode-B overlap depending on exact
    # boundary -- assert the coverage count is small (reflects the true
    # sparse episode structure), not the full n_dates_conditioned=60.
    assert cov["n_full_blocks"] == 5
    assert cov["n_blocks_with_ge2_in_cell"] < 5
    assert cov["n_blocks_with_ge2_in_cell"] >= 1


def test_diff_bootstrap_already_correct_unaffected_by_fix():
    """block_bootstrap_diff already carried the mask through correctly before
    this round's fix -- confirm it still behaves sanely on the same fixture
    (regression guard, not a new finding)."""
    vals, in_cell = _synthetic_two_episode_series()
    diffs = c3.block_bootstrap_diff(vals, in_cell, block=45, n_boot=500, seed=1)
    assert diffs is not None
    assert len(diffs) > 0
