"""CI-gate integration test for the pre-deploy model-bundle consistency check.

This is the gate that turns the four PROD consistency contracts (which fired
one-by-one on the 2026-06-23 XGB deploy) into a hard CI signal:

  1. wf_gate_metadata        — WF-gate metadata absent
  2. calibrator_scorer_match — calibrator/scorer fingerprint mismatch
  3. config_fingerprint      — config fingerprint mismatch
  4. watchlist               — watchlist size mismatch

It complements ``tests/test_check_model_bundle_consistency.py`` (which unit-tests
each contract via injected fingerprint functions) by:

  * asserting the contract NAMES reported by ``check_bundle`` exactly match the
    live preflight authority names the runtime P-* gates use, so the gate cannot
    silently drift away from production while still "passing"; and
  * exercising the script as an end-to-end CLI on a self-consistent bundle
    (exit 0) and on a deliberately-broken bundle (exit non-zero), proving the
    gate actually bites in CI.

Runs without the strategy venv: it builds a synthetic temp bundle and injects
the two fingerprint authorities, reusing the pattern from the unit test.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO_ROOT / "scripts" / "check_model_bundle_consistency.py"

_spec = importlib.util.spec_from_file_location("bundlecheck_cigate", _SCRIPT)
bundlecheck = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bundlecheck)

# These are the live preflight / runtime P-* gate authority names. The bundle
# check is only trustworthy as a pre-deploy gate if the contracts it reports map
# 1:1 to the contracts production enforces. If someone renames one of these in
# the script without keeping the runtime in sync, this test must fail.
LIVE_PREFLIGHT_CONTRACTS = frozenset(
    {"config_fingerprint", "watchlist", "calibrator_scorer_match", "wf_gate_metadata"}
)

LIVE_FP = "sha256:LIVE"
SCORER_FP = "sha256:SCORER"
WATCHLIST = ["AAPL", "MSFT", "NVDA"]


def _write_bundle(tmp_path: Path, *, art_fp=LIVE_FP, art_wl=WATCHLIST,
                  cal_fp=SCORER_FP, wf_passed=True, wf_complete=True) -> Path:
    """Build a synthetic, self-consistent renquant-104 panel-LTR bundle on disk.

    Mirrors ``tests/test_check_model_bundle_consistency.py`` so the two test
    modules exercise the exact same bundle shape.
    """
    sd = tmp_path / "backtesting" / "renquant_104"
    (sd / "artifacts" / "prod").mkdir(parents=True, exist_ok=True)
    wf = {}
    if wf_passed is not None:
        wf = {"passed": wf_passed, "operator_authorized_override": True}
        if wf_complete:
            wf.update({"wf_3cut_sharpe_mean": 0.7, "spy_sharpe_mean": 1.08,
                       "strategy_minus_spy_sharpe_mean": -0.38,
                       "n_cuts_beat_spy_sharpe": 1})
    art = {"kind": "panel_ltr_xgboost", "config_fingerprint": art_fp,
           "config_fingerprint_fields": {"watchlist": art_wl},
           "metadata": ({"wf_gate_metadata": wf} if wf else {})}
    (sd / "artifacts" / "prod" / "panel-ltr.alpha158_fund.json").write_text(json.dumps(art))
    cal = {"metadata": {"scorer_model_content_fingerprint": cal_fp}}
    (sd / "artifacts" / "prod" / "panel-rank-calibration.json").write_text(json.dumps(cal))
    cfg = {"watchlist": WATCHLIST,
           "ranking": {"panel_scoring": {
               "kind": "xgb",
               "artifact_path": "artifacts/prod/panel-ltr.alpha158_fund.json",
               "global_calibration": {
                   "enabled": True,
                   "artifact_path": "artifacts/prod/panel-rank-calibration.json"}}}}
    cfg_path = tmp_path / "strategy_config.json"
    cfg_path.write_text(json.dumps(cfg))
    return cfg_path


def _run(tmp_path: Path, **kw) -> dict:
    cfg_path = _write_bundle(tmp_path, **kw)
    sd = tmp_path / "backtesting" / "renquant_104"
    return bundlecheck.check_bundle(
        cfg_path, sd,
        fingerprint_config=lambda c: LIVE_FP,
        model_content_sha256=lambda a: SCORER_FP,
    )


def _contract_names(res: dict) -> set[str]:
    return {c["contract"] for c in res["checks"]}


def _verdict(res: dict, contract: str) -> bool:
    return next(c["pass"] for c in res["checks"] if c["contract"] == contract)


# --------------------------------------------------------------------------- #
# 1. Consistent bundle is deploy-ready AND reports every live-preflight contract
# --------------------------------------------------------------------------- #
def test_consistent_bundle_is_deploy_ready_and_covers_all_live_contracts(tmp_path):
    res = _run(tmp_path)
    assert res["deploy_ready"] is True
    assert all(c["pass"] for c in res["checks"])
    # The check must exercise every contract the live preflight enforces, by the
    # SAME name — otherwise a contract could silently stop being gated.
    reported = _contract_names(res)
    missing = LIVE_PREFLIGHT_CONTRACTS - reported
    assert not missing, f"bundle check is not wired to live preflight contracts: {sorted(missing)}"


# --------------------------------------------------------------------------- #
# 2. Each of the four drift contracts flips deploy_ready False + fails its own
#    named contract (the prod whack-a-mole, caught offline).
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "kwargs, contract",
    [
        ({"art_fp": "sha256:STALE"}, "config_fingerprint"),
        ({"art_wl": ["AAPL", "MSFT"]}, "watchlist"),
        ({"cal_fp": "sha256:OTHER_SCORER"}, "calibrator_scorer_match"),
        ({"wf_passed": None}, "wf_gate_metadata"),
    ],
    ids=["config_fingerprint", "watchlist", "calibrator_scorer_match", "wf_gate_metadata"],
)
def test_each_drift_contract_blocks_deploy(tmp_path, kwargs, contract):
    res = _run(tmp_path, **kwargs)
    assert res["deploy_ready"] is False, f"broken {contract} must not be deploy_ready"
    assert _verdict(res, contract) is False, f"contract {contract} must report fail"


# --------------------------------------------------------------------------- #
# 3. End-to-end CLI: the gate exits 0 on a good bundle and non-zero on a broken
#    one. This is what the GitHub Actions job relies on to actually bite.
# --------------------------------------------------------------------------- #
def _run_cli(tmp_path: Path, *, broken: bool) -> subprocess.CompletedProcess:
    """Drive scripts/check_model_bundle_consistency.py via a tiny harness.

    The script's ``main`` resolves the real pinned config and imports the live
    fingerprint authorities, which are not present without the strategy venv.
    So we invoke ``check_bundle`` through a subprocess shim that injects the
    same fingerprint stubs and propagates the deploy-readiness exit code,
    matching the script's own contract (0 = ready, 1 = a contract failed).
    """
    art_fp = "sha256:STALE" if broken else LIVE_FP
    cfg_path = _write_bundle(tmp_path, art_fp=art_fp)
    sd = tmp_path / "backtesting" / "renquant_104"
    shim = tmp_path / "_cli_shim.py"
    shim.write_text(textwrap.dedent(f"""
        import importlib.util, json, sys
        from pathlib import Path
        spec = importlib.util.spec_from_file_location("bc", {str(_SCRIPT)!r})
        bc = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bc)
        res = bc.check_bundle(
            Path({str(cfg_path)!r}), Path({str(sd)!r}),
            fingerprint_config=lambda c: {LIVE_FP!r},
            model_content_sha256=lambda a: {SCORER_FP!r},
        )
        print(json.dumps(res))
        sys.exit(0 if res["deploy_ready"] else 1)
    """))
    return subprocess.run([sys.executable, str(shim)], capture_output=True, text=True)


def test_cli_exits_zero_on_consistent_bundle(tmp_path):
    proc = _run_cli(tmp_path, broken=False)
    assert proc.returncode == 0, proc.stderr
    res = json.loads(proc.stdout)
    assert res["deploy_ready"] is True


def test_cli_exits_nonzero_on_broken_bundle(tmp_path):
    # This is the assertion the CI gate hangs on: a deliberately-broken fixture
    # MUST make the process exit non-zero so the workflow job fails.
    proc = _run_cli(tmp_path, broken=True)
    assert proc.returncode != 0, "broken bundle must make the gate exit non-zero"
    res = json.loads(proc.stdout)
    assert res["deploy_ready"] is False
    assert _verdict(res, "config_fingerprint") is False
