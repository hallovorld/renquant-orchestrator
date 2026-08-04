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


def test_the_traveling_keys_are_now_DECLARED_and_read():
    """The deliberate revisit the previous pin demanded: common#42 (merged
    2026-08-04, 20d4570a) typed metadata + smalln_ledger into LiveRunBundle,
    so the audit's finding set is EMPTY and stays pinned that way — a future
    producer key that the schema drops again flips this red, which is the
    tool's standing job. extra="ignore" itself is unchanged (still True):
    the defense is per-key declaration, not a config flip."""
    rep = A.audit()
    assert rep["schema_drops_unknown_keys"] is True
    assert rep["unread_keys_across_producers"] == [], rep


def test_main_EXITS_ZERO_with_no_unread_keys(capsys):
    """The exit code is what a scheduled job reads, so it is driven directly."""
    assert A.main([]) == 0
    out = capsys.readouterr().out
    assert "unread_keys=0" in out


def test_the_report_states_that_unread_is_NOT_lost(capsys):
    """The narrowing is load-bearing: these keys do reach disk. An audit that let a
    reader infer data loss would be over-claiming, which is the failure this programme
    keeps correcting."""
    A.main([])
    assert "Unread does not mean lost" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# ROUND 2 — codex on #690: a key census proves only that a function contains
# those assignments. It must also prove the validated boundary still exists.
# ---------------------------------------------------------------------------

def _mk(tmp_path, monkeypatch, body: str, name="p.py", func="build"):
    """Point the audit at a synthetic producer, through its real PRODUCERS table."""
    (tmp_path / name).write_text(body, encoding="utf-8")
    monkeypatch.setattr(A, "REPO", tmp_path)
    monkeypatch.setattr(A, "PRODUCERS", ((name, func),))


BUILDS_AND_VALIDATES = '''
def build(ctx):
    bundle = {"schema_version": 1, "source": "x", "decision_trace": (),
              "order_intents": (), "state_mutations": ()}
    validate_live_run_bundle(bundle)
    return bundle
'''

BUILDS_BUT_DOES_NOT_VALIDATE = '''
def build(ctx):
    bundle = {"schema_version": 1, "source": "x", "decision_trace": (),
              "order_intents": (), "state_mutations": ()}
    return bundle
'''

VALIDATES_SOMETHING_ELSE = '''
def build(ctx):
    bundle = {"schema_version": 1, "source": "x", "decision_trace": (),
              "order_intents": (), "state_mutations": ()}
    validate_live_run_bundle(ctx.other_bundle)
    return bundle
'''


def test_NEGATIVE_FIXTURE_the_builder_remains_but_validation_is_REMOVED(
        tmp_path, monkeypatch, capsys):
    """The case codex named. Before this round the audit reported this producer as a
    clean 'validated producer path' with a confident key census."""
    _mk(tmp_path, monkeypatch, BUILDS_BUT_DOES_NOT_VALIDATE)
    rep = A.audit()
    assert rep["producers_not_validating_their_bundle"] == ["p.py"], rep
    assert A.main([]) == 1
    out = capsys.readouterr().out
    assert "NOT VALIDATED" in out and "never called" in out


def test_validating_a_DIFFERENT_object_is_not_validating_the_bundle(
        tmp_path, monkeypatch, capsys):
    """Presence of the call is not enough — this is the bypass a name-only check misses."""
    _mk(tmp_path, monkeypatch, VALIDATES_SOMETHING_ELSE)
    rep = A.audit()
    assert rep["producers_not_validating_their_bundle"] == ["p.py"]
    A.main([])
    assert "not on a dict built in this function" in capsys.readouterr().out


def test_ANTI_VACUITY_a_producer_that_DOES_validate_its_bundle_passes(
        tmp_path, monkeypatch):
    """Without this the new check could reject everything and prove nothing."""
    _mk(tmp_path, monkeypatch, BUILDS_AND_VALIDATES)
    rep = A.audit()
    assert rep["producers_not_validating_their_bundle"] == []
    assert rep["producers"][0]["validates_its_bundle"] is True
    assert A.main([]) == 0


def test_a_MODULE_QUALIFIED_call_still_counts(tmp_path, monkeypatch):
    """`schemas.validate_live_run_bundle(bundle)` is the same call; rejecting it would
    be a false positive on a legitimate import style."""
    _mk(tmp_path, monkeypatch, BUILDS_AND_VALIDATES.replace(
        "validate_live_run_bundle(bundle)", "schemas.validate_live_run_bundle(bundle)"))
    assert A.audit()["producers_not_validating_their_bundle"] == []


def test_BOTH_REAL_producers_still_validate_their_own_bundle():
    """The live measurement. If a refactor ever removes the call this fails here, which
    is the whole point of adding the check."""
    rep = A.audit()
    assert rep["producers_not_validating_their_bundle"] == [], rep
    assert all(r["validates_its_bundle"] for r in rep["producers"]), rep
