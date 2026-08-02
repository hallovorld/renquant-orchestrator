"""pipeline#250 rollout step 3 — the daily bundle consumes the serving-features record.

Step 2 (pipeline#252, merged) made the pipeline stage the AS-SERVED matrix +
digest sidecar on the inference context. These tests pin the orchestrator
pickup: the daily ``run_bundle.json`` carries an additive ``serving_features``
block — the forwarded record when the producer staged (sha passthrough
verified against the parquet bytes ON DISK), an explicit ``not_staged``
marker when it did not (tri-state, never a missing key), tri-stated version
skew, and no disturbance to the AC6 R4 contract validation. The
bundle-shaped tests DRIVE THE REAL ``PersistDailyRunBundleTask`` and read
the artifact it wrote (the #669 lesson: in-memory assertions cannot see a
file-only defect).
"""

from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from renquant_orchestrator.serving_features_provenance import (
    STATUS_NOT_STAGED,
    STATUS_PIPELINE_SUPPORT_UNAVAILABLE,
    serving_features_block,
)

# The sibling-checkout skew guard, same pattern as test_daily_bundle_contract's
# `needs_binding`: an installed renquant-pipeline predating the #252 exports
# skips LOUDLY instead of measuring this machine's disk. CI checks out
# renquant-pipeline main and runs these.
try:
    from renquant_pipeline import stage_serving_features  # noqa: F401

    _HAS_SERVING_FEATURES = True
except ImportError:  # pragma: no cover - pre-#252 sibling checkout
    _HAS_SERVING_FEATURES = False

needs_serving_features = pytest.mark.skipif(
    not _HAS_SERVING_FEATURES,
    reason="installed renquant-pipeline predates the #252 serving-features "
    "exports — sync the sibling checkout. NOTE: the Makefile PIPELINE_SRC "
    "override does NOT reach pytest (pyproject's [tool.pytest.ini_options] "
    "pythonpath hardcodes ../renquant-pipeline/src ahead of it, measured "
    "2026-08-02); to run these against a current pipeline without touching "
    "the sibling, pass -o 'pythonpath=src ... <current-pipeline>/src ...'",
)


def _staged_inference_ctx(matrix=None):
    """An inference-context stand-in with a REAL staged matrix (via the
    pipeline's own producer, not a hand-built record)."""
    import datetime

    import pandas as pd

    from renquant_pipeline import stage_serving_features

    ctx = SimpleNamespace(
        decision_trace=[{"symbol": "AAPL"}], order_intents=[],
        today=datetime.date(2026, 8, 2),
    )
    if matrix is None:
        matrix = pd.DataFrame(
            {"f1": [1.25, -3.5], "f2": [0.5, 2.0]}, index=["AAA", "BBB"],
        )
    scorer = SimpleNamespace(
        feature_cols=["f1", "f2"],
        metadata={"feature_preprocess_version": 2},
    )
    stage_serving_features(ctx, matrix, scorer)
    return ctx, matrix


def _drive_bundle_task(tmp_path, inference_ctx):
    """Run the REAL PersistDailyRunBundleTask and return the on-disk bundle."""
    from renquant_orchestrator.daily import PersistDailyRunBundleTask

    ns = SimpleNamespace
    ctx = ns(
        run_id="2026-08-02T00:00:00Z", run_type="daily_full", dry_run=True,
        strategy_manifest={}, strategy_config={}, data_manifest={},
        market_snapshot={}, account_snapshot={}, resolved_serving_bundle=None,
        g4_session_admission=None, backtest_context=None,
        output_dir=tmp_path, stage_trace=[], run_bundle=None,
        training_context=ns(artifact_manifest={"a": 1}),
        inference_context=inference_ctx,
        execution_context=ns(submitted_orders=[{"symbol": "AAPL", "qty": 1}],
                             audit_rows=[{"stage": "submit", "ok": True}]),
    )
    PersistDailyRunBundleTask().run(ctx)
    return json.loads((tmp_path / "run_bundle.json").read_text(encoding="utf-8"))


# ── staged → the bundle carries the forwarded record, sha verified on disk ──


@needs_serving_features
def test_bundle_carries_the_block_when_staged(tmp_path: Path) -> None:
    import pandas as pd

    inference_ctx, matrix = _staged_inference_ctx()
    bundle = _drive_bundle_task(tmp_path, inference_ctx)

    block = bundle["serving_features"]
    assert block["status"] == "written"
    # the deferred write completed into THIS run's output dir
    parquet = tmp_path / "serving_features.parquet"
    assert parquet.exists()
    assert block["path"] == str(parquet)
    # sha passthrough: the bundle's digest is the digest of the file's bytes
    assert block["sha256"] == hashlib.sha256(parquet.read_bytes()).hexdigest()
    assert block["n_rows"] == 2 and block["n_cols"] == 2
    assert block["feature_cutoff"] == "2026-08-02"
    assert block["feature_builder_version"] == "2"
    # and the file IS the staged matrix
    read_back = pd.read_parquet(parquet)
    assert (
        read_back[["f1", "f2"]].to_numpy().tobytes()
        == matrix.to_numpy().tobytes()
    )


