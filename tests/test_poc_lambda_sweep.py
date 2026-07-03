"""Positive-control + run-selection tests for scripts/poc_lambda_sweep.py.

Round 2 (codex review r4): round 1's script never passed `min_invested_pct`
to the solver, so the wrapper default (0.0) disabled the entire cash-drag
objective term (qp_solver.py:468 requires BOTH min_invested_pct > 0 AND
cash_drag_lambda > 0) -- identical solutions across every lambda were
guaranteed by construction, not evidence the turnover cap masks anything.
These tests prove: (1) the mechanical null at min_invested_pct=0 is real and
expected, not a bug; (2) lambda DOES change the solution once the mechanism
is genuinely enabled (min_invested_pct > 0) -- the harness can actually
detect an effect when one exists; (3) run selection joins pipeline_runs by
date, not lexicographic run_id ordering.
"""
import importlib.util
import os
import sqlite3
import sys

import numpy as np
import pytest

_PIPE_ROOT = os.environ.get(
    "RQ_PIPELINE_ROOT", "/Users/renhao/git/github/renquant-pipeline/src")
if not os.path.isdir(_PIPE_ROOT):
    pytest.skip(f"renquant-pipeline sibling checkout not found at {_PIPE_ROOT}",
                allow_module_level=True)
sys.path.insert(0, _PIPE_ROOT)

_SCRIPT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scripts", "poc_lambda_sweep.py")
_spec = importlib.util.spec_from_file_location("poc_lambda_sweep", _SCRIPT_PATH)
poc_lambda_sweep = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(poc_lambda_sweep)


def _synthetic_inputs():
    n = 8
    tickers = tuple(f"T{i}" for i in range(n))
    rng = np.random.default_rng(20260702)
    mu = rng.uniform(0.001, 0.02, n)  # modest edge -- natural (lambda=0) deployment lands well below the 0.7 min_invested_pct target, matching the real-data pattern (deployed ~0.28-0.31 at lambda=0)
    sigma = rng.uniform(0.15, 0.35, n)
    w_cur = np.array([0.06, 0.05, 0.07, 0.04, 0.0, 0.0, 0.0, 0.0])  # partially invested (4/8 held) -- matches the real-data pattern (real portfolios were never fully cash); starting fully in cash makes turnover == deployed_frac exactly, which saturates the tight-cap test trivially and does not exercise the mechanism the same way real rebalancing does
    return tickers, mu, sigma, w_cur, n


def test_min_invested_zero_is_a_mechanical_null_not_evidence():
    """At min_invested_pct=0 (current production reality), the cash-drag
    objective term is structurally disabled (qp_solver.py:468) -- the
    solution MUST be identical across every lambda. This is the correct,
    expected behavior of the gate condition, not a bug to fix."""
    tickers, mu, sigma, w_cur, n = _synthetic_inputs()
    results = [
        poc_lambda_sweep._solve(
            w_cur=w_cur, n=n, tickers=tickers, mu=mu, sigma=sigma,
            lam=lam, min_invested_pct=0.0, turnover_max=0.50)
        for lam in poc_lambda_sweep.LAMBDAS
    ]
    deployed = {r["deployed_frac"] for r in results}
    assert len(deployed) == 1, (
        f"expected identical deployed_frac at every lambda when "
        f"min_invested_pct=0 (mechanism disabled by construction), got {deployed}")


def test_lambda_changes_solution_when_mechanism_enabled_non_binding_turnover():
    """Positive control: with min_invested_pct > 0 and a deliberately
    non-binding turnover cap, increasing lambda MUST change deployed_frac --
    proves the harness can actually detect a lambda effect when the
    mechanism is genuinely active, unlike round 1's harness which could not
    distinguish 'no effect' from 'gate never fired'."""
    tickers, mu, sigma, w_cur, n = _synthetic_inputs()
    results = [
        poc_lambda_sweep._solve(
            w_cur=w_cur, n=n, tickers=tickers, mu=mu, sigma=sigma,
            lam=lam, min_invested_pct=0.7, turnover_max=0.90)
        for lam in poc_lambda_sweep.LAMBDAS
    ]
    deployed = [r["deployed_frac"] for r in results]
    assert len(set(deployed)) > 1, (
        "expected deployed_frac to vary across lambda when min_invested_pct>0 "
        "and turnover is non-binding -- identical values would mean the "
        "positive control itself is broken")
    # monotonically non-decreasing: a larger cash-drag penalty should never
    # deploy LESS capital, all else equal
    assert all(b >= a - 1e-9 for a, b in zip(deployed, deployed[1:])), (
        f"expected deployed_frac non-decreasing in lambda, got {deployed}")


def test_turnover_cap_bounds_deployment_ceiling_but_lambda_still_acts():
    """At a tight turnover cap, lambda should still move the solution
    (not be masked to zero) even though the achievable ceiling is lower
    than at a loose cap -- distinguishes 'cap limits the ceiling' (true)
    from 'cap makes lambda have zero effect' (round 1's false claim)."""
    tickers, mu, sigma, w_cur, n = _synthetic_inputs()
    tight = [
        poc_lambda_sweep._solve(
            w_cur=w_cur, n=n, tickers=tickers, mu=mu, sigma=sigma,
            lam=lam, min_invested_pct=0.7, turnover_max=0.15)["deployed_frac"]
        for lam in poc_lambda_sweep.LAMBDAS
    ]
    loose = [
        poc_lambda_sweep._solve(
            w_cur=w_cur, n=n, tickers=tickers, mu=mu, sigma=sigma,
            lam=lam, min_invested_pct=0.7, turnover_max=0.90)["deployed_frac"]
        for lam in poc_lambda_sweep.LAMBDAS
    ]
    assert len(set(tight)) > 1, (
        f"expected lambda to move deployed_frac even under a tight turnover "
        f"cap, got a flat series {tight} -- would reproduce round 1's bug")
    assert max(loose) >= max(tight), (
        "the loose-turnover ceiling should be at least as high as the "
        "tight-turnover ceiling")


def test_run_selection_orders_by_date_not_lexicographic_run_id():
    """A run_id embedding an out-of-order hash suffix must not be picked
    over a genuinely later run_date -- proves selection joins pipeline_runs
    by run_date/created_at rather than sorting run_id strings."""
    con = sqlite3.connect(":memory:")
    con.execute("""
        create table pipeline_runs (
            run_id text primary key, run_date date, run_type text,
            strategy text, created_at timestamp)
    """)
    con.execute("""
        create table candidate_scores (run_id text, ticker text)
    """)
    # lexicographically LATER run_id but an EARLIER run_date -- a naive
    # `order by run_id desc` would wrongly prefer this over the real latest.
    con.execute(
        "insert into pipeline_runs values "
        "('2026-06-01-live-zzzzzzzz','2026-06-01','live','renquant-104',"
        "'2026-06-01 10:00:00')")
    con.execute(
        "insert into pipeline_runs values "
        "('2026-07-01-live-000000aa','2026-07-01','live','renquant-104',"
        "'2026-07-01 20:00:00')")
    for run_id in ("2026-06-01-live-zzzzzzzz", "2026-07-01-live-000000aa"):
        for i in range(85):
            con.execute(
                "insert into candidate_scores values (?,?)", (run_id, f"T{i}"))
    con.commit()

    selected = poc_lambda_sweep._runs(con, k=1)
    assert selected == ["2026-07-01-live-000000aa"], (
        f"expected the run with the later run_date to be selected regardless "
        f"of run_id string ordering, got {selected}")
