"""The pin must be able to FAIL, and for the right reason. (GOAL-3, #623)

#623's finding was that nothing in the repo says which copy of a symbol executes.
A pin that only ever passes would restate that problem in a greener colour, so
every branch below is exercised, and the mechanism tests use stdlib symbols so they
do not depend on which sibling checkouts happen to be importable.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

OPS = Path(__file__).resolve().parent.parent / "ops"
_SPEC = importlib.util.spec_from_file_location(
    "import_resolution_check", OPS / "import_resolution_check.py")
chk = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(chk)

#: Environment-independent stand-ins for the real symbol table.
FAKE = (("json", "dumps"), ("os.path", "join"))


@pytest.fixture()
def fake_symbols(monkeypatch):
    monkeypatch.setattr(chk, "PINNED_SYMBOLS", FAKE)
    return FAKE


def _live_pins() -> dict:
    return chk.emit()


# --- the happy path, so failures below are attributable ----------------------

def test_freshly_emitted_pins_verify_clean(fake_symbols):
    assert chk.verify(_live_pins()) == []


# --- drift: the case the pin exists for -------------------------------------

def test_source_file_drift_is_reported(fake_symbols):
    pins = _live_pins()
    pins["symbols"]["json.dumps"]["source_file"] = "somewhere/else.py"
    problems = chk.verify(pins)
    assert len(problems) == 1
    assert "source_file drifted" in problems[0]
    assert "Which copy runs has CHANGED" in problems[0]


def test_defined_in_drift_is_reported(fake_symbols):
    """A package __init__ re-exporting a DIFFERENT implementation under the same
    documented name is exactly #623 R1, and it shows up here as defined_in."""
    pins = _live_pins()
    pins["symbols"]["json.dumps"]["defined_in"] = "json.impostor"
    problems = chk.verify(pins)
    assert len(problems) == 1 and "defined_in drifted" in problems[0]


# --- absent / extra / broken pins must not pass silently ---------------------

def test_a_symbol_missing_from_the_pin_file_is_a_problem(fake_symbols):
    pins = _live_pins()
    del pins["symbols"]["json.dumps"]
    problems = chk.verify(pins)
    assert len(problems) == 1 and "absent from the pin file" in problems[0]


def test_a_pin_for_a_symbol_no_longer_checked_is_a_problem(fake_symbols):
    pins = _live_pins()
    pins["symbols"]["json.retired"] = {"defined_in": "json", "source_file": "json.py"}
    problems = chk.verify(pins)
    assert len(problems) == 1 and "no longer in PINNED_SYMBOLS" in problems[0]


def test_an_empty_pin_file_is_a_problem_not_a_pass(fake_symbols):
    assert chk.verify({"schema_version": 1, "symbols": {}}) != []
    assert chk.verify({}) != []


def test_a_pin_emitted_from_a_broken_environment_is_rejected(fake_symbols):
    """If the BASELINE records an error it is not a baseline. Accepting it would
    make the check pass forever on a symbol that never resolved."""
    pins = _live_pins()
    pins["symbols"]["json.dumps"] = {"error": "import failed: ModuleNotFoundError"}
    problems = chk.verify(pins)
    assert len(problems) == 1 and "the pin itself records an error" in problems[0]


def test_an_unresolvable_symbol_is_a_problem(monkeypatch):
    monkeypatch.setattr(chk, "PINNED_SYMBOLS", (("json", "no_such_attr"),))
    pins = {"schema_version": 1,
            "symbols": {"json.no_such_attr": {"defined_in": "json",
                                              "source_file": "json/__init__.py"}}}
    problems = chk.verify(pins)
    assert len(problems) == 1 and "unresolvable" in problems[0]


def test_a_missing_module_is_reported_not_skipped(monkeypatch):
    monkeypatch.setattr(chk, "PINNED_SYMBOLS", (("no_such_module_xyz", "thing"),))
    r = chk.resolve("no_such_module_xyz", "thing")
    assert "import failed" in r["error"]


# --- path normalisation: dev checkout vs run checkout ------------------------

def test_package_relative_strips_everything_above_src():
    """The sentinel and the daily run execute from `renquant-orchestrator-run`, not
    the dev checkout. Pinning absolute paths would fail for the wrong reason on the
    machine that matters."""
    dev = chk._package_relative("/Users/x/git/renquant-common/src/renquant_common/pipeline.py")
    run = chk._package_relative("/Users/x/git/renquant-common-run/src/renquant_common/pipeline.py")
    assert dev == run == "renquant_common/pipeline.py"


