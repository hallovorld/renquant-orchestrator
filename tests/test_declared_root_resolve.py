"""R9's remediation, extracted so it is reusable — and the distinctions it must keep.

Twin-registry R9: one artifact basename, 23 paths, 3 distinct digests, 22 of them under
`diagnostics/`. An `rglob` + `sorted(hits)[0]` silently measured a modal-sweep copy and
shifted a published median. Re-measured 2026-08-01: still 23 / 3 / 1-under-prod.

The rule was written once, inside `ops/regime_profile_census.py`, reachable only by that
tool. R9's subject is *which copy gets used*, so a rule against it that every new caller
must re-type is the same hazard one level up.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

OPS = pathlib.Path(__file__).resolve().parent.parent / "ops"
sys.path.insert(0, str(OPS))

from declared_root_resolve import (  # noqa: E402
    AMBIGUOUS,
    NOT_FOUND,
    RESOLVED,
    resolve_artifact,
)


def _w(p: pathlib.Path, body: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)


# ------------------------------------------------------------- the three outcomes --
def test_one_path_resolves(tmp_path):
    _w(tmp_path / "prod" / "a.json", "{}")
    r = resolve_artifact("a.json", str(tmp_path / "prod"))
    assert r["status"] == RESOLVED and r["n_digests"] == 1 and r["duplicate_paths"] == []


def test_many_paths_at_ONE_digest_still_resolves(tmp_path):
    """21 identical copies are one artifact wearing 21 names. Refusing there would block
    a legitimate resolution."""
    for i in range(4):
        _w(tmp_path / f"d{i}" / "a.json", "{}")
    r = resolve_artifact("a.json", str(tmp_path), recursive=True)
    assert r["status"] == RESOLVED
    assert r["n_paths"] == 4 and r["n_digests"] == 1
    assert len(r["duplicate_paths"]) == 3


def test_two_DISTINCT_digests_REFUSE(tmp_path):
    """Not 'prefer prod', not 'take the newest' — choosing is what produced R9."""
    _w(tmp_path / "prod" / "a.json", "{}")
    _w(tmp_path / "diagnostics" / "a.json", '{"x":1}')
    r = resolve_artifact("a.json", str(tmp_path), recursive=True)
    assert r["status"] == AMBIGUOUS
    assert r["n_paths"] == 2 and r["n_digests"] == 2
    assert "refusing to choose" in r["why"]
    assert "path" not in r          # it must not hand back a choice


def test_absent_is_NOT_FOUND_not_ambiguous(tmp_path):
    r = resolve_artifact("nope.json", str(tmp_path))
    assert r["status"] == NOT_FOUND


# ---------------------------------------------- the declared root IS the mechanism --
def test_a_NARROWER_root_resolves_what_the_wide_one_refuses(tmp_path):
    """The fix is the root, not the glob: the same tree is ambiguous from above and
    unambiguous from the declared directory."""
    _w(tmp_path / "prod" / "a.json", "{}")
    _w(tmp_path / "diagnostics" / "a.json", '{"x":1}')
    assert resolve_artifact("a.json", str(tmp_path), recursive=True)["status"] == AMBIGUOUS
    assert resolve_artifact("a.json", str(tmp_path / "prod"))["status"] == RESOLVED


def test_non_recursive_is_the_DEFAULT(tmp_path):
    """A caller who does not think about it gets the safe behaviour."""
    _w(tmp_path / "sub" / "a.json", "{}")
    assert resolve_artifact("a.json", str(tmp_path))["status"] == NOT_FOUND


def test_a_PATH_argument_is_reduced_to_its_basename(tmp_path):
    """Callers pass artifact names from manifests, which sometimes carry directories.
    Resolving those against the declared root is the point; honouring them would let a
    manifest re-point the search."""
    _w(tmp_path / "prod" / "a.json", "{}")
    r = resolve_artifact("/somewhere/else/a.json", str(tmp_path / "prod"))
    assert r["status"] == RESOLVED


def test_an_UNREADABLE_candidate_does_not_read_as_a_digest_difference(tmp_path, monkeypatch):
    """An IO error is not a content fact. Folding it into 'different digest' would make
    a permissions problem look like a twin."""
    _w(tmp_path / "a.json", "{}")
    real = pathlib.Path.open

    def boom(self, *a, **k):
        if self.name == "a.json":
            raise OSError("simulated")
        return real(self, *a, **k)

    monkeypatch.setattr(pathlib.Path, "open", boom, raising=False)
    import builtins
    ob = builtins.open

    def bopen(f, *a, **k):
        if str(f).endswith("a.json"):
            raise PermissionError("simulated")
        return ob(f, *a, **k)

    monkeypatch.setattr(builtins, "open", bopen)
    r = resolve_artifact("a.json", str(tmp_path))
    assert r["status"] == AMBIGUOUS and "unreadable" in r["why"]


# ------------------------------------------------------ the caller was rewired --
def test_the_census_IMPORTS_the_rule_rather_than_restating_it():
    """R9 is about a rule existing in one place. A second copy of the anti-duplication
    rule would be the joke writing itself."""
    src = (OPS / "regime_profile_census.py").read_text()
    assert "from declared_root_resolve import" in src
    assert "refusing to choose" not in src      # the message lives in the resolver now
