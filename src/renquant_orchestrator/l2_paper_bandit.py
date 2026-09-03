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
    η = 0.21          [DERIVED — Hedge rate √(8·lnN/T) at N=4 arms, T≈252;
                       r1 visible correction: the first draft derived at N=5
                       while the registry holds 4 arms — corrected BEFORE any
                       consumer existed (no log rows deployed)]
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

ETA = 0.21
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


def apply_champion_floor(weights: dict[str, float]) -> dict[str, float]:
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
    new = apply_champion_floor(updated)
    detail["returns"] = {a: (None if r is None else round(r, 6))
                         for a, r in returns.items()}
    return new, detail


def replay(arm_marks: dict[str, dict[str, float]]) -> list[dict]:
    """Deterministic full history: equal-start weights (floor applied), one
    Hedge step per date on which the CHAMPION has a return (the book's own
    calendar); other arms join on their marked dates per rule 3."""
    arm_rets = {a: paper_returns(m) for a, m in arm_marks.items()}
    calendar = sorted(arm_rets[CHAMPION])
    weights = apply_champion_floor({a: 1.0 for a in ARMS})
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


MIXTURE_SCHEMA = "l2_moe_mixture.v1"
MIXTURE_LOG = "l2_moe_mixture.jsonl"


def mixture_view(arm_marks: dict[str, dict[str, float]], rows: list[dict]) -> list[dict]:
    """The MoE paper book, DERIVED from the replay: on each calendar date the
    weights EFFECTIVE that day (the previous row's weights — rule 2, no same-day
    feedback; the equal-start floor-applied weights on the first date) are
    applied to each arm's realized paper return — but ONLY across a calendar
    step the arm can price: the arm must be marked on this date AND the
    previous calendar date. An arm without an honest mark contributes 0 (its
    capital sits in cash), and when it re-marks after a gap its multi-day
    catch-up return is EXCLUDED (``gap_excluded``) — the mixture never held it
    over that interval, so no synthetic P&L is booked and the path does not
    depend on when the gap closes. Values compound from 1.0. The per-arm
    values (champion / best fixed arm in hindsight) compound under the SAME
    held-step rule, so ``mixture_minus_champion`` and the best-fixed-arm gap
    are regret under one set of admissible observations. Raw, every-mark book
    returns remain in the verified log's ``returns`` field for anyone who
    wants the non-comparable reference.

    The champion book's own value and every arm's value are carried alongside
    so the §2 claim — a REGRET bound versus the best fixed arm in hindsight,
    never a profitability claim — is readable from the file. This is the
    mixture-of-experts allocation running in shadow: nothing here allocates
    capital; it marks what the Hedge weights WOULD have earned on the books
    the lanes already keep.
    """
    arm_rets = {a: paper_returns(m) for a, m in arm_marks.items()}
    start = apply_champion_floor({a: 1.0 for a in ARMS})
    effective = {a: round(w, 6) for a, w in start.items()}
    values = {a: 1.0 for a in ARMS}
    mixture = 1.0
    out: list[dict] = []
    cal_all = sorted(arm_marks[CHAMPION])
    prev_by_date = {cal_all[i]: cal_all[i - 1] for i in range(1, len(cal_all))}
    for row in rows:
        d = row["asof"]
        prev_date = prev_by_date.get(d)    # the champion's mark this step starts from
        rets = {a: arm_rets[a].get(d) for a in ARMS}
        # VALUATION RULE (codex #1114 r1): paper_returns() books the whole
        # return between consecutive MARKS on the later mark date. The mixture
        # holds an arm only across a single calendar step it can price — the
        # arm must be marked on BOTH this date and the previous calendar date.
        # Otherwise the arm's capital sits in cash for the gap (contributes 0)
        # and RE-ENTERS at the new mark: the multi-day catch-up return is never
        # applied to a weight that was not held over that interval, so no
        # synthetic P&L and no dependence on when the gap happens to close.
        held = {a: (r is not None and prev_date is not None and prev_date in arm_marks[a])
                for a, r in rets.items()}
        gap_excluded = sorted(a for a, r in rets.items() if r is not None and not held[a])
        mix_r = sum(effective[a] * rets[a] for a in ARMS if held[a])
        mixture *= 1.0 + mix_r
        # The comparators live under the SAME valuation rule (codex #1114 r2):
        # a fixed-arm book also compounds only across priced steps, so
        # "mixture minus best fixed arm" is regret under one set of admissible
        # observations, never the mixture against a book that saw returns the
        # mixture was defined unable to hold.
        for a in ARMS:
            if held[a]:
                values[a] *= 1.0 + rets[a]
        best_arm = max(values, key=values.get)
        out.append({
            "schema": MIXTURE_SCHEMA,
            "asof": d,
            "weights_effective": dict(effective),
            "arm_returns": {a: (None if r is None else round(r, 6)) for a, r in rets.items()},
            "held": sorted(a for a in ARMS if held[a]),
            "gap_excluded": gap_excluded,
            "mixture_return": round(mix_r, 6),
            "mixture_value": round(mixture, 6),
            "arm_values_held": {a: round(v, 6) for a, v in values.items()},
            "champion_value": round(values[CHAMPION], 6),
            "best_fixed_arm": best_arm,
            "best_fixed_arm_value": round(values[best_arm], 6),
            "mixture_minus_champion": round(mixture - values[CHAMPION], 6),
        })
        effective = dict(row["weights"])   # becomes effective from the next date
    return out


def write_mixture(log_dir: Path, mrows: list[dict]) -> Path:
    """The mixture file is a DERIVED view: rewritten in full on every run from
    the same deterministic replay (no append/verify — the verified object is
    l2_paper_bandit.jsonl; this file is a function of it and the arm DBs)."""
    log_dir.mkdir(parents=True, exist_ok=True)
    out = log_dir / MIXTURE_LOG
    tmp = out.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for row in mrows:
            f.write(json.dumps(row, sort_keys=True) + "\n")
    tmp.replace(out)
    return out


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
        mrows = mixture_view(arm_marks, rows)
        write_mixture(log_dir, mrows)
    except Exception as exc:  # noqa: BLE001 — fail-closed with the reason
        print(json.dumps({"status": "REFUSED", "why": str(exc)}, indent=2))
        return 1
    latest = rows[-1] if rows else {}
    mix_latest = mrows[-1] if mrows else {}
    print(json.dumps({"status": "SYNCED", "rows_verified": verified,
                      "rows_appended": appended,
                      "latest": latest,
                      "mixture_latest": {k: mix_latest.get(k) for k in (
                          "asof", "mixture_value", "champion_value", "best_fixed_arm",
                          "best_fixed_arm_value", "mixture_minus_champion")}},
                     indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
