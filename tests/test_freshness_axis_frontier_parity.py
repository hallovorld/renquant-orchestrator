"""Two axes, one cutoff, different rules — and the detector must not repeat the defect.

The tool exists because a fail-closed axis was reported as passing by a real gate. Its own
first version then did the same thing: it matched a bare `OK` inside `(max=20d OK)` and
called a `QUARTERLY UNVERIFIABLE ... fail-closed` axis OK. Both directions are pinned here.
"""

from __future__ import annotations

import pathlib
import sys

OPS = pathlib.Path(__file__).resolve().parent.parent / "ops" / "renquant104"
sys.path.insert(0, str(OPS))

import freshness_axis_frontier_parity as F  # noqa: E402

CORRECTED = ("  source[fast] transformer_panel: cutoff=2026-04-28 raw-age=88d is "
             "fwd-label-clipped: achievable frontier=2026-07-21 (cutoff + 60 trading "
             "days, stamped lookahead_days); age-beyond-frontier=4d sla=28d OK")
BARE = "  source[fast] rawlabel: cutoff=2026-04-28 age=88d sla=28d OFF-SLA"
FAILCLOSED = ("  source[slow] fundamentals: daily feed as-of 2026-06-26 age=7d "
              "(max=20d OK); QUARTERLY UNVERIFIABLE — no per-entity provenance; "
              "fail-closed until it exists")


# ------------------------------------------------ the defect the tool nearly had --
def test_a_FAIL_CLOSED_axis_is_never_reported_OK():
    """`(max=20d OK)` is a sub-clause about one sub-check. Reading it as the axis verdict
    is how a detector reports health it never measured."""
    row = F.parse_axis(FAILCLOSED)
    assert row["verdict"] == F._BREACH
    assert "fail-closed" in row["verdict_evidence"]


def test_OK_is_read_from_the_TERMINAL_verdict_not_from_anywhere_in_the_line():
    assert F.parse_axis(CORRECTED)["verdict"] == F._OK
    assert F.parse_axis(BARE)["verdict"] == F._BREACH


def test_an_unrecognised_line_is_UNKNOWN_which_is_not_OK():
    row = F.parse_axis("  source[fast] mystery: cutoff=2026-01-01 something else")
    assert row["verdict"] == F._UNKNOWN
    assert row["sla_satisfiable"] is None      # unknown, and unknown is not True


# ----------------------------------------------------- the satisfiability finding --
def test_the_floor_is_READ_from_the_logs_own_frontier_not_an_assumed_ratio():
    row = F.parse_axis(CORRECTED)
    assert row["floor_days"] == 84            # 2026-04-28 -> 2026-07-21, measured
    assert row["sla_days"] == 28
    assert row["sla_satisfiable"] is False


def test_an_axis_with_no_frontier_stamp_has_NO_floor_not_a_zero_one():
    row = F.parse_axis(BARE)
    assert row["floor_days"] is None
    assert row["sla_satisfiable"] is None


def test_unsatisfiable_SLA_is_reported_as_a_finding():
    rep = F.analyse([F.parse_axis(CORRECTED)])
    kinds = [f["kind"] for f in rep["findings"]]
    assert "sla_unsatisfiable_by_construction" in kinds


# ------------------------------------------------------------ the parity finding --
def test_the_shared_cutoff_disagreement_fires():
    rep = F.analyse([F.parse_axis(CORRECTED), F.parse_axis(BARE)])
    f = [x for x in rep["findings"]
         if x["kind"] == "frontier_correction_not_applied_to_sibling_axis"]
    assert len(f) == 1
    assert f[0]["axis"] == "rawlabel" and f[0]["sibling"] == "transformer_panel"
    assert f[0]["sibling_floor_days"] == 84


def test_the_parity_finding_states_its_CONDITIONAL_rather_than_asserting_entitlement():
    """The tool cannot see either axis's label, so it must not claim the bare axis is
    entitled to the correction — only that two axes at one cutoff were judged differently."""
    rep = F.analyse([F.parse_axis(CORRECTED), F.parse_axis(BARE)])
    cond = rep["findings"][-1]["conditional"]
    assert cond.startswith("IF ")
    assert "does not establish" in cond


def test_DIFFERENT_cutoffs_do_NOT_fire_the_parity_finding():
    """2026-07-03 had cutoffs 2026-04-02 and 2026-02-11; a blanket alarm there would make
    every run noisy and the real 07-25 coincidence invisible."""
    other = BARE.replace("cutoff=2026-04-28", "cutoff=2026-02-11")
    rep = F.analyse([F.parse_axis(CORRECTED), F.parse_axis(other)])
    assert not [x for x in rep["findings"]
                if x["kind"] == "frontier_correction_not_applied_to_sibling_axis"]


# ------------------------------------------------------------------- plumbing --
def test_axis_discovery_is_not_an_ALLOW_LIST():
    """An axis added tomorrow must be watched, not silently skipped."""
    row = F.parse_axis("  source[fast] a_brand_new_axis: cutoff=2026-01-01 sla=28d OK")
    assert row is not None and row["axis"] == "a_brand_new_axis"


def test_the_LAST_block_wins_when_a_log_holds_several_runs():
    text = "\n".join([CORRECTED, BARE,
                      CORRECTED.replace("2026-04-28", "2026-05-30"),
                      BARE.replace("2026-04-28", "2026-05-30")])
    axes = F.read_axes(text)
    assert [a["cutoff"] for a in axes] == ["2026-05-30", "2026-05-30"]


def test_a_missing_log_SKIPS_with_3_rather_than_reporting_clean(tmp_path):
    assert F.main(["--log", str(tmp_path / "nope.log")]) == 3


def test_a_log_with_no_block_SKIPS_with_3(tmp_path):
    p = tmp_path / "x.log"
    p.write_text("nothing of interest here\n")
    assert F.main(["--log", str(p)]) == 3


def test_findings_exit_1_and_a_clean_block_exits_0(tmp_path):
    bad = tmp_path / "bad.log"
    bad.write_text(CORRECTED + "\n" + BARE + "\n")
    assert F.main(["--log", str(bad)]) == 1
    ok = tmp_path / "ok.log"
    ok.write_text("  source[fast] only: cutoff=2026-04-28 age=1d sla=28d OK\n")
    assert F.main(["--log", str(ok)]) == 0


def test_json_mode_does_not_crash_on_every_shape(tmp_path, capsys):
    p = tmp_path / "j.log"
    p.write_text("\n".join([CORRECTED, BARE, FAILCLOSED]) + "\n")
    assert F.main(["--log", str(p), "--json"]) == 1
    import json
    rep = json.loads(capsys.readouterr().out)
    assert rep["n_axes"] == 3 and rep["n_breaching"] == 2
