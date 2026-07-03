#!/usr/bin/env python3
"""Thin orchestrator driver: regenerate the durable OOS pick table (S8, 2nd half).

Per the H2 execution roadmap (#231) Term EXEC row S8 and the direction-decision
doc `doc/design/2026-06-28-renquant105-direction-decision.md` §4: Track A's
evidence base is a durable, regeneratable per-(date, name) OOS pick table for
the prod GBDT walk-forward manifest. The SCORING and the export CONTRACT live
in renquant-backtesting (backtesting #59, branch `feat/sanity-dump-predictions`:
`analyze_manifest_sanity_placebo --dump-predictions` + the owning contract
module `renquant_backtesting/analysis/pick_table.py`). This driver is
deliberately THIN — it composes the invocation, enforces the gates, and never
reimplements scoring, deciles, hashing, or the sidecar.

RUN GATE (do not real-run until backtesting #59 is merged): the contract this
driver pins to lives on an unmerged review branch and could still change. The
gate is mechanical, not aspirational — a real run preflights the backtesting
checkout for the exact contract surface (`build_pick_table_manifest`,
`verify_pick_table`, `canonical_table_content_hash`, `default_sidecar_path`,
and the `dump_predictions` parameter of `analyze_manifest`) and refuses to
score if any of it is missing. `--dry-run` prints the exact commands/paths
without executing anything and works without #59.

What a real (non-dry) run does, in order:
  1. refuses any output not strictly under `<umbrella>/data/exp/` (fail closed,
     NO override flag — the umbrella tree's canonical `data/` and `artifacts/`
     paths are production inputs; see PROD_PATH_RULES in agent_workflows.py);
  2. preflights the #59 contract surface in the backtesting checkout;
  3. invokes backtesting's `analyze_manifest_sanity_placebo` with
     `--dump-predictions` against the prod manifest
     (`walkforward_manifest_gbdt_prod_recipe_v2.json`), writing to a STAGING
     path (`<stem>__staging.parquet`) so the final exp path and the committed
     RenQuant#430 sidecar are never clobbered by a run that then fails a gate;
  4. FAITHFULNESS GATE — reads the sanity gate's own JSON output and requires
     the regenerated `genuine_ic` (`aligned_real_60_ic - placebo_60_ic`, the
     same decomposition the WF gate stamps) to reproduce the committed
     genuine_ic to +/-0.001 (the A1 bar: 0.0415 vs 0.0417). Hard-fails
     otherwise: staging files are left for forensics, the final path is not
     touched, exit 1. NOTE (#431): this bar is currently DISPUTED — RenQuant#431's
     leak-controlled rerun disagrees with the cited committed figure. A hard
     FAIL here is therefore a legitimate, expected outcome until #431's
     reconciliation protocol is frozen and executed; the driver failing closed
     is the correct behavior, not a bug.
  5. ROW-COUNT SANITY — sidecar counts must match the committed shape
     (508 dates exactly; ~147,066 rows within tolerance);
  6. promotes staging -> final (parquet + sidecar), then re-verifies the FINAL
     artifact via the contract's own `verify_pick_table` (reload + canonical
     content-hash check) in the backtesting environment;
  7. reports (non-fatal) whether the fresh canonical content hash reproduces
     the anchor stamped in the pre-existing committed sidecar, if one exists.

Exit codes: 0 = all gates passed; 1 = a gate failed (faithfulness / counts /
post-write verification); 2 = could not run (path refusal, missing inputs,
missing #59 contract, subprocess failure).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Sequence

DEFAULT_UMBRELLA_ROOT = Path("/Users/renhao/git/github/RenQuant")
DEFAULT_BACKTESTING_ROOT = Path("/Users/renhao/git/github/renquant-backtesting")

#: Umbrella-relative defaults (the umbrella tree is READ-ONLY input except for
#: the sanctioned experiment area data/exp/).
REL_MANIFEST = "backtesting/renquant_104/artifacts/sim/walkforward_manifest_gbdt_prod_recipe_v2.json"
REL_ARTIFACT = (
    "backtesting/renquant_104/artifacts/walkforward_gbdt_prod_recipe_v2/2026-03-02/panel-ltr.json"
)
REL_STRATEGY_DIR = "backtesting/renquant_104"
REL_OUTPUT = "data/exp/oos_pick_table_recipe_v2.parquet"
REL_DIAGNOSTICS_DIR = "data/exp/oos_pick_table_recipe_v2_sanity"

ANALYZER_MODULE = "renquant_backtesting.analysis.analyze_manifest_sanity_placebo"
CONTRACT_MODULE = "renquant_backtesting.analysis.pick_table"
#: The exact #59 contract surface a real run preflights for (branch
#: feat/sanity-dump-predictions of renquant-backtesting).
CONTRACT_NAMES = (
    "build_pick_table_manifest",
    "verify_pick_table",
    "canonical_table_content_hash",
    "default_sidecar_path",
)

LABEL = "fwd_60d_excess"

#: The committed genuine_ic the regeneration must reproduce (the A1 bar).
#: Provenance: `metadata.wf_gate_metadata.model_placebo_profile.pooled.1x
#: .genuine_ic` stamped on the prod GBDT bundle
#: (artifacts/prod/panel-ltr.alpha158_fund.weekly_*.staging.json), i.e. the WF
#: gate's own aligned_real - placebo decomposition at the 1x (60d) shift; the
#: A1 audit reproduced it as 0.0415 vs this committed 0.0417.
#: DISPUTED per RenQuant#431 — see module docstring step 4.
COMMITTED_GENUINE_IC = 0.041680989995517316
IC_TOLERANCE = 0.001

#: Committed table shape (RenQuant#430 sidecar: data/exp/
#: oos_pick_table_recipe_v2.manifest.json — 147,066 rows / 508 dates).
EXPECTED_DATES = 508
EXPECTED_ROWS = 147066
ROWS_TOLERANCE_PCT = 1.0

_PREFLIGHT_SNIPPET = """
import inspect, json, sys
missing = []
try:
    import renquant_backtesting.analysis.pick_table as pt
