#!/usr/bin/env python3
"""Pin WHERE each public symbol this repo imports actually resolves. (GOAL-3, #623)

`#623` registered seven twin-implementation sites and stated the real defect
plainly: *the failure is not that duplicates exist — some duplication is
deliberate. The failure is that nothing in the repo tells you which copy
executes.* In four of the seven rows a defect was filed or a fix written against a
copy that does not run, two of them by me in one session.

This closes that gap for the surface this repo is entitled to constrain: **the
public symbols the orchestrator itself imports.** For each one it resolves the
object at import time and records the file the code actually comes from, then
compares against a committed pin. It answers "which copy runs" the only way that
cannot be fooled — **by resolution, not by grep.**

**Scope, deliberately narrow.** Only symbols this repo imports. It does NOT
enumerate other repos' internal twins: `renquant_pipeline`'s public
`VetoWeakBuysTask`-vs-kernel split is real (#623 R1) but it is not part of this
repo's dependency surface, and encoding a sibling's internals here would be the
boundary violation this programme has already paid for twice. What the orchestrator
IS entitled to pin is which implementation it gets when it imports a public name.

Three of this repo's own incidents were exactly that question:

* `renquant_common.load_scorer` decides which scorer the shadow path serves;
* `renquant_common.model_fingerprint.model_content_sha256` is why a root-level
  `training_contract` key raises and orch#620 had to nest the contract under
  `metadata` — which then made the WF gate's static sanity read the wrong panel;
* `renquant_common.validate_live_run_bundle` accepts a bundle after discarding 13
  of its 18 fields (#624), so *which* validator that name resolves to matters.

**Which tree the check measures (2026-08-30).** The pins are package-relative
paths, so a symbol resolving from a SIBLING checkout and the same symbol
resolving from the PINNED runtime (`.subrepo_runtime/repos/<repo>/src`) pin
identically — the pin cannot tell them apart, which is why the check must
establish the daily's resolution ITSELF and then ASSERT it. Two defects were
measured on the operator machine before this version:

* `run_surface_drift_check.py` imported this module and called `verify()`
  directly; only `main()` established the daily's package roots, so the scan
  ran with the launchd plist's PYTHONPATH (orchestrator only) and reported
  `renquant_backtesting.BacktestPipeline`, `renquant_execution.get_broker`
  and `renquant_execution.BrokerExecutionPipeline` "unresolvable
  (ModuleNotFoundError)" every day (three false alarms, 2026-08-30 07:00).
* `_ensure_daily_resolution()` APPENDED the runtime roots, i.e. AFTER
  site-packages — and the umbrella venv carries editable `.pth` entries for
  four packages (`renquant_common`, `renquant_artifacts`, `renquant_base_data`,
  `renquant_model`) pointing at `/Users/renhao/git/github/<repo>/src`. So even
  the CLI path resolved those four from the mutable sibling checkouts while
  the runtime sat at sys.path index 9+ (site-packages at index 4) and the pin
  read OK: the pin was being verified against unpinned trees.

Now `verify()` / `emit()` establish the resolution themselves (idempotent),
insert the chosen root's package paths where PYTHONPATH entries live — after
anything the caller exported, BEFORE the stdlib and site-packages, exactly the
precedence the daily's `current.env` PYTHONPATH gives them — and, for every
`renquant_*` symbol, assert that the file the object was defined in AND the
imported module's `__file__` lie under the chosen root. A symbol resolving from
anywhere else is reported as `resolved_from_unpinned_path`, a drift issue in its
own right.

Usage:

    import_resolution_check.py                # verify against the committed pins
    import_resolution_check.py --emit         # print fresh pins for review

`--emit` prints; it never writes. The pin file is updated only through a reviewed
PR, the same rule the launchd manifest follows — a surface that can silently
re-baseline itself is not a pin.

Exit codes: ``0`` all pins hold, ``1`` drift or an unresolvable symbol, ``2``
usage/IO error, so a broken invocation cannot read as a clean check.
"""

from __future__ import annotations

import argparse
import importlib
import inspect
import json
import os
import sys
from pathlib import Path
from typing import Any

PINS = Path(__file__).resolve().parent / "import_resolution_pins.json"