def test_package_relative_handles_a_non_src_layout_without_crashing():
    got = chk._package_relative("/a/b/c/d/mod.py")
    assert got and got.endswith("mod.py") and not got.startswith("/")


def test_package_relative_of_none_is_none():
    assert chk._package_relative(None) is None


# --- exit codes: a broken invocation must not read as clean ------------------

def test_missing_pin_file_exits_2(tmp_path, fake_symbols):
    assert chk.main(["--pins", str(tmp_path / "nope.json")]) == 2


def test_unreadable_pin_file_exits_2(tmp_path, fake_symbols):
    bad = tmp_path / "pins.json"
    bad.write_text("{truncated")
    assert chk.main(["--pins", str(bad)]) == 2


def test_drift_exits_1(tmp_path, fake_symbols):
    pins = _live_pins()
    pins["symbols"]["json.dumps"]["source_file"] = "elsewhere.py"
    p = tmp_path / "pins.json"
    p.write_text(json.dumps(pins))
    assert chk.main(["--pins", str(p)]) == 1


def test_clean_exits_0(tmp_path, fake_symbols):
    p = tmp_path / "pins.json"
    p.write_text(json.dumps(_live_pins()))
    assert chk.main(["--pins", str(p)]) == 0


def test_emit_writes_nothing(tmp_path, fake_symbols, capsys):
    """`--emit` prints for review. A surface that can silently re-baseline itself is
    not a pin, so this must never touch the pin file."""
    p = tmp_path / "pins.json"
    p.write_text("SENTINEL")
    assert chk.main(["--emit", "--pins", str(p)]) == 0
    assert p.read_text() == "SENTINEL"
    assert json.loads(capsys.readouterr().out)["symbols"]


# --- the COMMITTED pin file itself ------------------------------------------

def test_the_committed_pin_file_is_well_formed_and_has_no_errored_entries():
    """A committed pin containing an `error` would be a baseline that can never be
    violated. This caught a real mistake: my first emit pinned
    `model_content_sha` because the grep I built the symbol list from used a
    character class without digits and truncated `model_content_sha256`."""
    pins = json.loads((OPS / "import_resolution_pins.json").read_text())
    assert pins["schema_version"] == 1
    symbols = pins["symbols"]
    assert len(symbols) == len(chk.PINNED_SYMBOLS)
    errored = {k: v["error"] for k, v in symbols.items() if "error" in v}
    assert errored == {}, f"pins emitted from a broken environment: {errored}"
    for key, entry in symbols.items():
        assert entry.get("defined_in"), key
        assert entry.get("source_file"), key
        assert not entry["source_file"].startswith("/"), (
            f"{key} pins an absolute path, which differs between the dev and run "
            f"checkouts")


def test_every_pinned_symbol_is_one_this_repo_actually_imports():
    """A pin over a symbol the repo does not import is scope creep — it would drag
    a sibling's internals into this repo's contract, which is the boundary
    violation #623 R3/R4 came from."""
    src = Path(__file__).resolve().parent.parent / "src"
    blob = "\n".join(p.read_text(encoding="utf-8", errors="ignore")
                     for p in src.rglob("*.py"))
    missing = [f"{m}.{a}" for m, a in chk.PINNED_SYMBOLS if a not in blob]
    assert missing == [], f"pinned but never referenced in src/: {missing}"


# --- the gate: wired into the drift scan, not left as a tool nobody runs ------

