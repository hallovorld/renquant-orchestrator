#!/usr/bin/env python3
"""R0 twin-parity tripwires (#454 remediation stage R0 — "tripwires first").

Mechanical drift alarms for the KNOWN duplicated-contract instances catalogued
by the 2026-07 architecture audit (design:
``doc/design/2026-07-10-architecture-compliance-registry.md`` T3 + R0 + §5.1;
evidence: ``doc/research/evidence/arch_audit_2026_07/`` audit C §1/§3, audit B
§3/§4).  Zero behavior change — this script only makes silent drift VISIBLE:

1. Umbrella ``live/`` <-> renquant-execution twins (audit C §1.1, C1-a).
   - Byte-identical pairs (``alerts.py``, ``ibkr_broker.py``): assert byte
     equality.  A lockstep change to both sides preserves parity and passes.
   - Known-diverged pairs (``broker.py``, ``alpaca_broker.py``,
     ``paper_broker.py``, ``broker_readonly.py``/``readonly_broker.py``):
     the CURRENT divergence is pinned by sha256 of each side in the
     checked-in manifest.  If EITHER side changes without a manifest update,
     the check fails — updating the manifest is the deliberate review act.
2. ``MIN_FRACTIONAL_NOTIONAL_USD`` literal parity (audit C §1.3, C1-c):
   execution ``broker.py`` <-> pipeline ``kernel/sizing.py`` parsed via AST
   and asserted equal (and equal to the manifest pin).
3. ``compute_parent_intent_id`` duplicate pin (audit B §3): the function
   source on each side (pipeline ``intraday_decisioning.py``, execution
   ``order_state_machine.py``) is sha256-pinned in the manifest, plus a
   cross-side equality assertion on the behavior-critical ``_FIELD_SEP``
   module constant both implementations hash with.
4. Tax-convention trio pin (audit B §4, pipeline-internal): the three
   divergent tax families' key constants are snapshot in the manifest
   (rotation ``tax_drag`` defaults 0.50/0.32; QP bridge 0.30/0.15;
   selection flat 0.30).  R6 unifies; this pin makes further silent drift
   fail in the meantime.

Runner semantics / KNOWN LIMITATION
-----------------------------------
Sibling repos are resolved per the RENQUANT_REPOS.md sibling-checkout
convention (every subrepo checked out under one common parent directory,
same as ``mirror_drift_inventory.py``): ``<parent-of-this-repo>/<repo>``,
overridable via ``RENQUANT_SIBLINGS_ROOT`` or ``--siblings-root``.  When a
required sibling is absent, the affected checks SKIP with a loud message
and exit 0 — they do NOT silently pass as green assertions.  In practice:
orchestrator GitHub CI (ci.yml) checks out renquant-execution and
renquant-pipeline @ main, so the constant/function/tax pins ARE enforced
at merge time — but the umbrella ``RenQuant`` is NOT checked out there, so
the ``live/``-twin checks (the audit's HIGH-latent item) skip in CI and
only RUN via ``make test`` on the deploy machine.  That is exactly where
that drift matters — the live path executes from the deploy machine's
umbrella checkout ("merged is not deployed").  CI green does NOT certify
umbrella-twin parity; the deploy machine's ``make test`` is authoritative.
A CI-vs-deploy-machine disagreement (siblings @ main vs @ deployed pin) is
the T1 evidence-vs-live lag made visible — sync the pins, don't loosen
the pin.

Usage:
  python scripts/check_twin_parity.py                 # run checks
  python scripts/check_twin_parity.py --strict-missing  # SKIP -> FAIL
  python scripts/check_twin_parity.py --write-manifest  # re-pin (review act)

Exit codes: 0 = all checks pass or skip; 1 = at least one FAIL.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_DEFAULT = _REPO_ROOT / "data" / "twin_parity_manifest.json"

# Sibling-repo layout convention (per RENQUANT_REPOS.md, same derivation as
# scripts/mirror_drift_inventory.py): every subrepo is checked out as a
# sibling of this repo under a common parent directory.
_SIBLINGS_ROOT_ENV = "RENQUANT_SIBLINGS_ROOT"

#: repo key -> sibling directory name
REPO_DIRS = {
    "umbrella": "RenQuant",
    "execution": "renquant-execution",
    "pipeline": "renquant-pipeline",
}

# ---------------------------------------------------------------------------
# Twin/constant SPEC — what is checked lives here (code, reviewed like code);
# the pinned STATE (hashes/values) lives in the manifest.
# ---------------------------------------------------------------------------

#: (umbrella-relative, execution-relative) pairs asserted byte-identical
#: (audit C §1.1: identical today "only by luck" — this makes it a contract).
BYTE_IDENTICAL_TWINS = [
    ("live/alerts.py", "src/renquant_execution/alerts.py"),
    ("live/ibkr_broker.py", "src/renquant_execution/ibkr_broker.py"),
]

#: (name, umbrella-relative, execution-relative) KNOWN-diverged pairs whose
#: current per-side content is sha256-pinned in the manifest.
DIVERGED_TWINS = [
    ("broker", "live/broker.py", "src/renquant_execution/broker.py"),
    ("alpaca_broker", "live/alpaca_broker.py", "src/renquant_execution/alpaca_broker.py"),
    ("paper_broker", "live/paper_broker.py", "src/renquant_execution/paper_broker.py"),
    ("readonly_broker", "live/broker_readonly.py", "src/renquant_execution/readonly_broker.py"),
]

_EXEC_BROKER = "src/renquant_execution/broker.py"
_PIPE_SIZING = "src/renquant_pipeline/kernel/sizing.py"
_PIPE_INTRADAY = "src/renquant_pipeline/intraday_decisioning.py"
_EXEC_OSM = "src/renquant_execution/order_state_machine.py"
_PIPE_ROTATION = "src/renquant_pipeline/kernel/rotation.py"
_PIPE_QP_TASKS = "src/renquant_pipeline/kernel/portfolio_qp/tasks.py"
_PIPE_SELECTION = "src/renquant_pipeline/kernel/selection.py"

#: Tax-convention trio (audit B §4).  Each entry: manifest key ->
#: (repo key, relative path, extractor kind, extractor arg).
#: "cfg_get" collects every ``<anything>.get("<key>", <number>)`` default in
#: the file; "param_default" collects every function-signature default for a
#: parameter named <key>.  Counts are pinned too: a NEW hand-copied call site
#: (even with today's value) is exactly the duplication class the audit
#: flags, so it must also surface for review.
TAX_PINS = {
    "rotation_short_term_rate": (_PIPE_ROTATION, "cfg_get", "short_term_rate"),
    "rotation_long_term_rate": (_PIPE_ROTATION, "cfg_get", "long_term_rate"),
    "qp_tax_rate_st": (_PIPE_QP_TASKS, "cfg_get", "qp_tax_rate_st"),
    "qp_tax_rate_lt": (_PIPE_QP_TASKS, "cfg_get", "qp_tax_rate_lt"),
    "selection_tax_rate": (_PIPE_SELECTION, "param_default", "tax_rate"),
}

TAX_COMMENT = (
    "R6 unifies; this pin makes further silent drift fail. Three divergent "
    "tax families coexist in the pipeline kernel (audit B SS4): rotation "
    "tax_drag ST/LT cliff 0.50/0.32, QP Brown-Smith bridge 0.30/0.15, "
    "selection flat 0.30 — the same sell is costed differently per leg."
)


# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------

def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def module_constant(path: Path, name: str):
    """Return the literal value of a module-level ``NAME = <literal>``."""
    tree = ast.parse(path.read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return ast.literal_eval(node.value)
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == name and node.value is not None:
                return ast.literal_eval(node.value)
    raise LookupError(f"module-level constant {name!r} not found in {path}")


def function_source_sha(path: Path, func_name: str) -> str:
    """sha256 of the source segment of the first module-level or nested
    function named *func_name* (deterministic: ast.walk order, first hit)."""
    src = path.read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
            segment = ast.get_source_segment(src, node)
            if segment is None:  # pragma: no cover — py>=3.8 with full source
                raise LookupError(f"source segment unavailable for {func_name} in {path}")
            return hashlib.sha256(segment.encode("utf-8")).hexdigest()
    raise LookupError(f"function {func_name!r} not found in {path}")


_CFG_GET_RE_TMPL = r"\.get\(\s*[\"']{key}[\"']\s*,\s*([0-9]*\.?[0-9]+)\s*\)"


def cfg_get_defaults(path: Path, key: str) -> list[float]:
    """Every numeric default of ``<expr>.get("<key>", <number>)`` in the file."""
    pattern = re.compile(_CFG_GET_RE_TMPL.format(key=re.escape(key)))
    return [float(m.group(1)) for m in pattern.finditer(path.read_text())]


def param_defaults(path: Path, param_name: str) -> list[float]:
    """Every numeric signature default for a parameter named *param_name*."""
    tree = ast.parse(path.read_text())
    found: list[float] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        args = node.args
        positional = args.posonlyargs + args.args
        for arg, default in zip(positional[len(positional) - len(args.defaults):], args.defaults):
            if arg.arg == param_name and isinstance(default, ast.Constant) and isinstance(default.value, (int, float)):
                found.append(float(default.value))
        for arg, default in zip(args.kwonlyargs, args.kw_defaults):
            if default is not None and arg.arg == param_name and isinstance(default, ast.Constant) and isinstance(default.value, (int, float)):
                found.append(float(default.value))
    return found


def _tax_snapshot(pin_key: str, pipeline_root: Path) -> dict:
    rel, kind, arg = TAX_PINS[pin_key]
    path = pipeline_root / rel
    values = cfg_get_defaults(path, arg) if kind == "cfg_get" else param_defaults(path, arg)
    return {"values": sorted(set(values)), "count": len(values)}


# ---------------------------------------------------------------------------
# Repo resolution
# ---------------------------------------------------------------------------

def resolve_repos(siblings_root: Path | None = None) -> dict[str, Path | None]:
    """Map repo key -> checkout Path, or None when the sibling is absent."""
    if siblings_root is None:
        env = os.environ.get(_SIBLINGS_ROOT_ENV)
        siblings_root = Path(env) if env else _REPO_ROOT.parent
    resolved: dict[str, Path | None] = {}
    for key, dirname in REPO_DIRS.items():
        candidate = siblings_root / dirname
        resolved[key] = candidate if candidate.is_dir() else None
    return resolved


# ---------------------------------------------------------------------------
# Manifest build (the deliberate review act)
# ---------------------------------------------------------------------------

def build_manifest(repos: dict[str, Path | None]) -> dict:
    missing = [k for k, v in repos.items() if v is None]
    if missing:
        raise RuntimeError(f"cannot build manifest — missing sibling repos: {missing}")
    umbrella, execution, pipeline = repos["umbrella"], repos["execution"], repos["pipeline"]
    assert umbrella and execution and pipeline
    manifest: dict = {
        "comment": (
            "R0 twin-parity pins (#454). Pinned STATE only — the checked "
            "twin/constant SPEC lives in scripts/check_twin_parity.py. "
            "Updating this file is the deliberate review act that "
            "acknowledges a twin-side change; regenerate with "
            "`python scripts/check_twin_parity.py --write-manifest` and "
            "review the diff."
        ),
        "diverged_twins": {
            name: {
                "umbrella_path": umb_rel,
                "execution_path": exe_rel,
                "umbrella_sha256": sha256_file(umbrella / umb_rel),
                "execution_sha256": sha256_file(execution / exe_rel),
            }
            for name, umb_rel, exe_rel in DIVERGED_TWINS
        },
        "constants": {
            "MIN_FRACTIONAL_NOTIONAL_USD": module_constant(execution / _EXEC_BROKER, "MIN_FRACTIONAL_NOTIONAL_USD"),
        },
        "function_pins": {
            "compute_parent_intent_id": {
                "pipeline_path": _PIPE_INTRADAY,
                "execution_path": _EXEC_OSM,
                "pipeline_sha256": function_source_sha(pipeline / _PIPE_INTRADAY, "compute_parent_intent_id"),
                "execution_sha256": function_source_sha(execution / _EXEC_OSM, "compute_parent_intent_id"),
            },
        },
        "tax_conventions": {
            "comment": TAX_COMMENT,
            **{key: _tax_snapshot(key, pipeline) for key in TAX_PINS},
        },
    }
    return manifest


def load_manifest(path: Path) -> dict:
    with open(path) as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

@dataclass
class CheckResult:
    name: str
    status: str  # "PASS" | "FAIL" | "SKIP"
    detail: str = ""


def _skip(name: str, missing: list[str]) -> CheckResult:
    return CheckResult(
        name,
        "SKIP",
        f"sibling repo(s) {missing} not found — twin parity NOT verified here. "
        "This check only runs where the sibling checkouts exist (the deploy "
        "machine); CI green does NOT certify parity.",
    )


def check_byte_identical_twins(repos: dict[str, Path | None]) -> list[CheckResult]:
    umbrella, execution = repos["umbrella"], repos["execution"]
    missing = [k for k in ("umbrella", "execution") if repos[k] is None]
    if missing:
        return [_skip("byte_identical_twins", missing)]
    assert umbrella and execution
    results = []
    for umb_rel, exe_rel in BYTE_IDENTICAL_TWINS:
        name = f"byte_identical:{Path(umb_rel).name}"
        umb, exe = umbrella / umb_rel, execution / exe_rel
        if not umb.is_file() or not exe.is_file():
            results.append(CheckResult(name, "FAIL", f"twin file missing: {umb if not umb.is_file() else exe}"))
        elif umb.read_bytes() == exe.read_bytes():
            results.append(CheckResult(name, "PASS", f"{umb_rel} == {exe_rel} (byte-identical)"))
        else:
            results.append(CheckResult(
                name, "FAIL",
                f"{umb} and {exe} have DIVERGED (were byte-identical). A fix "
                "landed on one side may be missing from the stack that "
                "actually trades (audit C1-a class, cf. the 2026-06 "
                "self._config incident). Land the change on BOTH sides, or "
                "reclassify the pair as diverged in scripts/check_twin_parity.py "
                "via a reviewed PR.",
            ))
    return results


def check_diverged_twins(repos: dict[str, Path | None], manifest: dict) -> list[CheckResult]:
    umbrella, execution = repos["umbrella"], repos["execution"]
    missing = [k for k in ("umbrella", "execution") if repos[k] is None]
    if missing:
        return [_skip("diverged_twins", missing)]
    assert umbrella and execution
    pins = manifest.get("diverged_twins", {})
    results = []
    for name, umb_rel, exe_rel in DIVERGED_TWINS:
        cname = f"diverged_pin:{name}"
        pin = pins.get(name)
        if pin is None:
            results.append(CheckResult(cname, "FAIL", f"no manifest pin for diverged twin {name!r} — regenerate the manifest"))
            continue
        drifted = []
        for side, root, rel, key in (
            ("umbrella", umbrella, umb_rel, "umbrella_sha256"),
            ("execution", execution, exe_rel, "execution_sha256"),
        ):
            path = root / rel
            if not path.is_file():
                drifted.append(f"{side} file missing: {path}")
                continue
            actual = sha256_file(path)
            if actual != pin[key]:
                drifted.append(f"{side} side changed: {path} sha256 {actual[:16]}… != pinned {pin[key][:16]}…")
        if drifted:
            results.append(CheckResult(
                cname, "FAIL",
                "; ".join(drifted) + " — twin drift tripwire (#454 R0). If the "
                "change is deliberate and reviewed on both stacks, re-pin via "
                "`python scripts/check_twin_parity.py --write-manifest` in the "
                "same PR.",
            ))
        else:
            results.append(CheckResult(cname, "PASS", f"{umb_rel} / {exe_rel} match their pinned divergence"))
    return results


def check_min_fractional_notional(repos: dict[str, Path | None], manifest: dict) -> list[CheckResult]:
    execution, pipeline = repos["execution"], repos["pipeline"]
    missing = [k for k in ("execution", "pipeline") if repos[k] is None]
    if missing:
        return [_skip("min_fractional_notional", missing)]
    assert execution and pipeline
    name = "constant:MIN_FRACTIONAL_NOTIONAL_USD"
    try:
        exe_val = module_constant(execution / _EXEC_BROKER, "MIN_FRACTIONAL_NOTIONAL_USD")
        pipe_val = module_constant(pipeline / _PIPE_SIZING, "MIN_FRACTIONAL_NOTIONAL_USD")
    except (LookupError, OSError, SyntaxError) as exc:
        return [CheckResult(name, "FAIL", f"could not parse constant: {exc}")]
    pinned = manifest.get("constants", {}).get("MIN_FRACTIONAL_NOTIONAL_USD")
    if exe_val != pipe_val:
        return [CheckResult(
            name, "FAIL",
            f"literal parity broken: execution broker.py={exe_val} != pipeline "
            f"kernel/sizing.py={pipe_val} (audit C1-c — comment-sync only, this "
            "is the fingerprint-triple-impl failure shape). Align both sides.",
        )]
    if pinned is not None and exe_val != pinned:
        return [CheckResult(
            name, "FAIL",
            f"both sides moved to {exe_val} but the manifest pins {pinned} — "
            "re-pin via --write-manifest in the same reviewed PR.",
        )]
    return [CheckResult(name, "PASS", f"execution == pipeline == {exe_val}")]


def check_parent_intent_id(repos: dict[str, Path | None], manifest: dict) -> list[CheckResult]:
    execution, pipeline = repos["execution"], repos["pipeline"]
    missing = [k for k in ("execution", "pipeline") if repos[k] is None]
    if missing:
        return [_skip("compute_parent_intent_id", missing)]
    assert execution and pipeline
    results = []
    name = "function_pin:compute_parent_intent_id"
    pin = manifest.get("function_pins", {}).get("compute_parent_intent_id")
    if pin is None:
        return [CheckResult(name, "FAIL", "no manifest pin — regenerate the manifest")]
    try:
        pipe_sha = function_source_sha(pipeline / _PIPE_INTRADAY, "compute_parent_intent_id")
        exe_sha = function_source_sha(execution / _EXEC_OSM, "compute_parent_intent_id")
    except (LookupError, OSError, SyntaxError) as exc:
        return [CheckResult(name, "FAIL", f"could not extract function source: {exc}")]
    drifted = []
    if pipe_sha != pin["pipeline_sha256"]:
        drifted.append(f"pipeline {_PIPE_INTRADAY} function source changed")
    if exe_sha != pin["execution_sha256"]:
        drifted.append(f"execution {_EXEC_OSM} function source changed")
    if drifted:
        results.append(CheckResult(
            name, "FAIL",
            "; ".join(drifted) + " — the two copies are a BYTE-LOCKSTEP "
            "behavior contract (audit B SS3): any change must land in both "
            "repos (or move the one implementation to renquant-common), then "
            "re-pin via --write-manifest.",
        ))
    else:
        results.append(CheckResult(name, "PASS", "both function sources match their pins"))
    # _FIELD_SEP is hashed by both implementations — cross-side equality is
    # part of the behavior contract even though the docstrings diverge.
    sep_name = "function_pin:_FIELD_SEP"
    try:
        pipe_sep = module_constant(pipeline / _PIPE_INTRADAY, "_FIELD_SEP")
        exe_sep = module_constant(execution / _EXEC_OSM, "_FIELD_SEP")
    except (LookupError, OSError, SyntaxError) as exc:
        results.append(CheckResult(sep_name, "FAIL", f"could not parse _FIELD_SEP: {exc}"))
        return results
    if pipe_sep != exe_sep:
        results.append(CheckResult(
            sep_name, "FAIL",
            f"_FIELD_SEP diverged: pipeline={pipe_sep!r} != execution={exe_sep!r} "
            "— parent intent ids would silently stop matching across repos.",
        ))
    else:
        results.append(CheckResult(sep_name, "PASS", f"_FIELD_SEP identical on both sides ({pipe_sep!r})"))
    return results


def check_tax_conventions(repos: dict[str, Path | None], manifest: dict) -> list[CheckResult]:
    pipeline = repos["pipeline"]
    if pipeline is None:
        return [_skip("tax_conventions", ["pipeline"])]
    pins = manifest.get("tax_conventions", {})
    results = []
    for key in TAX_PINS:
        name = f"tax_pin:{key}"
        pin = pins.get(key)
        if pin is None:
            results.append(CheckResult(name, "FAIL", f"no manifest pin for {key!r} — regenerate the manifest"))
            continue
        try:
            current = _tax_snapshot(key, pipeline)
        except (OSError, SyntaxError) as exc:
            results.append(CheckResult(name, "FAIL", f"could not extract {key}: {exc}"))
            continue
        if current["values"] != pin["values"] or current["count"] != pin["count"]:
            rel, _, arg = TAX_PINS[key]
            results.append(CheckResult(
                name, "FAIL",
                f"{rel} {arg!r} defaults changed: values {current['values']} "
                f"(x{current['count']}) != pinned {pin['values']} (x{pin['count']}) "
                "— tax-convention tripwire (audit B SS4; R6 unifies). A new or "
                "changed hand-copied default needs review; if deliberate, "
                "re-pin via --write-manifest in the same PR.",
            ))
        else:
            results.append(CheckResult(name, "PASS", f"{key}: values {pin['values']} (x{pin['count']})"))
    return results


def run_checks(repos: dict[str, Path | None], manifest: dict) -> list[CheckResult]:
    results: list[CheckResult] = []
    results += check_byte_identical_twins(repos)
    results += check_diverged_twins(repos, manifest)
    results += check_min_fractional_notional(repos, manifest)
    results += check_parent_intent_id(repos, manifest)
    results += check_tax_conventions(repos, manifest)
    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--manifest", type=Path, default=MANIFEST_DEFAULT)
    parser.add_argument("--siblings-root", type=Path, default=None,
                        help=f"parent dir of sibling checkouts (default: parent of this repo, or ${_SIBLINGS_ROOT_ENV})")
    parser.add_argument("--write-manifest", action="store_true",
                        help="re-pin the manifest to the CURRENT twin state (the deliberate review act; diff it in the PR)")
    parser.add_argument("--strict-missing", action="store_true",
                        help="treat missing sibling repos as FAIL instead of SKIP (for the deploy machine)")
    args = parser.parse_args(argv)

    repos = resolve_repos(args.siblings_root)

    if args.write_manifest:
        manifest = build_manifest(repos)
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        print(f"wrote {args.manifest}")
        return 0

    if not args.manifest.is_file():
        print(f"FAIL: manifest not found at {args.manifest} — run --write-manifest and commit it")
        return 1
    manifest = load_manifest(args.manifest)
    results = run_checks(repos, manifest)

    width = max(len(r.name) for r in results)
    for r in results:
        print(f"[{r.status}] {r.name:<{width}}  {r.detail}")
    fails = [r for r in results if r.status == "FAIL"]
    skips = [r for r in results if r.status == "SKIP"]
    if skips:
        print(f"\nSKIPPED {len(skips)} check group(s) — twin parity NOT verified in this environment.")
        if args.strict_missing:
            print("--strict-missing: treating SKIP as FAIL.")
            fails += skips
    print(f"\ntwin-parity: {sum(r.status == 'PASS' for r in results)} pass, {len(fails)} fail, {len(skips)} skip")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
