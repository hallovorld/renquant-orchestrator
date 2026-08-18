"""Synthetic-data tests for the Stage-1 universe-triage runner's pure logic.

Target: doc/research/data/2026-08-18-universe-stage1-derivation.py (the
frozen runner for the orch#995 spec — ships reviewed, runs later). The
model#220 convention: the synthetic fixture IS the auditable control
surface. Covered here, with values hand-computable on paper:

  * DGTW cell adjustment (self-exclusion + the <15/cell unadjusted flag)
  * RS-5 bucket boundaries + the turnover cost-drag formula
  * the §5 four-condition verdict (each condition flips it) + the U8 floor
  * paired-placebo shared-cross-section identity (a name missing from one
    leg vanishes from BOTH; the floor fail-closes)
  * block segmentation counts (19 at h=60 / 58 at h=20 on the 233-obs grid)
    and the block-t arithmetic

NO market-data reads anywhere: everything below is constructed in-memory.
"""
import hashlib
import importlib.util
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

MOD = (Path(__file__).resolve().parents[1] / "doc" / "research" / "data"
       / "2026-08-18-universe-stage1-derivation.py")
spec = importlib.util.spec_from_file_location("universe_stage1", MOD)
us = importlib.util.module_from_spec(spec)
spec.loader.exec_module(us)


# ───────────────────────── DGTW cell adjustment ─────────────────────────

def test_dgtw_adjust_three_cell_fixture_hand_computed():
    """3 cells: one big (adjusted), one at the floor, one small (flagged)."""
    labels = pd.Series(
        {"A1": 0.10, "A2": 0.20, "A3": 0.30,   # cell 0 (n=3)
         "B1": -0.10, "B2": 0.10,              # cell 1 (n=2)
         "C1": 0.50})                          # cell 2 (n=1)
    cells = pd.Series({"A1": 0, "A2": 0, "A3": 0, "B1": 1, "B2": 1, "C1": 2})
    adj, n_flagged = us.dgtw_adjust(labels, cells, min_cell=3)
    # cell 0 is big: self-excluded means are (0.2+0.3)/2, (0.1+0.3)/2, (0.1+0.2)/2
    assert adj["A1"] == pytest.approx(0.10 - 0.25)
    assert adj["A2"] == pytest.approx(0.20 - 0.20)
    assert adj["A3"] == pytest.approx(0.30 - 0.15)
    # cells 1 and 2 are below min_cell=3: UNADJUSTED (raw label), flagged
    assert adj["B1"] == pytest.approx(-0.10)
    assert adj["B2"] == pytest.approx(0.10)
    assert adj["C1"] == pytest.approx(0.50)
    assert n_flagged == 3


def test_dgtw_adjust_all_cells_big_no_flags():
    labels = pd.Series({"A": 1.0, "B": 2.0, "C": 3.0})
    cells = pd.Series({"A": 0, "B": 0, "C": 0})
    adj, n_flagged = us.dgtw_adjust(labels, cells, min_cell=2)
    assert n_flagged == 0
    assert adj["B"] == pytest.approx(2.0 - 2.0)  # bench = (1+3)/2


def test_assign_cells_terciles_are_order_only():
    """Cell ids depend only on within-column ORDER (monotone-invariant)."""
    n = 9
    chars = pd.DataFrame({
        "STD60": np.arange(n, dtype=float),
        "ROC60": np.arange(n, dtype=float)[::-1],
        "BETA60": np.ones(n),
    }, index=[f"T{i}" for i in range(n)])
    a = us.assign_cells(chars)
    scaled = chars.copy()
    scaled["STD60"] = scaled["STD60"] * 100 - 3          # affine, monotone
    scaled["ROC60"] = scaled["ROC60"] ** 3               # monotone on >=0
    b = us.assign_cells(scaled)
    assert (a == b).all()
    assert a.between(0, 26).all()


# ────────────────────── bucket boundaries + cost drag ──────────────────────

def test_adv_bucket_boundaries():
    assert us.adv_bucket(30e6) == "adv_ge_25M"
    assert us.adv_bucket(25e6) == "adv_ge_25M"      # lower edge inclusive
    assert us.adv_bucket(24.9e6) == "adv_10_25M"
    assert us.adv_bucket(10e6) == "adv_10_25M"
    assert us.adv_bucket(9.9e6) == "adv_5_10M"
    assert us.adv_bucket(5e6) == "adv_5_10M"
    assert us.adv_bucket(4.9e6) == "adv_1_5M"
    assert us.adv_bucket(1e6) == "adv_1_5M"
    assert us.adv_bucket(0.5e6) is None


