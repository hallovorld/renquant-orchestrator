# Analyst estimate-revision as a model feature (P1 design)

**Status:** design / not started in code. Real data acquisition is operator-gated
(financial-analysis MCP OAuth). 2026-06-24.

## Why now
On 2026-06-23 a multi-lens trade review of the live book found that the model's
own picks reconcile to **real** account prices, so the analyst lens is valid and
*disagrees with the model in a usable way*: the names the model buys on its
volatility tilt (PANW/CRWD, near analyst targets, +2–13%) have the **least**
forward analyst upside, while beaten-down names (AMZN +33–36%, AVGO +29–38%,
NFLX +54%, all Buy/Strong Buy) have the **most**. The model has near-zero
genuine IC in BULL_CALM and ranks on a vol/beta tilt; analyst estimate revisions
are an orthogonal, well-documented alpha that the model does not see.

This is the "expensive new-data bet" flagged in the model roadmap as the next
move after the cheap in-repo levers were exhausted (neutralization / fundmom /
trend-scan all rejected/inconclusive). The cheap proxy — realized
fundamental-momentum (#177) — was REJECTED, so analyst data is **not**
pre-justified by it and must clear its own validation.

## Data source (operator-gated)
Use a licensed point-in-time feed, NOT web scraping. The session already has the
**financial-analysis MCP** servers connected (FactSet / S&P Global / Morningstar
/ LSEG); each exposes `authenticate` + `complete_authentication`. The operator
OAuths once, then we pull PIT consensus + estimates + revisions for the
~142-name watchlist.

Web search (how the 2026-06-23 review got its numbers) is fine for a one-off
human cross-check but is **disqualified for training**: no point-in-time history
→ look-ahead leakage, and unreliable coverage.

## Candidate features (per ticker, per date, point-in-time)
1. `consensus_rating_ord` — Buy/Hold/Sell mapped to an ordinal/score.
2. `implied_upside` — mean target / price − 1 (priced off the same series the
   model + execution use).
3. `target_dispersion` — (high − low) / mean (forecast uncertainty).
4. `n_analysts` — coverage depth (also a confidence weight).
5. **`estimate_revision_*` — Δ(mean EPS/target estimate) over 1m/3m, and
   up/down-grade counts. THIS is the actual alpha** (post-revision drift:
   Womack 1996; Gleason–Lee 2003), not the static level.

## Hard constraints (non-negotiable)
- **PIT discipline:** train/validate only on the consensus *as it was known on
  each historical date*. Using today's consensus on past dates is leakage the
  WF gate will (and must) catch.
- **Validation before production:** a new feature group must pass the per-regime
  walk-forward + placebo gate **placebo-clean positive** before it goes live
  (see the embargo-leakage-floor caveat: trust placebo-clean DIFFERENCES, not
  absolute IC). No graduation on a single aggregate IC.
- **Coverage gaps:** small/thin names lack coverage → explicit missing handling
  (don't median-impute a revision signal into existence — that's the
  DataIntegrity failure mode in reverse).

## Integration options (decide after a first validation pass)
- **A. Feature group in the panel** — add the revision features to the
  alpha158+fund set, retrain, gate. Most direct; couples to the retrain cadence.
- **B. Orthogonal sizing/meta overlay** — keep the model as-is, use
  estimate-revision as a conviction multiplier / meta-label on the RAW model
  (the P&L winner). Lower blast radius; testable as an overlay first.

Given the model's vol-tilt weakness, **B first** (overlay, observe, then decide
on A) mirrors the WARN-first discipline used for the data-integrity gate.

## Plan
1. **(operator)** OAuth the financial-analysis MCP (FactSet or S&P).
2. Pull PIT consensus + revisions for the watchlist → a `data/analyst_*` panel
   with the same date index discipline as `sec_fundamentals_daily`.
3. Build the features (above) with explicit missing handling.
4. Validate placebo-clean through the per-regime WF gate as an **overlay** on the
   RAW model. Only if positive: design integration A.
5. Wire freshness + completeness into the existing controls (P-FUND-FRESHNESS
   sibling + DataIntegrityJob dimension) so analyst data can't silently rot or
   impute the way fundamentals just did.

## Open decisions for the operator
- Which feed (FactSet vs S&P Global vs Morningstar)?
- Overlay (B) vs in-panel (A) for the first validation?
