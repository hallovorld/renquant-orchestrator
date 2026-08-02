"""AC6 R4 step 1 — the daily run bundle vs the shared LiveRunBundle contract.

MEASURED 2026-07-31, before any of this landed:

  * `validate_live_run_bundle` had **zero production callers** in any repo. Every
    reference was a test. AC6 R4's plan described the contract as "already wired
    into the native/bridge live-bundle path"; it was not wired anywhere.
  * **0 of 7** real daily `run_bundle.json` files validated against it.
  * **7 of 7** validated once exactly one key -- `source` -- was added.

So wiring the validator as R4 proposed, without that key, would have fail-closed
every daily run. That is the regression these tests exist to prevent from
reappearing, in both directions: the key must stay, and the check must stay real.
"""

from __future__ import annotations

import copy
import inspect

import pytest

from renquant_orchestrator.daily import _record_bundle_contract

# The AC6 R4 binding switch (common#40) may be absent from an installed
# renquant-common that predates it — the sibling-checkout state orch#747 item 6
# exists to fix. The binding tests skip LOUDLY on that skew instead of measuring
# this machine's disk; CI checks out renquant-common main and runs them.
try:
    from renquant_common import validate_live_run_bundle as _vlrb

    _HAS_BINDING = (
        "require_gate_provenance" in inspect.signature(_vlrb).parameters
    )
except ImportError:  # pragma: no cover - contract absent entirely
    _HAS_BINDING = False

needs_binding = pytest.mark.skipif(
    not _HAS_BINDING,
    reason="installed renquant-common predates the require_gate_provenance "
    "switch (common#40) — sync the sibling checkout (orch#747 item 6)",
)


class _Ctx:
    def __init__(self):
        self.stage_trace = []


def _bundle():
    """The key set a real daily bundle carries, taken from a captured run.

    Deliberately NOT read from the live tree: that tree is a production surface,
    and a test reaching into it would both couple this suite to one operator's
    disk and re-measure a moving target.

    `wf_gate_provenance` is part of the real key set: `PersistDailyRunBundleTask`
    writes the tri-state block unconditionally, and the persist-time check now
    REQUIRES it (the AC6 R4 binding switch).
    """
    return {
        "schema_version": 1,
        "source": "daily_run_bundle",
        "run_id": "2026-07-31T00:00:00Z",
        "run_type": "daily_full",
        "dry_run": True,
        "decision_trace": [{"symbol": "AAPL", "decision": "hold"}],
        "order_intents": [],
        "submitted_orders": [{"symbol": "AAPL", "qty": 1}],
        "execution_audit": [{"stage": "submit", "ok": True}],
        "stage_trace": [],
        "wf_gate_provenance": {"status": "no_artifact_manifest"},
    }


@needs_binding
def test_a_real_shaped_daily_bundle_MEETS_the_contract():
    ctx = _Ctx()
    b = _bundle()
    _record_bundle_contract(b, ctx)
    assert b["contract_validation"]["ok"] is True, b["contract_validation"]
    assert ctx.stage_trace[-1]["stage"] == "validate_daily_run_bundle"


@needs_binding
def test_without_source_it_FAILS_which_is_why_the_key_was_added():
    """Anti-vacuity. If this ever passes, the check has stopped checking."""
    ctx = _Ctx()
    b = _bundle()
    del b["source"]
    _record_bundle_contract(b, ctx)
    assert b["contract_validation"]["ok"] is False
    assert "source" in b["contract_validation"]["error"]


def test_the_daily_task_actually_emits_source():
    """The fix is in the emitted dict, not only in this test's fixture."""
    import inspect

    from renquant_orchestrator import daily

    src = inspect.getsource(daily.PersistDailyRunBundleTask)
    assert '"source": "daily_run_bundle"' in src


@needs_binding
def test_a_contract_failure_RECORDS_and_does_not_raise():
    """The bundle is the receipt of a run that already happened. Aborting on a
    malformed receipt would turn a documentation defect into a no-trade day."""
    ctx = _Ctx()
    b = {"schema_version": 99}          # violates the contract several ways
    _record_bundle_contract(b, ctx)     # must not raise
    assert b["contract_validation"]["ok"] is False
    assert ctx.stage_trace[-1]["ok"] is False


def test_contract_UNAVAILABLE_is_not_contract_MET():
    """`ok` is tri-state on purpose: True / False / None. Collapsing an import
    failure into a pass is the fail-open default this repo keeps re-learning."""
    ctx = _Ctx()
    b = _bundle()
    import builtins

    real = builtins.__import__

    def boom(name, *a, **k):
        if name == "renquant_common":
            raise ImportError("simulated")
        return real(name, *a, **k)

    builtins.__import__ = boom
    try:
        _record_bundle_contract(b, ctx)
    finally:
        builtins.__import__ = real
    assert b["contract_validation"]["ok"] is None      # NOT True, NOT False
    assert "contract unavailable" in b["contract_validation"]["error"]


def test_the_verdict_reaches_both_surfaces():
    ctx = _Ctx()
    b = _bundle()
    _record_bundle_contract(b, ctx)
    assert b["contract_validation"]["ok"] is ctx.stage_trace[-1]["ok"]


