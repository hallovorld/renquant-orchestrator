#!/usr/bin/env python3
"""Resolve an artifact basename against a DECLARED ROOT, refusing ambiguity. (GOAL-3 C6)

Twin-registry **R9**: `panel-ltr.alpha158_fund.json` resolves to **23 paths** under
`backtesting/renquant_104/artifacts` with **3 distinct sha256** — 22 of them under
`diagnostics/` — and an `rglob` + `sorted(hits)[0]` silently measured a modal-sweep
diagnostic copy, shifting a published median with no error raised. Re-measured
2026-08-01: still **23 paths / 3 digests / 1 under `prod/`**.

The remediation was written once, inside `ops/regime_profile_census.py`, and was reachable
only by that tool. R9's whole subject is "which copy gets used", so a rule against it that
every new caller must re-type is the same hazard one level up — this file is that rule,
importable.

WHAT IT ENFORCES, AND WHY EACH PART.

  * **Declared root, non-recursive by default.** The hazard is not `rglob`; it is globbing
    from a root that CONTAINS the diagnostic tree. Checked 2026-08-01:
    `model_freshness_enforcer.default_search_dirs` rglobs `panel-ltr*.json` but from
    `staging/ prod/ sim/`, so **0 of its 62 hits** are diagnostics copies — it is not
    exposed, and saying `rglob is the bug` would have been wrong.
  * **More than one DISTINCT DIGEST is AMBIGUOUS, and ambiguity REFUSES.** Not "prefer
    prod", not "take the newest" — a caller that wanted a specific copy should have named
    a root that contains one. Choosing is what produced R9.
  * **Several paths at ONE digest is fine.** 21 identical copies are one artifact wearing
    21 names; refusing there would block a legitimate resolution.

Read-only. Opens files to digest them, writes nothing.
"""

from __future__ import annotations

import glob
import hashlib
import os

RESOLVED, NOT_FOUND, AMBIGUOUS = "resolved", "not_found", "ambiguous"


def resolve_artifact(basename: str, search_root: str, *, recursive: bool = False) -> dict:
    """One artifact basename under one declared root.

    Returns a dict with ``status`` in {resolved, not_found, ambiguous}. The caller is
    expected to branch on it; there is deliberately no "just give me a path" variant,
    because that is the signature that produced R9.
    """
    base = os.path.basename(basename)
    pattern = (os.path.join(search_root, "**", base) if recursive
               else os.path.join(search_root, base))
    hits = sorted(glob.glob(pattern, recursive=recursive))
    if not hits:
        return {"status": NOT_FOUND, "artifact": base, "search_root": search_root,
                "why": "no path under this declared root"}

    by_digest: dict[str, list[str]] = {}
    for h in hits:
        try:
            with open(h, "rb") as fh:
                d = hashlib.sha256(fh.read()).hexdigest()
        except OSError as exc:
            # Unreadable is not "a different digest" and not "absent" — folding it into
            # either would make an IO error look like a content fact.
            return {"status": AMBIGUOUS, "artifact": base, "search_root": search_root,
                    "why": f"unreadable candidate {h}: {type(exc).__name__}",
                    "n_paths": len(hits)}
        by_digest.setdefault(d, []).append(os.path.relpath(h, search_root))

    if len(by_digest) > 1:
        return {"status": AMBIGUOUS, "artifact": base, "search_root": search_root,
                "n_paths": len(hits), "n_digests": len(by_digest),
                "why": (f"AMBIGUOUS: {len(hits)} paths with {len(by_digest)} distinct "
                        f"digests under this root — refusing to choose"),
                "candidates": by_digest}

    digest, paths = next(iter(by_digest.items()))
    return {"status": RESOLVED, "artifact": base, "search_root": search_root,
            "path": hits[0], "sha256": digest,
            "n_paths": len(hits), "n_digests": 1,
            "duplicate_paths": paths[1:]}
