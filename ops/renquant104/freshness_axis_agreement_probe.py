#!/usr/bin/env python3
"""Do the freshness MONITOR and the buy-admission LICENSE agree on the axis?

WHY (GOAL-5, measured 2026-08-05). Two in-repo implementations both cite RFC #210
and reach opposite conclusions about the same served artifact:

  monitor  (src/renquant_orchestrator/model_freshness_monitor.py)
      "[unknown] prod-panel: binding data cutoff unknown (fail-closed);
       trained_date=2026-08-02 is informational only, not a freshness axis"
      -> exit 3. Its DATA_CUTOFF_FIELDS deliberately EXCLUDES trained_date:
      a fresh run time over stale data is not fresh, so a missing binding
      cutoff fails closed to `unknown` rather than falling back.

  license  (renquant-pipeline kernel/rfc210_license.py, PINNED and live)
      ages `trained_date` and nothing else, and on that basis alone returns
      served=True for a WF-gate-FAILED artifact -> the daily run prints
      "P-WF-GATE [HARD] ... trained 2026-08-02, 3d old <= 28d serving SLA
       — buys admitted while the freshness license holds."

The served artifact `artifacts/prod/panel-ltr.alpha158_fund.json` carries
**none** of the six binding axes and only `trained_date` + `promotion_basis`.

THE CLAIM THIS PROBE MAKES, AND THE ONE IT REFUSES TO MAKE:

  makes   -- the freshness of the artifact deciding live buys is UNKNOWABLE
             from the artifact, while a gate certifies it as fresh.
  refuses -- any statement that the model IS stale. Nobody can say that, which
             is the entire finding. The data cutoff is absent, so the error's
             direction is unknown and the model may well be perfectly fresh.

A probe that concluded "the model is stale" here would be inventing the number
it was built to report as missing.

Read-only. Usage:
    python ops/renquant104/freshness_axis_agreement_probe.py [--artifact P] [--json]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys

RQ_ROOT = pathlib.Path("/Users/renhao/git/github/RenQuant")
DEFAULT_ARTIFACT = (RQ_ROOT / "backtesting" / "renquant_104" / "artifacts"
                    / "prod" / "panel-ltr.alpha158_fund.json")

#: The monitor's binding data-cutoff axes, most-binding first. Mirrored rather
#: than imported so this probe still reports when the monitor cannot be loaded —
#: and pinned by a test that asserts the two lists are equal, because a mirror
#: that drifts is worse than no mirror.
DATA_CUTOFF_FIELDS = [
    "label_observation_cutoff",
    "effective_selection_cutoff_date",
    "effective_train_cutoff_date",
    "data_cutoff_date",
    "live_train_end",
    "cutoff_date",
]

#: What the RFC #210 license ages instead.
LICENSE_AGE_FIELD = "trained_date"
LICENSE_BASIS_FIELD = "promotion_basis"
LICENSE_BASIS_VALUE = "freshness_fallback_rfc210"

AGREE = "AGREE"
CONTRADICTION = "CONTRADICTION"
NOT_LICENSED = "NOT_UNDER_LICENSE"
#: The licence names this artifact as its own, but its age field is unreadable, so
#: `rfc210_license.py:73-84` REFUSES rather than serving. There is no admission to
#: contradict, and calling this AGREE would hide the very refusal the probe exists
#: to surface (codex on orch#860). Its own state, never folded into either side.
LICENSE_WOULD_REFUSE = "LICENSE_WOULD_REFUSE"


class ArtifactUnreadable(RuntimeError):
    """The artifact could not be read. Not an agreement."""


def _get(payload: dict, field: str):
    """Top-level first, then metadata — the same order the license uses."""
    if field in payload:
        return payload[field]
    md = payload.get("metadata")
    if isinstance(md, dict) and field in md:
        return md[field]
    return None


def _trained_date_is_readable(raw) -> bool:
    """Exactly `rfc210_license.py`'s own test: a non-empty string that parses ISO.

    Kept as a named helper rather than inlined so the mirrored contract is
    greppable from the licence side, and so a test can pin it directly."""
    if not isinstance(raw, str) or not raw.strip():
        return False
    try:
        dt.date.fromisoformat(raw.strip())
    except ValueError:
        return False
    return True


def probe(artifact: pathlib.Path = DEFAULT_ARTIFACT) -> dict:
    try:
        payload = json.loads(artifact.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ArtifactUnreadable(f"{artifact}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ArtifactUnreadable(
            f"{artifact}: payload is not an object — cannot read either axis, "
            "and reporting that as agreement would publish a failed read as a "
            "clean result")

    present = {f: _get(payload, f) for f in DATA_CUTOFF_FIELDS}
    binding = {f: v for f, v in present.items() if v is not None}
    trained = _get(payload, LICENSE_AGE_FIELD)
    basis = _get(payload, LICENSE_BASIS_FIELD)
    licensed = basis == LICENSE_BASIS_VALUE

    # Mirror the licence's OWN readability test before judging agreement.
    # rfc210_license.py:73-84 serves only when trained_date is a non-empty string
    # that parses as an ISO date, and refuses otherwise. A probe that skipped this
    # would report AGREE for an artifact the licence actually refuses.
    age_readable = _trained_date_is_readable(trained)

    if not licensed:
        state = NOT_LICENSED
    elif not age_readable:
        state = LICENSE_WOULD_REFUSE
    elif binding:
        state = AGREE
    else:
        state = CONTRADICTION

    return {
        "artifact": str(artifact),
        "state": state,
        # The monitor's side.
        "binding_cutoff_fields_present": sorted(binding),
        "n_binding_cutoff_fields": len(binding),
        "monitor_verdict": "known" if binding else "unknown (fail-closed)",
        # The license's side.
        "promotion_basis": basis,
        "under_rfc210_license": licensed,
        "trained_date": trained,
        "trained_date_readable": age_readable,
        "license_ages_field": LICENSE_AGE_FIELD,
        # Stated so a CONTRADICTION is never read as a staleness measurement.
        "does_NOT_establish": (
            "that the model is stale. The binding data cutoff is ABSENT, so its "
            "vintage is unknown in BOTH directions — the model may be perfectly "
            "fresh. The finding is that nothing can tell you which."
        ),
    }


def render(p: dict) -> str:
    out = ["freshness axis agreement — monitor vs RFC#210 buy-admission license", ""]
    out.append(f"  artifact : {p['artifact']}")
    out.append(f"  state    : {p['state']}")
    out.append("")
    out.append(f"  monitor  : binding data cutoff -> {p['monitor_verdict']}")
    out.append(f"             fields present: {p['binding_cutoff_fields_present'] or 'NONE of 6'}")
    out.append(f"  license  : promotion_basis={p['promotion_basis']!r}")
    out.append(f"             ages {p['license_ages_field']}={p['trained_date']!r}")
    out.append("")
    if p["state"] == CONTRADICTION:
        out.append("  CONTRADICTION — the artifact deciding live buys carries NO binding")
        out.append("  data cutoff, so the monitor fails closed to `unknown`, while the")
        out.append("  RFC#210 license certifies it fresh from the run time alone and")
        out.append("  admits buys on a WF-gate-FAILED artifact.")
        out.append("")
        out.append(f"  This does NOT establish {p['does_NOT_establish']}")
    elif p["state"] == LICENSE_WOULD_REFUSE:
        out.append("  LICENSE WOULD REFUSE — promotion_basis names the RFC#210 fallback,")
        out.append(f"  but trained_date={p['trained_date']!r} is not a parseable ISO date, so")
        out.append("  the licence refuses rather than serving. Not agreement: there is no")
        out.append("  admission here to contradict.")
    elif p["state"] == AGREE:
        out.append("  both axes are readable — the license's age can be checked against")
        out.append("  a real data cutoff. NOTE: agreement on AXIS, not on VALUE.")
    else:
        out.append("  artifact is not served under the RFC#210 freshness fallback, so the")
        out.append("  license is not the admitting authority here.")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact", type=pathlib.Path, default=DEFAULT_ARTIFACT)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        p = probe(args.artifact)
    except ArtifactUnreadable as exc:
        print(f"REFUSING: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(p, indent=2) if args.json else render(p))
    return 1 if p["state"] == CONTRADICTION else 0


if __name__ == "__main__":
    sys.exit(main())
