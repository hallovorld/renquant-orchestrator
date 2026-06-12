#!/usr/bin/env python3
"""DRPH core (#108 S1-PR3) — ReplayCase format, canonicalizer, fingerprint, diff.

The behavior-identity substrate: content-addressed frozen inputs, canonical
decision JSON (sorted keys, fixed float precision), byte-diff verdicts.
Self-test builds a synthetic case, mutates one decision input, and proves
the diff localizes it.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

PRECISION = 8


def _canon(obj):
    if isinstance(obj, float):
        return round(obj, PRECISION)
    if isinstance(obj, dict):
        return {k: _canon(obj[k]) for k in sorted(obj)}
    if isinstance(obj, (list, tuple)):
        return [_canon(x) for x in obj]
    return obj


def canonical_json(decisions: dict) -> str:
    return json.dumps(_canon(decisions), sort_keys=True, separators=(",", ":"))


def sha(payload: bytes | str) -> str:
    b = payload.encode() if isinstance(payload, str) else payload
    return hashlib.sha256(b).hexdigest()[:16]


def run_fingerprint(*, config_sha, panel_sha, state_sha, artifact_shas: dict,
                    pin_digest, env_sha) -> dict:
    return {"config_sha": config_sha, "panel_sha": panel_sha,
            "state_sha": state_sha, "artifact_shas": dict(sorted(artifact_shas.items())),
            "pin_digest": pin_digest, "env_sha": env_sha}


class ReplayCase:
    """Content-addressed frozen case on disk."""

    def __init__(self, root: Path):
        self.root = Path(root)

    def write(self, *, inputs: dict, expected_decisions: dict) -> str:
        (self.root / "inputs").mkdir(parents=True, exist_ok=True)
        (self.root / "expected").mkdir(parents=True, exist_ok=True)
        manifest = {}
        for name, payload in inputs.items():
            blob = canonical_json(payload) if isinstance(payload, dict) else str(payload)
            f = self.root / "inputs" / f"{name}.json"
            f.write_text(blob)
            manifest[name] = sha(blob)
        (self.root / "expected" / "decisions.json").write_text(canonical_json(expected_decisions))
        manifest["expected"] = sha(canonical_json(expected_decisions))
        (self.root / "case_manifest.json").write_text(canonical_json(manifest))
        return sha(canonical_json(manifest))

    def verify(self, actual_decisions: dict) -> tuple[bool, list[str]]:
        exp = (self.root / "expected" / "decisions.json").read_text()
        act = canonical_json(actual_decisions)
        if exp == act:
            return True, []
        e, a = json.loads(exp), json.loads(act)
        diffs = []

        def walk(p, x, y):
            if isinstance(x, dict) and isinstance(y, dict):
                for k in sorted(set(x) | set(y)):
                    walk(f"{p}.{k}", x.get(k), y.get(k))
            elif x != y:
                diffs.append(f"{p}: expected={x!r} actual={y!r}")
        walk("$", e, a)
        return False, diffs[:20]


if __name__ == "__main__":
    import tempfile
    root = Path(tempfile.mkdtemp()) / "case_2026-06-11_false_bear"
    decisions = {
        "run_fingerprint": run_fingerprint(config_sha="c1", panel_sha="p1",
                                           state_sha="s1", artifact_shas={"primary": "a1"},
                                           pin_digest="d1", env_sha="e1"),
        "regime": {"label": "CHOPPY", "hard_bear": False, "vol_5d": 0.26123456789},
        "gates": [{"gate": "transition_window", "scope": "book",
                   "verdict": "block", "reason": "cooldown", "inputs": {"bars": 3}}],
        "orders": [],
    }
    case = ReplayCase(root)
    cid = case.write(inputs={"state": {"holdings": {"MU": 1}}, "config": {"x": 1}},
                     expected_decisions=decisions)
    ok, _ = case.verify(decisions)
    assert ok, "identity must verify"
    # float precision stability: 1e-12 wobble is identical post-canon
    wob = json.loads(canonical_json(decisions))
    wob["regime"]["vol_5d"] += 1e-12
    ok2, _ = case.verify(wob)
    assert ok2, "sub-precision wobble must not diff"
    # a real behavior change is localized
    bad = json.loads(canonical_json(decisions))
    bad["regime"]["hard_bear"] = True
    ok3, diffs = case.verify(bad)
    assert not ok3 and any("hard_bear" in d for d in diffs)
    print(f"case id={cid}; identity ✓  precision-stability ✓  diff-localization: {diffs[0]}")
