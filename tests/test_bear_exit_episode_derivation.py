"""Planted/null controls for the BEAR episode derivation (orch#917 line).

The model#220 convention: the synthetic fixture IS the auditable control
surface. These tests exercise the derivation module's pure grouping/tail/
coverage logic — the part a wrong index or an off-by-one would corrupt
silently — with planted episodes whose boundaries are known by
construction, plus a null control. The artifact/parquet read path is
--derive-only and machine-local by design (same split as the committed
reachability script's verify/derive modes).
"""
import csv
import importlib.util
from pathlib import Path

import pytest

MOD = (Path(__file__).resolve().parents[1] / "doc" / "research" / "data"
       / "2026-08-10-bear-exit-episode-derivation.py")
spec = importlib.util.spec_from_file_location("bear_episodes", MOD)
be = importlib.util.module_from_spec(spec)
spec.loader.exec_module(be)


def _days(pairs):
    """[(date, flag), ...] passthrough helper for readability."""
    return list(pairs)


def test_null_control_no_bear_days_zero_episodes():
    days = _days((f"2024-01-{d:02d}", False) for d in range(2, 12))
    assert be.group_episodes(days) == []


def test_planted_single_episode_with_full_tail():
    # 3 planted BEAR days inside 20 trading days; tail must be the NEXT
    # 10 trading days, not calendar days.
    dates = [f"d{idx:02d}" for idx in range(20)]
    days = [(d, 5 <= i <= 7) for i, d in enumerate(dates)]
    eps = be.group_episodes(days, tail_n=10)
    assert len(eps) == 1
    ep = eps[0]
    assert (ep["start"], ep["end"], ep["n_days"]) == ("d05", "d07", 3)
    assert (ep["tail_start"], ep["tail_end"]) == ("d08", "d17")
    assert ep["n_tail_days"] == 10 and ep["tail_clipped"] == 0


def test_planted_adjacent_blocks_split_by_one_day_are_two_episodes():
    # Contiguity is strict: one non-BEAR trading day splits episodes.
    dates = [f"d{idx:02d}" for idx in range(30)]
    bear = {3, 4, 6, 7}   # d05 breaks the run
    days = [(d, i in bear) for i, d in enumerate(dates)]
    eps = be.group_episodes(days, tail_n=10)
    assert [(e["start"], e["end"]) for e in eps] == [("d03", "d04"),
                                                    ("d06", "d07")]
    # Episode 1's tail overlaps episode 2's BEAR days — the derivation
    # records both verbatim (overlap handling is a flagged prereg
    # underspecification, not resolved here).
    assert eps[0]["tail_start"] == "d05" and eps[0]["tail_end"] == "d14"


def test_planted_tail_clipped_at_series_end():
    dates = [f"d{idx:02d}" for idx in range(10)]
    days = [(d, i in (7, 8)) for i, d in enumerate(dates)]
    eps = be.group_episodes(days, tail_n=10)
    assert len(eps) == 1
    ep = eps[0]
    assert (ep["start"], ep["end"]) == ("d07", "d08")
    assert ep["n_tail_days"] == 1 and ep["tail_end"] == "d09"
    assert ep["tail_clipped"] == 1


def test_planted_episode_ending_on_last_day_has_empty_tail():
    dates = [f"d{idx:02d}" for idx in range(5)]
    days = [(d, i == 4) for i, d in enumerate(dates)]
    eps = be.group_episodes(days, tail_n=10)
    assert len(eps) == 1
    ep = eps[0]
    assert ep["n_tail_days"] == 0 and ep["tail_end"] == ""
    assert ep["tail_clipped"] == 1


def test_coverage_flags_use_tail_end_not_episode_end():
    # Episode ends inside the window but its tail crosses the boundary:
    # the flag must be 0 (a sim must cover the tail too).
    ep = {"start": "2026-03-20", "end": "2026-03-25", "n_days": 4,
          "tail_start": "2026-03-26", "tail_end": "2026-04-08",
          "n_tail_days": 10, "tail_clipped": 0}
    flagged = be.coverage_flags(dict(ep))
    assert flagged["within_wf_2024"] == 0
    inside = dict(ep, tail_end="2026-03-27")
    assert be.coverage_flags(inside)["within_wf_2024"] == 1


