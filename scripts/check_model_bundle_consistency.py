#!/usr/bin/env python3
"""Pre-deploy self-consistency check for a renquant-104 model bundle.

The 2026-06-23 XGB deploy hit FOUR consistency contracts one-by-one, in PRODUCTION,
each patched by hand: (1) WF-gate metadata absent, (2) calibrator/scorer fingerprint
mismatch, (3) config fingerprint mismatch, (4) watchlist 142 != 145. Every one of these
is checkable OFFLINE before a deploy. This script runs all four against a candidate
strategy config + its resolved artifacts and reports deploy-readiness, so the
whack-a-mole happens here instead of on the live tree.

Reuses the SAME authorities the live preflight uses, so a PASS here means the runtime
P-* gates will pass too:
  - config fingerprint:   renquant_common.config_consistency.fingerprint_config
  - scorer fingerprint:    renquant_common.model_fingerprint.model_content_sha256
  - calibrator binding:    calibrator.metadata.scorer_model_content_fingerprint
  - WF gate metadata:      artifact (metadata.)wf_gate_metadata.{passed, numerics}
  - watchlist:             config.watchlist vs artifact.config_fingerprint_fields.watchlist

Usage:
    check_model_bundle_consistency.py [--config PATH] [--strategy-dir DIR] [--json]

Exit 0 = deploy-ready, 1 = at least one contract failed, 2 = could not evaluate.
Run inside the strategy venv with the subrepo PYTHONPATH (see scripts/subrepo_env.sh).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path

def _default_repo() -> Path:
    from renquant_orchestrator.runtime_paths import default_data_root
    return default_data_root()


def _resolve(strategy_dir: Path, rel: str) -> Path:
    p = Path(rel)
    if p.is_absolute():
        return p
    cand = strategy_dir / p
    if cand.exists():
        return cand
    return (strategy_dir.parent.parent / p)  # repo-root fallback (default_repo_root convention)


def _active_panel(config: dict) -> dict:
    return (config.get("ranking", {}).get("panel_scoring", {}) or config.get("panel_ltr", {}) or {})


def _finite(v) -> bool:
    try:
        f = float(v)
        return f == f and f not in (float("inf"), float("-inf"))
    except Exception:
        return False


def _runtime_scorer_fp(art_path: Path, repo: Path | None):
    """The fingerprint the LIVE runtime itself stamps on load (pinned pipeline
    PanelScorer). None when the pinned checkout is not importable here —
    callers must then treat a common-impl mismatch as FAIL (closed), because
    the runtime's answer is unknown, not because it is known-bad."""
    if repo is None:
        return None
    src = repo / ".subrepo_runtime" / "repos" / "renquant-pipeline" / "src"
    if not src.is_dir():
        return None
    sys.path.insert(0, str(src))
    try:
        from renquant_pipeline.kernel.panel_pipeline.panel_scorer import PanelScorer  # noqa: PLC0415
        return PanelScorer.load(str(art_path)).metadata.get("model_content_fingerprint")
    except Exception:
        return None
    finally:
        try:
            sys.path.remove(str(src))
        except ValueError:
            pass


