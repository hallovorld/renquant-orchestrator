"""Tests for model_sanity_compare (#108 — reproducible model evidence)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from renquant_orchestrator.model_sanity_compare import (
    SanityRow,
    best_candidate,
    compare,
    load_sanity,
    render_markdown,
)


def _write(tmp_path, name, *, aligned, placebo, promotion, real, nfeat):
    d = tmp_path / f"sanity_placebo_{name}"
    d.mkdir()
    p = d / "hf_patchtst_all_seed44_model.json"
    p.write_text(json.dumps({
        "feature_count": nfeat,
        "real_ic": {"mean_ic": real},
        "interpretation": {
            "aligned_real_60_ic": aligned,
            "placebo_60_ic": placebo,
            "promotion_evidence": promotion,
        },
    }))
    return p


def test_load_sanity_derives_name_and_fields(tmp_path):
    p = _write(tmp_path, "B2", aligned=0.023, placebo=-0.065, promotion=False,
               real=-0.026, nfeat=157)
    row = load_sanity(p)
    assert row.name == "B2"
    assert row.n_features == 157
    assert row.real_ic == -0.026
    assert row.aligned_real_60_ic == 0.023
    assert row.promotion_evidence is False


def test_placebo_ratio():
    r = SanityRow("x", 157, -0.026, 0.02, -0.06, False)
    assert r.placebo_ratio == 3.0  # 0.06 / 0.02
    assert SanityRow("y", None, None, 0.0, -0.06, False).placebo_ratio is None


def test_best_candidate_prefers_smaller_placebo_ratio(tmp_path):
    b1 = _write(tmp_path, "B1", aligned=0.004, placebo=-0.094, promotion=False,
                real=-0.040, nfeat=172)
    b2 = _write(tmp_path, "B2", aligned=0.023, placebo=-0.065, promotion=False,
                real=-0.026, nfeat=157)
    rows = compare([b1, b2])
    best = best_candidate(rows)
    assert best.name == "B2"  # ratio 2.8 < B1's 23.5


def test_best_candidate_prefers_promotion(tmp_path):
    a = _write(tmp_path, "A", aligned=0.01, placebo=-0.05, promotion=False,
               real=-0.02, nfeat=157)
    b = _write(tmp_path, "B", aligned=0.005, placebo=-0.05, promotion=True,
               real=-0.01, nfeat=157)
    rows = compare([a, b])
    assert best_candidate(rows).name == "B"  # promotion wins even with worse ratio


def test_render_markdown_has_rows_and_verdict(tmp_path):
    b1 = _write(tmp_path, "B1", aligned=0.004, placebo=-0.094, promotion=False,
                real=-0.040, nfeat=172)
    b2 = _write(tmp_path, "B2", aligned=0.023, placebo=-0.065, promotion=False,
                real=-0.026, nfeat=157)
    md = render_markdown(compare([b1, b2]))
    assert "| B1 |" in md and "| B2 |" in md
    assert "closest to passing:** B2" in md


def test_explicit_names_override(tmp_path):
    p = _write(tmp_path, "xxx", aligned=0.01, placebo=-0.02, promotion=False,
               real=-0.01, nfeat=157)
    rows = compare([p], names=["custom"])
    assert rows[0].name == "custom"


def test_explicit_names_must_match_path_count(tmp_path):
    a = _write(tmp_path, "A", aligned=0.01, placebo=-0.02, promotion=False,
               real=-0.01, nfeat=157)
    b = _write(tmp_path, "B", aligned=0.02, placebo=-0.01, promotion=True,
               real=0.02, nfeat=157)

    with pytest.raises(ValueError, match="same length"):
        compare([a, b], names=["only-a"])


def test_empty_best_candidate():
    assert best_candidate([]) is None