#: The daily's import resolution, reproduced [codex on orch#773: the first
#: version derived the SIBLING checkouts unconditionally, which is only the
#: daily's FALLBACK — daily_104.sh first sources the umbrella's
#: `.subrepo_assembly/current.env`, whose RENQUANT_SUBREPO_ROOT points at the
#: PINNED runtime (`.subrepo_runtime/repos`); measuring siblings while the
#: runtime is materialized can report imports healthy from a newer checkout
#: while the daily still fails]. Chain, mirroring scripts/subrepo_env.sh
#: `renquant_subrepo_root`: RENQUANT_SUBREPO_ROOT env (as current.env would
#: export) → sibling fallback. Why this checker exists at all: on the
#: aggregator's first scheduled run (2026-08-03) three symbols reported
#: "unresolvable (ModuleNotFoundError)" purely because ops_audit.py exports
#: no PYTHONPATH.
_UMBRELLA = Path("/Users/renhao/git/github/RenQuant")
_DAILY_REPOS: tuple[str, ...] = (
    "renquant-common", "renquant-base-data", "renquant-artifacts",
    "renquant-model", "renquant-pipeline", "renquant-execution",
    "renquant-strategy-104", "renquant-backtesting",
)

#: Only modules whose top-level package carries this prefix are subject to the
#: "resolves under the chosen root" assertion. The pin mechanism itself is
#: exercised on stdlib symbols in tests; the stdlib is not a daily repo.
RUNTIME_PACKAGE_PREFIX = "renquant_"


def _runtime_root_from_current_env(umbrella: Path) -> Path | None:
    """RENQUANT_SUBREPO_ROOT, resolved the way the daily resolves it.

    Precedence mirrors `renquant_subrepo_root`: an already-exported
    RENQUANT_SUBREPO_ROOT wins (that is what sourcing current.env does);
    otherwise parse the umbrella's committed-on-machine
    `.subrepo_assembly/current.env` for the same export. Returns None when
    neither yields an existing directory — the sibling fallback then applies,
    exactly as in the shell helper.
    """
    exported = os.environ.get("RENQUANT_SUBREPO_ROOT")
    if exported:
        root = Path(exported)
        if not root.is_absolute():
            root = umbrella / root
        return root if root.is_dir() else None
    env_file = umbrella / ".subrepo_assembly" / "current.env"
    if not env_file.is_file():
        return None
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("export RENQUANT_SUBREPO_ROOT="):
            root = Path(line.split("=", 1)[1].strip().strip('"'))
            return root if root.is_dir() else None
    return None


def _under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (ValueError, OSError):
        return False


def _pythonpath_insertion_index() -> int:
    """The sys.path index PYTHONPATH entries occupy: before the first entry that
    belongs to the interpreter itself (stdlib, lib-dynload, site-packages).

    Everything the caller exported sits before that index and keeps
    precedence; everything the interpreter contributes — INCLUDING editable
    `.pth` entries, which `site` appends after site-packages — sits at or
    after it. Inserting there is what mirrors `export PYTHONPATH=<runtime>`.
    """
    prefixes = []
    for p in (sys.prefix, sys.base_prefix, sys.exec_prefix, sys.base_exec_prefix):
        try:
            prefixes.append(Path(p).resolve())
        except OSError:
            continue
    for i, entry in enumerate(sys.path):
        try:
            e = Path(entry or os.getcwd()).resolve()
        except OSError:
            continue
        if any(e == pre or pre in e.parents for pre in prefixes):
            return i
    return len(sys.path)


#: Set once per process by _ensure_daily_resolution(): {"root": Path,
#: "runtime_materialized": bool, "preloaded": {top-level renquant_* names
#: that were already in sys.modules before the roots were inserted}}.
_RESOLUTION: dict[str, Any] = {}


def _ensure_daily_resolution() -> dict[str, Any]:
    """Insert the daily's package roots exactly once, root chosen ONCE.

    The root choice is made a single time (runtime when materialized, else
    the siblings) — exactly like `renquant_subrepo_root` followed by
    `renquant_subrepo_pythonpath`, which emits only the chosen root's repo
    paths [codex on orch#773 round 2: a per-repo runtime→sibling fallback
    would MASK a missing or incomplete pinned checkout with a sibling
    import; a repo absent from the chosen root must stay loudly
    unresolvable]. Inserted at the PYTHONPATH position, not appended:
    anything the caller already exported keeps precedence, and the
    interpreter's own editable `.pth` siblings do NOT (2026-08-30 — appended
    roots lost to those `.pth` entries for four of the eight packages).
    Idempotent: a second call re-inserts nothing and returns the same record.
    """
    if _RESOLUTION:
        return _RESOLUTION
    runtime = _runtime_root_from_current_env(_UMBRELLA)
    root = runtime if runtime is not None else (
        Path(__file__).resolve().parent.parent.parent)
    preloaded = sorted(
        name for name in sys.modules
        if name.startswith(RUNTIME_PACKAGE_PREFIX) and "." not in name)
    at = _pythonpath_insertion_index()
    for repo in _DAILY_REPOS:
        base = root / repo
        for candidate in (base / "src", base):
            if candidate.is_dir():
                p = str(candidate)
                if p not in sys.path:
                    sys.path.insert(at, p)
                    at += 1
                break
    _RESOLUTION.update({
        "root": root,
        "runtime_materialized": runtime is not None,
        "preloaded": preloaded,
    })
    return _RESOLUTION


