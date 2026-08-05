"""`RENQUANT_REPO_ROOT` is resolved through symlinks — sandboxing can redirect.

MEASURED 2026-08-05 `[VERIFIED]`: a stray `/tmp/RenQuant ->
/Users/renhao/git/github/RenQuant` symlink (created 11:56 that day, by no code
in this repo) made an isolated test root silently BECOME the live umbrella, and
`tests/test_scheduled_jobs.py` went red for a reason that had nothing to do with
what it asserts.

The test artefact is fixed there. THIS file pins the underlying behaviour,
because its consequence is not confined to tests: `default_repo_root()` calls
`.resolve()`, so an operator who sandboxes a job with
`RENQUANT_REPO_ROOT=/tmp/RenQuant` — a natural thing to do — is operating on the
**live tree**, and nothing says so.

Production is unaffected TODAY and that was checked, not assumed: 8+ wrappers
export `RENQUANT_REPO_ROOT`, every one of them to the real umbrella path, and
`/Users/renhao/git/github/RenQuant` is not itself a symlink
`[VERIFIED — 2026-08-05]`. So this is a latent hazard with a live blast radius,
recorded as behaviour rather than changed underneath a resolver eight scheduled
jobs depend on.
"""
from __future__ import annotations

from pathlib import Path
import sys

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
from renquant_orchestrator.runtime_paths import default_repo_root  # noqa: E402


def test_a_SYMLINKED_repo_root_resolves_to_its_TARGET(monkeypatch, tmp_path):
    """The hazard, stated as behaviour: what you configure is not what you get."""
    target = tmp_path / "real_umbrella"
    target.mkdir()
    link = tmp_path / "sandbox"
    link.symlink_to(target)

    monkeypatch.setenv("RENQUANT_REPO_ROOT", str(link))
    got = default_repo_root()

    assert got == target.resolve(), (
        "if this ever stops holding, the sandbox-redirect hazard is gone and "
        "this file should be re-derived rather than deleted")
    assert got != link, (
        "THE HAZARD: a job pointed at the sandbox path operates on the target. "
        "An operator sandboxing with RENQUANT_REPO_ROOT=/tmp/RenQuant when that "
        "is a symlink to the live umbrella writes to the LIVE tree.")


def test_a_PLAIN_repo_root_is_returned_unchanged(monkeypatch, tmp_path):
    """Anti-over-claim: resolution is only surprising through a symlink."""
    plain = tmp_path / "plain"
    plain.mkdir()
    monkeypatch.setenv("RENQUANT_REPO_ROOT", str(plain))
    assert default_repo_root() == plain.resolve()


def test_a_NON_EXISTENT_root_is_still_returned(monkeypatch, tmp_path):
    """Tests point at roots that do not exist; that must stay usable, which is
    exactly why `.resolve()` cannot simply be dropped."""
    missing = tmp_path / "nope" / "RenQuant"
    monkeypatch.setenv("RENQUANT_REPO_ROOT", str(missing))
    assert default_repo_root() == missing


def test_no_test_in_this_repo_still_hardcodes_the_symlinkable_literal():
    """`/private/tmp/RenQuant` is outside pytest's tmp tree, so anyone can
    create it — and one did. A fixture root a stranger can redirect is not a
    fixture root."""
    offenders = []
    for path in sorted((REPO / "tests").glob("test_*.py")):
        if path.name == Path(__file__).name:
            continue                    # this file NAMES the literal to ban it
        text = path.read_text(encoding="utf-8", errors="replace")
        for i, line in enumerate(text.splitlines(), 1):
            if "/private/tmp/RenQuant" in line and "monkeypatch.setenv" in line:
                offenders.append(f"{path.name}:{i}")
    assert not offenders, (
        "these tests set RENQUANT_REPO_ROOT to a path outside pytest's tmp "
        f"tree, so a stray symlink can redirect them onto the live umbrella: "
        f"{offenders}")
