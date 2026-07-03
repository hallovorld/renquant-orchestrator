"""Unit tests for the S8 pick-table regeneration driver (thin, run-gated on
backtesting #59).

NO real scoring anywhere here: the backtesting subprocess seam
(`_run_subprocess`) is monkeypatched with fakes that mimic the #59 contract
surface (analyzer writes staging parquet + sidecar + result JSON;
verify_pick_table returns a verification dict). What IS exercised for real:
command construction, the exp-path refusal, the faithfulness/counts gate
logic, staging->final promotion, and the wiring order.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "regen_oos_pick_table.py"
_spec = importlib.util.spec_from_file_location("regen_oos_pick_table", _SCRIPT)
driver = importlib.util.module_from_spec(_spec)
sys.modules["regen_oos_pick_table"] = driver  # dataclasses need the module registered
_spec.loader.exec_module(driver)


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _mk_tree(tmp_path: Path) -> tuple[Path, Path]:
    """Minimal umbrella + backtesting trees (inputs only, no data)."""
    umbrella = tmp_path / "RenQuant"
    (umbrella / "data" / "exp").mkdir(parents=True)
    manifest = umbrella / driver.REL_MANIFEST
    artifact = umbrella / driver.REL_ARTIFACT
    manifest.parent.mkdir(parents=True, exist_ok=True)
    artifact.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text("{}")
    artifact.write_text("{}")
    backtesting = tmp_path / "renquant-backtesting"
    (backtesting / "src").mkdir(parents=True)
    return umbrella, backtesting


def _cfg(umbrella: Path, backtesting: Path, *extra: str) -> "driver.DriverConfig":
    return driver.resolve_config(driver.parse_args([
        "--umbrella-root", str(umbrella),
        "--backtesting-root", str(backtesting),
        *extra,
    ]))


def _completed(argv, rc=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(list(argv), rc, stdout, stderr)


#: Fresh-run sanity JSON whose genuine_ic (aligned - placebo) = 0.0415 — the
#: A1 reproduction vs the committed 0.041681 (delta 0.00018 < 0.001).
GOOD_INTERP = {"aligned_real_60_ic": 0.05, "placebo_60_ic": 0.0085}
GOOD_SIDECAR_COUNTS = {"n_rows": 147066, "n_dates": 508, "n_names": 292}


class FakeBacktesting:
    """Mimics the #59 subprocess surface without any scoring."""

    def __init__(self, *, interp=None, counts=None, preflight_rc=0,
                 verify_rc=0, fresh_anchor="FRESH_ANCHOR"):
        self.interp = dict(GOOD_INTERP if interp is None else interp)
        self.counts = dict(GOOD_SIDECAR_COUNTS if counts is None else counts)
        self.preflight_rc = preflight_rc
        self.verify_rc = verify_rc
        self.fresh_anchor = fresh_anchor
        self.calls: list[list[str]] = []

    def __call__(self, argv, *, env, cwd, timeout=0):
        argv = list(argv)
        self.calls.append(argv)
        if argv[1] == "-m":  # the analyzer invocation
            dump = Path(argv[argv.index("--dump-predictions") + 1])
            outdir = Path(argv[argv.index("--output-dir") + 1])
            artifact = Path(argv[argv.index("--artifact") + 1])
            dump.parent.mkdir(parents=True, exist_ok=True)
            dump.write_bytes(b"PARQUET_BYTES")
            # exactly the contract's default_sidecar_path construction
            sidecar = dump.with_suffix("").with_suffix(".manifest.json")
            sidecar.write_text(json.dumps({
                "counts": self.counts,
                "output": {"output_content_sha256": self.fresh_anchor},
                "recipe": {"label": "fwd_60d_excess"},
            }))
            outdir.mkdir(parents=True, exist_ok=True)
            result = outdir / (artifact.stem.replace(".", "_") + ".json")
            result.write_text(json.dumps({"interpretation": self.interp}))
            return _completed(argv, 0, stdout="{}")
        assert argv[1] == "-c"
        if "import inspect" in argv[2]:  # the preflight snippet
            return _completed(argv, self.preflight_rc,
                              stdout=json.dumps({"ok": self.preflight_rc == 0}))
        # the verify snippet (verify_pick_table(sys.argv[1], sys.argv[2]))
        return _completed(argv, self.verify_rc, stdout=json.dumps({
            "content_sha256": self.fresh_anchor, "content_verified": True,
            "counts_verified": True, "parquet_sha256": "T",
            "parquet_transport_match": False,
        }))


