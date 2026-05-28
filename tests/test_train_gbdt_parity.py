"""AUDIT REGRESSION GUARD — orchestrator GBDT trainer byte-identity.

renquant_orchestrator.train_gbdt assembles the production GBDT training as a
Task/Job/Pipeline (model-side from the renquant-model engine, data/contract Tasks
from the umbrella). Its artifact MUST be byte-identical to the umbrella's
scripts/train_production_model.py for the same args, excluding the two fields the
umbrella script randomizes (train_run_id=uuid4, trained_date=utcnow).

Skipped when the production panel dataset is absent (e.g. CI).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

GITHUB = Path(__file__).resolve().parents[2]
UMBRELLA = GITHUB / "RenQuant"
ORCH_SRC = Path(__file__).resolve().parents[1] / "src"
DATASET = UMBRELLA / "data" / "alpha158_291_fundamental_dataset.parquet"
STATS = UMBRELLA / "data" / "alpha158_qlib_dataset.stats.json"

pytestmark = pytest.mark.skipif(
    not (DATASET.exists() and STATS.exists()),
    reason="production panel dataset not present (skipped outside the workstation)",
)

RANDOMIZED = {"train_run_id", "trained_date"}
_ARGS = ["--train-cutoff", "2017-01-01", "--side-label", "paritytest", "--skip-cv"]


def _run(cmd: list[str], out: Path) -> None:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(ORCH_SRC), env.get("PYTHONPATH", "")])
    r = subprocess.run(cmd + ["--output-path", str(out)], cwd=str(UMBRELLA),
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0, f"{cmd} failed:\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}"


def test_orchestrator_gbdt_byte_identical_to_umbrella(tmp_path: Path) -> None:
    legacy = tmp_path / "walkforward_umbrella.json"        # 'walkforward' satisfies §5.13.13
    orchestrated = tmp_path / "walkforward_orchestrated.json"
    # Script mode: train_gbdt is self-contained (bootstraps its own pin paths),
    # so it needs neither the package __init__ (which pulls the full pin set via
    # daily.py) nor a pre-set PYTHONPATH.
    _run([sys.executable, str(UMBRELLA / "scripts" / "train_production_model.py")] + _ARGS, legacy)
    _run([sys.executable, str(ORCH_SRC / "renquant_orchestrator" / "train_gbdt.py")] + _ARGS, orchestrated)

    a = json.loads(legacy.read_text())
    b = json.loads(orchestrated.read_text())
    assert a.get("booster_raw_json") == b.get("booster_raw_json"), "booster diverged"
    assert a.get("config_fingerprint") == b.get("config_fingerprint"), "fingerprint diverged"
    diffs = [k for k in (set(a) | set(b)) if k not in RANDOMIZED and a.get(k) != b.get(k)]
    assert not diffs, f"non-identical fields (excluding randomized): {diffs}"
