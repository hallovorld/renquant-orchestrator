"""Pre-registration: the freeze-first mechanism, mechanized.

The three-commit pattern (M8 `m8_frozen_spec.json`, D3 `frozen_spec.json`,
C2/C4 frozen addenda): commit 1 = the frozen spec (hypothesis, thresholds,
family size, seeds, evidence boundary, reopening conditions); commit 2 = the
harness + controls; commit 3 = results + verdict. Nothing in the spec may be
altered after commit 1; deviations must be disclosed, and any undeclared
deviation voids the run.

Prior art enforced prospectivity by convention (RS-5's runner refuses to run
on a contract mismatch; D3 asserts load-time identity facts). This module
adds the missing mechanical check: a git-history-aware assert that the spec
file was committed BEFORE any results file.

Hash convention: the spec hash pins the exact bytes of the committed spec
file (`sha256_file`), the same convention D3/RS-5 stamp into their manifests
("hash pins the exact bytes verified"). `FrozenSpec.sha256()` additionally
provides a canonical-JSON hash for in-memory specs that have not been written
yet; once written via `write_frozen_spec`, the file-bytes hash governs.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from renquant_orchestrator.expkit.evidence import canonical_json, sha256_bytes, sha256_file

__all__ = [
    "Criterion",
    "FreezeCheck",
    "FrozenSpec",
    "SpecNotFrozenError",
    "assert_spec_frozen_before_results",
    "check_spec_frozen_before_results",
    "load_frozen_spec",
    "write_frozen_spec",
]

_EVIDENCE_BOUNDARY_FIELDS = (
    # S-REL R3: the mandatory evidence-boundary block, one line per field;
    # "n/a" must be argued, not assumed.
    "window",
    "cells",
    "outcome_era",
    "cost_model",
    "substrate",
    "multiplicity",
    "not_covered",
)


@dataclass(frozen=True)
class Criterion:
    """One frozen decision criterion (a threshold that may not move after the
    freeze). `direction` is the comparator applied to the measured statistic:
    'gt' means the criterion is met iff statistic > threshold."""

    name: str
    threshold: float
    direction: str = "gt"  # 'gt' | 'lt' | 'ge' | 'le'
    units: str = ""
    description: str = ""

    def met(self, value: float) -> bool:
        if self.direction == "gt":
            return value > self.threshold
        if self.direction == "lt":
            return value < self.threshold
        if self.direction == "ge":
            return value >= self.threshold
        if self.direction == "le":
            return value <= self.threshold
        raise ValueError(f"unknown direction {self.direction!r}")


@dataclass(frozen=True)
class FrozenSpec:
    """The pre-registered experiment spec. Every field here is FROZEN at
    commit 1 and may not be tuned after seeing a result.

    - `family_size_k`: the Bonferroni family (number of candidates/looks).
      One-sided alpha = 0.05 / k (D3 k=12 -> 99.5833%; RS-5 k=4 -> 98.75%;
      M-SIG k=3 -> 98.33%). Seeds are NOT Bonferroni-counted — their frozen
      role is "robustness check on one corrected result, not extra looks",
      enforced as multi-seed unanimity (#264 lesson).
    - `evidence_boundary`: the R3 block fields (window, cells, outcome_era,
      cost_model, substrate, multiplicity, not_covered).
    - `reopening_conditions`: R4 — the specific future facts that would
      justify reopening; reopening executes as a NEW frozen prereg.
    """

    experiment_id: str
    hypothesis: str
    criteria: tuple[Criterion, ...]
    family_size_k: int
    seeds: tuple[int, ...]
    evidence_boundary: Mapping[str, str]
    reopening_conditions: tuple[str, ...]
    horizon: int = 60
    block: int = 60
    n_boot: int = 2000
    base_alpha: float = 0.05
    min_decision_dates: int = 600
    min_names: int = 30
    extra_frozen: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.family_size_k < 1:
            raise ValueError("family_size_k must be >= 1")
        if not self.seeds:
            raise ValueError("at least one seed must be frozen")
        if not self.criteria:
            raise ValueError("at least one frozen criterion is required")
        if not self.reopening_conditions:
            raise ValueError(
                "R4: reopening conditions are mandatory for every verdict-"
                "producing experiment ('someone wants to retry' is not one)"
            )
        missing = [f for f in _EVIDENCE_BOUNDARY_FIELDS if f not in self.evidence_boundary]
        if missing:
            raise ValueError(
                f"R3 evidence-boundary fields missing: {missing} "
                "(state each, or argue 'n/a' explicitly)"
            )

    @property
    def alpha_one_sided(self) -> float:
        return self.base_alpha / self.family_size_k

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["alpha_one_sided"] = self.alpha_one_sided
        return d

    def canonical_json(self) -> str:
        return canonical_json(self.to_dict())

    def sha256(self) -> str:
        """Canonical-JSON hash of the in-memory spec. Once the spec is
        written to disk, `sha256_file` of the committed bytes governs."""
        return sha256_bytes(self.canonical_json().encode())

    def criterion(self, name: str) -> Criterion:
        for c in self.criteria:
            if c.name == name:
                return c
        raise KeyError(name)


def write_frozen_spec(spec: FrozenSpec, path: Path | str) -> str:
    """Write the spec JSON (commit 1 of the three-commit pattern). Returns
    the file-bytes sha256 to stamp into manifests."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = spec.to_dict()
    payload["canonical_sha256"] = spec.sha256()
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")
    return sha256_file(path)


def load_frozen_spec(path: Path | str) -> FrozenSpec:
    raw = json.loads(Path(path).read_text())
    raw.pop("canonical_sha256", None)
    raw.pop("alpha_one_sided", None)
    raw["criteria"] = tuple(Criterion(**c) for c in raw["criteria"])
    raw["seeds"] = tuple(raw["seeds"])
    raw["reopening_conditions"] = tuple(raw["reopening_conditions"])
    return FrozenSpec(**raw)


class SpecNotFrozenError(AssertionError):
    """The spec was not committed before results (or not committed at all)."""


@dataclass
class FreezeCheck:
    ok: bool
    spec_path: str
    spec_first_commit: str | None
    spec_sha256_now: str | None
    results: dict[str, dict[str, Any]] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)

    def raise_if_failed(self) -> None:
        if not self.ok:
            raise SpecNotFrozenError("; ".join(self.problems))


