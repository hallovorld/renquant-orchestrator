"""Tests for scripts/mirror_drift_inventory.py and scripts/check_mirror_drift.py."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from mirror_drift_inventory import build_inventory, _is_import_only_diff, _diff_summary


@pytest.fixture
def twin_kernels(tmp_path):
    """Create a pair of kernel directories with known files."""
    pipeline = tmp_path / "pipeline" / "kernel"
    umbrella = tmp_path / "umbrella" / "kernel"
    pipeline.mkdir(parents=True)
    umbrella.mkdir(parents=True)

    # Identical file
    (pipeline / "identical.py").write_text("x = 1\n")
    (umbrella / "identical.py").write_text("x = 1\n")

    # Import-only drift
    (pipeline / "import_drift.py").write_text("from renquant_pipeline.kernel import foo\nx = 1\n")
    (umbrella / "import_drift.py").write_text("from renquant_104.kernel import foo\nx = 1\n")

    # Material drift
    (pipeline / "material.py").write_text("def compute():\n    return 1\n")
    (umbrella / "material.py").write_text("def compute():\n    return 2\n\ndef extra():\n    pass\n")

    # Pipeline-only
    (pipeline / "pipe_only.py").write_text("# pipeline feature\ndef new_gate(): pass\n")

    # Umbrella-only
    (umbrella / "umb_only.py").write_text(
        "def useful_gate():\n    x = 1\n    y = 2\n    z = 3\n    return x + y + z\n"
    )

    # Umbrella-only tiny (should RETIRE)
    (umbrella / "tiny.py").write_text("# stub\n")

    # Subdirectory handling
    (pipeline / "sub").mkdir()
    (umbrella / "sub").mkdir()
    (pipeline / "sub" / "__init__.py").write_text("")
    (umbrella / "sub" / "__init__.py").write_text("")
    (pipeline / "sub" / "shared_sub.py").write_text("a = 1\n")
    (umbrella / "sub" / "shared_sub.py").write_text("a = 1\n")
    (umbrella / "sub" / "umb_sub.py").write_text("def lift_me():\n    return True\n")

    return pipeline, umbrella


def test_build_inventory_counts(twin_kernels):
    pipeline, umbrella = twin_kernels
    inv = build_inventory(pipeline, umbrella)
    c = inv["counts"]
    assert c["pipeline_total"] == 6
    assert c["umbrella_total"] == 8
    assert c["shared"] == 5
    assert c["pipeline_only"] == 1
    assert c["umbrella_only"] == 3


def test_identical_files_classified(twin_kernels):
    pipeline, umbrella = twin_kernels
    inv = build_inventory(pipeline, umbrella)
    assert "identical.py" in inv["identical"]
    assert "sub/shared_sub.py" in inv["identical"]


def test_trivial_drift_classified(twin_kernels):
    pipeline, umbrella = twin_kernels
    inv = build_inventory(pipeline, umbrella)
    assert "import_drift.py" in inv["trivial_drift"]


def test_material_drift_classified(twin_kernels):
    pipeline, umbrella = twin_kernels
    inv = build_inventory(pipeline, umbrella)
    material_files = [e["file"] for e in inv["material_drift"]]
    assert "material.py" in material_files


def test_material_drift_has_summary(twin_kernels):
    pipeline, umbrella = twin_kernels
    inv = build_inventory(pipeline, umbrella)
    for entry in inv["material_drift"]:
        if entry["file"] == "material.py":
            assert "+extra" in entry["summary"]
            break
    else:
        pytest.fail("material.py not found in material_drift")


def test_umbrella_only_dispositions(twin_kernels):
    pipeline, umbrella = twin_kernels
    inv = build_inventory(pipeline, umbrella)
    dispositions = {e["file"]: e["disposition"] for e in inv["umbrella_only"]}
    assert dispositions["tiny.py"] == "RETIRE"
    assert dispositions["umb_only.py"] == "LIFT"


def test_pipeline_only(twin_kernels):
    pipeline, umbrella = twin_kernels
    inv = build_inventory(pipeline, umbrella)
    assert "pipe_only.py" in inv["pipeline_only"]


def test_is_import_only_diff():
    p = ["from renquant_pipeline.kernel import foo", "x = 1"]
    u = ["from renquant_104.kernel import foo", "x = 1"]
    assert _is_import_only_diff(p, u) is True


def test_is_import_only_diff_false():
    p = ["x = 1"]
    u = ["x = 2"]
    assert _is_import_only_diff(p, u) is False


def test_diff_summary_shows_added_funcs():
    p = ["def foo(): pass"]
    u = ["def foo(): pass", "def bar(): pass"]
    summary = _diff_summary(p, u)
    assert "+bar" in summary


def test_json_roundtrip(twin_kernels):
    pipeline, umbrella = twin_kernels
    inv = build_inventory(pipeline, umbrella)
    text = json.dumps(inv)
    loaded = json.loads(text)
    assert loaded["counts"] == inv["counts"]


class TestCheckMirrorDrift:
    """Tests for check_mirror_drift.py."""

    def test_no_drift_against_fresh_baseline(self, twin_kernels, tmp_path):
        from check_mirror_drift import check_drift

        pipeline, umbrella = twin_kernels
        baseline_path = tmp_path / "baseline.json"
        inv = build_inventory(pipeline, umbrella)
        baseline_path.write_text(json.dumps(inv))

        rc = check_drift(pipeline, umbrella, baseline_path, report_only=True)
        assert rc == 0

    def test_new_drift_detected(self, twin_kernels, tmp_path):
        from check_mirror_drift import check_drift

        pipeline, umbrella = twin_kernels
        baseline_path = tmp_path / "baseline.json"
        inv = build_inventory(pipeline, umbrella)
        baseline_path.write_text(json.dumps(inv))

        # Introduce new drift: modify a previously identical file in umbrella
        (umbrella / "identical.py").write_text("x = 999\n")

        rc = check_drift(pipeline, umbrella, baseline_path, report_only=True)
        # Report-only always returns 0
        assert rc == 0

    def test_new_drift_strict_mode(self, twin_kernels, tmp_path):
        from check_mirror_drift import check_drift

        pipeline, umbrella = twin_kernels
        baseline_path = tmp_path / "baseline.json"
        inv = build_inventory(pipeline, umbrella)
        baseline_path.write_text(json.dumps(inv))

        (umbrella / "identical.py").write_text("x = 999\n")

        rc = check_drift(pipeline, umbrella, baseline_path, report_only=False)
        assert rc == 1

    def test_no_baseline_warns(self, twin_kernels, tmp_path, capsys):
        from check_mirror_drift import check_drift

        pipeline, umbrella = twin_kernels
        rc = check_drift(pipeline, umbrella, tmp_path / "missing.json", report_only=True)
        assert rc == 0
        assert "no baseline" in capsys.readouterr().out.lower()

    def test_new_pipeline_only_file_is_not_drift(self, twin_kernels, tmp_path):
        """Pipeline is the sole kernel/ authority — a brand-new pipeline-only
        file is normal pipeline evolution, not umbrella mirror drift, and
        must never trip the strict-mode freeze-line."""
        from check_mirror_drift import check_drift

        pipeline, umbrella = twin_kernels
        baseline_path = tmp_path / "baseline.json"
        inv = build_inventory(pipeline, umbrella)
        baseline_path.write_text(json.dumps(inv))

        (pipeline / "brand_new.py").write_text("def fresh(): pass\n")

        rc = check_drift(pipeline, umbrella, baseline_path, report_only=False)
        assert rc == 0

    def test_new_umbrella_only_file_is_flagged(self, twin_kernels, tmp_path):
        """The umbrella mirror is meant to be frozen — a brand-new
        umbrella-only file is itself suspicious and must still fail
        strict mode."""
        from check_mirror_drift import check_drift

        pipeline, umbrella = twin_kernels
        baseline_path = tmp_path / "baseline.json"
        inv = build_inventory(pipeline, umbrella)
        baseline_path.write_text(json.dumps(inv))

        (umbrella / "brand_new.py").write_text("def fresh(): pass\n")

        rc = check_drift(pipeline, umbrella, baseline_path, report_only=False)
        assert rc == 1
