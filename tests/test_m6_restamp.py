"""Tests for the M6 stage-2 step-2 v1 fingerprint re-stamp tool.

Fixture artifacts only -- NEVER the live tree.  Hash values are obtained
from renquant_common.model_fingerprint (imports only).  Tests skip when
the sibling renquant-common checkout is not importable.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

mf = pytest.importorskip(
    "renquant_common.model_fingerprint",
    reason="sibling renquant-common checkout not on PYTHONPATH",
)
from renquant_orchestrator.m6_restamp import (  # noqa: E402
    compute_v1_fingerprint,
    find_model_metadata,
    load_metadata,
    main,
    restamp_metadata,
    verify_roundtrip,
)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _model_payload(seed: str = "default") -> dict:
    """A synthetic model metadata payload with both PREDICTIVE and OPERATIONAL keys."""
    return {
        # PREDICTIVE keys
        "kind": "panel_ltr_xgboost",
        "booster_raw_json": json.dumps({"trees": [1, 2, 3], "seed": seed}),
        "feature_cols": ["f1", "f2", "f3"],
        "feature_means": [0.1, 0.2, 0.3],
        "feature_stds": [1.0, 1.1, 1.2],
        "params": {"eta": 0.1, "max_depth": 6, "objective": "rank:pairwise"},
        "label_col": "fwd_60d_excess",
        "lookahead_days": 60,
        # OPERATIONAL keys
        "trained_date": "2026-07-01",
        "version": 3,
        "metadata": {"score_sample_range": [-0.5, 0.2]},
        "eval_ic": 0.045,
        "best_iter": 150,
    }


def _write_metadata(path: Path, payload: dict) -> Path:
    """Write a model metadata JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _make_tree(tmp_path: Path) -> Path:
    """Build a mock directory tree with model_metadata.json files."""
    root = tmp_path / "artifacts"

    # Three model metadata files at various depths.
    _write_metadata(
        root / "prod" / "model_metadata.json",
        _model_payload("prod"),
    )
    _write_metadata(
        root / "shadow" / "lane_a" / "model_metadata.json",
        _model_payload("shadow-a"),
    )
    _write_metadata(
        root / "wf" / "2026-03-02" / "model_metadata.json",
        _model_payload("wf-fold"),
    )
    # A non-metadata JSON file that should NOT be found.
    _write_metadata(
        root / "prod" / "calibration.json",
        {"method": "platt", "metadata": {}},
    )
    # A non-JSON file that should NOT be found.
    (root / "prod" / "notes.txt").write_text("not json")

    return root


# ---------------------------------------------------------------------------
# find_model_metadata
# ---------------------------------------------------------------------------

