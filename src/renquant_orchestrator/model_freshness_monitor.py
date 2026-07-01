"""Observe-only model freshness monitor for renquant_104 (data-cutoff-keyed).

Phase-1 of ``doc/design/2026-06-30-model-freshness-governance.md`` (#210). Reports
fast-axis freshness for the **three** model populations, each keyed on the
**binding DATA CUTOFF** — never ``trained_date`` (run time) alone, because a fresh
``trained_date`` over stale data is not fresh (design §2):

1. **Per-ticker tournament** — ``<TICKER>/<TICKER>-policy-metadata.json`` for the
   current watchlist (a coverage decision: reports min/median/max age + missing).
2. **Prod panel (XGB)** — ``artifacts/prod/panel-ltr.alpha158_fund.json``.
3. **Shadow panel (PatchTST)** — the artifact referenced by
   ``strategy_config.shadow.json`` ``ranking.panel_scoring.artifact_path`` (a model
   blob resolves to its ``<path>.metadata.json`` sidecar).

Fast-axis age tiers (design §1/§4): ``healthy`` <=14d, ``warn`` 14-21d,
``escalate`` 21-28d, ``breach`` >28d. Missing / unreadable artifacts **fail
closed** to ``breach``. The process exit code reflects the worst tier
(``healthy``=0, ``warn``=1, ``escalate``=2, ``breach``=3).

CRITICAL: ``now`` is injectable via ``--as-of`` so every time window is bounded on
both sides and tests are deterministic (never wall-clock-dependent).

OBSERVE-ONLY: this reads + reports + (behind ``--notify``) alerts. It never
retrains, promotes, or changes any pin.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
import json
from pathlib import Path
import statistics
import sys

from renquant_common import Job, Pipeline, Task

from .runtime_paths import default_github_root, default_repo_root
from .weekly_apy_monitor import post_ntfy


GITHUB = default_github_root()
DEFAULT_REPO_ROOT = default_repo_root()

# Fast-axis (daily OHLCV / price-derived / retrain-data cutoff) age tiers, design §1/§4.
DEFAULT_WARN_DAYS = 14
DEFAULT_ESCALATE_DAYS = 21
DEFAULT_BREACH_DAYS = 28

TIER_HEALTHY = "healthy"
TIER_WARN = "warn"
TIER_ESCALATE = "escalate"
TIER_BREACH = "breach"

_TIER_RANK = {TIER_HEALTHY: 0, TIER_WARN: 1, TIER_ESCALATE: 2, TIER_BREACH: 3}

# Data-cutoff axes, most-binding first. ``trained_date`` is a LAST-RESORT fallback
# only — run time is not a data-freshness axis (design §2). The binding cutoff is
# the model's most-recent data exposure; ``effective_selection_cutoff_date`` is the
# freshest such axis when present (PatchTST shadow sidecar), then the retrain/train
# cutoffs, then the per-ticker ``live_train_end``.
DATA_CUTOFF_FIELDS = (
    "effective_selection_cutoff_date",
    "effective_train_cutoff_date",
    "data_cutoff_date",
    "live_train_end",
    "cutoff_date",
)
_TRAINED_DATE_FIELD = "trained_date"

# Model blobs whose freshness metadata lives in a ``<path>.metadata.json`` sidecar.
_MODEL_BLOB_SUFFIXES = {".pt", ".pth", ".bin", ".ckpt", ".safetensors", ".onnx"}


def default_models_dir(repo_root: Path) -> Path:
    return repo_root / "backtesting" / "renquant_104" / "models"


def default_prod_panel_path(repo_root: Path) -> Path:
    return repo_root / "backtesting" / "renquant_104" / "artifacts" / "prod" / "panel-ltr.alpha158_fund.json"


def default_shadow_config_candidates(*, repo_root: Path, github_root: Path) -> tuple[Path, Path]:
    """Prefer the strategy subrepo shadow config (PatchTST), umbrella as fallback."""
    return (
        github_root / "renquant-strategy-104" / "configs" / "strategy_config.shadow.json",
        repo_root / "backtesting" / "renquant_104" / "strategy_config.shadow.json",
    )


def default_shadow_config_path(*, repo_root: Path, github_root: Path) -> Path:
    candidates = default_shadow_config_candidates(repo_root=repo_root, github_root=github_root)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def default_strategy_config_candidates(*, repo_root: Path, github_root: Path) -> tuple[Path, Path]:
    return (
        github_root / "renquant-strategy-104" / "configs" / "strategy_config.json",
        repo_root / "backtesting" / "renquant_104" / "strategy_config.json",
    )


def _parse_date(value: object) -> date | None:
    if value is None:
        return None
    text = str(value).strip()
    if len(text) < 10:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _text_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def parse_as_of(value: str | None) -> datetime | None:
    """Parse a ``--as-of`` value (date or ISO datetime) into a UTC-aware datetime."""
    if not value:
        return None
    text = str(value).strip()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        parsed = date.fromisoformat(text[:10])
        return datetime(parsed.year, parsed.month, parsed.day, tzinfo=timezone.utc)


def resolve_now(now: datetime | None) -> datetime:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        return current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc)


def tier_for_age(
    age_days: int | None,
    *,
    warn_days: int = DEFAULT_WARN_DAYS,
    escalate_days: int = DEFAULT_ESCALATE_DAYS,
    breach_days: int = DEFAULT_BREACH_DAYS,
) -> str:
    """Fast-axis tier for a data-cutoff age; ``None`` (no cutoff) fails closed."""
    if age_days is None:
        return TIER_BREACH
    if age_days > breach_days:
        return TIER_BREACH
    if age_days > escalate_days:
        return TIER_ESCALATE
    if age_days > warn_days:
        return TIER_WARN
    return TIER_HEALTHY


def worst_tier(tiers: list[str]) -> str:
    worst = TIER_HEALTHY
    for tier in tiers:
        if _TIER_RANK.get(tier, 0) > _TIER_RANK[worst]:
            worst = tier
    return worst


@dataclass
class ArtifactFreshness:
    """Freshness of a single JSON model artifact keyed on its binding data cutoff."""

    label: str
    path: str
    present: bool = False
    trained_date: str | None = None
    binding_cutoff: str | None = None
    binding_field: str | None = None
    age_days: int | None = None
    tier: str = TIER_BREACH
    detail: str = ""

    def as_dict(self) -> dict:
        return {
            "age_days": self.age_days,
            "binding_cutoff": self.binding_cutoff,
            "binding_field": self.binding_field,
            "detail": self.detail,
            "label": self.label,
            "path": self.path,
            "present": self.present,
            "tier": self.tier,
            "trained_date": self.trained_date,
        }


def read_artifact_freshness(
    label: str,
    path: Path | None,
    now: datetime,
    *,
    warn_days: int = DEFAULT_WARN_DAYS,
    escalate_days: int = DEFAULT_ESCALATE_DAYS,
    breach_days: int = DEFAULT_BREACH_DAYS,
) -> ArtifactFreshness:
    """Read one JSON artifact and derive its data-cutoff-keyed freshness tier.

    Missing / unreadable / cutoff-less artifacts fail closed to ``breach``.
    """
    result = ArtifactFreshness(label=label, path="" if path is None else str(path))
    if path is None:
        result.detail = "no artifact path resolved (fail-closed)"
        return result
    if not path.exists():
        result.detail = f"artifact missing: {path} (fail-closed)"
        return result
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        result.detail = f"unreadable artifact: {exc} (fail-closed)"
        return result
    if not isinstance(data, dict):
        result.detail = "artifact is not a JSON object (fail-closed)"
        return result

    result.present = True
    result.trained_date = _text_or_none(data.get(_TRAINED_DATE_FIELD))

    for field_name in DATA_CUTOFF_FIELDS:
        if _parse_date(data.get(field_name)) is not None:
            result.binding_cutoff = str(data[field_name]).strip()[:10]
            result.binding_field = field_name
            break
    if result.binding_cutoff is None and _parse_date(result.trained_date) is not None:
        result.binding_cutoff = result.trained_date[:10]
        result.binding_field = _TRAINED_DATE_FIELD

    cutoff = _parse_date(result.binding_cutoff)
    if cutoff is None:
        result.detail = "no parseable trained_date or data cutoff (fail-closed)"
        result.tier = TIER_BREACH
        return result

    result.age_days = (now.date() - cutoff).days
    result.tier = tier_for_age(
        result.age_days,
        warn_days=warn_days,
        escalate_days=escalate_days,
        breach_days=breach_days,
    )
    fallback = "; trained_date fallback (no data-cutoff field)" if result.binding_field == _TRAINED_DATE_FIELD else ""
    result.detail = f"{result.binding_field}={result.binding_cutoff} age={result.age_days}d{fallback}"
    return result


@dataclass
class TournamentFreshness:
    """Coverage + age spread for the per-ticker tournament population."""

    n_expected: int = 0
    n_present: int = 0
    n_missing: int = 0
    missing: list[str] = field(default_factory=list)
    min_age_days: int | None = None
    median_age_days: float | None = None
    max_age_days: int | None = None
    per_ticker: list[ArtifactFreshness] = field(default_factory=list)
    tier: str = TIER_BREACH
    detail: str = ""

    def as_dict(self) -> dict:
        return {
            "detail": self.detail,
            "max_age_days": self.max_age_days,
            "median_age_days": self.median_age_days,
            "min_age_days": self.min_age_days,
            "missing": list(self.missing),
            "n_expected": self.n_expected,
            "n_missing": self.n_missing,
            "n_present": self.n_present,
            "tier": self.tier,
        }


def read_tournament_freshness(
    models_dir: Path,
    watchlist: list[str],
    now: datetime,
    *,
    warn_days: int = DEFAULT_WARN_DAYS,
    escalate_days: int = DEFAULT_ESCALATE_DAYS,
    breach_days: int = DEFAULT_BREACH_DAYS,
) -> TournamentFreshness:
    result = TournamentFreshness(n_expected=len(watchlist))
    if not watchlist:
        result.tier = TIER_BREACH
        result.detail = "empty watchlist (fail-closed)"
        return result

    ages: list[int] = []
    tiers: list[str] = []
    for ticker in watchlist:
        path = models_dir / ticker / f"{ticker}-policy-metadata.json"
        freshness = read_artifact_freshness(
            f"tournament:{ticker}",
            path,
            now,
            warn_days=warn_days,
            escalate_days=escalate_days,
            breach_days=breach_days,
        )
        result.per_ticker.append(freshness)
        tiers.append(freshness.tier)
        if freshness.present and freshness.age_days is not None:
            result.n_present += 1
            ages.append(freshness.age_days)
        else:
            result.n_missing += 1
            result.missing.append(ticker)

    if ages:
        ordered = sorted(ages)
        result.min_age_days = ordered[0]
        result.max_age_days = ordered[-1]
        result.median_age_days = statistics.median(ordered)

    # Missing tickers already fail closed to breach in ``tiers``.
    result.tier = worst_tier(tiers)
    age_part = (
        f"age min/med/max={result.min_age_days}/{result.median_age_days}/{result.max_age_days}d"
        if ages
        else "no present ages"
    )
    missing_part = f" missing={len(result.missing)}" if result.missing else ""
    result.detail = f"{result.n_present}/{result.n_expected} present {age_part}{missing_part}"
    return result


def _freshness_path_for(artifact: Path) -> Path:
    """A model blob's freshness lives in a ``<path>.metadata.json`` sidecar."""
    if artifact.suffix.lower() in _MODEL_BLOB_SUFFIXES:
        return artifact.with_name(artifact.name + ".metadata.json")
    return artifact


