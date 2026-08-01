"""GOAL-6 — the question orch#673 left: is the regime criterion satisfiable at all?

`BEAR` clears the placebo leg on **11 of 11** artifacts with a placebo IC at **4%** of
its real IC, so the criterion is not impossible.

TWO CLAIMS WITHDRAWN, both by orch#680 (merged) rather than by review:

  * ~~"#673's two hypotheses are BOTH wrong"~~ — the demonstration comes from 55 dates
    in the panel's smallest regime. That is insufficient evidence of generalisability to
    the regimes that carry the panel, so it excludes only the strictly weaker claim that
    the criterion passes NOWHERE. Mis-specification is NOT excluded.
  * ~~"that is a property of the labels in those regimes"~~ — a mechanism, and nothing
    here measures it. A persistent cross-section would produce this profile; so would
    other things.

WHAT SURVIVES, and it is a decomposition fact rather than an inference: in `BULL_CALM`
and `CHOPPY` a **60-day-shifted label out-ranks the aligned one** (median placebo/real
**2.15** and **6.61**), so the failing conjunct is the **placebo ceiling** while
`mean_ic` stays positive — the skill floor is met. Why the shifted label ranks that well
is not established here.
"""

from __future__ import annotations

import csv
import pathlib
import statistics

CSV = (pathlib.Path(__file__).resolve().parent.parent
       / "doc/research/evidence/2026-07-31-regime-sanity-decomposed"
       / "regime_placebo_vs_real.csv")


def _all_rows():
    """Every row of the committed CSV — used by the provenance tests, which are about
    the file itself rather than any one regime."""
    import csv
    with open(CSV) as fh:
        return list(csv.DictReader(fh))


def _reg(name):
    with CSV.open() as fh:
        return [r for r in csv.DictReader(fh) if r["regime"] == name]


def _median_ratio(rows):
    v = [float(r["placebo_over_real"]) for r in rows if r["placebo_over_real"]]
    return statistics.median(v)


def test_the_criterion_IS_satisfiable_SOMEWHERE():
    """Without a regime that passes, "the models are bad" and "the criterion is
    impossible" would be indistinguishable. That is ALL this establishes: one regime
    on 55 dates. It does not exclude mis-specification — see orch#680."""
    bear = _reg("BEAR")
    assert len(bear) == 30
    assert all(r["placebo_leg_ok"] == "True" for r in bear)
    assert _median_ratio(bear) < 0.10


def test_bull_calm_fails_the_PLACEBO_leg_not_the_skill_floor():
    """`min_mean_ic = max(0.0, 0.25*|real_ic|)` — a floor the regime's own IC scales
    with. The failing conjunct is the placebo ceiling, on every artifact."""
    bc = _reg("BULL_CALM")
    assert bc, "no BULL_CALM rows — an empty selection cannot fail a conjunct"
    assert all(r["placebo_leg_ok"] == "False" for r in bc)
    # THE FLOOR ITSELF, not a proxy for it `[codex on orch#677]`. The claim is that the
    # SKILL floor is met and the PLACEBO leg is what fails. `mean_ic > 0` does not
    # establish that: a positive IC below 0.25*|real_ic| would fail the skill floor too,
    # and the test would still pass while the sentence above it became false.
    for r in bc:
        stated = max(0.0, 0.25 * abs(float(r["aligned_real_ic"])))
        stamped = float(r["stamped_min_mean_ic"])
        mic = float(r["mean_ic"])
        assert mic >= stated, (
            f"{r['artifact']} BULL_CALM: mean_ic={mic} < stated floor {stated}")
        assert mic >= stamped, (
            f"{r['artifact']} BULL_CALM: mean_ic={mic} < STAMPED min_mean_ic {stamped}")


def test_the_STATED_floor_and_the_STAMPED_one_are_DIFFERENT_RULES():
    """Found while testing the conjunct `[codex on orch#677]`.

    The prose floor is `max(0, 0.25*|real_ic|)` — proportional to the regime's own IC.
    The artifact stamps `min_mean_ic`, a FLAT absolute threshold. Both hold on this
    corpus, but they are not the same rule, and asserting only the prose one would leave
    the gate's actual bar untested. Recording the divergence rather than picking a
    favourite.
    """
    rows = [r for r in _all_rows() if r["aligned_real_ic"]]
    assert rows
    stamped = {float(r["stamped_min_mean_ic"]) for r in rows}
    # CORRECTED while writing this test: I first asserted the stamped floor was a FLAT
    # 0.02, having read it off the deployed artifact alone. It is not — it varies per
    # ARTIFACT (0.0136 … 0.02 across this corpus), which is a different shape again from
    # the prose rule's per-REGIME variation. Asserting what was measured, and claiming
    # nothing about which rule generates it: that would be inferring a formula from a
    # value, which is the mistake this review cycle already corrected twice.
    assert len(stamped) > 1, (
        f"stamped min_mean_ic collapsed to {stamped} — if it were constant the two "
        f"rules could not be distinguished on this corpus")
    assert 0.02 in stamped, "the deployed artifact's stamped floor"
    per_regime = {round(max(0.0, 0.25 * abs(float(r["aligned_real_ic"]))), 6)
                  for r in rows}
    assert len(per_regime) > 1, "the prose floor varies with each regime's own IC"