except Exception as exc:  # noqa: BLE001
    print(json.dumps({"ok": False, "error": f"contract module import failed: {exc}"}))
    sys.exit(1)
for name in __CONTRACT_NAMES__:
    if not callable(getattr(pt, name, None)):
        missing.append("pick_table." + name)
try:
    import renquant_backtesting.analysis.analyze_manifest_sanity_placebo as ap
    if "dump_predictions" not in inspect.signature(ap.analyze_manifest).parameters:
        missing.append("analyze_manifest(dump_predictions=...)")
except Exception as exc:  # noqa: BLE001
    print(json.dumps({"ok": False, "error": f"analyzer import failed: {exc}"}))
    sys.exit(1)
print(json.dumps({"ok": not missing, "missing": missing}))
sys.exit(0 if not missing else 1)
"""

_VERIFY_SNIPPET = """
import json, sys
from renquant_backtesting.analysis.pick_table import verify_pick_table
print(json.dumps(verify_pick_table(sys.argv[1], sys.argv[2])))
"""


class GateError(RuntimeError):
    """A regeneration gate failed — the fresh table must NOT be treated as
    durable evidence."""


class DriverSetupError(RuntimeError):
    """The driver could not (or refused to) run at all."""


@dataclass
class DriverConfig:
    umbrella_root: Path
    backtesting_root: Path
    manifest: Path
    artifact: Path
    strategy_dir: Path
    output: Path
    diagnostics_dir: Path
    label: str = LABEL
    committed_genuine_ic: float = COMMITTED_GENUINE_IC
    ic_tolerance: float = IC_TOLERANCE
    expected_dates: int = EXPECTED_DATES
    expected_rows: int = EXPECTED_ROWS
    rows_tolerance_pct: float = ROWS_TOLERANCE_PCT
    python: str = field(default_factory=lambda: sys.executable)
    dry_run: bool = False


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--umbrella-root", default=str(DEFAULT_UMBRELLA_ROOT),
                    help="umbrella RenQuant tree (inputs read-only; output under data/exp/)")
    ap.add_argument("--backtesting-root", default=str(DEFAULT_BACKTESTING_ROOT),
                    help="renquant-backtesting checkout providing the #59 contract")
    ap.add_argument("--manifest", default=None,
                    help=f"WF manifest JSON (default <umbrella>/{REL_MANIFEST})")
    ap.add_argument("--artifact", default=None,
                    help=f"reference bundle for feature_cols/label (default <umbrella>/{REL_ARTIFACT})")
    ap.add_argument("--output", default=None,
                    help=f"final pick-table parquet (default <umbrella>/{REL_OUTPUT}; "
                         "MUST be under <umbrella>/data/exp/)")
    ap.add_argument("--diagnostics-dir", default=None,
                    help=f"analyzer JSON/md output dir (default <umbrella>/{REL_DIAGNOSTICS_DIR}; "
                         "MUST be under <umbrella>/data/exp/)")
    ap.add_argument("--label", default=LABEL)
    ap.add_argument("--committed-genuine-ic", type=float, default=COMMITTED_GENUINE_IC,
                    help="committed genuine_ic the run must reproduce (A1 bar; disputed per #431)")
    ap.add_argument("--ic-tolerance", type=float, default=IC_TOLERANCE)
    ap.add_argument("--expected-dates", type=int, default=EXPECTED_DATES)
    ap.add_argument("--expected-rows", type=int, default=EXPECTED_ROWS)
    ap.add_argument("--rows-tolerance-pct", type=float, default=ROWS_TOLERANCE_PCT)
    ap.add_argument("--python", default=sys.executable,
                    help="interpreter with the backtesting deps (scipy/pandas/pyarrow)")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the exact commands/paths without executing (works without #59)")
    return ap.parse_args(argv)


def resolve_config(args: argparse.Namespace) -> DriverConfig:
    umbrella = Path(args.umbrella_root).expanduser().resolve()
    backtesting = Path(args.backtesting_root).expanduser().resolve()

    def _resolve(value: Optional[str], rel: str) -> Path:
        return Path(value).expanduser().resolve() if value else (umbrella / rel)

    return DriverConfig(
        umbrella_root=umbrella,
        backtesting_root=backtesting,
        manifest=_resolve(args.manifest, REL_MANIFEST),
        artifact=_resolve(args.artifact, REL_ARTIFACT),
        strategy_dir=umbrella / REL_STRATEGY_DIR,
        output=_resolve(args.output, REL_OUTPUT),
        diagnostics_dir=_resolve(args.diagnostics_dir, REL_DIAGNOSTICS_DIR),
        label=str(args.label),
        committed_genuine_ic=float(args.committed_genuine_ic),
        ic_tolerance=float(args.ic_tolerance),
        expected_dates=int(args.expected_dates),
        expected_rows=int(args.expected_rows),
        rows_tolerance_pct=float(args.rows_tolerance_pct),
        python=str(args.python),
        dry_run=bool(args.dry_run),
    )


def ensure_exp_path(path: Path, umbrella_root: Path) -> None:
    """Refuse any output that is not strictly under <umbrella>/data/exp/.

    The umbrella tree's canonical `data/` and `artifacts/` trees are LIVE
    production inputs (PROD_PATH_RULES; hard memory rule: never touch
    production inputs on the live tree). `data/exp/` is the one sanctioned
    experiment area — RenQuant#430 established it as the pick table's home.
    There is deliberately NO override flag on the orchestrator side; the
    driver also never passes the backtesting layer's --allow-production-path.
    """
    exp_root = (umbrella_root / "data" / "exp").resolve()
    resolved = Path(path).resolve()
    if exp_root != resolved and exp_root not in resolved.parents:
        raise DriverSetupError(
            f"refusing output path {resolved}: the pick table embeds REALIZED "
            f"forward labels and may only be written under {exp_root} "
            "(the sanctioned experiment area; no override)"
        )


def staging_paths(output: Path) -> tuple[Path, Path, Path]:
    """(staging_parquet, staging_sidecar, final_sidecar) for a final parquet.

    Staging uses `__staging` (no extra dot) so the contract's
    `default_sidecar_path` (`<stem>.manifest.json`, suffix-stripping) cannot
    collide with — and clobber — the committed final sidecar.
    """
    output = Path(output)
    staging_parquet = output.with_name(output.stem + "__staging.parquet")
    staging_sidecar = output.with_name(output.stem + "__staging.manifest.json")
    final_sidecar = output.with_name(output.stem + ".manifest.json")
    return staging_parquet, staging_sidecar, final_sidecar


def subprocess_env(cfg: DriverConfig) -> dict[str, str]:
    """Env for the backtesting subprocesses.

    RENQUANT_REPO_ROOT pins the umbrella tree the backtesting runner resolves
    (wf_gate.runner._resolve_repo_root) — the sanity panel parquets
    (data/alpha158_291_fundamental_dataset*.parquet) are read relative to it.
    """
    env = dict(os.environ)
    src = str(cfg.backtesting_root / "src")
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = src + (os.pathsep + existing if existing else "")
    env["RENQUANT_REPO_ROOT"] = str(cfg.umbrella_root)
    return env


def build_preflight_command(cfg: DriverConfig) -> list[str]:
    snippet = _PREFLIGHT_SNIPPET.replace("__CONTRACT_NAMES__", repr(CONTRACT_NAMES))
    return [cfg.python, "-c", snippet]


def build_analyzer_command(cfg: DriverConfig, staging_parquet: Path) -> list[str]:
    """The exact #59 invocation. NEVER passes --allow-production-path — the
    contract-side research-only path guard stays armed."""
    return [
        cfg.python, "-m", ANALYZER_MODULE,
        "--artifact", str(cfg.artifact),
        "--manifest", str(cfg.manifest),
        "--label", cfg.label,
        "--strategy-dir", str(cfg.strategy_dir),
        "--output-dir", str(cfg.diagnostics_dir),
        "--dump-predictions", str(staging_parquet),
    ]


def build_verify_command(cfg: DriverConfig, parquet: Path, sidecar: Path) -> list[str]:
    return [cfg.python, "-c", _VERIFY_SNIPPET, str(parquet), str(sidecar)]


def analyzer_result_json_path(cfg: DriverConfig) -> Path:
    """Where the analyzer writes its result JSON (pinned to #59's naming:
    `<output-dir>/<artifact stem, dots -> underscores>.json`)."""
    stem = cfg.artifact.stem.replace(".", "_")
    return cfg.diagnostics_dir / f"{stem}.json"


def faithfulness_gate(result: dict[str, Any], committed: float, tolerance: float) -> dict[str, Any]:
    """The A1 bar: fresh genuine_ic (aligned_real_60 - placebo_60, read from
    the sanity gate's own JSON output) must reproduce the committed genuine_ic
    to +/-`tolerance`. Fails closed on missing/NaN inputs."""
    interp = result.get("interpretation") or {}
    aligned = interp.get("aligned_real_60_ic")
    placebo = interp.get("placebo_60_ic")
    if aligned is None or placebo is None:
        raise GateError(
            "faithfulness gate: sanity JSON is missing "
            "interpretation.aligned_real_60_ic / placebo_60_ic — cannot prove "
            "the regeneration is faithful; failing closed"
        )
    fresh = float(aligned) - float(placebo)
    if fresh != fresh:  # NaN
        raise GateError("faithfulness gate: fresh genuine_ic is NaN; failing closed")
    delta = abs(fresh - float(committed))
    summary = {
        "fresh_genuine_ic": fresh,
        "aligned_real_60_ic": float(aligned),
        "placebo_60_ic": float(placebo),
        "committed_genuine_ic": float(committed),
        "abs_delta": delta,
        "tolerance": float(tolerance),
    }
    if delta > float(tolerance):
        raise GateError(
            "FAITHFULNESS GATE FAILED: regenerated genuine_ic "
            f"{fresh:+.6f} vs committed {float(committed):+.6f} "
            f"(|delta| {delta:.6f} > tolerance {float(tolerance):.6f}). "
            "The regenerated table is NOT proven faithful to the committed "
            "evidence and must not be used. NOTE: per RenQuant#431 the "
            "committed bar itself is disputed — a fail here may be the #431 "
            "discrepancy, not a scoring bug; do not loosen the tolerance to "
            "force a pass. " + json.dumps(summary)
        )
    return summary


def counts_gate(sidecar: dict[str, Any], *, expected_dates: int, expected_rows: int,
                rows_tolerance_pct: float) -> dict[str, Any]:
    """Row-count sanity against the committed shape (~147k rows / 508 dates)."""
    counts = sidecar.get("counts") or {}
    n_rows = counts.get("n_rows")
    n_dates = counts.get("n_dates")
    if n_rows is None or n_dates is None:
        raise GateError("counts gate: sidecar is missing counts.n_rows/n_dates; failing closed")
    n_rows, n_dates = int(n_rows), int(n_dates)
    summary = {
        "n_rows": n_rows,
        "n_dates": n_dates,
        "expected_rows": int(expected_rows),
        "expected_dates": int(expected_dates),
        "rows_tolerance_pct": float(rows_tolerance_pct),
    }
    if n_dates != int(expected_dates):
        raise GateError(
            f"COUNTS GATE FAILED: {n_dates} OOS dates != expected {expected_dates}. "
            + json.dumps(summary)
        )
    allowed = abs(float(expected_rows)) * float(rows_tolerance_pct) / 100.0
    if abs(n_rows - int(expected_rows)) > allowed:
        raise GateError(
            f"COUNTS GATE FAILED: {n_rows} rows deviates from expected "
            f"{expected_rows} by more than {rows_tolerance_pct}%. " + json.dumps(summary)
        )
    return summary


def _run_subprocess(argv: Sequence[str], *, env: dict[str, str], cwd: Path,
                    timeout: int = 7200) -> subprocess.CompletedProcess:
    """Single subprocess seam (monkeypatched in tests; no real scoring there)."""
    return subprocess.run(
        list(argv), env=env, cwd=str(cwd), capture_output=True, text=True, timeout=timeout,
    )


def preflight_contract(cfg: DriverConfig) -> None:
    """The mechanical #59 run gate."""
    proc = _run_subprocess(build_preflight_command(cfg), env=subprocess_env(cfg),
                           cwd=cfg.backtesting_root, timeout=600)
    detail = (proc.stdout or "").strip() or (proc.stderr or "").strip()
    if proc.returncode != 0:
        raise DriverSetupError(
            "RUN GATE CLOSED: the backtesting checkout at "
            f"{cfg.backtesting_root} does not provide the #59 pick-table "
            "contract (backtesting #59 `feat/sanity-dump-predictions` not "
            f"merged/checked out?). Preflight said: {detail}"
        )


def print_plan(cfg: DriverConfig) -> None:
    staging_parquet, staging_sidecar, final_sidecar = staging_paths(cfg.output)
    env = subprocess_env(cfg)
    plan = {
        "mode": "DRY-RUN — nothing executed",
        "run_gate": (
            "real run requires backtesting #59 (feat/sanity-dump-predictions) "
            "merged into the backtesting checkout; preflight checks "
            f"{CONTRACT_MODULE}.{{{', '.join(CONTRACT_NAMES)}}} and "
            "analyze_manifest(dump_predictions=...)"
        ),
        "cwd": str(cfg.backtesting_root),
        "env_overrides": {
            "RENQUANT_REPO_ROOT": env["RENQUANT_REPO_ROOT"],
            "PYTHONPATH": env["PYTHONPATH"],
        },
        "commands": {
            "1_preflight_contract": build_preflight_command(cfg),
            "2_analyzer": build_analyzer_command(cfg, staging_parquet),
            "3_verify_final": build_verify_command(cfg, cfg.output, final_sidecar),
        },
        "paths": {
            "manifest": str(cfg.manifest),
            "reference_artifact": str(cfg.artifact),
            "strategy_dir": str(cfg.strategy_dir),
            "diagnostics_dir": str(cfg.diagnostics_dir),
            "analyzer_result_json": str(analyzer_result_json_path(cfg)),
            "staging_parquet": str(staging_parquet),
            "staging_sidecar": str(staging_sidecar),
            "final_parquet": str(cfg.output),
            "final_sidecar": str(final_sidecar),
        },
        "gates": {
            "faithfulness": {
                "committed_genuine_ic": cfg.committed_genuine_ic,
                "tolerance": cfg.ic_tolerance,
                "note": "disputed per RenQuant#431; a hard FAIL is a legitimate outcome",
            },
            "counts": {
                "expected_dates": cfg.expected_dates,
                "expected_rows": cfg.expected_rows,
                "rows_tolerance_pct": cfg.rows_tolerance_pct,
            },
            "post_write": "verify_pick_table on the FINAL parquet+sidecar",
        },
    }
    print(json.dumps(plan, indent=2))


def run(cfg: DriverConfig) -> int:
    staging_parquet, staging_sidecar, final_sidecar = staging_paths(cfg.output)
    # Gate 0 — exp-path refusal (applies to dry-run too: a plan targeting a
    # production path is already wrong).
    for p in (cfg.output, staging_parquet, cfg.diagnostics_dir):
        ensure_exp_path(p, cfg.umbrella_root)

    if cfg.dry_run:
        print_plan(cfg)
        return 0

    for p, what in ((cfg.manifest, "manifest"), (cfg.artifact, "reference artifact"),
                    (cfg.backtesting_root, "backtesting checkout")):
        if not Path(p).exists():
            raise DriverSetupError(f"missing {what}: {p}")

    # Snapshot the committed anchor BEFORE anything is written.
    committed_anchor: Optional[str] = None
    if final_sidecar.exists():
        try:
            committed_anchor = str(
                json.loads(final_sidecar.read_text())["output"]["output_content_sha256"]
            )
        except Exception:  # noqa: BLE001 — anchor comparison is report-only
            committed_anchor = None

    preflight_contract(cfg)

    env = subprocess_env(cfg)
    analyzer_cmd = build_analyzer_command(cfg, staging_parquet)
    print("running:", " ".join(analyzer_cmd), file=sys.stderr)
    proc = _run_subprocess(analyzer_cmd, env=env, cwd=cfg.backtesting_root)
    if proc.returncode != 0:
        raise DriverSetupError(
            f"analyzer failed (exit {proc.returncode}). stderr tail:\n"
            + (proc.stderr or "")[-2000:]
        )

    result_path = analyzer_result_json_path(cfg)
    if not result_path.exists():
        raise DriverSetupError(f"analyzer result JSON not found at {result_path}")
    result = json.loads(result_path.read_text())
    if not staging_parquet.exists() or not staging_sidecar.exists():
        raise DriverSetupError(
            f"analyzer did not write {staging_parquet} / {staging_sidecar}"
        )
    sidecar = json.loads(staging_sidecar.read_text())

    # Gates — a failure leaves staging in place and never touches the final path.
    faith = faithfulness_gate(result, cfg.committed_genuine_ic, cfg.ic_tolerance)
    counts = counts_gate(
        sidecar,
        expected_dates=cfg.expected_dates,
        expected_rows=cfg.expected_rows,
        rows_tolerance_pct=cfg.rows_tolerance_pct,
    )

    # Promote staging -> final, then re-verify the FINAL artifact through the
    # contract's own reload check (writing is not evidence; verifying is).
    os.replace(staging_parquet, cfg.output)
    os.replace(staging_sidecar, final_sidecar)
    vproc = _run_subprocess(build_verify_command(cfg, cfg.output, final_sidecar),
                            env=env, cwd=cfg.backtesting_root, timeout=900)
    if vproc.returncode != 0:
        raise GateError(
            "POST-WRITE VERIFICATION FAILED: verify_pick_table rejected the "
            f"promoted artifact {cfg.output} — do not use it. stderr tail:\n"
            + (vproc.stderr or "")[-2000:]
        )
    verified = json.loads((vproc.stdout or "").strip().splitlines()[-1])

    fresh_anchor = str(sidecar.get("output", {}).get("output_content_sha256", ""))
    anchor_report: dict[str, Any] = {
        "committed_anchor": committed_anchor,
        "fresh_anchor": fresh_anchor,
        "reproduced": (committed_anchor == fresh_anchor) if committed_anchor else None,
        "note": (
            "report-only: the RenQuant#430 anchor predates the #59 contract; "
            "a mismatch is flagged for review, the binding gates are "
            "faithfulness + counts + post-write verification"
        ),
    }

    print(json.dumps({
        "status": "PASS",
        "final_parquet": str(cfg.output),
        "final_sidecar": str(final_sidecar),
        "analyzer_result_json": str(result_path),
        "faithfulness": faith,
        "counts": counts,
        "post_write_verification": verified,
        "content_anchor": anchor_report,
    }, indent=2))
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    cfg = resolve_config(parse_args(argv))
    try:
        return run(cfg)
    except GateError as exc:
        print(f"GATE FAILED: {exc}", file=sys.stderr)
        return 1
    except DriverSetupError as exc:
        print(f"CANNOT RUN: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
