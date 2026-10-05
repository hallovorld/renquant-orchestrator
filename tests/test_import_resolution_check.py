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


@pytest.fixture(autouse=True)
def _fresh_resolution(monkeypatch):
    """The resolver chooses its root ONCE per process (idempotent); every test
    that sets RENQUANT_SUBREPO_ROOT needs a fresh choice, and the sys.path it
    inserts must not leak into the next test."""
    before = list(sys.path)
    monkeypatch.setattr(chk, "_RESOLUTION", {})
    sys.path.insert(0, str(OPS))
    try:
        import import_resolution_check as C
        monkeypatch.setattr(C, "_RESOLUTION", {})
    finally:
        sys.path.pop(0)
    yield
    sys.path[:] = before


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
    """The drift scan's own call path — `irc.verify(pins)` with NO main() — in
    a fresh interpreter with no PYTHONPATH, i.e. the launchd plist's shape.
    Before 2026-08-30 that path never established the daily's package roots
    and reported three sibling packages unresolvable every morning. Run out of
    process on purpose: in THIS process pytest's pythonpath / earlier tests
    have already imported the renquant_* packages from wherever the test run
    found them, which is exactly the state the check is designed to flag."""
    import os
    import subprocess

    github = Path(__file__).resolve().parent.parent.parent
    umbrella_runtime = chk._UMBRELLA / ".subrepo_runtime" / "repos"
    if not (github / "renquant-backtesting" / "src").is_dir() and not umbrella_runtime.is_dir():
        pytest.skip("neither sibling checkouts nor a pinned runtime — resolution not reproducible here")
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "RENQUANT_SUBREPO_ROOT")}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    code = (
        "import sys, json; sys.path.insert(0, %r)\n"
        "import run_surface_drift_check as d\n"
        "loud, info = d.check_import_resolution()\n"
        "print(json.dumps({'loud': loud, 'info': info}))\n" % str(OPS))
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=180)
    assert r.returncode == 0, (r.stdout, r.stderr)
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out["loud"] == [], out["loud"]
    assert len(out["info"]) == 1 and "resolve as reviewed" in out["info"][0]
    assert "resolved against the" in out["info"][0]


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


def test_caller_pythonpath_keeps_precedence_over_the_runtime_insert():
    """Inserted at the PYTHONPATH position, not prepended: a caller-exported
    resolution must win, so the checker never reports a third resolution that
    neither the shell nor the daily would use. (Since 2026-08-30 the roots are
    no longer APPENDED either — see the site-packages test below.)"""
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


def test_runtime_missing_one_repo_does_NOT_fall_back_to_its_sibling(tmp_path, monkeypatch):
    """[codex on orch#773 round 2] The shell helper picks the root ONCE and
    emits only that root's repo paths; a repo missing from a materialized
    runtime must stay loudly unresolvable, never masked by a sibling import."""
    import sys as _sys
    import import_resolution_check as C

    runtime = tmp_path / "runtime-repos"
    (runtime / "renquant-common" / "src").mkdir(parents=True)
    # renquant-backtesting deliberately ABSENT from the runtime; the real
    # sibling exists on this machine.
    monkeypatch.setenv("RENQUANT_SUBREPO_ROOT", str(runtime))
    before = list(_sys.path)
    try:
        C._ensure_daily_resolution()
        added = [p for p in _sys.path if p not in before]
        assert any(str(runtime) in p for p in added), added
        assert not any("renquant-backtesting" in p for p in added), (
            "a sibling was substituted for a repo missing from the "
            "materialized runtime — the exact masking the review names")
    finally:
        _sys.path[:] = before


# --- 2026-08-30: the check measures the PINNED tree, and says so -------------
#
# Measured on the operator machine before this version: the umbrella venv
# carries editable `.pth` entries for four packages pointing at
# /Users/renhao/git/github/<repo>/src, and the checker APPENDED the runtime
# roots behind site-packages — so renquant_common / _artifacts / _base_data /
# _model_gbdt resolved from the mutable siblings (site-packages at sys.path
# index 4, the runtime at 9+) while the package-relative pin read OK. And the
# drift scan, which calls verify() directly, never established any root at
# all: three symbols "unresolvable" every morning. The fakes below build a
# runtime tree and an "editable sibling" in tmp_path; nothing reads the disk.