def check_bundle(config_path: Path, strategy_dir: Path, *,
                 fingerprint_config=None, model_content_sha256=None,
                 repo: Path | None = None) -> dict:
    # Reuse the live preflight authorities by default; allow injection for unit tests.
    if fingerprint_config is None:
        from renquant_common.config_consistency import fingerprint_config  # noqa: PLC0415
    if model_content_sha256 is None:
        from renquant_common.model_fingerprint import model_content_sha256  # noqa: PLC0415

    config = json.loads(config_path.read_text())
    panel = _active_panel(config)
    kind = panel.get("kind", "xgb")
    checks: list[dict] = []

    def add(name, ok, detail):
        checks.append({"contract": name, "pass": bool(ok), "detail": detail})

    # Resolve scorer artifact (skip sequence/.pt — those use sidecars; this check targets panel-LTR)
    art_rel = panel.get("artifact_path", "artifacts/prod/panel-ltr.alpha158_fund.json")
    art_path = _resolve(strategy_dir, art_rel)
    if kind in {"hf_patchtst", "patchtst"} or str(art_path).endswith(".pt"):
        add("scorer_kind", True, f"sequence scorer ({kind}); bundle check targets panel-LTR — skipping JSON-artifact contracts")
        return {"kind": kind, "deploy_ready": True, "checks": checks, "skipped": True}
    if not art_path.exists():
        add("artifact_present", False, f"missing scorer artifact at {art_path}")
        return {"kind": kind, "deploy_ready": False, "checks": checks}
    art = json.loads(art_path.read_text())
    add("artifact_present", True, str(art_path))

    # (3) config fingerprint
    live_fp = fingerprint_config(config)
    stored_fp = art.get("config_fingerprint")
    add("config_fingerprint", stored_fp == live_fp,
        f"live={live_fp} stored={stored_fp}")

    # (4) watchlist
    live_wl = list(config.get("watchlist", []))
    stored_wl = list((art.get("config_fingerprint_fields") or {}).get("watchlist", []))
    miss = sorted(set(live_wl) - set(stored_wl))
    add("watchlist", set(live_wl) == set(stored_wl),
        f"live n={len(live_wl)} trained n={len(stored_wl)} in_live_not_trained={miss[:6]}")

    # (2) calibrator/scorer fingerprint binding
    gc = panel.get("global_calibration", {}) or {}
    cal_rel = gc.get("artifact_path")
    if gc.get("enabled") and cal_rel:
        cal_path = _resolve(strategy_dir, cal_rel)
        if not cal_path.exists():
            add("calibrator_present", False, f"missing calibrator at {cal_path}")
        else:
            cal = json.loads(cal_path.read_text())
            cal_fp = (cal.get("metadata") or {}).get("scorer_model_content_fingerprint")
            scorer_fp = model_content_sha256(art)
            if cal_fp == scorer_fp:
                add("calibrator_scorer_match", True,
                    f"calibrator_expects={cal_fp} scorer={scorer_fp}")
            else:
                # 2026-08-04: the common-impl hash and the runtime's stamped
                # fingerprint are DIFFERENT SCHEMAS (v1 vs legacy; the M6
                # dispatch compares within one schema). The question this
                # check must answer is the RUNTIME's: does the pair match at
                # PanelScorer.load time? Ask it directly when the pinned
                # pipeline is importable; if it is not, stay FAILED (closed) —
                # unknown is not a pass.
                rt_fp = _runtime_scorer_fp(art_path, repo)
                if rt_fp is not None and cal_fp == rt_fp:
                    add("calibrator_scorer_match", True,
                        f"common-impl mismatch (common={scorer_fp}) but the "
                        f"RUNTIME pair matches: runtime_fp={rt_fp} == "
                        f"calibrator stamp — schema divergence, runtime is "
                        f"authoritative")
                else:
                    add("calibrator_scorer_match", False,
                        f"calibrator_expects={cal_fp} scorer={scorer_fp} "
                        f"runtime_fp={rt_fp}")
    else:
        add("calibrator_scorer_match", True, "global_calibration disabled — n/a")

    # (1) WF gate metadata (what the live P-WF-GATE needs for buys)
    wf = ((art.get("metadata") or {}).get("wf_gate_metadata")) or art.get("wf_gate_metadata") or {}
    if not wf:
        add("wf_gate_metadata", False, "absent — buy runs will be blocked by P-WF-GATE")
    else:
        req = ["wf_3cut_sharpe_mean", "spy_sharpe_mean", "strategy_minus_spy_sharpe_mean"]
        missing = [k for k in req if not _finite(wf.get(k))]
        gate_passed = wf.get("passed") is True
        # RFC #210 (2026-08-04 incident, third consumer found the same day):
        # a freshness-fallback promotion serves with passed=False BY DESIGN,
        # and the live P-WF-GATE admits it while fresh. This checker's job is
        # "what the live P-WF-GATE needs for buys", so it mirrors that
        # license. Rules kept in LOCKSTEP with renquant-pipeline
        # kernel/rfc210_license.py (exact basis string; parseable ISO
        # trained_date; age 0..28d; future-dated refuses; fail closed).
        licensed = False
        lic_note = ""
        if not gate_passed:
            meta = art.get("metadata") or {}
            basis = meta.get("promotion_basis", art.get("promotion_basis"))
            raw = art.get("trained_date", meta.get("trained_date"))
            if basis == "freshness_fallback_rfc210" and isinstance(raw, str) and raw.strip():
                try:
                    age = (_dt.date.today() - _dt.date.fromisoformat(raw.strip())).days
                except ValueError:
                    lic_note = " rfc210=refused(bad trained_date)"
                else:
                    licensed = 0 <= age <= 28
                    lic_note = f" rfc210={'served' if licensed else 'refused'}(age={age}d)"
        ok = ((gate_passed or licensed) and not missing
              and ("n_cuts_beat_spy_sharpe" in wf))
        add("wf_gate_metadata", ok,
            f"passed={wf.get('passed')}{lic_note} missing_numerics={missing} "
            f"override={wf.get('operator_authorized_override')}")

    ready = all(c["pass"] for c in checks)
    return {"kind": kind, "deploy_ready": ready, "checks": checks,
            "artifact": str(art_path)}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default=None,
                    help="strategy config path (default: pinned 104 strategy_config.json)")
    ap.add_argument("--strategy-dir", default=None,
                    help="artifact resolution base (default: <repo>/backtesting/renquant_104)")
    ap.add_argument("--repo", default=None)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    repo = Path(a.repo) if a.repo else _default_repo()
    config_path = Path(a.config) if a.config else (
        repo / ".subrepo_runtime/repos/renquant-strategy-104/configs/strategy_config.json")
    strategy_dir = Path(a.strategy_dir) if a.strategy_dir else (repo / "backtesting/renquant_104")
    if not config_path.exists():
        print(f"config not found: {config_path}", file=sys.stderr)
        sys.exit(2)
    res = check_bundle(config_path, strategy_dir, repo=repo)
    if a.json:
        print(json.dumps(res, indent=2))
    else:
        print(f"BUNDLE CONSISTENCY — kind={res['kind']}  deploy_ready={res['deploy_ready']}")
        for c in res["checks"]:
            print(f"  [{'PASS' if c['pass'] else 'FAIL'}] {c['contract']:24} {c['detail']}")
    sys.exit(0 if res["deploy_ready"] else 1)


if __name__ == "__main__":
    main()
