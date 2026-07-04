"""The monthly risk-budget statement + CLI (107 sprint D3). OBSERVE-ONLY.

One statement, four budgets (DD 15% hard / β 0.6 planning / per-name
concentration per regime cap / sleeve DD sub-budget), each with:
consumption, remaining runway, and a breach status. Plus the attribution
bridge's answer to "which LEG is consuming the DD budget", and a first-class
censoring appendix (censored eras propagate explicitly per #253 — nothing is
imputed anywhere in this package).

Breach semantics (per budget, on its consumption fraction):

- ``> 0.80``  → **WARN**      (process exit code 2)
- ``>= 1.00`` → **CRITICAL**  (process exit code 1)
- otherwise   → OK            (exit code 0)

The exit code is the worst status across evaluated budgets — the same
0/1/2 convention as the rq104 scorer-identity monitor, so the ops wrapper
can ntfy on it without parsing anything. Censored budgets can never breach;
they are listed as censored instead (a silent skip is not a pass, but an
unmeasurable budget must not fake a reading either).

The writer refuses production paths (umbrella ``data/`` / ``runtime/``) —
identical guard to the attribution reporter. This module never writes
anywhere near prod and never trades: budgets are ENFORCED, where they are
enforced at all, by the pinned strategy config's existing controls.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from renquant_orchestrator.risk_budget import attribution_bridge as ab
from renquant_orchestrator.risk_budget import budget as bd

DEFAULT_OUT_DIR = Path.home() / "renquant-data/research/risk_budget"

# Paths this reporter must never write into (prod inputs, run DB home).
_FORBIDDEN_OUT_PREFIXES = (
    Path.home() / "git/github/RenQuant/data",
    Path.home() / "git/github/RenQuant/runtime",
)

WARN_THRESHOLD = 0.80
CRITICAL_THRESHOLD = 1.00

STATUS_OK = "OK"
STATUS_WARN = "WARN"
STATUS_CRITICAL = "CRITICAL"
STATUS_CENSORED = "CENSORED"

_EXIT_CODE = {STATUS_OK: 0, STATUS_CENSORED: 0, STATUS_WARN: 2, STATUS_CRITICAL: 1}
_SEVERITY = {STATUS_OK: 0, STATUS_CENSORED: 0, STATUS_WARN: 1, STATUS_CRITICAL: 2}


def breach_status(consumption: float | None) -> str:
    """>80% WARN, >=100% CRITICAL, censored (None) can never breach."""
    if consumption is None:
        return STATUS_CENSORED
    if consumption >= CRITICAL_THRESHOLD:
        return STATUS_CRITICAL
    if consumption > WARN_THRESHOLD:
        return STATUS_WARN
    return STATUS_OK


def overall_status(statuses: list[str]) -> str:
    worst = STATUS_OK
    for s in statuses:
        if _SEVERITY.get(s, 0) > _SEVERITY[worst]:
            worst = s
    return worst


def exit_code(status: str) -> int:
    return _EXIT_CODE.get(status, 0)


# ---------------------------------------------------------------------------
# Statement assembly
# ---------------------------------------------------------------------------

def build_statement(
    conn: sqlite3.Connection,
    strategy_config: str | Path | None = None,
    sleeve_log: str | Path | None = None,
    ohlcv_dir: str | Path | None = None,
    run_type: str = "live",
    burn_window: int = 21,
    beta_window: int = 63,
    beta_min_obs: int = 40,
    half_spread_bps: float = 0.0,
    allow_sim: bool = False,
    close_loader=None,
) -> dict[str, Any]:
    """Assemble the full statement dict. All inputs read-only.

    ``close_loader(ticker) -> pd.Series | None`` is injectable for tests;
    the default reads the umbrella ohlcv parquet store when present.
    """
    controls = bd.load_strategy_risk_controls(strategy_config)
    budgets = bd.build_budgets(controls)
    censoring: list[dict[str, str]] = [
        {"where": "strategy_config", "reason": r} for r in controls.get("censored", [])
    ]

    # --- drawdown -----------------------------------------------------------
    curve = bd.load_equity_curve(conn, run_type=run_type)
    drawdown = bd.running_drawdown(curve, stamped_hwm=bd.stamped_high_water_mark(conn))
    dd_limit = budgets["max_drawdown"]["limit"]
    if not drawdown.get("censored"):
        censoring.append({
            "where": "equity_curve",
            "reason": (
                f"eod_only(series is end-of-day closes starting "
                f"{drawdown['start_date']}; intraday troughs and earlier "
                "drawdowns are unknowable)"
            ),
        })
        if drawdown.get("current_drawdown_vs_stamped_hwm") is not None:
            censoring.append({
                "where": "drawdown.hwm",
                "reason": (
                    f"stamped_hwm_above_measured_peak(stamped "
                    f"{drawdown['stamped_hwm']:.2f} > measured peak "
                    f"{drawdown['peak_value']:.2f}; conservative figure drives "
                    "consumption)"
                ),
            })
    dd_cons = bd.dd_budget_consumption(drawdown, dd_limit)
    burn = bd.burn_rate(curve, limit=dd_limit, window=burn_window)
    if drawdown.get("censored"):
        censoring.append({"where": "drawdown", "reason": drawdown["censored"]})
    if burn.get("censored"):
        censoring.append({"where": "burn_rate", "reason": burn["censored"]})

    # --- positions / concentration -------------------------------------------
    positions = bd.latest_positions(conn, run_type=run_type)
    conc = bd.concentration(
        positions, budgets["per_name_concentration"]["per_regime"]
    )
    if conc.get("censored"):
        censoring.append({"where": "concentration", "reason": conc["censored"]})
    gap = positions.get("cash_identity_gap")
    if gap is not None and abs(gap) > 0.02:
        censoring.append({
            "where": "positions.cash",
            "reason": (
                f"recorded_cash_inconsistent(recorded cash weight "
                f"{positions.get('recorded_cash_weight'):.3f} + invested "
                f"{positions.get('invested_weight'):.3f} = {1 + gap:.3f} of book; "
                "cash weight derived from positions instead)"
            ),
        })

    # --- sleeve sub-budget ----------------------------------------------------
    sleeve = bd.read_sleeve_shadow(sleeve_log)
    if sleeve.get("censored"):
        censoring.append({"where": "sleeve", "reason": sleeve["censored"]})

    # --- beta -----------------------------------------------------------------
    # The DB's own beta_spy_252d column is NULL on every live row (measured
    # 2026-07-03) — recorded as censored-at-source; we compute instead.
    censoring.append({"where": "portfolio_daily_metrics.beta_spy_252d",
                      "reason": bd.CENSOR_DB_BETA_NULL})
    spy_ret = bd.spy_return_series(conn)
    if curve.empty or spy_ret.empty:
        realized = {"censored": bd.CENSOR_NO_SPY if spy_ret.empty else bd.CENSOR_NO_EQUITY,
                    "n_obs": 0}
    else:
        book_ret = curve.set_index("date")["daily_return"].dropna()
        realized = bd.realized_beta(book_ret, spy_ret)
    if realized.get("censored"):
        censoring.append({"where": "realized_beta", "reason": realized["censored"]})

    if close_loader is None:
        base = Path(ohlcv_dir) if ohlcv_dir is not None else bd.DEFAULT_OHLCV_DIR

        def close_loader(ticker: str):  # noqa: ANN001 - local default
            return bd.load_close_series(base, ticker)

    tickers = [p["ticker"] for p in positions.get("positions", []) if p.get("weight")]
    closes = {t: close_loader(t) for t in [*tickers, bd.BENCHMARK_TICKER]}
    betas = bd.per_name_betas(closes, window=beta_window, min_obs=beta_min_obs)
    composition = bd.beta_composition(positions, betas, sleeve)
    for name, reason in composition.get("censored_names", {}).items():
        censoring.append({"where": f"beta[{name}]", "reason": reason})

    # Breach driver for the beta budget: the most conservative MEASURED view
    # (realized book beta vs measured-composition beta) — censored views are
    # excluded, never guessed.
    beta_measures = [
        v for v in (
            realized.get("beta"),
            composition.get("book_beta_measured_names"),
        )
        if v is not None
    ]
    beta_driver = max(beta_measures) if beta_measures else None
    beta_limit = budgets["book_beta"]["limit"]

    # --- attribution bridge -----------------------------------------------------
    dd_window = None
    if not drawdown.get("censored"):
        dd_window = (drawdown["max_drawdown_peak_date"], drawdown["as_of"])
    try:
        legs = ab.leg_dd_consumption(
            conn,
            dd_window=dd_window,
            run_type=run_type,
            half_spread_bps=half_spread_bps,
            allow_sim=allow_sim,
        )
    except ValueError as exc:  # e.g. sim refused — surfaced, not swallowed
        legs = {"censored": str(exc)}
        censoring.append({"where": "attribution_bridge", "reason": str(exc)})

    # --- breach evaluation --------------------------------------------------------
    sleeve_consumption = sleeve.get("max_dd_budget_consumption_pct")
    if sleeve_consumption is not None:
        sleeve_consumption = float(sleeve_consumption)
    breaches = {
        "max_drawdown": {
            "limit": dd_limit,
            "consumption": dd_cons.get("max_consumption"),
            "status": breach_status(dd_cons.get("max_consumption")),
        },
        "book_beta": {
            "limit": beta_limit,
            "consumption": (beta_driver / beta_limit) if beta_driver is not None else None,
            "measured_beta": beta_driver,
            "status": breach_status(
                (beta_driver / beta_limit) if beta_driver is not None else None
            ),
        },
        "per_name_concentration": {
            "limit": conc.get("cap"),
            "consumption": conc.get("consumption"),
            "status": breach_status(conc.get("consumption")),
        },
        "sleeve_dd_sub_budget": {
            "limit": budgets["sleeve_dd_sub_budget"]["limit"],
            "consumption": sleeve_consumption,
            "status": breach_status(sleeve_consumption),
        },
    }
    status = overall_status([b["status"] for b in breaches.values()])

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+0000"),
        "as_of": drawdown.get("as_of"),
        "run_type": run_type,
        "status": status,
        "exit_code": exit_code(status),
        "provenance": {
            "strategy_config": controls.get("config_path"),
            "strategy_config_pinned": controls.get("pinned"),
            "sleeve_log": sleeve.get("path"),
            "read_only": True,
        },
        "budgets": budgets,
        "controls_context": {
            "cash_reserve_per_regime": {
                r: p.get("cash_reserve_pct")
                for r, p in (controls.get("regime_params") or {}).items()
            },
            "max_positions_per_sector": controls.get("max_positions_per_sector"),
            "vol_gate": controls.get("vol_gate"),
            "sleeve_flag": controls.get("sleeve"),
        },
        "readings": {
            "drawdown": drawdown,
            "dd_consumption": dd_cons,
            "burn": burn,
            "positions": positions,
            "concentration": conc,
            "beta_realized": realized,
            "beta_composition": composition,
            "sleeve": sleeve,
        },
        "leg_decomposition": legs,
        "breaches": breaches,
        "censoring": censoring,
    }


# ---------------------------------------------------------------------------
# Rendering + writing
# ---------------------------------------------------------------------------

def _fmt(v: Any, pct: bool = False) -> str:
    if v is None:
        return "censored"
    if isinstance(v, float):
        if v == float("inf"):
            return "inf"
        return f"{v * 100:.1f}%" if pct else f"{v:.3f}"
    return str(v)


def render_markdown(statement: dict[str, Any]) -> str:
    r = statement["readings"]
    dd, cons, burn = r["drawdown"], r["dd_consumption"], r["burn"]
    conc, sleeve = r["concentration"], r["sleeve"]
    lines = [
        "# Risk-budget statement (observe-only)",
        "",
        f"- generated: {statement['generated_at']}  ·  as-of: {statement['as_of']}"
        f"  ·  run_type: {statement['run_type']}",
        f"- **status: {statement['status']}** (exit {statement['exit_code']})",
        f"- strategy config: `{statement['provenance']['strategy_config']}`"
        f" (pinned: {statement['provenance']['strategy_config_pinned']})",
        "",
        "## Budgets vs consumption",
        "",
        "| budget | limit | consumption | status | notes |",
        "|---|---|---|---|---|",
    ]
    b = statement["breaches"]
    dd_note = (
        f"running max DD {_fmt(dd.get('max_drawdown'), pct=True)} "
        f"({dd.get('max_drawdown_peak_date')} → {dd.get('max_drawdown_date')}); "
        f"current {_fmt(dd.get('current_drawdown'), pct=True)}"
        if not dd.get("censored") else dd["censored"]
    )
    lines.append(
        f"| max_drawdown (HARD, G*) | {_fmt(b['max_drawdown']['limit'], pct=True)} "
        f"| {_fmt(b['max_drawdown']['consumption'], pct=True)} "
        f"| {b['max_drawdown']['status']} | {dd_note} |"
    )
    beta_real = r["beta_realized"]
    comp = r["beta_composition"]
    beta_note = (
        f"realized β {_fmt(beta_real.get('beta'))} (n={beta_real.get('n_obs')}, "
        f"R²={_fmt(beta_real.get('r2'))}); pt-composition "
        f"{_fmt(comp.get('book_beta_measured_names'))} over measured weight "
        f"{_fmt(comp.get('measured_weight'), pct=True)}"
    )
    lines.append(
        f"| book_beta (planning, RS-1) | {_fmt(b['book_beta']['limit'])} "
        f"| {_fmt(b['book_beta']['consumption'], pct=True)} "
        f"| {b['book_beta']['status']} | {beta_note} |"
    )
    conc_note = (
        f"top {conc.get('top_name')} {_fmt(conc.get('top_name_weight'), pct=True)} vs "
        f"{conc.get('regime')} cap {_fmt(conc.get('cap'), pct=True)}; "
        f"HHI(book) {_fmt(conc.get('hhi_book'))}, eff-N {_fmt(conc.get('effective_n_invested'))}"
        if conc.get("n_names") else str(conc.get("censored"))
    )
    lines.append(
        f"| per_name_concentration | {_fmt(b['per_name_concentration']['limit'], pct=True)} "
        f"| {_fmt(b['per_name_concentration']['consumption'], pct=True)} "
        f"| {b['per_name_concentration']['status']} | {conc_note} |"
    )
    sleeve_note = (
        f"log {sleeve.get('n_records')} records; reversal inputs: 3m contribution "
        f"{_fmt((sleeve.get('reversal_metrics') or {}).get('contribution_sum_pct'))}, "
        f"triggered={(sleeve.get('reversal_metrics') or {}).get('triggered')}"
        if sleeve.get("present") else str(sleeve.get("censored"))
    )
    lines.append(
        f"| sleeve_dd_sub_budget | {_fmt(b['sleeve_dd_sub_budget']['limit'], pct=True)} "
        f"| {_fmt(b['sleeve_dd_sub_budget']['consumption'], pct=True)} "
        f"| {b['sleeve_dd_sub_budget']['status']} | {sleeve_note} |"
    )

    if comp.get("per_name"):
        lines += ["", "### Beta composition (point-in-time, measured — never assumed)", "",
                  "| name | weight | beta (n, window) | w·β contribution |",
                  "|---|---|---|---|"]
        for name, info in sorted(
            comp["per_name"].items(),
            key=lambda kv: -(kv[1]["weight"] * kv[1].get("beta", 0.0)
                             if kv[1].get("beta") is not None else 0.0),
        ):
            if info.get("beta") is not None:
                lines.append(
                    f"| {name} | {_fmt(info['weight'], pct=True)} "
                    f"| {info['beta']:.2f} (n={info['n_obs']}) "
                    f"| {info['weight'] * info['beta']:.3f} |"
                )
            else:
                lines.append(
                    f"| {name} | {_fmt(info['weight'], pct=True)} "
                    f"| censored: {info.get('censored')} | censored |"
                )
        if comp.get("sleeve_leg"):
            sl = comp["sleeve_leg"]
            lines.append(
                f"| sleeve (SPY) | {_fmt(sl['spy_weight'], pct=True)} | 1.00 (definitional) "
                f"| {sl['beta_contribution']:.3f} |"
            )
        lines.append(
            f"| cash | {_fmt(r['positions'].get('cash_weight'), pct=True)} | 0.00 | 0.000 |"
        )

    lines += ["", "## Runway", ""]
    if burn.get("censored"):
        lines.append(f"- {burn['censored']} (window {burn.get('window')})")
    if burn.get("burn_per_session") is not None:
        lines.append(
            f"- DD-budget burn over last {burn['window']} sessions: "
            f"{_fmt(burn['burn_per_session'], pct=True)}/session of budget "
            f"(consumption {_fmt(burn['consumption_window_start'], pct=True)} → "
            f"{_fmt(burn['consumption_now'], pct=True)})"
        )
        if burn.get("runway_sessions") is not None:
            lines.append(f"- runway at current burn: {burn['runway_sessions']:.0f} sessions")

    legs = statement["leg_decomposition"]
    lines += [
        "", "## Which leg consumes the DD budget", "",
        "Leg semantics (doc/design/2026-07-03-attribution-engine.md): MARKET/SIGNAL",
        "are decision-quality dollars on INTENDED notional — they include",
        "decisions whose fills were never confirmed, so they are NOT realized",
        "book P&L. TIMING/SIZING/COST require confirmed fills; negative rows",
        "are the DD-budget consumers this section exists to name.",
        "",
    ]
    if legs.get("censored"):
        lines.append(f"- censored: {legs['censored']}")
    else:
        for view in ("overall", "dd_window"):
            agg = legs.get(view)
            if not agg:
                continue
            hdr = "full history" if view == "overall" else (
                f"current DD window {agg['start']} → {agg['end']}"
            )
            lines += [f"### {hdr}", "",
                      "| leg | total $ | n decomposed | censored (top reason) |",
                      "|---|---|---|---|"]
            for row in agg["ranking"]:
                cens = agg["leg_censored"][row["leg"]]
                top_reason = max(cens.items(), key=lambda kv: kv[1]) if cens else None
                cens_txt = f"{sum(cens.values())} ({top_reason[0]})" if top_reason else "0"
                lines.append(
                    f"| {row['leg']} | {row['total']:+.2f} | {row['n']} | {cens_txt} |"
                )
            lines.append("")

    lines += ["## Censoring appendix (nothing imputed)", ""]
    for c in statement["censoring"]:
        lines.append(f"- `{c['where']}`: {c['reason']}")
    lines += [
        "",
        "---",
        "OBSERVE-ONLY: this statement measures budgets; it never gates, sizes,",
        "or trades. Enforcement lives in the pinned strategy config's existing",
        "controls (regime caps / per-name caps / vol-gated regime detector).",
    ]
    return "\n".join(lines)


def _check_out_dir(out_dir: Path) -> Path:
    out_dir = out_dir.expanduser().resolve()
    for forbidden in _FORBIDDEN_OUT_PREFIXES:
        try:
            out_dir.relative_to(forbidden.resolve())
        except ValueError:
            continue
        raise ValueError(
            f"refusing to write risk-budget outputs under production path {forbidden}"
        )
    return out_dir


def write_statement(statement: dict[str, Any], out_dir: str | Path) -> dict[str, Path]:
    """Write markdown + JSON into the research lake (never prod paths)."""
    out = _check_out_dir(Path(out_dir))
    out.mkdir(parents=True, exist_ok=True)
    stamp = statement["generated_at"].replace(":", "").replace("+0000", "Z")
    base = f"risk_budget_{statement['run_type']}_{stamp}"
    md_path = out / f"{base}.md"
    json_path = out / f"{base}.json"
    md_path.write_text(render_markdown(statement))
    json_path.write_text(json.dumps(statement, indent=2, default=str))
    return {"markdown": md_path, "json": json_path}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="renquant-risk-budget",
        description=(
            "Observe-only risk-budget statement (read-only over the run DB; "
            "exit 0 OK / 2 WARN >80% / 1 CRITICAL >=100%)."
        ),
    )
    p.add_argument("--db", default=str(bd.DEFAULT_DB), help="run DB path (opened read-only)")
    p.add_argument("--strategy-config", default=None,
                   help="strategy config path (default: pinned runtime copy, then sibling)")
    p.add_argument("--sleeve-log", default=None,
                   help="parking-sleeve shadow JSONL (default: umbrella 104 run dir)")
    p.add_argument("--ohlcv-dir", default=None,
                   help="daily ohlcv store for per-name beta (default: umbrella data/ohlcv)")
    p.add_argument("--run-type", default="live", choices=["live"])
    p.add_argument("--burn-window", type=int, default=21)
    p.add_argument("--beta-window", type=int, default=63)
    p.add_argument("--half-spread-bps", type=float, default=0.0,
                   help="optional spread-cost proxy for the attribution bridge")
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR),
                   help="research-lake output dir (prod paths are refused)")
    args = p.parse_args(argv)

    conn = bd.connect(args.db)
    try:
        statement = build_statement(
            conn,
            strategy_config=args.strategy_config,
            sleeve_log=args.sleeve_log,
            ohlcv_dir=args.ohlcv_dir,
            run_type=args.run_type,
            burn_window=args.burn_window,
            beta_window=args.beta_window,
            half_spread_bps=args.half_spread_bps,
        )
    finally:
        conn.close()
    paths = write_statement(statement, args.out_dir)

    b = statement["breaches"]
    print(
        f"risk_budget_statement: STATUS={statement['status']} as_of={statement['as_of']} "
        f"dd={_fmt(b['max_drawdown']['consumption'], pct=True)} "
        f"beta={_fmt(b['book_beta']['consumption'], pct=True)} "
        f"conc={_fmt(b['per_name_concentration']['consumption'], pct=True)} "
        f"sleeve={_fmt(b['sleeve_dd_sub_budget']['consumption'], pct=True)}"
    )
    for name, row in b.items():
        print(f"  {name:>24}: {row['status']:>8}  consumption={_fmt(row['consumption'], pct=True)}")
    print(f"markdown: {paths['markdown']}")
    print(f"json:     {paths['json']}")
    return statement["exit_code"]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
