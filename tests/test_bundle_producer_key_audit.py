"""The producer half of AC6 R4: which built keys does the shared schema never read?

The audit's own failure modes are the subject here. A key-coverage audit is trivially
green if it finds no producers, cannot parse one, or silently skips keys it cannot
interpret — so each of those is a test.
"""

from __future__ import annotations

import ast
import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
MOD = ROOT / "ops" / "bundle_producer_key_audit.py"


def _load():
    spec = importlib.util.spec_from_file_location("bpka", MOD)
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


A = _load()


def _fn(src: str, name: str = "f"):
    return next(n for n in ast.walk(ast.parse(src))
                if isinstance(n, ast.FunctionDef) and n.name == name)


# --- the key reader --------------------------------------------------------

def test_it_reads_DICT_LITERAL_keys():
    keys, unknowable = A._assigned_keys(_fn('def f():\n    return {"a": 1, "b": 2}\n'))
    assert keys == {"a", "b"} and unknowable == []


def test_it_reads_SUBSCRIPT_assignment_keys():
    """The shape a regex over the dict literal misses — and it is not hypothetical:
    `metadata` is assigned this way on BOTH real producers, so a literal-only reader
    reports one unread key where there are two."""
    keys, _ = A._assigned_keys(
        _fn('def f():\n    b = {"a": 1}\n    b["metadata"] = 2\n    return b\n'))
    assert keys == {"a", "metadata"}


def test_a_COMPUTED_key_is_recorded_as_UNKNOWABLE_not_dropped():
    """Silently ignoring what it cannot parse is how this audit would report clean for
    the wrong reason."""
    keys, unknowable = A._assigned_keys(
        _fn('def f(k):\n    b = {"a": 1}\n    b[k] = 2\n    return b\n'))
    assert keys == {"a"}
    assert unknowable and "computed subscript" in unknowable[0]


def test_dict_UNPACKING_is_recorded_as_unknowable():
    _, unknowable = A._assigned_keys(_fn('def f(d):\n    return {"a": 1, **d}\n'))
    assert unknowable and "unpacking" in unknowable[0]


# --- the audit's own integrity --------------------------------------------

def test_a_MISSING_producer_is_a_FAILURE_not_a_shrinking_denominator():
    """Otherwise deleting a producer is the cheapest way to make this audit green."""
    r = A.audit_producer("src/renquant_orchestrator/does_not_exist.py", "build")
    assert r["readable"] is False and "vanished" in r["why"]


def test_a_RENAMED_target_function_is_a_FAILURE():
    r = A.audit_producer("src/renquant_orchestrator/native_live_bundle.py", "nope")
    assert r["readable"] is False and "moved" in r["why"]


def test_the_schema_field_set_is_READ_OFF_THE_MODEL_not_hardcoded():
    from renquant_common.contracts.schemas import LiveRunBundle
    assert A.schema_declared() == frozenset(LiveRunBundle.model_fields)


# --- the live measurement --------------------------------------------------

def test_BOTH_declared_producers_are_readable_today():
    rep = A.audit()
    assert rep["n_producers_read"] == rep["n_producers_declared"] == 2, rep
    assert all(not r["unknowable"] for r in rep["producers"]), rep


def test_the_live_finding_metadata_and_smalln_ledger_are_UNREAD():
    """Pins the measurement this tool was written to produce. If the schema later
    declares these, this test fails and the R4 decision gets revisited deliberately."""
    rep = A.audit()
    assert rep["schema_drops_unknown_keys"] is True
    assert rep["unread_keys_across_producers"] == ["metadata", "smalln_ledger"], rep


def test_main_EXITS_NONZERO_while_unread_keys_exist(capsys):
    """The exit code is what a scheduled job reads, so it is driven directly."""
    assert A.main([]) == 1
    assert "UNREAD KEYS" in capsys.readouterr().out


def test_the_report_states_that_unread_is_NOT_lost(capsys):
    """The narrowing is load-bearing: these keys do reach disk. An audit that let a
    reader infer data loss would be over-claiming, which is the failure this programme
    keeps correcting."""
    A.main([])
    assert "Unread does not mean lost" in capsys.readouterr().out
