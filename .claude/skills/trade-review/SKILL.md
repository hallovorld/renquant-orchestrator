---
name: trade-review
description: >-
  Independent, multi-lens professional review of proposed/placed orders or the live
  renquant-104 portfolio. Use when the user asks to evaluate/judge the quality of
  orders or the book, sanity-check what the model bought, or decide which positions
  to keep/trim/cut. Cross-checks the model with portfolio math + technicals + analyst
  consensus + fundamentals. Advisory only — never auto-cancels/resizes without confirmation.
---

# trade-review

Run an independent, sell-side-research-grade review of a set of orders (or the live
book / a ticker list). The 104 model + its WF/conviction gates are the *internal*
trust boundary; this skill is the *external* cross-check (portfolio + market + analyst
+ fundamentals) that catches what the gates miss — backwards sizing vs forward upside,
technically broken buys, over-concentration, cash drag.

## Setup
The scripts use the live Alpaca data/broker. Run them with the strategy venv and env:
```bash
cd /Users/renhao/git/github/RenQuant && set -a && source .env && set +a
PY=/Users/renhao/git/github/RenQuant/.venv/bin/python
SK=/Users/renhao/git/github/renquant-orchestrator/.claude/skills/trade-review/scripts
```

## Workflow

1. **Scope the names.** Determine the ticker set: (a) today's proposed/placed orders,
   (b) the full live book, or (c) a list the user gives. If unclear, ask.

2. **Portfolio math** — `"$PY" "$SK/portfolio_weights.py"` (read-only). Gives post-fill
   weights (% equity and % long-book), invested vs **cash %**, HHI and effective-N.
   Flag cash drag (under-deployment) and concentration explicitly.

3. **Technical** — `"$PY" "$SK/technical_battery.py" T1 T2 ...` (vs SPY). Per name:
   trend (vs SMA50/200), RSI14, 3m/6m return, **relative strength vs SPY**, realized
   vol, 52-week range position. Indicators are scale-invariant → trustworthy even when
   absolute prices look odd.

4. **Analyst / third-party** — WebSearch each name
   (`"<TICKER> stock analyst rating consensus price target <current month/year>"`).
   Extract: consensus rating (Buy/Hold/Sell counts), average / high / low price target,
   analyst count. **Reconcile the target against the account's quoted price** before
   computing implied upside (the feed can differ from public quotes; quote the upside
   off the account price the order fills at). Cite the sources.

5. **Fundamental** — business quality / moat, growth & margin profile, valuation
   context, key risks (from knowledge; flag that live multiples need confirmation).
   Phase 2: pull hard numbers from the financial-analysis MCP (FactSet/S&P/Morningstar)
   if the user authenticates.

6. **Synthesize.** Build one table: `ticker | weight% | technical(trend/RSI/RS/vol/52w)
   | analyst(rating, target, implied upside, n) | fundamental(quality/risk) | verdict`.
   Verdict per name = **keep / trim / cut** with a one-line reason combining the lenses.
   Then a portfolio-level read: is sizing aligned with forward upside? concentration?
   structure (momentum vs mean-reversion barbell)? cash drag? → recommended target
   weights / cut list.

## Guardrails
- **Advisory only.** Never cancel/resize orders without explicit user confirmation in
  the same turn. The scripts are read-only; only place/cancel via a separate, confirmed step.
- The **model is primary**; this skill *flags divergence* (e.g. "model overweights the
  names with the least analyst upside"), it does not override. The user decides on conflict.
- **Lead with the bottom line** (which to cut/keep) before the detail.
- Stamp data sources + the run timestamp so the recommendation is auditable later.
