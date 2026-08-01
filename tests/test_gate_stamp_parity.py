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
    assert problems and "'<absent>'" in problems[0]


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
