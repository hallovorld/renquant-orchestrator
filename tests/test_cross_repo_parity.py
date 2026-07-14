"""G3 Phase A: cross-repo parity tripwires.

These tests verify that duplicated constants and contracts across sibling repos
remain in sync.  They import directly from sibling repo source trees via
sys.path and are intentionally fragile: a failure means the duplication has
drifted and the single-source consolidation (Phase B) should be prioritised.

Registry items: A2 (duplicated constants), A3 (calendar inventory).
"""
from __future__ import annotations

import importlib
import inspect
import sys
from pathlib import Path
from types import ModuleType

import pytest

GITHUB_ROOT = Path(__file__).resolve().parents[2]
_SIBLING_SRC_DIRS = [
    GITHUB_ROOT / "renquant-pipeline" / "src",
    GITHUB_ROOT / "renquant-execution" / "src",
    GITHUB_ROOT / "renquant-common" / "src",
]

_original_path: list[str] = []


def _ensure_siblings_importable() -> None:
    global _original_path  # noqa: PLW0603
    _original_path = list(sys.path)
    for d in _SIBLING_SRC_DIRS:
        s = str(d)
        if d.is_dir() and s not in sys.path:
            sys.path.insert(0, s)


def _import_or_skip(module_path: str) -> ModuleType:
    _ensure_siblings_importable()
    try:
        return importlib.import_module(module_path)
    except (ImportError, ModuleNotFoundError) as exc:
        pytest.skip(f"sibling module {module_path} not importable: {exc}")
        raise  # unreachable but makes mypy happy


# ---------------------------------------------------------------------------
# A2: duplicated constants parity
# ---------------------------------------------------------------------------


class TestMinFractionalNotionalParity:
    """MIN_FRACTIONAL_NOTIONAL_USD must be identical in pipeline and execution."""

    def test_value_equal(self) -> None:
        pipeline_sizing = _import_or_skip("renquant_pipeline.kernel.sizing")
        execution_broker = _import_or_skip("renquant_execution.broker")

        p_val = pipeline_sizing.MIN_FRACTIONAL_NOTIONAL_USD
        e_val = execution_broker.MIN_FRACTIONAL_NOTIONAL_USD

        assert p_val == e_val, (
            f"MIN_FRACTIONAL_NOTIONAL_USD drifted: pipeline={p_val}, execution={e_val}"
        )

    def test_type_is_numeric(self) -> None:
        pipeline_sizing = _import_or_skip("renquant_pipeline.kernel.sizing")
        execution_broker = _import_or_skip("renquant_execution.broker")

        assert isinstance(pipeline_sizing.MIN_FRACTIONAL_NOTIONAL_USD, (int, float))
        assert isinstance(execution_broker.MIN_FRACTIONAL_NOTIONAL_USD, (int, float))


class TestComputeParentIntentIdParity:
    """compute_parent_intent_id must produce identical output in both repos."""

    GOLDEN_VECTORS = [
        dict(
            account="DU12345",
            symbol="AAPL",
            trading_day="2026-01-15",
            side="buy",
            signal_version="v1",
        ),
        dict(
            account="DU12345",
            symbol="MSFT",
            trading_day="2026-03-01",
            side="sell",
            signal_version="v2",
        ),
        dict(
            account="LIVE99",
            symbol="NVDA",
            trading_day="2026-07-01",
            side="buy",
            signal_version="v3.1",
        ),
    ]

    def test_signatures_match(self) -> None:
        p_mod = _import_or_skip("renquant_pipeline.intraday_decisioning")
        e_mod = _import_or_skip("renquant_execution.order_state_machine")

        p_sig = inspect.signature(p_mod.compute_parent_intent_id)
        e_sig = inspect.signature(e_mod.compute_parent_intent_id)

        assert list(p_sig.parameters.keys()) == list(e_sig.parameters.keys()), (
            f"parameter names differ: pipeline={list(p_sig.parameters)} "
            f"vs execution={list(e_sig.parameters)}"
        )

    def test_golden_vectors_match(self) -> None:
        p_mod = _import_or_skip("renquant_pipeline.intraday_decisioning")
        e_mod = _import_or_skip("renquant_execution.order_state_machine")

        for kw in self.GOLDEN_VECTORS:
            p_val = p_mod.compute_parent_intent_id(**kw)
            e_val = e_mod.compute_parent_intent_id(**kw)
            assert p_val == e_val, (
                f"compute_parent_intent_id({kw}) drifted: "
                f"pipeline={p_val}, execution={e_val}"
            )


# ---------------------------------------------------------------------------
# A3: calendar implementation inventory
# ---------------------------------------------------------------------------


class TestCalendarImplementationInventory:
    """Pipeline should use renquant_common.market_calendar, not raw
    pandas_market_calendars.  This test counts non-canonical callsites."""

    PIPELINE_KERNEL_DIR = GITHUB_ROOT / "renquant-pipeline" / "src" / "renquant_pipeline" / "kernel"
    CANONICAL_IMPORT = "renquant_common.market_calendar"

    def _count_raw_mcal_imports(self) -> list[tuple[str, int]]:
        """Find files that import pandas_market_calendars directly."""
        if not self.PIPELINE_KERNEL_DIR.is_dir():
            pytest.skip("pipeline kernel dir not found")

        hits: list[tuple[str, int]] = []
        for py in sorted(self.PIPELINE_KERNEL_DIR.rglob("*.py")):
            for lineno, line in enumerate(py.read_text().splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if "pandas_market_calendars" in stripped and "import" in stripped:
                    rel = py.relative_to(self.PIPELINE_KERNEL_DIR)
                    hits.append((str(rel), lineno))
        return hits

    def test_inventory_reported(self) -> None:
        """Document the current count of raw mcal imports.

        This test PASSES even if the count is nonzero — it documents drift,
        not blocks on it (Phase A tripwire contract).  When Phase B lands
        calendar consolidation, tighten this to assert count == 0.
        """
        hits = self._count_raw_mcal_imports()

        # Record the inventory in the test output for visibility.
        if hits:
            msg_lines = [
                f"Found {len(hits)} raw pandas_market_calendars import(s) "
                f"in pipeline kernel (should use {self.CANONICAL_IMPORT}):",
            ]
            for path, lineno in hits:
                msg_lines.append(f"  {path}:{lineno}")
            import warnings

            warnings.warn("\n".join(msg_lines), stacklevel=1)

        assert isinstance(hits, list)

    def test_non_canonical_count_upper_bound(self) -> None:
        """Catch NEW non-canonical imports (current baseline)."""
        hits = self._count_raw_mcal_imports()
        baseline = 7
        assert len(hits) <= baseline, (
            f"Non-canonical calendar imports grew from {baseline} to {len(hits)}. "
            f"New imports must use {self.CANONICAL_IMPORT}."
        )
