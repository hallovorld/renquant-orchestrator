"""Tests for the software-stop registry-file contract (LOCATION side only).

PR #481 round 3 (Codex CHANGES_REQUESTED, 2026-07-11): the pager wrapper's
``RENQUANT_STOPS_PAGER_DATA_ROOT`` still names the deprecated umbrella in
production; this module defines the neutral-runtime-root convention (an
exact mirror of ``deployment_manifest.deploy_state_root``), so "consume the
neutral contract" is concrete and testable BEFORE the actual writer
migration (out of scope for this repo) lands.

Round 5 correction (Codex CHANGES_REQUESTED, 2026-07-12T04:32:57Z): the
round-3 revision also invented a versioned "envelope" content schema
(``schema_version``/``kind``, ``classify_registry_file``) that this repo
does not own and that never matched what the real writer
(``renquant_pipeline.software_stops``) produces. That machinery — and its
tests — has been removed. Registry CONTENT validity is now delegated to
``renquant_execution.software_stops_liveness`` (backed by
``renquant_pipeline.software_stops``'s real schema); see
``scripts/install_stops_pager.sh`` for the fail-closed pre-install guard
that now calls it. This module keeps only the LOCATION convention (the
neutral runtime-state root) and the NEUTRAL-vs-LEGACY path classifier.
See ``doc/progress/2026-07-11-stops-liveness-pager-package.md`` for the
full round history.

Bootstrap step (2026-08-29): the registry SEEDER (``ensure_registry_seeded``
+ the ``seed`` CLI) and, after Codex CHANGES_REQUESTED on #1078
(2026-08-29T07:54:11Z), the READINESS classifier (``registry_readiness`` +
the ``readiness`` CLI): a seed is LOCATABLE and schema-VALID but explicitly
NOT READY; READY needs a real writer heartbeat at the canonical path within
budget. The "readiness" tests below drive the pipeline's own
``SoftwareStopRegistry`` for that heartbeat — never a hand-written stamp. Everything under
"registry seeder" below runs against ``tmp_path`` only — the neutral root
env var is pinned to a throwaway dir in every seeder test so nothing can
reach ``~/.renquant``. Tagging and schema are the pipeline's: tests that
need ``renquant_pipeline.software_stops`` (or the execution checker) skip
WITH the reason when the sibling checkout is not on the path, and the
import-failure test proves the seeder fails closed in exactly that case.
"""
from __future__ import annotations

import datetime
import json
import os
import plistlib
import subprocess
import sys
from pathlib import Path

import pytest

