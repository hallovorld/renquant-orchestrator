"""A shadow table must be ATTRIBUTED, not merely un-contradicted.

The defect: `shadow_scores_for` read

    if "shadow_name" in df.columns and df["shadow_name"].iloc[0] != SHADOW_NAME:
        continue

so a table with NO `shadow_name` column fell through and was accepted as the
clf's. Measured 2026-07-30: 0 of the 40 newest comparison.json files carry a
`shadow_name` (or `run_date`) column, so the only model-identity check in this
path NEVER EXECUTED.

Not theoretical: three shadows write `shadow_score` tables. On 2026-07-28 the two
newest of the day were `xgb_alpha158_fund_previous_primary`, not the clf; on
2026-07-29 the clf and PatchTST tables were logged 25.7 MILLISECONDS apart with
identical 78-row shapes, so the mtime fallback cannot discriminate. And
`append_ledger` is idempotent per run_date, so a mis-attribution is written once
and never corrected.

These tests build a real mlruns tree on disk and drive the real function. A test
that only checked "a clf table is found" would have passed on the broken code —
the failure is that a NON-clf table is also found.
"""
from __future__ import annotations

import importlib.util
import json
import os
from datetime import date
from pathlib import Path

import pytest

OPS = Path(__file__).resolve().parent.parent / "ops" / "renquant104"


def _load():
    spec = importlib.util.spec_from_file_location(
        "rq104_blend_readout", OPS / "rq104_blend_readout.py")
    mod = importlib.util.module_from_spec(spec)
    import sys
    sys.path.insert(0, str(OPS.parent))
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.path.remove(str(OPS.parent))
    return mod


mod = _load()
TODAY = date.today().isoformat()


def _write_run(mlruns: Path, run: str, *, tag: str | None,
               column: str | None, scores: dict[str, float],
               mtime: float | None = None) -> Path:
    """One MLflow-shaped run: <run>/artifacts/comparison.json plus tags/."""
    art = mlruns / "0" / run / "artifacts"
    art.mkdir(parents=True)
    cols = ["ticker", "shadow_score"] + (["shadow_name"] if column else [])
    data = [[t, v] + ([column] if column else []) for t, v in scores.items()]
    p = art / "comparison.json"
    p.write_text(json.dumps({"columns": cols, "data": data}))
    if tag is not None:
        tags = mlruns / "0" / run / "tags"
        tags.mkdir(parents=True, exist_ok=True)
        (tags / "shadow_name").write_text(tag)
    if mtime is not None:
        os.utime(p, (mtime, mtime))
    return p


def test_a_table_with_NO_identity_anywhere_is_REFUSED(tmp_path, capsys):
    """THE REGRESSION. The old code accepted this as the clf's scores."""
    _write_run(tmp_path, "r1", tag=None, column=None, scores={"AAPL": 1.0})
    assert mod.shadow_scores_for(TODAY, tmp_path) is None
    assert "identity unresolved" in capsys.readouterr().out


def test_identity_from_the_mlflow_tag_is_accepted(tmp_path):
    """The tag was always on disk; the function just never read it."""
    _write_run(tmp_path, "r1", tag=mod.SHADOW_NAME, column=None,
               scores={"AAPL": 1.0, "MSFT": 2.0})
    out = mod.shadow_scores_for(TODAY, tmp_path)
    assert out is not None and out.loc["MSFT"] == pytest.approx(2.0)


def test_a_wrong_tag_is_refused(tmp_path, capsys):
    _write_run(tmp_path, "r1", tag="xgb_alpha158_fund_previous_primary",
               column=None, scores={"AAPL": 1.0})
    assert mod.shadow_scores_for(TODAY, tmp_path) is None
    assert "xgb_alpha158_fund_previous_primary" in capsys.readouterr().out