def _git(repo_root: Path | str, *args: str) -> str:
    out = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout


def _first_commit_adding(repo_root: Path | str, rel_path: str) -> str | None:
    """Earliest commit that ADDED the file (git log --diff-filter=A --follow;
    the last line of the log is the earliest add)."""
    try:
        out = _git(
            repo_root,
            "log",
            "--diff-filter=A",
            "--follow",
            "--format=%H",
            "--",
            rel_path,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    lines = [ln for ln in out.splitlines() if ln.strip()]
    return lines[-1] if lines else None


def _is_ancestor(repo_root: Path | str, ancestor: str, descendant: str) -> bool:
    try:
        subprocess.run(
            ["git", "-C", str(repo_root), "merge-base", "--is-ancestor", ancestor, descendant],
            capture_output=True,
            check=True,
        )
        return True
    except subprocess.CalledProcessError:
        return False


def check_spec_frozen_before_results(
    repo_root: Path | str,
    spec_path: Path | str,
    results_paths: Sequence[Path | str],
    *,
    expected_spec_sha256: str | None = None,
) -> FreezeCheck:
    """The git-history-aware freeze-first check.

    Passes iff:
    1. the spec file is COMMITTED (a spec that only exists in the working
       tree freezes nothing);
    2. for every results file that is committed, the spec's first-add commit
       is an ancestor of (or equal to) the results file's first-add commit —
       the three-commit ordering. Results still uncommitted in the working
       tree are fine: the spec is committed first by construction;
    3. if `expected_spec_sha256` is given, the spec's CURRENT bytes still
       hash to it (the frozen spec was not retro-edited after the freeze).
    """
    repo_root = Path(repo_root)
    spec_path = Path(spec_path)
    rel_spec = str(spec_path.resolve().relative_to(repo_root.resolve()))
    problems: list[str] = []

    spec_commit = _first_commit_adding(repo_root, rel_spec)
    if spec_commit is None:
        problems.append(
            f"spec {rel_spec} has no committed history — a working-tree spec freezes nothing"
        )

    sha_now = sha256_file(spec_path) if spec_path.exists() else None
    if expected_spec_sha256 is not None and sha_now != expected_spec_sha256:
        problems.append(
            f"spec {rel_spec} bytes drifted from the frozen hash "
            f"(expected {expected_spec_sha256}, now {sha_now}) — retro-editing voids the freeze"
        )

    results: dict[str, dict[str, Any]] = {}
    for rp in results_paths:
        rp = Path(rp)
        rel = str(rp.resolve().relative_to(repo_root.resolve()))
        r_commit = _first_commit_adding(repo_root, rel)
        entry: dict[str, Any] = {"first_commit": r_commit}
        if r_commit is None:
            entry["status"] = "uncommitted (ok: spec precedes it by construction)"
        elif spec_commit is None:
            entry["status"] = "committed but spec is not"
        elif r_commit == spec_commit:
            entry["status"] = "same commit as spec (freeze-first VIOLATED: spec must land first)"
            problems.append(
                f"results {rel} landed in the SAME commit as the spec — the three-commit "
                "pattern requires the spec committed strictly before results"
            )
        elif _is_ancestor(repo_root, spec_commit, r_commit):
            entry["status"] = "spec committed before results (ok)"
        else:
            entry["status"] = "results committed before spec (freeze-first VIOLATED)"
            problems.append(f"results {rel} were committed before the spec {rel_spec}")
        results[rel] = entry

    return FreezeCheck(
        ok=not problems,
        spec_path=rel_spec,
        spec_first_commit=spec_commit,
        spec_sha256_now=sha_now,
        results=results,
        problems=problems,
    )


def assert_spec_frozen_before_results(
    repo_root: Path | str,
    spec_path: Path | str,
    results_paths: Sequence[Path | str],
    *,
    expected_spec_sha256: str | None = None,
) -> FreezeCheck:
    check = check_spec_frozen_before_results(
        repo_root, spec_path, results_paths, expected_spec_sha256=expected_spec_sha256
    )
    check.raise_if_failed()
    return check
