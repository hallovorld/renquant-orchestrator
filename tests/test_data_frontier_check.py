"""A rebuild that touches a file is not a rebuild that advanced the data —
and a structurally-lagged frontier is not a stale one.

Both halves are pinned here because the first revision of this checker got the
second half wrong: it applied a flat age bound to two panels carrying
`fwd_60d_excess` and reported both as UPSTREAM_EMPTY. A 60-trading-day forward
label cannot exist until ~84 calendar days after its feature date, so those
panels were as fresh as they can physically be. That is the same single-axis
error the two-axis shadow-freshness rule (renquant-pipeline#220) exists to fix.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ops"))
import data_frontier_check as F  # noqa: E402

AS_OF = dt.date(2026, 7, 29)


def _parquet(tmp_path: Path, name: str, last: str, *, days_old_mtime: int = 0) -> str:
    p = tmp_path / name
    dates = pd.bdate_range(end=pd.Timestamp(last), periods=30)
    pd.DataFrame({"date": dates, "ticker": ["X"] * 30}).to_parquet(p)
    if days_old_mtime:
        import os
        t = (dt.datetime.combine(AS_OF, dt.time()) - dt.timedelta(days=days_old_mtime)).timestamp()
        os.utime(p, (t, t))
    else:
        import os
        t = dt.datetime.combine(AS_OF, dt.time()).timestamp()
        os.utime(p, (t, t))
    return str(p)


# --- the trading->calendar conversion the structural floor rests on ---------

@pytest.mark.parametrize("tdays,cal", [(60, 84), (20, 28), (5, 7), (1, 2)])
def test_trading_to_calendar_days(tdays, cal):
    assert F.trading_to_calendar_days(tdays) == cal


def test_a_label_bearing_artifact_gets_a_structural_bound():
    art = F.WatchedArtifact(name="p", path="/x", label_horizon_tdays=60)
    bound, how = F.frontier_bound_days(art)
    assert bound == 84 + 28
    assert "structural floor 84d" in how and "60 trading days" in how


def test_a_label_free_artifact_gets_a_flat_bound():
    art = F.WatchedArtifact(name="p", path="/x", max_data_age_days=7)
    bound, how = F.frontier_bound_days(art)
    assert bound == 7 and "no forward label" in how


# --- the false positive this checker shipped in its first revision ----------

def test_the_real_transformer_panel_is_HEALTHY_not_stale(tmp_path):
    """92 calendar days behind, carrying a 60-trading-day label. Correct, not stale.

    The first revision called this UPSTREAM_EMPTY.
    """
    path = _parquet(tmp_path, "panel.parquet", "2026-04-28", days_old_mtime=4)
    art = F.WatchedArtifact(name="transformer-panel", path=path,
                            cadence_days=7, label_horizon_tdays=60)
    r = F.read_frontier(art, as_of=AS_OF)
    assert r.data_age_days == 92
    assert r.status == F.HEALTHY, r.describe()
    assert "structural floor 84d" in r.detail


def test_a_genuinely_stale_label_panel_is_still_caught(tmp_path):
    """The guard must not become permissive: 200d is beyond floor+slack."""
    path = _parquet(tmp_path, "panel.parquet", "2026-01-10", days_old_mtime=1)
    art = F.WatchedArtifact(name="p", path=path, cadence_days=7,
                            label_horizon_tdays=60)
    r = F.read_frontier(art, as_of=AS_OF)
    # ONE observation cannot prove the frontier is stuck -> retryable, not futile
    assert r.status == F.NOT_ADVANCING
    assert F.retry_advice(r)[0] == 1


def test_one_stale_observation_is_NOT_upstream_empty(tmp_path):
    """The regression codex caught: a single snapshot forced zero retries.

    The module defines UPSTREAM_EMPTY as "across repeated observations"; the
    first revision assigned it from one. That mislabels a transient upstream
    failure as futile — the opposite of check-and-retry.
    """
    path = _parquet(tmp_path, "d.parquet", "2026-05-01", days_old_mtime=0)
    art = F.WatchedArtifact(name="d", path=path, max_data_age_days=7,
                            cadence_days=1)
    r = F.read_frontier(art, as_of=AS_OF)
    assert r.status == F.NOT_ADVANCING
    assert F.retry_advice(r)[0] == 1


def test_a_PRIOR_observation_of_the_same_frontier_proves_it_stuck(tmp_path):
    """Two observations of the same newest date: now a retry IS futile."""
    path = _parquet(tmp_path, "d.parquet", "2026-05-01", days_old_mtime=0)
    art = F.WatchedArtifact(name="d", path=path, max_data_age_days=7,
                            cadence_days=1)
    r = F.read_frontier(art, as_of=AS_OF, prior_frontier=dt.date(2026, 5, 1),
                        prior_observed_on=AS_OF - dt.timedelta(days=3))
    assert r.status == F.UPSTREAM_EMPTY
    assert F.retry_advice(r)[0] == 0
    assert "saw the SAME frontier" in r.detail


def test_a_prior_observation_that_ADVANCED_is_not_stuck(tmp_path):
    path = _parquet(tmp_path, "d.parquet", "2026-05-01", days_old_mtime=0)
    art = F.WatchedArtifact(name="d", path=path, max_data_age_days=7,
                            cadence_days=1)
    r = F.read_frontier(art, as_of=AS_OF, prior_frontier=dt.date(2026, 4, 1),
                        prior_observed_on=AS_OF - dt.timedelta(days=3))
    assert r.status == F.NOT_ADVANCING


# --- mtime-fresh / data-stale, the original motivating defect ---------------

def test_touched_today_but_data_far_behind_needs_a_second_observation(tmp_path):
    """The motivating defect (mtime-fresh / data-stale) is still caught — but
    as NOT_ADVANCING until a prior reading confirms the frontier is stuck."""
    path = _parquet(tmp_path, "d.parquet", "2026-05-01", days_old_mtime=0)
    art = F.WatchedArtifact(name="d", path=path, max_data_age_days=7,
                            cadence_days=1)
    assert F.read_frontier(art, as_of=AS_OF).status == F.NOT_ADVANCING
    r2 = F.read_frontier(art, as_of=AS_OF, prior_frontier=dt.date(2026, 5, 1),
                         prior_observed_on=AS_OF - dt.timedelta(days=3))
    assert r2.status == F.UPSTREAM_EMPTY


def test_not_touched_and_stale_is_TRANSIENT(tmp_path):
    """Job appears not to have run — retrying IS the right response."""
    path = _parquet(tmp_path, "d.parquet", "2026-07-01", days_old_mtime=20)
    art = F.WatchedArtifact(name="d", path=path, max_data_age_days=7,
                            cadence_days=1)
    r = F.read_frontier(art, as_of=AS_OF)
    assert r.status == F.TRANSIENT
    assert F.retry_advice(r)[0] == 3


def test_a_fresh_artifact_is_healthy(tmp_path):
    path = _parquet(tmp_path, "d.parquet", "2026-07-24")
    art = F.WatchedArtifact(name="d", path=path, max_data_age_days=7,
                            cadence_days=1)
    assert F.read_frontier(art, as_of=AS_OF).status == F.HEALTHY


def test_a_missing_artifact_is_TRANSIENT_and_retryable(tmp_path):
    art = F.WatchedArtifact(name="gone", path=str(tmp_path / "nope.parquet"))
    r = F.read_frontier(art, as_of=AS_OF)
    assert r.status == F.TRANSIENT and F.retry_advice(r)[0] == 3


def test_an_unreadable_date_column_is_TRANSIENT_not_stale(tmp_path):
    path = _parquet(tmp_path, "d.parquet", "2026-07-24")
    art = F.WatchedArtifact(name="d", path=path, date_column="nope")
    r = F.read_frontier(art, as_of=AS_OF)
    assert r.status == F.TRANSIENT
    assert "not as stale" in r.detail


# --- the retry policy that keeps a futile retry from hiding a data problem --

def test_upstream_empty_gets_ZERO_retries_with_a_reason():
    r = F.FrontierReading("x", F.UPSTREAM_EMPTY, dt.date(2026, 5, 1), 89,
                          AS_OF, "")
    n, why = F.retry_advice(r)
    assert n == 0
    assert "futile" in why


def test_the_alarm_title_is_ascii(monkeypatch, tmp_path):
    """An alarm about data must not fail to deliver for an encoding reason."""
    sent = []
    monkeypatch.setattr(F, "alert", lambda t, b, **k: sent.append(t))
    monkeypatch.setattr(F, "WATCHED", (F.WatchedArtifact(
        name="d", path=_parquet(tmp_path, "d.parquet", "2026-05-01",
                                days_old_mtime=0),
        max_data_age_days=7, cadence_days=1),))
    assert F.main(["--as-of", "2026-07-29"]) == 1
    assert sent and sent[0].isascii()


def test_dry_run_sends_nothing(monkeypatch, tmp_path):
    sent = []
    monkeypatch.setattr(F, "alert", lambda t, b, **k: sent.append(t))
    monkeypatch.setattr(F, "WATCHED", (F.WatchedArtifact(
        name="d", path=_parquet(tmp_path, "d.parquet", "2026-05-01",
                                days_old_mtime=0),
        max_data_age_days=7, cadence_days=1),))
    assert F.main(["--as-of", "2026-07-29", "--dry-run"]) == 1
    assert sent == []


# --- sameness is not enough: the cadence SPAN must be proven ---------------


def test_same_frontier_but_TOO_SOON_is_not_upstream_empty(tmp_path):
    """The regression codex caught on the second revision.

    `prior_frontier == newest` proves the value did not change, not that time
    passed. Two observations minutes apart agree trivially, so requiring only
    sameness bought zero retries far too cheaply. UPSTREAM_EMPTY's own
    contract is "spanning more than one expected cadence".
    """
    path = _parquet(tmp_path, "d.parquet", "2026-05-01", days_old_mtime=0)
    art = F.WatchedArtifact(name="d", path=path, max_data_age_days=7,
                            cadence_days=7)
    r = F.read_frontier(art, as_of=AS_OF, prior_frontier=dt.date(2026, 5, 1),
                        prior_observed_on=AS_OF - dt.timedelta(days=2))
    assert r.status == F.NOT_ADVANCING, r.describe()
    assert F.retry_advice(r)[0] == 1
    assert "2d ago" in r.detail and "7d cadence" in r.detail


def test_same_frontier_with_NO_timestamp_is_not_upstream_empty(tmp_path):
    """A caller that persists the value but not when it saw it cannot reach
    the zero-retry status — the safe direction."""
    path = _parquet(tmp_path, "d.parquet", "2026-05-01", days_old_mtime=0)
    art = F.WatchedArtifact(name="d", path=path, max_data_age_days=7,
                            cadence_days=7)
    r = F.read_frontier(art, as_of=AS_OF, prior_frontier=dt.date(2026, 5, 1))
    assert r.status == F.NOT_ADVANCING
    assert F.retry_advice(r)[0] == 1
    assert "timestamp was not supplied" in r.detail


def test_same_frontier_spanning_exactly_one_cadence_IS_upstream_empty(tmp_path):
    """The boundary: >= cadence_days qualifies."""
    path = _parquet(tmp_path, "d.parquet", "2026-05-01", days_old_mtime=0)
    art = F.WatchedArtifact(name="d", path=path, max_data_age_days=7,
                            cadence_days=7)
    r = F.read_frontier(art, as_of=AS_OF, prior_frontier=dt.date(2026, 5, 1),
                        prior_observed_on=AS_OF - dt.timedelta(days=7))
    assert r.status == F.UPSTREAM_EMPTY
    assert F.retry_advice(r)[0] == 0


# --- the refresh-chain invariant: derived may not lag its own input ---------

def _reading(name, newest, age=90):
    return F.FrontierReading(name, F.HEALTHY, newest, age, AS_OF, "")


def test_the_real_production_lag_is_caught(monkeypatch):
    """Measured 2026-07-29 and the reason this check exists.

    PROD fund panel  max_date 2026-05-01
    PROD corpus      max_date 2026-04-28   <- 3 sessions behind its own input
    Both were inside their own 112d structural bound, so the age check reported
    HEALTHY for both and could not see the chain was out of order.
    """
    monkeypatch.setattr(F, "DERIVED_FROM",
                        (("transformer-panel", "alpha158-fund-panel"),))
    out = F.check_derived_not_behind_upstream([
        _reading("transformer-panel", dt.date(2026, 4, 28), 92),
        _reading("alpha158-fund-panel", dt.date(2026, 5, 1), 89),
    ])
    assert len(out) == 1
    assert "3d BEHIND" in out[0]
    assert "age check alone cannot see this" in out[0]


def test_derived_level_with_upstream_is_clean(monkeypatch):
    monkeypatch.setattr(F, "DERIVED_FROM",
                        (("transformer-panel", "alpha158-fund-panel"),))
    assert F.check_derived_not_behind_upstream([
        _reading("transformer-panel", dt.date(2026, 5, 1)),
        _reading("alpha158-fund-panel", dt.date(2026, 5, 1)),
    ]) == []


def test_derived_AHEAD_of_upstream_is_not_a_finding(monkeypatch):
    """Only BEHIND is a fault; ahead is legitimate (independent inputs)."""
    monkeypatch.setattr(F, "DERIVED_FROM",
                        (("transformer-panel", "alpha158-fund-panel"),))
    assert F.check_derived_not_behind_upstream([
        _reading("transformer-panel", dt.date(2026, 5, 5)),
        _reading("alpha158-fund-panel", dt.date(2026, 5, 1)),
    ]) == []


def test_an_unreadable_side_is_skipped_not_double_counted(monkeypatch):
    """The age check already reports an unreadable input; a second finding for
    the same fault would double-count it."""
    monkeypatch.setattr(F, "DERIVED_FROM",
                        (("transformer-panel", "alpha158-fund-panel"),))
    assert F.check_derived_not_behind_upstream([
        F.FrontierReading("transformer-panel", F.TRANSIENT, None, None, None, ""),
        _reading("alpha158-fund-panel", dt.date(2026, 5, 1)),
    ]) == []


def test_main_exits_nonzero_on_a_chain_fault_alone(monkeypatch, tmp_path, capsys):
    """A chain fault must fail the run even when every artifact is HEALTHY."""
    up = _parquet(tmp_path, "up.parquet", "2026-07-24")
    dn = _parquet(tmp_path, "dn.parquet", "2026-07-21")
    monkeypatch.setattr(F, "WATCHED", (
        F.WatchedArtifact(name="U", path=up, max_data_age_days=30, cadence_days=1),
        F.WatchedArtifact(name="D", path=dn, max_data_age_days=30, cadence_days=1),
    ))
    monkeypatch.setattr(F, "DERIVED_FROM", (("D", "U"),))
    monkeypatch.setattr(F, "alert", lambda *a, **k: None)
    rc = F.main(["--as-of", "2026-07-29"])
    out = capsys.readouterr().out
    assert "[HEALTHY] U" in out and "[HEALTHY] D" in out
    assert "[CHAIN]" in out and "3d BEHIND" in out
    assert rc == 1, "a chain fault with all-healthy artifacts must still fail"
