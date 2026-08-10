"""Controls for the data-completeness registry's watchlist pin validation.

PR #963 review (codex, MED): the derivation reads the MUTABLE
``.subrepo_runtime`` strategy_config.json; without validating it against
``subrepos.lock.json`` the script could silently classify a different
watchlist than the pin the research note reports.  These tests hold the fix
to its contract: a mismatched checkout must fail LOUDLY, naming both
identifiers, before any data is read — and a matching one must pass (the
positive control, so the guard is proven to examine the real object rather
than reject everything).
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from scripts.data_completeness_registry import (  # noqa: E402
    PinMismatchError, STRATEGY_CONFIG_RELPATH, load_pinned_watchlist_config)

SCRIPT = REPO / "scripts" / "data_completeness_registry.py"


def _git(cwd: Path, *args: str) -> str:
    res = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t",
         "-c", "commit.gpgsign=false", "-C", str(cwd), *args],
        capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    return res.stdout.strip()


@pytest.fixture()
def pinned_checkout(tmp_path):
    """A real git checkout whose HEAD commit contains a strategy config,
    plus a lock file pinning exactly that HEAD."""
    checkout = tmp_path / "renquant-strategy-104"
    cfg = checkout / STRATEGY_CONFIG_RELPATH
    cfg.parent.mkdir(parents=True)
    cfg.write_text(json.dumps({"watchlist": ["AAPL", "SPY"]}))
    _git(checkout, "init", "-q")
    _git(checkout, "add", "-A")
    _git(checkout, "commit", "-q", "-m", "pin fixture")
    head = _git(checkout, "rev-parse", "HEAD")
    lock = tmp_path / "subrepos.lock.json"
    lock.write_text(json.dumps({"subrepos": [
        {"name": "renquant-strategy-104", "commit": head}]}))
    return checkout, lock, head


def test_positive_control_matching_pin_returns_config_and_provenance(
        pinned_checkout):
    checkout, lock, head = pinned_checkout
    cfg, prov = load_pinned_watchlist_config(lock, checkout)
    assert cfg["watchlist"] == ["AAPL", "SPY"]
    assert prov["lock_pin"] == head
    assert prov["checkout_head"] == head
    expected = hashlib.sha256(
        (checkout / STRATEGY_CONFIG_RELPATH).read_bytes()).hexdigest()
    assert prov["config_sha256"] == expected


def test_mismatched_pin_fails_naming_BOTH_shas(pinned_checkout):
    checkout, lock, head = pinned_checkout
    wrong = "0" * 40
    lock.write_text(json.dumps({"subrepos": [
        {"name": "renquant-strategy-104", "commit": wrong}]}))
    with pytest.raises(PinMismatchError) as exc:
        load_pinned_watchlist_config(lock, checkout)
    msg = str(exc.value)
    assert head in msg and wrong in msg


def test_dirty_config_fails_naming_both_digests(pinned_checkout):
    """HEAD equals the pin but the FILE was edited after the commit — the
    exact 'mutable working tree' hazard the review named."""
    checkout, lock, head = pinned_checkout
    cfg = checkout / STRATEGY_CONFIG_RELPATH
    committed_sha = hashlib.sha256(cfg.read_bytes()).hexdigest()
    cfg.write_text(json.dumps({"watchlist": ["EVIL"]}))
    dirty_sha = hashlib.sha256(cfg.read_bytes()).hexdigest()
    with pytest.raises(PinMismatchError) as exc:
        load_pinned_watchlist_config(lock, checkout)
    msg = str(exc.value)
    assert committed_sha in msg and dirty_sha in msg


def test_cli_control_mismatched_checkout_exits_nonzero_naming_both_shas(
        pinned_checkout, tmp_path):
    """The review's requested control, end-to-end: point the SCRIPT at a
    mismatched fixture → nonzero exit naming both shas.  The umbrella fixture
    contains no data files, proving validation runs before any data read."""
    checkout, lock, head = pinned_checkout
    wrong = "f" * 40
    umbrella = tmp_path / "umbrella"
    runtime = umbrella / ".subrepo_runtime" / "repos"
    runtime.mkdir(parents=True)
    (umbrella / "subrepos.lock.json").write_text(json.dumps({"subrepos": [
        {"name": "renquant-strategy-104", "commit": wrong}]}))
    res = subprocess.run(
        [sys.executable, str(SCRIPT), "--umbrella", str(umbrella),
         "--strategy-checkout", str(checkout),
         "--out", str(tmp_path / "reg.csv")],
        capture_output=True, text=True)
    assert res.returncode != 0
    assert head in res.stderr and wrong in res.stderr
    assert not (tmp_path / "reg.csv").exists()
