"""Weekly live-performance monitor for renquant_104."""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import sys
import urllib.error
import urllib.request

from renquant_common import Job, Pipeline, Task

from .runtime_paths import default_github_root, default_repo_root


GITHUB = default_github_root()
DEFAULT_REPO_ROOT = default_repo_root()


@dataclass
class WeeklyApyContext:
    repo_root: Path
    audit_log: Path
    window_days: int = 30
    alert_threshold: float = 0.25
    drawdown_threshold: float = 0.20
    drawdown_days: int = 5
    topic: str = "renquant"
    quiet: bool = False
    rows: list[dict] = field(default_factory=list)
    apy: float | None = None
    n_rows: int = 0
    drawdown_streak: int = 0
    sharpe_21d: float | None = None
    sharpe_63d: float | None = None
    exit_code: int = 0
    alert_title: str | None = None
    alert_body: str | None = None
    summary: str = ""


def _parse_utc_datetime(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def read_recent_rows(path: Path, window_days: int, *, now: datetime | None = None) -> list[dict]:
    if not path.exists():
        return []
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    else:
        current = current.astimezone(timezone.utc)
    cutoff = current - timedelta(days=window_days + 1)
    out: list[dict] = []
    with path.open(encoding="utf-8") as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            try:
                row = json.loads(raw)
                row_dt = _parse_utc_datetime(row["date"])
            except (json.JSONDecodeError, KeyError, ValueError, TypeError):
                continue
            if row_dt >= cutoff:
                out.append(row)
    return out


def compute_rolling_apy(rows: list[dict]) -> tuple[float | None, int]:
    valid = [r for r in rows if r.get("equity") is not None]
    if len(valid) < 2:
        return None, len(valid)
    first = valid[0]
    last = valid[-1]
    try:
        first_eq = float(first["equity"])
        last_eq = float(last["equity"])
        first_date = _parse_utc_datetime(first["date"])
        last_date = _parse_utc_datetime(last["date"])
    except (ValueError, KeyError, TypeError):
        return None, len(valid)
    days = (last_date - first_date).days
    if days <= 0 or first_eq <= 0:
        return None, len(valid)
    return (last_eq / first_eq) ** (365.0 / days) - 1.0, len(valid)


def drawdown_streak(rows: list[dict], threshold: float) -> int:
    best = cur = 0
    for row in rows:
        dd = row.get("drawdown_pct")
        if dd is not None and float(dd) > threshold:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def latest_sharpe(db_path: Path) -> tuple[float | None, float | None] | None:
    if not db_path.exists():
        return None
    try:
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                """SELECT sharpe_21d, sharpe_63d
                     FROM portfolio_daily_metrics
                    WHERE run_type='live' AND strategy='renquant-104'
                    ORDER BY as_of_date DESC LIMIT 1"""
            ).fetchone()
    except sqlite3.Error:
        return None
    if row is None:
        return None
    return row


def post_ntfy(title: str, body: str, topic: str) -> None:
    url = f"https://ntfy.sh/{topic}"
    try:
        req = urllib.request.Request(
            url,
            data=body.encode("utf-8"),
            headers={"Title": title},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=5).read()
    except (urllib.error.URLError, OSError):
        pass


class LoadAuditRowsTask(Task):
    def run(self, ctx: WeeklyApyContext) -> bool | None:
        ctx.rows = read_recent_rows(ctx.audit_log, ctx.window_days)
        return True


class ComputeWeeklyHealthTask(Task):
    def run(self, ctx: WeeklyApyContext) -> bool | None:
        ctx.apy, ctx.n_rows = compute_rolling_apy(ctx.rows)
        ctx.drawdown_streak = drawdown_streak(ctx.rows, ctx.drawdown_threshold)
        sharpe = latest_sharpe(ctx.repo_root / "data" / "runs.db")
        if sharpe:
            ctx.sharpe_21d, ctx.sharpe_63d = sharpe

        parts = [f"{ctx.n_rows} rows"]
        if ctx.apy is not None:
            parts.append(f"APY={ctx.apy:+.1%}")
        if ctx.drawdown_streak:
            parts.append(f"dd_streak={ctx.drawdown_streak}d")
        if ctx.sharpe_21d is not None:
            parts.append(f"Sharpe21d={ctx.sharpe_21d:.2f}")
        if ctx.sharpe_63d is not None:
            parts.append(f"Sharpe63d={ctx.sharpe_63d:.2f}")
        ctx.summary = " / ".join(parts)
        return True