def resolve_shadow_artifact_path(
    config_path: Path | None,
    *,
    search_bases: list[Path] | None = None,
) -> Path | None:
    """Resolve the shadow panel scoring artifact JSON (blob -> ``.metadata.json``).

    A relative ``artifact_path`` is tried against each of ``search_bases`` (the
    pinned subrepo config stores it relative to the *deployed* umbrella location,
    e.g. ``../../artifacts/...`` from ``backtesting/renquant_104``); the first
    candidate whose freshness JSON exists wins, otherwise the first candidate is
    returned so the caller fails closed on a concrete path.
    """
    if config_path is None or not config_path.exists():
        return None
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    raw = (((config.get("ranking") or {}).get("panel_scoring") or {}).get("artifact_path"))
    if not raw:
        return None

    artifact = Path(str(raw))
    if artifact.is_absolute():
        return _freshness_path_for(artifact)

    bases = search_bases or [config_path.parent]
    candidates = [_freshness_path_for((base / artifact).resolve()) for base in bases]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _watchlist_from_config(path: Path) -> list[str]:
    if not path.exists():
        return []
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    watchlist = config.get("watchlist")
    if isinstance(watchlist, list):
        return [str(t).strip().upper() for t in watchlist if str(t).strip()]
    return []


def _watchlist_from_prod_panel(path: Path) -> list[str]:
    if not path.exists():
        return []
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    watchlist = (artifact.get("config_fingerprint_fields") or {}).get("watchlist")
    if isinstance(watchlist, list):
        return [str(t).strip().upper() for t in watchlist if str(t).strip()]
    return []