@needs_serving_features
def test_a_completed_record_is_forwarded_verbatim(tmp_path: Path) -> None:
    """When the pipeline already finalized the write (facade / payload-writer
    paths), the bundle forwards that record — it does not re-write."""
    from renquant_pipeline import write_staged_serving_features

    inference_ctx, _ = _staged_inference_ctx()
    pipeline_dir = tmp_path / "pipeline-run"
    record = write_staged_serving_features(inference_ctx, pipeline_dir)
    assert record["status"] == "written"

    bundle_dir = tmp_path / "bundle-run"
    bundle_dir.mkdir()
    bundle = _drive_bundle_task(bundle_dir, inference_ctx)
    assert bundle["serving_features"] == record
    assert not (bundle_dir / "serving_features.parquet").exists()


# ── not staged → explicit marker, never a missing key ───────────────────────


@needs_serving_features
def test_explicit_absent_marker_when_not_staged(tmp_path: Path) -> None:
    inference_ctx = SimpleNamespace(decision_trace=[], order_intents=[])
    bundle = _drive_bundle_task(tmp_path, inference_ctx)
    block = bundle["serving_features"]
    assert block["status"] == STATUS_NOT_STAGED
    assert "note" in block
    assert not (tmp_path / "serving_features.parquet").exists()


def test_the_key_is_always_present_whatever_the_pipeline_vintage(
    tmp_path: Path,
) -> None:
    """Tri-state means the KEY exists on every bundle — a pre-#252 pipeline
    yields the skew marker, a current one the not-staged marker; absence of
    the key would be indistinguishable from a pre-step-3 orchestrator."""
    inference_ctx = SimpleNamespace(decision_trace=[], order_intents=[])
    bundle = _drive_bundle_task(tmp_path, inference_ctx)
    block = bundle["serving_features"]
    assert isinstance(block, dict)
    assert block["status"] in (
        STATUS_NOT_STAGED, STATUS_PIPELINE_SUPPORT_UNAVAILABLE,
    )


# ── version skew → tri-stated, never raised ─────────────────────────────────


def test_pre_252_pipeline_is_tri_stated_not_raised() -> None:
    import builtins

    real = builtins.__import__

    def boom(name, *a, **k):
        if name == "renquant_pipeline":
            raise ImportError("simulated pre-#252 pipeline")
        return real(name, *a, **k)

    builtins.__import__ = boom
    try:
        block = serving_features_block(SimpleNamespace(), output_dir=None)
    finally:
        builtins.__import__ = real
    assert block["status"] == STATUS_PIPELINE_SUPPORT_UNAVAILABLE
    assert "error" in block


# ── failure containment: a producer write failure is a status, not an abort ─


@needs_serving_features
def test_write_failure_is_forwarded_and_the_bundle_still_lands(
    tmp_path: Path,
) -> None:
    inference_ctx, _ = _staged_inference_ctx()
    blocker = tmp_path / "blocker"
    blocker.write_text("a file where the output dir must go")

    block = serving_features_block(
        inference_ctx, output_dir=blocker / "nested",
    )
    assert block["status"] == "write_failed"
    assert block["error"]

    # and the daily task still persists a bundle carrying that verdict
    # (a fresh ctx so the failed record does not leak across the assert)
    inference_ctx2, _ = _staged_inference_ctx()
    bundle = _drive_bundle_task(tmp_path / "run", inference_ctx2)
    assert bundle["serving_features"]["status"] == "written"


# ── AC6 R4 contract validation undisturbed ──────────────────────────────────


try:
    from renquant_common import validate_live_run_bundle as _vlrb

    _HAS_BINDING = (
        "require_gate_provenance" in inspect.signature(_vlrb).parameters
    )
except ImportError:  # pragma: no cover
    _HAS_BINDING = False

needs_binding = pytest.mark.skipif(
    not _HAS_BINDING,
    reason="installed renquant-common predates the require_gate_provenance "
    "switch (common#40) — sync the sibling checkout (orch#747 item 6)",
)


@needs_binding
@needs_serving_features
def test_contract_validation_unaffected_when_staged(tmp_path: Path) -> None:
    inference_ctx, _ = _staged_inference_ctx()
    bundle = _drive_bundle_task(tmp_path, inference_ctx)
    assert bundle["contract_validation"]["ok"] is True, (
        bundle["contract_validation"]
    )


@needs_binding
def test_contract_validation_unaffected_when_absent(tmp_path: Path) -> None:
    inference_ctx = SimpleNamespace(decision_trace=[], order_intents=[])
    bundle = _drive_bundle_task(tmp_path, inference_ctx)
    assert bundle["contract_validation"]["ok"] is True, (
        bundle["contract_validation"]
    )


# ── the emitted source, not only this file's fixtures ───────────────────────


def test_the_daily_task_actually_emits_serving_features() -> None:
    """Same pattern that guards `source` and `wf_gate_provenance`: the block
    is in the emitted dict, not only in these fixtures."""
    from renquant_orchestrator import daily

    src = inspect.getsource(daily.PersistDailyRunBundleTask)
    assert '"serving_features": serving_features_block(' in src