def test_committed_csvs_verify_end_to_end():
    # The committed derivation artifacts must reproduce every frozen
    # EXPECTED number through the module's own verify() — the same check
    # CI would run, wired here so a silent CSV edit fails loudly.
    assert be.verify() == 0


# ── corruption fixtures (codex review on orch#962) ──────────────────────
# The review found the original verify() compared only start/end/tail_end
# per row, so compensating/same-total corruption of the other fields
# passed. check_rows() now compares EVERY field of every row; one mutation
# per previously-unchecked field below proves each is detected.

def _committed_rows():
    with open(be.DAYS_CSV, newline="") as fh:
        day_rows = list(csv.DictReader(fh))
    with open(be.EPISODES_CSV, newline="") as fh:
        ep_rows = list(csv.DictReader(fh))
    return day_rows, ep_rows


def test_committed_rows_pass_check_rows_clean():
    day_rows, ep_rows = _committed_rows()
    assert be.check_rows(day_rows, ep_rows) == []


@pytest.mark.parametrize("field,mutate", [
    # previously UNCHECKED fields — each single-field mutation must fail
    ("episode_id", lambda v: str(int(v) + 7)),
    ("n_days", lambda v: str(int(v) + 1)),
    ("tail_start", lambda v: "1999-01-01"),
    ("n_tail_days", lambda v: str(int(v) - 1)),
    ("tail_clipped", lambda v: str(1 - int(v))),
    ("within_wf_2024", lambda v: str(1 - int(v))),
    ("within_aux_2022", lambda v: str(1 - int(v))),
    # previously checked fields — regression: still detected
    ("start", lambda v: "1999-01-01"),
    ("end", lambda v: "1999-01-01"),
    ("tail_end", lambda v: "1999-01-01"),
])
def test_single_field_corruption_is_detected(field, mutate):
    day_rows, ep_rows = _committed_rows()
    ep_rows[0] = dict(ep_rows[0])
    ep_rows[0][field] = mutate(ep_rows[0][field])
    problems = be.check_rows(day_rows, ep_rows)
    assert problems, f"corrupted {field} passed verification"
    assert any(field in p for p in problems), (field, problems)


def test_artifact_partition_corruption_is_detected():
    day_rows, ep_rows = _committed_rows()
    ep_rows[0] = dict(ep_rows[0], artifact="sim_hmm")
    assert any("count" in p for p in be.check_rows(day_rows, ep_rows))


def test_compensating_flag_corruption_same_aggregate_is_detected():
    # Flip within_aux_2022 in two rows of the same arm, one each
    # direction: the aggregate episodes_within_aux_2022 count is
    # unchanged, so ONLY the row-level full comparison can catch it —
    # the exact corruption class the review named.
    day_rows, ep_rows = _committed_rows()
    prod = [i for i, r in enumerate(ep_rows) if r["artifact"] == "prod_gmm"]
    ones = [i for i in prod if ep_rows[i]["within_aux_2022"] == "1"]
    zeros = [i for i in prod if ep_rows[i]["within_aux_2022"] == "0"]
    assert ones and zeros, "fixture premise: both flag values exist"
    ep_rows[ones[0]] = dict(ep_rows[ones[0]], within_aux_2022="0")
    ep_rows[zeros[0]] = dict(ep_rows[zeros[0]], within_aux_2022="1")
    agg = be._summaries_from_rows(day_rows, ep_rows)
    assert (agg["prod_gmm"]["episodes_within_aux_2022"]
            == be.EXPECTED["prod_gmm"]["episodes_within_aux_2022"]), \
        "fixture premise: aggregate must be unchanged"
    problems = be.check_rows(day_rows, ep_rows)
    assert sum("within_aux_2022" in p for p in problems) == 2, problems


def test_day_row_corruption_is_detected():
    # Flip one mid-episode BEAR day label: episode boundaries shift, the
    # committed episode table no longer regroups — row leg catches it
    # even where aggregate counts barely move.
    day_rows, ep_rows = _committed_rows()
    idx = next(i for i, r in enumerate(day_rows)
               if r["date"] == "2020-03-16")   # inside the COVID episode
    assert day_rows[idx]["prod_gmm_label"] == "BEAR", "fixture premise"
    day_rows[idx] = dict(day_rows[idx], prod_gmm_label="BULL_VOLATILE")
    assert be.check_rows(day_rows, ep_rows)
