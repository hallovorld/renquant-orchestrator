"""The sizing tracer must trace the call site, not just the definition.

A tracer that silently traces nothing is the same failure as a guard that
silently passes — and it is easy to commit here, because `task_selection`
binds `compute_position_size` by name at import time.
"""
from __future__ import annotations

import io
from pathlib import Path
import sys

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "ops" / "renquant104"))
import trace_sizing_preflight as T  # noqa: E402

pytest.importorskip("renquant_pipeline.kernel.sizing")


@pytest.fixture
def restore():
    import renquant_pipeline.kernel.sizing as SZ
    original = SZ.compute_position_size
    yield SZ
    SZ.compute_position_size = original


def test_the_call_site_resolves_through_the_PATCHED_module(restore):
    """`SizeAndEmitTask` imports the symbol INSIDE `run()`, so the name is
    resolved from the defining module per call and patching it is enough.

    I first assumed the opposite — that the caller bound it at import time —
    and patched a module attribute that does not exist. This test is the check
    that would have caught a tracer which traces nothing."""
    import renquant_pipeline.kernel.pipeline.task_selection as TS

    assert not hasattr(TS, "compute_position_size"), (
        "task_selection now binds the symbol at module scope — the tracer must "
        "patch it there too, or it will silently trace nothing")
    SZ = restore
    T.install_trace(out=io.StringIO())
    from renquant_pipeline.kernel.sizing import compute_position_size as fresh
    assert fresh is SZ.compute_position_size, (
        "a fresh import must see the traced function")


def test_the_trace_records_the_arguments_and_the_RESULT(restore):
    SZ = restore
    buf = io.StringIO()
    T.install_trace(out=buf)
    out = SZ.compute_position_size(10565.46, 9162.85, 0.02322928, 0.0, 306.5236,
                                   fractional=False, min_notional=0.0)
    line = [l for l in buf.getvalue().splitlines() if "pv=" in l][0]
    assert "max_pct=0.02322928" in line
    assert "price=306.52" in line
    assert f"-> {out}" in line


def test_the_traced_function_returns_the_ORIGINAL_result(restore):
    """An observer that changes the observation is not an observer."""
    SZ = restore
    before = SZ.compute_position_size(10565.46, 9162.85, 0.02322928, 0.0,
                                      306.5236, fractional=False, min_notional=0.0)
    T.install_trace(out=io.StringIO())
    after = SZ.compute_position_size(10565.46, 9162.85, 0.02322928, 0.0,
                                     306.5236, fractional=False, min_notional=0.0)
    assert before == after


def test_it_ANNOUNCES_installation_so_an_empty_trace_is_readable(restore):
    """An empty trace must be distinguishable from a tracer that never loaded."""
    buf = io.StringIO()
    T.install_trace(out=buf)
    assert "installed" in buf.getvalue()
