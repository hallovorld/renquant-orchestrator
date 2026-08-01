"""GOAL-6 — decomposing the gate answers the question orch#670 left open.

#670 measured 0 unaided passes in 11 artifacts and said: *"while every admission is
manual there is no way to tell 'the gate is right and the candidates are bad' from
'the gate is mis-specified'."* Decomposing the verdict into its sub-criteria gives a
way, and the answer is that **three sub-gates fail on 11 of 11** — and two of them
fail on the **same regime every single time**.

A criterion that rejects 100% of the population it judges carries no information
about which candidate is better. It can reject; it cannot rank.
"""

from __future__ import annotations

import csv
import json
import pathlib

DIR = (pathlib.Path(__file__).resolve().parent.parent
       / "doc/research/evidence/2026-07-31-wf-gate-subcriteria")
SUM = json.loads((DIR / "summary.json").read_text(encoding="utf-8"))


def _rows():
    return list(csv.DictReader((DIR / "subgate_matrix.csv").open()))


def test_three_subgates_reject_every_single_artifact():
    assert SUM["n_artifacts"] == 11
    assert SUM["sanity_fail_rate"] == "11/11"
    assert SUM["sanity_regime_ic_fail_rate"] == "11/11"
    assert SUM["trade_monotonicity_fail_rate"] == "11/11"


def test_the_gate_is_not_uniformly_broken():
    """CONTROL. If every sub-gate failed everywhere the matrix would say nothing
    about the failing ones — `trade_contract` passes 11/11, so the artifacts are
    being evaluated, not merely erroring out."""
    assert SUM["trade_contract_fail_rate"] == "0/11"
    # 9/11, corrected 2026-08-01 by re-derivation: the 07-06 staging artifact carries
    # passed=true on disk and the first hand-built matrix recorded FAIL. Two artifacts
    # pass `wf` -- the deployed one only via an operator override (see below).
    assert SUM["wf_fail_rate"] == "9/11"


def test_BULL_CALM_CO_FAILS_regime_ic_and_monotonicity_on_every_artifact():
    """The MEASURED co-failure, and nothing beyond it `[codex on orch#673]`.

    The previous name and docstring called the two sub-criteria "independent" and
    attributed the pattern to "the criterion or the regime — not eleven independently bad
    models". That inference was withdrawn elsewhere in this PR while remaining alive in
    executable text, where it is an assertion, not prose. Both are removed.

    What the rows support: on all eleven, BULL_CALM appears in the regime-IC failures AND
    is the monotonicity failure. Whether that is a property of the regime, of the
    criteria, of their shared inputs, or of a model population trained on overlapping
    windows is NOT established here — the eleven are not independent draws.
    """
    rows = _rows()
    assert all("BULL_CALM" in r["regime_ic_failed_regimes"] for r in rows)
    assert all(r["monotonicity_failed_regimes"] == "BULL_CALM" for r in rows)


def test_CHOPPY_also_fails_everywhere_and_BULL_VOLATILE_almost():
    rows = _rows()
    assert all("CHOPPY" in r["regime_ic_failed_regimes"] for r in rows)
    bv = sum(1 for r in rows if "BULL_VOLATILE" in r["regime_ic_failed_regimes"])
    assert bv == 10                                 # every one except the deployed


def test_exactly_one_artifact_is_marked_deployed():
    assert sum(1 for r in _rows() if r["deployed"] == "True") == 1


def test_the_document_does_not_claim_the_two_subcriteria_are_INDEPENDENT():
    """Self-audit before review, and the hole is a real one.

    `sanity_regime_ic` and `trade_monotonicity` are both evaluated on the same regime
    slice, so one property of that slice's population could fail both. Two failures are
    not two pieces of evidence until independence is shown, and nothing in this evidence
    shows it. The first draft called them "two independent sub-criteria".

    Paired with the check below so that withdrawing the word is not achieved by
    deleting the finding.
    """
    import pathlib
    doc = (pathlib.Path(__file__).resolve().parent.parent
           / "doc/progress/2026-07-31-wf-gate-subcriterion-matrix.md").read_text("utf-8")
    import re
    flat = re.sub(r"\s*\n>?\s*", " ", doc)
    struck = [m.span() for m in re.finditer(r"~~.+?~~", flat, re.S)]
    for at in (m.start() for m in re.finditer(r"independent sub-criteria", flat)):
        assert any(a <= at < b for a, b in struck), \
            "'independent sub-criteria' is asserted outside a withdrawal"
    assert "not established" in flat


def test_the_document_still_states_the_signature_it_DID_measure():
    """ANTI-VACUITY for the test above. Narrowing a claim must not delete it: the
    stable structural signature -- both sub-criteria failing the same regime on every
    artifact -- is measured and stays."""
    import pathlib
    doc = (pathlib.Path(__file__).resolve().parent.parent
           / "doc/progress/2026-07-31-wf-gate-subcriterion-matrix.md").read_text("utf-8")
    assert "fails two different sub-criteria on every artifact" in doc
    assert "not independent draws" in doc


# ---------------------------------------------------------------------------
# Bound to the artifacts, 2026-08-01 `[codex on orch#673]`
# ---------------------------------------------------------------------------
def test_every_row_names_a_path_and_a_digest():
    """An unbound matrix is a table, not evidence: a reader could not tell which file
    produced a row."""
    for r in _rows():
        assert r["artifact_path"].startswith("/")
        assert len(r["artifact_sha256"]) == 64


def test_no_two_rows_are_the_same_FILE():
    """Duplicate-content accounting. A `wf_gate_metadata` count in this programme has
    already been distorted by an artifact with 23 copies at 3 digests; if two of these
    eleven were byte-identical, every rate here would be inflated. Measured: 11 rows,
    11 distinct content groups."""
    rows = _rows()
    assert len({r["content_group"] for r in rows}) == len(rows) == 11
    assert len({r["artifact_sha256"] for r in rows}) == 11


def test_the_deployed_artifacts_wf_PASS_is_an_OPERATOR_OVERRIDE():
    """The fact the single `wf` column was hiding: the served artifact's gate verdict
    before override is FAIL, and it is deployed under an operator authorisation."""
    dep = [r for r in _rows() if r["deployed"] == "True"]
    assert len(dep) == 1
    assert dep[0]["wf"] == "PASS"
    assert dep[0]["wf_before_override"] == "FAIL"
    assert dep[0]["operator_authorized_override"] == "True"


def test_no_STAGING_artifact_was_overridden():
    for r in _rows():
        if r["deployed"] != "True":
            assert r["operator_authorized_override"] == "False", r["artifact"]


def test_the_provenance_sidecar_records_the_extraction_command():
    import json
    side = json.loads((DIR / "subgate_matrix.provenance.json").read_text())
    assert "subgate_matrix_extract.py --emit" in side["extraction_command"]
    assert side["n_rows"] == 11
    assert "selection_note" in side
