#!/usr/bin/env python3
"""ArtifactResolver prototype (#108 S1-PR5) — ONE resolution authority.

Kills incident #2 (#114 shadow dead a week: primary resolved strategy_dir-
first, shadow resolved repo-root-first). Proof obligations at bottom run
against the REAL production layout.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import NamedTuple


class ResolvedArtifact(NamedTuple):
    path: Path
    sha256: str
    source: str          # "strategy_dir" | "repo_root"
    ref: str


def resolve_artifact(ref: str, *, strategy_dir: Path, repo_root: Path) -> ResolvedArtifact:
    """strategy_dir-first, repo_root fallback, fail-closed. EVERY artifact
    load (primary/shadow/calibrator/gmm/gate) must call this and nothing else."""
    p = Path(ref)
    candidates = ([p] if p.is_absolute()
                  else [strategy_dir / p, repo_root / p])
    sources = (["absolute"] if p.is_absolute()
               else ["strategy_dir", "repo_root"])
    for cand, src in zip(candidates, sources):
        cand = cand.resolve()
        if cand.exists():
            digest = hashlib.sha256(cand.read_bytes()).hexdigest()[:16]
            return ResolvedArtifact(cand, digest, src, ref)
    raise FileNotFoundError(f"artifact unresolvable (fail-closed): {ref!r} "
                            f"tried {[str(c) for c in candidates]}")


if __name__ == "__main__":
    SD = Path("/Users/renhao/git/github/RenQuant/backtesting/renquant_104")
    RR = Path("/Users/renhao/git/github/RenQuant")
    # P1: the exact ref that was dead for a week (#114) now resolves
    shadow = resolve_artifact("artifacts/prod/panel-ltr.alpha158_fund.json",
                              strategy_dir=SD, repo_root=RR)
    print(f"P1 shadow ref resolves via {shadow.source}: sha={shadow.sha256}")
    # P2: the primary (repo-root relative ../../) resolves identically through the same code path
    primary = resolve_artifact(
        "../../artifacts/patchtst_shadow/pt07_strict_trainfit_embargo60_20260522/seed_44/hf_patchtst_all_seed44_model.pt",
        strategy_dir=SD, repo_root=RR)
    print(f"P2 primary resolves via {primary.source}: sha={primary.sha256}")
    # P3: fail-closed on garbage
    try:
        resolve_artifact("artifacts/nope.json", strategy_dir=SD, repo_root=RR)
        raise SystemExit("P3 FAILED: should have raised")
    except FileNotFoundError:
        print("P3 fail-closed OK")
    print("ALL PROOFS PASS — sha256 feeds the DRPH run fingerprint")