# --------------------------------------------------------------------------
# dry-run correctness (testable without #59)
# --------------------------------------------------------------------------

def test_dry_run_prints_exact_commands_and_executes_nothing(tmp_path, capsys, monkeypatch):
    umbrella, backtesting = _mk_tree(tmp_path)

    def _no_subprocess(*a, **k):  # dry-run must never spawn anything
        raise AssertionError("dry-run executed a subprocess")

    monkeypatch.setattr(driver, "_run_subprocess", _no_subprocess)
    rc = driver.main(["--dry-run", "--umbrella-root", str(umbrella),
                      "--backtesting-root", str(backtesting)])
    assert rc == 0
    plan = json.loads(capsys.readouterr().out)
    cmd = plan["commands"]["2_analyzer"]
    assert cmd[1:3] == ["-m", driver.ANALYZER_MODULE]
    assert cmd[cmd.index("--manifest") + 1].endswith(
        "walkforward_manifest_gbdt_prod_recipe_v2.json")
    dump = Path(cmd[cmd.index("--dump-predictions") + 1])
    assert dump.name == "oos_pick_table_recipe_v2__staging.parquet"
    assert str(dump).startswith(str((umbrella / "data" / "exp").resolve()))
    assert cmd[cmd.index("--label") + 1] == "fwd_60d_excess"
    # the driver must never disarm the contract-side research-only path guard
    for c in plan["commands"].values():
        assert "--allow-production-path" not in c
    env = plan["env_overrides"]
    assert env["RENQUANT_REPO_ROOT"] == str(umbrella.resolve())
    assert str((backtesting / "src").resolve()) in env["PYTHONPATH"]
    # final artifact paths + run-gate statement present
    assert plan["paths"]["final_parquet"].endswith("data/exp/oos_pick_table_recipe_v2.parquet")
    assert "#59" in plan["run_gate"]
    # nothing was written
    assert list((umbrella / "data" / "exp").iterdir()) == []


def test_staging_sidecar_matches_contract_default_sidecar_path():
    parquet, staging_sidecar, final_sidecar = driver.staging_paths(
        Path("/u/data/exp/oos_pick_table_recipe_v2.parquet"))
    # pinned to #59 pick_table.default_sidecar_path: with_suffix('') twice
    assert staging_sidecar == parquet.with_suffix("").with_suffix(".manifest.json")
    assert staging_sidecar != final_sidecar  # a failed run cannot clobber the committed sidecar
    assert final_sidecar.name == "oos_pick_table_recipe_v2.manifest.json"


# --------------------------------------------------------------------------
# refusal of non-data/exp output paths (no override)
# --------------------------------------------------------------------------

@pytest.mark.parametrize("rel", [
    "data/oos_pick_table_recipe_v2.parquet",           # canonical data/ (prod)
    "data/expansion/oos.parquet",                      # not data/exp/
    "backtesting/renquant_104/artifacts/sim/oos.parquet",  # artifacts tree
])
def test_refuses_non_exp_output_paths(tmp_path, rel):
    umbrella, backtesting = _mk_tree(tmp_path)
    rc = driver.main(["--dry-run", "--umbrella-root", str(umbrella),
                      "--backtesting-root", str(backtesting),
                      "--output", str(umbrella / rel)])
    assert rc == 2


def test_refuses_output_outside_the_umbrella_exp_area(tmp_path):
    umbrella, backtesting = _mk_tree(tmp_path)
    elsewhere = tmp_path / "elsewhere" / "data" / "exp" / "oos.parquet"
    rc = driver.main(["--dry-run", "--umbrella-root", str(umbrella),
                      "--backtesting-root", str(backtesting),
                      "--output", str(elsewhere)])
    assert rc == 2


