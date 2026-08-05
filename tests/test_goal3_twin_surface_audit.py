"""GOAL-3: a duplicate-definition census, and the guard's missing counterpart root.

renquant-pipeline's twin guard resolves each `__all__` export and looks for a
same-named definition under one CONFIGURED counterpart root, `kernel/`. This
module does NOT compute that relation: it is an all-files, same-name census, and
its counts must never be compared with the guard's.

The one contract-faithful fact about the guard needs no new machinery and is
measured by `--kernel-root-map`: `renquant_pipeline` is the only package with a
`kernel/` root, so everywhere else the guard's relation is UNDEFINED — not
"passes", not "clean".

`[codex on orch#814]` An earlier version of this docstring said `__all__` covers
"3 of 949 module-level public definitions" and that a guard there "would report
clean forever". Both are withdrawn: 949 is the count of UNIQUE public definition
NAMES, and the ratio compared the documented API against unrelated internal
names — a comparison this file otherwise exists to stop making.
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
        assert r["all_size"] == 1 and r["unique_public_def_names"] == 2
        assert "def NAMES ...... 2" in render(r)

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
        assert r["unique_public_def_names"] == 1        # outer only
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
    assert r["unique_public_def_names"] > 500, r["unique_public_def_names"]
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


# ── [codex on orch#814] the seven-repo claim must be MEASURED, not asserted ──

def test_the_kernel_root_map_covers_every_package_the_record_lists():
    from scripts.goal3_twin_surface_audit import SURVEYED_PACKAGES, kernel_root_map

    doc = " ".join((Path(__file__).resolve().parent.parent / "doc" / "progress"
                    / "2026-08-05-goal3-twin-guard-subject-audit.md")
                   .read_text().split())
    for pkg in SURVEYED_PACKAGES:
        repo = pkg.replace("_", "-").replace("renquant-strategy-104",
                                             "renquant-strategy-104")
        assert repo in doc, ("the record's table names a repo the survey does "
                             "not cover, or vice versa", repo)
    got = kernel_root_map()
    assert set(got) == set(SURVEYED_PACKAGES)


def test_an_UNIMPORTABLE_package_reads_as_NOT_MEASURED_not_as_absent():
    """`None`, never `False`: an unimportable package is not evidence of an
    absent root — that would turn a missing measurement into a finding."""
    from scripts.goal3_twin_surface_audit import kernel_root_map

    got = kernel_root_map(("definitely_not_a_real_package_xyz",))
    assert got["definitely_not_a_real_package_xyz"] is None


def test_the_EXACT_kernel_root_map_the_record_states():
    """[codex on orch#814] The record says none of the seven was unmeasured and
    every non-pipeline package is False. The earlier test filtered `None` away
    and accepted any three imports, so the table was stronger than its evidence.

    This asserts the EXACT map where the environment can produce it. Off-machine
    (CI has no sibling checkouts) it skips loudly, naming what could not be
    measured — a skip that says which packages are missing is not the same as a
    pass computed over whichever happened to import.
    """
    from scripts.goal3_twin_surface_audit import SURVEYED_PACKAGES, kernel_root_map

    got = kernel_root_map()
    unmeasured = sorted(k for k, v in got.items() if v is None)
    if unmeasured:
        pytest.skip("cannot verify the record's map here — unmeasured: "
                    + ", ".join(unmeasured))
    expected = {p: (p == "renquant_pipeline") for p in SURVEYED_PACKAGES}
    assert got == expected, (
        "the live kernel-root map no longer matches the record — re-derive the "
        "GOAL-3 table rather than inheriting it", got)


# ── GOAL-3: which duplicates can a caller actually CONFUSE? ──────────────────
#
# The 42 duplicate names are a work list, not findings. Measured 2026-08-05:
# 29 are never imported by name at all — module-local Tasks/Jobs instantiated
# in their own module — 8 come from exactly one source, and only 5 are imported
# from MORE THAN ONE module, which is the only shape where a reader could expect
# one implementation and get another.

class TestReachability:
    def test_a_name_with_no_import_site_is_classified_as_such(self, tmp_path):
        pkg = _pkg(tmp_path, "p_reach1",
                   {"a.py": "class J:\n    x = 1\n", "b.py": "class J:\n    x = 2\n"})
        d = audit(pkg)["duplicates"]["J"]
        assert d["reachability"] == "no-import-site-found"
        assert d["imported_from"] == []

    def test_one_importing_module_is_one_source(self, tmp_path):
        pkg = _pkg(tmp_path, "p_reach2",
                   {"a.py": "class J:\n    x = 1\n", "b.py": "class J:\n    x = 2\n",
                    "c.py": "from p_reach2.a import J\n"})
        d = audit(pkg)["duplicates"]["J"]
        assert d["reachability"] == "one-source"
        assert d["imported_from"] == ["p_reach2.a"]
        assert d["sites_reached"] == ["a.py"]

    def test_two_source_modules_is_MULTI_SOURCE(self, tmp_path):
        """The only shape where a reader could expect one and get the other."""
        pkg = _pkg(tmp_path, "p_reach3",
                   {"a.py": "class J:\n    x = 1\n", "b.py": "class J:\n    x = 2\n",
                    "c.py": "from p_reach3.a import J\n",
                    "d.py": "from p_reach3.b import J\n"})
        d = audit(pkg)["duplicates"]["J"]
        assert d["reachability"] == "MULTI-SOURCE"
        assert d["sites_reached"] == ["a.py", "b.py"]

    def test_the_counts_reconcile_with_the_duplicate_total(self, tmp_path):
        pkg = _pkg(tmp_path, "p_reach4",
                   {"a.py": "class J:\n    x = 1\n\n\nclass K:\n    y = 1\n",
                    "b.py": "class J:\n    x = 2\n\n\nclass K:\n    y = 2\n",
                    "c.py": "from p_reach4.a import J\n"})
        r = audit(pkg)
        assert sum(r["reachability_counts"].values()) == r["n_duplicate_names"]

    def test_the_render_REFUSES_to_call_no_import_site_unreachable(self, tmp_path):
        """[codex on orch#821] The first version said "module-local; cannot be
        confused". Tests import several of those names, so that was false."""
        pkg = _pkg(tmp_path, "p_reach5",
                   {"a.py": "class J:\n    x = 1\n", "b.py": "class J:\n    x = 2\n"})
        text = render(audit(pkg))
        assert "NOT proof of unreachability" in text
        assert "cannot be confused" not in text
        assert "a reader could expect one and get the other" in text


class TestAnImportIsCreditedOnlyToTHISNamesOwnSites:
    """[codex on orch#821, round 2] Counting `from MODULE import NAME` by NAME
    alone lets an unrelated module make a duplicate look reachable — and two of
    them make it look MULTI-SOURCE. Measured on the live packages, four such
    credits existed: `arch.bootstrap` (a third-party library) for
    `optimal_block_length`, `renquant_common.metrics.{deflated_sharpe,
    perf_summary}` (a DIFFERENT repo) for two more, and a script module for
    `analyze` `[VERIFIED — this session]`."""

    def test_an_UNRELATED_module_exporting_the_same_name_is_NOT_credited(
            self, tmp_path):
        pkg = _pkg(tmp_path, "p_ident1",
                   {"a.py": "class J:\n    x = 1\n", "b.py": "class J:\n    x = 2\n",
                    "c.py": "from third_party import J\n",
                    "d.py": "from another_vendor import J\n"})
        d = audit(pkg)["duplicates"]["J"]
        assert d["reachability"] == "no-import-site-found", d
        assert d["sites_reached"] == []
        assert d["foreign_import_sources"] == ["another_vendor", "third_party"]

    def test_a_foreign_credit_is_RECORDED_not_dropped(self, tmp_path):
        """It is not evidence about this name, but it is evidence — a same-named
        export elsewhere is exactly what makes the census ambiguous to read."""
        pkg = _pkg(tmp_path, "p_ident2",
                   {"a.py": "class J:\n    x = 1\n", "b.py": "class J:\n    x = 2\n",
                    "c.py": "from p_ident2.a import J\nfrom arch.bootstrap import J\n"})
        d = audit(pkg)["duplicates"]["J"]
        assert d["reachability"] == "one-source", d
        assert d["foreign_import_sources"] == ["arch.bootstrap"]

    def test_two_ALIASES_of_ONE_definition_are_not_MULTI_SOURCE(self, tmp_path):
        """Reachability counts SITES reached, not import strings. A package that
        re-exports its own definition has not created a second definition."""
        pkg = _pkg(tmp_path, "p_ident3",
                   {"a.py": "class J:\n    x = 1\n", "b.py": "class J:\n    x = 2\n",
                    "shim.py": "from p_ident3.a import J\n",
                    "c.py": "from p_ident3.a import J\n",
                    "d.py": "from p_ident3.shim import J\n"})
        d = audit(pkg)["duplicates"]["J"]
        assert d["sites_reached"] == ["a.py"], d
        assert d["reachability"] == "one-source", d

    def test_a_RELATIVE_import_is_normalised_before_it_is_matched(self, tmp_path):
        pkg = _pkg(tmp_path, "p_ident4",
                   {"a.py": "class J:\n    x = 1\n", "b.py": "class J:\n    x = 2\n",
                    "c.py": "from .b import J\n"})
        d = audit(pkg)["duplicates"]["J"]
        assert d["sites_reached"] == ["b.py"], d

    def test_a_relative_import_in_an___init___stays_INSIDE_its_package(
            self, tmp_path):
        """REGRESSION: `from .x import y` in `pkg/sub/__init__.py` is relative to
        `pkg.sub`, not to `pkg`. Resolving it one level too high sent every such
        importer to `foreign_import_sources` — it is how
        `renquant_backtesting.metrics.deflated_sharpe` was read as the
        non-existent `renquant_backtesting.deflated_sharpe`."""
        pkg = _pkg(tmp_path, "p_ident5",
                   {"a.py": "class J:\n    x = 1\n", "b.py": "class J:\n    x = 2\n"})
        sub = tmp_path / pkg / "sub"
        sub.mkdir()
        (sub / "__init__.py").write_text("from .inner import J\n", encoding="utf-8")
        (sub / "inner.py").write_text("class J:\n    x = 3\n", encoding="utf-8")
        d = audit(pkg)["duplicates"]["J"]
        assert d["sites_reached"] == ["sub/inner.py"], d
        assert d["foreign_import_sources"] == [], d

    def test_a_relative_import_from_OUTSIDE_the_package_is_not_guessed(
            self, tmp_path):
        """A test or script has no package to be relative to. Unresolvable is
        recorded as unresolvable, never matched on the bare name."""
        from scripts.goal3_twin_surface_audit import _importer_package

        assert _importer_package(tmp_path / "tests" / "t.py", tmp_path / "src") is None


def test_the_LIVE_reachability_breakdown_is_PINNED_exactly():
    """[codex on orch#821] The first version asserted only `>=30`, `never>multi`
    and `main in multi` — it would have kept passing through the very drift that
    tripled the multi-source count. Pin the numbers the record states."""
    r = audit("renquant_orchestrator")
    assert r["reachability_counts"] == {
        "no-import-site-found": 17, "one-source": 11, "MULTI-SOURCE": 14}, (
        "the reachability breakdown moved — re-derive the GOAL-3 work list "
        "rather than inheriting it", r["reachability_counts"])
    multi = sorted(k for k, v in r["duplicates"].items()
                   if v["reachability"] == "MULTI-SOURCE")
    assert multi == [
        "AdmittedName", "IllegalTransition", "append_records",
        "collect", "connect", "default_pilot_path", "default_shadow_log_path",
        "default_tick_feed_path", "emit_alert", "evaluate_session", "main",
        "render_markdown", "session_date", "summarize"], multi
    # `build_report` LEFT this list under source identity: its two "sources"
    # were `renquant_orchestrator.attribution` and
    # `renquant_orchestrator.attribution.report` — the package re-exporting its
    # own single definition. Two aliases of one definition are not a fork
    # [VERIFIED — this session].
    assert r["duplicates"]["build_report"]["sites_reached"] == [
        "attribution/report.py"]


def test_the_scan_covers_TESTS_not_only_the_package():
    """The counterexample that broke the first version: tests/ imports several
    names the package never does."""
    from scripts.goal3_twin_surface_audit import SCAN_ROOTS

    assert "tests" in SCAN_ROOTS and "src" in SCAN_ROOTS
    r = audit("renquant_orchestrator")
    admitted = r["duplicates"]["AdmittedName"]
    assert admitted["reachability"] == "MULTI-SOURCE", admitted
    assert admitted["imported_from"], "AdmittedName is imported by tests/"


def test_a_package_with_no_sibling_scan_roots_scans_ITSELF_not_nothing(tmp_path):
    """Scanning nothing would report every name as having no import site — the
    vacuous pass this file exists to avoid."""
    from scripts.goal3_twin_surface_audit import _scan_paths

    pkg = tmp_path / "lonely"
    pkg.mkdir()
    (pkg / "a.py").write_text("x = 1\n", encoding="utf-8")
    got = _scan_paths(tmp_path / "no-such-repo", pkg)
    assert [p.name for p in got] == ["a.py"]