def test_the_verdict_is_RECORDED_BEFORE_the_bundle_is_written():
    """codex #669: the verdict was recorded AFTER the final write, so
    run_bundle.json never carried `contract_validation` — including on failure.

    Asserted on ORDER in the emitted source, because that is what the defect was.
    An in-memory assertion would have passed throughout the bug: `ctx.run_bundle`
    was always correct and the FILE was the only thing wrong, so a test that never
    opens the artifact cannot see it.
    """
    import inspect

    from renquant_orchestrator import daily

    src = inspect.getsource(daily.PersistDailyRunBundleTask)
    record = src.index("_record_bundle_contract(bundle, ctx)")
    # the LAST write is the one that lands the final artifact
    final_write = src.rindex("_write_json(out, bundle)")
    assert record < final_write, (
        "_record_bundle_contract runs after the final _write_json — the verdict "
        "would exist only in memory and the artifact on disk would look like the "
        "contract had never been checked")


# ================ the verdict must reach DISK, not only memory ================
# codex review of #669: `_record_bundle_contract` ran AFTER the final
# `_write_json`, so the artifact on disk lacked `contract_validation` entirely --
# including on failure.
#
# MY FIRST VERSION OF THESE TESTS WAS VACUOUS. Its helper called
# `_record_bundle_contract` and then `_write_json` ITSELF, in the correct order,
# so it passed with the bug present -- an "integration" test that integrated
# nothing. Mutation-checking caught it: reverting the source order failed only the
# source-order assertion. These now DRIVE THE REAL TASK and read what it emitted.

def _drive_task(tmp_path, *, break_contract=False):
    """Run PersistDailyRunBundleTask for real and return the file it wrote."""
    import json
    import types

    from renquant_orchestrator.daily import PersistDailyRunBundleTask

    ns = types.SimpleNamespace
    ctx = ns(
        run_id="2026-07-31T00:00:00Z", run_type="daily_full", dry_run=True,
        strategy_manifest={}, strategy_config={}, data_manifest={},
        market_snapshot={}, account_snapshot={}, resolved_serving_bundle=None,
        g4_session_admission=None, backtest_context=None,
        output_dir=tmp_path, stage_trace=[], run_bundle=None,
        training_context=ns(artifact_manifest={"a": 1}),
        inference_context=ns(decision_trace=[{"symbol": "AAPL"}], order_intents=[]),
        execution_context=ns(submitted_orders=[{"symbol": "AAPL", "qty": 1}],
                             audit_rows=[{"stage": "submit", "ok": True}]),
    )
    if break_contract:
        # Remove the one key the contract needs, at the source: patch the task's
        # emitted literal rather than editing the file after the fact, so the
        # FAILURE path is what actually runs.
        import renquant_orchestrator.daily as daily

        real = daily._record_bundle_contract

        def strip_then_record(bundle, c):
            bundle.pop("source", None)
            return real(bundle, c)

        daily._record_bundle_contract = strip_then_record
        try:
            PersistDailyRunBundleTask().run(ctx)
        finally:
            daily._record_bundle_contract = real
    else:
        PersistDailyRunBundleTask().run(ctx)
    return json.loads((tmp_path / "run_bundle.json").read_text(encoding="utf-8"))


# =================== AC6 R4 binding switch (this PR's teeth) ===================


@needs_binding
def test_missing_gate_provenance_now_FAILS_the_binding():
    """The flip's anti-vacuity: before it, a bundle with no gate block validated
    clean; now its absence is a recorded contract failure naming the block."""
    ctx = _Ctx()
    b = _bundle()
    del b["wf_gate_provenance"]
    _record_bundle_contract(b, ctx)
    assert b["contract_validation"]["ok"] is False
    assert "wf_gate_provenance" in b["contract_validation"]["error"]


def test_the_daily_task_actually_emits_wf_gate_provenance():
    """The block is in the emitted dict, not only in this test's fixture —
    the same pattern that guards `source` above."""
    import inspect

    from renquant_orchestrator import daily

    src = inspect.getsource(daily.PersistDailyRunBundleTask)
    assert '"wf_gate_provenance": wf_gate_provenance(' in src


def test_contract_version_skew_is_TRI_STATED_not_a_violation():
    """A renquant-common predating the kwarg (common#40) must record ok=None —
    ok=False has to keep meaning "the bundle violates the contract"."""
    import renquant_common

    ctx = _Ctx()
    b = _bundle()
    real = renquant_common.validate_live_run_bundle

    def old_signature(bundle):  # no keyword — the pre-common#40 surface
        raise TypeError(
            "validate_live_run_bundle() got an unexpected keyword argument "
            "'require_gate_provenance'")

    renquant_common.validate_live_run_bundle = old_signature
    try:
        _record_bundle_contract(b, ctx)
    finally:
        renquant_common.validate_live_run_bundle = real
    assert b["contract_validation"]["ok"] is None
    assert "too old" in b["contract_validation"]["error"]


@needs_binding
def test_the_verdict_is_on_disk_for_a_PASSING_bundle(tmp_path):
    written = _drive_task(tmp_path)
    assert "contract_validation" in written, sorted(written)
    assert written["contract_validation"]["ok"] is True


@needs_binding
def test_the_verdict_is_on_disk_for_a_FAILING_bundle(tmp_path):
    """The case that matters: a failure that never reaches the artifact is worse
    than no check at all, because the file looks complete."""
    written = _drive_task(tmp_path, break_contract=True)
    assert "contract_validation" in written, sorted(written)
    assert written["contract_validation"]["ok"] is False
    assert "source" in written["contract_validation"]["error"]
