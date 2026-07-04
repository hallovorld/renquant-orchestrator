"""The orchestrating entry: spec -> substrate -> controls gate -> evaluation
-> stats -> verdict + evidence bundle.

An experiment plugs in as a FrozenSpec plus four callbacks (load_substrate,
evaluate, positive_control, null_control). Everything else — the freeze
check, the mandatory-controls gate, the placebo-difference gate with the
automatic small-n branch, the power-aware verdict, and the hash-stamped
evidence bundle — is the library's job, identical for every experiment.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import numpy as np
import pandas as pd

from renquant_orchestrator.expkit import evidence as ev
from renquant_orchestrator.expkit.controls import ControlsReport, run_controls
from renquant_orchestrator.expkit.prereg import FreezeCheck, FrozenSpec, check_spec_frozen_before_results
from renquant_orchestrator.expkit.stats import bootstrap_or_exact
from renquant_orchestrator.expkit.verdict import GateDecision, decide, verdicts_md_row

__all__ = [
    "ExperimentPlugin",
    "ExperimentResult",
    "gate_per_date",
    "run_experiment",
]


def _clean_series(per_date: pd.DataFrame | pd.Series) -> pd.Series:
    if isinstance(per_date, pd.Series):
        return per_date.dropna().sort_index()
    if "clean_ic" not in per_date.columns:
        raise ValueError("per-date frame must carry a 'clean_ic' column")
    return per_date.dropna(subset=["clean_ic"]).sort_index()["clean_ic"]


def gate_per_date(
    per_date: pd.DataFrame | pd.Series,
    spec: FrozenSpec,
    *,
    in_cell: np.ndarray | None = None,
    controls_ok: bool | None = None,
    non_voting_reasons: Sequence[str] = (),
) -> tuple[dict[str, Any], GateDecision]:
    """Evaluate the frozen gate on a per-date clean-IC series (or a frame
    with a clean_ic column; real_ic/placebo_ic means are summarized when
    present). The gate bar is the spec's FIRST criterion (frozen convention:
    criteria[0] is THE decision bar, direction 'gt' on the one-sided LB).

    Returns (gate_summary, decision). The small-n branch engages
    automatically inside stats.bootstrap_or_exact.
    """
    clean = _clean_series(per_date)
    vals = clean.to_numpy(dtype=float)
    bar = spec.criteria[0]
    stats_result = bootstrap_or_exact(
        vals,
        block=spec.block,
        n_boot=spec.n_boot,
        seeds=spec.seeds,
        alpha_one_sided=spec.alpha_one_sided,
        in_cell=in_cell,
        threshold=bar.threshold,
    )
    observed = float(vals.mean()) if len(vals) else None
    decision = decide(
        stats_result,
        threshold=bar.threshold,
        min_decision_dates=spec.min_decision_dates,
        alpha_one_sided=spec.alpha_one_sided,
        controls_ok=controls_ok,
        observed_mean=observed,
        non_voting_reasons=non_voting_reasons,
    )
    summary: dict[str, Any] = {
        "n_dates": int(len(vals)),
        "sample_floor_met": bool(len(vals) >= spec.min_decision_dates),
        "mean_clean_ic": observed,
        "clean_hit_rate": float((vals > 0).mean()) if len(vals) else None,
        "criterion": {"name": bar.name, "threshold": bar.threshold, "direction": bar.direction},
        "stats": {k: v for k, v in stats_result.items() if k != "exact"},
    }
    if isinstance(per_date, pd.DataFrame):
        for col, key in (("real_ic", "mean_real_ic"), ("placebo_ic", "mean_placebo_ic")):
            if col in per_date.columns:
                aligned = per_date.loc[clean.index, col]
                summary[key] = float(aligned.mean()) if aligned.notna().any() else None
    if stats_result["method"] == "exact":
        summary["stats"]["exact"] = vars(stats_result["exact"]).copy()
    return summary, decision


@dataclass
class ExperimentPlugin:
    """One experiment = one frozen spec + a few callbacks.

    - load_substrate(): read-only load of everything the experiment needs
      (any object). Called once.
    - evaluate(substrate) -> per-date DataFrame with clean_ic (+ real_ic /
      placebo_ic when applicable) — build scores, labels, placebo, and the
      per-date IC here using evaluation.py primitives.
    - positive_control(substrate) / null_control(substrate) -> per-date
      series/frame gated with the SAME frozen gate; both MUST pass before
      any verdict is admissible (controls.run_controls semantics).
    - in_cell(substrate, per_date) -> bool mask over the per-date index for
      regime-conditioned gates (carried through the full-series bootstrap).
    - non_voting_reasons: declared substrate disqualifiers / unmet
      preconditions — forces the governing outcome to NON-VOTING while the
      mechanical rule output is still computed and recorded (the C2
      EXPLORATORY_NON_VOTING pattern).
    - require_negative_branch: RS-5 null semantics (default) — the true null
      must not only be un-detected, its negative branch (KILL/NULL) must
      actually fire. Waiving it (the C2 PC-C "specificity only" semantics —
      a harness honestly under-powered to actively KILL a null) REQUIRES a
      documented `negative_branch_waiver` reason.
    - inputs: logical-name -> path map, content-hashed into the manifest.
    - spec_path/results_paths: enables the git-history freeze-first check.
    """

    spec: FrozenSpec
    load_substrate: Callable[[], Any]
    evaluate: Callable[[Any], pd.DataFrame]
    positive_control: Callable[[Any], pd.DataFrame | pd.Series]
    null_control: Callable[[Any], pd.DataFrame | pd.Series]
    declared_plant_effect: float | None = None
    in_cell: Callable[[Any, pd.DataFrame], np.ndarray] | None = None
    non_voting_reasons: tuple[str, ...] = ()
    require_negative_branch: bool = True
    negative_branch_waiver: str = ""
    inputs: Mapping[str, Path] = field(default_factory=dict)
    spec_path: Path | None = None
    results_paths: tuple[Path, ...] = ()
    script: str = ""

    def __post_init__(self) -> None:
        if not self.require_negative_branch and not self.negative_branch_waiver.strip():
            raise ValueError(
                "waiving require_negative_branch needs a documented "
                "negative_branch_waiver reason (C2 PC-C precedent: state WHY "
                "non-detection alone suffices for this harness)"
            )


@dataclass
class ExperimentResult:
    experiment_id: str
    outcome: str | None
    decision: GateDecision | None
    gate_summary: dict[str, Any] | None
    controls: ControlsReport | None
    freeze_check: FreezeCheck | None
    spec_sha256: str
    evidence_path: Path | None
    per_date_path: Path | None
    dry_run: bool = False
    dry_run_plan: dict[str, Any] | None = None
    spec: FrozenSpec | None = None

    def verdicts_md_row(
        self,
        *,
        date: str,
        rationale: str,
        verification: str = "PROVISIONAL",
        verification_note: str = "(R1 default)",
    ) -> str:
        boundary = "see evidence bundle"
        boundary_map: Mapping[str, str] = {}
        if self.gate_summary is not None:
            boundary_map = self.gate_summary.get("evidence_boundary") or {}
        if not boundary_map and self.spec is not None:
            boundary_map = self.spec.evidence_boundary
        if boundary_map:
            boundary = "; ".join(f"{k}: {v}" for k, v in boundary_map.items())
        reopening: Sequence[str] = (
            self.spec.reopening_conditions if self.spec is not None else ()
        )
        return verdicts_md_row(
            date=date,
            id_source=self.experiment_id,
            verdict=self.outcome or "NON-VOTING",
            rationale=rationale,
            evidence_boundary=boundary,
            verification=verification,
            verification_note=verification_note,
            reopening_condition="; ".join(reopening or ("see frozen spec",)),
        )


def run_experiment(
    plugin: ExperimentPlugin,
    *,
    out_dir: Path | str | None = None,
    repo_root: Path | str | None = None,
    dry_run: bool = False,
    freeze_check: bool = True,
    env_lock: bool = False,
) -> ExperimentResult:
    """Run one pre-registered experiment end to end.

    Order is the contract: freeze check -> controls -> evaluation -> stats
    -> verdict -> evidence. The controls gate is not skippable: a plugin
    without passing controls gets a NON-VOTING governing outcome, never a
    verdict. With dry_run=True the wiring and spec are validated and a plan
    is returned — no substrate is loaded, nothing is written.
    """
    spec = plugin.spec
    spec_sha = spec.sha256()

    fcheck: FreezeCheck | None = None
    if freeze_check and plugin.spec_path is not None:
        if repo_root is None:
            raise ValueError("repo_root is required for the freeze-first check")
        fcheck = check_spec_frozen_before_results(
            repo_root, plugin.spec_path, plugin.results_paths
        )
        if not dry_run:
            fcheck.raise_if_failed()

    if dry_run:
        plan = {
            "experiment_id": spec.experiment_id,
            "spec_sha256": spec_sha,
            "alpha_one_sided": spec.alpha_one_sided,
            "gate_criterion": {
                "name": spec.criteria[0].name,
                "threshold": spec.criteria[0].threshold,
            },
            "seeds": list(spec.seeds),
            "block": spec.block,
            "n_boot": spec.n_boot,
            "min_decision_dates": spec.min_decision_dates,
            "controls": ["positive_plant", "true_null"],
            "non_voting_reasons_declared": list(plugin.non_voting_reasons),
            "freeze_check": None if fcheck is None else vars(fcheck),
            "inputs": {k: str(v) for k, v in plugin.inputs.items()},
            "would_write": (str(out_dir) if out_dir else None),
        }
        return ExperimentResult(
            experiment_id=spec.experiment_id,
            outcome=None,
            decision=None,
            gate_summary=None,
            controls=None,
            freeze_check=fcheck,
            spec_sha256=spec_sha,
            evidence_path=None,
            per_date_path=None,
            dry_run=True,
            dry_run_plan=plan,
            spec=spec,
        )

    substrate = plugin.load_substrate()

    # --- mandatory controls, gated with the SAME frozen gate -------------
    def _control_gate(per_date: pd.DataFrame | pd.Series) -> GateDecision:
        _, d = gate_per_date(per_date, spec, controls_ok=True)
        return d

    controls = run_controls(
        _control_gate,
        positive_input=plugin.positive_control(substrate),
        null_input=plugin.null_control(substrate),
        declared_effect=plugin.declared_plant_effect,
        require_negative_branch=plugin.require_negative_branch,
    )
    if not plugin.require_negative_branch:
        controls.null.detail["negative_branch_waiver"] = plugin.negative_branch_waiver

    # --- evaluation + gate ------------------------------------------------
    per_date = plugin.evaluate(substrate)
    mask = plugin.in_cell(substrate, per_date) if plugin.in_cell is not None else None
    gate_summary, decision = gate_per_date(
        per_date,
        spec,
        in_cell=mask,
        controls_ok=controls.all_passed,
        non_voting_reasons=plugin.non_voting_reasons,
    )
    gate_summary["evidence_boundary"] = dict(spec.evidence_boundary)

    evidence_path: Path | None = None
    per_date_path: Path | None = None
    if out_dir is not None:
        out_dir = Path(out_dir)
        manifest = ev.build_manifest(
            repo_root=repo_root if repo_root is not None else Path.cwd(),
            script=plugin.script or f"expkit:{spec.experiment_id}",
            inputs=plugin.inputs,
            seeds=spec.seeds,
            spec_sha256=spec_sha,
            env_lock=env_lock,
        )
        payload = {
            "experiment_id": spec.experiment_id,
            "spec": spec.to_dict(),
            "spec_sha256": spec_sha,
            "freeze_check": None if fcheck is None else vars(fcheck),
            "controls": controls.to_dict(),
            "gate": gate_summary,
            "decision": decision.to_dict(),
            "manifest": manifest,
        }
        evidence_path = ev.write_evidence(
            out_dir, f"{spec.experiment_id}_results.json", payload
        )
        frame = per_date if isinstance(per_date, pd.DataFrame) else per_date.to_frame("clean_ic")
        per_date_path = out_dir / f"{spec.experiment_id}_per_date.json"
        frame.reset_index().to_json(
            per_date_path, orient="records", date_format="iso", indent=1
        )

    return ExperimentResult(
        experiment_id=spec.experiment_id,
        outcome=decision.outcome.value,
        decision=decision,
        gate_summary=gate_summary,
        controls=controls,
        freeze_check=fcheck,
        spec_sha256=spec_sha,
        evidence_path=evidence_path,
        per_date_path=per_date_path,
        spec=spec,
    )