class TestFindModelMetadata:

    def test_finds_all_metadata_files(self, tmp_path):
        root = _make_tree(tmp_path)
        paths = find_model_metadata(root)
        assert len(paths) == 3
        names = [p.parent.name for p in paths]
        # Sorted order: lane_a, 2026-03-02, prod (alphabetic by full path).
        assert all(p.name == "model_metadata.json" for p in paths)

    def test_excludes_non_metadata_files(self, tmp_path):
        root = _make_tree(tmp_path)
        paths = find_model_metadata(root)
        path_strs = [str(p) for p in paths]
        assert not any("calibration.json" in s for s in path_strs)
        assert not any("notes.txt" in s for s in path_strs)

    def test_returns_empty_on_nonexistent_dir(self, tmp_path):
        paths = find_model_metadata(tmp_path / "nonexistent")
        assert paths == []

    def test_returns_empty_on_empty_dir(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        paths = find_model_metadata(empty)
        assert paths == []

    def test_custom_filename(self, tmp_path):
        root = tmp_path / "artifacts"
        _write_metadata(root / "custom_meta.json", _model_payload())
        paths = find_model_metadata(root, filename="custom_meta.json")
        assert len(paths) == 1
        assert paths[0].name == "custom_meta.json"

    def test_results_are_sorted(self, tmp_path):
        root = _make_tree(tmp_path)
        paths = find_model_metadata(root)
        assert paths == sorted(paths)


# ---------------------------------------------------------------------------
# load_metadata
# ---------------------------------------------------------------------------

class TestLoadMetadata:

    def test_loads_valid_json(self, tmp_path):
        payload = _model_payload()
        path = _write_metadata(tmp_path / "model_metadata.json", payload)
        result = load_metadata(path)
        assert result == payload

    def test_raises_on_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_metadata(tmp_path / "missing.json")

    def test_raises_on_invalid_json(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("not json {{{")
        with pytest.raises(json.JSONDecodeError):
            load_metadata(path)

    def test_raises_on_non_dict_json(self, tmp_path):
        path = tmp_path / "list.json"
        path.write_text("[1, 2, 3]")
        with pytest.raises(ValueError, match="expected JSON object"):
            load_metadata(path)


# ---------------------------------------------------------------------------
# compute_v1_fingerprint
# ---------------------------------------------------------------------------

class TestComputeV1Fingerprint:

    def test_deterministic_output(self):
        payload = _model_payload("deterministic")
        fp1 = compute_v1_fingerprint(payload)
        fp2 = compute_v1_fingerprint(payload)
        assert fp1 == fp2
        assert fp1.startswith("sha256:")
        assert len(fp1) == len("sha256:") + 64  # sha256 hex digest

    def test_matches_shared_impl(self):
        """The tool's fingerprint must be the SAME object as renquant-common's."""
        payload = _model_payload()
        tool_fp = compute_v1_fingerprint(payload)
        shared_fp = mf.model_content_sha256(payload)
        assert tool_fp == shared_fp

    def test_different_content_different_hash(self):
        fp1 = compute_v1_fingerprint(_model_payload("seed-a"))
        fp2 = compute_v1_fingerprint(_model_payload("seed-b"))
        assert fp1 != fp2

    def test_operational_changes_do_not_affect_hash(self):
        payload_a = _model_payload("same")
        payload_b = _model_payload("same")
        payload_b["trained_date"] = "2099-12-31"
        payload_b["eval_ic"] = 0.999
        payload_b["best_iter"] = 9999
        assert compute_v1_fingerprint(payload_a) == compute_v1_fingerprint(payload_b)

    def test_raises_on_unclassified_key(self):
        payload = _model_payload()
        payload["totally_new_field"] = "surprise"
        with pytest.raises(mf.UnclassifiedKeyError):
            compute_v1_fingerprint(payload)

    def test_raises_on_non_finite_predictive_value(self):
        payload = _model_payload()
        payload["feature_means"] = [0.1, float("nan"), 0.3]
        with pytest.raises(mf.NonFiniteValueError):
            compute_v1_fingerprint(payload)


# ---------------------------------------------------------------------------
# restamp_metadata -- dry-run
# ---------------------------------------------------------------------------

class TestRestampDryRun:

    def test_dry_run_does_not_modify_file(self, tmp_path):
        payload = _model_payload()
        path = _write_metadata(tmp_path / "model_metadata.json", payload)
        before = path.read_bytes()

        result = restamp_metadata(path, dry_run=True)

        assert result["status"] == "dry_run"
        assert result["dry_run"] is True
        assert result["v1_fingerprint"] is not None
        assert result["v1_fingerprint"].startswith("sha256:")
        assert path.read_bytes() == before  # file unchanged

    def test_dry_run_reports_prior_state(self, tmp_path):
        payload = _model_payload()
        payload["model_content_fingerprint"] = "sha256:" + "a" * 64
        payload["fingerprint_schema_version"] = 99
        path = _write_metadata(tmp_path / "model_metadata.json", payload)

        result = restamp_metadata(path, dry_run=True)

        assert result["prior_fingerprint"] == "sha256:" + "a" * 64
        assert result["prior_schema_version"] == 99

    def test_dry_run_default(self, tmp_path):
        """dry_run=True is the default -- safety invariant."""
        payload = _model_payload()
        path = _write_metadata(tmp_path / "model_metadata.json", payload)
        before = path.read_bytes()

        result = restamp_metadata(path)  # no explicit dry_run

        assert result["dry_run"] is True
        assert path.read_bytes() == before

    def test_dry_run_on_error_payload(self, tmp_path):
        payload = _model_payload()
        payload["unknown_key_xyz"] = "boom"
        path = _write_metadata(tmp_path / "model_metadata.json", payload)

        result = restamp_metadata(path, dry_run=True)

        assert result["status"] == "error"
        assert "UnclassifiedKeyError" in result["error"] or "unclassified" in result["error"]


# ---------------------------------------------------------------------------
# restamp_metadata -- wet-run (apply)
# ---------------------------------------------------------------------------

class TestRestampWetRun:

    def test_wet_run_writes_v1_stamp(self, tmp_path):
        payload = _model_payload()
        path = _write_metadata(tmp_path / "model_metadata.json", payload)

        result = restamp_metadata(path, dry_run=False)

        assert result["status"] == "stamped"
        assert result["v1_fingerprint"] is not None

        written = json.loads(path.read_text())
        assert written["model_content_fingerprint"] == result["v1_fingerprint"]
        assert written["fingerprint_schema_version"] == mf.FINGERPRINT_SCHEMA_VERSION

    def test_wet_run_preserves_legacy_hash(self, tmp_path):
        payload = _model_payload()
        legacy_hash = "sha256:" + "b" * 64
        payload["model_content_fingerprint"] = legacy_hash
        path = _write_metadata(tmp_path / "model_metadata.json", payload)

        result = restamp_metadata(path, dry_run=False)

        written = json.loads(path.read_text())
        # The prior legacy hash is preserved for audit/rollback.
        assert written["model_content_fingerprint_legacy_081"] == legacy_hash
        # The new v1 hash is written.
        assert written["model_content_fingerprint"] == result["v1_fingerprint"]
        assert written["model_content_fingerprint"] != legacy_hash

    def test_wet_run_writes_provenance(self, tmp_path):
        payload = _model_payload()
        path = _write_metadata(tmp_path / "model_metadata.json", payload)

        restamp_metadata(path, dry_run=False)

        written = json.loads(path.read_text())
        prov = written["restamp_provenance"]
        assert prov["tool"] == "renquant_orchestrator.m6_restamp"
        assert prov["schema_version"] == mf.FINGERPRINT_SCHEMA_VERSION
        assert "timestamp" in prov

    def test_wet_run_preserves_predictive_content(self, tmp_path):
        payload = _model_payload("preserve-test")
        path = _write_metadata(tmp_path / "model_metadata.json", payload)
        fp_before = compute_v1_fingerprint(payload)

        restamp_metadata(path, dry_run=False)

        written = json.loads(path.read_text())
        # v1 fingerprint should match what we computed before the write,
        # since predictive content was not changed.
        assert written["model_content_fingerprint"] == fp_before

    def test_wet_run_error_does_not_write(self, tmp_path):
        payload = _model_payload()
        payload["unknown_key_xyz"] = "causes error"
        path = _write_metadata(tmp_path / "model_metadata.json", payload)
        before = path.read_bytes()

        result = restamp_metadata(path, dry_run=False)

        assert result["status"] == "error"
        assert path.read_bytes() == before  # file unchanged on error


# ---------------------------------------------------------------------------
# verify_roundtrip
# ---------------------------------------------------------------------------

class TestVerifyRoundtrip:

    def test_passes_after_restamp(self, tmp_path):
        payload = _model_payload()
        path = _write_metadata(tmp_path / "model_metadata.json", payload)
        restamp_metadata(path, dry_run=False)

        assert verify_roundtrip(path) is True

    def test_fails_on_unstamped_file(self, tmp_path):
        payload = _model_payload()
        path = _write_metadata(tmp_path / "model_metadata.json", payload)
        # No restamp -- file has no fingerprint_schema_version.
        assert verify_roundtrip(path) is False

    def test_fails_on_tampered_fingerprint(self, tmp_path):
        payload = _model_payload()
        path = _write_metadata(tmp_path / "model_metadata.json", payload)
        restamp_metadata(path, dry_run=False)

        # Tamper with the stored fingerprint.
        written = json.loads(path.read_text())
        written["model_content_fingerprint"] = "sha256:" + "f" * 64
        path.write_text(json.dumps(written, indent=2) + "\n")

        assert verify_roundtrip(path) is False

    def test_fails_on_tampered_content(self, tmp_path):
        payload = _model_payload()
        path = _write_metadata(tmp_path / "model_metadata.json", payload)
        restamp_metadata(path, dry_run=False)

        # Tamper with predictive content.
        written = json.loads(path.read_text())
        written["feature_cols"] = ["f1", "f2", "f3", "f4_injected"]
        path.write_text(json.dumps(written, indent=2) + "\n")

        assert verify_roundtrip(path) is False

    def test_fails_on_missing_file(self, tmp_path):
        assert verify_roundtrip(tmp_path / "nonexistent.json") is False

    def test_fails_on_wrong_schema_version(self, tmp_path):
        payload = _model_payload()
        path = _write_metadata(tmp_path / "model_metadata.json", payload)
        restamp_metadata(path, dry_run=False)

        written = json.loads(path.read_text())
        written["fingerprint_schema_version"] = 99
        path.write_text(json.dumps(written, indent=2) + "\n")

        assert verify_roundtrip(path) is False


# ---------------------------------------------------------------------------
# CLI (main)
# ---------------------------------------------------------------------------

class TestCLI:

    def test_dry_run_cli(self, tmp_path, capsys):
        root = _make_tree(tmp_path)
        rc = main(["--artifacts-dir", str(root)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "dry-run" in out.lower() or "dry_run" in out.lower()
        # No files modified.
        for p in find_model_metadata(root):
            data = json.loads(p.read_text())
            assert "fingerprint_schema_version" not in data

    def test_apply_cli(self, tmp_path, capsys):
        root = _make_tree(tmp_path)
        rc = main(["--artifacts-dir", str(root), "--apply"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "stamped" in out.lower()
        # All files stamped.
        for p in find_model_metadata(root):
            data = json.loads(p.read_text())
            assert data["fingerprint_schema_version"] == mf.FINGERPRINT_SCHEMA_VERSION
            assert data["model_content_fingerprint"].startswith("sha256:")

    def test_apply_with_verify(self, tmp_path, capsys):
        root = _make_tree(tmp_path)
        rc = main(["--artifacts-dir", str(root), "--apply", "--verify"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "PASS" in out

    def test_output_report(self, tmp_path):
        root = _make_tree(tmp_path)
        report_path = tmp_path / "report.json"
        rc = main([
            "--artifacts-dir", str(root),
            "--output-report", str(report_path),
        ])
        assert rc == 0
        assert report_path.exists()
        report = json.loads(report_path.read_text())
        assert report["summary"]["n_total"] == 3
        assert report["summary"]["n_dry_run"] == 3

    def test_nonexistent_dir_returns_2(self, tmp_path, capsys):
        rc = main(["--artifacts-dir", str(tmp_path / "nonexistent")])
        assert rc == 2

    def test_empty_dir_returns_0(self, tmp_path, capsys):
        empty = tmp_path / "empty"
        empty.mkdir()
        rc = main(["--artifacts-dir", str(empty)])
        assert rc == 0

    def test_custom_filename(self, tmp_path, capsys):
        root = tmp_path / "artifacts"
        _write_metadata(root / "sub" / "my_model.json", _model_payload())
        rc = main([
            "--artifacts-dir", str(root),
            "--filename", "my_model.json",
        ])
        assert rc == 0
        out = capsys.readouterr().out
        assert "1 file" in out
