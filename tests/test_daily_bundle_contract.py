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

import pytest

from renquant_orchestrator.daily import _record_bundle_contract


class _Ctx:
    def __init__(self):
        self.stage_trace = []


def _bundle():
    """The key set a real daily bundle carries, taken from a captured run.

    Deliberately NOT read from the live tree: that tree is a production surface,
    and a test reaching into it would both couple this suite to one operator's
    disk and re-measure a moving target.
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
    }


def test_a_real_shaped_daily_bundle_MEETS_the_contract():
    ctx = _Ctx()
    b = _bundle()
    _record_bundle_contract(b, ctx)
    assert b["contract_validation"]["ok"] is True, b["contract_validation"]
    assert ctx.stage_trace[-1]["stage"] == "validate_daily_run_bundle"


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
