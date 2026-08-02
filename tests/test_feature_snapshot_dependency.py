"""GOAL-1 — the T-1 feature-snapshot producer is blocked on an upstream omission.

orch#647: shadow-serving stays dead until a producer materialises a `FeatureSnapshot`.
Task #17: serving feature vectors are never persisted. Same blocker, two ends.

These pin the second half so the day someone starts persisting features, the doc's
premise visibly changes rather than rotting.
"""

from __future__ import annotations

import inspect

from renquant_orchestrator import daily, realtime_data_plane


def test_the_snapshot_contract_is_three_keys():
    """Cheap to satisfy — except for `features`."""
    src = inspect.getsource(realtime_data_plane.FeatureSnapshot.from_mapping)
    for key in ("feature_cutoff", "feature_builder_version", "features"):
        assert key in src, key


def test_the_daily_bundle_now_carries_the_serving_features_block():
    """THE PREMISE FLIPPED, as this test was built to detect. Its previous
    form pinned the measured omission ("the daily bundle does not carry
    feature vectors -- the reason the producer cannot be built"). The plan it
    guarded then landed: pipeline#250 (design), pipeline#252 (the run
    persists the AS-SERVED matrix + digest sidecar), and the orchestrator
    pickup of that record into the bundle (#250 rollout step 3). This
    successor pins the NEW premise: the bundle emits the tri-state
    ``serving_features`` block, so the T-1 producer's missing input now has
    a standing home -- the remaining work (orch#647) is a formatting step
    over yesterday's parquet, not an excavation."""
    src = inspect.getsource(daily.PersistDailyRunBundleTask)
    assert '"serving_features": serving_features_block(' in src
    # and the digest-sidecar record comes from the shared provenance module,
    # imported -- not a re-implementation inside the task
    module_src = inspect.getsource(daily)
    assert ("from renquant_orchestrator.serving_features_provenance import "
            "serving_features_block") in module_src
