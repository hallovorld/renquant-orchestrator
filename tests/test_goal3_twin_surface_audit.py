"""GOAL-3: the twin guard's SUBJECT, measured before anyone installs it elsewhere.

renquant-pipeline's twin guard scans `__all__`. The obvious next step — install
it in the other repos — has a prior question: would it SEE anything there?
Measured 2026-08-05: `__all__` covers 3 of renquant-orchestrator's 949
module-level public definitions, so an `__all__`-scoped guard there would report
clean forever. That is the registry's own defect class (a check whose subject is
not the object you assume), one level up.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.goal3_twin_surface_audit import audit, render  # noqa: E402


def _pkg(tmp_path, name, files: dict, all_names=()):
    root = tmp_path / name
    root.mkdir(parents=True, exist_ok=True)
    (root / "__init__.py").write_text(f"__all__ = {list(all_names)!r}\n",
                                      encoding="utf-8")
    for fname, body in files.items():
        (root / fname).write_text(body, encoding="utf-8")
    sys.path.insert(0, str(tmp_path))
    for mod in [m for m in list(sys.modules) if m == name or m.startswith(name + ".")]:
        del sys.modules[mod]
    return name


class TestItSeparatesCopiesFromTwins:
    def test_identical_bodies_read_as_a_COPY(self, tmp_path):
        same = "class J:\n    def run(self):\n        return 1\n"
        pkg = _pkg(tmp_path, "p_copy", {"a.py": same, "b.py": same})
        d = audit(pkg)["duplicates"]["J"]
        assert d["shape"] == "identical-copy"
        assert {s["body_sha256"] for s in d["sites"]} == {d["sites"][0]["body_sha256"]}

    def test_differing_bodies_read_as_the_TWIN_shape(self, tmp_path):
        pkg = _pkg(tmp_path, "p_twin",
                   {"a.py": "class J:\n    def run(self):\n        return 1\n",
                    "b.py": "class J:\n    def run(self):\n        return 2\n"})
        assert audit(pkg)["duplicates"]["J"]["shape"] == "differing-bodies"

    def test_a_name_defined_ONCE_is_not_a_duplicate(self, tmp_path):
        pkg = _pkg(tmp_path, "p_single", {"a.py": "class Solo:\n    pass\n"})
        assert audit(pkg)["duplicates"] == {}


class TestTheSubjectMeasurement:
    def test_coverage_is_all_over_public_defs(self, tmp_path):
        pkg = _pkg(tmp_path, "p_cov",
                   {"a.py": "class A:\n    pass\n\n\nclass B:\n    pass\n"},
                   all_names=["A"])
        r = audit(pkg)
        assert r["all_size"] == 1 and r["public_module_level_defs"] == 2
        assert "public defs ..... 2" in render(r)

    def test_an_UNEXPORTED_duplicate_is_reported_as_INVISIBLE(self, tmp_path):
        """The load-bearing distinction: a duplicate outside `__all__` is exactly
        what an `__all__`-scoped guard cannot see."""
        pkg = _pkg(tmp_path, "p_vis",
                   {"a.py": "class Hidden:\n    x = 1\n",
                    "b.py": "class Hidden:\n    x = 2\n"})
        r = audit(pkg)
        assert r["duplicates_not_exported"] == ["Hidden"]
        assert r["duplicates_that_are_exported"] == []
        assert "not exported ............. 1" in render(r)

    def test_an_EXPORTED_duplicate_is_reported_as_VISIBLE(self, tmp_path):
        pkg = _pkg(tmp_path, "p_vis2",
                   {"a.py": "class Shown:\n    x = 1\n",
                    "b.py": "class Shown:\n    x = 2\n"},
                   all_names=["Shown"])
        r = audit(pkg)
        assert r["duplicates_that_are_exported"] == ["Shown"]

    def test_private_and_nested_definitions_are_NOT_counted(self, tmp_path):
        """Module level only, public only — otherwise the denominator inflates
        and the coverage number stops meaning anything."""
        pkg = _pkg(tmp_path, "p_scope",
                   {"a.py": "def _priv():\n    pass\n\n\n"
                            "def outer():\n    def inner():\n        pass\n    return inner\n"})
        r = audit(pkg)
        assert r["public_module_level_defs"] == 1        # outer only
        assert r["duplicates"] == {}


class TestItRefusesToOverclaim:
    def test_the_render_says_a_duplicate_is_a_CANDIDATE_not_a_verdict(self, tmp_path):
        pkg = _pkg(tmp_path, "p_claim",
                   {"a.py": "class J:\n    x = 1\n", "b.py": "class J:\n    x = 2\n"})
        text = render(audit(pkg))
        assert "CANDIDATE, not a verdict" in text
        assert "work list, not the audit" in text

    def test_an_unparseable_file_is_skipped_not_counted_as_clean(self, tmp_path):
        """It must not raise, and it must not silently inflate 'no duplicates'."""
        pkg = _pkg(tmp_path, "p_bad",
                   {"a.py": "class J:\n    x = 1\n", "b.py": "class J:\n    x = 2\n",
                    "broken.py": "def (:\n"})
        assert audit(pkg)["duplicates"]["J"]["shape"] == "differing-bodies"


def test_the_LIVE_orchestrator_measurement_behind_the_GOAL3_claim():
    """Bound to reality: if this repo's surface changes, the recorded claim has
    to be re-derived rather than inherited."""
    r = audit("renquant_orchestrator")
    assert r["all_size"] <= 10, r["all_size"]
    assert r["public_module_level_defs"] > 500, r["public_module_level_defs"]
    assert r["n_duplicate_names"] >= 30, r["n_duplicate_names"]
    assert r["duplicates_that_are_exported"] == [], (
        "an __all__-scoped guard would now see something here — re-derive the "
        "GOAL-3 record", r["duplicates_that_are_exported"])


def test_the_POSITIVE_CONTROL_is_in_the_SUITE_not_only_in_the_prose():
    """[codex on orch#814] I described a positive control in the doc and never
    wrote it as a test, so a regression to the old dynamic-`__all__` failure
    mode — which reported ZERO duplicates everywhere, including pipeline —
    would still have passed.

    renquant-pipeline is KNOWN to have ~20 exported duplicate names. A method
    that finds none there is broken, whatever it reports about other repos.
    """
    r = audit("renquant_pipeline")
    assert r["all_size"] >= 40, ("pipeline's __all__ read as nearly empty — the "
                                 "dynamic-__all__ failure mode is back", r["all_size"])
    assert len(r["duplicates_that_are_exported"]) >= 15, (
        "pipeline's exported duplicates vanished — the census method is broken, "
        "so no 'clean' census for any other repo can be trusted",
        r["duplicates_that_are_exported"])
    assert r["has_kernel_counterpart_root"] is True
    for known in ("PanelScoringJob", "ApplyScoresTask", "LoadScorerTask"):
        assert known in r["duplicates"], known
        assert r["duplicates"][known]["shape"] == "differing-bodies", known


def test_a_repo_reporting_clean_is_only_meaningful_WITH_the_control():
    """The two halves are one claim: 'orchestrator has no exported duplicates'
    means something only because the same call finds pipeline's."""
    control = audit("renquant_pipeline")
    subject = audit("renquant_orchestrator")
    assert control["duplicates_that_are_exported"], "control found nothing"
    assert subject["duplicates_that_are_exported"] == []


def test_the_census_does_NOT_claim_to_be_the_pipeline_guards_relation():
    """[codex on orch#814] The pipeline guard resolves each export and looks for
    a same-named def under one CONFIGURED counterpart root (`kernel/`). This
    census is an all-files same-name scan — broader, and NOT a stand-in. An
    earlier version compared the two and reported a 'guard subject coverage'
    percentage that measured the documented API against unrelated internal
    names. It is gone, and this test keeps it gone."""
    import scripts.goal3_twin_surface_audit as M

    src = Path(M.__file__).read_text(encoding="utf-8")
    assert "guard_subject_coverage" not in src
    assert "visible_to_an_all_scoped_guard" not in src
    assert "NOT a stand-in" in src or "must not be compared" in src
    assert "must not be compared" in render(audit("renquant_orchestrator"))


def test_an_ABSENT_kernel_root_reads_as_UNDEFINED_not_as_clean():
    """The one contract-faithful fact about the guard, and it needs no new
    machinery: outside pipeline there is no `kernel/` root, so the guard's
    relation does not even parse there."""
    r = audit("renquant_orchestrator")
    assert r["has_kernel_counterpart_root"] is False
    text = render(r)
    assert "UNDEFINED here, not 'clean'" in text