def _drift():
    sys.path.insert(0, str(OPS))
    try:
        spec = importlib.util.spec_from_file_location(
            "run_surface_drift_check", OPS / "run_surface_drift_check.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        sys.path.pop(0)


def test_the_drift_scan_actually_calls_the_check():
    """'Deployed but dark' is not done. If this check is not reachable from the
    scheduled job it is a document, not a gate."""
    src = (OPS / "run_surface_drift_check.py").read_text()
    assert "check_import_resolution()" in src
    i = src.index("def main(")
    assert "check_import_resolution()" in src[i:], "defined but never called from main"


def test_drift_scan_check_is_quiet_when_pins_hold():
    loud, info = _drift().check_import_resolution()
    assert loud == [], loud
    assert len(info) == 1 and "resolve as reviewed" in info[0]


def test_drift_scan_check_is_LOUD_on_a_missing_pin_file(monkeypatch, tmp_path):
    d = _drift()
    sys.path.insert(0, str(OPS))
    try:
        import import_resolution_check as irc
        monkeypatch.setattr(irc, "PINS", tmp_path / "gone.json")
        loud, info = d.check_import_resolution()
    finally:
        sys.path.pop(0)
    assert len(loud) == 1 and "pin file missing" in loud[0]
    assert info == []


def test_bare_invocation_resolves_like_the_daily_not_like_the_shell():
    """The ops-audit aggregator invokes this checker with NO PYTHONPATH; on its
    first scheduled run (2026-08-03) three symbols read "unresolvable
    (ModuleNotFoundError)" purely for that reason while the daily's own path
    set resolved them fine — the checker measured the invoking shell, not the
    deployment. A bare subprocess must now succeed on the operator machine
    (skips loudly where the sibling checkouts are absent — CI)."""
    import os
    import subprocess
    import sys as _sys
    from pathlib import Path as _P

    github = _P(__file__).resolve().parent.parent.parent
    if not (github / "renquant-backtesting" / "src").is_dir():
        import pytest
        pytest.skip("sibling checkouts absent — daily-resolution not reproducible here")
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    r = subprocess.run(
        [_sys.executable, str(_P(__file__).resolve().parent.parent
                              / "ops" / "import_resolution_check.py")],
        capture_output=True, text=True, env=env, timeout=120)
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert "unresolvable" not in r.stdout


def test_caller_pythonpath_keeps_precedence_over_the_sibling_append():
    """APPEND, not prepend: a caller-exported resolution must win, so the
    checker never reports a third resolution that neither the shell nor the
    daily would use."""
    import sys as _sys
    sys_path_before = list(_sys.path)
    try:
        import import_resolution_check as C
        marker = "/nonexistent-caller-export"
        _sys.path.insert(0, marker)
        C._ensure_daily_resolution()
        assert _sys.path[0] == marker  # caller's entry still first
    finally:
        _sys.path[:] = sys_path_before


def test_materialized_runtime_root_wins_over_a_conflicting_sibling(tmp_path, monkeypatch):
    """[codex on orch#773] The daily sources current.env FIRST; siblings are
    only its fallback. With a runtime root materialized, the checker must
    resolve each repo from the RUNTIME and must NOT also append the sibling —
    otherwise it can report imports healthy from a newer sibling while the
    daily (pinned runtime) still fails."""
    import sys as _sys
    import import_resolution_check as C

    runtime = tmp_path / "runtime-repos"
    (runtime / "renquant-backtesting" / "src").mkdir(parents=True)
    monkeypatch.setenv("RENQUANT_SUBREPO_ROOT", str(runtime))
    before = list(_sys.path)
    try:
        C._ensure_daily_resolution()
        added = [p for p in _sys.path if p not in before]
        runtime_hits = [p for p in added if str(runtime) in p]
        sibling_hits = [p for p in added
                        if "renquant-backtesting" in p and str(runtime) not in p]
        assert runtime_hits, added
        assert sibling_hits == [], (
            "sibling appended alongside a materialized runtime — the checker "
            "would measure a resolution the daily does not use")
    finally:
        _sys.path[:] = before


def test_current_env_parsing_mirrors_the_shell_export(tmp_path, monkeypatch):
    import import_resolution_check as C
    umbrella = tmp_path / "RenQuant"
    (umbrella / ".subrepo_assembly").mkdir(parents=True)
    runtime = tmp_path / "rt"
    runtime.mkdir()
    (umbrella / ".subrepo_assembly" / "current.env").write_text(
        "# comment\nexport RENQUANT_ASSEMBLY_DIR=/x\n"
        f"export RENQUANT_SUBREPO_ROOT={runtime}\n", encoding="utf-8")
    monkeypatch.delenv("RENQUANT_SUBREPO_ROOT", raising=False)
    assert C._runtime_root_from_current_env(umbrella) == runtime


def test_missing_current_env_falls_back_to_none_not_a_guess(tmp_path, monkeypatch):
    import import_resolution_check as C
    monkeypatch.delenv("RENQUANT_SUBREPO_ROOT", raising=False)
    assert C._runtime_root_from_current_env(tmp_path / "nope") is None
