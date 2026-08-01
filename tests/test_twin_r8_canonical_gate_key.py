"""R8 tripwire — no reader may take the gate stamp from the LEGACY key alone.

The twin registry's R8 records that `wf_gate_metadata` exists in two places inside one
artifact: `metadata.wf_gate_metadata` (canonical) and a legacy top-level copy that is
present on only 14 of 29 prod panels and DISAGREES with the canonical one on 2 of those.
Reading the legacy key alone produced three defects in one evening, two of them
published claims that had to be retracted.

This is the "executable pointer" the registry says would retire a row: an AST check that
every reader in this repo consults the canonical location.

WHY AST AND NOT GREP. A line-oriented regex cannot tell whether the receiver of
`.get("wf_gate_metadata")` is the whole payload or the `metadata` sub-dict. The first
pass of the sweep that found R8 flagged six production files and FIVE were false
positives for exactly that reason. The count came from grep; the finding came from
reading the code. So this walks the tree and looks at what the receiver actually is.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
KEY = "wf_gate_metadata"

# Files whose top-level read is INTENTIONAL because a canonical read precedes it in the
# same function (a documented fallback). Each entry is a promise that a human checked.
ALLOWED_FALLBACK = {
    "src/renquant_orchestrator/bundle_seal.py",
    "src/renquant_orchestrator/model_bundle.py",
    "src/renquant_orchestrator/model_freshness_enforcer.py",
    "scripts/check_model_bundle_consistency.py",
}


def _sources():
    for sub in ("src", "scripts", "ops"):
        for f in (REPO / sub).rglob("*.py"):
            if ".claude" in f.parts or "build" in f.parts:
                continue
            yield f


CANONICAL_RECEIVER_NAMES = ("metadata", "meta", "md")


def _receiver_is_canonical(recv: ast.AST) -> bool:
    """Does this receiver DERIVE from `metadata`?

    Decided over the receiver's whole subtree, not just its top node. The earlier
    version accepted a bare `ast.Name`, so the common defensive form
    `(meta or {}).get("wf_gate_metadata")` — receiver is a `BoolOp`, not a `Name` —
    was scored as a legacy-only read. That is a FALSE POSITIVE against a compliant
    reader, and the fix belongs here rather than in an allow-list: an allow-list entry
    would have silenced this check for that file permanently, including for a future
    edit that really did read the legacy key alone.
    """
    src = ast.dump(recv)
    if '"metadata"' in src or "'metadata'" in src:
        return True
    return any(isinstance(n, ast.Name) and n.id in CANONICAL_RECEIVER_NAMES
               for n in ast.walk(recv))


def _reads(tree: ast.AST) -> tuple[bool, bool]:
    """(reads canonical, reads top-level) — decided by the RECEIVER, not the line."""
    canonical = toplevel = False
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in ("get", "__getitem__")):
            continue
        args = node.args
        if not args or not (isinstance(args[0], ast.Constant) and args[0].value == KEY):
            continue
        if _receiver_is_canonical(node.func.value):
            canonical = True
        else:
            toplevel = True
    # subscript form: meta["wf_gate_metadata"]
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant) \
                and node.slice.value == KEY:
            if _receiver_is_canonical(node.value):
                canonical = True
            else:
                toplevel = True
    return canonical, toplevel


def test_no_reader_takes_the_gate_stamp_from_the_LEGACY_key_alone():
    offenders = []
    for f in _sources():
        try:
            text = f.read_text(encoding="utf-8")
        except OSError:  # pragma: no cover
            continue
        if KEY not in text:
            continue
        try:
            tree = ast.parse(text)
        except SyntaxError:  # pragma: no cover
            pytest.fail(f"{f} failed to parse — the scan is a lower bound, not a pass")
        canonical, toplevel = _reads(tree)
        rel = str(f.relative_to(REPO))
        if toplevel and not canonical and rel not in ALLOWED_FALLBACK:
            offenders.append(rel)
    assert offenders == [], (
        "these read the legacy top-level wf_gate_metadata without consulting "
        f"metadata.wf_gate_metadata first: {offenders}")


def test_the_allow_list_has_not_gone_stale():
    """Anti-vacuity: an allow-list entry that no longer reads the key at all is a
    silent widening of the exemption. Every entry must still be a real reader."""
    stale = [rel for rel in ALLOWED_FALLBACK
             if not (REPO / rel).exists() or KEY not in (REPO / rel).read_text(encoding="utf-8")]
    assert stale == [], f"allow-list entries that no longer read {KEY}: {stale}"


def test_the_registry_records_R8_and_R9():
    doc = (REPO / "doc/arch/twin-implementation-registry.md").read_text(encoding="utf-8")
    d = " ".join(doc.split())
    assert "## R8" in doc and "## R9" in doc
    assert "29 carry the canonical block; 14 also carry the legacy copy" in d
    assert "agree on 12 and DISAGREE on 2" in d
    assert "23 paths" in d and "3 distinct sha256" in d


def test_the_detector_accepts_the_DEFENSIVE_receiver_form():
    """`(meta or {}).get(KEY)` is a canonical read. Scoring it legacy-only was a false
    positive that would have been "fixed" by an allow-list entry, permanently silencing
    the check for that file."""
    tree = ast.parse('def f(payload):\n'
                     '    meta = payload.get("metadata")\n'
                     '    return (meta or {}).get("wf_gate_metadata")\n')
    canonical, toplevel = _reads(tree)
    assert canonical and not toplevel


def test_the_detector_STILL_catches_a_genuine_legacy_only_read():
    """Anti-vacuity: generalising the receiver must not make the check unfalsifiable."""
    tree = ast.parse('def f(payload):\n    return payload.get("wf_gate_metadata")\n')
    canonical, toplevel = _reads(tree)
    assert toplevel and not canonical