def resolution_summary() -> str:
    """One human line naming WHICH tree the verdict is about."""
    r = _ensure_daily_resolution()
    kind = "pinned runtime" if r["runtime_materialized"] else (
        "sibling FALLBACK root (no pinned runtime materialized)")
    return f"resolved against the {kind} {r['root']}"


#: The symbols to pin, as (module, attribute). Kept as data next to the resolver so
#: adding one is a one-line reviewed change. Each entry is a name THIS repo imports.
PINNED_SYMBOLS: tuple[tuple[str, str], ...] = (
    ("renquant_common", "load_scorer"),
    ("renquant_common", "validate_live_run_bundle"),
    ("renquant_common", "Pipeline"),
    ("renquant_common", "Task"),
    ("renquant_common.model_fingerprint", "model_content_sha256"),
    ("renquant_common.config_consistency", "fingerprint_config"),
    ("renquant_common.market_calendar", "last_completed_session"),
    ("renquant_common.notify", "send"),
    ("renquant_artifacts", "hash_jsonable"),
    ("renquant_execution", "get_broker"),
    ("renquant_execution", "BrokerExecutionPipeline"),
    ("renquant_model_gbdt", "PanelGbdtTrainingPipeline"),
    ("renquant_backtesting", "BacktestPipeline"),
    ("renquant_base_data.loaders.data", "fetch_ohlcv_incremental"),
)


def _package_relative(path: str | None) -> str | None:
    """Strip everything above the top-level package directory.

    Absolute paths differ between the dev checkout and the run checkout
    (`renquant-orchestrator` vs `renquant-orchestrator-run`), so pinning them would
    make the check fail for the wrong reason on the machine that matters. What must
    be stable is the path *inside* the package.
    """
    if not path:
        return None
    parts = Path(path).resolve().parts
    for i in range(len(parts) - 1, -1, -1):
        if parts[i] == "src" and i + 1 < len(parts):
            return "/".join(parts[i + 1:])
    # No src/ layout: fall back to the last three components, which is still more
    # stable than an absolute path and is reported as-is rather than silently.
    return "/".join(parts[-3:])


#: Fields of a resolve() record that name ABSOLUTE paths. They are what the
#: root assertion reads; emit() strips them so the committed pin stays
#: checkout-independent.
_ABSOLUTE_FIELDS: tuple[str, ...] = ("abs_source_file", "abs_module_file")


def resolve(module_name: str, attr: str) -> dict[str, Any]:
    """Where does `module_name.attr` actually come from? Never raises."""
    out: dict[str, Any] = {"module": module_name, "attr": attr}
    try:
        mod = importlib.import_module(module_name)
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"import failed: {type(exc).__name__}: {exc}"
        return out
    if not hasattr(mod, attr):
        out["error"] = f"{module_name} has no attribute {attr!r}"
        return out
    obj = getattr(mod, attr)
    # __module__ is where the object was DEFINED, not where it was re-exported
    # from. That difference is the entire point: a package's __init__ can map a
    # documented name onto a different implementation than the one a reader finds.
    out["defined_in"] = getattr(obj, "__module__", None)
    try:
        abs_source = inspect.getsourcefile(obj)
    except Exception:  # noqa: BLE001
        abs_source = None
    out["source_file"] = _package_relative(abs_source)
    out["abs_source_file"] = str(Path(abs_source).resolve()) if abs_source else None
    mod_file = getattr(mod, "__file__", None)
    out["abs_module_file"] = str(Path(mod_file).resolve()) if mod_file else None
    out["kind"] = type(obj).__name__
    return out


