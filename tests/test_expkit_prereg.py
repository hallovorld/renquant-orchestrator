"""expkit.prereg — freeze-first specs + the git-history-aware check."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from renquant_orchestrator.expkit.prereg import (
    Criterion,
    FrozenSpec,
    SpecNotFrozenError,
    assert_spec_frozen_before_results,
    check_spec_frozen_before_results,
    load_frozen_spec,
    write_frozen_spec,
)

BOUNDARY = {
    "window": "2020-01-01 -> 2025-01-01; 1000 dates",
    "cells": "one cell",
    "outcome_era": "current",
    "cost_model": "none",
    "substrate": "synthetic",
    "multiplicity": "k=3",
    "not_covered": "everything else",
}


def make_spec(**overrides) -> FrozenSpec:
    kwargs = dict(
        experiment_id="toy",
        hypothesis="toy signal predicts toy label",
        criteria=(Criterion(name="bar", threshold=0.015),),
        family_size_k=3,
        seeds=(42, 43, 44),
        evidence_boundary=BOUNDARY,
        reopening_conditions=("new PIT substrate lands",),
    )
    kwargs.update(overrides)
    return FrozenSpec(**kwargs)


# ---------------------------------------------------------------------------
# Criterion
# ---------------------------------------------------------------------------
def test_criterion_directions():
    assert Criterion("c", 1.0, "gt").met(1.1) and not Criterion("c", 1.0, "gt").met(1.0)
    assert Criterion("c", 1.0, "lt").met(0.9) and not Criterion("c", 1.0, "lt").met(1.0)
    assert Criterion("c", 1.0, "ge").met(1.0)
    assert Criterion("c", 1.0, "le").met(1.0)
    with pytest.raises(ValueError):
        Criterion("c", 1.0, "eq").met(1.0)


# ---------------------------------------------------------------------------
# FrozenSpec validation + hashing
# ---------------------------------------------------------------------------
def test_spec_requires_r3_boundary_fields():
    incomplete = {k: v for k, v in BOUNDARY.items() if k != "cost_model"}
    with pytest.raises(ValueError, match="cost_model"):
        make_spec(evidence_boundary=incomplete)


def test_spec_requires_r4_reopening_conditions():
    with pytest.raises(ValueError, match="[Rr]eopening"):
        make_spec(reopening_conditions=())


def test_spec_requires_criteria_seeds_and_valid_family():
    with pytest.raises(ValueError):
        make_spec(criteria=())
    with pytest.raises(ValueError):
        make_spec(seeds=())
    with pytest.raises(ValueError):
        make_spec(family_size_k=0)


def test_alpha_one_sided_is_bonferroni():
    assert make_spec(family_size_k=3).alpha_one_sided == pytest.approx(0.05 / 3)
    assert make_spec(family_size_k=12).alpha_one_sided == pytest.approx(0.05 / 12)


def test_spec_sha_deterministic_and_content_sensitive():
    a, b = make_spec(), make_spec()
    assert a.sha256() == b.sha256()
    c = make_spec(criteria=(Criterion(name="bar", threshold=0.016),))
    assert c.sha256() != a.sha256()  # a moved threshold is a different spec


def test_criterion_lookup():
    spec = make_spec()
    assert spec.criterion("bar").threshold == 0.015
    with pytest.raises(KeyError):
        spec.criterion("nope")


def test_write_load_round_trip(tmp_path: Path):
    spec = make_spec()
    file_sha = write_frozen_spec(spec, tmp_path / "spec.json")
    assert len(file_sha) == 64
    loaded = load_frozen_spec(tmp_path / "spec.json")
    assert loaded == spec
    assert loaded.sha256() == spec.sha256()


# ---------------------------------------------------------------------------
# Git-history freeze-first check (temp repos, never a primary checkout)
# ---------------------------------------------------------------------------
def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args],
        check=True,
        capture_output=True,
    )


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    return tmp_path


def _commit(repo: Path, name: str, content: str = "x") -> Path:
    p = repo / name
    p.write_text(content)
    _git(repo, "add", name)
    _git(repo, "commit", "-q", "-m", f"add {name}")
    return p


def test_freeze_ok_spec_before_results(repo: Path):
    spec = _commit(repo, "spec.json", '{"frozen": true}')
    results = _commit(repo, "results.json", '{"ic": 0.01}')
    check = check_spec_frozen_before_results(repo, spec, [results])
    assert check.ok
    assert "ok" in check.results["results.json"]["status"]


def test_freeze_violated_results_before_spec(repo: Path):
    results = _commit(repo, "results.json", '{"ic": 0.01}')
    spec = _commit(repo, "spec.json", '{"frozen": true}')
    check = check_spec_frozen_before_results(repo, spec, [results])
    assert not check.ok
    with pytest.raises(SpecNotFrozenError, match="before the spec"):
        assert_spec_frozen_before_results(repo, spec, [results])


def test_freeze_violated_same_commit(repo: Path):
    spec = repo / "spec.json"
    spec.write_text('{"frozen": true}')
    results = repo / "results.json"
    results.write_text('{"ic": 0.01}')
    _git(repo, "add", "spec.json", "results.json")
    _git(repo, "commit", "-q", "-m", "spec and results together")
    check = check_spec_frozen_before_results(repo, spec, [results])
    assert not check.ok
    assert any("SAME commit" in p for p in check.problems)


def test_freeze_violated_uncommitted_spec(repo: Path):
    _commit(repo, "seed.txt")  # repo needs one commit for git log to work
    spec = repo / "spec.json"
    spec.write_text('{"frozen": true}')  # never committed
    check = check_spec_frozen_before_results(repo, spec, [])
    assert not check.ok
    assert any("freezes nothing" in p for p in check.problems)


def test_freeze_uncommitted_results_are_fine(repo: Path):
    spec = _commit(repo, "spec.json", '{"frozen": true}')
    results = repo / "results.json"
    results.write_text('{"ic": 0.01}')  # working tree only
    check = check_spec_frozen_before_results(repo, spec, [results])
    assert check.ok


def test_freeze_retro_edit_detected(repo: Path):
    spec = _commit(repo, "spec.json", '{"frozen": true}')
    from renquant_orchestrator.expkit.evidence import sha256_file

    frozen_sha = sha256_file(spec)
    spec.write_text('{"frozen": true, "threshold": "moved"}')
    check = check_spec_frozen_before_results(
        repo, spec, [], expected_spec_sha256=frozen_sha
    )
    assert not check.ok
    assert any("retro-editing" in p for p in check.problems)
