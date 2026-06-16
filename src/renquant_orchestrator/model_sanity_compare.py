"""Compare model sanity-placebo diagnostics across retrains.

``analyze_manifest_sanity_placebo.py`` emits one JSON per model; collecting them
into a promotion-evidence table is how the B1 / B2 / B3 / xstock / A1 retrain
comparison gets read. This makes that reproducible and evidence-grade: point it
at the JSONs, get the table (and the verdict on which retrain is closest to
passing the gate).

Verdict heuristic mirrors the gate: a model is closer to promotable when its
60-day aligned real IC is higher AND its 60-day placebo IC is smaller in
magnitude relative to it (the gate fails when |placebo| > 0.5*|aligned_real|).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, NamedTuple


class SanityRow(NamedTuple):
    name: str
    n_features: int | None
    real_ic: float | None
    aligned_real_60_ic: float | None
    placebo_60_ic: float | None
    promotion_evidence: bool

    @property
    def placebo_ratio(self) -> float | None:
        """|placebo_60| / |aligned_real_60| — the gate fails this above ~2.0
        (gate threshold is |placebo| > 0.5*|aligned_real|)."""
        a = self.aligned_real_60_ic
        p = self.placebo_60_ic
        if a is None or p is None or a == 0:
            return None
        return abs(p) / abs(a)


def _real_ic(d: dict) -> float | None:
    ri = d.get("real_ic")
    if isinstance(ri, dict):
        return ri.get("mean_ic")
    return ri


def load_sanity(path: str | Path, *, name: str | None = None) -> SanityRow:
    """Parse one analyze_manifest_sanity_placebo JSON into a row."""
    path = Path(path)
    d = json.loads(path.read_text())
    interp = d.get("interpretation", {}) or {}
    if name is None:
        # sanity_placebo_B2/hf_..._model.json -> "B2"
        parent = path.parent.name
        name = parent.replace("sanity_placebo_", "") if parent else path.stem
    return SanityRow(
        name=name,
        n_features=d.get("feature_count"),
        real_ic=_real_ic(d),
        aligned_real_60_ic=interp.get("aligned_real_60_ic"),
        placebo_60_ic=interp.get("placebo_60_ic"),
        promotion_evidence=bool(interp.get("promotion_evidence")),
    )


def compare(paths: Iterable[str | Path],
            names: Iterable[str] | None = None) -> list[SanityRow]:
    paths = list(paths)
    name_list = list(names) if names is not None else [None] * len(paths)
    return [load_sanity(p, name=n) for p, n in zip(paths, name_list)]


def best_candidate(rows: list[SanityRow]) -> SanityRow | None:
    """The retrain closest to passing: prefer promotion_evidence, then the
    smallest placebo ratio, then the highest aligned real IC."""
    if not rows:
        return None

    def key(r: SanityRow):
        ratio = r.placebo_ratio
        return (
            r.promotion_evidence,
            -(ratio if ratio is not None else float("inf")),
            r.aligned_real_60_ic if r.aligned_real_60_ic is not None else float("-inf"),
        )

    return max(rows, key=key)


def _fmt(x: float | None, nd: int = 4) -> str:
    return f"{x:+.{nd}f}" if isinstance(x, (int, float)) else "—"


def render_markdown(rows: list[SanityRow]) -> str:
    lines = [
        "| model | n_feat | real IC | aligned 60d | placebo 60d | |plc|/|aln| | pass |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        ratio = r.placebo_ratio
        lines.append(
            f"| {r.name} | {r.n_features if r.n_features is not None else '—'} "
            f"| {_fmt(r.real_ic)} | {_fmt(r.aligned_real_60_ic)} "
            f"| {_fmt(r.placebo_60_ic)} "
            f"| {f'{ratio:.2f}' if ratio is not None else '—'} "
            f"| {'YES' if r.promotion_evidence else 'no'} |"
        )
    best = best_candidate(rows)
    if best is not None:
        lines.append("")
        lines.append(f"**closest to passing:** {best.name} "
                     f"(aligned {_fmt(best.aligned_real_60_ic)}, "
                     f"placebo ratio "
                     f"{f'{best.placebo_ratio:.2f}' if best.placebo_ratio is not None else '—'})")
    return "\n".join(lines)
