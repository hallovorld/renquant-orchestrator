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


def test_the_daily_bundle_does_not_carry_feature_vectors():
    """The measured reason the producer cannot be built. If this starts failing,
    step 1 of the plan has landed and the design doc must be revisited."""
    src = inspect.getsource(daily.PersistDailyRunBundleTask)
    bundle_keys = [ln for ln in src.splitlines() if ln.strip().startswith('"')]
    assert not any("feature" in ln.lower() and "manifest" not in ln.lower()
                   for ln in bundle_keys), bundle_keys
