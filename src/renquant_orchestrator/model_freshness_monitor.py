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

Each population keys on a **per-population** freshness policy (never one global
scalar): the per-ticker tournament and the prod XGB panel use the prod fast-axis
tiers (design §1/§4: ``healthy`` <=14d, ``warn`` 14-21d, ``escalate`` 21-28d,
``breach`` >28d), while the **shadow PatchTST panel** uses the merged RFC #212 §3.2
shadow policy (looser 35d breach ceiling because shadow is non-trading, AND keyed on
a persisted, pin-bound **promotion receipt** — never a free, spoofable sidecar
boolean).

**Panel freshness axis (umbrella #423, round-3 CORRECTED).** The prod XGB panel
stamps TWO DISTINCT information-set fields (never conflated). This module's own
round-2 fix keyed panel freshness on ``max_feature_anchor_date``; Codex's round-3
review on #423 established that is WRONG, so the roles are swapped here:

- ``label_observation_cutoff`` — the fwd-label-clipped max FULLY-LABELED training
  row. THIS is the freshness axis: it is the latest information that actually
  affected fitting (weights/normalization/CV), and only moves when the labeled
  training frame moves. Because the label horizon means even a same-day retrain
  cannot show a label more recent than the model's OWN horizon ago, the panel
  fast-axis policy WIDENS its tiering thresholds by that EXPECTED lag (never
  subtracted from the reported age) so a genuinely fresh retrain reads HEALTHY,
  not born-BREACH. The prod XGB panel today trains on ``fwd_60d`` (~60 business
  days), but the widening is derived from THIS ARTIFACT's own stamped
  ``lookahead_days`` (#223 amendment A1), never a hardcoded 60 — a different
  model family with a different label horizon (or an artifact that fails to
  stamp its horizon) is never silently assumed to be fwd_60d.
- ``max_feature_anchor_date`` — the RAW feature/data frontier (latest date with
  feature rows, BEFORE the fwd-label ``dropna`` clip; leads the label axis by
  the model's label horizon by construction — ~60 business days for the prod
  XGB panel today). This is **data-pipeline-HEALTH provenance
  only** (proof the feed is current) — **NOT** a freshness axis. Those trailing
  rows carry no observable forward label, so the model's weights/CV never
  consumed them: keying freshness here would let fresh UNLABELED rows make a
  frozen, never-retrained model read fresh ("fresh metadata over stale trained
  information" under a new field name — the exact bug #423 round-3 rejects). It
  is captured for context only and is never used for tiering.

**Shadow promote binding (umbrella #419 / RFC #212 §3.2).** The served shadow pin's
freshness reaches ``healthy`` only when a persisted **promotion receipt** (written by
``scripts/promote_shadow_patchtst.py`` to ``logs/promote_shadow_patchtst/*.json``)
certifies it. The receipt is validated to **bind** the served pin (``promoted_pin``),
the source cutoffs it saw (``source_verdicts[].data_cutoff``), the gate build that
judged it (``gate_version``), the candidate bytes (``candidate_sha256`` vs the served
``.pt`` hash) and the validation result (``rc``/``fresh``/``gates``). A missing,
unreadable, unbound (superseded/stale) or under-populated receipt **FAILS CLOSED**
(escalate — the served pin can never read ``healthy`` on age alone); a receipt that
labels the pin non-fresh, fails validation, or whose digest does not match the served
bytes fails closed to ``breach``. A free boolean in the sidecar is spoofable and stale
after an artifact replacement, so it is NOT trusted.

Fail-closed states, kept DISTINCT so operators can tell them apart:

- ``breach``  — the binding data cutoff is known but too OLD (or a future/look-ahead
  cutoff, or a shadow pin labeled non-fresh).
- ``unknown`` — the binding DATA cutoff is missing / unparseable. This is NOT
  ``trained_date`` (run time): a fresh ``trained_date`` over stale/absent data does
  NOT certify freshness (design §2). ``trained_date`` is informational context only.
  ``unknown`` fails closed at breach severity for the exit code / alerting.

Missing / unreadable artifacts **fail closed** to ``breach``. The process exit code
reflects the worst tier (``healthy``=0, ``warn``=1, ``escalate``=2, ``breach``=3,
``unknown``=3 [breach-severity]).

CRITICAL: ``now`` is injectable via ``--as-of`` so every time window is bounded on
both sides (a cutoff LATER than ``now`` is rejected as a look-ahead, never treated as
a negative age that reads healthy) and tests are deterministic.

OBSERVE-ONLY: this reads + reports + (behind ``--notify``) alerts. It never
retrains, promotes, or changes any pin.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import statistics
import sys

from renquant_common import Job, Pipeline, Task

from .runtime_paths import default_github_root, default_repo_root
from .weekly_apy_monitor import post_ntfy


GITHUB = default_github_root()
DEFAULT_REPO_ROOT = default_repo_root()

# Prod fast-axis (daily OHLCV / price-derived / retrain-data cutoff) age tiers, design §1/§4.
DEFAULT_WARN_DAYS = 14
DEFAULT_ESCALATE_DAYS = 21
DEFAULT_BREACH_DAYS = 28

# Shadow PatchTST fast-axis tiers — merged RFC #212 §3.2: a looser breach ceiling
# (35d, because the shadow moves no capital) AND keyed on validated-promote status.
# NOT the prod 28d scalar applied uniformly to all three populations.
SHADOW_WARN_DAYS = 28
SHADOW_ESCALATE_DAYS = 33
SHADOW_BREACH_DAYS = 35

TIER_HEALTHY = "healthy"
TIER_WARN = "warn"
TIER_ESCALATE = "escalate"
TIER_BREACH = "breach"
# UNKNOWN = binding DATA cutoff missing/unparseable. Reported SEPARATELY from a
# too-old ``breach`` (design §2 / #210: trained_date must never certify freshness),
# but fails closed at breach severity for the exit code / alerting.
TIER_UNKNOWN = "unknown"

# Ordering for the headline "worst" tier. ``unknown`` ranks ABOVE ``breach`` (a
# missing cutoff is at least as alarming as a stale one — you cannot even tell how
# stale it is), but both map to exit code 3 (breach severity) via ``_TIER_EXIT_CODE``.
_TIER_RANK = {TIER_HEALTHY: 0, TIER_WARN: 1, TIER_ESCALATE: 2, TIER_BREACH: 3, TIER_UNKNOWN: 4}
_TIER_EXIT_CODE = {TIER_HEALTHY: 0, TIER_WARN: 1, TIER_ESCALATE: 2, TIER_BREACH: 3, TIER_UNKNOWN: 3}

# Data-cutoff axes, most-binding first. The binding cutoff is the model's most-recent
# DATA exposure -- specifically the latest information that actually affected fitting.
# ``label_observation_cutoff`` (umbrella #423 round-3) is the fwd_60d-clipped max
# FULLY-LABELED training row and leads this list: it is the panel's freshness axis
# (round-3 Codex review REJECTED keying freshness on ``max_feature_anchor_date`` --
# see the module docstring). Its ~60 business-day EXPECTED lag is accounted for by
# widening the tiering thresholds (``_AXIS_EXPECTED_LAG_BDAYS`` /
# ``_expected_lag_calendar_days`` below), never by omitting it from this list. Then the
# PatchTST shadow ``effective_selection_cutoff_date``, the retrain/train cutoffs, and
# the per-ticker ``live_train_end``. ``max_feature_anchor_date`` is deliberately NOT in
# this list (data-pipeline-health provenance only, never a freshness axis -- captured
# separately below). ``trained_date`` (run time) is also deliberately NOT in this list:
# it is not a data-freshness axis (design §2) and never certifies freshness — a missing
# binding cutoff fails closed to ``unknown`` instead of falling back to it.
DATA_CUTOFF_FIELDS = (
    "label_observation_cutoff",
    "effective_selection_cutoff_date",
    "effective_train_cutoff_date",
    "data_cutoff_date",
    "live_train_end",
    "cutoff_date",
)
_TRAINED_DATE_FIELD = "trained_date"
# The freshness-axis field name, named so the EXPECTED fwd-label-horizon lag (below)
# can be keyed on it without hardcoding the string in multiple places.
_LABEL_OBSERVATION_FIELD = "label_observation_cutoff"
# #223 amendment A1: the artifact's OWN declared label horizon (stamped by
# ``hf_patchtst_scorer.py`` / ``train_production_model.py::build_artifact`` in the
# RenQuant umbrella repo) — read per-artifact instead of assuming a single constant
# horizon for every model family.
_LOOKAHEAD_DAYS_FIELD = "lookahead_days"

# PROVENANCE-only field: captured + echoed for context, NEVER used for tiering.
# ``max_feature_anchor_date`` (umbrella #423) is the RAW feature/data frontier, ~60
# business days AHEAD of the label-observation cutoff by construction (it includes
# rows whose forward label is not yet observable). It is data-pipeline-HEALTH
# provenance (proof the feed is current) — NOT model freshness: those trailing rows
# were excluded from training, so appending fresh unlabeled rows to a frozen panel
# must never make a stale model read fresh (Codex #423 round-3 review).
_FEATURE_ANCHOR_FIELD = "max_feature_anchor_date"

# Axes that carry an INHERENT horizon lag, mapped to the DOCUMENTED DEFAULT width
# (absent / 0 for axes with none). ``label_observation_cutoff`` is fwd-label-clipped:
# even a same-day retrain cannot show a label more recent than the model's OWN label
# horizon ago (the horizon is WHY the trailing rows are still unlabeled), so its age
# must be measured against that EXPECTED frontier — never against ``now`` directly,
# or every fresh retrain would read born-BREACH.
#
# 2026-07-02 (#223 amendment A1: "each model family declares its label horizon in
# its recipe ... not hardcoded to one constant"). This dict now serves ONLY to name
# WHICH axes need compensation and the DIAGNOSTIC default shown when an artifact's
# own horizon is unknown — it is NEVER used to widen a tier. The ACTUAL compensation
# width is read PER-ARTIFACT from its own stamped ``lookahead_days`` field (stamped
# by ``hf_patchtst_scorer.py`` / ``train_production_model.py::build_artifact`` in
# the RenQuant umbrella repo) by ``_expected_lag_calendar_days`` below. This monitor
# covers THREE populations — per-ticker tournament, prod XGB panel (fwd_60d today),
# shadow PatchTST panel — and a future model family can have a genuinely different
# label horizon; assuming this default for every artifact would mis-widen (or
# under-widen) a different recipe's threshold. Per ``_expected_lag_calendar_days``, a
# missing/invalid stamped horizon on an axis that needs compensation now fails
# closed to ``TIER_UNKNOWN`` instead of silently certifying a tier under this
# guessed default.
_LABEL_OBSERVATION_LOOKAHEAD_BDAYS = 60
_AXIS_EXPECTED_LAG_BDAYS: dict[str, int] = {
    _LABEL_OBSERVATION_FIELD: _LABEL_OBSERVATION_LOOKAHEAD_BDAYS,
}

# 2026-07-02 (Codex #225 round 2): a self-declared ``lookahead_days`` is
# NECESSARY but not SUFFICIENT — the round-1 fix accepted ANY value coerced
# via ``int(...)``, which silently accepted ``True`` (== 1), floats (e.g.
# ``60.9``), numeric strings (e.g. ``"60"``), and — critically — any
# unboundedly large integer. A stale artifact could therefore certify
# itself HEALTHY by stamping ``lookahead_days=6000``, widening every
# threshold by ~6000 business days. This repo's artifacts carry no existing
# recipe/model-kind identifier field to bind an expected horizon against
# (all three populations this monitor covers — per-ticker tournament, prod
# XGB panel, shadow PatchTST panel — currently use fwd_60d), so the
# accepted value is bound to an EXPLICIT PLAUSIBLE RANGE instead: up to 2x
# the documented fwd_60d convention — generous enough for a plausible
# future shorter/longer-horizon model, but rejecting clearly-implausible or
# corrupted values. If/when artifacts gain a real recipe/schema identifier,
# replace this range check with a per-recipe expected-value lookup (mirrors
# the training-side provenance-schema fix landing concurrently in
# RenQuant's shadow_scoring.py — #426).
_MIN_PLAUSIBLE_LOOKAHEAD_BDAYS = 1
_MAX_PLAUSIBLE_LOOKAHEAD_BDAYS = 2 * _LABEL_OBSERVATION_LOOKAHEAD_BDAYS


def _validate_lookahead_days(value: object) -> int | None:
    """Strictly validate a stamped ``lookahead_days`` value: must be an
    EXACT JSON integer — never a ``bool`` (``int(True) == 1`` would
    otherwise silently accept it), a ``float``, or a numeric string — AND
    within the explicit plausible range (#225 round 2). Returns the
    validated int, or ``None`` if the value fails any check; callers MUST
    treat ``None`` exactly like a missing horizon (fail closed to
    ``TIER_UNKNOWN``), never fall back to guessing a default from it."""
    if not isinstance(value, int) or isinstance(value, bool):
        return None
    if not (_MIN_PLAUSIBLE_LOOKAHEAD_BDAYS <= value <= _MAX_PLAUSIBLE_LOOKAHEAD_BDAYS):
        return None
    return value

# Model blobs whose freshness metadata lives in a ``<path>.metadata.json`` sidecar.
_MODEL_BLOB_SUFFIXES = {".pt", ".pth", ".bin", ".ckpt", ".safetensors", ".onnx"}

# Persisted shadow promotion receipts (umbrella #419 / RFC #212 §5): one JSON per
# validated served-pin promote, written under ``<repo_root>/logs/promote_shadow_patchtst``.
_PROMOTE_RECEIPT_DIRNAME = ("logs", "promote_shadow_patchtst")


def default_promote_receipt_dir(repo_root: Path) -> Path:
    return repo_root.joinpath(*_PROMOTE_RECEIPT_DIRNAME)


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


def _optional_bool(value: object) -> bool | None:
    """Parse a JSON-ish bool (native, or a "true"/"false"/"1"/"0" string); else None."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    return None


def _subtract_business_days(base: date, n: int) -> date:
    """Subtract ``n`` Mon-Fri business days from ``base``. Matches
    ``pandas.offsets.BDay`` weekday semantics (no holiday calendar) — sufficient for
    a fixed, documented label horizon (#423)."""
    current = base
    remaining = n
    while remaining > 0:
        current -= timedelta(days=1)
        if current.weekday() < 5:
            remaining -= 1
    return current


def _expected_lag_calendar_days(
    binding_field: str | None, lookahead_bdays: object, now: datetime
) -> tuple[int | None, int]:
    """Calendar-day width of ``binding_field``'s EXPECTED business-day lag as of
    ``now`` (0 for axes with no inherent horizon lag — every axis except
    ``label_observation_cutoff``). Used to WIDEN the tiering thresholds so a
    genuinely fresh artifact on a lagged axis does not read born-stale (#423
    round-3): a same-day retrain's ``label_observation_cutoff`` is ~60 business
    days behind ``now`` by construction, and that gap is expected, not staleness.
    ``age_days`` itself is never adjusted — only the ceilings it is compared
    against.

    Returns ``(compensation_lag, diagnostic_lag)``:

    - ``compensation_lag`` is the value :func:`read_artifact_freshness` may
      actually use to widen a tiering threshold. It requires the artifact's
      OWN stamped ``lookahead_days`` to be a genuine positive integer — this
      monitor covers THREE populations (per-ticker tournament, prod XGB
      panel, shadow PatchTST panel), and a future model family can have a
      different label horizon (per-ticker tournament != fwd_60d panel != any
      future short-horizon model, #223 amendment A1). Silently assuming the
      documented ``_LABEL_OBSERVATION_LOOKAHEAD_BDAYS`` default for every
      artifact would mis-widen (or under-widen) a different recipe's
      threshold, and would let a genuinely unstamped/unknown horizon be
      guessed into a certified tier — exactly the class of bug this module's
      own "trained_date must never certify freshness" discipline exists to
      prevent (see module docstring). ``None`` means "this axis needs
      compensation but the artifact did not stamp a positive
      ``lookahead_days``" — the caller must fail closed to ``TIER_UNKNOWN``,
      never apply the default as a guess.
    - ``diagnostic_lag`` is ALWAYS computed (using
      ``_LABEL_OBSERVATION_LOOKAHEAD_BDAYS`` when the stamped value is
      missing/invalid) purely for the ``detail`` string — "would have been Nd
      if the documented 60-BD default were assumed" — troubleshooting only,
      NEVER used to widen a tier when ``compensation_lag`` is ``None``.
    """
    bdays_default = _AXIS_EXPECTED_LAG_BDAYS.get(binding_field or "", 0)
    if not bdays_default:
        return 0, 0
    stamped_bdays = _validate_lookahead_days(lookahead_bdays) or 0
    diagnostic_bdays = stamped_bdays if stamped_bdays > 0 else bdays_default
    diagnostic_frontier = _subtract_business_days(now.date(), diagnostic_bdays)
    diagnostic_lag = (now.date() - diagnostic_frontier).days
    if stamped_bdays <= 0:
        return None, diagnostic_lag
    return diagnostic_lag, diagnostic_lag


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


@dataclass(frozen=True)
class FreshnessPolicy:
    """Per-population freshness policy.

    Makes the tiering ceilings and any promote-status gate EXPLICIT per population so
    the prod fast axis and the shadow (RFC #212) axis are never conflated into one
    global scalar. ``require_validated_promote`` additionally keys the shadow tier on
    the served pin's validated-promote status (RFC #212 §3.2).
    """

    name: str
    warn_days: int = DEFAULT_WARN_DAYS
    escalate_days: int = DEFAULT_ESCALATE_DAYS
    breach_days: int = DEFAULT_BREACH_DAYS
    require_validated_promote: bool = False

    def as_dict(self) -> dict:
        return {
            "breach_days": self.breach_days,
            "escalate_days": self.escalate_days,
            "name": self.name,
            "require_validated_promote": self.require_validated_promote,
            "warn_days": self.warn_days,
        }


# Prod fast-axis policy: per-ticker tournament + prod XGB panel (governance §1/§4).
PROD_FAST_POLICY = FreshnessPolicy(
    name="prod-fast-axis",
    warn_days=DEFAULT_WARN_DAYS,
    escalate_days=DEFAULT_ESCALATE_DAYS,
    breach_days=DEFAULT_BREACH_DAYS,
)

# Shadow PatchTST policy: merged RFC #212 §3.2 — 35d breach ceiling + validated-promote.
SHADOW_POLICY = FreshnessPolicy(
    name="shadow-patchtst",
    warn_days=SHADOW_WARN_DAYS,
    escalate_days=SHADOW_ESCALATE_DAYS,
    breach_days=SHADOW_BREACH_DAYS,
    require_validated_promote=True,
)


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
    # PROVENANCE only (umbrella #423 round-3): the RAW feature/data frontier, ~60d
    # AHEAD of the (tiered) label-observation cutoff. Data-pipeline-health context
    # only; NEVER used for tiering (round-3 Codex review — see module docstring).
    max_feature_anchor_date: str | None = None
    # Shadow (RFC #212 §3.2) only: validated-promote status derived from a persisted,
    # pin-bound promotion RECEIPT (never a sidecar boolean). ``None`` when the
    # population has no promote gate; ``True`` only when a bound, validated receipt
    # certifies the served pin.
    promote_validated: bool | None = None
    non_fresh: bool = False
    promotion_status: str | None = None
    promotion_receipt_path: str | None = None
    # #223 amendment A1: the artifact's OWN stamped ``lookahead_days`` (the label
    # horizon this recipe declares), strictly validated (#225 round 2: exact JSON
    # int, not bool/float/string, within the explicit plausible range — see
    # ``_validate_lookahead_days``). ``None`` when the binding axis needs horizon
    # compensation but no valid value was stamped — the tier fails closed to
    # ``unknown`` in that case (see ``read_artifact_freshness``). Always ``None``
    # for an axis that does not need compensation at all.
    lookahead_days_stamped: int | None = None
    # #225 round 2: what ``lookahead_days_stamped`` was validated against, so the
    # validation basis is part of the observable record, not just an internal
    # pass/fail. ``None`` when no horizon was stamped/validated at all.
    horizon_validated_against: str | None = None

    def as_dict(self) -> dict:
        return {
            "age_days": self.age_days,
            "binding_cutoff": self.binding_cutoff,
            "binding_field": self.binding_field,
            "detail": self.detail,
            "horizon_validated_against": self.horizon_validated_against,
            "label": self.label,
            "lookahead_days_stamped": self.lookahead_days_stamped,
            "max_feature_anchor_date": self.max_feature_anchor_date,
            "non_fresh": self.non_fresh,
            "path": self.path,
            "promote_validated": self.promote_validated,
            "promotion_receipt_path": self.promotion_receipt_path,
            "promotion_status": self.promotion_status,
            "tier": self.tier,
            "trained_date": self.trained_date,
        }


def read_artifact_freshness(
    label: str,
    path: Path | None,
    now: datetime,
    *,
    policy: FreshnessPolicy = PROD_FAST_POLICY,
) -> ArtifactFreshness:
    """Read one JSON artifact and derive its data-cutoff-keyed freshness tier.

    Fail-closed semantics (all kept DISTINCT so operators can act on them):

    - missing / unreadable / non-object artifact -> ``breach``;
    - a missing / unparseable **binding DATA cutoff** -> ``unknown`` (breach-severity
      for exit code, reported separately from a too-old ``breach``). ``trained_date``
      is captured as informational context ONLY and never certifies freshness (§2);
    - a cutoff **later than** ``now`` -> ``breach`` (look-ahead; a negative age must
      never read as ``healthy`` — PR #211 lesson, windows bounded on both sides).

    The freshness axis for the panel is ``label_observation_cutoff`` (the fwd-label-
    clipped max LABELED row — the latest information that actually affected fitting,
    umbrella #423 round-3); its EXPECTED label-horizon lag WIDENS the tiering
    thresholds (never subtracted from the reported ``age_days``) so a genuinely fresh
    retrain reads HEALTHY. The lag width is read from THIS ARTIFACT's own stamped
    ``lookahead_days`` (#223 amendment A1: per-recipe, not one hardcoded constant for
    every model family) — a missing/invalid stamped horizon on this axis fails
    closed to ``unknown`` rather than guessing the documented fwd_60d default.
    ``max_feature_anchor_date`` (the raw feature/data frontier) is captured as
    data-pipeline-health PROVENANCE only and is NEVER tiered — keying freshness on
    it would let fresh unlabeled rows the model never trained on make a frozen
    panel read fresh (round-3 Codex review on #423 rejected round-2's choice).
    The shadow promote gate (RFC #212 §3.2) is NOT applied here — it keys on a
    persisted, pin-bound RECEIPT and is layered on by ``apply_promotion_gate`` in the
    caller, so this reader stays a pure age function.
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
    # PROVENANCE only (#423 round-3): captured + echoed, NEVER used for tiering.
    result.max_feature_anchor_date = (
        raw[:10] if (raw := _text_or_none(data.get(_FEATURE_ANCHOR_FIELD))) else None
    )
    # #223 amendment A1 / #225 round 2: this artifact's OWN declared label
    # horizon, strictly validated (exact JSON int, in-range — see
    # ``_validate_lookahead_days``). Read here so it is available for BOTH the
    # widening computation below and observability (``as_dict``) regardless of
    # tier outcome.
    result.lookahead_days_stamped = _validate_lookahead_days(data.get(_LOOKAHEAD_DAYS_FIELD))
    if result.lookahead_days_stamped is not None:
        result.horizon_validated_against = (
            f"explicit_range[{_MIN_PLAUSIBLE_LOOKAHEAD_BDAYS},"
            f"{_MAX_PLAUSIBLE_LOOKAHEAD_BDAYS}]bdays"
        )

    for field_name in DATA_CUTOFF_FIELDS:
        if _parse_date(data.get(field_name)) is not None:
            result.binding_cutoff = str(data[field_name]).strip()[:10]
            result.binding_field = field_name
            break

    # A missing / unparseable binding DATA cutoff is UNKNOWN, not "stale" — it FAILS
    # CLOSED (breach-severity) but is reported separately so operators see "cutoff
    # unknown" vs "cutoff old". trained_date is NEVER used to certify freshness (§2);
    # it is only echoed as informational context (recreating the #210 incident — a
    # retrain-today-on-stale-data reads age 0 / healthy — is exactly what we prevent).
    cutoff = _parse_date(result.binding_cutoff)
    if cutoff is None:
        result.tier = TIER_UNKNOWN
        context = (
            f"; trained_date={result.trained_date} is informational only, not a freshness axis"
            if result.trained_date
            else ""
        )
        result.detail = f"binding data cutoff unknown (fail-closed){context}"
        return result

    age_days = (now.date() - cutoff).days
    result.age_days = age_days

    # A cutoff later than the effective ``now`` is a look-ahead: reject it (fail
    # closed) rather than let a negative age be accepted as healthy by ``tier_for_age``.
    # Checked against ``now`` directly (never the lag-widened threshold below): a
    # labeled row genuinely cannot postdate "now", regardless of any axis lag.
    if age_days < 0:
        result.tier = TIER_BREACH
        result.detail = (
            f"future cutoff {result.binding_field}={result.binding_cutoff} "
            f"> now={now.date().isoformat()} (look-ahead, fail-closed)"
        )
        return result

    # ``label_observation_cutoff`` carries an EXPECTED fwd-label-horizon lag (#423
    # round-3): WIDEN the tiering thresholds by that lag so a genuinely fresh
    # retrain reads HEALTHY instead of born-BREACH. ``age_days`` stays the literal,
    # unadjusted calendar-day age (consistent meaning across every axis); only the
    # ceilings it is compared against shift for a lagged axis. #223 amendment A1:
    # the lag WIDTH comes from THIS artifact's own stamped ``lookahead_days`` — a
    # missing/invalid value on an axis that needs compensation fails closed to
    # ``unknown`` rather than guessing the documented default (never certifies a
    # tier under an assumed horizon).
    lag_days, diagnostic_lag_days = _expected_lag_calendar_days(
        result.binding_field, data.get(_LOOKAHEAD_DAYS_FIELD), now
    )
    if lag_days is None:
        result.tier = TIER_UNKNOWN
        result.detail = (
            f"{result.binding_field}={result.binding_cutoff} age={age_days}d requires "
            f"a stamped positive {_LOOKAHEAD_DAYS_FIELD!r} for horizon compensation "
            f"but none was present/valid ({data.get(_LOOKAHEAD_DAYS_FIELD)!r}); not "
            f"guessed at the documented {_LABEL_OBSERVATION_LOOKAHEAD_BDAYS}-BD "
            f"default (diagnostic-only widened threshold would be "
            f"+{diagnostic_lag_days}d) (fail-closed, #223 amendment A1)"
        )
        return result
    result.tier = tier_for_age(
        age_days,
        warn_days=policy.warn_days + lag_days,
        escalate_days=policy.escalate_days + lag_days,
        breach_days=policy.breach_days + lag_days,
    )
    result.detail = f"{result.binding_field}={result.binding_cutoff} age={age_days}d"
    if lag_days:
        result.detail += (
            f" (thresholds +{lag_days}d for this artifact's own "
            f"{result.lookahead_days_stamped}-BD stamped label horizon)"
        )
    if result.max_feature_anchor_date:
        result.detail += (
            f"; max_feature_anchor_date={result.max_feature_anchor_date}"
            " is data-pipeline-health provenance, not a freshness axis"
        )
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
    policy: FreshnessPolicy = PROD_FAST_POLICY,
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
            policy=policy,
        )
        result.per_ticker.append(freshness)
        tiers.append(freshness.tier)
        # A usable age is present, parseable, AND non-negative. Missing files,
        # cutoff-unknown, and future/look-ahead cutoffs all fail closed via ``tiers``
        # and are excluded from the age spread so they cannot skew min/median/max.
        if freshness.present and freshness.age_days is not None and freshness.age_days >= 0:
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


def _blob_from_freshness_path(freshness_path: Path | None) -> Path | None:
    """Invert ``_freshness_path_for``: recover the served model blob (the ``.pt`` pin)
    from its ``<blob>.metadata.json`` sidecar, so the promote gate can BIND and DIGEST
    the served bytes. Returns ``None`` when the freshness path is not a model-blob
    sidecar (a plain ``.json`` scoring artifact has no ``.pt`` pin to bind — the gate
    then fails closed to ``unbound`` rather than certifying on age alone)."""
    if freshness_path is None:
        return None
    suffix = ".metadata.json"
    name = freshness_path.name
    if not name.endswith(suffix):
        return None
    blob = freshness_path.with_name(name[: -len(suffix)])
    if blob.suffix.lower() not in _MODEL_BLOB_SUFFIXES:
        return None
    return blob


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


# --------------------------------------------------------------------------- #
# Shadow promotion receipt (umbrella #419 / RFC #212 §5): a persisted, pin-bound
# certification of the served shadow pin. The monitor never trusts a free, spoofable
# sidecar boolean — it reads the LATEST receipt and verifies it BINDS the served pin,
# the source cutoffs, the gate build, the candidate bytes, and the validation result.
# --------------------------------------------------------------------------- #
# Promote-gate outcomes, mapped to a tier effect by ``apply_promotion_gate``.
PROMOTE_OK = "validated"                 # bound + validated + fresh -> allow age tier
PROMOTE_MISSING = "missing"              # no receipt dir / no receipts -> fail closed (escalate)
PROMOTE_UNREADABLE = "unreadable"        # latest receipt corrupt / not an object -> escalate
PROMOTE_UNBOUND = "unbound"              # latest receipt does not bind served pin (superseded/stale) -> escalate
PROMOTE_INCOMPLETE = "incomplete"        # receipt missing a required binding field -> escalate
PROMOTE_NON_FRESH = "non_fresh"          # receipt labels the served pin non-fresh -> breach
PROMOTE_VALIDATION_FAILED = "validation_failed"  # rc!=0 / a gate failed / not fresh -> breach
PROMOTE_DIGEST_MISMATCH = "digest_mismatch"      # served .pt bytes != receipt candidate_sha256 -> breach

# Escalate-severity (can't certify) vs breach-severity (actively bad) fail-closed sets.
_PROMOTE_ESCALATE = frozenset(
    {PROMOTE_MISSING, PROMOTE_UNREADABLE, PROMOTE_UNBOUND, PROMOTE_INCOMPLETE}
)
_PROMOTE_BREACH = frozenset(
    {PROMOTE_NON_FRESH, PROMOTE_VALIDATION_FAILED, PROMOTE_DIGEST_MISMATCH}
)


def _sha256_file(path: Path, *, chunk: int = 1 << 20) -> str | None:
    """Streamed sha256 of a file (bounded memory); ``None`` if unreadable."""
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while block := handle.read(chunk):
                digest.update(block)
        return digest.hexdigest()
    except OSError:
        return None


@dataclass(frozen=True)
class PromotionReceipt:
    """One persisted shadow-promote receipt (umbrella #419 ``PromoteReport`` schema).

    Written by ``scripts/promote_shadow_patchtst.py`` on every validated served-pin
    promote. The monitor validates that it BINDS the decision so a stale/spoofed
    boolean can never certify: ``promoted_pin`` (which pin), ``source_cutoffs`` (which
    sources), ``gate_version`` (which gate build), ``candidate_sha256`` (which bytes)
    and the validation result (``rc``/``fresh``/``gates_ok``/``labeled_non_fresh``).
    """

    path: str
    promoted_pin: str | None = None
    candidate_pt: str | None = None
    candidate_sha256: str | None = None
    gate_version: str | None = None
    rc: int | None = None
    fresh: bool = False
    labeled_non_fresh: bool = False
    gates_ok: bool = False
    n_gates: int = 0
    source_cutoffs: tuple[str, ...] = ()
    promoted_at: str | None = None

    @classmethod
    def from_dict(cls, path: Path, data: dict) -> "PromotionReceipt":
        gates = data.get("gates")
        gates = gates if isinstance(gates, list) else []
        verdicts = data.get("source_verdicts")
        verdicts = verdicts if isinstance(verdicts, list) else []
        cutoffs = tuple(
            str(v["data_cutoff"])
            for v in verdicts
            if isinstance(v, dict) and v.get("data_cutoff")
        )
        rc = data.get("rc")
        return cls(
            path=str(path),
            promoted_pin=_text_or_none(data.get("promoted_pin")),
            candidate_pt=_text_or_none(data.get("candidate_pt")),
            candidate_sha256=_text_or_none(data.get("candidate_sha256")),
            gate_version=_text_or_none(data.get("gate_version")),
            rc=rc if isinstance(rc, int) else None,
            fresh=_optional_bool(data.get("fresh")) is True,
            labeled_non_fresh=_optional_bool(data.get("labeled_non_fresh")) is True,
            gates_ok=bool(gates) and all(_optional_bool(g.get("ok")) is True for g in gates),
            n_gates=len(gates),
            source_cutoffs=cutoffs,
            promoted_at=_text_or_none(data.get("promoted_at")),
        )


def read_latest_promotion_receipt(receipt_dir: Path) -> tuple[PromotionReceipt | None, str]:
    """Return ``(receipt, status)`` for the newest receipt in ``receipt_dir``.

    Receipts are named on a UTC ISO timestamp, so lexicographic max == newest. A
    missing dir / empty dir -> ``(None, PROMOTE_MISSING)``; a corrupt or non-object
    newest file -> ``(None, PROMOTE_UNREADABLE)`` (fail closed, never skipped-over).
    """
    if not receipt_dir.is_dir():
        return None, PROMOTE_MISSING
    receipts = sorted(p for p in receipt_dir.glob("*.json") if p.is_file())
    if not receipts:
        return None, PROMOTE_MISSING
    latest = receipts[-1]
    try:
        data = json.loads(latest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, PROMOTE_UNREADABLE
    if not isinstance(data, dict):
        return None, PROMOTE_UNREADABLE
    return PromotionReceipt.from_dict(latest, data), PROMOTE_OK


def _resolve_pin_blob(pin: str, config_path: Path, repo_root: Path) -> Path | None:
    """Resolve a (possibly relative) pin to its ``.pt`` blob path the way the runtime
    does (umbrella ``resolve_pin_path``): config dir first, then repo-root fallbacks."""
    p = Path(pin)
    if p.is_absolute():
        return p.resolve()
    bases = [
        config_path.parent,
        repo_root / "backtesting" / "renquant_104",
        repo_root,
    ]
    candidates = [(base / p).resolve() for base in bases]
    for cand in candidates:
        if cand.exists() or Path(str(cand) + ".metadata.json").exists():
            return cand
    return candidates[0]


def evaluate_promotion(
    *,
    receipt_dir: Path,
    served_pt: Path | None,
    config_path: Path,
    repo_root: Path,
    require_digest: bool = True,
) -> tuple[str, str, PromotionReceipt | None]:
    """Judge the served shadow pin against its latest promotion receipt.

    Returns ``(status, detail, receipt)``. A receipt certifies (``PROMOTE_OK``) only
    when it BINDS the served pin (``promoted_pin`` resolves to ``served_pt``), carries
    every required binding field (source cutoffs, gate version, candidate digest,
    validation result), passes validation (``rc==0`` & ``fresh`` & all gates ok & not
    labeled non-fresh), and the served ``.pt`` bytes hash to ``candidate_sha256``.
    Everything else fails closed (escalate for "cannot certify", breach for "bad").
    """
    receipt, read_status = read_latest_promotion_receipt(receipt_dir)
    if receipt is None:
        detail = {
            PROMOTE_MISSING: f"no promotion receipt under {receipt_dir}",
            PROMOTE_UNREADABLE: f"newest promotion receipt in {receipt_dir} is unreadable",
        }.get(read_status, read_status)
        return read_status, detail, None

    # BIND to the served pin: a receipt for a superseded/replaced pin is stale and must
    # not certify (each promote writes a distinct timestamped snapshot path).
    if not receipt.promoted_pin:
        return PROMOTE_UNBOUND, "receipt has no promoted_pin", receipt
    if served_pt is None:
        return PROMOTE_UNBOUND, "served pin unresolved; cannot bind receipt", receipt
    promoted_blob = _resolve_pin_blob(receipt.promoted_pin, config_path, repo_root)
    if promoted_blob is None or promoted_blob.resolve() != served_pt.resolve():
        return (
            PROMOTE_UNBOUND,
            f"receipt promoted_pin={receipt.promoted_pin} does not bind served pin "
            f"{served_pt} (superseded/stale)",
            receipt,
        )

    # Verify the receipt actually BINDS every certification input (a partial receipt is
    # not trusted — this is the producer contract the monitor enforces, #419 follow-up).
    missing: list[str] = []
    if not receipt.source_cutoffs:
        missing.append("source_cutoffs")
    if receipt.gate_version is None:
        missing.append("gate_version")
    if require_digest and receipt.candidate_sha256 is None:
        missing.append("candidate_sha256")
    if receipt.rc is None or receipt.n_gates == 0:
        missing.append("validation_result")
    if missing:
        return (
            PROMOTE_INCOMPLETE,
            f"receipt missing required binding(s): {','.join(missing)}",
            receipt,
        )

    # Validation RESULT (a free bool is spoofable — we require the full gate evidence).
    if receipt.labeled_non_fresh:
        return PROMOTE_NON_FRESH, "receipt labels served pin non-fresh", receipt
    if receipt.rc != 0 or not receipt.fresh or not receipt.gates_ok:
        return (
            PROMOTE_VALIDATION_FAILED,
            f"receipt validation failed (rc={receipt.rc} fresh={receipt.fresh} "
            f"gates_ok={receipt.gates_ok})",
            receipt,
        )

    # Candidate DIGEST binding: the served .pt bytes must match the promoted candidate
    # (robust to an out-of-band artifact replacement at the same path).
    if require_digest and receipt.candidate_sha256 is not None:
        digest = _sha256_file(served_pt)
        if digest is None:
            return (
                PROMOTE_DIGEST_MISMATCH,
                f"served pin {served_pt} unreadable; cannot verify candidate_sha256",
                receipt,
            )
        if digest != receipt.candidate_sha256:
            return (
                PROMOTE_DIGEST_MISMATCH,
                "served .pt sha256 != receipt candidate_sha256 (artifact replaced out of band)",
                receipt,
            )
    return PROMOTE_OK, "validated promote (receipt bound to served pin + digest)", receipt


def apply_promotion_gate(
    freshness: ArtifactFreshness,
    *,
    receipt_dir: Path,
    served_pt: Path | None,
    config_path: Path,
    repo_root: Path,
    require_digest: bool = True,
) -> ArtifactFreshness:
    """Layer the RFC #212 §3.2 promote gate onto a shadow artifact's age tier.

    The gate only ever RAISES severity: a validated, pin-bound receipt lets the age
    tier stand (so a fresh shadow can read ``healthy``); anything else fails closed.
    """
    status, detail, receipt = evaluate_promotion(
        receipt_dir=receipt_dir,
        served_pt=served_pt,
        config_path=config_path,
        repo_root=repo_root,
        require_digest=require_digest,
    )
    freshness.promotion_status = status
    if receipt is not None:
        freshness.promotion_receipt_path = receipt.path
        freshness.non_fresh = receipt.labeled_non_fresh
    freshness.promote_validated = status == PROMOTE_OK

    if status == PROMOTE_OK:
        freshness.detail += f"; {detail}"
    elif status in _PROMOTE_BREACH:
        freshness.tier = TIER_BREACH
        freshness.detail += f"; {detail} (fail-closed breach)"
    else:  # _PROMOTE_ESCALATE — cannot certify; never let age alone read healthy.
        freshness.tier = worst_tier([freshness.tier, TIER_ESCALATE])
        freshness.detail += f"; {detail} (fail-closed escalate)"
    return freshness


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
    promote_receipt_dir: Path | None = None
    explicit_watchlist: list[str] | None = None
    fast_policy: FreshnessPolicy = PROD_FAST_POLICY
    shadow_policy: FreshnessPolicy = SHADOW_POLICY
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
        # Per-population policy (NOT one global scalar): tournament + prod panel key on
        # the prod fast axis; the shadow panel keys on RFC #212's 35d + promote status.
        ctx.tournament = read_tournament_freshness(
            ctx.models_dir, ctx.watchlist, ctx.now, policy=ctx.fast_policy
        )
        ctx.prod_panel = read_artifact_freshness(
            "prod-panel", ctx.prod_panel_path, ctx.now, policy=ctx.fast_policy
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
            "shadow-panel", ctx.shadow_artifact_path, ctx.now, policy=ctx.shadow_policy
        )
        # RFC #212 §3.2 / umbrella #419: layer the persisted, pin-bound promote RECEIPT
        # gate onto the shadow age tier. Fail-closed — a shadow with no validated receipt
        # can never read healthy on age alone (reader-side of the #419 producer contract).
        if ctx.shadow_policy.require_validated_promote:
            apply_promotion_gate(
                ctx.shadow_panel,
                receipt_dir=(
                    ctx.promote_receipt_dir or default_promote_receipt_dir(ctx.repo_root)
                ),
                served_pt=_blob_from_freshness_path(ctx.shadow_artifact_path),
                config_path=ctx.shadow_config_path,
                repo_root=ctx.repo_root,
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
        # UNKNOWN outranks BREACH for the headline tier but both map to exit code 3.
        ctx.exit_code = _TIER_EXIT_CODE[ctx.worst_tier]
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
    parser.add_argument(
        "--promote-receipt-dir",
        type=Path,
        default=None,
        help=(
            "Dir of persisted shadow promotion receipts (umbrella #419); defaults to "
            "<repo-root>/logs/promote_shadow_patchtst."
        ),
    )
    parser.add_argument("--watchlist", default=None, help="Comma-separated tickers; overrides config/scan resolution.")
    # Prod fast-axis tiers (per-ticker tournament + prod XGB panel), governance §4.
    parser.add_argument("--warn-days", type=int, default=DEFAULT_WARN_DAYS)
    parser.add_argument("--escalate-days", type=int, default=DEFAULT_ESCALATE_DAYS)
    parser.add_argument("--breach-days", type=int, default=DEFAULT_BREACH_DAYS)
    # Shadow PatchTST tiers (RFC #212 §3.2) — explicit per-population config, NOT the
    # prod 28d scalar applied uniformly. Looser breach ceiling (35d, non-trading).
    parser.add_argument("--shadow-warn-days", type=int, default=SHADOW_WARN_DAYS)
    parser.add_argument("--shadow-escalate-days", type=int, default=SHADOW_ESCALATE_DAYS)
    parser.add_argument("--shadow-breach-days", type=int, default=SHADOW_BREACH_DAYS)
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
            "fast_axis": ctx.fast_policy.as_dict(),
            "shadow": ctx.shadow_policy.as_dict(),
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
    promote_receipt_dir = (
        args.promote_receipt_dir or default_promote_receipt_dir(repo_root)
    ).expanduser().resolve()
    explicit = (
        [t for t in str(args.watchlist).split(",") if t.strip()] if args.watchlist else None
    )
    fast_policy = FreshnessPolicy(
        name="prod-fast-axis",
        warn_days=args.warn_days,
        escalate_days=args.escalate_days,
        breach_days=args.breach_days,
    )
    shadow_policy = FreshnessPolicy(
        name="shadow-patchtst",
        warn_days=args.shadow_warn_days,
        escalate_days=args.shadow_escalate_days,
        breach_days=args.shadow_breach_days,
        require_validated_promote=True,
    )
    return ModelFreshnessContext(
        now=resolve_now(parse_as_of(args.as_of)),
        repo_root=repo_root,
        github_root=github_root,
        models_dir=models_dir,
        prod_panel_path=prod_panel,
        shadow_config_path=shadow_config,
        strategy_config_path=strategy_config,
        promote_receipt_dir=promote_receipt_dir,
        explicit_watchlist=explicit,
        fast_policy=fast_policy,
        shadow_policy=shadow_policy,
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
