"""S3-P2: the served-matrix → FeatureSnapshot bridge (orch#1026 / #1030).

The producer computes nothing — it re-keys and re-stamps what the prod scorer
was actually served — so almost every test here is about REFUSING: stale
sources, ambiguous sources, drifted schemas. Producing nothing when provenance
fails is the correct output.
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from renquant_orchestrator.feature_snapshot_producer import (
    build_payload,
    locate_source,
    main,
    write_snapshot,
)
from renquant_orchestrator.realtime_data_plane import FeatureSnapshot


def _manifest(**over):
    base = dict(schema_version="served-matrix-1", lane="alpaca",
                as_of_date="2026-08-21", run_id="2026-08-21-live-abc",
                feature_cols=["BETA10", "RSV5"])
    base.update(over)
    return base


def _matrix():
    return pd.DataFrame({
        "ticker": ["APH", "NEM"],
        "BETA10": [0.5, float("nan")],
        "RSV5": [1.25, -0.75],
        "not_a_feature": ["x", "y"],     # present in parquet, absent from manifest
    })


def _source(tmp_path, date="2026-08-21", lane="alpaca", n=1, manifest=None):
    d = tmp_path / date
    d.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        pq = d / f"{lane}__2026-08-21-live-{i}.parquet"
        _matrix().to_parquet(pq)
        pq.with_suffix(".json").write_text(json.dumps(manifest or _manifest()))
    return tmp_path


class TestLocateFailsClosed:
    def test_happy_path_finds_the_single_prod_pair(self, tmp_path):
        pq, mf = locate_source(_source(tmp_path), "2026-08-24")
        assert pq.name.startswith("alpaca__") and mf.is_file()

    def test_a_stale_source_is_refused_not_substituted(self, tmp_path):
        """An older matrix silently standing in for the prior session is the
        staleness class the batch-score export already refuses."""
        with pytest.raises(SystemExit, match="calendar days"):
            locate_source(_source(tmp_path, date="2026-08-10"), "2026-08-24")

    def test_two_prod_files_on_one_date_are_ambiguous(self, tmp_path):
        with pytest.raises(SystemExit, match="exactly one"):
            locate_source(_source(tmp_path, n=2), "2026-08-24")

    def test_shadow_lane_files_do_not_count_as_prod(self, tmp_path):
        root = _source(tmp_path, lane="alpaca_shadow_blend")
        with pytest.raises(SystemExit, match="exactly one"):
            locate_source(root, "2026-08-24")

    def test_missing_manifest_is_fatal(self, tmp_path):
        root = _source(tmp_path)
        next(root.glob("*/alpaca__*.json")).unlink()
        with pytest.raises(SystemExit, match="manifest missing"):
            locate_source(root, "2026-08-24")


class TestPayloadHonoursTheREALContract:
    def test_the_payload_round_trips_through_FeatureSnapshot(self):
        p = build_payload(_matrix(), _manifest())
        fs = FeatureSnapshot.from_mapping(p)
        assert fs.cutoff == "2026-08-21"
        assert fs.builder_version.startswith("served-matrix-bridge-v1+partial-bar-1355")
        assert fs.features["APH"]["RSV5"] == 1.25

    def test_the_vintage_marker_is_in_the_builder_version(self):
        """Design amendment #1030: the served matrix carries the 13:55
        partial-bar vintage; no consumer may mistake it for an EOD freeze."""
        assert "partial-bar-1355" in build_payload(_matrix(), _manifest())["feature_builder_version"]

    def test_nan_becomes_null_and_features_restrict_to_manifest_cols(self):
        p = build_payload(_matrix(), _manifest())
        assert p["features"]["NEM"]["BETA10"] is None
        assert "not_a_feature" not in p["features"]["APH"], (
            "the manifest's feature_cols is the authority, not the parquet's width")

    @pytest.mark.parametrize("drift,match", [
        (dict(schema_version="served-matrix-2"), "schema_version"),
        (dict(lane="alpaca_shadow_blend"), "lane"),
        (dict(feature_cols=[]), "no feature_cols"),
        (dict(feature_cols=["BETA10", "MISSING_COL"]), "absent from parquet"),
    ])
    def test_drift_fails_closed(self, drift, match):
        with pytest.raises(SystemExit, match=match):
            build_payload(_matrix(), _manifest(**drift))

    def test_a_tickerless_parquet_is_fatal(self):
        with pytest.raises(SystemExit, match="ticker"):
            build_payload(_matrix().drop(columns=["ticker"]), _manifest())


class TestWriteIsAtomicAndSelfDescribing:
    def test_meta_digest_equals_the_class_digest_and_sources_are_hashed(self, tmp_path):
        root = _source(tmp_path / "sm")
        src = locate_source(root, "2026-08-24")
        payload = build_payload(_matrix(), _manifest())
        out, out_meta = write_snapshot(payload, tmp_path / "o", "2026-08-24", src)
        meta = json.loads(out_meta.read_text())
        fs = FeatureSnapshot.from_mapping(json.loads(out.read_text()))
        assert meta["feature_snapshot_digest"] == fs.digest
        assert meta["source_parquet"]["sha256"] and meta["source_manifest"]["sha256"]
        assert not list((tmp_path / "o").glob("*.tmp"))

    def test_end_to_end_via_main_is_deterministic(self, tmp_path):
        root = _source(tmp_path / "sm")
        args = ["--served-matrix-root", str(root), "--out-dir", str(tmp_path / "o"),
                "--date", "2026-08-24"]
        assert main(args) == 0
        first = (tmp_path / "o" / "feature_snapshot_2026-08-24.json").read_bytes()
        assert main(args) == 0
        assert (tmp_path / "o" / "feature_snapshot_2026-08-24.json").read_bytes() == first