def _unpinned_path_problem(key: str, got: dict[str, Any]) -> str | None:
    """`resolved_from_unpinned_path` when a renquant_* symbol's code or its
    import module lies outside the chosen root. None otherwise, and None for
    modules outside the runtime scope (stdlib test stand-ins)."""
    if not str(got.get("module", "")).startswith(RUNTIME_PACKAGE_PREFIX):
        return None
    r = _ensure_daily_resolution()
    root: Path = r["root"]
    outside = [got[f] for f in _ABSOLUTE_FIELDS
               if got.get(f) and not _under(Path(got[f]), root)]
    if not outside:
        return None
    top = str(got.get("module", "")).split(".")[0]
    cached = (f" — {top} was already imported before the pinned resolution was "
              f"established (a cached module; establish the resolution first)"
              if top in r["preloaded"] else "")
    kind = "pinned runtime" if r["runtime_materialized"] else "sibling fallback root"
    return (f"{key}: resolved_from_unpinned_path — {', '.join(sorted(set(outside)))} "
            f"is not under the {kind} {root}; an editable .pth / sibling checkout / "
            f"caller PYTHONPATH is shadowing the pin, so this process is not "
            f"measuring the tree the daily runs{cached}")


def emit() -> dict[str, Any]:
    _ensure_daily_resolution()
    symbols: dict[str, Any] = {}
    for m, a in PINNED_SYMBOLS:
        rec = resolve(m, a)
        for f in _ABSOLUTE_FIELDS:
            rec.pop(f, None)
        symbols[f"{m}.{a}"] = rec
    return {
        "schema_version": 1,
        "_comment": (
            "GOAL-3 #623: which copy of each imported public symbol actually runs. "
            "Generated by ops/import_resolution_check.py --emit and committed via a "
            "reviewed PR, never auto-written. A drift here means a public name now "
            "resolves to a different implementation than the one this repo was "
            "reviewed against."
        ),
        "symbols": symbols,
    }


def verify(pins: dict[str, Any]) -> list[str]:
    """Compare live resolution against the pins. Returns problem lines.

    Establishes the daily's resolution itself first (idempotent), so a caller
    that imports this module and calls verify() directly — the drift scan —
    measures the same tree as the CLI.
    """
    _ensure_daily_resolution()
    problems: list[str] = []
    pinned = pins.get("symbols") or {}
    if not pinned:
        return ["pin file contains no symbols — cannot verify anything"]

    live = {f"{m}.{a}": resolve(m, a) for m, a in PINNED_SYMBOLS}

    # A symbol dropped from PINNED_SYMBOLS while still in the pin file, or added
    # without re-emitting, both mean the pin no longer describes the code. Neither
    # may pass silently: an unchecked symbol is indistinguishable from a clean one.
    for key in sorted(set(pinned) - set(live)):
        problems.append(
            f"{key}: pinned but no longer in PINNED_SYMBOLS — re-emit the pin file "
            f"so the record matches what is actually checked")
    for key in sorted(set(live) - set(pinned)):
        problems.append(
            f"{key}: checked but absent from the pin file — run --emit and commit, "
            f"otherwise this symbol has no baseline")

    for key in sorted(set(pinned) & set(live)):
        want, got = pinned[key], live[key]
        if got.get("error"):
            problems.append(f"{key}: unresolvable ({got['error']})")
            continue
        if want.get("error"):
            problems.append(
                f"{key}: the pin itself records an error ({want['error']}) — it was "
                f"emitted from a broken environment and is not a valid baseline")
            continue
        for field in ("defined_in", "source_file"):
            if want.get(field) != got.get(field):
                problems.append(
                    f"{key}: {field} drifted — reviewed against {want.get(field)!r}, "
                    f"now resolves to {got.get(field)!r}. Which copy runs has "
                    f"CHANGED; confirm the new one is intended before re-pinning")
        unpinned = _unpinned_path_problem(key, got)
        if unpinned:
            problems.append(unpinned)
    return problems


def main(argv: list[str] | None = None) -> int:
    _ensure_daily_resolution()
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--emit", action="store_true",
                    help="print fresh pins for review (never writes)")
    ap.add_argument("--pins", type=Path, default=PINS)
    args = ap.parse_args(argv)

    if args.emit:
        print(json.dumps(emit(), indent=2, sort_keys=True))
        return 0

    if not args.pins.exists():
        print(f"FATAL: pin file missing at {args.pins} — run --emit and commit it",
              file=sys.stderr)
        return 2
    try:
        pins = json.loads(args.pins.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"FATAL: pin file unreadable: {type(exc).__name__}: {exc}",
              file=sys.stderr)
        return 2

    problems = verify(pins)
    if problems:
        print("\n".join(problems))
        print(f"\nimport-resolution: {len(problems)} problem(s) ({resolution_summary()})")
        return 1
    print(f"import-resolution OK — {len(PINNED_SYMBOLS)} symbols resolve as reviewed "
          f"({resolution_summary()})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