def test_exp_path_accepts_the_sanctioned_area(tmp_path):
    umbrella, _ = _mk_tree(tmp_path)
    driver.ensure_exp_path(umbrella / "data" / "exp" / "x.parquet", umbrella)
    with pytest.raises(driver.DriverSetupError):
        driver.ensure_exp_path(umbrella / "data" / "x.parquet", umbrella)


# --------------------------------------------------------------------------
# faithfulness gate on fixtures
# --------------------------------------------------------------------------

def test_faithfulness_gate_passes_the_a1_bar():
    out = driver.faithfulness_gate({"interpretation": dict(GOOD_INTERP)},
                                   driver.COMMITTED_GENUINE_IC, 0.001)
    assert out["fresh_genuine_ic"] == pytest.approx(0.0415)
    assert out["abs_delta"] <= 0.001


def test_faithfulness_gate_hard_fails_outside_tolerance():
    with pytest.raises(driver.GateError, match="FAITHFULNESS GATE FAILED"):
        driver.faithfulness_gate(
            {"interpretation": {"aligned_real_60_ic": 0.09, "placebo_60_ic": 0.0085}},
            driver.COMMITTED_GENUINE_IC, 0.001)


def test_faithfulness_gate_fails_closed_on_missing_fields():
    with pytest.raises(driver.GateError, match="failing closed"):
        driver.faithfulness_gate({}, driver.COMMITTED_GENUINE_IC, 0.001)
    with pytest.raises(driver.GateError, match="failing closed"):
        driver.faithfulness_gate(
            {"interpretation": {"aligned_real_60_ic": 0.05, "placebo_60_ic": None}},
            driver.COMMITTED_GENUINE_IC, 0.001)
    with pytest.raises(driver.GateError, match="NaN"):
        driver.faithfulness_gate(
            {"interpretation": {"aligned_real_60_ic": float("nan"), "placebo_60_ic": 0.0}},
            driver.COMMITTED_GENUINE_IC, 0.001)


# --------------------------------------------------------------------------
# row-count sanity gate
# --------------------------------------------------------------------------

def test_counts_gate_passes_committed_shape():
    out = driver.counts_gate({"counts": dict(GOOD_SIDECAR_COUNTS)},
                             expected_dates=508, expected_rows=147066,
                             rows_tolerance_pct=1.0)
    assert out["n_rows"] == 147066 and out["n_dates"] == 508


@pytest.mark.parametrize("counts", [
    {"n_rows": 147066, "n_dates": 507},   # date-count drift
    {"n_rows": 140000, "n_dates": 508},   # >1% row loss
    {},                                    # missing counts -> fail closed
])
def test_counts_gate_fails_on_drift(counts):
    with pytest.raises(driver.GateError):
        driver.counts_gate({"counts": counts} if counts else {},
                           expected_dates=508, expected_rows=147066,
                           rows_tolerance_pct=1.0)


# --------------------------------------------------------------------------
# mocked end-to-end wiring (subprocess seam faked; no scoring)
# --------------------------------------------------------------------------

def test_run_pass_promotes_staging_and_verifies_final(tmp_path, capsys, monkeypatch):
    umbrella, backtesting = _mk_tree(tmp_path)
    cfg = _cfg(umbrella, backtesting)
    _, staging_sidecar, final_sidecar = driver.staging_paths(cfg.output)
    # a pre-existing committed sidecar with a DIFFERENT anchor
    final_sidecar.parent.mkdir(parents=True, exist_ok=True)
    final_sidecar.write_text(json.dumps({"output": {"output_content_sha256": "OLD_ANCHOR"}}))

    fake = FakeBacktesting()
    monkeypatch.setattr(driver, "_run_subprocess", fake)
    assert driver.run(cfg) == 0

    # staging was promoted to the final exp paths
    assert cfg.output.read_bytes() == b"PARQUET_BYTES"
    assert not cfg.output.with_name(cfg.output.stem + "__staging.parquet").exists()
    assert not staging_sidecar.exists()
    assert json.loads(final_sidecar.read_text())["counts"] == GOOD_SIDECAR_COUNTS

    # wiring order: preflight -> analyzer -> verify(FINAL paths)
    kinds = ["analyzer" if c[1] == "-m" else
             ("preflight" if "import inspect" in c[2] else "verify")
             for c in fake.calls]
    assert kinds == ["preflight", "analyzer", "verify"]
    verify_argv = fake.calls[-1]
    assert verify_argv[-2] == str(cfg.output)
    assert verify_argv[-1] == str(final_sidecar)
    assert all("--allow-production-path" not in c for c in fake.calls)

    summary = json.loads(capsys.readouterr().out)
    assert summary["status"] == "PASS"
    assert summary["post_write_verification"]["content_verified"] is True
    # the #430 anchor comparison is REPORTED, not gated
    assert summary["content_anchor"] == {
        "committed_anchor": "OLD_ANCHOR", "fresh_anchor": "FRESH_ANCHOR",
        "reproduced": False, "note": summary["content_anchor"]["note"],
    }


