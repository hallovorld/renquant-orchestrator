"""GOAL-3: which twin does the PUBLISHED surface hand out?

The census answers "could a caller reach two definitions". This answers the
one with consequences: for the names the package publishes, which definition
does `from <pkg> import <name>` resolve to? Resolved by importing, not guessed
from import sites — the package's own `__init__` decides.
"""
from __future__ import annotations

from pathlib import Path
import sys

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from scripts.goal3_public_export_resolution import (  # noqa: E402
    STATE_NO_COUNTERPART, STATE_RESOLVES_ELSEWHERE, STATE_RESOLVES_TO_COUNTERPART,
    STATE_UNRESOLVABLE, render, resolve_exports)


def _pkg(tmp_path, name, files: dict, all_names=(), init_extra="",
         with_kernel=True):
    root = tmp_path / name
    if with_kernel:
        (root / "kernel").mkdir(parents=True, exist_ok=True)
        (root / "kernel" / "__init__.py").write_text("", encoding="utf-8")
    else:
        root.mkdir(parents=True, exist_ok=True)
    (root / "__init__.py").write_text(
        f"__all__ = {list(all_names)!r}\n{init_extra}\n", encoding="utf-8")
    for fname, body in files.items():
        (root / fname).write_text(body, encoding="utf-8")
    sys.path.insert(0, str(tmp_path))
    for mod in [m for m in list(sys.modules) if m == name or m.startswith(name + ".")]:
        del sys.modules[mod]
    return name


CLS = "class J:\n    x = {}\n"


class TestItReadsWhatTheExportACTUALLYIs:
    def test_an_export_bound_to_the_NON_kernel_twin_is_named_as_such(self, tmp_path):
        pkg = _pkg(tmp_path, "p_res1",
                   {"plain.py": CLS.format(1), "kernel/twin.py": CLS.format(2)},
                   all_names=["J"], init_extra="from p_res1.plain import J")
        r = resolve_exports(pkg)
        row = r["exports"][0]
        assert row["state"] == STATE_RESOLVES_ELSEWHERE, row
        assert row["resolves_to"] == "p_res1.plain"
        assert row["counterpart_sites"] == ["kernel/twin.py"]

    def test_an_export_bound_to_the_KERNEL_twin_is_named_as_such(self, tmp_path):
        pkg = _pkg(tmp_path, "p_res2",
                   {"plain.py": CLS.format(1), "kernel/twin.py": CLS.format(2)},
                   all_names=["J"], init_extra="from p_res2.kernel.twin import J")
        assert resolve_exports(pkg)["exports"][0]["state"] == \
            STATE_RESOLVES_TO_COUNTERPART

    def test_a_duplicate_with_NO_kernel_twin_is_its_own_state(self, tmp_path):
        """Two non-kernel copies are a duplicate, but not this question."""
        pkg = _pkg(tmp_path, "p_res3",
                   {"a.py": CLS.format(1), "b.py": CLS.format(2)},
                   all_names=["J"], init_extra="from p_res3.a import J")
        assert resolve_exports(pkg)["exports"][0]["state"] == STATE_NO_COUNTERPART

    def test_a_name_defined_ONCE_is_not_reported_at_all(self, tmp_path):
        pkg = _pkg(tmp_path, "p_res4", {"a.py": CLS.format(1)},
                   all_names=["J"], init_extra="from p_res4.a import J")
        assert resolve_exports(pkg)["exports"] == []

    def test_the_SHAPE_rides_along_because_a_wrapper_is_not_a_twin(self, tmp_path):
        """Identical bodies are a copy; differing bodies mean the export is not
        a thin wrapper around the kernel definition."""
        pkg = _pkg(tmp_path, "p_res5",
                   {"plain.py": CLS.format(1), "kernel/twin.py": CLS.format(1)},
                   all_names=["J"], init_extra="from p_res5.plain import J")
        assert resolve_exports(pkg)["exports"][0]["shape"] == "identical-copy"


    def test_an_export_that_carries_NO_module_is_its_own_state(self, tmp_path):
        """A `__all__` entry bound to something with no `__module__` (a plain
        value, a namedtuple field, an int) must not be silently classified —
        the fourth state exists so it lands somewhere visible."""
        pkg = _pkg(tmp_path, "p_res7",
                   {"plain.py": CLS.format(1), "kernel/twin.py": CLS.format(2)},
                   all_names=["J"], init_extra="J = 7")
        assert resolve_exports(pkg)["exports"][0]["state"] == STATE_UNRESOLVABLE

    def test_a_package_with_NO_kernel_root_reads_UNDEFINED_not_clean(self, tmp_path):
        pkg = _pkg(tmp_path, "p_res8",
                   {"a.py": CLS.format(1), "b.py": CLS.format(2)},
                   all_names=["J"], init_extra="from p_res8.a import J",
                   with_kernel=False)
        r = resolve_exports(pkg)
        assert r["has_counterpart_root"] is False
        text = render(r)
        assert "UNDEFINED here, not clean" in text
        assert "RESOLVES" not in text, "no per-export verdict may be printed"

    def test_the_measured_COPY_is_recorded(self, tmp_path):
        """`import` resolves against sys.path: a record naming only the package
        NAME could have measured another checkout or an installed wheel."""
        pkg = _pkg(tmp_path, "p_res9",
                   {"plain.py": CLS.format(1), "kernel/twin.py": CLS.format(2)},
                   all_names=["J"], init_extra="from p_res9.plain import J")
        r = resolve_exports(pkg)
        assert r["package_path"].endswith("p_res9")
        assert "measured copy" in render(r)