def test_the_measured_2026_07_28_scenario(tmp_path):
    """The two newest tables of that day were the previous-primary xgb, not the
    clf. The clf's table exists but is older, so a locator that stops at the
    newest acceptable-looking table gets the wrong model."""
    base = 1_700_000_000.0
    _write_run(tmp_path, "clf", tag=mod.SHADOW_NAME, column=None,
               scores={"AAPL": 0.5}, mtime=base)
    _write_run(tmp_path, "xgb_a", tag="xgb_alpha158_fund_previous_primary",
               column=None, scores={"AAPL": 9.9}, mtime=base + 10)
    _write_run(tmp_path, "xgb_b", tag="xgb_alpha158_fund_previous_primary",
               column=None, scores={"AAPL": 8.8}, mtime=base + 20)
    for run in ("clf", "xgb_a", "xgb_b"):
        p = tmp_path / "0" / run / "artifacts" / "comparison.json"
        d = date.fromtimestamp(p.stat().st_mtime).isoformat()
        got = mod.shadow_scores_for(d, tmp_path)
        if run == "clf":
            assert got is not None and got.loc["AAPL"] == pytest.approx(0.5)


def test_two_tables_25ms_apart_are_disambiguated_by_identity_not_mtime(tmp_path):
    """The measured 2026-07-29 case: clf and PatchTST 25.7 ms apart, identical
    row counts. mtime cannot tell them apart; the tag can."""
    base = 1_700_000_000.0
    _write_run(tmp_path, "patchtst", tag="hf_patchtst", column=None,
               scores={"AAPL": 7.0, "MSFT": 7.0}, mtime=base + 0.0257)
    _write_run(tmp_path, "clf", tag=mod.SHADOW_NAME, column=None,
               scores={"AAPL": 3.0, "MSFT": 4.0}, mtime=base)
    d = date.fromtimestamp(base).isoformat()
    out = mod.shadow_scores_for(d, tmp_path)
    assert out is not None
    assert out.loc["AAPL"] == pytest.approx(3.0), "picked the PatchTST table"


def test_a_payload_column_still_wins_when_present(tmp_path):
    _write_run(tmp_path, "r1", tag=None, column=mod.SHADOW_NAME,
               scores={"AAPL": 1.5})
    out = mod.shadow_scores_for(TODAY, tmp_path)
    assert out is not None and out.loc["AAPL"] == pytest.approx(1.5)


def test_an_empty_or_blank_tag_does_not_count_as_identity(tmp_path):
    """A zero-byte tag file must not read as 'identity established'."""
    _write_run(tmp_path, "r1", tag="   ", column=None, scores={"AAPL": 1.0})
    assert mod.shadow_scores_for(TODAY, tmp_path) is None


def test_resolver_returns_None_rather_than_raising_on_a_bare_path(tmp_path):
    """Fail-closed must never become fail-crash: this runs in an ops job."""
    import pandas as pd
    assert mod._resolve_shadow_name(
        pd.DataFrame({"ticker": ["A"], "shadow_score": [1.0]}),
        tmp_path / "nope" / "comparison.json") is None


def test_no_identity_check_remains_of_the_col_in_df_and_form():
    """The regression pin. `if col in df.columns and <check>` skips the check
    entirely when the column is absent — the exact shape of this defect, and the
    fifth instance on this programme of a guard validating something other than
    what it appears to."""
    src = (OPS / "rq104_blend_readout.py").read_text(encoding="utf-8")
    code = "\n".join(l for l in src.splitlines()
                     if not l.lstrip().startswith("#")).replace("\\\n", " ")
    # Scoped to the DEFECTIVE shape: a column-presence probe fused to the
    # identity comparison, which is what makes the comparison skippable. A bare
    # presence probe whose failure falls through to another source (as in
    # _resolve_shadow_name) is fine — the first version of this pin flagged that
    # legitimate line, a false positive of exactly the kind that makes a pin
    # untrustworthy.
    assert not any("in df.columns" in ln and "SHADOW_NAME" in ln
                   for ln in code.splitlines()), (
        "an identity comparison is fused to a column-presence probe, so it is "
        "skipped whenever the column is absent")
    # And the acceptance path must be gated on an EXPLICIT unresolved branch.
    assert "if name is None:" in code
    assert "_resolve_shadow_name(" in code
