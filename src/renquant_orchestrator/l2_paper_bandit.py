"""L2 online expert allocation — paper bandit (allocation machine, orch#918 §2).

Hedge / exponentiated-gradient weights over the expert PAPER books that the
shadow-lane infrastructure already marks daily. Shadow phase: this engine
publishes weights and logs; it allocates nothing and touches no live surface.

THE §2 CONTRACT (frozen in the merged design; the regret bound is conditional
on every item):
  1. bounded loss transform — the update consumes clip(r, −C, +C), C = 5%/day;
     a clip event is recorded on the row.
  2. feedback timing — weights are computed from day t's final paper marks and
     labelled effective from t+1; no same-day feedback.
  3. eligible-arm rule — an arm with no honest mark for a date gets NO update
     that date: its weight is carried, the exclusion is recorded on the row.
  4. costs — paper marks come from the lane books as marked; in any future
     live phase turnover costs must be charged inside the return BEFORE the
     transform. The shadow engine allocates paper capital only.
  5. the guarantee claimed is a REGRET bound on the transformed net series
     versus the best fixed arm in hindsight — never a profitability claim.

FROZEN PARAMETERS:
    η = 0.25          [DERIVED — Hedge rate √(8·lnN/T) at N=5 arms, T≈252]
    C = 0.05          per-day return clip
    W_CHAMPION = 0.5  the champion floor: containment, not the theorem

CHAMPION FLOOR SEMANTICS: after every multiplicative update and
renormalisation, if the champion's weight is below the floor it is raised to
exactly the floor and the others are scaled proportionally. The champion arm
is the LIVE book's own construction — "keep the panel" is a constraint in the
optimizer, per the design.

SELF-VERIFYING LOG: every run deterministically replays the FULL weight
history from the arm DBs, verifies every existing log row matches the replay
(divergence = REFUSED, exit 1 — a tampered or drifted log never gets appended
to), then appends rows for new dates only.
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
from pathlib import Path

from .runtime_paths import default_data_root

ETA = 0.25
CLIP = 0.05
W_CHAMPION_FLOOR = 0.5
CHAMPION = "champion_live_blend"

# Frozen arm registry: canonical arm id -> lane DB path relative to data root.
# The champion is the live book's own construction; the others are the shadow
# profile books the lane infrastructure already marks daily.
ARMS = {
    CHAMPION: "data/runs.alpaca.db",
    "profile_blend": "data/runs.alpaca_shadow_blend.db",
    "profile_blend_mom": "data/runs.alpaca_shadow_blend_mom.db",
    "profile_blend_rb_mom": "data/runs.alpaca_shadow_blend_rb_mom.db",
}

DEFAULT_LOG_SUBDIR = ("logs", "l2_paper_bandit")
SCHEMA = "l2_paper_bandit.v1"


def load_paper_marks(db_path: Path) -> dict[str, float]:
    """run_date -> end-of-day portfolio_value (the LAST snapshot of each date)."""
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT run_date, portfolio_value FROM live_state_snapshots "
            "WHERE portfolio_value IS NOT NULL ORDER BY run_date, created_at").fetchall()
    finally:
        con.close()
    marks: dict[str, float] = {}
    for d, pv in rows:  # later rows overwrite: last snapshot of the date wins
        if pv and pv > 0:
            marks[str(d)] = float(pv)
    return marks


def paper_returns(marks: dict[str, float]) -> dict[str, float]:
    """date -> daily paper return between consecutive MARKED dates."""
    out: dict[str, float] = {}
    dates = sorted(marks)
    for prev, curr in zip(dates, dates[1:]):
        out[curr] = marks[curr] / marks[prev] - 1.0
    return out


def apply_floor(weights: dict[str, float]) -> dict[str, float]:
    total = sum(weights.values())
    w = {k: v / total for k, v in weights.items()}
    short = W_CHAMPION_FLOOR - w[CHAMPION]
    if short <= 0:
        return w
    others = 1.0 - w[CHAMPION]
    if others <= 0:
        return {k: (1.0 if k == CHAMPION else 0.0) for k in w}
    scale = (1.0 - W_CHAMPION_FLOOR) / others
    out = {k: v * scale for k, v in w.items() if k != CHAMPION}
    out[CHAMPION] = W_CHAMPION_FLOOR
    return out


def hedge_step(weights: dict[str, float],
               returns: dict[str, float | None]) -> tuple[dict[str, float], dict]:
    """One Hedge update. ``returns[arm] is None`` = no honest mark (rule 3):
    weight carried, no update. Returns (new_weights, row_detail)."""
    detail: dict = {"clipped": [], "excluded": []}
    updated = {}
    for arm, w in weights.items():
        r = returns.get(arm)
        if r is None:
            detail["excluded"].append(arm)
            updated[arm] = w
            continue
        clipped = min(max(r, -CLIP), CLIP)
        if clipped != r:
            detail["clipped"].append(arm)
        updated[arm] = w * math.exp(ETA * clipped)
    new = apply_floor(updated)
    detail["returns"] = {a: (None if r is None else round(r, 6))
                         for a, r in returns.items()}
    return new, detail


def replay(arm_marks: dict[str, dict[str, float]]) -> list[dict]:
    """Deterministic full history: equal-start weights (floor applied), one
    Hedge step per date on which the CHAMPION has a return (the book's own
    calendar); other arms join on their marked dates per rule 3."""
    arm_rets = {a: paper_returns(m) for a, m in arm_marks.items()}
    calendar = sorted(arm_rets[CHAMPION])
    weights = apply_floor({a: 1.0 for a in ARMS})
    rows: list[dict] = []
    for d in calendar:
        rets = {a: arm_rets[a].get(d) for a in ARMS}
        weights, detail = hedge_step(weights, rets)
        rows.append({
            "schema": SCHEMA,
            "asof": d,
            "effective_from": "next_trading_day",   # rule 2, explicit
            "weights": {a: round(w, 6) for a, w in weights.items()},
            **detail,
            "params": {"eta": ETA, "clip": CLIP,
                       "w_champion_floor": W_CHAMPION_FLOOR},
        })
    return rows


def sync_log(log_dir: Path, rows: list[dict]) -> tuple[int, int]:
    """Verify every existing line matches the replay, then append new rows.
    Divergence raises — a drifted log is never appended to."""
    log_dir.mkdir(parents=True, exist_ok=True)
    out = log_dir / "l2_paper_bandit.jsonl"
    existing: list[dict] = []
    if out.exists():
        existing = [json.loads(x) for x in out.read_text(encoding="utf-8").splitlines() if x.strip()]
    for i, old in enumerate(existing):
        if i >= len(rows) or old != rows[i]:
            raise RuntimeError(
                f"log row {i} (asof {old.get('asof')}) does not match the "
                "deterministic replay — a drifted or tampered log is never "
                "appended to; investigate before touching the file")
    with out.open("a", encoding="utf-8") as f:
        for row in rows[len(existing):]:
            f.write(json.dumps(row, sort_keys=True) + "\n")
    return len(existing), len(rows) - len(existing)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-root", type=Path, default=None,
                    help="overrides default_data_root() resolution")
    ap.add_argument("--log-dir", type=Path, default=None)
    args = ap.parse_args(argv)
    data_root = args.data_root or default_data_root()
    log_dir = args.log_dir or data_root.joinpath(*DEFAULT_LOG_SUBDIR)
    try:
        arm_marks = {}
        for arm, rel in ARMS.items():
            db = data_root / rel
            if not db.exists():
                raise RuntimeError(f"arm {arm}: DB missing at {db}")
            arm_marks[arm] = load_paper_marks(db)
        if len(arm_marks[CHAMPION]) < 2:
            raise RuntimeError("champion book has fewer than 2 marks — no calendar")
        rows = replay(arm_marks)
        verified, appended = sync_log(log_dir, rows)
    except Exception as exc:  # noqa: BLE001 — fail-closed with the reason
        print(json.dumps({"status": "REFUSED", "why": str(exc)}, indent=2))
        return 1
    latest = rows[-1] if rows else {}
    print(json.dumps({"status": "SYNCED", "rows_verified": verified,
                      "rows_appended": appended,
                      "latest": latest}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
