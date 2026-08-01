"""Tests for scripts/check_twin_parity.py (#454 R0 twin-parity tripwires).

Two layers:

1. Synthetic-fixture tests (always run, incl. GitHub CI): a miniature
   sibling-repo tree in tmp_path exercises every pass/fail/skip path of the
   checker logic.
2. Live integration test: runs the REAL checks against whatever actual
   sibling checkouts exist plus the COMMITTED manifest.  Check groups whose
   siblings are absent SKIP loudly.  Orchestrator GitHub CI checks out
   renquant-execution/renquant-pipeline @ main but NOT the umbrella, so CI
   enforces the constant/function/tax pins while the live/-twin checks are
   only enforced by ``make test`` on the deploy machine — which is exactly
   where that drift matters (the live path executes from the umbrella
   sibling checkout).  CI green does NOT certify umbrella-twin parity.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import check_twin_parity as ctp


# ---------------------------------------------------------------------------
# Synthetic sibling tree
# ---------------------------------------------------------------------------

_IDENTICAL_ALERTS = "def send_alert(msg):\n    return msg\n"
_IDENTICAL_IBKR = "class IBKRBroker:\n    pass\n"

_UMB_BROKER = "class Broker:\n    side = 'umbrella'\n"
_EXE_BROKER = (
    "MIN_FRACTIONAL_NOTIONAL_USD = 1.0\n"
    "class Broker:\n    side = 'execution'\n"
)
_UMB_ALPACA = "class AlpacaBroker:\n    side = 'umbrella'\n"
_EXE_ALPACA = "class AlpacaBroker:\n    side = 'execution'\n"
_UMB_PAPER = "class PaperBroker:\n    rich = True\n"
_EXE_PAPER = "class PaperBroker:\n    rich = False\n"
_UMB_READONLY = "class ReadOnlyBroker:\n    side = 'umbrella'\n"
_EXE_READONLY = "class ReadOnlyBroker:\n    side = 'execution'\n"

_INTENT_FN = (
    "def compute_parent_intent_id(*, account, symbol, trading_day, side, signal_version):\n"
    "    payload = _FIELD_SEP.join([account, symbol, trading_day, side, signal_version])\n"
    "    return 'pi-' + payload\n"
)
_EXE_OSM = '_FIELD_SEP = "\\x1f"\n\n' + _INTENT_FN
_PIPE_INTRADAY = '_FIELD_SEP = "\\x1f"\n\n' + _INTENT_FN

_PIPE_SIZING = "MIN_FRACTIONAL_NOTIONAL_USD = 1.0\n"
_PIPE_ROTATION = (
    "def a(tax_cfg):\n"
    '    st = float(tax_cfg.get("short_term_rate", 0.50))\n'
    '    lt = float(tax_cfg.get("long_term_rate", 0.32))\n'
    "def b(tax_cfg):\n"
    '    st = float(tax_cfg.get("short_term_rate", 0.50))\n'
    '    lt = float(tax_cfg.get("long_term_rate", 0.32))\n'
    "def c(tax_cfg):\n"
    '    st = float(tax_cfg.get("short_term_rate", 0.50))\n'
    '    lt = float(tax_cfg.get("long_term_rate", 0.32))\n'
)
_PIPE_QP_TASKS = (
    "def qp(cfg):\n"
    '    st_rate = float(cfg.get("qp_tax_rate_st", 0.30))\n'
    '    lt_rate = float(cfg.get("qp_tax_rate_lt", 0.15))\n'
)
_PIPE_SELECTION = (
    "def wash_sale_npv_cost(loss, tax_rate: float = 0.30, discount_rate=0.04):\n"
    "    return loss * tax_rate\n"
    "def selection_score(pl, tax_rate: float = 0.30):\n"
    "    return pl * tax_rate\n"
)


def _write(root: Path, rel: str, content: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


@pytest.fixture
def sibling_tree(tmp_path):
    """Miniature RenQuant / renquant-execution / renquant-pipeline layout."""
    umbrella = tmp_path / "RenQuant"
    execution = tmp_path / "renquant-execution"
    pipeline = tmp_path / "renquant-pipeline"

    _write(umbrella, "live/alerts.py", _IDENTICAL_ALERTS)
    _write(execution, "src/renquant_execution/alerts.py", _IDENTICAL_ALERTS)
    _write(umbrella, "live/ibkr_broker.py", _IDENTICAL_IBKR)
    _write(execution, "src/renquant_execution/ibkr_broker.py", _IDENTICAL_IBKR)

    _write(umbrella, "live/broker.py", _UMB_BROKER)
    _write(execution, "src/renquant_execution/broker.py", _EXE_BROKER)
    _write(umbrella, "live/alpaca_broker.py", _UMB_ALPACA)
    _write(execution, "src/renquant_execution/alpaca_broker.py", _EXE_ALPACA)
    _write(umbrella, "live/paper_broker.py", _UMB_PAPER)
    _write(execution, "src/renquant_execution/paper_broker.py", _EXE_PAPER)
    _write(umbrella, "live/broker_readonly.py", _UMB_READONLY)
    _write(execution, "src/renquant_execution/readonly_broker.py", _EXE_READONLY)

    _write(execution, "src/renquant_execution/order_state_machine.py", _EXE_OSM)
    _write(pipeline, "src/renquant_pipeline/intraday_decisioning.py", _PIPE_INTRADAY)
    _write(pipeline, "src/renquant_pipeline/kernel/sizing.py", _PIPE_SIZING)
    _write(pipeline, "src/renquant_pipeline/kernel/rotation.py", _PIPE_ROTATION)
    _write(pipeline, "src/renquant_pipeline/kernel/portfolio_qp/tasks.py", _PIPE_QP_TASKS)
    _write(pipeline, "src/renquant_pipeline/kernel/selection.py", _PIPE_SELECTION)

    repos = ctp.resolve_repos(tmp_path)
    assert all(repos.values()), repos
    # kernel shelf + meta_label twins (orch#734/#728): shelf pairs byte-identical,
    # meta_label pairs carrying exactly the 4-line import-rewrite divergence.
    for kern_rel, pinned_rel in ctp.KERNEL_SHELF_TWINS:
        for rel in (kern_rel, pinned_rel):
            f = umbrella / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(f"# shared shelf module {Path(kern_rel).name}\n")
    for kern_rel, pinned_rel in ctp.KERNEL_META_LABEL_TWINS:
        a, b = umbrella / kern_rel, umbrella / pinned_rel
        a.parent.mkdir(parents=True, exist_ok=True)
        b.parent.mkdir(parents=True, exist_ok=True)
        a.write_text("from kernel.pipeline.pipeline import Task\n# body\n")
        b.write_text("from renquant_common.pipeline import Task\n# body\n")
    return tmp_path, repos


def _fails(results):
    return [r for r in results if r.status == "FAIL"]


def _statuses(results):
    return {r.name: r.status for r in results}


# ---------------------------------------------------------------------------
# Synthetic: happy path + manifest roundtrip
# ---------------------------------------------------------------------------

def test_synthetic_all_pass(sibling_tree):
    _, repos = sibling_tree
    manifest = ctp.build_manifest(repos)
    results = ctp.run_checks(repos, manifest)
    assert not _fails(results), _statuses(results)
    assert all(r.status == "PASS" for r in results)


def test_manifest_json_roundtrip(sibling_tree, tmp_path):
    _, repos = sibling_tree
    manifest = ctp.build_manifest(repos)
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True))
    results = ctp.run_checks(repos, ctp.load_manifest(path))
    assert not _fails(results)


def test_manifest_pins_expected_shape(sibling_tree):
    _, repos = sibling_tree
    manifest = ctp.build_manifest(repos)
    assert set(manifest["diverged_twins"]) == {
        "broker", "alpaca_broker", "paper_broker", "readonly_broker",
    }
    assert manifest["constants"]["MIN_FRACTIONAL_NOTIONAL_USD"] == 1.0
    fn = manifest["function_pins"]["compute_parent_intent_id"]
    assert len(fn["pipeline_sha256"]) == 64 and len(fn["execution_sha256"]) == 64
    tax = manifest["tax_conventions"]
    assert tax["rotation_short_term_rate"] == {"values": [0.5], "count": 3}
    assert tax["rotation_long_term_rate"] == {"values": [0.32], "count": 3}
    assert tax["qp_tax_rate_st"] == {"values": [0.3], "count": 1}
    assert tax["qp_tax_rate_lt"] == {"values": [0.15], "count": 1}
    assert tax["selection_tax_rate"] == {"values": [0.3], "count": 2}


# ---------------------------------------------------------------------------
# Synthetic: each tripwire fires
# ---------------------------------------------------------------------------

def test_byte_identical_drift_fails(sibling_tree):
    tmp_path, repos = sibling_tree
    manifest = ctp.build_manifest(repos)
    _write(tmp_path / "RenQuant", "live/alerts.py", _IDENTICAL_ALERTS + "# hotfix on one side only\n")
    fails = _fails(ctp.run_checks(repos, manifest))
    assert [f.name for f in fails] == ["byte_identical:alerts.py"]
    assert "DIVERGED" in fails[0].detail


def test_byte_identical_lockstep_change_passes(sibling_tree):
    tmp_path, repos = sibling_tree
    manifest = ctp.build_manifest(repos)
    new = _IDENTICAL_ALERTS + "# same change on BOTH sides\n"
    _write(tmp_path / "RenQuant", "live/alerts.py", new)
    _write(tmp_path / "renquant-execution", "src/renquant_execution/alerts.py", new)
    assert not _fails(ctp.run_checks(repos, manifest))


def test_diverged_umbrella_side_change_fails(sibling_tree):
    tmp_path, repos = sibling_tree
    manifest = ctp.build_manifest(repos)
    _write(tmp_path / "RenQuant", "live/broker.py", _UMB_BROKER + "# umbrella edit\n")
    fails = _fails(ctp.run_checks(repos, manifest))
    assert [f.name for f in fails] == ["diverged_pin:broker"]
    assert "umbrella side changed" in fails[0].detail


def test_diverged_execution_side_change_fails(sibling_tree):
    tmp_path, repos = sibling_tree
    manifest = ctp.build_manifest(repos)
    _write(tmp_path / "renquant-execution", "src/renquant_execution/readonly_broker.py",
           _EXE_READONLY + "# execution edit\n")
    fails = _fails(ctp.run_checks(repos, manifest))
    assert [f.name for f in fails] == ["diverged_pin:readonly_broker"]
    assert "execution side changed" in fails[0].detail


def test_diverged_twin_file_deletion_fails(sibling_tree):
    tmp_path, repos = sibling_tree
    manifest = ctp.build_manifest(repos)
    (tmp_path / "RenQuant" / "live" / "paper_broker.py").unlink()
    fails = _fails(ctp.run_checks(repos, manifest))
    assert [f.name for f in fails] == ["diverged_pin:paper_broker"]
    assert "missing" in fails[0].detail


def test_min_fractional_parity_break_fails(sibling_tree):
    tmp_path, repos = sibling_tree
    manifest = ctp.build_manifest(repos)
    _write(tmp_path / "renquant-pipeline", "src/renquant_pipeline/kernel/sizing.py",
           "MIN_FRACTIONAL_NOTIONAL_USD = 2.0\n")
    fails = _fails(ctp.run_checks(repos, manifest))
    names = [f.name for f in fails]
    assert "constant:MIN_FRACTIONAL_NOTIONAL_USD" in names
    [c] = [f for f in fails if f.name == "constant:MIN_FRACTIONAL_NOTIONAL_USD"]
    assert "parity broken" in c.detail


def test_min_fractional_lockstep_change_without_repin_fails(sibling_tree):
    tmp_path, repos = sibling_tree
    manifest = ctp.build_manifest(repos)
    _write(tmp_path / "renquant-pipeline", "src/renquant_pipeline/kernel/sizing.py",
           "MIN_FRACTIONAL_NOTIONAL_USD = 2.0\n")
    _write(tmp_path / "renquant-execution", "src/renquant_execution/broker.py",
           _EXE_BROKER.replace("1.0", "2.0"))
    results = ctp.run_checks(repos, manifest)
    [c] = [f for f in _fails(results) if f.name == "constant:MIN_FRACTIONAL_NOTIONAL_USD"]
    assert "manifest pins" in c.detail  # both sides moved: still needs the review act


def test_parent_intent_function_change_fails(sibling_tree):
    tmp_path, repos = sibling_tree
    manifest = ctp.build_manifest(repos)
    _write(tmp_path / "renquant-execution", "src/renquant_execution/order_state_machine.py",
           _EXE_OSM.replace("'pi-'", "'PI-'"))
    fails = _fails(ctp.run_checks(repos, manifest))
    assert [f.name for f in fails] == ["function_pin:compute_parent_intent_id"]
    assert "execution" in fails[0].detail


def test_field_sep_divergence_fails(sibling_tree):
    tmp_path, repos = sibling_tree
    manifest = ctp.build_manifest(repos)
    _write(tmp_path / "renquant-pipeline", "src/renquant_pipeline/intraday_decisioning.py",
           _PIPE_INTRADAY.replace('"\\x1f"', '"|"'))
    fails = _fails(ctp.run_checks(repos, manifest))
    names = [f.name for f in fails]
    # the function-source pin stays intact (constant lives outside the def),
    # so _FIELD_SEP needs its own tripwire — this is it
    assert names == ["function_pin:_FIELD_SEP"]


def test_tax_default_value_change_fails(sibling_tree):
    tmp_path, repos = sibling_tree
    manifest = ctp.build_manifest(repos)
    _write(tmp_path / "renquant-pipeline", "src/renquant_pipeline/kernel/portfolio_qp/tasks.py",
           _PIPE_QP_TASKS.replace("0.15", "0.20"))
    fails = _fails(ctp.run_checks(repos, manifest))
    assert [f.name for f in fails] == ["tax_pin:qp_tax_rate_lt"]


def test_tax_new_call_site_fails(sibling_tree):
    tmp_path, repos = sibling_tree
    manifest = ctp.build_manifest(repos)
    _write(tmp_path / "renquant-pipeline", "src/renquant_pipeline/kernel/rotation.py",
           _PIPE_ROTATION + 'def d(tax_cfg):\n    st = float(tax_cfg.get("short_term_rate", 0.50))\n')
    fails = _fails(ctp.run_checks(repos, manifest))
    # same VALUE, new hand-copied site: count pin fires (the audit's
    # duplication class), value set unchanged
    assert [f.name for f in fails] == ["tax_pin:rotation_short_term_rate"]
    assert "(x4)" in fails[0].detail


def test_selection_param_default_change_fails(sibling_tree):
    tmp_path, repos = sibling_tree
    manifest = ctp.build_manifest(repos)
    _write(tmp_path / "renquant-pipeline", "src/renquant_pipeline/kernel/selection.py",
           _PIPE_SELECTION.replace("tax_rate: float = 0.30)", "tax_rate: float = 0.37)"))
    fails = _fails(ctp.run_checks(repos, manifest))
    assert [f.name for f in fails] == ["tax_pin:selection_tax_rate"]


# ---------------------------------------------------------------------------
# Synthetic: skip semantics + CLI
# ---------------------------------------------------------------------------

def test_missing_siblings_all_skip(tmp_path):
    repos = ctp.resolve_repos(tmp_path)  # empty dir: no siblings
    assert repos == {"umbrella": None, "execution": None, "pipeline": None}
    results = ctp.run_checks(repos, {})
    assert results and all(r.status == "SKIP" for r in results)
    assert all("NOT verified" in r.detail for r in results)


def test_cli_skip_exits_zero(tmp_path, capsys):
    empty = tmp_path / "empty"
    empty.mkdir()
    rc = ctp.main(["--siblings-root", str(empty)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "SKIPPED" in out and "NOT verified" in out


def test_cli_strict_missing_exits_one(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    assert ctp.main(["--siblings-root", str(empty), "--strict-missing"]) == 1


def test_cli_missing_manifest_exits_one(sibling_tree, tmp_path):
    root, _ = sibling_tree
    rc = ctp.main(["--siblings-root", str(root), "--manifest", str(tmp_path / "nope.json")])
    assert rc == 1


def test_cli_write_manifest_then_check_roundtrip(sibling_tree, tmp_path):
    root, _ = sibling_tree
    manifest_path = tmp_path / "m.json"
    assert ctp.main(["--siblings-root", str(root), "--manifest", str(manifest_path), "--write-manifest"]) == 0
    assert manifest_path.is_file()
    assert ctp.main(["--siblings-root", str(root), "--manifest", str(manifest_path)]) == 0


def test_cli_detects_drift_exit_one(sibling_tree, tmp_path):
    root, _ = sibling_tree
    manifest_path = tmp_path / "m.json"
    ctp.main(["--siblings-root", str(root), "--manifest", str(manifest_path), "--write-manifest"])
    _write(root / "RenQuant", "live/broker.py", _UMB_BROKER + "# drift\n")
    assert ctp.main(["--siblings-root", str(root), "--manifest", str(manifest_path)]) == 1


def test_build_manifest_requires_all_siblings(tmp_path):
    with pytest.raises(RuntimeError, match="missing sibling repos"):
        ctp.build_manifest(ctp.resolve_repos(tmp_path))


# ---------------------------------------------------------------------------
# Live integration (deploy machine only — the actual tripwire)
# ---------------------------------------------------------------------------

def _live_repos():
    env = os.environ.get("RENQUANT_SIBLINGS_ROOT")
    return ctp.resolve_repos(Path(env) if env else None)


_live = _live_repos()
_live_any = any(_live.values()) and ctp.MANIFEST_DEFAULT.is_file()


@pytest.mark.skipif(
    not _live_any,
    reason=(
        "no sibling repos found (or manifest missing) — twin parity NOT "
        "verified in this environment; the full tripwire runs via `make "
        "test` on the deploy machine, which is where drift matters"
    ),
)
def test_live_twin_parity_manifest_current():
    """THE tripwire: real siblings vs the committed manifest.

    Runs granularly against whatever siblings exist: orchestrator GitHub CI
    checks out renquant-execution + renquant-pipeline @ main (so the
    constant/function/tax pins ARE enforced at merge time, per #454 §5.1)
    but NOT the umbrella — the live/-twin checks skip there and are only
    enforced by `make test` on the deploy machine, whose umbrella tree is
    the code that actually trades.

    If this fails, a known twin/constant changed without the deliberate
    manifest re-pin — see scripts/check_twin_parity.py output for the side
    that moved, land the change on both stacks (or review the divergence),
    and re-pin via --write-manifest in the same PR.  A CI-vs-deploy-machine
    disagreement (siblings @ main vs @ deployed pin) is the T1
    evidence-vs-live lag made visible — sync the pins, don't loosen the pin.
    """
    manifest = ctp.load_manifest(ctp.MANIFEST_DEFAULT)
    results = ctp.run_checks(_live_repos(), manifest)
    fails = _fails(results)
    assert not fails, "twin-parity tripwire fired:\n" + "\n".join(
        f"[{r.status}] {r.name}: {r.detail}" for r in results
    )
    if all(r.status == "SKIP" for r in results):  # pragma: no cover — guarded by skipif
        pytest.skip("all twin-parity groups skipped — no sibling repos found")


# ------------------------------ kernel shelf + meta_label pins (orch#734/#728) ----

def _mini_umbrella(tmp_path, shelf_equal=True, pin_shift=None):
    """A tiny umbrella tree carrying ONE shelf pair and ONE pinned meta_label pair."""
    u = tmp_path / "umb"
    a = u / "backtesting/renquant_104/kernel/metrics/hac_se.py"
    b = u / ".subrepo_runtime/repos/renquant-common/src/renquant_common/metrics/hac_se.py"
    for f in (a, b):
        f.parent.mkdir(parents=True, exist_ok=True)
    a.write_text("SHELF\n")
    b.write_text("SHELF\n" if shelf_equal else "SHELF CHANGED\n")
    ma = u / "backtesting/renquant_104/kernel/meta_label/task_snapshot.py"
    mb = u / ".subrepo_runtime/repos/renquant-backtesting/src/renquant_backtesting/meta_label/task_snapshot.py"
    for f in (ma, mb):
        f.parent.mkdir(parents=True, exist_ok=True)
    ma.write_text("from kernel.pipeline.pipeline import Task\n")
    mb.write_text("from renquant_common.pipeline import Task\n")
    if pin_shift == "umbrella":
        ma.write_text(ma.read_text() + "# edited\n")
    if pin_shift == "pinned":
        mb.write_text(mb.read_text() + "# pin advanced\n")
    import hashlib as _h
    pin = {"task_snapshot": {
        "umbrella_path": "backtesting/renquant_104/kernel/meta_label/task_snapshot.py",
        "umbrella_sha256": _h.sha256(b"from kernel.pipeline.pipeline import Task\n").hexdigest(),
        "pinned_backtesting_path": ".subrepo_runtime/repos/renquant-backtesting/src/renquant_backtesting/meta_label/task_snapshot.py",
        "pinned_sha256": _h.sha256(b"from renquant_common.pipeline import Task\n").hexdigest(),
    }}
    return u, {"kernel_meta_label_twins": pin}


def _shelf_only(mod, u):
    orig = mod.KERNEL_SHELF_TWINS
    mod.KERNEL_SHELF_TWINS = [orig[1][:]] if False else [
        ("backtesting/renquant_104/kernel/metrics/hac_se.py",
         ".subrepo_runtime/repos/renquant-common/src/renquant_common/metrics/hac_se.py")]
    return orig


def test_kernel_shelf_identical_passes(tmp_path):
    u, man = _mini_umbrella(tmp_path, shelf_equal=True)
    orig = _shelf_only(ctp, u)
    try:
        rs = ctp.check_kernel_shelf_twins({"umbrella": u})
    finally:
        ctp.KERNEL_SHELF_TWINS = orig
    assert [r.status for r in rs] == ["PASS"], rs


def test_kernel_shelf_divergence_FAILS_with_the_A6_instruction(tmp_path):
    u, man = _mini_umbrella(tmp_path, shelf_equal=False)
    orig = _shelf_only(ctp, u)
    try:
        rs = ctp.check_kernel_shelf_twins({"umbrella": u})
    finally:
        ctp.KERNEL_SHELF_TWINS = orig
    assert rs[0].status == "FAIL"
    assert "DIVERGED" in rs[0].detail and "reviewed PR" in rs[0].detail


def test_metalabel_pin_matches_both_sides(tmp_path):
    u, man = _mini_umbrella(tmp_path)
    rs = ctp.check_kernel_meta_label_twins({"umbrella": u}, man)
    assert [r.status for r in rs] == ["PASS"], rs


@pytest.mark.parametrize("side", ["umbrella", "pinned"])
def test_metalabel_pin_fails_when_EITHER_side_moves(tmp_path, side):
    u, man = _mini_umbrella(tmp_path, pin_shift=side)
    rs = ctp.check_kernel_meta_label_twins({"umbrella": u}, man)
    assert rs[0].status == "FAIL"
    assert "re-pin" in rs[0].detail


def test_missing_umbrella_SKIPS_both_new_checks():
    a = ctp.check_kernel_shelf_twins({"umbrella": None})
    b = ctp.check_kernel_meta_label_twins({"umbrella": None}, {})
    assert a[0].status == "SKIP" and b[0].status == "SKIP"


def test_an_empty_pin_section_is_a_FAIL_not_a_silent_pass(tmp_path):
    u, _ = _mini_umbrella(tmp_path)
    rs = ctp.check_kernel_meta_label_twins({"umbrella": u}, {})
    assert rs[0].status == "FAIL"
    assert "no kernel_meta_label_twins pins" in rs[0].detail
