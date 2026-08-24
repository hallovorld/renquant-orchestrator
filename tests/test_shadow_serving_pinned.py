"""S3-b wiring tests — the pinned blend scorer adapter (shadow_serving_pinned).

The real pipeline loader is faked via sys.modules injection (its own pin
verification is tested in renquant-pipeline; re-testing it here would be a
proxy). What IS tested here is this module's own contract:

  * refusals propagate (a loader raise is not swallowed);
  * an empty composite fingerprint refuses (no unidentifiable artifact serves);
  * the matrix is built from fresh rows' served values verbatim, censored rows
    excluded, and a fresh row without a feature ref REFUSES;
  * NaN blend outputs are dropped (the non-intersection), finite ones keyed
    by upper-cased ticker;
  * main() digests the served snapshot file and binds it to the scorer, so a
    swapped snapshot is rejected by _resolve_provenance downstream;
  * the delegated collector actually runs with the wired scorer (rc=0, rows
    written) — the "no scorer wired" refusal is gone on this path.
"""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

from renquant_orchestrator import shadow_serving_pinned as mod
from renquant_orchestrator.realtime_data_plane import (
    FeatureSnapshot,
    build_realtime_snapshot,
)
from renquant_orchestrator.shadow_realtime_serving import ProvenanceError


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------
class _FakeBlend:
    def __init__(self, scores, feature_cols=("f1", "f2"), fingerprint="sha256:comp0comp1"):
        self._scores = dict(scores)
        self.feature_cols = list(feature_cols)
        self.metadata = {"config_fingerprint": fingerprint}
        self.seen_matrix = None

    def score(self, matrix, ctx=None):
        import pandas as pd

        self.seen_matrix = matrix
        return pd.Series({t: self._scores.get(t, float("nan")) for t in matrix.index})


def _install_fake_pipeline(monkeypatch, blend=None, raise_exc=None):
    """Inject a fake renquant_pipeline.…blend_scorer with load_blend_scorer."""
    m = types.ModuleType("renquant_pipeline.kernel.panel_pipeline.blend_scorer")

    def load_blend_scorer(config):
        if raise_exc is not None:
            raise raise_exc
        assert config.get("_strategy_dir"), "wiring must anchor _strategy_dir"
        return blend

    m.load_blend_scorer = load_blend_scorer
    for name in (
        "renquant_pipeline",
        "renquant_pipeline.kernel",
        "renquant_pipeline.kernel.panel_pipeline",
    ):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    monkeypatch.setitem(
        sys.modules, "renquant_pipeline.kernel.panel_pipeline.blend_scorer", m
    )
    return m


def _snapshot(tmp_path: Path, tickers=("AAPL", "MSFT"), stale=()):
    payload = {
        "feature_cutoff": "2026-08-21",
        "feature_builder_version": "served-matrix-bridge-v1+test",
        "features": {t: {"f1": 1.0 + i, "f2": 2.0 + i} for i, t in enumerate(tickers)},
    }
    snap_path = tmp_path / "feature_snapshot.json"
    snap_path.write_text(json.dumps(payload))
    ticks = tmp_path / "ticks.jsonl"
    rows = []
    for t in tickers:
        age_ok = t not in stale
        rows.append(
            {
                # the #216 intraday_ticks.jsonl fields the join actually reads:
                # date (session), tick_time (causal ts), mid (priceable)
                "ticker": t,
                "date": "2026-08-24",
                "tick_time": (
                    "2026-08-24T17:00:00+00:00" if age_ok
                    else "2026-08-24T01:00:00+00:00"
                ),
                "mid": 10.1,
                "source": "test",
            }
        )
    ticks.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return snap_path, ticks, payload


def _build_market_snapshot(snap_payload, ticks_path):
    return build_realtime_snapshot(
        as_of="2026-08-24T17:00:05+00:00",
        feature_snapshot=FeatureSnapshot.from_mapping(snap_payload),
        feed_source=_JsonlSource(ticks_path),
    )


class _JsonlSource:
    def __init__(self, path):
        self._path = Path(path)

    def read_ticks(self):
        for line in self._path.read_text().splitlines():
            if line.strip():
                yield json.loads(line)


# ---------------------------------------------------------------------------
# Loader refusals
# ---------------------------------------------------------------------------
def test_loader_refusal_propagates(monkeypatch, tmp_path):
    _install_fake_pipeline(
        monkeypatch, raise_exc=ValueError("content_sha256 MISMATCH")
    )
    cfg = tmp_path / "strategy_config.json"
    cfg.write_text("{}")
    with pytest.raises(ValueError, match="MISMATCH"):
        mod.load_pinned_blend_shadow_scorer(
            strategy_config_path=cfg, strategy_dir=tmp_path
        )


def test_empty_composite_fingerprint_refuses(monkeypatch, tmp_path):
    _install_fake_pipeline(
        monkeypatch, blend=_FakeBlend({}, fingerprint="")
    )
    cfg = tmp_path / "strategy_config.json"
    cfg.write_text("{}")
    with pytest.raises(ProvenanceError, match="unidentifiable"):
        mod.load_pinned_blend_shadow_scorer(
            strategy_config_path=cfg, strategy_dir=tmp_path
        )


