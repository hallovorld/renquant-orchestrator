# Design: `trade-review` — independent multi-lens order/portfolio review skill

STATUS: design for review (no implementation yet — per operator: describe → discuss → PR to Codex → then implement).

## Motivation

The 104 model decides what to buy; the WF gate + conviction gate are **model-internal**
trust boundaries. They do NOT catch portfolio- and market-level mistakes. The
2026-06-23 XGB deploy made this concrete — the model's order set (CRWD/CSCO/AMZN/
NFLX/ZM, post-fill weights) had, on independent review:

- **inverted sizing vs forward upside** — the 3 biggest positions (CRWD/PANW/CSCO,
  73% of the long book) sat at analyst targets (+5–10% upside), while the 3 smallest
  (AMZN/NFLX/ZM, 26%) had the most upside (+27–56%);
- a **technically broken name** bought near a 52-week low with RSI 17 (NFLX);
- **concentration** — CRWD+PANW = 53% of the book in two correlated (ρ≈0.84) security
  names;
- **78% cash** while nominally "trading" (a sizing/deployment gap, not a name gap).

None of that is visible to the model's own gates. We want an **independent,
multi-source professional cross-check** — the kind a discretionary PM/analyst runs —
that can be applied to the model's orders before/after they trade.

## What it does

Given a set of proposed orders (or the live portfolio / an arbitrary ticker list),
produce a sell-side-research-grade review:

1. **Portfolio math** — post-fill weights, HHI / effective-N, sector + sub-sector
   exposure, cash %, gross/net, (optional) portfolio beta.
2. **Technical** (per name, from real price history) — trend (price vs SMA50/200),
   momentum (RSI14, 3m/6m return), relative strength vs SPY, realized vol, 52-week
   range position. (All scale-invariant → robust to absolute-price data quirks.)
3. **Analyst / third-party** (per name) — consensus rating, average / high / low
   price target, implied upside, analyst count.
4. **Fundamental** (per name) — business quality / moat, growth & margin profile,
   valuation context, key risks.
5. **Synthesis** — per-name **keep / trim / cut** + a portfolio-level read (is sizing
   aligned with upside? concentration? barbell/structure? cash drag?) + target weights.
6. **Output** — a structured report (table + findings + recommendation) and,
   optionally, the concrete cancel/resize order list.

## Data sources (phased)

| Lens | Phase 1 (now) | Phase 2 (later) |
|---|---|---|
| Technical | Alpaca price history (creds in `.env`) | — |
| Portfolio | Alpaca broker (positions/equity/open orders) | — |
| Analyst | WebSearch (MarketBeat / TipRanks / StockAnalysis) | financial-analysis MCP (FactSet / S&P / Morningstar) |
| Fundamental | WebSearch + model knowledge | financial-analysis MCP (hard P&L / growth / margins) |

Web is fast, free, and good-enough to start; the MCP path gives authoritative numbers
but needs auth/subscription, so it is a later upgrade behind the same skill interface.

## Design decisions (please review)

1. **Data source:** start with WebSearch; upgrade analyst/fundamental to the MCP later
   behind the same output contract. *(recommend)*
2. **Position in the workflow:** ship as a **standalone** skill first (`/trade-review`,
   run manually). Only after it proves value, consider wiring it as an **advisory
   post-decision step** in the daily pipeline, and *separately* debate whether it ever
   becomes a **pre-trade gate**. *(recommend: standalone first; no auto-gate yet)*
3. **Autonomy:** **advisory only** by default — it never cancels/resizes orders without
   explicit operator confirmation. *(recommend)*
4. **Model vs. review on conflict:** the model is **primary** (it carries the WF-gated
   edge). This skill is an **independent overlay** that *flags divergence* (e.g.
   "model overweights names with the least analyst upside"), not an override. The
   operator decides on conflict. *(recommend)*
5. **Scope of input:** (a) today's proposed/placed orders, (b) the full live book,
   (c) an arbitrary ticker list. Support all three.

## Structure

```
.claude/skills/trade-review/
  SKILL.md                       # workflow the skill follows
  scripts/technical_battery.py   # Alpaca price-history -> trend/RSI/RS/vol/52w
  scripts/portfolio_weights.py   # broker positions+orders -> post-fill weights/HHI
  # analyst + fundamental: WebSearch in-skill (Phase 1); MCP adapter (Phase 2)
```

## Output contract (stable across data-source phases)

Per-name row: `ticker | weight% | technical{trend,RSI,RS6m,vol,52w} |
analyst{rating,target,upside,n} | fundamental{quality,growth,risk} | verdict{keep|trim|cut, reason}`.
Portfolio block: `cash%, HHI, effective_N, sub-sector mix, sizing-vs-upside flag,
concentration flag, recommended target weights, optional cancel/resize orders`.

## Open questions for Codex / operator

- **Home:** orchestrator repo `.claude/skills/` (version-controlled, Codex-reviewable,
  reproducible) vs the operator's global `~/.claude/skills/`. *(recommend repo)*
- **Caching:** cache analyst data per ticker/day to avoid re-searching the same names?
- **Risk depth:** qualitative sub-sector/beta read (Phase 1) vs a real factor-model
  exposure decomposition (later)?
- **Provenance:** every review stamps its data sources + timestamps so a recommendation
  is auditable later (consistent with the repo's evidence-block norm).
