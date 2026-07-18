"""AC-1 executable consumer evidence: orchestrator vs the 176-col sidecar.

Companion to renquant-base-data
``doc/design/2026-07-18-rawlabel-sidecar-sentiment-reconciliation.md`` (AC-1)
and its evidence appendix. The orchestrator touches the served
``alpha158_291_fundamental_dataset_rawlabel.parquet`` on two surfaces:

1. ``build_patchtst_wf_manifest`` / ``retrain_patchtst``: pure PATH PLUMBING —
   the resolved path is handed to ``renquant_model_patchtst.fit_calibrator``
   via ``--raw-label-panel``; no parquet is opened here. Safe at 176 columns
   transitively (the calibrator's read is column-pruned to keys + er label —
   pinned in the renquant-model companion tests).

2. ``retrain_alpha158_fund`` σ-head refresh: WAS an ACTIVE WRITER of the
   served sidecar path — the second writer whose recipe conflict with the
   base-data builder deadlocked the weekly PatchTST corpus refresh. The AC-1
   evidence for that writer war (the σ-head builder re-emitting sentiment; its
   column-contract-blind validator; its rejection of bar-frontier extension
   rows) has been SUPERSEDED: the single-writer amendment (base-data#48) makes
   the base-data builder the sole writer at a canonical 179-col contract, and
   the orchestrator σ-head refresh is now a CONSUMER (writer cessation). Those
   three writer-conflict evidence tests are therefore removed here; the
   resolution — writer cessation + fit-equivalence — is pinned by
   ``tests/test_retrain_sigma_head_rawlabel.py`` (AC-A) and
   ``tests/test_sigma_head_fit_equivalence.py`` (AC-B). Surface-1 (below)
   still holds unchanged.

Fixture provenance: ``tests/fixture_rawlabel_sidecar_columns_176.json`` is an
export of renquant-base-data ``rawlabel_sidecar.RAWLABEL_SIDECAR_COLUMNS`` at
main ``b72dd92`` — a FROZEN historical snapshot (the pre-amendment 176-col
contract); the canonical contract is now 179 (base-data#48).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from renquant_orchestrator import retrain_alpha158_fund as sigma_mod
from renquant_orchestrator.build_patchtst_wf_manifest import (
    DEFAULT_RAW_LABEL_PANEL_REL,
    build_calibrator_cmd,
    default_raw_label_panel_path,
)

pytest.importorskip("pyarrow")

SIDECAR_COLUMNS = json.loads(
    (Path(__file__).parent / "fixture_rawlabel_sidecar_columns_176.json").read_text()
)
SENTIMENT_COLS = ["sentiment_pos_share", "mean_sentiment", "n_articles_log"]


# ── surface 1: PatchTST WF manifest path plumbing (reader-by-proxy) ──────────


def test_manifest_builder_binds_the_exact_served_sidecar_filename(tmp_path):
    assert (
        str(DEFAULT_RAW_LABEL_PANEL_REL)
        == "data/alpha158_291_fundamental_dataset_rawlabel.parquet"
    )
    resolved = default_raw_label_panel_path(tmp_path)
    assert resolved == str(tmp_path / DEFAULT_RAW_LABEL_PANEL_REL)
    assert default_raw_label_panel_path(None) is None


def test_manifest_builder_passes_path_through_without_reading(tmp_path):
    """The path lands verbatim in the fit_calibrator argv; the manifest
    builder itself never opens the parquet (nothing to break at 176)."""
    raw = tmp_path / "data" / "alpha158_291_fundamental_dataset_rawlabel.parquet"
    cmd = build_calibrator_cmd(
        scorer_artifact=tmp_path / "model.pt",
        out_path=tmp_path / "cal.json",
        panel_path=tmp_path / "panel.parquet",
        raw_label_panel_path=raw,  # does not even exist: pass-through only
        label="fwd_60d_excess",
        data_end="2026-01-01",
        batch_size=2048,
        method="platt",
        min_rows=1000,
    )
    assert "--raw-label-panel" in cmd
    assert cmd[cmd.index("--raw-label-panel") + 1] == str(raw)
    assert "renquant_model_patchtst.fit_calibrator" in cmd


# ── surface 2: the σ-head refresh WAS a competing writer — now retired ───────
# The three executable writer-conflict evidence tests (σ-head builder re-emits
# sentiment; column-contract-blind validator; validator rejects extension rows)
# are removed: the single-writer amendment (base-data#48) retired the σ-head
# self-build + validator entirely. The writer cessation is now pinned by
# tests/test_retrain_sigma_head_rawlabel.py (AC-A) and the base-data/σ-head fit
# equivalence by tests/test_sigma_head_fit_equivalence.py (AC-B).


def test_embedded_176_schema_is_sentiment_free():
    # Frozen historical snapshot of the PRE-amendment 176-col contract; the
    # canonical contract is now 179 (base-data#48). Kept only to pin the
    # provenance of the archived fixture.
    assert len(SIDECAR_COLUMNS) == 176
    assert not set(SENTIMENT_COLS) & set(SIDECAR_COLUMNS)
    assert SIDECAR_COLUMNS[-1] == sigma_mod.RAWLABEL_COLUMN