def _watchlist_from_models_dir(models_dir: Path) -> list[str]:
    if not models_dir.is_dir():
        return []
    tickers = [
        entry.name
        for entry in models_dir.iterdir()
        if entry.is_dir() and (entry / f"{entry.name}-policy-metadata.json").exists()
    ]
    return sorted(tickers)


def resolve_watchlist(
    explicit: list[str] | None,
    *,
    strategy_config_path: Path,
    prod_panel_path: Path,
    models_dir: Path,
) -> tuple[list[str], str]:
    """Resolve the tournament watchlist (explicit > strategy config > panel > scan)."""
    if explicit:
        return [t.strip().upper() for t in explicit if t.strip()], "explicit"
    watchlist = _watchlist_from_config(strategy_config_path)
    if watchlist:
        return watchlist, f"strategy_config:{strategy_config_path.name}"
    watchlist = _watchlist_from_prod_panel(prod_panel_path)
    if watchlist:
        return watchlist, "prod_panel:config_fingerprint_fields.watchlist"
    watchlist = _watchlist_from_models_dir(models_dir)
    if watchlist:
        return watchlist, "models_dir_scan"
    return [], "none"


@dataclass
class ModelFreshnessContext:
    now: datetime
    repo_root: Path
    github_root: Path
    models_dir: Path
    prod_panel_path: Path
    shadow_config_path: Path
    strategy_config_path: Path
    explicit_watchlist: list[str] | None = None
    warn_days: int = DEFAULT_WARN_DAYS
    escalate_days: int = DEFAULT_ESCALATE_DAYS
    breach_days: int = DEFAULT_BREACH_DAYS
    topic: str = "renquant"
    quiet: bool = False
    notify: bool = False
    watchlist: list[str] = field(default_factory=list)
    watchlist_source: str = ""
    tournament: TournamentFreshness | None = None
    prod_panel: ArtifactFreshness | None = None
    shadow_panel: ArtifactFreshness | None = None
    shadow_artifact_path: Path | None = None
    worst_tier: str = TIER_HEALTHY
    exit_code: int = 0
    summary: str = ""
    alert_title: str | None = None
    alert_body: str | None = None