def test_bucket_rt_costs_frozen_values():
    assert us.bucket_rt_cost("adv_ge_25M") == pytest.approx(0.0025)
    assert us.bucket_rt_cost("adv_10_25M") == pytest.approx(0.0040)
    assert us.bucket_rt_cost("adv_5_10M") == pytest.approx(0.0060)
    assert us.bucket_rt_cost("adv_1_5M") is None       # uncostable
    assert us.bucket_rt_cost(None) is None


def test_cost_drag_hand_computed():
    """First obs = full entry; then only entering names pay; h/step scales."""
    cost = {"A": 0.0025, "B": 0.0040, "C": 0.0060}
    tops = [(0, ("A", "B")), (1, ("A", "B")), (2, ("A", "C"))]
    drags = us.cost_drag_series(tops, cost, h=60, step=5)
    # obs 0: full entry (A+B) = 0.0065; /2 names; x12
    assert drags[0] == pytest.approx(12 * 0.0065 / 2)
    # obs 1: no turnover
    assert drags[1] == pytest.approx(0.0)
    # obs 2: C enters (0.0060) / 2 names x 12
    assert drags[2] == pytest.approx(12 * 0.0060 / 2)


def test_cost_drag_h20_factor_and_uncostable_fail_closed():
    drags = us.cost_drag_series([(0, ("A",))], {"A": 0.0025}, h=20, step=5)
    assert drags[0] == pytest.approx(4 * 0.0025)
    with pytest.raises(AssertionError, match="uncostable"):
        us.cost_drag_series([(0, ("A", "Z"))], {"A": 0.0025, "Z": None}, h=60)


# ───────────────────── §5 verdict: each condition flips ─────────────────────

BASE = dict(net_delta=0.01, block_t=1.5, pos_frac=0.6,
            n_blocks_with_data=15, transfer_ok=True)


def test_verdict_all_four_pass():
    v, why = us.triage_verdict(**BASE)
    assert v == "PASS (triage)"
    assert "all four" in why


@pytest.mark.parametrize("flip, expect_frag", [
    ({"net_delta": -0.001}, "net_delta"),
    ({"net_delta": 0.0}, "net_delta"),                 # strict > 0
    ({"block_t": 0.99}, "block_t"),
    ({"pos_frac": 0.5}, "pos_block_frac"),             # strictly greater
    ({"transfer_ok": False}, "transfer"),
])
def test_verdict_each_condition_flips(flip, expect_frag):
    v, why = us.triage_verdict(**{**BASE, **flip})
    assert v == "DEPRIORITIZED"
    assert expect_frag in why


def test_verdict_boundary_values_pass():
    v, _ = us.triage_verdict(**{**BASE, "block_t": 1.0})     # >= 1.0 passes
    assert v == "PASS (triage)"


def test_verdict_unmeasurable_below_block_floor():
    v, why = us.triage_verdict(**{**BASE, "n_blocks_with_data": 9})
    assert v == "UNMEASURABLE"
    assert "insufficient_blocks" in why
    # ... and the floor does NOT trip at exactly 10
    v2, _ = us.triage_verdict(**{**BASE, "n_blocks_with_data": 10})
    assert v2 == "PASS (triage)"


def test_positive_control_floor_and_sign():
    ok, _ = us.positive_control_ok(us.POSITIVE_CONTROL_MIN + 1e-9)
    assert ok
    ok, why = us.positive_control_ok(us.POSITIVE_CONTROL_MIN - 1e-6)
    assert not ok and "frozen floor" in why
    ok, _ = us.positive_control_ok(-0.5)
    assert not ok
    ok, why = us.positive_control_ok(float("nan"))
    assert not ok
    # in-sample inflation is telemetry, never a failure
    ok, why = us.positive_control_ok(1.0)
    assert ok and "in-sample inflation" in why


# ─────────────── paired-placebo shared-cross-section identity ───────────────

def _chars(names):
    rng = {n: float(i) for i, n in enumerate(names)}
    return pd.DataFrame({
        "STD60": [rng[n] for n in names],
        "ROC60": [rng[n] * 2 for n in names],
        "BETA60": [rng[n] % 3.0 for n in names],
    }, index=names)


