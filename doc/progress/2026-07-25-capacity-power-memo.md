# 2026-07-25 — Capacity + power reconciliation memo (rescued from #574; evidence committed)

STATUS:    research memo for review; no code, no production surface
WHAT:      `doc/research/2026-07-24-capacity-and-power-reconciliation.md` (§1-7) +
           committed evidence `doc/research/evidence/2026-07-24-capacity-memo/`
           (6 result JSONs + the 5 analysis scripts that produced them).
WHY/DIR:   One synthesis that reconciles the flat live P&L, the 83%-win/0.89-payoff
           signature, the WF-gate chronic borderline rejections, and the VERDICTS
           NULL streak — and derives where marginal research effort pays.
EVIDENCE (§4(b), per memo section):
  §1-5 capacity/power:
    artifact:      evidence/2026-07-24-capacity-memo/horizon_matched_result.json
                   (matched-embargo IC grid) + audit_result.json (self-audit of the
                   retracted precursor study) + console-recorded anchor repro
                   (mean_ic 0.0488 vs live artifact 0.0533, ANCHOR check in the
                   relocated factorial executor, model#67)
    prod or exp:   EXPERIMENT, read-only; live-book stats cited from the 07-24
                   daily_104 log (equity $10,609, drawdown 4.23%) and standing memos
    existing data: TC=0.4 cited to doc/research/2026-07-02-ic-ceiling-institutional-gap-107-route.md
    best-known?:   first fundamental-law decomposition of this book; ρ=0.25 is the
                   single assumed number (sensitivity 0.15-0.35 reported in-memo)
    scope:         survivorship panel ⇒ all LEVELS are upper bounds; block-t and
                   paired statistics are the robust parts
  §6 signal identity:
    artifact:      evidence/.../depth_probe_result.json (+ depth_probe.py)
    scope:         "clean IC block-t=1.15 (n=35); 62% of top-10 spread from >±100%
                   movers; 2026 YTD clean IC +0.0015" — measured on the production
                   recipe rebuilt in-harness, NOT on the live artifact's own scores
  §7 structural decomposition:
    artifact:      evidence/.../structural_decomposition_result.json
                   (+ structural_decomposition.py); placebo_clean_all172.json;
                   feature_redundancy_result.json
    prod or exp:   exit-stack counterfactual uses PRODUCTION strategy_config.json
                   BULL_CALM stop params on real OHLCV paths; read-only
    best-known?:   DGTW adjustment is the standard skill/characteristics separation;
                   first application on this book
    scope:         "DGTW skill +0.243/60d block-t=+2.92 (winsorized t=+1.70 — the
                   certification is tail-dependent); stop-layer cost −2.69pp/pos/60d
                   is a LOWER bound (model exits excluded)"
NEXT:      none from this PR — the memo authorizes nothing; follow-ons live in
           model#67 (factorial), model#68 (objective blend), base-data#51 (PIT audit).
           Verdicts, when earned, register in VERDICTS.md here.