def test_run_faithfulness_fail_never_touches_final_path(tmp_path, monkeypatch):
    umbrella, backtesting = _mk_tree(tmp_path)
    cfg = _cfg(umbrella, backtesting)
    _, staging_sidecar, final_sidecar = driver.staging_paths(cfg.output)
    final_sidecar.parent.mkdir(parents=True, exist_ok=True)
    final_sidecar.write_text(json.dumps({"output": {"output_content_sha256": "OLD_ANCHOR"}}))

    fake = FakeBacktesting(interp={"aligned_real_60_ic": 0.30, "placebo_60_ic": 0.0})
    monkeypatch.setattr(driver, "_run_subprocess", fake)
    with pytest.raises(driver.GateError, match="FAITHFULNESS"):
        driver.run(cfg)

    assert not cfg.output.exists()  # final parquet never written
    # committed sidecar untouched; staging left in place for forensics
    assert json.loads(final_sidecar.read_text()) == {
        "output": {"output_content_sha256": "OLD_ANCHOR"}}
    assert staging_sidecar.exists()
    assert cfg.output.with_name(cfg.output.stem + "__staging.parquet").exists()
    # verify_pick_table was never invoked after the failed gate
    assert all("import inspect" in c[2] for c in fake.calls if c[1] == "-c")


def test_run_counts_fail_blocks_promotion(tmp_path, monkeypatch):
    umbrella, backtesting = _mk_tree(tmp_path)
    cfg = _cfg(umbrella, backtesting)
    fake = FakeBacktesting(counts={"n_rows": 147066, "n_dates": 400, "n_names": 292})
    monkeypatch.setattr(driver, "_run_subprocess", fake)
    with pytest.raises(driver.GateError, match="COUNTS"):
        driver.run(cfg)
    assert not cfg.output.exists()


def test_run_gate_closed_without_59_contract(tmp_path, monkeypatch):
    umbrella, backtesting = _mk_tree(tmp_path)
    cfg = _cfg(umbrella, backtesting)
    fake = FakeBacktesting(preflight_rc=1)
    monkeypatch.setattr(driver, "_run_subprocess", fake)
    with pytest.raises(driver.DriverSetupError, match="#59"):
        driver.run(cfg)
    assert len(fake.calls) == 1  # nothing after the closed run gate


def test_post_write_verification_failure_is_a_gate_failure(tmp_path, monkeypatch):
    umbrella, backtesting = _mk_tree(tmp_path)
    cfg = _cfg(umbrella, backtesting)
    fake = FakeBacktesting(verify_rc=1)
    monkeypatch.setattr(driver, "_run_subprocess", fake)
    with pytest.raises(driver.GateError, match="POST-WRITE VERIFICATION FAILED"):
        driver.run(cfg)


def test_main_maps_gate_failures_to_exit_1(tmp_path, monkeypatch, capsys):
    umbrella, backtesting = _mk_tree(tmp_path)
    fake = FakeBacktesting(interp={"aligned_real_60_ic": 0.30, "placebo_60_ic": 0.0})
    monkeypatch.setattr(driver, "_run_subprocess", fake)
    rc = driver.main(["--umbrella-root", str(umbrella),
                      "--backtesting-root", str(backtesting)])
    assert rc == 1
    assert "GATE FAILED" in capsys.readouterr().err