class ResolveWatchlistTask(Task):
    def run(self, ctx: ModelFreshnessContext) -> bool | None:
        ctx.watchlist, ctx.watchlist_source = resolve_watchlist(
            ctx.explicit_watchlist,
            strategy_config_path=ctx.strategy_config_path,
            prod_panel_path=ctx.prod_panel_path,
            models_dir=ctx.models_dir,
        )
        return True


class ComputeFreshnessTask(Task):
    def run(self, ctx: ModelFreshnessContext) -> bool | None:
        thresholds = dict(
            warn_days=ctx.warn_days,
            escalate_days=ctx.escalate_days,
            breach_days=ctx.breach_days,
        )
        ctx.tournament = read_tournament_freshness(
            ctx.models_dir, ctx.watchlist, ctx.now, **thresholds
        )
        ctx.prod_panel = read_artifact_freshness(
            "prod-panel", ctx.prod_panel_path, ctx.now, **thresholds
        )
        ctx.shadow_artifact_path = resolve_shadow_artifact_path(
            ctx.shadow_config_path,
            search_bases=[
                ctx.shadow_config_path.parent,
                ctx.repo_root / "backtesting" / "renquant_104",
                ctx.repo_root,
            ],
        )
        ctx.shadow_panel = read_artifact_freshness(
            "shadow-panel", ctx.shadow_artifact_path, ctx.now, **thresholds
        )
        ctx.worst_tier = worst_tier(
            [ctx.tournament.tier, ctx.prod_panel.tier, ctx.shadow_panel.tier]
        )
        ctx.summary = self._summary(ctx)
        return True

    @staticmethod
    def _summary(ctx: ModelFreshnessContext) -> str:
        lines = [
            f"model-freshness @ {ctx.now.date().isoformat()} "
            f"(worst={ctx.worst_tier.upper()}; watchlist={ctx.watchlist_source})",
            f"  [{ctx.tournament.tier}] tournament: {ctx.tournament.detail}",
            f"  [{ctx.prod_panel.tier}] {ctx.prod_panel.label}: {ctx.prod_panel.detail}",
            f"  [{ctx.shadow_panel.tier}] {ctx.shadow_panel.label}: {ctx.shadow_panel.detail}",
        ]
        return "\n".join(lines)


class DecideFreshnessAlertTask(Task):
    def run(self, ctx: ModelFreshnessContext) -> bool | None:
        ctx.exit_code = _TIER_RANK[ctx.worst_tier]
        if ctx.worst_tier != TIER_HEALTHY:
            ctx.alert_title = f"RenQuant 104 model freshness {ctx.worst_tier.upper()}"
            ctx.alert_body = ctx.summary
        return True