from renquant_orchestrator import software_stops_registry_contract as contract
from renquant_orchestrator.software_stops_registry_contract import (
    DEFAULT_REGISTRY_REL,
    DEFAULT_RUNTIME_STATE_ROOT,
    DEFAULT_SEED_MAX_STALENESS_MINUTES,
    NOT_READY_CORRUPT,
    NOT_READY_STALE,
    NOT_READY_UNINITIALIZED,
    NOT_READY_UNSEEDED,
    READINESS_EXIT,
    READY,
    SEED_EXIT_CORRUPT,
    SEED_EXIT_IMPORT,
    SEED_EXIT_OK,
    SEED_EXIT_USAGE,
    SoftwareStopRegistryCorruptOnDisk,
    classify_data_root,
    describe_data_root,
    ensure_registry_seeded,
    registry_readiness,
    runtime_state_root,
    seeded_registry_path,
    software_stops_registry_path,
    software_stops_registry_root,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PAGER_PLIST = _REPO_ROOT / "deploy" / "com.renquant.stops-liveness.plist"

# --- neutral runtime-state root (mirrors test_state_root_env_override) --------------


def test_runtime_state_root_default_is_sibling_of_deploy_root() -> None:
    assert runtime_state_root() == Path("~/.renquant/runtime").expanduser()


def test_runtime_state_root_env_override(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("RENQUANT_RUNTIME_STATE_ROOT", str(tmp_path / "root"))
    assert runtime_state_root() == tmp_path / "root"
    monkeypatch.delenv("RENQUANT_RUNTIME_STATE_ROOT")
    assert runtime_state_root() == Path("~/.renquant/runtime").expanduser()


def test_runtime_state_root_explicit_override_wins_over_env(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("RENQUANT_RUNTIME_STATE_ROOT", str(tmp_path / "env-root"))
    assert runtime_state_root(tmp_path / "explicit") == tmp_path / "explicit"


def test_software_stops_registry_path_layout(tmp_path: Path) -> None:
    root = software_stops_registry_root(tmp_path)
    assert root == tmp_path / "software-stops"
    assert software_stops_registry_path(tmp_path, broker="alpaca") == root / "alpaca.json"


# --- data-root classifier ------------------------------------------------------------


def test_classify_data_root_neutral_when_under_runtime_root(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    data_root = runtime_root / "software-stops"
    data_root.mkdir(parents=True)
    verdict = classify_data_root(data_root, runtime_root=runtime_root)
    assert verdict.neutral is True
    assert "NEUTRAL" in verdict.message


def test_classify_data_root_neutral_when_equal_to_runtime_root(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    verdict = classify_data_root(runtime_root, runtime_root=runtime_root)
    assert verdict.neutral is True


def test_classify_data_root_legacy_for_umbrella_path(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    umbrella_like = tmp_path / "RenQuant"
    umbrella_like.mkdir()
    verdict = classify_data_root(umbrella_like, runtime_root=runtime_root)
    assert verdict.neutral is False
    assert "LEGACY/UNVERSIONED" in verdict.message
    assert "R-PIN writer migration not yet landed" in verdict.message


def test_classify_data_root_legacy_for_actual_production_value(tmp_path: Path) -> None:
    """A non-neutral path (e.g. the deprecated umbrella) must classify
    LEGACY against any neutral root."""
    runtime_root = tmp_path / "runtime"
    verdict = classify_data_root(
        "/Users/renhao/git/github/RenQuant", runtime_root=runtime_root
    )
    assert verdict.neutral is False


def test_describe_data_root_matches_classify(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    assert describe_data_root(tmp_path / "elsewhere", runtime_root=runtime_root) == (
        classify_data_root(tmp_path / "elsewhere", runtime_root=runtime_root).message
    )


# --- registry seeder (writer migration, step 1) ---------------------------------------


@pytest.fixture
def pipeline_stops():
    """The owning repo's registry module, or a clearly-reasoned skip."""
    return pytest.importorskip(
        "renquant_pipeline.software_stops",
        reason="sibling renquant-pipeline src not on the path — seeder tests need "
               "its registry_path_for / validate_software_stop_snapshot",
    )


@pytest.fixture
def neutral_root(monkeypatch, tmp_path: Path) -> Path:
    """Pin the neutral root to tmp so no seeder test can reach ~/.renquant."""
    root = tmp_path / "runtime"
    monkeypatch.setenv("RENQUANT_RUNTIME_STATE_ROOT", str(root))
    return root


def _read(path: Path) -> dict:
    return json.loads(path.read_text())


def test_default_registry_rel_and_budget_match_pipeline_defaults(pipeline_stops) -> None:
    """The seeder's local constants are pinned to the pipeline's — if the
    owning repo moves its default, this is the test that goes red."""
    assert DEFAULT_REGISTRY_REL == pipeline_stops.DEFAULT_REGISTRY_PATH
    assert DEFAULT_SEED_MAX_STALENESS_MINUTES == pipeline_stops.DEFAULT_MAX_STALENESS_MINUTES


def test_seeded_registry_path_is_pipeline_tagged(pipeline_stops, tmp_path: Path) -> None:
    expected = pipeline_stops.registry_path_for(tmp_path / DEFAULT_REGISTRY_REL, "alpaca")
    got = seeded_registry_path(tmp_path, "alpaca")
    assert got == expected
    assert got == tmp_path / "data" / "rq105" / "software_stops.alpaca.json"
    # An untagged (None) broker is the pipeline's own sim/test convention.
    assert seeded_registry_path(tmp_path, None) == tmp_path / DEFAULT_REGISTRY_REL
    # The pipeline's broker allow-list is the gate; this repo adds nothing.
    with pytest.raises(ValueError):
        seeded_registry_path(tmp_path, "../evil")


def test_seed_creates_dir_and_schema_valid_empty_file(
    pipeline_stops, neutral_root: Path, tmp_path: Path, caplog
) -> None:
    data_root = tmp_path / "stops-root"
    assert not data_root.exists()
    with caplog.at_level("INFO", logger=contract.__name__):
        path = ensure_registry_seeded(data_root, "alpaca", max_staleness_minutes=12)
    assert path == seeded_registry_path(data_root, "alpaca")
    assert path.is_file()
    raw = _read(path)
    # The pipeline's PUBLIC validator is the judge of shape, not this test.
    assert pipeline_stops.validate_software_stop_snapshot(raw) is raw
    assert raw == {
        "version": pipeline_stops.REGISTRY_VERSION,
        "contract": pipeline_stops.REGISTRY_CONTRACT,
        "max_staleness_minutes": 12.0,
        "last_evaluated_at": None,
        "stops": {},
    }
    # No scratch file left behind; exactly one file in the registry dir.
    assert sorted(p.name for p in path.parent.iterdir()) == [path.name]
    assert any("SEEDED" in r.getMessage() for r in caplog.records)


def test_seed_is_idempotent_and_never_rewrites_a_valid_file(
    pipeline_stops, neutral_root: Path, tmp_path: Path, caplog
) -> None:
    path = ensure_registry_seeded(tmp_path, "alpaca")
    before_bytes = path.read_bytes()
    before_stat = path.stat()
    with caplog.at_level("DEBUG", logger=contract.__name__):
        again = ensure_registry_seeded(tmp_path, "alpaca", max_staleness_minutes=5)
    assert again == path
    assert path.read_bytes() == before_bytes
    assert path.stat().st_mtime_ns == before_stat.st_mtime_ns
    assert path.stat().st_ino == before_stat.st_ino
    assert not any("SEEDED" in r.getMessage() for r in caplog.records)
    assert any("no-op" in r.getMessage() for r in caplog.records)


def test_seed_leaves_a_valid_populated_registry_untouched(
    pipeline_stops, tmp_path: Path
) -> None:
    """A real writer's file with an armed stop is the state the seeder must
    never disturb — same path, different (valid) content."""
    path = seeded_registry_path(tmp_path, "alpaca")
    path.parent.mkdir(parents=True)
    populated = {
        "version": pipeline_stops.REGISTRY_VERSION,
        "contract": pipeline_stops.REGISTRY_CONTRACT,
        "max_staleness_minutes": 30.0,
        "last_evaluated_at": "2026-08-28T13:00:00-07:00",
        "stops": {"BLK": {"symbol": "BLK", "qty": 0.34, "stop_price": 760.0, "source": "z9"}},
    }
    pipeline_stops.validate_software_stop_snapshot(populated)
    path.write_text(json.dumps(populated))
    before = path.read_bytes()
    assert ensure_registry_seeded(tmp_path, "alpaca") == path
    assert path.read_bytes() == before


def test_seed_refuses_to_touch_a_corrupt_file(pipeline_stops, tmp_path: Path) -> None:
    path = seeded_registry_path(tmp_path, "alpaca")
    path.parent.mkdir(parents=True)
    path.write_text("{not json")
    before_bytes = path.read_bytes()
    before_mtime = path.stat().st_mtime_ns
    with pytest.raises(SoftwareStopRegistryCorruptOnDisk) as ei:
        ensure_registry_seeded(tmp_path, "alpaca")
    assert ei.value.path == path
    assert "left untouched" in str(ei.value)
    assert path.read_bytes() == before_bytes
    assert path.stat().st_mtime_ns == before_mtime
    assert sorted(p.name for p in path.parent.iterdir()) == [path.name]
    # Schema-invalid (parses, wrong version) is corrupt too — the pipeline decides.
    path.write_text(json.dumps({"version": 99, "stops": {}}))
    with pytest.raises(SoftwareStopRegistryCorruptOnDisk):
        ensure_registry_seeded(tmp_path, "alpaca")


def test_seed_rejects_a_non_positive_budget_before_writing(pipeline_stops, tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        ensure_registry_seeded(tmp_path, "alpaca", max_staleness_minutes=0)
    assert not (tmp_path / "data").exists()


def test_seed_fails_closed_when_pipeline_module_is_missing(
    monkeypatch, tmp_path: Path
) -> None:
    """No pipeline module => ImportError naming it, and NOTHING on disk.
    ``sys.modules[name] = None`` is the documented way to make ``import``
    raise ImportError for that name."""
    monkeypatch.setitem(sys.modules, "renquant_pipeline.software_stops", None)
    with pytest.raises(ImportError) as ei:
        ensure_registry_seeded(tmp_path, "alpaca")
    assert "renquant_pipeline.software_stops" in str(ei.value)
    assert "FAIL CLOSED" in str(ei.value)
    assert list(tmp_path.iterdir()) == []
    assert contract.main(["seed", "--broker", "alpaca", "--data-root", str(tmp_path)]) == SEED_EXIT_IMPORT
    assert list(tmp_path.iterdir()) == []


def test_seed_path_equals_execution_checker_resolution(pipeline_stops, tmp_path: Path) -> None:
    """The one property the seeder exists for: the file lands where the
    pager's checker looks for it, for the same --data-root and --broker."""
    liveness = pytest.importorskip(
        "renquant_execution.software_stops_liveness",
        reason="sibling renquant-execution src not on the path — cannot compare "
               "against resolve_registry_path",
    )
    for broker in ("alpaca", "alpaca_paper", "paper"):
        checker_path = liveness.resolve_registry_path(
            registry=None, data_root=str(tmp_path), broker=broker,
        )
        assert ensure_registry_seeded(tmp_path, broker) == checker_path


def test_seed_is_schema_valid_bootstrap_but_NOT_ready(pipeline_stops, tmp_path: Path) -> None:
    """A seed flips the execution checker's structural verdict MISSING ->
    VALID (the registry is now LOCATABLE). That is ALL it does: it is
    NOT_READY_UNINITIALIZED for arming, because no writer has evaluated it
    (Codex on #1078: VALID is bootstrap, never readiness evidence)."""
    liveness = pytest.importorskip(
        "renquant_execution.software_stops_liveness",
        reason="sibling renquant-execution src not on the path",
    )
    path = ensure_registry_seeded(tmp_path, "alpaca")
    code, msg = liveness.validate_registry(path)
    assert code == liveness.REGISTRY_VALID, msg
    verdict = registry_readiness(path)
    assert verdict.verdict == NOT_READY_UNINITIALIZED
    assert verdict.ready is False
    assert verdict.n_stops == 0 and verdict.last_evaluated_at is None


# --- readiness classification (the landing gate) ------------------------------------


def _writer_pass(pipeline_stops, data_root: Path, *, now: datetime.datetime, broker: str = "alpaca"):
    """ONE real sell-only-loop pass, constructed the way the umbrella runner
    will (``from_config`` + ``repo_root=<the pager's data root>``)."""
    registry = pipeline_stops.SoftwareStopRegistry.from_config(
        {"execution": {"software_stops": {"enabled": True, "max_staleness_minutes": 30}}},
        broker_name=broker, repo_root=data_root,
    )
    assert registry is not None and registry.is_armed()
    assert registry.evaluate({}, now=now) == []
    return registry


_NOW = datetime.datetime(2026, 8, 29, 10, 0, tzinfo=datetime.timezone.utc)


def test_readiness_unseeded_when_no_file(pipeline_stops, tmp_path: Path) -> None:
    v = registry_readiness(seeded_registry_path(tmp_path, "alpaca"))
    assert v.verdict == NOT_READY_UNSEEDED and not v.ready
    assert v.exit_code == READINESS_EXIT[NOT_READY_UNSEEDED] != 0


def test_readiness_ready_after_one_real_writer_pass_on_the_seeded_path(
    pipeline_stops, tmp_path: Path
) -> None:
    """Seed -> UNINITIALIZED; one real ``SoftwareStopRegistry.evaluate()``
    on the SAME root (resolved via ``from_config``) -> READY at the very
    path the seeder created."""
    seeded = ensure_registry_seeded(tmp_path, "alpaca")
    assert registry_readiness(seeded, now=_NOW).verdict == NOT_READY_UNINITIALIZED
    registry = _writer_pass(pipeline_stops, tmp_path, now=_NOW)
    assert Path(registry._path) == seeded, "writer and seeder must agree on the canonical path"
    v = registry_readiness(seeded, max_staleness_minutes=30, now=_NOW + datetime.timedelta(minutes=5))
    assert v.verdict == READY and v.ready and v.exit_code == 0
    assert v.n_stops == 0 and 4.9 < v.age_minutes < 5.1 and v.budget_minutes == 30.0
    # the seed did NOT survive as-is: the writer's heartbeat is on disk
    assert json.loads(seeded.read_text())["last_evaluated_at"] is not None


def test_readiness_stale_when_heartbeat_older_than_budget(pipeline_stops, tmp_path: Path) -> None:
    seeded = ensure_registry_seeded(tmp_path, "alpaca")
    _writer_pass(pipeline_stops, tmp_path, now=_NOW)
    v = registry_readiness(seeded, max_staleness_minutes=30, now=_NOW + datetime.timedelta(minutes=31))
    assert v.verdict == NOT_READY_STALE and not v.ready
    assert v.exit_code == READINESS_EXIT[NOT_READY_STALE]
    assert 30.9 < v.age_minutes < 31.1


def test_readiness_budget_is_the_tighter_of_caller_and_file(pipeline_stops, tmp_path: Path) -> None:
    """The file's own max_staleness_minutes (30) cannot LOOSEN a stricter
    caller bar (10); a looser caller bar (60) is tightened to the file's."""
    seeded = ensure_registry_seeded(tmp_path, "alpaca")
    _writer_pass(pipeline_stops, tmp_path, now=_NOW)
    later = _NOW + datetime.timedelta(minutes=20)
    assert registry_readiness(seeded, max_staleness_minutes=10, now=later).verdict == NOT_READY_STALE
    v = registry_readiness(seeded, max_staleness_minutes=60, now=later)
    assert v.verdict == READY and v.budget_minutes == 30.0


def test_readiness_corrupt_file_is_reported_and_untouched(pipeline_stops, tmp_path: Path) -> None:
    path = seeded_registry_path(tmp_path, "alpaca")
    path.parent.mkdir(parents=True)
    for text in ("{not json", json.dumps({"version": 99, "stops": {}})):
        path.write_text(text)
        v = registry_readiness(path)
        assert v.verdict == NOT_READY_CORRUPT and not v.ready
        assert v.exit_code == READINESS_EXIT[NOT_READY_CORRUPT]
        assert path.read_text() == text


def test_readiness_unparseable_or_future_heartbeat_is_corrupt(pipeline_stops, tmp_path: Path) -> None:
    """A non-null heartbeat the pipeline validator does not police is still
    not a heartbeat: unparseable, or further in the future than the budget,
    is classified CORRUPT (fail closed), never READY."""
    seeded = ensure_registry_seeded(tmp_path, "alpaca")
    doc = json.loads(seeded.read_text())
    doc["last_evaluated_at"] = "yesterday-ish"
    seeded.write_text(json.dumps(doc))
    assert registry_readiness(seeded, now=_NOW).verdict == NOT_READY_CORRUPT
    doc["last_evaluated_at"] = (_NOW + datetime.timedelta(minutes=31)).isoformat()
    seeded.write_text(json.dumps(doc))
    assert registry_readiness(seeded, max_staleness_minutes=30, now=_NOW).verdict == NOT_READY_CORRUPT
    doc["last_evaluated_at"] = (_NOW + datetime.timedelta(minutes=2)).isoformat()
    seeded.write_text(json.dumps(doc))
    assert registry_readiness(seeded, max_staleness_minutes=30, now=_NOW).verdict == READY, (
        "small clock skew within the budget is not a failure"
    )


def test_readiness_wrong_root_fails_closed_at_the_canonical_path(pipeline_stops, tmp_path: Path) -> None:
    """A VALID and READY registry under a DIFFERENT data root is worth
    nothing: readiness is a property of the canonical path the pager reads."""
    other_root = tmp_path / "other-root"
    ensure_registry_seeded(other_root, "alpaca")
    _writer_pass(pipeline_stops, other_root, now=_NOW)
    assert registry_readiness(seeded_registry_path(other_root, "alpaca"), now=_NOW).verdict == READY
    canonical = seeded_registry_path(tmp_path / "canonical-root", "alpaca")
    v = registry_readiness(canonical, now=_NOW)
    assert v.verdict == NOT_READY_UNSEEDED and not v.ready


def test_readiness_never_depends_on_stop_count(pipeline_stops, tmp_path: Path) -> None:
    """A populated registry with NO heartbeat is NOT ready; an empty one
    WITH a fresh heartbeat IS. n_stops is reported, never decisive."""
    path = seeded_registry_path(tmp_path, "alpaca")
    path.parent.mkdir(parents=True)
    populated = {
        "version": pipeline_stops.REGISTRY_VERSION, "contract": pipeline_stops.REGISTRY_CONTRACT,
        "max_staleness_minutes": 30.0, "last_evaluated_at": None,
        "stops": {"BLK": {"symbol": "BLK", "qty": 0.34, "stop_price": 760.0, "source": "z9"}},
    }
    path.write_text(json.dumps(populated))
    v = registry_readiness(path, now=_NOW)
    assert v.verdict == NOT_READY_UNINITIALIZED and v.n_stops == 1


def test_readiness_cli_exit_codes_are_distinct_and_zero_only_on_ready(
    pipeline_stops, neutral_root: Path, tmp_path: Path, capsys
) -> None:
    root = tmp_path / "root"
    now = _NOW.isoformat()

    def run(*extra):
        return contract.main(["readiness", "--broker", "alpaca", "--data-root", str(root), "--now", now, *extra])

    assert run() == READINESS_EXIT[NOT_READY_UNSEEDED] == 10
    assert capsys.readouterr().out.startswith("NOT_READY_UNSEEDED: ")
    ensure_registry_seeded(root, "alpaca")
    assert run() == READINESS_EXIT[NOT_READY_UNINITIALIZED] == 11
    assert capsys.readouterr().out.startswith("NOT_READY_UNINITIALIZED: ")
    _writer_pass(pipeline_stops, root, now=_NOW - datetime.timedelta(minutes=5))
    assert run() == 0
    assert capsys.readouterr().out.startswith("READY: ")
    assert run("--max-staleness-minutes", "4") == READINESS_EXIT[NOT_READY_STALE] == 12
    assert capsys.readouterr().out.startswith("NOT_READY_STALE: ")
    seeded_registry_path(root, "alpaca").write_text("garbage")
    assert run() == READINESS_EXIT[NOT_READY_CORRUPT] == 13
    assert capsys.readouterr().out.startswith("NOT_READY_CORRUPT: ")
    assert contract.main(["readiness", "--broker", "bogus", "--data-root", str(root)]) == SEED_EXIT_USAGE
    assert len(set(READINESS_EXIT.values())) == len(READINESS_EXIT)


def test_readiness_cli_fails_closed_without_the_pipeline_module(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setitem(sys.modules, "renquant_pipeline.software_stops", None)
    assert contract.main(["readiness", "--broker", "alpaca", "--data-root", str(tmp_path)]) == SEED_EXIT_IMPORT


# --- seed CLI ------------------------------------------------------------------------


def test_seed_cli_exit_codes(pipeline_stops, neutral_root: Path, tmp_path: Path, capsys) -> None:
    data_root = tmp_path / "root"
    assert contract.main(["seed", "--broker", "alpaca", "--data-root", str(data_root)]) == SEED_EXIT_OK
    out = capsys.readouterr().out
    path = seeded_registry_path(data_root, "alpaca")
    assert out.startswith("SEEDED: ") and str(path) in out
    assert _read(path)["max_staleness_minutes"] == DEFAULT_SEED_MAX_STALENESS_MINUTES

    assert contract.main(["seed", "--broker", "alpaca", "--data-root", str(data_root)]) == SEED_EXIT_OK
    assert capsys.readouterr().out.startswith("EXISTS: ")

    path.write_text("garbage")
    assert contract.main(["seed", "--broker", "alpaca", "--data-root", str(data_root)]) == SEED_EXIT_CORRUPT
    assert "CORRUPT" in capsys.readouterr().err
    assert path.read_text() == "garbage"

    assert contract.main(["seed", "--broker", "not-a-broker", "--data-root", str(data_root)]) == SEED_EXIT_USAGE
    assert "USAGE-ERROR" in capsys.readouterr().err
    assert not (data_root / "data" / "rq105" / "software_stops.not_a_broker.json").exists()


def test_seed_cli_budget_flag_is_written_into_a_new_seed_only(
    pipeline_stops, neutral_root: Path, tmp_path: Path
) -> None:
    assert contract.main(
        ["seed", "--broker", "alpaca", "--data-root", str(tmp_path), "--max-staleness-minutes", "15"]
    ) == SEED_EXIT_OK
    path = seeded_registry_path(tmp_path, "alpaca")
    assert _read(path)["max_staleness_minutes"] == 15.0
    assert contract.main(
        ["seed", "--broker", "alpaca", "--data-root", str(tmp_path), "--max-staleness-minutes", "5"]
    ) == SEED_EXIT_OK
    assert _read(path)["max_staleness_minutes"] == 15.0


def test_seed_cli_default_data_root_is_the_neutral_software_stops_dir(
    pipeline_stops, neutral_root: Path
) -> None:
    """Without --data-root the CLI seeds under the neutral runtime root's
    ``software-stops`` dir — which the env var pins to tmp here."""
    assert contract.main(["seed", "--broker", "alpaca"]) == SEED_EXIT_OK
    expected_root = software_stops_registry_root(runtime_state_root())
    assert expected_root == neutral_root / "software-stops"
    assert seeded_registry_path(expected_root, "alpaca").is_file()


def test_seed_cli_default_matches_the_pager_plist_data_root() -> None:
    """The plist arms the pager with an absolute, host-specific path; the
    seeder's default is the same location by convention. Compare the
    host-independent suffix, not the operator's home directory."""
    with _PAGER_PLIST.open("rb") as fh:
        env = plistlib.load(fh)["EnvironmentVariables"]
    plist_root = Path(env["RENQUANT_STOPS_PAGER_DATA_ROOT"])
    default_root = software_stops_registry_root(DEFAULT_RUNTIME_STATE_ROOT)
    assert default_root == Path("~/.renquant/runtime/software-stops")
    assert plist_root.parts[-3:] == default_root.parts[-3:]


def test_seed_cli_module_entry_point(pipeline_stops, tmp_path: Path) -> None:
    """``python -m ...`` is what the umbrella sell wrapper will call."""
    # Build PYTHONPATH from where the imported packages actually live — NOT
    # from ``sys.path``: in the full suite ``sys.path`` carries hundreds of
    # duplicated ``sys.path.insert`` entries from other test modules, and the
    # joined string (50,356 bytes, 391 entries, 89 unique) made the child exit 0 with EMPTY stdout in the
    # full run while passing in isolation (measured 2026-08-29).
    src_dirs: list[str] = []
    for name, mod in list(sys.modules.items()):
        if name.startswith("renquant_") and "." not in name and getattr(mod, "__file__", None):
            d = str(Path(mod.__file__).resolve().parents[1])
            if d not in src_dirs:
                src_dirs.append(d)
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["PYTHONPATH"] = os.pathsep.join(src_dirs)
    env["RENQUANT_RUNTIME_STATE_ROOT"] = str(tmp_path / "unused")
    proc = subprocess.run(
        [sys.executable, "-m", "renquant_orchestrator.software_stops_registry_contract",
         "seed", "--broker", "alpaca", "--data-root", str(tmp_path / "root")],
        capture_output=True, text=True, env=env, check=False,
    )
    diag = (
        f"rc={proc.returncode} stdout={proc.stdout!r} stderr={proc.stderr!r} "
        f"executable={sys.executable!r} run={subprocess.run!r} "
        f"PYTHONPATH={env['PYTHONPATH']!r}"
    )
    assert proc.returncode == SEED_EXIT_OK, diag
    assert proc.stdout.startswith("SEEDED: "), diag
    assert seeded_registry_path(tmp_path / "root", "alpaca").is_file()
    assert not (tmp_path / "unused").exists()