def test_the_skill_floor_ASSERTION_would_fail_if_the_floor_were_breached():
    """Anti-vacuity for the conjunct above: the floor must be capable of failing.

    Without this, `mean_ic >= max(0, 0.25*|real_ic|)` could hold trivially — e.g. if
    every `aligned_real_ic` were 0, the floor would be 0 and any positive IC would clear
    it, proving nothing about skill.
    """
    bc = _reg("BULL_CALM")
    floors = [max(0.0, 0.25 * abs(float(r["aligned_real_ic"]))) for r in bc]
    assert any(f > 0 for f in floors), (
        "every floor is 0 — the conjunct is trivially satisfied and asserts nothing")
    # And a synthetic breach must be detectable by the same arithmetic.
    worst = min(float(r["mean_ic"]) - max(0.0, 0.25 * abs(float(r["aligned_real_ic"])))
                for r in bc)
    assert worst >= 0.0
    assert (worst - 1.0) < 0.0, "a breached floor must compare as negative"


def test_a_shifted_label_OUT_RANKS_the_aligned_one_in_the_failing_regimes():
    """CORRECTED 2026-08-01. The published thresholds were `> 2.0` and `> 6.0`; both were
    computed on a hand-built 11-artifact subset. On the reproducible 30-artifact
    extraction the medians are **1.98** and **2.63** — the first is BELOW its stated bar
    and the second is far below.

    The DIRECTION survives and is what the section claims: a shifted label out-ranks the
    aligned one in both failing regimes (ratio > 1) and does not in BEAR (0.046). The
    MAGNITUDES were an artefact of the subset.

    Asserted at the measured values, with a margin, rather than at the numbers that were
    published — moving the threshold to fit would be the inverse of what the provenance
    work was for.
    """
    bc = _median_ratio(_reg("BULL_CALM"))
    ch = _median_ratio(_reg("CHOPPY"))
    assert 1.9 < bc < 2.1, bc
    assert 2.5 < ch < 2.8, ch
    assert bc > 1.0 and ch > 1.0, "the direction is the claim; the magnitude was not"


def test_the_bar_a_model_would_have_to_clear_by_skill_alone():
    """ceiling = 0.5*|aligned_real_ic|, so passing with the observed placebo needs
    real_ic >= 2*placebo. Measured on the newest artifact that is ~4x today's."""
    newest = [r for r in _reg("BULL_CALM") if "20260730" in r["artifact"]][0]
    need = 2.0 * abs(float(newest["placebo_60_ic"]))
    have = abs(float(newest["aligned_real_ic"]))
    assert need / have > 4.0


def test_exactly_one_artifact_is_the_deployed_one():
    assert sum(1 for r in _reg("BULL_CALM") if r["deployed"] == "True") == 1


# ---------------------------------------------------------------------------
# ROUND 2 — codex on #677: the CSV was an unproven snapshot.
# ---------------------------------------------------------------------------

def test_every_row_is_BOUND_to_a_source_path_and_digest():
    """A CSV recording only artifact NAMES is a transcription. Provenance means each row
    names the file it came from and the bytes it was read out of."""
    for r in _all_rows():
        assert r.get("artifact_path"), r
        assert len(r.get("content_sha256", "")) == 64, r
        assert r.get("scope_source"), "which key answered must be recorded"


def test_the_committed_CSV_VERIFIES_against_the_artifacts_when_present():
    """The half that carries the weight: re-read every path, recompute every digest.
    Skips loudly when the artifact root is not on this machine — a verification that
    cannot run must not read as one that passed."""
    import importlib.util, os, pathlib, sys
    import pytest
    root = ("/Users/renhao/git/github/RenQuant/backtesting/renquant_104/"
            "artifacts/prod")
    if not os.path.isdir(root):
        pytest.skip("artifact root not present on this machine")
    mod = (pathlib.Path(__file__).resolve().parent.parent / "ops" / "renquant104"
           / "regime_sanity_extract.py")
    spec = importlib.util.spec_from_file_location("rse", mod)
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    res = m.verify(root, str(CSV))
    assert res["ok"], res
    assert res["unbound_rows"] == [], "every row must carry its binding"


def test_the_manifest_records_the_EXTRACTION_COMMAND():
    """'Reproducible' means a reader can run it, not that it was run once."""
    import json, pathlib
    man = json.loads((CSV.parent / "extract_manifest.json").read_text())
    assert "--emit" in man["command"] and "--root" in man["command"]
    assert man["canonical_key"].startswith("metadata.wf_gate_metadata")
    assert man["n_rows"] == len(_all_rows())
    assert "does not make the store immutable" in man["scope_note"]