# ---------------------------------------------------------------------------
# Matrix construction
# ---------------------------------------------------------------------------
def test_matrix_from_fresh_rows_verbatim(tmp_path):
    snap_path, ticks, payload = _snapshot(tmp_path, tickers=("AAPL", "MSFT"))
    snapshot = _build_market_snapshot(payload, ticks)
    matrix = mod.build_feature_matrix(snapshot, ["f1", "f2"])
    assert sorted(matrix.index) == ["AAPL", "MSFT"]
    assert list(matrix.columns) == ["f1", "f2"]
    assert matrix.loc["AAPL", "f1"] == 1.0
    assert matrix.loc["MSFT", "f2"] == 3.0


def test_matrix_excludes_censored_rows(tmp_path):
    snap_path, ticks, payload = _snapshot(
        tmp_path, tickers=("AAPL", "MSFT"), stale=("MSFT",)
    )
    snapshot = _build_market_snapshot(payload, ticks)
    fresh = {r.ticker for r in snapshot.fresh_rows()}
    assert "MSFT" not in fresh, "precondition: the stale quote must be censored"
    matrix = mod.build_feature_matrix(snapshot, ["f1", "f2"])
    assert list(matrix.index) == ["AAPL"]


def test_fresh_row_without_feature_ref_refuses(tmp_path):
    snap_path, ticks, payload = _snapshot(tmp_path, tickers=("AAPL",))
    snapshot = _build_market_snapshot(payload, ticks)
    stripped = [row.__class__(**{**row.__dict__, "daily_feature_ref": None})
                for row in snapshot.rows]
    bare = snapshot.__class__(
        as_of=snapshot.as_of,
        session_date=snapshot.session_date,
        rows=tuple(stripped),
        metadata=snapshot.metadata,
    )
    with pytest.raises(ProvenanceError, match="daily_feature_ref"):
        mod.build_feature_matrix(bare, ["f1"])


# ---------------------------------------------------------------------------
# Score adaptation
# ---------------------------------------------------------------------------
def test_scores_drop_nan_and_uppercase(monkeypatch, tmp_path):
    blend = _FakeBlend({"AAPL": 1.25, "MSFT": float("nan")})
    _install_fake_pipeline(monkeypatch, blend=blend)
    cfg = tmp_path / "strategy_config.json"
    cfg.write_text("{}")
    scorer = mod.load_pinned_blend_shadow_scorer(
        strategy_config_path=cfg, strategy_dir=tmp_path
    )
    snap_path, ticks, payload = _snapshot(tmp_path, tickers=("AAPL", "MSFT"))
    snapshot = _build_market_snapshot(payload, ticks)
    out = scorer.score(snapshot)
    assert out == {"AAPL": 1.25}
    assert blend.seen_matrix is not None
    assert scorer.artifact_digest == "sha256:comp0comp1"


# ---------------------------------------------------------------------------
# End-to-end through main(): the collector runs with the wired scorer
# ---------------------------------------------------------------------------
def test_main_wires_scorer_and_collector_writes(monkeypatch, tmp_path, capsys):
    blend = _FakeBlend({"AAPL": 0.5, "MSFT": 0.25})
    _install_fake_pipeline(monkeypatch, blend=blend)
    cfg = tmp_path / "strategy_config.json"
    cfg.write_text("{}")
    snap_path, ticks, payload = _snapshot(tmp_path, tickers=("AAPL", "MSFT"))
    scores_path = tmp_path / "batch_scores.json"
    scores_path.write_text(json.dumps({"AAPL": 0.4, "MSFT": 0.3}))
    out_path = tmp_path / "shadow_log.jsonl"

    rc = mod.main(
        [
            "--pinned-strategy-config", str(cfg),
            "--strategy-dir", str(tmp_path),
            "--feature-snapshot-json", str(snap_path),
            "--as-of", "2026-08-24T17:00:05+00:00",
            "--tick-feed", str(ticks),
            "--batch-scores-json", str(scores_path),
            "--batch-run-id", "test-run-1",
            "--out", str(out_path),
            "--json",
        ]
    )
    assert rc == 0, "the wired path must not hit the no-scorer refusal (rc=2)"
    summary = json.loads(capsys.readouterr().out)
    assert summary["n_written"] > 0, "collector must actually write rows"
    rows = [json.loads(l) for l in out_path.read_text().splitlines() if l.strip()]
    expected_digest = FeatureSnapshot.from_mapping(payload).digest
    for row in rows:
        assert row["artifact_digest"] == "sha256:comp0comp1"
        assert row["feature_snapshot_digest"] == expected_digest


def test_main_requires_pinned_config(monkeypatch, tmp_path):
    with pytest.raises(SystemExit):
        mod.main(["--strategy-dir", str(tmp_path)])