class DecideWeeklyAlertTask(Task):
    def run(self, ctx: WeeklyApyContext) -> bool | None:
        if not ctx.rows:
            ctx.summary = f"audit log {ctx.audit_log} is empty or missing; no action"
            return True
        if ctx.apy is not None and ctx.apy < ctx.alert_threshold:
            ctx.exit_code = 2
            ctx.alert_title = "RenQuant 104 WATCH"
            ctx.alert_body = (
                f"Live rolling {ctx.window_days}d APY {ctx.apy:+.1%} "
                f"< alert {ctx.alert_threshold:+.1%} ({ctx.summary})"
            )
        elif ctx.drawdown_streak >= ctx.drawdown_days:
            ctx.exit_code = 3
            ctx.alert_title = "RenQuant 104 WATCH"
            ctx.alert_body = (
                f"Live drawdown > {ctx.drawdown_threshold:.0%} for "
                f"{ctx.drawdown_streak} days; check HWM ({ctx.summary})"
            )
        return True


class EmitWeeklyAlertTask(Task):
    def run(self, ctx: WeeklyApyContext) -> bool | None:
        if ctx.alert_title and ctx.alert_body and not ctx.quiet:
            post_ntfy(ctx.alert_title, ctx.alert_body, ctx.topic)
        return True


class LoadAuditRowsJob(Job):
    @property
    def tasks(self) -> list[Task]:
        return [LoadAuditRowsTask()]


class ComputeWeeklyHealthJob(Job):
    @property
    def tasks(self) -> list[Task]:
        return [ComputeWeeklyHealthTask()]


class AlertDecisionJob(Job):
    @property
    def tasks(self) -> list[Task]:
        return [DecideWeeklyAlertTask(), EmitWeeklyAlertTask()]


def build_pipeline() -> Pipeline:
    return Pipeline([LoadAuditRowsJob(), ComputeWeeklyHealthJob(), AlertDecisionJob()], name="weekly-apy-monitor")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=DEFAULT_REPO_ROOT)
    parser.add_argument("--window-days", type=int, default=30)
    parser.add_argument("--alert-threshold", type=float, default=0.25)
    parser.add_argument("--drawdown-threshold", type=float, default=0.20)
    parser.add_argument("--drawdown-days", type=int, default=5)
    parser.add_argument("--audit-log", default=None)
    parser.add_argument("--topic", default="renquant")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = args.repo_root.expanduser().resolve()
    audit_log = Path(args.audit_log).expanduser().resolve() if args.audit_log else (
        repo_root / "logs" / "live_104" / "audit.jsonl"
    )
    ctx = WeeklyApyContext(
        repo_root=repo_root,
        audit_log=audit_log,
        window_days=args.window_days,
        alert_threshold=args.alert_threshold,
        drawdown_threshold=args.drawdown_threshold,
        drawdown_days=args.drawdown_days,
        topic=args.topic,
        quiet=args.quiet,
    )
    build_pipeline().run(ctx)
    if args.json:
        print(json.dumps({
            "alert_body": ctx.alert_body,
            "alert_title": ctx.alert_title,
            "apy": ctx.apy,
            "drawdown_streak": ctx.drawdown_streak,
            "exit_code": ctx.exit_code,
            "n_rows": ctx.n_rows,
            "sharpe_21d": ctx.sharpe_21d,
            "sharpe_63d": ctx.sharpe_63d,
            "summary": ctx.summary,
        }, sort_keys=True))
    elif ctx.alert_title and ctx.alert_body:
        print(f"{ctx.alert_title}: {ctx.alert_body}", file=sys.stderr)
    else:
        print(f"weekly_apy_check: healthy - {ctx.summary}")
    return ctx.exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
