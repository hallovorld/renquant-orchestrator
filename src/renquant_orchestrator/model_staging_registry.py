"""Rolling registry of recent *staging* model artifacts (#210, design
``doc/design/2026-06-30-model-freshness-governance.md``).

This is the **read-only** half of the Phase-4 *shadow-first* fallback (design §5.6 +
rollout Phase 4): it scans a staging directory for ``*.staging.json`` metadata
sidecars and turns them into a structured, queryable registry of recent retrain
candidates — each carrying its **data cutoff**, its **gate verdict + failure
CLASS** (infra vs substance, §4.3.1), a **point-in-time availability timestamp**
(§5.0-i-a), and a **computable quality metric** (the pre-registered selection
score, §4.3.4).

Strictly observe-only. This module **scans and reads**; it never writes a pin, a
config, a model artifact, or the staging files themselves. The only thing that
ever consumes it is :mod:`renquant_orchestrator.fallback_shadow_logger`, which
also promotes nothing.

Staging sidecar schema (``<artifact>.staging.json``)::

    {
      "artifact_id": "hf_patchtst_20260625_c0620",
      "model_family": "panel",                       # "panel" | "tournament" | ...
      "artifact_path": "artifacts/patchtst_staging/.../model.pt",
      "artifact_created_at": "2026-06-25T14:03:00Z", # immutable availability instant
      "registry_available_at": "2026-06-25T14:05:00Z",  # optional; overrides created_at
      "data_cutoff": "2026-06-20",                   # fast-axis data cutoff (§2)
      "trained_date": "2026-06-25",                  # retrain run date
      "recipe_fingerprint": "cfdd6cb8",              # optional; prod-contract comparability (§4.3.1)
      "gate": {
        "verdict": "fail",                           # pass | fail | error | unknown
        "failure_class": "timeout",                  # raw token (classified below)
        "observed_at": "2026-06-25T15:00:00Z",       # immutable verdict instant
        "reason": "ParallelTimeoutError after 600s"
      },
      "quality": {                                   # computable metrics
        "oos_sharpe": 0.42, "spy_sharpe": 0.30,
        "genuine_ic": 0.03, "placebo_ic": 0.01, "net_return": 0.012
      },
      "integrity": {                                 # basic-integrity floor (§4.3.2)
        "loads": true, "smoke_scored_no_nan": true,
        "not_degenerate": true, "recipe_loads": true
      }
    }

Missing / malformed files degrade to a candidate with ``parse_error`` set rather
than throwing — a rolling registry must survive a half-written sidecar.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping

# ── Failure taxonomy (design §4.3.1) ──────────────────────────────────────
# The ONLY failure classes the best-of-recent fallback may EVER act on. This is
# a closed, enumerated allowlist (the operator's directive, narrowed by Codex to
# mechanical/infra reasons only). Anything not classified into this set — every
# substance / leakage / placebo / recipe-mismatch / unknown failure — stays
# FAIL-CLOSED.
#
# Codex r7 narrowing: a RECIPE / FINGERPRINT mismatch (of ANY flavour, mechanical
# hash bug included) means the candidate is **not comparable to the production
# contract**, so it must be INELIGIBLE — never "rescued" as infra. It is removed
# from this allowlist and classified fail-closed (see :func:`classify_failure`).
INFRA_FAILURE_CLASSES: frozenset[str] = frozenset(
    {"timeout", "config_path", "artifact_not_found"}
)

# Normalized categories a raw gate ``failure_class`` maps to.
CATEGORY_NONE = "none"                # gate passed / no failure
CATEGORY_INFRA = "infra"             # enumerated mechanical failure (actionable)
CATEGORY_SUBSTANTIVE = "substantive"  # sub-SPY / negative ΔSharpe / no edge
CATEGORY_LEAKAGE = "leakage"         # real leakage contamination
CATEGORY_PLACEBO = "placebo"         # real placebo contamination / placebo floor
CATEGORY_UNKNOWN = "unknown"         # unclassified failure

# Every category the fallback must fail-closed on (i.e. NOT auto-promote).
FAIL_CLOSED_CATEGORIES: frozenset[str] = frozenset(
    {CATEGORY_SUBSTANTIVE, CATEGORY_LEAKAGE, CATEGORY_PLACEBO, CATEGORY_UNKNOWN}
)

_PASS_VERDICTS = frozenset({"pass", "passed", "ok", "promote", "promotable", "green"})

# Basic-integrity floor keys (design §4.3.2): loadability is NOT edge, but it is a
# necessary gate — a candidate must clear ALL of these before it can be selected.
INTEGRITY_FLOOR_KEYS: tuple[str, ...] = (
    "loads",              # artifact loads
    "smoke_scored_no_nan",  # scores a smoke panel without NaN
    "not_degenerate",     # not all-one-sign / degenerate
    "recipe_loads",       # the recipe loads
)

# Pre-registered selection score (design §4.3.4): OOS Sharpe, decided BEFORE
# looking; genuine_ic is the documented fallback metric.
SELECTION_SCORE_KEYS: tuple[str, ...] = ("oos_sharpe", "genuine_ic")


def _normalize_token(raw: str | None) -> str:
    if not raw:
        return ""
    return "".join(
        ch if ch.isalnum() else "_" for ch in str(raw).strip().lower()
    )


def classify_failure(raw_failure_class: str | None, verdict: str | None = None) -> str:
    """Map a raw gate ``failure_class`` (free-form) to a normalized category.

    Conservative by construction (design §7 narrowing + the task's mandate):
    fail-closed keywords (leakage / placebo / substance) are matched BEFORE the
    infra allowlist, so a "placebo floor" or a "sub-SPY" reject can never be
    mistaken for a mechanical failure. Only the four enumerated infra tokens
    (§4.3.1) return :data:`CATEGORY_INFRA`; everything unmatched is
    :data:`CATEGORY_UNKNOWN` (fail-closed).
    """
    token = _normalize_token(raw_failure_class)
    v = (verdict or "").strip().lower()
    if not token:
        # No failure recorded: a pass verdict is "none"; anything else with no
        # class is an unclassified failure → unknown (fail-closed).
        return CATEGORY_NONE if (v in _PASS_VERDICTS or v == "") else CATEGORY_UNKNOWN

    # Fail-closed keywords first (conservative).
    if "leakage" in token:
        return CATEGORY_LEAKAGE
    if "placebo" in token:
        return CATEGORY_PLACEBO
    # Recipe / fingerprint mismatch → NOT comparable to the production contract
    # (Codex r7). Any recipe or fingerprint mismatch — the mechanical hash bug
    # ("recipe_fingerprint_mismatch"), the identity violation
    # ("recipe_identity_mismatch"), or a bare "recipe_mismatch" — is a
    # comparability violation, NOT a mechanical rescue. Fail-closed as substantive
    # so it can never be selected. Matched BEFORE the infra allowlist.
    if "recipe" in token or "fingerprint" in token:
        return CATEGORY_SUBSTANTIVE
    if any(
        k in token
        for k in (
            "sub_spy", "subspy", "below_spy", "beat_spy", "spy",
            "sharpe", "no_edge", "noedge", "substant", "substance",
            "weak", "monoton", "identity", "delta",
        )
    ):
        return CATEGORY_SUBSTANTIVE

    # Enumerated infra allowlist (§4.3.1): timeout / config-path / artifact-not-found
    # ONLY. Recipe / fingerprint mismatches were already fail-closed above.
    if any(k in token for k in ("timeout", "time_out")):
        return CATEGORY_INFRA
    if "config" in token and ("path" in token or "not_found" in token or token == "config"):
        return CATEGORY_INFRA
    if "config_path" in token:
        return CATEGORY_INFRA
    if "not_found" in token or "notfound" in token:  # artifact/file not found
        return CATEGORY_INFRA

    return CATEGORY_UNKNOWN


def selection_score(quality: Mapping[str, Any] | None) -> float | None:
    """The pre-registered selection score (design §4.3.4): OOS Sharpe, then the
    documented genuine_ic fallback. Returns ``None`` when neither is a usable
    number — an unscoreable candidate cannot be selected."""
    if not quality:
        return None
    for key in SELECTION_SCORE_KEYS:
        v = quality.get(key)
        if isinstance(v, bool):
            continue
        if isinstance(v, (int, float)):
            return float(v)
    return None


def passes_integrity_floor(integrity: Mapping[str, Any] | None) -> bool:
    """True iff EVERY basic-integrity check (§4.3.2) is explicitly ``True``. A
    missing key fails the floor (conservative — integrity is necessary but not
    sufficient, and absence is not a pass)."""
    if not integrity:
        return False
    return all(integrity.get(k) is True for k in INTEGRITY_FLOOR_KEYS)


def _parse_dt(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    s = value.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        # date-only string is a valid instant at midnight
        try:
            return datetime.fromisoformat(s + "T00:00:00")
        except ValueError:
            return None


def _parse_date(value: Any) -> date | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
        return None


def _as_of_date(as_of: date | datetime) -> date:
    return as_of.date() if isinstance(as_of, datetime) else as_of


@dataclass(frozen=True)
class StagingCandidate:
    """One parsed ``*.staging.json`` sidecar."""

    artifact_id: str
    model_family: str
    source_path: str
    artifact_path: str | None
    artifact_created_at: datetime | None
    registry_available_at: datetime | None
    data_cutoff: date | None
    trained_date: date | None
    gate_verdict: str
    raw_failure_class: str | None
    failure_category: str
    gate_observed_at: datetime | None
    recipe_fingerprint: str | None = None
    quality: dict = field(default_factory=dict)
    integrity: dict = field(default_factory=dict)
    parse_error: str | None = None

    # ── availability / recency (design §5.0-i-a, §4.3.4) ──────────────────
    @property
    def available_at(self) -> datetime | None:
        """Point-in-time availability instant: the registry-available timestamp
        if present, else the artifact-created timestamp. Never inferred from a
        filesystem mtime (§5.0 fails those closed)."""
        return self.registry_available_at or self.artifact_created_at

    def recency_date(self) -> date | None:
        """The date the best-of-recent window is measured against: ``trained_date``
        (the retrain run), falling back to ``data_cutoff``."""
        return self.trained_date or self.data_cutoff

    def age_days(self, as_of: date | datetime) -> int | None:
        rd = self.recency_date()
        return None if rd is None else (_as_of_date(as_of) - rd).days

    def is_available_at(self, as_of: date | datetime) -> bool:
        """§5.0-i-a: eligible only if an availability timestamp EXISTS and is
        ``<= as_of``. A missing timestamp fails closed (never backfilled)."""
        av = self.available_at
        return av is not None and av.date() <= _as_of_date(as_of)

    # ── quality helpers ───────────────────────────────────────────────────
    @property
    def selection_score(self) -> float | None:
        return selection_score(self.quality)

    @property
    def passes_integrity_floor(self) -> bool:
        return passes_integrity_floor(self.integrity)

    # ── construction ──────────────────────────────────────────────────────
    @classmethod
    def from_dict(cls, payload: Mapping[str, Any], source_path: str) -> "StagingCandidate":
        gate = payload.get("gate") or {}
        if not isinstance(gate, Mapping):
            gate = {}
        verdict = str(gate.get("verdict") or "unknown")
        raw_fc = gate.get("failure_class")
        raw_fc = str(raw_fc) if raw_fc not in (None, "") else None
        return cls(
            artifact_id=str(payload.get("artifact_id") or Path(source_path).name),
            model_family=str(payload.get("model_family") or "unknown"),
            source_path=source_path,
            artifact_path=(str(payload["artifact_path"]) if payload.get("artifact_path") else None),
            artifact_created_at=_parse_dt(payload.get("artifact_created_at")),
            registry_available_at=_parse_dt(payload.get("registry_available_at")),
            data_cutoff=_parse_date(payload.get("data_cutoff")),
            trained_date=_parse_date(payload.get("trained_date")),
            gate_verdict=verdict,
            raw_failure_class=raw_fc,
            failure_category=classify_failure(raw_fc, verdict),
            gate_observed_at=_parse_dt(gate.get("observed_at")),
            recipe_fingerprint=(
                str(payload["recipe_fingerprint"]) if payload.get("recipe_fingerprint") else None
            ),
            quality=dict(payload.get("quality") or {}),
            integrity=dict(payload.get("integrity") or {}),
        )

    @classmethod
    def from_file(cls, path: Path) -> "StagingCandidate":
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            return cls._broken(path, f"read error: {exc!s}"[:200])
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            return cls._broken(path, f"invalid JSON: {exc!s}"[:200])
        if not isinstance(payload, Mapping):
            return cls._broken(path, "sidecar is not a JSON object")
        return cls.from_dict(payload, str(path))

    @classmethod
    def _broken(cls, path: Path, error: str) -> "StagingCandidate":
        return cls(
            artifact_id=path.name,
            model_family="unknown",
            source_path=str(path),
            artifact_path=None,
            artifact_created_at=None,
            registry_available_at=None,
            data_cutoff=None,
            trained_date=None,
            gate_verdict="unknown",
            raw_failure_class=None,
            failure_category=CATEGORY_UNKNOWN,
            gate_observed_at=None,
            parse_error=error,
        )


class ModelStagingRegistry:
    """A rolling, read-only view of the staging model artifacts.

    Build it with :meth:`scan` (a filesystem scan) or the constructor (for tests /
    an in-memory list), then query :meth:`within_last_days`.
    """

    def __init__(self, candidates: list[StagingCandidate]) -> None:
        self._candidates: list[StagingCandidate] = list(candidates)

    @classmethod
    def scan(
        cls,
        staging_dir: str | Path,
        *,
        family: str | None = None,
        pattern: str = "*.staging.json",
    ) -> "ModelStagingRegistry":
        """Read-only recursive scan of ``staging_dir`` for ``*.staging.json``
        sidecars. A missing directory yields an empty registry (not an error);
        each sidecar is parsed defensively (malformed → ``parse_error``)."""
        base = Path(staging_dir)
        candidates: list[StagingCandidate] = []
        if base.exists():
            for path in sorted(base.rglob(pattern)):
                if path.is_file():
                    candidates.append(StagingCandidate.from_file(path))
        if family is not None:
            candidates = [c for c in candidates if c.model_family == family]
        return cls(candidates)

    @property
    def candidates(self) -> list[StagingCandidate]:
        return list(self._candidates)

    def valid(self) -> list[StagingCandidate]:
        """Candidates that parsed cleanly (no ``parse_error``)."""
        return [c for c in self._candidates if c.parse_error is None]

    def within_last_days(
        self,
        n_days: int,
        *,
        as_of: date | datetime,
        family: str | None = None,
        require_available: bool = True,
    ) -> list[StagingCandidate]:
        """Candidates **trained within the last ``n_days``** as of ``as_of``,
        newest first.

        A candidate is included iff:
          * it parsed cleanly and has a usable recency date (``trained_date`` →
            ``data_cutoff``);
          * ``0 <= (as_of - recency_date) <= n_days`` — future-dated artifacts
            (negative age) are excluded;
          * (``require_available``, default True) it satisfies the §5.0-i-a
            point-in-time availability predicate — an availability timestamp
            exists and is ``<= as_of``. A missing timestamp fails closed.

        Sorted newest-recency-date first, then by ``artifact_id`` for a stable,
        deterministic order.
        """
        as_of_d = _as_of_date(as_of)
        out: list[StagingCandidate] = []
        for c in self._candidates:
            if c.parse_error is not None:
                continue
            if family is not None and c.model_family != family:
                continue
            rd = c.recency_date()
            if rd is None:
                continue
            age = (as_of_d - rd).days
            if age < 0 or age > n_days:
                continue
            if require_available and not c.is_available_at(as_of_d):
                continue
            out.append(c)
        out.sort(key=lambda c: c.artifact_id)
        out.sort(key=lambda c: c.recency_date() or date.min, reverse=True)
        return out
