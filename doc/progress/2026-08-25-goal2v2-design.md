# GOAL-2v2 design: stacked meta-model over base scores + state/macro trends

STATUS: design PR per the mandated workflow (direction → operator approval →
design doc → codex → implementation). Direction approved by the operator
2026-08-25 ("按这个做").

WHAT: `doc/design/2026-08-25-goal2v2-stacked-meta-model.md` — two-layer
stacked generalization: 3–5 NEW preregistered base models (momentum,
mean-reversion/quality, regime-specialists, optional vol) + PIT-clean macro
trend features (VIX, DGS10 trend, 2s10s, sector breadth) → xgb meta layer.
§0 freezes the operator's verbatim spec (two prior instantiations each
narrowed it; the second narrowing was caught only by the operator — the
verbatim section is the anti-drift device).

WHY the three GOAL-2 kills do not bind (§1): all three traced to EXISTING
legs' recipes being selected on the windows validation needs. This design's
recipes are frozen at prereg from literature + 2024–26 experience only —
exactly the merged h=20 design's own pass criterion — so 2016–19 train /
2020–23 one-shot eval stays clean, with ESS already measured (~16 blocks ≥
bar 12 [VERIFIED — #1045 §3]).

STAGES: A daily stack (now) / A′ 10-min backfill parallel ($0, Alpaca
aggregation; procures only, nothing consumes it before B) / B intraday
variant → plugs into S3-P4's existing scorer seam for 105 / C transformer
meta. Labels per #1045 r4 (NOT-DEMONSTRATED / UNDERPOWERED-NULL; NO-EFFECT
unavailable). Repo split: training internals → renquant-model; panel
assembly → renquant-pipeline; prereg/eval harness → orchestrator.

§4(b): no measurements claimed here beyond the reused #1045 ESS ceiling;
every Stage-A number arrives via its own prereg artifacts.