def test_paired_cross_section_drops_names_missing_from_either_leg():
    names = [f"N{i:02d}" for i in range(12)]
    gen = pd.Series(np.linspace(0, 1, 12), index=names)
    pla = gen.drop("N03")                       # lag leg misses one name
    lab = pd.Series(np.linspace(-0.1, 0.1, 12), index=names)
    lab["N07"] = np.nan                          # label missing for another
    res = us.paired_spread_cross_section(
        gen, pla, lab, _chars(names), names_floor=5, min_cell=3)
    assert res is not None
    shared = set(res["names"])
    assert "N03" not in shared and "N07" not in shared
    assert shared == set(names) - {"N03", "N07"}
    assert res["n"] == 10
    assert len(set(res["names"])) == len(res["names"])   # no dups
    # the genuine decile is drawn only from the shared names
    assert set(res["top_gen"]) <= shared
    assert res["delta"] == pytest.approx(res["spread_gen"] - res["spread_pla"])


def test_paired_cross_section_floor_fail_closed():
    names = [f"N{i}" for i in range(8)]
    gen = pd.Series(np.arange(8, dtype=float), index=names)
    pla = gen.copy()
    lab = pd.Series(np.arange(8, dtype=float) / 100, index=names)
    assert us.paired_spread_cross_section(
        gen, pla, lab, _chars(names), names_floor=9, min_cell=3) is None


def test_paired_cross_section_perfect_score_positive_spread():
    """Scores == labels => the genuine decile owns the top labels."""
    names = [f"N{i:02d}" for i in range(30)]
    lab = pd.Series(np.linspace(-0.2, 0.2, 30), index=names)
    gen = lab.copy()                       # perfect ranking
    pla = pd.Series(np.zeros(30), index=names)  # uninformative placebo
    pla.iloc[:] = list(range(30))[::-1]         # anti-ranked
    res = us.paired_spread_cross_section(
        gen, pla, lab, _chars(names), names_floor=5, min_cell=100)
    # min_cell=100 => everything unadjusted => spread on raw labels
    assert res["n_flagged_unadjusted"] == 30
    k = us.top_decile_n(30)
    assert k == 3
    expect_gen = lab.nlargest(3).mean() - lab.mean()
    expect_pla = lab.nsmallest(3).mean() - lab.mean()
    assert res["spread_gen"] == pytest.approx(expect_gen)
    assert res["spread_pla"] == pytest.approx(expect_pla)
    assert res["delta"] > 0


# ───────────────────── block segmentation + block-t ─────────────────────

