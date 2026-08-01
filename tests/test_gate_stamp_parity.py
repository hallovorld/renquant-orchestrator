"""R8's parity check: two gate stamps in one artifact that give different answers.

The twin registry's retirement condition for R8 asks for a check that REPORTS the
artifacts where the two copies disagree "instead of silently preferring one". Nothing in
the repo did that. These tests drive the check on SYNTHETIC fixtures, so they measure the
contract rather than this operator's artifact tree.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
MOD = ROOT / "ops" / "renquant104" / "gate_stamp_parity.py"


def _load():
    spec = importlib.util.spec_from_file_location("gsp", MOD)
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


G = _load()
Q = "panel-ltr.alpha158_fund*.json"


def _art(d: pathlib.Path, name: str, canon=None, legacy=None):
    body: dict = {}
    if canon is not None:
        body["metadata"] = {"wf_gate_metadata": canon}
    if legacy is not None:
        body["wf_gate_metadata"] = legacy
    (d / name).write_text(json.dumps(body), encoding="utf-8")


def test_agreeing_copies_are_not_a_problem(tmp_path):
    blk = {"passed": True, "sanity_eval_scope": "walkforward_manifest"}
    _art(tmp_path, "panel-ltr.alpha158_fund.json", canon=blk, legacy=dict(blk))
    problems, infos = G.scan(str(tmp_path), Q)
    assert problems == [], problems
    assert "1 carry BOTH copies" in infos[0]


def test_a_DISAGREEMENT_ON_PASSED_is_reported(tmp_path):
    """The live shape: canonical says the gate failed, legacy says it passed."""
    _art(tmp_path, "panel-ltr.alpha158_fund.json",
         canon={"passed": False, "sanity_eval_scope": "walkforward_manifest"},
         legacy={"passed": True, "operator_authorized_override": True})
    problems, _ = G.scan(str(tmp_path), Q)
    assert len(problems) == 1
    assert "passed: canonical=False legacy=True" in problems[0]


def test_ABSENT_counts_as_a_disagreement_not_as_equal(tmp_path):
    """Measured on the live tree: a legacy block with no `sanity_eval_scope` beside a
    canonical block that records one. Treating absent as "no opinion" would hide it."""
    _art(tmp_path, "panel-ltr.alpha158_fund.json",
         canon={"sanity_eval_scope": "walkforward_manifest"},
         legacy={"passed": True})
    problems, _ = G.scan(str(tmp_path), Q)
    # ROUND 2: the marker is now rendered UNQUOTED. Under the old `{value!r}` an
    # artifact whose field literally held the string "<absent>" printed exactly like a
    # missing one; see the collision test below.
    assert problems and "<absent>" in problems[0]


def test_canonical_only_and_legacy_only_are_counted_not_flagged(tmp_path):
    _art(tmp_path, "panel-ltr.alpha158_fund.a.json", canon={"passed": True})
    _art(tmp_path, "panel-ltr.alpha158_fund.b.json", legacy={"passed": True})
    problems, infos = G.scan(str(tmp_path), Q)
    assert problems == [], problems
    joined = " ".join(infos)
    assert "1 canonical-only" in joined and "1 legacy-only" in joined
    assert "ONLY the legacy top-level copy" in joined


def test_an_empty_scan_is_a_PROBLEM_not_parity(tmp_path):
    """Anti-vacuity: finding no subjects is not the same as finding agreement."""
    problems, _ = G.scan(str(tmp_path), Q)
    assert len(problems) == 1 and "no subjects" in problems[0]


def test_an_unreadable_artifact_is_reported_not_skipped(tmp_path):
    (tmp_path / "panel-ltr.alpha158_fund.bad.json").write_text("{not json", encoding="utf-8")
    problems, _ = G.scan(str(tmp_path), Q)
    assert problems and "unreadable" in problems[0]


def test_the_exit_code_is_nonzero_when_a_disagreement_exists(tmp_path):
    _art(tmp_path, "panel-ltr.alpha158_fund.json",
         canon={"passed": False}, legacy={"passed": True})
    assert G.main(["--root", str(tmp_path)]) == 1
    _art(tmp_path, "panel-ltr.alpha158_fund.json",
         canon={"passed": True}, legacy={"passed": True})
    assert G.main(["--root", str(tmp_path)]) == 0


# ---------------------------------------------------------------------------
# ROUND 2 — codex on orch#687: the eight-field enumeration WAS the fail-open
# default, and a malformed copy read as an absent one.
# ---------------------------------------------------------------------------

N = "panel-ltr.alpha158_fund.json"


def _raw(d: pathlib.Path, body: dict, name: str = N):
    """Write the payload VERBATIM — `_art` omits a key whose value is None, and the
    difference between 'key absent' and 'key present holding JSON null' is exactly
    what two of these tests are about."""
    (d / name).write_text(json.dumps(body), encoding="utf-8")


def test_a_field_OUTSIDE_the_old_enumeration_is_now_caught(tmp_path):
    """The exact hole codex named: a gate field nobody listed, disagreeing.

    `n_folds` is not in SALIENT_FIELDS and never was. Under the eight-field
    enumeration this artifact reported clean.
    """
    _art(tmp_path, N, canon={"passed": True, "n_folds": 43},
         legacy={"passed": True, "n_folds": 11})
    problems, _ = G.scan(str(tmp_path), Q)
    assert problems, "an unlisted field disagreeing must be a problem"
    assert "n_folds" in problems[0] and "43" in problems[0] and "11" in problems[0]


def test_a_NESTED_field_outside_the_enumeration_is_caught(tmp_path):
    _art(tmp_path, N, canon={"passed": True, "sanity": {"placebo_ic": 0.04}},
         legacy={"passed": True, "sanity": {"placebo_ic": 0.41}})
    problems, _ = G.scan(str(tmp_path), Q)
    assert problems and "sanity.placebo_ic" in problems[0], problems


def test_a_key_present_in_ONE_copy_only_is_a_disagreement(tmp_path):
    _art(tmp_path, N, canon={"passed": True, "override_reason": "operator"},
         legacy={"passed": True})
    problems, _ = G.scan(str(tmp_path), Q)
    assert problems and "override_reason" in problems[0] and "absent" in problems[0]


def test_ANTI_VACUITY_two_identical_blocks_are_still_clean(tmp_path):
    """Without this the deep walk could 'catch' everything and prove nothing."""
    blk = {"passed": True, "n_folds": 43, "sanity": {"placebo_ic": 0.04},
           "cuts": [1, 2, 3], "note": None}
    _art(tmp_path, N, canon=dict(blk), legacy=dict(blk))
    problems, _ = G.scan(str(tmp_path), Q)
    assert problems == [], problems


def test_a_MALFORMED_legacy_copy_FAILS_CLOSED(tmp_path):
    """Present but not an object. Previously classified as absent -> reported clean."""
    _art(tmp_path, N, canon={"passed": True}, legacy="passed")
    problems, _ = G.scan(str(tmp_path), Q)
    assert problems, "a malformed copy must not read as a single-stamped artifact"
    assert "MALFORMED" in problems[0] and G.LEGACY in problems[0], problems


def test_a_MALFORMED_canonical_copy_FAILS_CLOSED(tmp_path):
    _art(tmp_path, N, canon=["passed"], legacy={"passed": True})
    problems, _ = G.scan(str(tmp_path), Q)
    assert problems and G.CANONICAL in problems[0], problems


def test_a_malformed_METADATA_container_fails_closed_too(tmp_path):
    """`metadata` itself not an object: the canonical copy is unreadable, not absent."""
    _raw(tmp_path, {"metadata": "n/a", "wf_gate_metadata": {"passed": True}})
    problems, _ = G.scan(str(tmp_path), Q)
    assert problems and "MALFORMED" in problems[0], problems


def test_a_JSON_null_stamp_is_ABSENT_not_malformed(tmp_path):
    """The distinction has to cut BOTH ways, or it is just a stricter alarm."""
    _raw(tmp_path, {"metadata": {"wf_gate_metadata": {"passed": True}},
                    "wf_gate_metadata": None})
    problems, infos = G.scan(str(tmp_path), Q)
    assert problems == [], problems
    assert "1 canonical-only" in infos[0], infos[0]


def test_an_EMPTY_canonical_block_is_not_mistaken_for_legacy_only(tmp_path):
    """Truthiness, same shape codex found in orch#683.

    `{}` is falsy, so `if canon and legacy` fell through to `elif legacy` and counted a
    genuinely dual-stamped artifact as legacy-only, skipping the comparison entirely.
    """
    _art(tmp_path, N, canon={}, legacy={"passed": True})
    problems, infos = G.scan(str(tmp_path), Q)
    assert "1 carry BOTH copies" in infos[0], infos[0]
    assert problems and "passed" in problems[0], problems


def test_the_scan_states_its_own_denominator(tmp_path):
    """Every matched artifact lands in exactly one bucket, and the summary says so."""
    _art(tmp_path, "panel-ltr.alpha158_fund.a.json", canon={"passed": True})
    _art(tmp_path, "panel-ltr.alpha158_fund.b.json", legacy={"passed": True})
    _art(tmp_path, "panel-ltr.alpha158_fund.c.json", canon={"passed": True},
         legacy="bad")
    problems, infos = G.scan(str(tmp_path), Q)
    assert "3 artifact(s) scanned" in infos[0], infos[0]
    assert "1 malformed" in infos[0], infos[0]
    assert not any("fell through every branch" in p for p in problems), problems


def test_a_field_literally_holding_the_absent_marker_is_DISTINGUISHABLE(tmp_path):
    """Why the marker is unquoted now.

    Under `{value!r}` both of these rendered `'<absent>'`, so a reader could not tell
    "this copy omits the field" from "this copy holds the string '<absent>'". Here the
    canonical copy HOLDS the marker string and the legacy copy OMITS the field: the two
    sides of the same reported line must not read identically.
    """
    _art(tmp_path, N, canon={"passed": True, "override_reason": "<absent>"},
         legacy={"passed": True})
    problems, _ = G.scan(str(tmp_path), Q)
    line = next(p for p in problems if "override_reason" in p)
    seg = line.split("override_reason:", 1)[1]
    assert "canonical='<absent>'" in seg, seg   # a real string value, quoted
    assert "legacy=<absent>" in seg, seg        # the missing-field marker, unquoted