def test_the_render_REFUSES_to_say_production_runs_the_wrong_code(tmp_path):
    pkg = _pkg(tmp_path, "p_res6",
               {"plain.py": CLS.format(1), "kernel/twin.py": CLS.format(2)},
               all_names=["J"], init_extra="from p_res6.plain import J")
    text = render(resolve_exports(pkg))
    assert "NOT a claim" in text
    assert "which definition production runs" in text


def test_the_LIVE_pipeline_measurement_behind_the_GOAL3_record():
    """Bound to reality: if the published surface starts handing out the kernel
    twin, the GOAL-3 record must be re-derived rather than inherited."""
    try:
        r = resolve_exports("renquant_pipeline")
    except ModuleNotFoundError:
        pytest.skip("renquant_pipeline not importable here")
    assert r["has_counterpart_root"] is True
    assert r["n_exported_duplicates"] == 20, r["n_exported_duplicates"]
    assert r["counts"][STATE_RESOLVES_ELSEWHERE] == 19, r["counts"]
    assert r["counts"][STATE_RESOLVES_TO_COUNTERPART] == 0, r["counts"]
    va = next(x for x in r["exports"] if x["name"] == "validate_order_attribution")
    assert va["state"] == STATE_RESOLVES_ELSEWHERE
    assert va["shape"] == "differing-bodies", (
        "the public and kernel order-attribution validators accept mutually "
        "incompatible schemas — if they ever converge, re-derive the record")
    # The record cites a specific checkout, not "whatever was importable".
    assert r["package_repo"] is not None and \
        r["package_repo"].endswith("renquant-pipeline"), r["package_repo"]
    assert r["package_repo_revision"] and len(r["package_repo_revision"]) == 40


RECORD = (Path(__file__).resolve().parent.parent / "doc" / "progress" /
          "2026-08-05-goal3-public-export-resolution.md")


def test_the_RECORD_names_the_revision_that_was_actually_measured():
    """[codex on orch#833] Asserting the revision is 40 characters proves
    nothing about the record: the pipeline checkout could advance while the
    aggregate counts stayed 20/19/0, and CI would stay green over a provenance
    claim that had gone stale. The recorded prefix must BE the measured one, so
    a source change forces the result to be re-derived rather than inherited."""
    import re

    try:
        r = resolve_exports("renquant_pipeline")
    except ModuleNotFoundError:
        pytest.skip("renquant_pipeline not importable here")
    text = RECORD.read_text(encoding="utf-8")
    recorded = re.findall(r"repo revision ([0-9a-f]{7,40})", text)
    assert recorded, ("the progress record must state the revision it measured; "
                      "found none in " + str(RECORD))
    measured = r["package_repo_revision"]
    for rev in recorded:
        assert measured.startswith(rev), (
            f"the record cites pipeline revision {rev}, but the measured "
            f"checkout is at {measured[:12]} — re-derive the 20/19/0 result "
            f"against the current source rather than inheriting it")