def test_block_counts_on_the_frozen_grid():
    """233 weekly obs -> 19 complete h=60 blocks, 58 complete h=20 blocks."""
    assert us.complete_blocks(233, 60 // 5) == 19
    assert us.complete_blocks(233, 20 // 5) == 58
    # the spec's own derived 231 gives the same complete-block counts
    assert us.complete_blocks(231, 12) == 19
    assert us.complete_blocks(231, 4) == 57  # ...except h=20 (58 needs >=232)


def test_block_of_obs_mapping():
    assert us.block_of_obs(0, 12) == 0
    assert us.block_of_obs(11, 12) == 0
    assert us.block_of_obs(12, 12) == 1
    assert us.block_of_obs(227, 12) == 18     # last obs of the last complete block
    assert us.block_of_obs(228, 12) == 19     # trailing incomplete block


def test_block_t_stats_hand_computed():
    # two obs in block 0 (mean 0.02), one in block 1 (0.04), one in the
    # incomplete tail (obs 24, excluded with n_complete=2)
    obs = [(0, 0.01), (5, 0.03), (13, 0.04), (24, 9.9)]
    st = us.block_t_stats(obs, blocks_per=12, n_complete=2)
    assert st["n_blocks_with_data"] == 2
    assert st["block_deltas"] == pytest.approx([0.02, 0.04])
    mean, sd = 0.03, np.std([0.02, 0.04], ddof=1)
    assert st["block_t"] == pytest.approx(mean / (sd / math.sqrt(2)))
    assert st["pos_block_frac"] == 1.0


def test_block_t_stats_empty_and_degenerate():
    st = us.block_t_stats([], blocks_per=12, n_complete=19)
    assert st["n_blocks_with_data"] == 0 and math.isnan(st["block_t"])
    st = us.block_t_stats([(0, 0.5)], blocks_per=12, n_complete=19)
    assert st["n_blocks_with_data"] == 1 and math.isnan(st["block_t"])
    # zero variance across blocks -> t undefined, NaN (never inf)
    st = us.block_t_stats([(0, 0.5), (12, 0.5)], blocks_per=12, n_complete=19)
    assert math.isnan(st["block_t"])


# ───────────────────────── pin-compare helpers ─────────────────────────

def test_content_pin_matches_production_semantics():
    full = "6461b827ab2339a8" + "0" * 48
    assert us.content_pin_matches("sha256:6461b827ab2339a8", full)
    assert us.content_pin_matches(full, full)
    assert not us.content_pin_matches("sha256:deadbeefdeadbeef", full)
    assert not us.content_pin_matches("sha256:6461b82", full)   # < 8 hex
    assert not us.content_pin_matches("", full)


def test_config_fp_pin_matches_no_abbreviation():
    assert us.config_fp_pin_matches("sha256:abc123", "sha256:abc123")
    assert us.config_fp_pin_matches("abc123", "sha256:abc123")
    assert not us.config_fp_pin_matches("sha256:abc1", "sha256:abc123")
    assert not us.config_fp_pin_matches("", "sha256:abc123")


# ───────────────────────── run guards (U10 / U11) ─────────────────────────

def test_one_shot_passes_when_no_outputs_exist(tmp_path):
    us.assert_one_shot(outputs=(tmp_path / "results.json",))


def test_one_shot_refuses_when_any_output_exists(tmp_path):
    marker = tmp_path / "results.json"
    marker.write_text("{}")
    with pytest.raises(AssertionError, match="one-shot"):
        us.assert_one_shot(outputs=(marker, tmp_path / "absent.csv"))


def test_this_pr_ships_unrun_no_outputs_committed():
    """The runner PR must not carry any run outputs (spec §6 / U10)."""
    us.assert_one_shot()


def _stub_git(monkeypatch, *, fetch_rc=0, show_rc=0, show_bytes=None,
              main_sha="a" * 40):
    """Fake us.subprocess.run for the U11 git triad; returns the call log."""
    calls = []
    top = str(MOD.parents[3])

    class R:
        def __init__(self, rc, out, err=""):
            self.returncode, self.stdout, self.stderr = rc, out, err

    def run(cmd, **kw):
        calls.append(list(cmd))
        if "rev-parse" in cmd and "--show-toplevel" in cmd:
            return R(0, top + "\n")
        if "fetch" in cmd:
            return R(fetch_rc, "", "fetch blocked (test)")
        if "show" in cmd:
            body = MOD.read_bytes() if show_bytes is None else show_bytes
            return R(show_rc, body, b"")
        if "rev-parse" in cmd:
            return R(0, main_sha + "\n")
        raise AssertionError(f"unexpected git call: {cmd}")

    monkeypatch.setattr(us.subprocess, "run", run)
    return calls


def test_runner_matches_main_fetch_failure_fails_closed(monkeypatch):
    _stub_git(monkeypatch, fetch_rc=1)
    with pytest.raises(AssertionError, match="cannot fetch origin/main"):
        us.assert_runner_matches_main()


def test_runner_matches_main_refuses_when_not_merged(monkeypatch):
    _stub_git(monkeypatch, show_rc=128)
    with pytest.raises(AssertionError, match="not on origin/main"):
        us.assert_runner_matches_main()


def test_runner_matches_main_refuses_on_byte_drift(monkeypatch):
    _stub_git(monkeypatch, show_bytes=b"# a superseded copy\n")
    with pytest.raises(AssertionError, match="differ from origin/main"):
        us.assert_runner_matches_main()


def test_runner_matches_main_fetches_before_compare_and_pins_lineage(monkeypatch):
    """orch#997: the fetch must precede show/rev-parse, and the returned
    provenance must be the post-fetch sha + the executing file's sha256."""
    sha = "b" * 40
    calls = _stub_git(monkeypatch, main_sha=sha)
    out = us.assert_runner_matches_main()
    kinds = [("fetch" if "fetch" in c else
              "show" if "show" in c else
              "rev-parse-main" if "origin/main" in c else "toplevel")
             for c in calls]
    assert kinds.index("fetch") < kinds.index("show")
    assert kinds.index("fetch") < kinds.index("rev-parse-main")
    assert out == {"origin_main_sha": sha,
                   "runner_sha256": hashlib.sha256(MOD.read_bytes()).hexdigest()}
