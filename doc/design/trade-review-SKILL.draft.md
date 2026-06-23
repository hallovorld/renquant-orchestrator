---
name: trade-review
description: >-
  Independent, multi-lens professional review of proposed orders or the live
  portfolio for renquant-104. Cross-checks the model's trade decisions with
  portfolio math, technicals, analyst consensus, and fundamentals, and returns a
  keep/trim/cut recommendation. DRAFT — design under review (doc/design/2026-06-23-trade-review-skill.md);
  scripts not yet implemented.
---

# trade-review (DRAFT — design under review)

Run an independent, sell-side-research-grade review of a set of orders (or the live
book / a ticker list). The 104 model + WF/conviction gates are model-internal; this
skill is the **external** cross-check (portfolio + market + analyst + fundamentals).

> Status: this SKILL.md captures the intended workflow for Codex review. The supporting
> scripts under `scripts/` are NOT implemented yet — see the design doc for the phased
> plan and open questions. Do not treat this as runnable until the implementation PR lands.

## Inputs
One of: (a) today's proposed/placed orders, (b) the full live portfolio, (c) a ticker list.
Plus account equity/cash (from the broker).

## Workflow
1. **Portfolio math** — `scripts/portfolio_weights.py`: post-fill weights, HHI / effective-N,
   sub-sector mix, cash %, gross/net.
2. **Technical** — `scripts/technical_battery.py` (Alpaca price history): per name, trend
   (vs SMA50/200), RSI14, 3m/6m return, relative strength vs SPY, realized vol, 52-week
   range position.
3. **Analyst** — WebSearch each name (MarketBeat / TipRanks / StockAnalysis): consensus
   rating, avg/high/low price target, implied upside, analyst count. (Phase 2: FactSet/S&P MCP.)
4. **Fundamental** — business quality/moat, growth & margin, valuation context, key risks.
   (Phase 2: hard numbers from the financial-analysis MCP.)
5. **Synthesize** — per name: **keep / trim / cut** with a one-line reason combining the
   lenses. Portfolio level: is sizing aligned with forward upside? concentration? structure
   (momentum vs mean-reversion barbell)? cash drag? → recommended target weights.
6. **Output** — the structured table + portfolio findings + recommendation. Optionally the
   concrete cancel/resize order list. **Advisory only — never auto-execute without operator
   confirmation.** Stamp data sources + timestamps for auditability.

## Guardrails
- The model is primary; this skill **flags divergence**, it does not override.
- Read-only on the broker except when the operator explicitly approves a cancel/resize.
- Technicals are scale-invariant (robust to absolute-price data quirks); analyst targets
  must be reconciled against the account's quoted price before quoting upside.