FAKE_PKG = "renquant_fakeprobe_t"   # carries the renquant_ prefix: subject to the root assertion


def _fake_runtime(tmp_path: Path, *, package_in_runtime: bool) -> tuple[Path, Path]:
    """(runtime root, sibling src). The sibling ALWAYS has the package; the
    runtime has it only when asked. Both define `thing` in mod.py."""
    runtime = tmp_path / "runtime-repos"
    (runtime / "renquant-common" / "src").mkdir(parents=True)
    if package_in_runtime:
        pkg = runtime / "renquant-common" / "src" / FAKE_PKG
        pkg.mkdir()
        (pkg / "__init__.py").write_text(f"from {FAKE_PKG}.mod import thing\n")
        (pkg / "mod.py").write_text("def thing():\n    return 'runtime'\n")
    sibling = tmp_path / "sibling" / "src"
    spkg = sibling / FAKE_PKG
    spkg.mkdir(parents=True)
    (spkg / "__init__.py").write_text(f"from {FAKE_PKG}.mod import thing\n")
    (spkg / "mod.py").write_text("def thing():\n    return 'sibling'\n")
    return runtime, sibling


@pytest.fixture()
def fake_probe(monkeypatch):
    monkeypatch.setattr(chk, "PINNED_SYMBOLS", ((FAKE_PKG, "thing"),))
    yield
    for name in [n for n in sys.modules if n == FAKE_PKG or n.startswith(FAKE_PKG + ".")]:
        del sys.modules[name]


def test_a_symbol_resolving_only_from_an_editable_sibling_is_flagged(tmp_path, monkeypatch, fake_probe):
    """The package is importable ONLY from the sibling (appended, where a
    `.pth` entry lands). The pin itself matches — package-relative paths are
    identical — so only the root assertion can tell: resolved_from_unpinned_path."""
    runtime, sibling = _fake_runtime(tmp_path, package_in_runtime=False)
    monkeypatch.setenv("RENQUANT_SUBREPO_ROOT", str(runtime))
    sys.path.append(str(sibling))
    pins = chk.emit()
    assert pins["symbols"][f"{FAKE_PKG}.thing"]["source_file"] == f"{FAKE_PKG}/mod.py"
    assert "abs_source_file" not in pins["symbols"][f"{FAKE_PKG}.thing"], "pins must stay path-independent"
    problems = chk.verify(pins)
    assert len(problems) == 1, problems
    assert "resolved_from_unpinned_path" in problems[0]
    assert str(sibling) in problems[0] and str(runtime) in problems[0]
    assert "pinned runtime" in problems[0]


def test_the_pinned_runtime_beats_an_editable_sibling_that_is_also_present(tmp_path, monkeypatch, fake_probe):
    """Both trees carry the package; the sibling sits where site's `.pth`
    entries sit (appended). The runtime must win — inserted BEFORE the
    interpreter's own entries — and the check is then clean."""
    runtime, sibling = _fake_runtime(tmp_path, package_in_runtime=True)
    monkeypatch.setenv("RENQUANT_SUBREPO_ROOT", str(runtime))
    sys.path.append(str(sibling))
    problems = chk.verify(chk.emit())
    assert problems == [], problems
    import importlib
    assert importlib.import_module(FAKE_PKG).thing() == "runtime"