class EmitFreshnessAlertTask(Task):
    def run(self, ctx: ModelFreshnessContext) -> bool | None:
        if ctx.alert_title and ctx.alert_body and ctx.notify and not ctx.quiet:
            post_ntfy(ctx.alert_title, ctx.alert_body, ctx.topic)
        return True


class ResolveWatchlistJob(Job):
    @property
    def tasks(self) -> list[Task]:
        return [ResolveWatchlistTask()]


class ComputeFreshnessJob(Job):
    @property
    def tasks(self) -> list[Task]:
        return [ComputeFreshnessTask()]


class FreshnessAlertJob(Job):
    @property
    def tasks(self) -> list[Task]:
        return [DecideFreshnessAlertTask(), EmitFreshnessAlertTask()]


def build_pipeline() -> Pipeline:
    return Pipeline(
        [ResolveWatchlistJob(), ComputeFreshnessJob(), FreshnessAlertJob()],
        name="model-freshness-monitor",
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", default=None, help="Inject 'now' (YYYY-MM-DD or ISO datetime); defaults to UTC now.")
    parser.add_argument("--repo-root", type=Path, default=DEFAULT_REPO_ROOT)
    parser.add_argument("--github-root", type=Path, default=GITHUB)
    parser.add_argument("--models-dir", type=Path, default=None)
    parser.add_argument("--prod-panel", type=Path, default=None)
    parser.add_argument("--shadow-config", type=Path, default=None)
    parser.add_argument("--strategy-config", type=Path, default=None)
    parser.add_argument("--watchlist", default=None, help="Comma-separated tickers; overrides config/scan resolution.")
    parser.add_argument("--warn-days", type=int, default=DEFAULT_WARN_DAYS)
    parser.add_argument("--escalate-days", type=int, default=DEFAULT_ESCALATE_DAYS)
    parser.add_argument("--breach-days", type=int, default=DEFAULT_BREACH_DAYS)
    parser.add_argument("--topic", default="renquant")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--notify", action="store_true", help="Post an ntfy alert when the worst tier is not healthy.")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def _context_json(ctx: ModelFreshnessContext) -> dict:
    return {
        "alert_body": ctx.alert_body,
        "alert_title": ctx.alert_title,
        "exit_code": ctx.exit_code,
        "now": ctx.now.isoformat(),
        "prod_panel": ctx.prod_panel.as_dict() if ctx.prod_panel else None,
        "shadow_panel": ctx.shadow_panel.as_dict() if ctx.shadow_panel else None,
        "summary": ctx.summary,
        "thresholds": {
            "breach_days": ctx.breach_days,
            "escalate_days": ctx.escalate_days,
            "warn_days": ctx.warn_days,
        },
        "tournament": ctx.tournament.as_dict() if ctx.tournament else None,
        "watchlist_source": ctx.watchlist_source,
        "worst_tier": ctx.worst_tier,
    }


def build_context(args: argparse.Namespace) -> ModelFreshnessContext:
    repo_root = args.repo_root.expanduser().resolve()
    github_root = args.github_root.expanduser().resolve()
    models_dir = (args.models_dir or default_models_dir(repo_root)).expanduser().resolve()
    prod_panel = (args.prod_panel or default_prod_panel_path(repo_root)).expanduser().resolve()
    shadow_config = (
        args.shadow_config
        or default_shadow_config_path(repo_root=repo_root, github_root=github_root)
    ).expanduser().resolve()
    strategy_config = (
        args.strategy_config
        or default_strategy_config_candidates(repo_root=repo_root, github_root=github_root)[1]
    ).expanduser().resolve()
    explicit = (
        [t for t in str(args.watchlist).split(",") if t.strip()] if args.watchlist else None
    )
    return ModelFreshnessContext(
        now=resolve_now(parse_as_of(args.as_of)),
        repo_root=repo_root,
        github_root=github_root,
        models_dir=models_dir,
        prod_panel_path=prod_panel,
        shadow_config_path=shadow_config,
        strategy_config_path=strategy_config,
        explicit_watchlist=explicit,
        warn_days=args.warn_days,
        escalate_days=args.escalate_days,
        breach_days=args.breach_days,
        topic=args.topic,
        quiet=args.quiet,
        notify=args.notify,
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    ctx = build_context(args)
    build_pipeline().run(ctx)
    if args.json:
        print(json.dumps(_context_json(ctx), sort_keys=True))
    else:
        print(ctx.summary)
        if ctx.alert_title and ctx.alert_body:
            print(f"{ctx.alert_title}: {ctx.alert_body}", file=sys.stderr)
    return ctx.exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
