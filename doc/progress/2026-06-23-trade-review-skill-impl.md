# trade-review skill — implementation

STATUS:   implemented (Phase 1). Follows the design merged in #169.
WHAT:     runnable `trade-review` skill — SKILL.md workflow + two read-only scripts
          (technical_battery.py, portfolio_weights.py); analyst lens via WebSearch.
WHY/DIR:  external PM-style cross-check of the model's orders/book — catches backwards
          sizing vs upside, technically broken buys, over-concentration, cash drag —
          none of which the WF/conviction gates see.
EVIDENCE: both scripts tested live on account 212830627: portfolio_weights shows the
          post-fill book (invested 22% / cash 78% / HHI 0.22 / eff_N 4.5); technical_battery
          reproduces the trend/RSI/RS/vol/52w used in the 2026-06-23 review (e.g. NFLX
          DOWN/RSI17/52w-0%, CSCO UP/RS+48%). `[VERIFIED — live run this session]`
NOTE:     skill lives under .claude/skills/ (force-added past the local .claude exclude;
          tracked normally in the repo for review). Phase 2 = financial-analysis MCP for
          hard fundamentals; optional daily-pipeline wiring is a separate decision.