def test_verify_establishes_the_resolution_itself_without_main(tmp_path, monkeypatch, fake_probe):
    """The drift scan's shape: import the module, call verify() — no main().
    Before 2026-08-30 nothing put the runtime on sys.path on that path."""
    runtime, _ = _fake_runtime(tmp_path, package_in_runtime=True)
    monkeypatch.setenv("RENQUANT_SUBREPO_ROOT", str(runtime))
    assert not any(str(runtime) in p for p in sys.path)
    pins = {"schema_version": 1, "symbols": {f"{FAKE_PKG}.thing": {
        "defined_in": f"{FAKE_PKG}.mod", "source_file": f"{FAKE_PKG}/mod.py"}}}
    assert chk.verify(pins) == []
    assert any(str(runtime) in p for p in sys.path)


def test_runtime_roots_are_inserted_before_the_interpreters_own_entries(tmp_path, monkeypatch):
    """The exact defect: appended roots lose to site-packages and its `.pth`
    siblings. Every inserted root must precede the first stdlib/site entry
    and follow whatever the caller exported."""
    runtime = tmp_path / "runtime-repos"
    for repo in ("renquant-common", "renquant-backtesting"):
        (runtime / repo / "src").mkdir(parents=True)
    monkeypatch.setenv("RENQUANT_SUBREPO_ROOT", str(runtime))
    caller = str(tmp_path / "caller-export")
    sys.path.insert(0, caller)
    chk._ensure_daily_resolution()
    idx = {p: i for i, p in enumerate(sys.path)}
    inserted = [p for p in sys.path if p.startswith(str(runtime))]
    assert len(inserted) == 2
    site_like = [i for i, p in enumerate(sys.path)
                 if p and any(p.startswith(str(Path(x).resolve())) for x in (sys.prefix, sys.base_prefix))]
    assert site_like, "no interpreter entry found on sys.path?"
    assert all(idx[p] < min(site_like) for p in inserted), (inserted, site_like, sys.path)
    assert all(idx[p] > idx[caller] for p in inserted)


def test_stdlib_symbols_are_outside_the_root_assertion(fake_symbols):
    """The mechanism tests above use stdlib stand-ins; the root assertion
    applies to renquant_* modules only, so those stay clean."""
    assert chk.verify(chk.emit()) == []
    assert chk._unpinned_path_problem("json.dumps", chk.resolve("json", "dumps")) is None


def test_resolution_is_established_once_and_reported(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime-repos"
    (runtime / "renquant-common" / "src").mkdir(parents=True)
    monkeypatch.setenv("RENQUANT_SUBREPO_ROOT", str(runtime))
    first = chk._ensure_daily_resolution()
    monkeypatch.setenv("RENQUANT_SUBREPO_ROOT", str(tmp_path / "elsewhere"))
    assert chk._ensure_daily_resolution() is first, "the root is chosen ONCE per process"
    assert first["runtime_materialized"] is True and first["root"] == runtime
    assert "pinned runtime" in chk.resolution_summary() and str(runtime) in chk.resolution_summary()


def test_without_a_runtime_the_summary_names_the_sibling_fallback(tmp_path, monkeypatch):
    monkeypatch.delenv("RENQUANT_SUBREPO_ROOT", raising=False)
    monkeypatch.setattr(chk, "_UMBRELLA", tmp_path / "no-umbrella")
    r = chk._ensure_daily_resolution()
    assert r["runtime_materialized"] is False
    assert "sibling FALLBACK root" in chk.resolution_summary()


def test_a_module_cached_from_an_unpinned_path_is_named_as_cached(tmp_path, monkeypatch, fake_probe):
    """A process that imported a renquant_* package BEFORE the resolution was
    established keeps the cached module; the problem line must say so, since
    re-inserting sys.path cannot fix a module already in sys.modules."""
    import importlib
    runtime, sibling = _fake_runtime(tmp_path, package_in_runtime=True)
    sys.path.append(str(sibling))
    importlib.import_module(FAKE_PKG)          # cached from the sibling
    monkeypatch.setenv("RENQUANT_SUBREPO_ROOT", str(runtime))
    problems = chk.verify(chk.emit())
    assert len(problems) == 1 and "resolved_from_unpinned_path" in problems[0]
    assert "already imported before the pinned resolution was established" in problems[0]
