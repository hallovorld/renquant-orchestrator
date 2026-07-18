"""Run-bundle binding fields — GOAL-5 AC4 phase 3 PR-C (RFC RenQuant#492 §2.2).

Covers BOTH paths of the optional provenance block:

* store NOT deployed (the current daily reality; migration is gated on
  the RFC §3 census): the persisted run bundle carries the explicit
  ``{"bundle_store": "not_deployed"}`` marker and nothing else changes;
* a resolved bundle: the four §2.2 fields ``{bundle_id, manifest_digest,
  member digests, pointer_generation}`` are recorded, fail-closed on any
  partial/malformed resolution.

The resolved-bundle fake mirrors the renquant-artifacts
``ResolvedBundle``/``PublishResult`` shape (``bundle_id`` /
``generation`` / ``manifest.manifest_digest`` / ``manifest.members``
with per-member ``sha256``+``bytes``) — duck-typed on purpose so this
repo records provenance without importing the store.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from renquant_orchestrator.serving_bundle_provenance import (
    BINDING_FIELDS,
    BUNDLE_STORE_NOT_DEPLOYED,
    BUNDLE_STORE_RESOLVED,
    serving_bundle_provenance,
)

BUNDLE_ID = "20260718T030001Z-0123456789abcdef"
MANIFEST_DIGEST = "d" * 64
PANEL = "panel-ltr.alpha158_fund.json"
CAL = "panel-rank-calibration.json"


def _resolved(**overrides):
    members = overrides.pop(
        "members",
        {
            PANEL: SimpleNamespace(sha256="a" * 64, bytes=452),
            CAL: SimpleNamespace(sha256="b" * 64, bytes=463),
        },
    )
    manifest = overrides.pop(
        "manifest",
        SimpleNamespace(manifest_digest=MANIFEST_DIGEST, members=members),
    )
    base = {
        "bundle_id": BUNDLE_ID,
        "generation": 7,
        "manifest": manifest,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


# ---------------------------------------------------------------------------
# Helper: not-deployed path
# ---------------------------------------------------------------------------

def test_none_records_explicit_not_deployed_marker() -> None:
    block = serving_bundle_provenance(None)
    assert block == {"bundle_store": BUNDLE_STORE_NOT_DEPLOYED}


def test_default_argument_is_the_not_deployed_marker() -> None:
    assert serving_bundle_provenance() == {"bundle_store": "not_deployed"}


# ---------------------------------------------------------------------------
# Helper: resolved path
# ---------------------------------------------------------------------------

def test_resolved_records_all_four_binding_fields() -> None:
    block = serving_bundle_provenance(_resolved())
    assert block["bundle_store"] == BUNDLE_STORE_RESOLVED
    assert set(BINDING_FIELDS) <= set(block)
    assert block["bundle_id"] == BUNDLE_ID
    assert block["manifest_digest"] == MANIFEST_DIGEST
    assert block["pointer_generation"] == 7
    assert block["member_digests"] == {
        PANEL: {"sha256": "a" * 64, "bytes": 452},
        CAL: {"sha256": "b" * 64, "bytes": 463},
    }
    # JSON-serializable as-is (it goes straight into run_bundle.json).
    json.dumps(block)


def test_resolved_accepts_mapping_style_member_digests() -> None:
    block = serving_bundle_provenance(
        _resolved(
            members={
                PANEL: {"sha256": "a" * 64, "bytes": 1},
                CAL: {"sha256": "b" * 64, "bytes": 2},
            }
        )
    )
    assert block["member_digests"][PANEL] == {"sha256": "a" * 64, "bytes": 1}


@pytest.mark.parametrize(
    "overrides, match",
    [
        ({"bundle_id": None}, "bundle_id"),
        ({"bundle_id": ""}, "bundle_id"),
        ({"manifest": None}, "manifest_digest"),
        (
            {"manifest": SimpleNamespace(manifest_digest="", members={})},
            "manifest_digest",
        ),
        (
            {"manifest": SimpleNamespace(manifest_digest="d" * 64, members={})},
            "member digest map",
        ),
        (
            {
                "members": {
                    PANEL: SimpleNamespace(sha256="a" * 64, bytes=1),
                    CAL: SimpleNamespace(sha256=None, bytes=2),
                }
            },
            "sha256",
        ),
        (
            {
                "members": {
                    PANEL: SimpleNamespace(sha256="a" * 64, bytes=1),
                    CAL: SimpleNamespace(sha256="b" * 64, bytes=None),
                }
            },
            "byte size",
        ),
        ({"generation": None}, "pointer generation"),
        ({"generation": "7"}, "pointer generation"),
        ({"generation": True}, "pointer generation"),
    ],
)
def test_partial_resolution_fails_closed(overrides: dict, match: str) -> None:
    """§2.2 replay guarantee: never persist a half-recorded binding —
    raise instead (the not-deployed marker is the ONLY sanctioned
    degraded record, and it is for the store being absent, not broken)."""
    with pytest.raises(ValueError, match=match):
        serving_bundle_provenance(_resolved(**overrides))


# ---------------------------------------------------------------------------
# Persistence integration: PersistDailyRunBundleTask records the block
# ---------------------------------------------------------------------------

def _persisted_bundle(tmp_path: Path, ctx) -> dict:
    from renquant_orchestrator.daily import PersistDailyRunBundleTask

    assert PersistDailyRunBundleTask().run(ctx) is True
    return json.loads((ctx.output_dir / "run_bundle.json").read_text())


def _setup_daily_ctx(tmp_path: Path):
    """Minimal PersistDailyRunBundleTask-ready context (mirrors
    tests/test_daily.py::TestPersistDailyRunBundleTask)."""
    from renquant_execution import ExecutionContext
    from renquant_model_gbdt import TrainingContext
    from renquant_pipeline import InferenceContext

    from tests.test_daily import (
        _artifact_manifest,
        _data_manifest,
        _make_ctx,
        _market_snapshot,
        _model_config,
        _strategy_config,
    )

    ctx = _make_ctx(tmp_path)
    ctx.training_context = TrainingContext(
        dataset_manifest=_data_manifest(),
        model_config=_model_config(),
        output_dir=tmp_path / "training",
    )
    ctx.training_context.artifact_manifest = _artifact_manifest()
    ctx.inference_context = InferenceContext(
        strategy_config=_strategy_config(),
        data_manifest=_data_manifest(),
        artifact_manifest=_artifact_manifest(),
        market_snapshot=_market_snapshot(),
    )
    ctx.execution_context = ExecutionContext(
        broker_name="paper", order_intents=[],
    )
    ctx.output_dir.mkdir(parents=True, exist_ok=True)
    return ctx


def test_persisted_run_bundle_carries_not_deployed_marker_by_default(
    tmp_path: Path,
) -> None:
    """Store not deployed (ctx default): the run bundle states it
    explicitly, and the daily run's behavior is otherwise unchanged."""
    ctx = _setup_daily_ctx(tmp_path)
    assert ctx.resolved_serving_bundle is None
    bundle = _persisted_bundle(tmp_path, ctx)
    assert bundle["serving_bundle"] == {"bundle_store": "not_deployed"}


def test_persisted_run_bundle_records_resolved_binding_fields(
    tmp_path: Path,
) -> None:
    ctx = _setup_daily_ctx(tmp_path)
    ctx.resolved_serving_bundle = _resolved()
    bundle = _persisted_bundle(tmp_path, ctx)
    block = bundle["serving_bundle"]
    assert block["bundle_store"] == "resolved"
    assert block["bundle_id"] == BUNDLE_ID
    assert block["manifest_digest"] == MANIFEST_DIGEST
    assert block["pointer_generation"] == 7
    assert sorted(block["member_digests"]) == [PANEL, CAL]
